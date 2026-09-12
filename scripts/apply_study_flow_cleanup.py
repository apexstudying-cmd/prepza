from pathlib import Path

APP = Path("app.py")


def normalize_podcast_script_route(s):
    route_pos = s.find('def podcast_script_document(document_id):')
    if route_pos < 0:
        raise SystemExit("podcast script route not found")
    start = '    if document.user_id != user_id:\n'
    start_pos = s.find(start, route_pos)
    end = '    try:\n        result = ai_service.generate_document_podcast_script(\n'
    end_pos = s.find(end, start_pos)
    if start_pos < 0 or end_pos < 0:
        raise SystemExit("podcast script published branch boundaries not found")
    canonical = '''    if document.user_id != user_id:\n        material = GeneratedMaterial.query.filter_by(\n            document_content_id=document.document_content_id,\n            material_type="podcast",\n            status="ready",\n            scope="shared",\n            owner_user_id=None,\n        ).first()\n        if not material or not material.payload:\n            return jsonify({"error": "Podcast has not been published yet"}), 404\n        record_document_studied(user_id, content.id)\n        db.session.commit()\n        return jsonify({\n            "material_id": material.id,\n            "reused": True,\n            "podcast": json.loads(material.payload),\n        }), 200\n\n'''
    return s[:start_pos] + canonical + s[end_pos:]


def normalize_podcast_audio_post(s):
    route_pos = s.find('def trigger_podcast_audio(document_id):')
    if route_pos < 0:
        raise SystemExit("podcast audio POST route not found")
    start = '    document = db.session.get(Document, document_id)\n'
    marker = '@app.route("/documents/<int:document_id>/podcast-audio")\n'
    first = s.find(start, route_pos)
    stop = s.find(marker, first)
    if first < 0 or stop < 0:
        raise SystemExit("podcast audio POST boundaries not found")
    segment = s[first:stop]
    guard = '''    if document.user_id != user_id:\n        return jsonify({"error": "Podcast audio is not ready yet"}), 409\n\n'''
    if guard not in segment:
        raise SystemExit("podcast audio synthesis guard not found")
    first_guard = segment.find(guard)
    segment = segment[:first_guard + len(guard)] + segment[first_guard + len(guard):].replace(guard, "")
    return s[:first] + segment + s[stop:]


def normalize_podcast_audio_get(s):
    marker = '@app.route("/documents/<int:document_id>/podcast-audio")\n'
    start = s.find(marker)
    if start < 0:
        raise SystemExit("podcast audio GET route not found")
    body_start = s.find('    document = db.session.get(Document, document_id)\n', start)
    if body_start < 0:
        raise SystemExit("podcast audio GET document lookup not found")
    lookup = '    if document.user_id == user_id:\n'
    lookup_pos = s.find(lookup, body_start)
    if lookup_pos < 0:
        raise SystemExit("podcast audio GET material lookup not found")
    old_guard = s[body_start:lookup_pos]
    old_owner = '''    document = db.session.get(Document, document_id)\n    if not document or document.user_id != user_id or document.is_removed:\n        return jsonify({"error": "Document not found"}), 404\n\n'''
    new_guard = '''    document = db.session.get(Document, document_id)\n    if not _can_study_document(user_id, document):\n        return jsonify({"error": "Document not found"}), 404\n\n'''
    if old_owner in old_guard:
        return s[:body_start] + new_guard + s[lookup_pos:]
    if new_guard in old_guard:
        return s
    raise SystemExit("podcast audio GET access guard shape not recognized")


def normalize_podcast_audio_get_shared_lookup(s):
    marker = '@app.route("/documents/<int:document_id>/podcast-audio")\n'
    start = s.find(marker)
    if start < 0:
        raise SystemExit("podcast audio GET route not found")
    end = s.find('\n@app.route(', start + len(marker))
    if end < 0:
        end = len(s)
    segment = s[start:end]
    old = '''        material = GeneratedMaterial.query.filter_by(\n            document_content_id=document.document_content_id,\n            material_type="podcast",\n            status="ready",\n        ).first()'''
    new = '''        material = GeneratedMaterial.query.filter_by(\n            document_content_id=document.document_content_id,\n            material_type="podcast",\n            status="ready",\n            scope="shared",\n            owner_user_id=None,\n        ).first()'''
    if new in segment:
        return s
    if old not in segment:
        raise SystemExit("podcast audio GET shared lookup shape not found")
    return s[:start] + segment.replace(old, new, 1) + s[end:]


def normalize_document_rename_owner(s):
    marker = '@app.route("/documents/<int:document_id>", methods=["PATCH"])\n'
    start = s.find(marker)
    if start < 0:
        raise SystemExit("document rename route not found")
    end = s.find('@app.route(', start + len(marker))
    if end < 0:
        end = len(s)
    segment = s[start:end]
    shared_guard = '''    document = db.session.get(Document, document_id)\n    if not _can_study_document(user_id, document):\n        return jsonify({"error": "Document not found"}), 404\n'''
    owner_guard = '''    document = db.session.get(Document, document_id)\n    if not document or document.user_id != user_id or document.is_removed:\n        return jsonify({"error": "Document not found"}), 404\n'''
    if owner_guard in segment:
        return s
    if shared_guard not in segment:
        raise SystemExit("document rename access guard shape not found")
    return s[:start] + segment.replace(shared_guard, owner_guard, 1) + s[end:]


def normalize_completion_guards(s):
    routes = (
        '@app.route("/documents/<int:document_id>/quiz/<int:material_id>/complete", methods=["POST"])',
        '@app.route("/documents/<int:document_id>/flashcards/<int:material_id>/complete", methods=["POST"])',
    )
    guard = '''    if document.user_id != user_id and (material.scope != "shared" or material.owner_user_id is not None):\n'''
    for marker in routes:
        start = s.find(marker)
        if start < 0:
            raise SystemExit(f"completion route not found: {marker}")
        end = s.find('\n@app.route(', start + len(marker))
        if end < 0:
            end = len(s)
        segment = s[start:end]
        lines = segment.splitlines(True)
        seen = False
        output = []
        i = 0
        while i < len(lines):
            if lines[i].startswith(guard):
                if seen:
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith('data = request.get_json') and lines[i].strip() != '':
                        i += 1
                    continue
                seen = True
            output.append(lines[i])
            i += 1
        normalized = ''.join(output)
        if normalized != segment:
            s = s[:start] + normalized + s[end:]
    return s


def main():
    s = APP.read_text()
    s = normalize_podcast_script_route(s)
    s = normalize_podcast_audio_post(s)
    s = normalize_podcast_audio_get(s)
    s = normalize_podcast_audio_get_shared_lookup(s)
    s = normalize_document_rename_owner(s)
    s = normalize_completion_guards(s)
    APP.write_text(s)
    print("study-flow access blocks normalized")


if __name__ == "__main__":
    main()
