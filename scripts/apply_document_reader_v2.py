from pathlib import Path

p = Path('app.py')
s = p.read_text()
s = s.replace('return bool(pub and document.id not in _flagged_document_ids())', 'return bool(pub)', 1)
old = '''    try:\n        pdf = fitz.open(stream=file_bytes, filetype="pdf")\n        try:\n            pix = pdf.load_page(page_num).get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)\n            image_bytes = pix.tobytes("png")\n        finally: pdf.close()\n    except Exception: return jsonify({"error": "Document page could not be rendered"}), 500\n'''
new = '''    viewer = db.session.get(User, user_id)\n    watermark = (viewer.email if viewer and viewer.email else "Prepza")\n    try:\n        image_bytes, _ = render_watermarked_page(file_bytes, page_num, watermark, zoom=1.6)\n    except Exception:\n        return jsonify({"error": "Document page could not be rendered"}), 500\n'''
if old in s: s = s.replace(old, new, 1)
elif new not in s: raise SystemExit('reader rendering block not found')

old_audio_post = '''    user_id = session.get("user_id")\n    if not user_id:\n        return jsonify({"error": "Not logged in"}), 401\n\n    document = db.session.get(Document, document_id)\n    if not document or document.user_id != user_id or document.is_removed:\n        return jsonify({"error": "Document not found"}), 404\n    if not document.document_content_id:\n        return jsonify({"error": "Document has no content to generate a podcast from"}), 400\n\n    material = get_generated_material_for_user(\n        document.document_content_id, "podcast", session.get("user_id")\n    )\n'''
new_audio_post = '''    user_id = session.get("user_id")\n    if not user_id:\n        return jsonify({"error": "Not logged in"}), 401\n\n    document = db.session.get(Document, document_id)\n    if not _can_study_document(user_id, document):\n        return jsonify({"error": "Document not found"}), 404\n    if not document.document_content_id:\n        return jsonify({"error": "Document has no content to generate a podcast from"}), 400\n\n    material = get_generated_material_for_user(\n        document.document_content_id, "podcast", session.get("user_id")\n    )\n'''
if old_audio_post in s:
    s = s.replace(old_audio_post, new_audio_post, 1)
elif new_audio_post not in s:
    raise SystemExit('podcast audio POST access block not found')

old_audio_guard = '''    if audio_status == "processing":\n        return jsonify({"audio_status": "processing", "material_id": material.id}), 202\n\n    podcast_audio.start_podcast_audio_processing(material.id, app)\n'''
new_audio_guard = '''    if audio_status == "processing":\n        return jsonify({"audio_status": "processing", "material_id": material.id}), 202\n\n    # Published readers may replay an existing audio artifact, but they must\n    # never be able to trigger a new paid synthesis job themselves.\n    if document.user_id != user_id:\n        return jsonify({"error": "Podcast audio is not ready yet"}), 409\n\n    podcast_audio.start_podcast_audio_processing(material.id, app)\n'''
if old_audio_guard in s:
    s = s.replace(old_audio_guard, new_audio_guard, 1)
elif new_audio_guard not in s:
    raise SystemExit('podcast audio generation guard not found')

old_audio_get = '''    user_id = session.get("user_id")\n    if not user_id:\n        return jsonify({"error": "Not logged in"}), 401\n\n    document = db.session.get(Document, document_id)\n    if not document or document.user_id != user_id or document.is_removed:\n        return jsonify({"error": "Document not found"}), 404\n\n    if not document.document_content_id:\n'''
new_audio_get = '''    user_id = session.get("user_id")\n    if not user_id:\n        return jsonify({"error": "Not logged in"}), 401\n\n    document = db.session.get(Document, document_id)\n    if not _can_study_document(user_id, document):\n        return jsonify({"error": "Document not found"}), 404\n\n    if not document.document_content_id:\n'''
if old_audio_get in s:
    s = s.replace(old_audio_get, new_audio_get, 1)
elif new_audio_get not in s:
    raise SystemExit('podcast audio GET access block not found')

p.write_text(s)
print('reader and published podcast security patch applied')
