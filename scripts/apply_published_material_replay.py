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
    """Return an approved document's READY artifact without allowing generation.

    Published study materials are replayable shared artifacts. A non-owner may
    consume an artifact that already exists for the document, but must never
    become the generation owner merely because a fingerprint is missing.
    Parameter matching prevents a published viewer from receiving a different
    variant when a feature supports explicit generation parameters.
    """
    if not document or document.user_id == user_id:
        return None
    if not _can_study_document(user_id, document):
        return None
    if not document.document_content_id:
        return None

    content = db.session.get(DocumentContent, document.document_content_id)
    if not content or content.status != "ready":
        return None

    try:
        from ai_reusable_generation import normalize_parameters
        normalized = normalize_parameters(material_type, parameters)
    except ValueError:
        raise

    candidates = (
        GeneratedMaterial.query
        .filter_by(
            document_content_id=content.id,
            material_type=material_type,
            status="ready",
        )
        .order_by(GeneratedMaterial.updated_at.desc())
        .all()
    )
    for material in candidates:
        stored = material.generation_parameters or {}
        if stored == normalized and material.payload:
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

    routes = [
        ("summary", "summary", "summary"),
        ("quiz", "quiz", "quiz"),
        ("flashcards", "flashcards", "flashcards"),
        ("mindmap", "mind_map", "mindmap"),
    ]

    for route_name, material_type, response_key in routes:
        if route_name == "mindmap":
            marker = '    if not document.document_content_id:\n        return jsonify({"error": "Document has no content to generate a mind map from"}), 400\n\n'
        else:
            marker = f'    if not document.document_content_id:\n        return jsonify({{"error": "Document has no content to {route_name}{{" if False else ""}}"}}), 400\n\n'
            # The exact existing messages differ, so use route-specific anchors below.
        if route_name == "summary":
            marker = '    if not document.document_content_id:\n        return jsonify({"error": "Document has no content to summarize"}), 400\n\n'
        elif route_name == "quiz":
            marker = '    if not document.document_content_id:\n        return jsonify({"error": "Document has no content to quiz"}), 400\n\n'
        elif route_name == "flashcards":
            marker = '    if not document.document_content_id:\n        return jsonify({"error": "Document has no content to generate flashcards from"}), 400\n\n'

        replay = f'''    if document.user_id != user_id:
        shared = _published_ready_material_for_viewer(
            user_id, document, "{material_type}", _ai_generation_parameters_from_request()
        )
        if not shared:
            return jsonify({{"error": "Published {response_key.replace('_', ' ')} has not been generated yet"}}), 404
        content, material = shared
        result = _published_material_response(user_id, content, material)
        return jsonify({{
            "material_id": result["material_id"],
            "reused": True,
            "{response_key}": result["payload"],
        }}), 200

'''
        s = replace_once(s, marker, marker + replay, f"{route_name} published replay")

    APP.write_text(s)


if __name__ == "__main__":
    main()
