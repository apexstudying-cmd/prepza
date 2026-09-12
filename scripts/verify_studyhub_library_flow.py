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

print("StudyHub/Library save flow safety anchors verified")
