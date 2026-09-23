from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"
text = APP.read_text()

# This patch targets the newer LibraryPublication academic-context schema.
# Older/current branches still derive cohort eligibility from Unit/UnitProgram;
# do not fail the entire frontend build when that schema is not present.
model_start=text.find("class LibraryPublication")
model_end=text.find("class SavedLibraryMaterial", model_start)
library_model=text[model_start:model_end] if model_start >= 0 and model_end > model_start else ""
if "university_id = db.Column" not in library_model or "program_id = db.Column" not in library_model:
    print("Skipped exact Library academic-eligibility patch: LibraryPublication academic fields are not present.")
    raise SystemExit(0)


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
'''    if semester is None:\n        semester = user.semester\n\n    if not document_id:''',
'''    if semester is None:\n        semester = user.semester\n\n    if data.get("unit_id") is not None:\n        return jsonify({"error": "unit_id is no longer supported for Library publications"}), 400\n    if any(value is None for value in (university_id, program_id, year, semester)):\n        return jsonify({"error": "university, course, year, and semester are required for Library publication"}), 400\n    if not isinstance(university_id, int) or isinstance(university_id, bool):\n        return jsonify({"error": "university_id must be an integer"}), 400\n    university = University.query.filter_by(id=university_id, is_active=True).first()\n    if not university:\n        return jsonify({"error": "Selected university was not found"}), 400\n    if not isinstance(program_id, int) or isinstance(program_id, bool):\n        return jsonify({"error": "program_id must be an integer"}), 400\n    program = Program.query.filter_by(id=program_id, university_id=university_id, is_active=True).first()\n    if not program:\n        return jsonify({"error": "Selected course does not belong to the selected university"}), 400\n    if not isinstance(year, int) or isinstance(year, bool) or not 1 <= year <= 8:\n        return jsonify({"error": "year must be an integer between 1 and 8"}), 400\n    if not isinstance(semester, int) or isinstance(semester, bool) or semester not in (1, 2):\n        return jsonify({"error": "semester must be 1 or 2"}), 400\n\n    if not document_id:''',
    "complete academic context validation",
)

if "FREE_LIBRARY_DOCUMENT_LIMIT" in text:
    print("Skipped exact Library academic-eligibility patch: canonical Free cohort entitlement is already enforced.")
    raise SystemExit(0)

if "_library_context_matches(viewer, publication)" not in text:
    marker = 'LIBRARY_ACTIVE_STATUSES = ("pending", "approved")'
    if text.count(marker) != 1:
        raise SystemExit(f"FAIL CLOSED: Library active-status anchor: expected 1 match, found {text.count(marker)}")
    helper = '''LIBRARY_ACTIVE_STATUSES = ("pending", "approved")

def _library_context_matches(viewer, publication):
    """Return True only for an exact university/course/year/semester match."""
    if not viewer or not publication:
        return False
    values = (
        viewer.university_id, viewer.program_id, viewer.year, viewer.semester,
        publication.university_id, publication.program_id, publication.year, publication.semester,
    )
    return all(value is not None for value in values) and (
        viewer.university_id == publication.university_id
        and viewer.program_id == publication.program_id
        and viewer.year == publication.year
        and viewer.semester == publication.semester
    )
'''
    text = text.replace(marker, helper, 1)



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

APP.write_text(text)
print("Applied exact Library academic eligibility rules successfully.")
