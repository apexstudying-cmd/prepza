from pathlib import Path

p = Path('app.py')
s = p.read_text()
old = '''    document = db.session.get(Document, document_id)\n    if not document or document.user_id != user_id:\n        return jsonify({"error": "Document not found"}), 404\n\n    content = db.session.get(DocumentContent, document.document_content_id) if document.document_content_id else None\n'''
new = '''    document = db.session.get(Document, document_id)\n    if not _can_study_document(user_id, document):\n        return jsonify({"error": "Document not found"}), 404\n\n    content = db.session.get(DocumentContent, document.document_content_id) if document.document_content_id else None\n'''
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('get_document access block not found')

old_view = '''    view_url = None\n    if content and content.status == "ready":\n        view_url = get_signed_url(content.storage_path, bucket="documents")\n'''
new_view = '''    view_url = None\n    # Published readers use the native page renderer instead of receiving a\n    # signed URL to the original private file. Owners retain the existing\n    # signed view URL for backwards-compatible document access.\n    if content and content.status == "ready" and document.user_id == user_id:\n        view_url = get_signed_url(content.storage_path, bucket="documents")\n'''
if old_view in s:
    s = s.replace(old_view, new_view, 1)
elif new_view not in s:
    raise SystemExit('document view URL block not found')

p.write_text(s)
print('student study access security patch applied')
