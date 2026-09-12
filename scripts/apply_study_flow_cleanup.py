from pathlib import Path

APP = Path("app.py")


def normalize_podcast_script(s):
    start_marker = 'def podcast_script_document(document_id):'
    start = s.find(start_marker)
    if start < 0:
        raise SystemExit('podcast script endpoint not found')
    generation_marker = '    try:\n        result = ai_service.generate_document_podcast_script(\n'
    generation = s.find(generation_marker, start)
    if generation < 0:
        raise SystemExit('podcast generation anchor not found')
    branch_marker = '    if document.user_id != user_id:\n'
    branch = s.find(branch_marker, start, generation)
    if branch < 0:
        raise SystemExit('published podcast viewer branch not found')
    shared = '''    if document.user_id != user_id:\n        material = GeneratedMaterial.query.filter_by(\n            document_content_id=document.document_content_id,\n            material_type="podcast",\n            status="ready",\n            scope="shared",\n            owner_user_id=None,\n        ).first()\n        if not material or not material.payload:\n            return jsonify({"error": "Podcast has not been published yet"}), 404\n        record_document_studied(user_id, content.id)\n        db.session.commit()\n        return jsonify({\n            "material_id": material.id,\n            "reused": True,\n            "podcast": json.loads(material.payload),\n        }), 200\n\n'''
    return s[:branch] + shared + s[generation:]


def normalize_audio_post(s):
    start = s.find('def trigger_podcast_audio(document_id):')
    if start < 0:
        raise SystemExit('podcast audio POST endpoint not found')
    synth = s.find('    podcast_audio.start_podcast_audio_processing(material.id, app)\n', start)
    if synth < 0:
        raise SystemExit('podcast audio synthesis anchor not found')
    segment = s[start:synth]
    guard = '''    if document.user_id != user_id:\n        return jsonify({"error": "Podcast audio is not ready yet"}), 409\n\n'''
    while guard in segment:
        segment = segment.replace(guard, '', 1)
    segment += guard
    return s[:start] + segment + s[synth:]


def normalize_audio_get(s):
    start = s.find('def get_podcast_audio(document_id):')
    if start < 0:
        raise SystemExit('podcast audio GET endpoint not found')
    end = s.find('\n@app.route("/podcasts")', start)
    if end < 0:
        raise SystemExit('podcast audio GET boundary not found')
    segment = s[start:end]
    old_access = '''    document = db.session.get(Document, document_id)\n    if not document or document.user_id != user_id or document.is_removed:\n        return jsonify({"error": "Document not found"}), 404\n'''
    new_access = '''    document = db.session.get(Document, document_id)\n    if not _can_study_document(user_id, document):\n        return jsonify({"error": "Document not found"}), 404\n'''
    segment = segment.replace(old_access, new_access, 1)
    legacy = '''    else:\n        material = GeneratedMaterial.query.filter_by(\n            document_content_id=document.document_content_id,\n            material_type="podcast",\n            status="ready",\n        ).first()\n'''
    shared = '''    else:\n        material = GeneratedMaterial.query.filter_by(\n            document_content_id=document.document_content_id,\n            material_type="podcast",\n            status="ready",\n            scope="shared",\n            owner_user_id=None,\n        ).first()\n'''
    segment = segment.replace(legacy, shared, 1)
    return s[:start] + segment + s[end:]


def main():
    s = APP.read_text()
    s = normalize_podcast_script(s)
    s = normalize_audio_post(s)
    s = normalize_audio_get(s)
    APP.write_text(s)
    print('study-flow access blocks normalized')


if __name__ == '__main__':
    main()
