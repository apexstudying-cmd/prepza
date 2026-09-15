from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"
text = APP.read_text()


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"FAIL CLOSED: {label}: expected 1 match, found {count}")
    text = text.replace(old, new, 1)

replace_once(
'''    unit_id = db.Column(db.Integer, db.ForeignKey("unit.id"), nullable=True)\n    title = db.Column(db.String(200), nullable=False)''',
'''    unit_id = db.Column(db.Integer, db.ForeignKey("unit.id"), nullable=True)\n    # Publication context is a snapshot for this document, not a permanent\n    # mutation of the student's profile. This lets a student publish older\n    # or future-semester material without corrupting their current profile.\n    university_id = db.Column(db.Integer, db.ForeignKey("university.id"), nullable=True)\n    program_id = db.Column(db.Integer, db.ForeignKey("program.id"), nullable=True)\n    year = db.Column(db.Integer, nullable=True)\n    semester = db.Column(db.Integer, nullable=True)\n    title = db.Column(db.String(200), nullable=False)''',
    "LibraryPublication academic-context columns",
)

replace_once(
'''    material_type = (data.get("material_type") or "").strip()\n    unit_id = data.get("unit_id")\n\n    if not document_id:''',
'''    material_type = (data.get("material_type") or "").strip()\n    unit_id = data.get("unit_id")\n    university_id = data.get("university_id")\n    program_id = data.get("program_id")\n    year = data.get("year")\n    semester = data.get("semester")\n\n    user = db.session.get(User, user_id)\n    if not user:\n        return jsonify({"error": "Account not found"}), 404\n\n    # Profile values are defaults only. The publication stores the final\n    # confirmed context independently, so a stale profile never rewrites an\n    # already-published document's academic placement.\n    if university_id is None:\n        university_id = user.university_id\n    if program_id is None:\n        program_id = user.program_id\n    if year is None:\n        year = user.year\n    if semester is None:\n        semester = user.semester\n\n    if not document_id:''',
    "publish metadata inputs/defaults",
)

replace_once(
'''    if unit_id is not None:\n        if not db.session.get(Unit, unit_id):\n            return jsonify({"error": "Unit not found"}), 404\n\n    if _document_content_has_flagged_material(document.document_content_id):''',
'''    if university_id is not None:\n        if not isinstance(university_id, int) or isinstance(university_id, bool):\n            return jsonify({"error": "university_id must be an integer"}), 400\n        university = University.query.filter_by(id=university_id, is_active=True).first()\n        if not university:\n            return jsonify({"error": "Selected university was not found"}), 400\n\n    if program_id is not None:\n        if not isinstance(program_id, int) or isinstance(program_id, bool):\n            return jsonify({"error": "program_id must be an integer"}), 400\n        if university_id is None:\n            return jsonify({"error": "program_id requires a university_id"}), 400\n        program = Program.query.filter_by(id=program_id, university_id=university_id, is_active=True).first()\n        if not program:\n            return jsonify({"error": "Selected course does not belong to the selected university"}), 400\n\n    if year is not None:\n        if not isinstance(year, int) or isinstance(year, bool) or not 1 <= year <= 8:\n            return jsonify({"error": "year must be an integer between 1 and 8"}), 400\n    if semester is not None:\n        if not isinstance(semester, int) or isinstance(semester, bool) or semester not in (1, 2):\n            return jsonify({"error": "semester must be 1 or 2"}), 400\n\n    if unit_id is not None:\n        unit = db.session.get(Unit, unit_id)\n        if not unit:\n            return jsonify({"error": "Unit not found"}), 404\n        if university_id is not None and unit.university_id not in (None, university_id):\n            return jsonify({"error": "Selected unit does not belong to the selected university"}), 400\n        if year is not None and unit.year != year:\n            return jsonify({"error": "Selected unit does not belong to the selected year"}), 400\n        if semester is not None and unit.semester != semester:\n            return jsonify({"error": "Selected unit does not belong to the selected semester"}), 400\n        if program_id is not None:\n            linked = UnitProgram.query.filter_by(unit_id=unit.id, program_id=program_id).first()\n            if not linked:\n                return jsonify({"error": "Selected unit is not part of the selected course"}), 400\n\n    if _document_content_has_flagged_material(document.document_content_id):''',
    "publish metadata validation",
)

replace_once(
'''    publication = LibraryPublication(\n        document_id=document_id,\n        user_id=user_id,\n        unit_id=unit_id,\n        title=title,''',
'''    publication = LibraryPublication(\n        document_id=document_id,\n        user_id=user_id,\n        unit_id=unit_id,\n        university_id=university_id,\n        program_id=program_id,\n        year=year,\n        semester=semester,\n        title=title,''',
    "persist publication academic context",
)

