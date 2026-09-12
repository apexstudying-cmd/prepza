from pathlib import Path

p = Path('app.py')
s = p.read_text()
s = s.replace('return bool(pub and document.id not in _flagged_document_ids())', 'return bool(pub)', 1)
old = '''    try:\n        pdf = fitz.open(stream=file_bytes, filetype="pdf")\n        try:\n            pix = pdf.load_page(page_num).get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)\n            image_bytes = pix.tobytes("png")\n        finally: pdf.close()\n    except Exception: return jsonify({"error": "Document page could not be rendered"}), 500\n'''
new = '''    viewer = db.session.get(User, user_id)\n    watermark = (viewer.email if viewer and viewer.email else "Prepza")\n    try:\n        image_bytes, _ = render_watermarked_page(file_bytes, page_num, watermark, zoom=1.6)\n    except Exception:\n        return jsonify({"error": "Document page could not be rendered"}), 500\n'''
if old in s: s = s.replace(old, new, 1)
elif new not in s: raise SystemExit('reader rendering block not found')

old_script_access = '''    document = db.session.get(Document, document_id)\n    if not document or document.user_id != user_id or document.is_removed:\n        return jsonify({"error": "Document not found"}), 404\n\n    if not document.document_content_id:\n        return jsonify({"error": "Document has no content to generate a podcast from"}), 400\n'''
new_script_access = '''    document = db.session.get(Document, document_id)\n    if not _can_study_document(user_id, document):\n        return jsonify({"error": "Document not found"}), 404\n\n    if not document.document_content_id:\n        return jsonify({"error": "Document has no content to generate a podcast from"}), 400\n'''
if old_script_access in s:
    s = s.replace(old_script_access, new_script_access, 1)
elif new_script_access not in s:
    raise SystemExit('podcast script access block not found')

published_script_block = '''    if document.user_id != user_id:\n        material = GeneratedMaterial.query.filter_by(\n            document_content_id=document.document_content_id,\n            material_type="podcast",\n            status="ready",\n        ).first()\n        if not material or not material.payload:\n            return jsonify({"error": "Podcast has not been published yet"}), 404\n        record_document_studied(user_id, content.id)\n        db.session.commit()\n        return jsonify({\n            "material_id": material.id,\n            "reused": True,\n            "podcast": json.loads(material.payload),\n        }), 200\n\n'''
shared_script_block = '''    if document.user_id != user_id:\n        material = GeneratedMaterial.query.filter_by(\n            document_content_id=document.document_content_id,\n            material_type="podcast",\n            status="ready",\n            scope="shared",\n            owner_user_id=None,\n        ).first()\n        if not material or not material.payload:\n            return jsonify({"error": "Podcast has not been published yet"}), 404\n        record_document_studied(user_id, content.id)\n        db.session.commit()\n        return jsonify({\n            "material_id": material.id,\n            "reused": True,\n            "podcast": json.loads(material.payload),\n        }), 200\n\n'''
if published_script_block in s:
    s = s.replace(published_script_block, shared_script_block, 1)
elif shared_script_block not in s:
    raise SystemExit('published podcast script block not found')
while s.count(shared_script_block) > 1:
    first = s.find(shared_script_block)
    s = s[:first + len(shared_script_block)] + s[first + len(shared_script_block):].replace(shared_script_block, '', 1)

old_audio_material = '''    material = get_generated_material_for_user(\n        document.document_content_id, "podcast", session.get("user_id")\n    )\n'''
new_audio_material = '''    if document.user_id == user_id:\n        material = get_generated_material_for_user(\n            document.document_content_id, "podcast", session.get("user_id")\n        )\n    else:\n        material = GeneratedMaterial.query.filter_by(\n            document_content_id=document.document_content_id,\n            material_type="podcast",\n            status="ready",\n            scope="shared",\n            owner_user_id=None,\n        ).first()\n'''
legacy_audio_material = '''    if document.user_id == user_id:\n        material = get_generated_material_for_user(\n            document.document_content_id, "podcast", session.get("user_id")\n        )\n    else:\n        material = GeneratedMaterial.query.filter_by(\n            document_content_id=document.document_content_id,\n            material_type="podcast",\n            status="ready",\n        ).first()\n'''
if new_audio_material not in s:
    if legacy_audio_material in s:
        s = s.replace(legacy_audio_material, new_audio_material, 1)
    elif old_audio_material in s:
        s = s.replace(old_audio_material, new_audio_material, 1)
    else:
        raise SystemExit('podcast audio material lookup anchor not found')

# Collapse duplicate audio-synthesis guards left by older patch runs.
guard = '''    if document.user_id != user_id:\n        return jsonify({"error": "Podcast audio is not ready yet"}), 409\n\n'''
if guard not in s:
    raise SystemExit('podcast audio synthesis guard not found')
first = s.find(guard)
second_part = s[first + len(guard):]
s = s[:first + len(guard)] + second_part.replace(guard, '')

# The polling endpoint must also allow approved published viewers, but only
# against a shared READY artifact. It never generates or exposes private files.
old_poll_access = '''    document = db.session.get(Document, document_id)\n    if not document or document.user_id != user_id or document.is_removed:\n        return jsonify({"error": "Document not found"}), 404\n'''
new_poll_access = '''    document = db.session.get(Document, document_id)\n    if not _can_study_document(user_id, document):\n        return jsonify({"error": "Document not found"}), 404\n'''
if old_poll_access in s:
    s = s.replace(old_poll_access, new_poll_access, 1)

old_poll_lookup = '''    if document.user_id == user_id:\n        material = get_generated_material_for_user(\n            document.document_content_id, "podcast", session.get("user_id")\n        )\n    else:\n        material = GeneratedMaterial.query.filter_by(\n            document_content_id=document.document_content_id,\n            material_type="podcast",\n            status="ready",\n        ).first()\n'''
new_poll_lookup = '''    if document.user_id == user_id:\n        material = get_generated_material_for_user(\n            document.document_content_id, "podcast", session.get("user_id")\n        )\n    else:\n        material = GeneratedMaterial.query.filter_by(\n            document_content_id=document.document_content_id,\n            material_type="podcast",\n            status="ready",\n            scope="shared",\n            owner_user_id=None,\n        ).first()\n'''
if new_poll_lookup not in s:
    if old_poll_lookup in s:
        s = s.replace(old_poll_lookup, new_poll_lookup, 1)
    else:
        raise SystemExit('podcast polling lookup anchor not found')

p.write_text(s)
print('reader and published podcast shared-artifact patch applied')