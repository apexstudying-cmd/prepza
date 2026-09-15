from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"
text = APP.read_text(encoding="utf-8")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if old not in source:
        raise RuntimeError(f"Study Hub/Library backend patch anchor missing: {label}")
    if source.count(old) != 1:
        raise RuntimeError(f"Study Hub/Library backend patch anchor is not unique: {label}")
    return source.replace(old, new, 1)


# A publisher may remove their own Study Hub copy without deleting the public
# Library publication. is_removed is a personal Study Hub visibility flag, not
# a destruction flag for an approved Library source.
text = replace_once(
    text,
    "if not document or document.is_removed:\n        return None",
    "if not document:\n        return None",
    "approved Library publication source visibility",
)

# The source document may be soft-removed from its owner's Study Hub while its
# approved Library publication remains valid. A saving student still receives
# their own personal Document row.
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

# Save means "put this into my Study Hub". If the student already has an active
# personal Document pointing at the same deduplicated content, reject the save
# instead of creating a second Study Hub copy.
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

# Removing a Library save removes the student's personal Study Hub copy too,
# but never deletes or soft-removes the public Library source document.
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

APP.write_text(text, encoding="utf-8")
print("Study Hub/Library ownership rules applied")
