from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
LIBRARY_ROUTES = ROOT / "library_routes.py"
LIBRARY_MODELS = ROOT / "library_models.py"
app_text = APP.read_text(encoding="utf-8")
route_text = LIBRARY_ROUTES.read_text(encoding="utf-8")
library_model_text = LIBRARY_MODELS.read_text(encoding="utf-8")

if not all(token in library_model_text for token in (
    "university_id = db.Column",
    "program_id = db.Column",
    "year = db.Column",
    "semester = db.Column",
)):
    print("Skipped exact Library academic-eligibility patch: LibraryPublication academic fields are not present.")
    raise SystemExit(0)


def replace_app_once(old, new, label):
    global app_text
    count = app_text.count(old)
    if count == 1:
        app_text = app_text.replace(old, new, 1)
        return
    if count == 0 and new in app_text:
        print(f"Skipped {label}: canonical app-level policy is already present.")
        return
    raise SystemExit(f"FAIL CLOSED: {label}: expected 1 match or canonical policy, found {count}")


def replace_route_once_or_skip(old, new, label, already_applied):
    global route_text
    count = route_text.count(old)
    if count == 1:
        route_text = route_text.replace(old, new, 1)
        return
    if count == 0 and already_applied():
        print(f"Skipped {label}: canonical Library route is already present.")
        return
    raise SystemExit(f"FAIL CLOSED: {label}: expected 1 legacy match or verified canonical route, found {count}")


def replace_route_all_exact_or_skip(old, new, expected, label, already_applied):
    global route_text
    count = route_text.count(old)
    if count == expected:
        route_text = route_text.replace(old, new)
        return
    if count == 0 and already_applied():
        print(f"Skipped {label}: canonical response fields are already present.")
        return
    raise SystemExit(f"FAIL CLOSED: {label}: expected {expected} legacy matches or verified canonical fields, found {count}")


replace_app_once(
    'LIBRARY_MATERIAL_TYPES = {"lecture_notes", "past_paper", "summary", "other"}',
    'LIBRARY_MATERIAL_TYPES = {"lecture_notes", "past_paper"}',
    "material types",
)

