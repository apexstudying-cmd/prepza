from pathlib import Path

APP = Path("app.py")


def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"{label}: expected anchor not found")
    if text.count(old) != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def main():
    s = APP.read_text()

    helper_anchor = '@app.route("/documents/<int:document_id>/summarize", methods=["POST"])\n'
    helper = '''def _published_ready_material_for_viewer(user_id, document, material_type, parameters):
    """Return an approved document's READY shared artifact without generation."""
    if not document or document.user_id == user_id:
        return None
    if not _can_study_document(user_id, document):
        return None
    if not document.document_content_id:
        return None

    content = db.session.get(DocumentContent, document.document_content_id)
    if not content or content.status != "ready":
        return None

    from ai_reusable_generation import normalize_parameters
    normalized = normalize_parameters(material_type, parameters)

    candidates = (
        GeneratedMaterial.query
        .filter_by(
            document_content_id=content.id,
            material_type=material_type,
            status="ready",
            scope="shared",
        )
        .order_by(GeneratedMaterial.updated_at.desc())
        .all()
    )
    for material in candidates:
        if material.owner_user_id is None and (material.generation_parameters or {}) == normalized and material.payload:
            return content, material
    return None


def _published_material_response(user_id, content, material):
    record_document_studied(user_id, content.id)
    db.session.commit()
    return {
        "material_id": material.id,
        "reused": True,
        "payload": json.loads(material.payload),
    }


'''
    s = replace_once(s, helper_anchor, helper + helper_anchor, "published replay helper")

    private_materials_block = '''    materials = []
    if content:
        materials = [
            {"type": m.material_type, "status": m.status}
            for m in GeneratedMaterial.query.filter_by(document_content_id=content.id).all()
        ]
'''
    shared_materials_block = '''    materials = []
    if content:
        material_query = GeneratedMaterial.query.filter_by(document_content_id=content.id)
        if document.user_id != user_id:
            material_query = material_query.filter_by(status="ready", scope="shared", owner_user_id=None)
        materials = [
            {"type": m.material_type, "status": m.status}
            for m in material_query.all()
        ]
'''
    s = replace_once(s, private_materials_block, shared_materials_block, "published material visibility")

    markers = {
        "summary": '    if not document.document_content_id:\n        return jsonify({"error": "Document has no content to summarize"}), 400\n\n',
        "quiz": '    if not document.document_content_id:\n        return jsonify({"error": "Document has no content to quiz"}), 400\n\n',
        "flashcards": '    if not document.document_content_id:\n        return jsonify({"error": "Document has no content to generate flashcards from"}), 400\n\n',
        "mindmap": '    if not document.document_content_id:\n        return jsonify({"error": "Document has no content to generate a mind map from"}), 400\n\n',
    }
    material_types = {
        "summary": "summary",
        "quiz": "quiz",
        "flashcards": "flashcards",
        "mindmap": "mind_map",
    }

    for route_name, marker in markers.items():
        material_type = material_types[route_name]
        replay = f'''    if document.user_id != user_id:
        shared = _published_ready_material_for_viewer(
            user_id, document, "{material_type}", _ai_generation_parameters_from_request()
        )
        if not shared:
            return jsonify({{"error": "Published {route_name.replace('_', ' ')} has not been generated yet"}}), 404
        content, material = shared
        result = _published_material_response(user_id, content, material)
        return jsonify({{
            "material_id": result["material_id"],
            "reused": True,
            "{route_name}": result["payload"],
        }}), 200

'''
        s = replace_once(s, marker, marker + replay, f"{route_name} published replay")

    # Published students may complete a shared READY quiz/flashcard artifact.
    # This records the viewer's own attempt/session and XP; it never grants
    # generation rights or touches the owner's quota.
    completion_access = '''    document = db.session.get(Document, document_id)\n    if not document or document.user_id != user_id or document.is_removed:\n        return jsonify({"error": "Document not found"}), 404\n'''
    shared_access = '''    document = db.session.get(Document, document_id)\n    if not _can_study_document(user_id, document):\n        return jsonify({"error": "Document not found"}), 404\n'''
    for func in ("complete_quiz", "complete_flashcards"):
        marker = f"def {func}(document_id, material_id):"
        start = s.find(marker)
        if start < 0:
            raise SystemExit(f"{func} not found")
        pos = s.find(completion_access, start)
        if pos < 0:
            if shared_access not in s[start:]:
                raise SystemExit(f"{func} access block not found")
        else:
            s = s[:pos] + shared_access + s[pos + len(completion_access):]
        material_type = "quiz" if func == "complete_quiz" else "flashcards"
        validation = f'''        or material.material_type != "{material_type}"\n        or material.status != "ready"\n'''
        secure_validation = f'''        or material.material_type != "{material_type}"\n        or material.status != "ready"\n        or (document.user_id != user_id and (material.scope != "shared" or material.owner_user_id is not None))\n'''
        if secure_validation not in s[start:]:
            if validation not in s[start:]:
                raise SystemExit(f"{func} material validation block not found")
            s = s.replace(validation, secure_validation, 1)

    APP.write_text(s)


if __name__ == "__main__":
    main()
