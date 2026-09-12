from pathlib import Path

s = Path("app.py").read_text()

required = [
    'def _ensure_studyhub_document_for_publication(user_id, publication):',
    'in_studyhub',
    'document_content_id=content.id',
    'SavedLibraryMaterial.query.filter_by(',
]
for anchor in required:
    if anchor not in s:
        raise SystemExit(f"missing StudyHub/Library flow anchor: {anchor}")

old_route = 'return jsonify({"message": "Saved", "save_count": publication.save_count}), 201'
if old_route in s:
    raise SystemExit("legacy Library save route still returns without StudyHub document")

existing_branch = '''    if existing:\n        # A legacy SavedLibraryMaterial row may predate the StudyHub-document\n        # guarantee. In that case _ensure_studyhub_document_for_publication\n        # returns a new, transient Document that must be persisted here.\n        if studyhub_document.id is None:\n            db.session.add(studyhub_document)\n            db.session.flush()\n'''
if existing_branch not in s:
    raise SystemExit("existing Library save branch does not persist a missing StudyHub document")

print("StudyHub/Library save flow safety anchors verified")