replace_route_once_or_skip(
'''    material_type = (data.get("material_type") or "").strip()
    unit_id = data.get("unit_id")

    if not document_id:''',
'''    material_type = (data.get("material_type") or "").strip()
    university_id = data.get("university_id")
    program_id = data.get("program_id")
    year = data.get("year")
    semester = data.get("semester")

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "Account not found"}), 404

    if university_id is None:
        university_id = user.university_id
    if program_id is None:
        program_id = user.program_id
    if year is None:
        year = user.year
    if semester is None:
        semester = user.semester

    if not document_id:''',
    "publish metadata inputs/defaults",
    lambda: all(token in route_text for token in (
        'university_id = data.get("university_id")',
        'program_id = data.get("program_id")',
        'year = data.get("year")',
        'semester = data.get("semester")',
        "user.university_id", "user.program_id", "user.year", "user.semester",
    )),

replace_route_once_or_skip(
'''    if semester is None:
        semester = user.semester

    if not document_id:''',
'''    if semester is None:
        semester = user.semester

    if data.get("unit_id") is not None:
        return jsonify({"error": "unit_id is no longer supported for Library publications"}), 400
    if any(value is None for value in (university_id, program_id, year, semester)):
        return jsonify({"error": "university, course, year, and semester are required for Library publication"}), 400
    if not isinstance(university_id, int) or isinstance(university_id, bool):
        return jsonify({"error": "university_id must be an integer"}), 400
    university = University.query.filter_by(id=university_id, is_active=True).first()
    if not university:
        return jsonify({"error": "Selected university was not found"}), 400
    if not isinstance(program_id, int) or isinstance(program_id, bool):
        return jsonify({"error": "program_id must be an integer"}), 400
    program = Program.query.filter_by(id=program_id, university_id=university_id, is_active=True).first()
    if not program:
        return jsonify({"error": "Selected course does not belong to the selected university"}), 400
    if not isinstance(year, int) or isinstance(year, bool) or not 1 <= year <= 5:
        return jsonify({"error": "year must be an integer between 1 and 5"}), 400
    if not isinstance(semester, int) or isinstance(semester, bool) or semester not in (1, 2, 3):
        return jsonify({"error": "semester must be 1, 2, or 3"}), 400

    if not document_id:''',
    "complete academic context validation",
    lambda: all(token in route_text for token in (
        'unit_id is no longer supported for Library publications',
        'Selected course does not belong to the selected university',
        'year must be an integer between 1 and 5',
        'semester must be 1, 2, or 3',
    )),
)

replace_route_once_or_skip(
'''    publication = LibraryPublication(
        document_id=document_id,
        user_id=user_id,
        unit_id=unit_id,
        title=title,''',
'''    publication = LibraryPublication(
        document_id=document_id,
        user_id=user_id,
        university_id=university_id,
        program_id=program_id,
        year=year,
        semester=semester,
        title=title,''',
    "persist publication academic context",
    lambda: all(token in route_text for token in (
        "university_id=university_id", "program_id=program_id", "year=year", "semester=semester",
    )),
)

replace_route_all_exact_or_skip(
'''            "unit_id": pub.unit_id,
            "unit_code": unit.code if unit else None,''',
'''            "university_id": pub.university_id,
            "program_id": pub.program_id,
            "year": pub.year,
            "semester": pub.semester,''',
    4,
    "student-facing library metadata responses",
    lambda: (
        '"unit_id": pub.unit_id' not in route_text
        and '"unit_code": unit.code if unit else None' not in route_text
        and all(route_text.count(token) >= 2 for token in (
            '"university_id": pub.university_id',
            '"program_id": pub.program_id',
            '"year": pub.year',
            '"semester": pub.semester',
        ))
    ),
)

replace_route_once_or_skip(
'''    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    query = LibraryPublication.query.filter_by(status="approved")''',
'''    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    viewer = db.session.get(User, user_id)
    query = LibraryPublication.query.filter_by(status="approved")''',
    "library browse viewer",
    lambda: (
        (lambda start: start >= 0 and "viewer = db.session.get(User, user_id)" in route_text[start:route_text.find("def save_library_item(", start)])
        (route_text.find("def browse_library():"))
    ),
)

replace_route_once_or_skip(
'''    university_id = request.args.get("university_id", type=int)
    if university_id:
        query = query.join(Unit, LibraryPublication.unit_id == Unit.id).filter(
            Unit.university_id == university_id
        )

    material_type = request.args.get("material_type")''',
'''    university_id = request.args.get("university_id", type=int)
    if university_id:
        query = query.filter(LibraryPublication.university_id == university_id)

    program_id = request.args.get("program_id", type=int)
    if program_id:
        query = query.filter(LibraryPublication.program_id == program_id)

    year = request.args.get("year", type=int)
    if year:
        query = query.filter(LibraryPublication.year == year)

    semester = request.args.get("semester", type=int)
    if semester:
        query = query.filter(LibraryPublication.semester == semester)

    material_type = request.args.get("material_type")''',
    "library academic filters",
    lambda: all(token in route_text for token in (
        'program_id = request.args.get("program_id", type=int)',
        'year = request.args.get("year", type=int)',
        'semester = request.args.get("semester", type=int)',
        "LibraryPublication.university_id == university_id",
    )),
)

replace_route_once_or_skip(
'''    publications = (
        query.order_by(order_col)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )''',
'''    relevance_order = []
    if viewer and not q and not university_id and not program_id and not year and not semester and not material_type:
        if viewer.university_id is not None:
            relevance_order.append((LibraryPublication.university_id == viewer.university_id).desc())
        if viewer.program_id is not None:
            relevance_order.append((LibraryPublication.program_id == viewer.program_id).desc())
        if viewer.year is not None:
            relevance_order.append((LibraryPublication.year == viewer.year).desc())
        if viewer.semester is not None:
            relevance_order.append((LibraryPublication.semester == viewer.semester).desc())

    publications = (
        query.order_by(*relevance_order, order_col)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )''',
    "library relevance ordering",
    lambda: "relevance_order = []" in route_text and "query.order_by(*relevance_order, order_col)" in route_text,
)

if "_library_context_matches(viewer, publication)" not in app_text:
    marker = 'LIBRARY_ACTIVE_STATUSES = ("pending", "approved")'
    if app_text.count(marker) != 1:
        raise SystemExit(f"FAIL CLOSED: Library active-status anchor: expected 1 match, found {app_text.count(marker)}")
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
    app_text = app_text.replace(marker, helper, 1)

replace_route_once_or_skip(
'''    query = LibraryPublication.query.filter_by(status="approved")
    flagged_document_ids = _flagged_document_ids()''',
'''    viewer = db.session.get(User, user_id)
    if not viewer:
        return jsonify({"error": "Account not found"}), 404
    if any(value is None for value in (viewer.university_id, viewer.program_id, viewer.year, viewer.semester)):
        return jsonify({"error": "Complete your university, course, year, and semester before accessing the Library"}), 400

    query = LibraryPublication.query.filter(
        LibraryPublication.status == "approved",
        LibraryPublication.university_id == viewer.university_id,
        LibraryPublication.program_id == viewer.program_id,
        LibraryPublication.year == viewer.year,
        LibraryPublication.semester == viewer.semester,
    )
    flagged_document_ids = _flagged_document_ids()''',
    "browse exact academic gate",
    lambda: "LibraryPublication.semester == viewer.semester" in route_text,
)

replace_route_once_or_skip(
'''    publication = db.session.get(LibraryPublication, publication_id)
    if not publication or publication.status != "approved":
        return jsonify({"error": "Library item not found"}), 404

    source = db.session.get(Document, publication.document_id)''',
'''    publication = db.session.get(LibraryPublication, publication_id)
    if not publication or publication.status != "approved":
        return jsonify({"error": "Library item not found"}), 404

    viewer = db.session.get(User, user_id)
    if not viewer:
        return jsonify({"error": "Account not found"}), 404
    if not _library_context_matches(viewer, publication):
        return jsonify({"error": "This Library item is not available for your university, course, year, and semester"}), 403

    source = db.session.get(Document, publication.document_id)''',
    "save exact academic gate",
    lambda: "_library_context_matches(viewer, publication)" in route_text,
)

APP.write_text(app_text, encoding="utf-8")
LIBRARY_ROUTES.write_text(route_text, encoding="utf-8")
LIBRARY_MODELS.write_text(library_model_text, encoding="utf-8")
print("Applied exact Library academic eligibility rules to app.py and library_routes.py.")
