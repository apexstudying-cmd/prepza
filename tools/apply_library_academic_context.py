from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY_ROUTES = ROOT / "library_routes.py"
LIBRARY_MODELS = ROOT / "library_models.py"
route_source = LIBRARY_ROUTES.read_text(encoding="utf-8")
route_start = route_source.find("    @app.route(")
if route_start < 0:
    raise SystemExit("FAIL CLOSED: extracted Library route registration block was not found")
route_prefix = route_source[:route_start]
text = "\n".join(line[4:] if line.startswith("    ") else line for line in route_source[route_start:].splitlines())
library_model_text = LIBRARY_MODELS.read_text(encoding="utf-8")

# The ORM model now belongs to library_models.py; route handlers remain in
# library_routes.py. Apply the schema transformation only when the legacy Unit field is
# still present, but always continue with route transformations below.
if all(token in library_model_text for token in (
    "university_id = db.Column",
    "program_id = db.Column",
    "year = db.Column",
    "semester = db.Column",
)):
    print("Skipped Library academic-context schema patch: canonical fields are already present.")
else:
    old_model = '''    unit_id = db.Column(db.Integer, db.ForeignKey("unit.id"), nullable=True)\n    title = db.Column(db.String(200), nullable=False)'''
    new_model = '''    # Publication context is a snapshot for this document, not a permanent\n    # mutation of the student's profile. This lets a student publish older\n    # or future-semester material without corrupting their current profile.\n    university_id = db.Column(db.Integer, db.ForeignKey("university.id"), nullable=True)\n    program_id = db.Column(db.Integer, db.ForeignKey("program.id"), nullable=True)\n    year = db.Column(db.Integer, nullable=True)\n    semester = db.Column(db.Integer, nullable=True)\n    title = db.Column(db.String(200), nullable=False)'''
    if library_model_text.count(old_model) != 1:
        raise SystemExit(f"FAIL CLOSED: LibraryPublication academic-context columns: expected 1 match, found {library_model_text.count(old_model)}")
    library_model_text = library_model_text.replace(old_model, new_model, 1)


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"FAIL CLOSED: {label}: expected 1 match, found {count}")
    text = text.replace(old, new, 1)


def replace_all_exact(old, new, expected, label):
    global text
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"FAIL CLOSED: {label}: expected {expected} matches, found {count}")
    text = text.replace(old, new)


def replace_once_or_skip(old, new, label, already_applied):
    global text
    count = text.count(old)
    if count == 1:
        text = text.replace(old, new, 1)
        return
    if count == 0 and already_applied():
        print(f"Skipped {label}: canonical implementation is already present.")
        return
    raise SystemExit(f"FAIL CLOSED: {label}: expected 1 legacy match or a verified canonical implementation, found {count}")


def replace_all_exact_or_skip(old, new, expected, label, already_applied):
    global text
    count = text.count(old)
    if count == expected:
        text = text.replace(old, new)
        return
    if count == 0 and already_applied():
        print(f"Skipped {label}: canonical response fields are already present.")
        return
    raise SystemExit(f"FAIL CLOSED: {label}: expected {expected} legacy matches or verified canonical fields, found {count}")


replace_once_or_skip(
'''    material_type = (data.get("material_type") or "").strip()\n    unit_id = data.get("unit_id")\n\n    if not document_id:''',
'''    material_type = (data.get("material_type") or "").strip()\n    university_id = data.get("university_id")\n    program_id = data.get("program_id")\n    year = data.get("year")\n    semester = data.get("semester")\n\n    user = db.session.get(User, user_id)\n    if not user:\n        return jsonify({"error": "Account not found"}), 404\n\n    # Profile values are defaults only. The publication stores the final\n    # confirmed context independently, so a stale profile never rewrites an\n    # already-published document's academic placement.\n    if university_id is None:\n        university_id = user.university_id\n    if program_id is None:\n        program_id = user.program_id\n    if year is None:\n        year = user.year\n    if semester is None:\n        semester = user.semester\n\n    if not document_id:''',
    "publish metadata inputs/defaults",
    lambda: all(token in text for token in (
        'university_id = data.get("university_id")',
        'program_id = data.get("program_id")',
        'year = data.get("year")',
        'semester = data.get("semester")',
        'if university_id is None: university_id = user.university_id',
        'if program_id is None: program_id = user.program_id',
        'if year is None: year = user.year',
        'if semester is None: semester = user.semester',
    )),
)

