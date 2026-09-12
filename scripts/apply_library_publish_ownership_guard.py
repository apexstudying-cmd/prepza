from pathlib import Path

p = Path("app.py")
s = p.read_text()

helper = '''def _can_publish_document(user_id, document):
    """Publishing is an ownership action, not merely a study permission."""
    return bool(
        document
        and not document.is_removed
        and document.user_id == user_id
    )

'''

# Remove every existing copy first so repeated workflow runs converge to one helper.
while helper in s:
    s = s.replace(helper, "", 1)

anchor = 'def _document_reader_watermark(user_id, document):\n'
if anchor not in s:
    raise SystemExit("watermark helper anchor not found")
s = s.replace(anchor, helper + anchor, 1)

old_publish_check = '''    document = db.session.get(Document, document_id)
    if not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404
    if document.status != "ready":
'''
new_publish_check = '''    document = db.session.get(Document, document_id)
    if not _can_publish_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404
    if document.status != "ready":
'''
if old_publish_check in s:
    s = s.replace(old_publish_check, new_publish_check, 1)
elif new_publish_check not in s:
    raise SystemExit("publish ownership check anchor not found")

p.write_text(s)
print("Library publish ownership guard normalized")
