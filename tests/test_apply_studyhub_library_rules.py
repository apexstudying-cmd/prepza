from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "apply_studyhub_library_rules.py"
SPEC = importlib.util.spec_from_file_location("studyhub_library_rules", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def source_before_patch() -> str:
    return '''def _approved_library_publication(document):
    """Return the approved Library publication for a document, if public."""
    if not document or document.is_removed:
        return None
    return LibraryPublication.query.filter_by(
        document_id=document.id,
        status="approved",
    ).first()

def _ensure_studyhub_document_for_publication(user_id, publication):
    source = db.session.get(Document, publication.document_id)
    if not source or source.is_removed or not source.document_content_id:
        return None

def save_library_item(publication_id):
    source = db.session.get(Document, publication.document_id)
    if not source or source.is_removed or not source.document_content_id:
        return jsonify({"error": "Library document is not ready"}), 409
    studyhub_document = _ensure_studyhub_document_for_publication(user_id, publication)

def unsave_library_item(publication_id):
    publication = db.session.get(LibraryPublication, publication_id)
    db.session.delete(saved)
'''


def test_library_rules_patch_applies_all_expected_changes() -> None:
    updated = MODULE.apply_rules(source_before_patch())
    assert "if not document or document.is_removed:" not in updated
    assert "if not source or source.is_removed or not source.document_content_id:" not in updated
    assert '"code": "already_in_studyhub"' not in updated
    assert "personal_copy.is_removed = True" in updated


def test_library_rules_patch_is_idempotent() -> None:
    once = MODULE.apply_rules(source_before_patch())
    twice = MODULE.apply_rules(once)
    assert twice == once



def test_library_rules_patch_removes_legacy_conflicting_save_guard() -> None:
    patched = MODULE.apply_rules(source_before_patch())
    save_anchor = "    studyhub_document = _ensure_studyhub_document_for_publication(user_id, publication)\\n"
    obsolete_guard = """    existing_studyhub = Document.query.filter_by(
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
    with_guard = patched.replace(save_anchor, obsolete_guard + save_anchor, 1)
    cleaned = MODULE.apply_rules(with_guard)
    assert '"code": "already_in_studyhub"' not in cleaned
    assert save_anchor in cleaned
    assert MODULE.apply_rules(cleaned) == cleaned