replace_once_or_skip(
'''    publication = LibraryPublication(\n        document_id=document_id,\n        user_id=user_id,\n        unit_id=unit_id,\n        title=title,''',
'''    publication = LibraryPublication(\n        document_id=document_id,\n        user_id=user_id,\n        university_id=university_id,\n        program_id=program_id,\n        year=year,\n        semester=semester,\n        title=title,''',
    "persist publication academic context",
    lambda: all(token in text for token in (
        '        university_id=university_id,',
        '        program_id=program_id,',
        '        year=year,',
        '        semester=semester,',
    )),
)

replace_all_exact_or_skip(
'''            "unit_id": pub.unit_id,\n            "unit_code": unit.code if unit else None,''',
'''            "university_id": pub.university_id,\n            "program_id": pub.program_id,\n            "year": pub.year,\n            "semester": pub.semester,''',
    4,
    "student-facing library metadata responses",
    lambda: (
        '"unit_id": pub.unit_id' not in text
        and '"unit_code": unit.code if unit else None' not in text
        and all(text.count(token) >= 2 for token in (
            '"university_id": pub.university_id',
            '"program_id": pub.program_id',
            '"year": pub.year',
            '"semester": pub.semester',
        ))
    ),
)

replace_once_or_skip(
'''    user_id = session.get("user_id")\n    if not user_id:\n        return jsonify({"error": "Not logged in"}), 401\n\n    query = LibraryPublication.query.filter_by(status="approved")''',
'''    user_id = session.get("user_id")\n    if not user_id:\n        return jsonify({"error": "Not logged in"}), 401\n\n    viewer = db.session.get(User, user_id)\n    query = LibraryPublication.query.filter_by(status="approved")''',
    "library browse viewer",
    lambda: (
        (lambda start: start >= 0 and "viewer = db.session.get(User, user_id)" in text[start:text.find("\n@app.route", start + 1)])
        (text.find("def browse_library():"))
    ),
)

replace_once_or_skip(
'''    university_id = request.args.get("university_id", type=int)\n    if university_id:\n        query = query.join(Unit, LibraryPublication.unit_id == Unit.id).filter(\n            Unit.university_id == university_id\n        )\n\n    material_type = request.args.get("material_type")''',
'''    university_id = request.args.get("university_id", type=int)\n    if university_id:\n        query = query.filter(LibraryPublication.university_id == university_id)\n\n    program_id = request.args.get("program_id", type=int)\n    if program_id:\n        query = query.filter(LibraryPublication.program_id == program_id)\n\n    year = request.args.get("year", type=int)\n    if year:\n        query = query.filter(LibraryPublication.year == year)\n\n    semester = request.args.get("semester", type=int)\n    if semester:\n        query = query.filter(LibraryPublication.semester == semester)\n\n    material_type = request.args.get("material_type")''',
    "library academic filters",
    lambda: all(token in text for token in (
        'program_id = request.args.get("program_id", type=int)',
        'year = request.args.get("year", type=int)',
        'semester = request.args.get("semester", type=int)',
        'query = query.filter(LibraryPublication.university_id == university_id)',
    )),
)

replace_once_or_skip(
'''    publications = (\n        query.order_by(order_col)\n        .offset((page - 1) * per_page)\n        .limit(per_page)\n        .all()\n    )''',
'''    relevance_order = []\n    if viewer and not q and not university_id and not program_id and not year and not semester and not material_type:\n        # Exact academic matches rise to the top without excluding broader\n        # discovery. Publication context is independent from the student's\n        # current profile, so old-semester uploads stay correctly placed.\n        if viewer.university_id is not None:\n            relevance_order.append((LibraryPublication.university_id == viewer.university_id).desc())\n        if viewer.program_id is not None:\n            relevance_order.append((LibraryPublication.program_id == viewer.program_id).desc())\n        if viewer.year is not None:\n            relevance_order.append((LibraryPublication.year == viewer.year).desc())\n        if viewer.semester is not None:\n            relevance_order.append((LibraryPublication.semester == viewer.semester).desc())\n\n    publications = (\n        query.order_by(*relevance_order, order_col)\n        .offset((page - 1) * per_page)\n        .limit(per_page)\n        .all()\n    )''',
    "library relevance ordering",
    lambda: (
        "relevance_order = []" in text
        and "query.order_by(*relevance_order, order_col)" in text
    ),
)

LIBRARY_ROUTES.write_text((route_prefix + "\n".join(("    " + line) if line else "" for line in text.splitlines())).rstrip() + "\n", encoding="utf-8")
LIBRARY_MODELS.write_text(library_model_text, encoding="utf-8")
print("Applied Library academic-context patch successfully.")