replace_once(
'''            "unit_id": pub.unit_id,\n            "unit_code": unit.code if unit else None,''',
'''            "unit_id": pub.unit_id,\n            "unit_code": unit.code if unit else None,\n            "university_id": pub.university_id,\n            "program_id": pub.program_id,\n            "year": pub.year,\n            "semester": pub.semester,''',
    "submission metadata response",
)

replace_once(
'''    user_id = session.get("user_id")\n    if not user_id:\n        return jsonify({"error": "Not logged in"}), 401\n\n    query = LibraryPublication.query.filter_by(status="approved")''',
'''    user_id = session.get("user_id")\n    if not user_id:\n        return jsonify({"error": "Not logged in"}), 401\n\n    viewer = db.session.get(User, user_id)\n    query = LibraryPublication.query.filter_by(status="approved")''',
    "library browse viewer",
)

replace_once(
'''    university_id = request.args.get("university_id", type=int)\n    if university_id:\n        query = query.join(Unit, LibraryPublication.unit_id == Unit.id).filter(\n            Unit.university_id == university_id\n        )\n\n    material_type = request.args.get("material_type")''',
'''    university_id = request.args.get("university_id", type=int)\n    if university_id:\n        query = query.filter(LibraryPublication.university_id == university_id)\n\n    program_id = request.args.get("program_id", type=int)\n    if program_id:\n        query = query.filter(LibraryPublication.program_id == program_id)\n\n    year = request.args.get("year", type=int)\n    if year:\n        query = query.filter(LibraryPublication.year == year)\n\n    semester = request.args.get("semester", type=int)\n    if semester:\n        query = query.filter(LibraryPublication.semester == semester)\n\n    material_type = request.args.get("material_type")''',
    "library academic filters",
)

replace_once(
'''    publications = (\n        query.order_by(order_col)\n        .offset((page - 1) * per_page)\n        .limit(per_page)\n        .all()\n    )''',
'''    relevance_order = []\n    if viewer and not q and not unit_id and not university_id and not program_id and not year and not semester and not material_type:\n        # Exact academic matches rise to the top without excluding broader\n        # discovery. Publication context is independent from the student's\n        # current profile, so old-semester uploads stay correctly placed.\n        if viewer.university_id is not None:\n            relevance_order.append((LibraryPublication.university_id == viewer.university_id).desc())\n        if viewer.program_id is not None:\n            relevance_order.append((LibraryPublication.program_id == viewer.program_id).desc())\n        if viewer.year is not None:\n            relevance_order.append((LibraryPublication.year == viewer.year).desc())\n        if viewer.semester is not None:\n            relevance_order.append((LibraryPublication.semester == viewer.semester).desc())\n\n    publications = (\n        query.order_by(*relevance_order, order_col)\n        .offset((page - 1) * per_page)\n        .limit(per_page)\n        .all()\n    )''',
    "library relevance ordering",
)

replace_once(
'''            "unit_id": pub.unit_id,\n            "unit_code": unit.code if unit else None,\n            "author": _display_name(author) if author else "Deleted user",''',
'''            "unit_id": pub.unit_id,\n            "unit_code": unit.code if unit else None,\n            "university_id": pub.university_id,\n            "program_id": pub.program_id,\n            "year": pub.year,\n            "semester": pub.semester,\n            "author": _display_name(author) if author else "Deleted user",''',
    "library browse metadata response",
)

# The same response shape appears in /library/saved; apply the academic
# fields to that occurrence after the browse response has already been
# changed above.
replace_once(
'''            "unit_id": pub.unit_id,\n            "unit_code": unit.code if unit else None,\n            "author": _display_name(author) if author else "Deleted user",''',
'''            "unit_id": pub.unit_id,\n            "unit_code": unit.code if unit else None,\n            "university_id": pub.university_id,\n            "program_id": pub.program_id,\n            "year": pub.year,\n            "semester": pub.semester,\n            "author": _display_name(author) if author else "Deleted user",''',
    "saved library metadata response",
)

replace_once(
'''            "unit_id": pub.unit_id,\n            "unit_code": unit.code if unit else None,\n            "author_email": author.email if author else None,''',
'''            "unit_id": pub.unit_id,\n            "unit_code": unit.code if unit else None,\n            "university_id": pub.university_id,\n            "program_id": pub.program_id,\n            "year": pub.year,\n            "semester": pub.semester,\n            "author_email": author.email if author else None,''',
    "admin library metadata response",
)

APP.write_text(text)
print("Applied Library academic-context patch successfully.")
