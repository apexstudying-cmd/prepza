from pathlib import Path
import re

APP = Path("app.py")


def _route_pattern(route_anchor):
    match = re.search(r'@app\.route\(["\']([^"\']+)["\']', route_anchor)
    if not match:
        raise SystemExit(f"invalid route anchor: {route_anchor}")
    path = re.escape(match.group(1))
    return re.compile(rf'@app\.route\(\s*["\']{path}["\']\s*(?:,\s*methods\s*=\s*\[[^\]]+\])?\s*\)')


def route_segment(text, route_anchor):
    exact = text.find(route_anchor)
    if exact >= 0:
        route_pos = exact
        route_end = exact + len(route_anchor)
    else:
        match = _route_pattern(route_anchor).search(text)
        if not match:
            raise SystemExit(f"route not found: {route_anchor}")
        route_pos = match.start()
        route_end = match.end()
    next_route = text.find("@app.route(", route_end)
    if next_route < 0:
        next_route = len(text)
    return route_pos, next_route, text[route_pos:next_route]


def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"{label}: expected anchor not found")
    if text.count(old) != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def replace_in_route(text, route_anchor, old, new, label):
    route_pos, next_route, segment = route_segment(text, route_anchor)
    if new in segment:
        return text
    if old not in segment:
        raise SystemExit(f"{label}: expected anchor not found in route")
    return text[:route_pos] + segment.replace(old, new, 1) + text[next_route:]


def replace_function_guard_in_route(text, route_anchor, new_guard, label):
    route_pos, next_route, segment = route_segment(text, route_anchor)
    owner_guard = '''    if not document or document.user_id != user_id or document.is_removed:\n        return jsonify({"error": "Document not found"}), 404\n'''
    for duplicate in (new_guard + owner_guard, owner_guard + new_guard):
        if duplicate in segment:
            segment = segment.replace(duplicate, new_guard, 1)
            return text[:route_pos] + segment + text[next_route:]
    if new_guard in segment:
        return text
    guard_start = segment.find("    if not document")
    guard_end = segment.find("    if not document.document_content_id:", guard_start)
    if guard_start < 0 or guard_end < 0:
        raise SystemExit(f"{label}: document guard shape not found")
    segment = segment[:guard_start] + new_guard + segment[guard_end:]
    return text[:route_pos] + segment + text[next_route:]


PUBLISHED_REPLAY_HELPER = """def _published_ready_material_for_viewer(user_id, document, material_type, parameters):
    '''Return an approved document's READY shared artifact without generation.'''
    if not document or document.user_id == user_id:
        return None
    if not _can_study_document(user_id, document):
        return None
    if not document.document_content_id:
        return None
    content = db.session.get(DocumentContent, document.document_content_id)
    if not content or content.status != "ready":
        return None
    from ai_artifact_fingerprint import GENERATION_VERSION, build_generation_fingerprint
    from ai_reusable_generation import PROMPT_VERSIONS, SCHEMA_VERSIONS, normalize_parameters
    try:
        normalized = normalize_parameters(material_type, parameters)
        fingerprint = build_generation_fingerprint(
            content_hash=content.content_hash,
            material_type=material_type,
            parameters=normalized,
            prompt_version=PROMPT_VERSIONS[material_type],
            schema_version=SCHEMA_VERSIONS[material_type],
            scope="shared",
            owner_user_id=None,
        )
    except (KeyError, ValueError):
        return None
    material = GeneratedMaterial.query.filter_by(
        generation_fingerprint=fingerprint,
        document_content_id=content.id,
        material_type=material_type,
        status="ready",
        scope="shared",
        owner_user_id=None,
        generation_version=GENERATION_VERSION,
    ).first()
    if not material or not material.payload:
        return None
    return content, material


"""

PUBLISHED_REPLAY_RESPONSE = """def _published_material_response(user_id, content, material):
    record_document_studied(user_id, content.id)
    db.session.commit()
    return {
        "material_id": material.id,
        "reused": True,
        "payload": json.loads(material.payload),
    }


"""


def _remove_function_definitions(source, marker):
    return re.sub(rf"(?ms)^def {re.escape(marker)}\(.*?(?=^def )", "", source)


