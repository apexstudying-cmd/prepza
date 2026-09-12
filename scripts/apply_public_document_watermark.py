from pathlib import Path

p = Path("app.py")
s = p.read_text()

old = '''def _can_study_document(user_id, document):
    if not document or document.is_removed: return False
    if document.user_id == user_id: return True
    pub = LibraryPublication.query.filter_by(document_id=document.id, status="approved").first()
    return bool(pub)
'''

new = '''def _approved_library_publication(document):
    """Return the approved Library publication for a document, if public."""
    if not document or document.is_removed:
        return None
    return LibraryPublication.query.filter_by(
        document_id=document.id,
        status="approved",
    ).first()


def _can_study_document(user_id, document):
    if not document or document.is_removed:
        return False
    if document.user_id == user_id:
        return True
    return bool(_approved_library_publication(document))


def _document_reader_watermark(user_id, document):
    """Resolve a reader watermark without leaking a student's email publicly.

    Private StudyHub documents retain the existing viewer-specific email
    watermark. Once a document has an approved Library publication, the
    public reader always uses Prepza attribution instead, including when the
    publisher is viewing their own published document.
    """
    if _approved_library_publication(document):
        return "SOURCED FROM PREPZA"

    viewer = db.session.get(User, user_id)
    return viewer.email if viewer and viewer.email else "Prepza"
'''

current_with_publish_guard = '''def _can_study_document(user_id, document):
    if not document or document.is_removed:
        return False
    if document.user_id == user_id:
        return True
    return bool(_approved_library_publication(document))


def _can_publish_document(user_id, document):
'''

if old in s:
    s = s.replace(old, new, 1)
elif new not in s and current_with_publish_guard not in s:
    raise SystemExit("document access helper anchor not found")
else:
    print("document access helper already patched")

old_watermark = '''    viewer = db.session.get(User, user_id)
    watermark = (viewer.email if viewer and viewer.email else "Prepza")
    try:
        image_bytes, _ = render_watermarked_page(file_bytes, page_num, watermark, zoom=1.6)
'''
new_watermark = '''    watermark = _document_reader_watermark(user_id, document)
    try:
        image_bytes, _ = render_watermarked_page(file_bytes, page_num, watermark, zoom=1.6)
'''

if old_watermark in s:
    s = s.replace(old_watermark, new_watermark, 1)
elif new_watermark not in s:
    raise SystemExit("native reader watermark anchor not found")

p.write_text(s)
print("public document watermark patch applied")
