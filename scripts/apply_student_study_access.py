from pathlib import Path

p = Path('app.py')
s = p.read_text()
old = '''    document = db.session.get(Document, document_id)\n    if not document or document.user_id != user_id or document.is_removed:\n        return jsonify({"error": "Document not found"}), 404\n\n    content = db.session.get(DocumentContent, document.document_content_id) if document.document_content_id else None\n'''
new = '''    document = db.session.get(Document, document_id)\n    if not _can_study_document(user_id, document):\n        return jsonify({"error": "Document not found"}), 404\n\n    content = db.session.get(DocumentContent, document.document_content_id) if document.document_content_id else None\n'''
if old not in s:
    if new not in s:
        raise SystemExit('get_document access block not found')
else:
    s = s.replace(old, new, 1)
p.write_text(s)
print('student study access patch applied')