def install_published_replay_helpers(s):
    s = _remove_function_definitions(s, "_published_ready_material_for_viewer")
    s = _remove_function_definitions(s, "_published_material_response")
    function_pos = s.find("def summarize_document(document_id):")
    if function_pos < 0:
        raise SystemExit("summary function insertion anchor not found")
    route_pos = s.rfind("@app.route(", 0, function_pos)
    if route_pos < 0:
        raise SystemExit("summary route decorator insertion anchor not found")
    return s[:route_pos] + PUBLISHED_REPLAY_HELPER + PUBLISHED_REPLAY_RESPONSE + s[route_pos:]


def main():
    s = install_published_replay_helpers(APP.read_text())
    private_materials_block = '''    materials = []\n    if content:\n        materials = [\n            {"type": m.material_type, "status": m.status}\n            for m in GeneratedMaterial.query.filter_by(document_content_id=content.id).all()\n        ]\n'''
    shared_materials_block = '''    materials = []\n    if content:\n        material_query = GeneratedMaterial.query.filter_by(document_content_id=content.id)\n        if document.user_id != user_id:\n            material_query = material_query.filter_by(status="ready", scope="shared", owner_user_id=None)\n        materials = [\n            {"type": m.material_type, "status": m.status}\n            for m in material_query.all()\n        ]\n'''
    s = replace_once(s, private_materials_block, shared_materials_block, "published material visibility")

    routes = {
        "summary": '@app.route("/documents/<int:document_id>/summarize", methods=["POST"])',
        "quiz": '@app.route("/documents/<int:document_id>/quiz", methods=["POST"])',
        "flashcards": '@app.route("/documents/<int:document_id>/flashcards", methods=["POST"])',
        "mindmap": '@app.route("/documents/<int:document_id>/mindmap", methods=["POST"])',
    }
    markers = {
        "summary": '    if not document.document_content_id:\n        return jsonify({"error": "Document has no content to summarize"}), 400\n\n',
        "quiz": '    if not document.document_content_id:\n        return jsonify({"error": "Document has no content to quiz"}), 400\n\n',
        "flashcards": '    if not document.document_content_id:\n        return jsonify({"error": "Document has no content to generate flashcards from"}), 400\n\n',
        "mindmap": '    if not document.document_content_id:\n        return jsonify({"error": "Document has no content to generate a mind map from"}), 400\n\n',
    }
    types = {"summary": "summary", "quiz": "quiz", "flashcards": "flashcards", "mindmap": "mind_map"}
    shared_guard = '''    if not document or not _can_study_document(user_id, document):\n        return jsonify({"error": "Document not found"}), 404\n'''

    for name, marker in markers.items():
        route = routes[name]
        if name in ("flashcards", "mindmap"):
            s = replace_function_guard_in_route(s, route, shared_guard, f"{name} study access guard")
        replay = f'''    if document.user_id != user_id:\n        shared = _published_ready_material_for_viewer(\n            user_id, document, "{types[name]}", _ai_generation_parameters_from_request()\n        )\n        if not shared:\n            return jsonify({{"error": "Published {name.replace('_', ' ')} has not been generated yet"}}), 404\n        content, material = shared\n        result = _published_material_response(user_id, content, material)\n        return jsonify({{\n            "material_id": result["material_id"],\n            "reused": True,\n            "{name}": result["payload"],\n        }}), 200\n\n'''
        s = replace_in_route(s, route, marker, marker + replay, f"{name} published replay")

    for name, route in {
        "quiz": '@app.route("/documents/<int:document_id>/quiz/<int:material_id>/complete", methods=["POST"])',
        "flashcards": '@app.route("/documents/<int:document_id>/flashcards/<int:material_id>/complete", methods=["POST"])',
    }.items():
        s = replace_function_guard_in_route(s, route, shared_guard, f"complete_{name} study access guard")
        route_pos, next_route, segment = route_segment(s, route)
        if '    material = db.session.get(GeneratedMaterial, material_id)\n' not in segment:
            raise SystemExit(f"complete_{name}: material lookup not found")
        label = "Quiz" if name == "quiz" else "Flashcard"
        shared_material_guard = f'''    if document.user_id != user_id and (material.scope != "shared" or material.owner_user_id is not None):\n        return jsonify({{"error": "{label} material not found"}}), 404\n'''
        if shared_material_guard not in segment:
            anchor = f'''        or material.status != "ready"\n    ):\n        return jsonify({{"error": "{label} material not found"}}), 404\n'''
            if anchor not in segment:
                raise SystemExit(f"complete_{name}: material validation anchor not found")
            segment = segment.replace(anchor, anchor + shared_material_guard, 1)
            s = s[:route_pos] + segment + s[next_route:]

    APP.write_text(s)


if __name__ == "__main__":
    main()
