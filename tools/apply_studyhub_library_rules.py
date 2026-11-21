from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
LIBRARY_ROUTES = ROOT / "library_routes.py"


def replace_once_or_already_applied(source: str, old: str, new: str, label: str, already_applied: str) -> str:
    old_count = source.count(old)
    applied_count = source.count(already_applied)
    if applied_count == 1 and (old_count == 0 or old in already_applied):
        return source
    if old_count == 1 and applied_count == 0:
        return source.replace(old, new, 1)
    reason = "original anchor is not unique" if old_count > 1 else (
        "already-applied anchor is not unique" if applied_count > 1 else
        "neither the original nor the expected result was found"
    )
    raise RuntimeError(f"Study Hub/Library backend patch failed ({label}): {reason}")


def apply_app_rules(source: str) -> str:
    old = (
        'def _approved_library_publication(document):\n'
        '    """Return the approved Library publication for a document, if public."""\n'
        '    if not document or document.is_removed:\n'
        '        return None'
    )
    new = (
        'def _approved_library_publication(document):\n'
        '    """Return the approved Library publication for a document, if public."""\n'
        '    if not document:\n'
        '        return None'
    )
    return replace_once_or_already_applied(
        source, old, new, "approved Library publication source visibility", new
    )


def apply_library_route_rules(source: str) -> str:
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

    obsolete_save_guard = """    existing_studyhub = Document.query.filter_by(
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
    guard_count = source.count(obsolete_save_guard)
    if guard_count > 1:
        raise RuntimeError("Study Hub/Library backend patch failed (obsolete duplicate save guard): anchor is not unique")
    if guard_count == 1:
        source = source.replace(obsolete_save_guard, "", 1)

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
    return replace_once_or_already_applied(
        source, unsave_anchor, unsave_replacement,
        "Library unsave removes personal Study Hub copy", unsave_replacement,
    )


def apply_rules(source: str) -> str:
    """Compatibility helper retained for focused tests of the complete patch."""
    return apply_library_route_rules(apply_app_rules(source))


def split_library_route_source(source: str) -> tuple[str, str]:
    marker = "    @app.route("
    start = source.find(marker)
    if start < 0:
        raise RuntimeError("Extracted Library route registration block was not found")
    prefix = source[:start]
    body = "\n".join(line[4:] if line.startswith("    ") else line for line in source[start:].splitlines())
    return prefix, body


def restore_library_route_source(prefix: str, body: str) -> str:
    indented = "\n".join(("    " + line) if line else "" for line in body.splitlines())
    return (prefix + indented).rstrip() + "\n"


if __name__ == "__main__":
    app_text = APP.read_text(encoding="utf-8")
    route_source = LIBRARY_ROUTES.read_text(encoding="utf-8")
    route_prefix, route_text = split_library_route_source(route_source)
    updated_app = apply_app_rules(app_text)
    updated_routes = apply_library_route_rules(route_text)
    if updated_app != app_text or updated_routes != route_text:
        APP.write_text(updated_app, encoding="utf-8")
        LIBRARY_ROUTES.write_text(restore_library_route_source(route_prefix, updated_routes), encoding="utf-8")
        print("Study Hub/Library ownership rules applied")
    else:
        print("Study Hub/Library ownership rules already applied; no changes needed")
