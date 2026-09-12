from pathlib import Path

p = Path('app.py')
s = p.read_text()
old = '''    document = db.session.get(Document, document_id)\n    if not document or document.user_id != user_id:\n        return jsonify({"error": "Document not found"}), 404\n\n    content = db.session.get(DocumentContent, document.document_content_id) if document.document_content_id else None\n'''
new = '''    document = db.session.get(Document, document_id)\n    if not _can_study_document(user_id, document):\n        return jsonify({"error": "Document not found"}), 404\n\n    content = db.session.get(DocumentContent, document.document_content_id) if document.document_content_id else None\n'''
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('get_document access block not found')
p.write_text(s)
print('student study access patch applied')
