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


def replace_in_function(text, function_anchor, old, new, label):
    function_pos = text.find(function_anchor)
    if function_pos < 0:
        raise SystemExit(f"{label}: function not found")
    next_function = text.find("\ndef ", function_pos + len(function_anchor))
    if next_function < 0:
        next_function = len(text)
    segment = text[function_pos:next_function]
    if new in segment:
        return text
    if old not in segment:
        raise SystemExit(f"{label}: expected anchor not found in function")
    return text[:function_pos] + segment.replace(old, new, 1) + text[next_function:]


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
    try:
        normalized = normalize_parameters(material_type, parameters)
    except ValueError:
        return None

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

    owner_guard = '''    if not document or document.user_id != user_id or document.is_removed:\n        return jsonify({"error": "Document not found"}), 404\n'''
    shared_guard = '''    if not document or not _can_study_document(user_id, document):\n        return jsonify({"error": "Document not found"}), 404\n'''

    function_names = {
        "summary": "summarize_document(document_id):",
        "quiz": "quiz_document(document_id):",
        "flashcards": "flashcards_document(document_id):",
        "mindmap": "mindmap_document(document_id):",
    }
    for route_name, marker in markers.items():
        material_type = material_types[route_name]
        if route_name in ("flashcards", "mindmap"):
            s = replace_in_function(
                s,
                f'def {function_names[route_name]}',
                owner_guard,
                shared_guard,
                f"{route_name} study access guard",
            )
        replay = f'''    if document.user_id != user_id:\n        shared = _published_ready_material_for_viewer(\n            user_id, document, "{material_type}", _ai_generation_parameters_from_request()\n        )\n        if not shared:\n            return jsonify({{"error": "Published {route_name.replace('_', ' ')} has not been generated yet"}}), 404\n        content, material = shared\n        result = _published_material_response(user_id, content, material)\n        return jsonify({{\n            "material_id": result["material_id"],\n            "reused": True,\n            "{route_name}": result["payload"],\n        }}), 200\n\n'''
        s = replace_in_function(s, f'def {function_names[route_name]}', marker, marker + replay, f"{route_name} published replay")

    for route_name in ("quiz", "flashcards"):
        function_anchor = f'def complete_{route_name}(document_id, material_id):'
        s = replace_in_function(
            s,
            function_anchor,
            owner_guard,
            shared_guard,
            f"complete_{route_name} study access guard",
        )
        route_pos = s.find(function_anchor)
        next_function = s.find("\ndef ", route_pos + len(function_anchor))
        if next_function < 0:
            next_function = len(s)
        segment = s[route_pos:next_function]
        material_lookup = '''    material = db.session.get(GeneratedMaterial, material_id)\n'''
        if material_lookup not in segment:
            raise SystemExit(f"complete_{route_name}: material lookup not found")
        shared_material_guard = f'''    if document.user_id != user_id and (material.scope != "shared" or material.owner_user_id is not None):\n        return jsonify({{"error": "{route_name.capitalize()} material not found"}}), 404\n'''
        anchor = '''        or material.status != "ready"\n    ):\n        return jsonify({"error": "''' + ("Quiz" if route_name == "quiz" else "Flashcard") + ''' material not found"}), 404\n'''
        if shared_material_guard not in segment:
            if anchor not in segment:
                raise SystemExit(f"complete_{route_name}: material validation anchor not found")
            segment = segment.replace(anchor, anchor + shared_material_guard, 1)
            s = s[:route_pos] + segment + s[next_function:]

    APP.write_text(s)


if __name__ == "__main__":
    main()
