from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"


def replace_once_or_already_applied(
    source: str,
    old: str,
    new: str,
    label: str,
    already_applied: str,
) -> str:
    """Apply one source transformation, or safely accept its exact prior result."""
    old_count = source.count(old)
    applied_count = source.count(already_applied)

    if applied_count == 1 and (old_count == 0 or old in already_applied):
        return source

    if old_count == 1 and applied_count == 0:
        return source.replace(old, new, 1)

    if old_count > 1:
        reason = "original anchor is not unique"
    elif applied_count > 1:
        reason = "already-applied anchor is not unique"
    else:
        reason = "neither the original nor the expected result was found"
    raise RuntimeError(f"Study Hub/Library backend patch failed ({label}): {reason}")


def apply_rules(source: str) -> str:
    # A publisher may remove their own Study Hub copy without deleting the public
    # Library publication. is_removed is a personal Study Hub visibility flag, not
    # a destruction flag for an approved Library source.
    old_publication_visibility = (
        'def _approved_library_publication(document):\n'
        '    """Return the approved Library publication for a document, if public."""\n'
        '    if not document or document.is_removed:\n'
        '        return None'
    )
    new_publication_visibility = (
        'def _approved_library_publication(document):\n'
        '    """Return the approved Library publication for a document, if public."""\n'
        '    if not document:\n'
        '        return None'
    )
    source = replace_once_or_already_applied(
        source,
        old_publication_visibility,
        new_publication_visibility,
        "approved Library publication source visibility",
        new_publication_visibility,
    )

    # The source document may be soft-removed from its owner's Study Hub while its
    # approved Library publication remains valid. A saving student still receives
    # their own personal Document row.
    old_copy_visibility = (
        "source = db.session.get(Document, publication.document_id)\n"
        "    if not source or source.is_removed or not source.document_content_id:\n"
        "        return None"
    )
    new_copy_visibility = (
        "source = db.session.get(Document, publication.document_id)\n"
        "    if not source or not source.document_content_id:\n"
        "        return None"
    )
    source = replace_once_or_already_applied(
        source, old_copy_visibility, new_copy_visibility,
        "Study Hub copy creation source visibility", new_copy_visibility,
    )

    old_save_visibility = (
        'source = db.session.get(Document, publication.document_id)\n'
        '    if not source or source.is_removed or not source.document_content_id:\n'
        '        return jsonify({"error": "Library document is not ready"}), 409'
    )
    new_save_visibility = (
        'source = db.session.get(Document, publication.document_id)\n'
        '    if not source or not source.document_content_id:\n'
        '        return jsonify({"error": "Library document is not ready"}), 409'
    )
    source = replace_once_or_already_applied(
        source, old_save_visibility, new_save_visibility,
        "Library save source visibility", new_save_visibility,
    )

    # Save means "put this into my Study Hub". Reject an additional copy when an
    # active personal Document already points at the same deduplicated content.
    save_anchor = "    studyhub_document = _ensure_studyhub_document_for_publication(user_id, publication)\n"
    save_guard = """    existing_studyhub = Document.query.filter_by(
        user_id=user_id,
        document_content_id=source.document_content_id,
        is_removed=False,
    ).first()
    if existing_studyhub:
        return jsonify({
            "error": "This document is already in your Study Hub.",
            "code": "already_in_studyhub",
        }), 409

"""
    source = replace_once_or_already_applied(
        source,
        save_anchor,
        save_guard + save_anchor,
        "duplicate Study Hub save guard",
        save_guard + save_anchor,
    )

    # Removing a Library save removes the student's personal Study Hub copy too,
    # but never deletes or soft-removes the public Library source document.
    unsave_anchor = (
        "    publication = db.session.get(LibraryPublication, publication_id)\n"
        "    db.session.delete(saved)\n"
    )
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
    source = replace_once_or_already_applied(
        source,
        unsave_anchor,
        unsave_replacement,
        "Library unsave removes personal Study Hub copy",
        unsave_replacement,
    )
    return source


if __name__ == "__main__":
    text = APP.read_text(encoding="utf-8")
    updated = apply_rules(text)
    if updated != text:
        APP.write_text(updated, encoding="utf-8")
        print("Study Hub/Library ownership rules applied")
    else:
        print("Study Hub/Library ownership rules already applied; no changes needed")
