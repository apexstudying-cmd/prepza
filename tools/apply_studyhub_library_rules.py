from __future__ import annotations

from pathlib import Path
import re

APP = Path(__file__).resolve().parents[1] / "app.py"
text = APP.read_text(encoding="utf-8")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if old not in source:
        raise RuntimeError(f"Study Hub/Library backend patch anchor missing: {label}")
    if source.count(old) != 1:
        raise RuntimeError(f"Study Hub/Library backend patch anchor is not unique: {label}")
    return source.replace(old, new, 1)


text = replace_once(
    text,
    "if not document or document.is_removed:\n        return None",
    "if not document:\n        return None",
    "approved Library publication source visibility",
)
text = replace_once(
    text,
    "if not source or source.is_removed or not source.document_content_id:\n        return None",
    "if not source or not source.document_content_id:\n        return None",
    "Study Hub copy creation source visibility",
)
text = replace_once(
    text,
    "if not source or source.is_removed or not source.document_content_id:\n        return jsonify({\"error\": \"Library document is not ready\"}), 409",
    "if not source or not source.document_content_id:\n        return jsonify({\"error\": \"Library document is not ready\"}), 409",
    "Library save source visibility",
)

save_anchor = "    studyhub_document = _ensure_studyhub_document_for_publication(user_id, publication)\n"
save_guard = """    existing_studyhub = Document.query.filter_by(
        user_id=user_id,
        document_content_id=source.document_content_id,
        is_removed=False,
    ).first()
    if existing_studyhub:
        return jsonify({
            \"error\": \"This document is already in your Study Hub.\",
            \"code\": \"already_in_studyhub\",
        }), 409

"""
text = replace_once(text, save_anchor, save_guard + save_anchor, "duplicate Study Hub save guard")

unsave_anchor = "    publication = db.session.get(LibraryPublication, publication_id)\n    db.session.delete(saved)\n"
unsave_replacement = """    publication = db.session.get(LibraryPublication, publication_id)
    if publication:
        source = db.session.get(Document, publication.document_id)
        if source and source.document_content_id:
            personal_copy = Document.query.filter_by(
                user_id=user_id,
                document_content_id=source.document_content_id,
                is_removed=False,
            ).first()
            if personal_copy and personal_copy.id != publication.document_id:
                personal_copy.is_removed = True

    db.session.delete(saved)
"""
text = replace_once(text, unsave_anchor, unsave_replacement, "Library unsave removes personal Study Hub copy")

# /library/saved must return the student's personal Study Hub Document id, not
# the publisher's source Document id. This makes opening, reading progress, and
# removal operate on the student's own copy.
saved_func = re.compile(r'(@app\.route\("/library/saved"\)[\s\S]*?)(?=\n@app\.route\()', re.M)
match = saved_func.search(text)
if not match:
    raise RuntimeError("Study Hub/Library patch anchor missing: saved Library route")
saved_body = match.group(1)
old_saved_unit = "        unit = db.session.get(Unit, pub.unit_id) if pub.unit_id else None\n"
if saved_body.count(old_saved_unit) != 1:
    raise RuntimeError("Study Hub/Library patch anchor is not unique: saved Library unit lookup")
new_saved_unit = """        source = db.session.get(Document, pub.document_id)
        studyhub_document = None
        if source and source.document_content_id:
            studyhub_document = Document.query.filter_by(
                user_id=user_id,
                document_content_id=source.document_content_id,
                is_removed=False,
            ).first()
        if not studyhub_document:
            continue
        unit = db.session.get(Unit, pub.unit_id) if pub.unit_id else None
"""
saved_body = saved_body.replace(old_saved_unit, new_saved_unit, 1)
saved_body = replace_once(saved_body, '            "document_id": pub.document_id,', '            "document_id": studyhub_document.id,', "saved Library personal document id")
text = text[:match.start()] + saved_body + text[match.end():]

# Removing any personal Document from Study Hub also removes the student's
# corresponding Library save row. The public Library publication/source is
# untouched, so it can be saved again later.
delete_anchor = "    document.is_removed = True\n    db.session.commit()\n"
delete_replacement = """    if document.document_content_id:
        saved_rows = SavedLibraryMaterial.query.filter_by(user_id=user_id).all()
        for saved in saved_rows:
            publication = db.session.get(LibraryPublication, saved.library_publication_id)
            source = db.session.get(Document, publication.document_id) if publication else None
            if source and source.document_content_id == document.document_content_id:
                db.session.delete(saved)
                if publication and publication.save_count > 0:
                    publication.save_count -= 1

    document.is_removed = True
    db.session.commit()
"""
text = replace_once(text, delete_anchor, delete_replacement, "Study Hub document removal clears Library save")

APP.write_text(text, encoding="utf-8")
print("Study Hub/Library ownership rules applied")
