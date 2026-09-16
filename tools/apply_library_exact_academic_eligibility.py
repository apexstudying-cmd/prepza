from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"
text = APP.read_text(encoding="utf-8")


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"FAIL CLOSED: {label}: expected 1 match, found {count}")
    text = text.replace(old, new, 1)


replace_once(
    'LIBRARY_MATERIAL_TYPES = {"lecture_notes", "past_paper", "summary", "other"}',
    'LIBRARY_MATERIAL_TYPES = {"lecture_notes", "past_paper"}',
    "material types",
)

replace_once(
    '    unit_id = data.get("unit_id")\n    university_id = data.get("university_id")',
    '    if data.get("unit_id") is not None:\n        return jsonify({"error": "unit_id is no longer supported for Library publications"}), 400\n    unit_id = None\n    university_id = data.get("university_id")',
    "reject unit metadata",
)

replace_once(
    '    if semester is not None:\n        if not isinstance(semester, int) or isinstance(semester, bool) or semester not in (1, 2):\n            return jsonify({"error": "semester must be 1 or 2"}), 400\n\n    if _document_content_has_flagged_material(document.document_content_id):',
    '    if semester is not None:\n        if not isinstance(semester, int) or isinstance(semester, bool) or semester not in (1, 2):\n            return jsonify({"error": "semester must be 1 or 2"}), 400\n\n    if any(value is None for value in (university_id, program_id, year, semester)):\n        return jsonify({"error": "university, course, year, and semester are required for Library publication"}), 400\n\n    if _document_content_has_flagged_material(document.document_content_id):',
    "require complete context",
)

replace_once(
    'LIBRARY_ACTIVE_STATUSES = ("pending", "approved")\n\n\ndef _document_content_has_flagged_material',
    'LIBRARY_ACTIVE_STATUSES = ("pending", "approved")\n\n\ndef _library_context_matches(viewer, publication):\n    """Return True only for an exact university/course/year/semester match."""\n    if not viewer or not publication:\n        return False\n    values = (viewer.university_id, viewer.program_id, viewer.year, viewer.semester, publication.university_id, publication.program_id, publication.year, publication.semester)\n    return all(value is not None for value in values) and (\n        viewer.university_id == publication.university_id\n        and viewer.program_id == publication.program_id\n        and viewer.year == publication.year\n        and viewer.semester == publication.semester\n    )\n\n\ndef _document_content_has_flagged_material',
    "exact academic match helper",
)

replace_once(
    '    query = LibraryPublication.query.filter_by(status="approved")\n    flagged_document_ids = _flagged_document_ids()',
    '    viewer = db.session.get(User, user_id)\n    if not viewer:\n        return jsonify({"error": "Account not found"}), 404\n    if any(value is None for value in (viewer.university_id, viewer.program_id, viewer.year, viewer.semester)):\n        return jsonify({"error": "Complete your university, course, year, and semester before accessing the Library"}), 400\n\n    query = LibraryPublication.query.filter(\n        LibraryPublication.status == "approved",\n        LibraryPublication.university_id == viewer.university_id,\n        LibraryPublication.program_id == viewer.program_id,\n        LibraryPublication.year == viewer.year,\n        LibraryPublication.semester == viewer.semester,\n    )\n    flagged_document_ids = _flagged_document_ids()',
    "browse exact academic gate",
)

replace_once(
    '    publication = db.session.get(LibraryPublication, publication_id)\n    if not publication or publication.status != "approved":\n        return jsonify({"error": "Library item not found"}), 404\n\n    source = db.session.get(Document, publication.document_id)',
    '    publication = db.session.get(LibraryPublication, publication_id)\n    if not publication or publication.status != "approved":\n        return jsonify({"error": "Library item not found"}), 404\n\n    viewer = db.session.get(User, user_id)\n    if not viewer:\n        return jsonify({"error": "Account not found"}), 404\n    if not _library_context_matches(viewer, publication):\n        return jsonify({"error": "This Library item is not available for your university, course, year, and semester"}), 403\n\n    source = db.session.get(Document, publication.document_id)',
    "save exact academic gate",
)

# The academic-context patch has already introduced these fields by the time
# this script runs during the frontend production prebuild. Force Library
# publications to remain unit-free while retaining the legacy DB column for
# compatibility with unrelated historical schema.
replace_once(
    '        unit_id=unit_id,\n        university_id=university_id,',
    '        unit_id=None,\n        university_id=university_id,',
    "remove Library unit persistence",
)

APP.write_text(text, encoding="utf-8")
print("Applied exact Library academic eligibility rules successfully.")
