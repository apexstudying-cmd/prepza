"""Reconciled admin routes restored from the last complete admin runtime."""
import app as _app
# The module is imported at the end of app.py, after the current application
# globals and modular runtimes have been initialized.
globals().update({k:getattr(_app,k) for k in dir(_app) if not k.startswith("__")})

ADMIN_USER_STATUS_VALUES = ("active", "suspended")

ADMIN_USER_SUB_VALUES = ("free", "premium")

@app.route("/admin/users")

def admin_list_users():
    """
    Lists users for the admin dashboard, optionally filtered by an
    email/display_name substring, suspension status, and subscription
    tier. Newest signups first; users with no created_at (pre-migration
    accounts) sort last rather than first.

    Each row is enriched with document count, AI request count, and
    current subscription plan - all computed via grouped aggregate
    queries up front (one query per metric) rather than per-user
    lookups, so this stays cheap regardless of user count.
    """
    search = (request.args.get("search") or "").strip().lower()
    status_filter = (request.args.get("status") or "").strip().lower()
    sub_filter = (request.args.get("sub") or "").strip().lower()

    if status_filter and status_filter not in ADMIN_USER_STATUS_VALUES:
        return jsonify({"error": "status must be one of: " + ", ".join(ADMIN_USER_STATUS_VALUES)}), 400
    if sub_filter and sub_filter not in ADMIN_USER_SUB_VALUES:
        return jsonify({"error": "sub must be one of: " + ", ".join(ADMIN_USER_SUB_VALUES)}), 400

    query = User.query
    if search:
        query = query.filter(
            or_(
                User.email.ilike(f"%{search}%"),
                User.display_name.ilike(f"%{search}%"),
            )
        )
    if status_filter == "active":
        query = query.filter(User.is_suspended.is_(False))
    elif status_filter == "suspended":
        query = query.filter(User.is_suspended.is_(True))

    users = query.all()
    users.sort(key=lambda u: u.created_at or datetime.min, reverse=True)
    user_ids = [u.id for u in users]

    doc_counts = dict(
        db.session.query(Document.user_id, func.count(Document.id))
        .filter(Document.user_id.in_(user_ids), Document.is_removed.is_(False))
        .group_by(Document.user_id)
        .all()
    ) if user_ids else {}

    ai_counts = dict(
        db.session.query(AiUsageLog.user_id, func.count(AiUsageLog.id))
        .filter(AiUsageLog.user_id.in_(user_ids))
        .group_by(AiUsageLog.user_id)
        .all()
    ) if user_ids else {}

    # Latest successful subscription payment per user, so plan can be
    # derived the same way get_user_subscription_status() does for a
    # single user - done here as one grouped query instead of N calls.
    sub_rows = (
        db.session.query(Payment.user_id, Payment.plan, Payment.subscription_expires_at)
        .filter(
            Payment.user_id.in_(user_ids),
            Payment.payment_type == "subscription",
            Payment.status == "success",
            Payment.subscription_expires_at.isnot(None),
        )
        .all()
    ) if user_ids else []
    latest_sub = {}
    for uid, plan, expires_at in sub_rows:
        existing = latest_sub.get(uid)
        if existing is None or expires_at > existing[1]:
            latest_sub[uid] = (plan, expires_at)

    now = datetime.utcnow()
    result = []
    for u in users:
        sub_entry = latest_sub.get(u.id)
        is_sub_active = bool(sub_entry and sub_entry[1] > now)
        plan = sub_entry[0] if (sub_entry and is_sub_active) else "free"

        if sub_filter == "premium" and plan == "free":
            continue
        if sub_filter == "free" and plan != "free":
            continue

        university = db.session.get(University, u.university_id) if u.university_id else None
        program = db.session.get(Program, u.program_id) if u.program_id else None

        result.append({
            "id": u.id,
            "email": u.email,
            "year": u.year,
            "semester": u.semester,
            "display_name": u.display_name,
            "email_verified": u.email_verified,
            "is_admin": u.is_admin,
            "is_suspended": u.is_suspended,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "signup_source": u.signup_source,
            "university_name": university.name if university else None,
            "program_name": program.name if program else None,
            "documents_count": doc_counts.get(u.id, 0),
            "ai_requests_count": ai_counts.get(u.id, 0),
            "subscription_plan": plan,
            "subscription_active": is_sub_active,
        })

    return jsonify(result)

@app.route("/admin/users/<int:user_id>", methods=["PATCH"])

def admin_update_user(user_id):
    """
    Lets an admin edit a student's year/semester, or toggle their
    is_admin / is_suspended flags. Self-protection: the acting admin
    cannot remove their own is_admin flag or suspend themselves here -
    that would risk locking the only admin out with no recovery path
    short of a direct DB edit.
    """
    acting_admin_id = session.get("user_id")

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    target_user = db.session.get(User, user_id)
    if not target_user:
        return jsonify({"error": "User not found"}), 404

    if "year" in data:
        year = data["year"]
        if year is not None:
            if not isinstance(year, int) or year < 1 or year > 4:
                return jsonify({"error": "Year must be a number between 1 and 4"}), 400
        target_user.year = year

    if "semester" in data:
        semester = data["semester"]
        if semester is not None:
            if not isinstance(semester, int) or semester not in (1, 2):
                return jsonify({"error": "Semester must be 1 or 2"}), 400
        target_user.semester = semester

    if "is_admin" in data:
        is_admin = data["is_admin"]
        if not isinstance(is_admin, bool):
            return jsonify({"error": "is_admin must be true or false"}), 400
        if user_id == acting_admin_id and is_admin is False:
            return jsonify({"error": "You can't remove your own admin access"}), 400
        target_user.is_admin = is_admin

    if "is_suspended" in data:
        is_suspended = data["is_suspended"]
        if not isinstance(is_suspended, bool):
            return jsonify({"error": "is_suspended must be true or false"}), 400
        if user_id == acting_admin_id and is_suspended is True:
            return jsonify({"error": "You can't suspend your own account"}), 400
        target_user.is_suspended = is_suspended

    _audit_details = {}
    if "is_admin" in data:
        _audit_details["is_admin"] = target_user.is_admin
    if "is_suspended" in data:
        _audit_details["is_suspended"] = target_user.is_suspended
    if _audit_details:
        log_admin_action(acting_admin_id, "user_updated", target_type="user", target_id=target_user.id, details=_audit_details)
    db.session.commit()

    return jsonify({
        "id": target_user.id,
        "email": target_user.email,
        "year": target_user.year,
        "semester": target_user.semester,
        "is_admin": target_user.is_admin,
        "is_suspended": target_user.is_suspended,
    })


# ---------- Admin: universities & programs (Chunk 10) ----------

UNIVERSITY_NAME_MAX = 150

UNIVERSITY_SHORT_CODE_MAX = 20

UNIVERSITY_COUNTRY_MAX = 80

def _serialize_admin_university(university):
    return {
        "id": university.id,
        "name": university.name,
        "short_code": university.short_code,
        "country": university.country,
        "is_active": university.is_active,
        "created_at": university.created_at.isoformat() if university.created_at else None,
    }

@app.route("/admin/universities", methods=["GET"])

def admin_list_universities():
    """Lists ALL universities (active and inactive) for admin management -
    unlike the public GET /universities, which only returns active ones."""
    universities = University.query.order_by(University.name).all()
    return jsonify({"universities": [_serialize_admin_university(u) for u in universities]})

@app.route("/admin/universities", methods=["POST"])

def admin_create_university():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    name = (data.get("name") or "").strip()
    short_code = (data.get("short_code") or "").strip().upper()
    country = data.get("country")

    if not name or len(name) > UNIVERSITY_NAME_MAX:
        return jsonify({"error": f"name is required and must be {UNIVERSITY_NAME_MAX} characters or fewer"}), 400
    if not short_code or len(short_code) > UNIVERSITY_SHORT_CODE_MAX:
        return jsonify({
            "error": f"short_code is required and must be {UNIVERSITY_SHORT_CODE_MAX} characters or fewer"
        }), 400
    if University.query.filter_by(short_code=short_code).first():
        return jsonify({"error": "A university with this short_code already exists"}), 409

    if country is not None:
        if not isinstance(country, str):
            return jsonify({"error": "country must be a string"}), 400
        country = country.strip() or None
        if country and len(country) > UNIVERSITY_COUNTRY_MAX:
            return jsonify({"error": f"country must be {UNIVERSITY_COUNTRY_MAX} characters or fewer"}), 400

    university = University(name=name, short_code=short_code, country=country)
    db.session.add(university)
    db.session.commit()

    return jsonify(_serialize_admin_university(university)), 201

@app.route("/admin/universities/<int:university_id>", methods=["PATCH"])

def admin_update_university(university_id):
    """
    Edits a university's fields and/or toggles is_active. Deactivating
    hides it from the public /universities and
    /universities/<id>/programs routes (and therefore from new student
    signups) without deleting anything - same reactive kill-switch
    pattern used throughout this file (Organisation.is_active,
    Group.is_active, etc).
    """
    university = db.session.get(University, university_id)
    if not university:
        return jsonify({"error": "University not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name or len(name) > UNIVERSITY_NAME_MAX:
            return jsonify({"error": f"name must be 1-{UNIVERSITY_NAME_MAX} characters"}), 400
        university.name = name

    if "short_code" in data:
        short_code = (data.get("short_code") or "").strip().upper()
        if not short_code or len(short_code) > UNIVERSITY_SHORT_CODE_MAX:
            return jsonify({"error": f"short_code must be 1-{UNIVERSITY_SHORT_CODE_MAX} characters"}), 400
        existing = University.query.filter_by(short_code=short_code).first()
        if existing and existing.id != university.id:
            return jsonify({"error": "A university with this short_code already exists"}), 409
        university.short_code = short_code

    if "country" in data:
        country = data.get("country")
        if country is not None:
            if not isinstance(country, str):
                return jsonify({"error": "country must be a string"}), 400
            country = country.strip() or None
            if country and len(country) > UNIVERSITY_COUNTRY_MAX:
                return jsonify({"error": f"country must be {UNIVERSITY_COUNTRY_MAX} characters or fewer"}), 400
        university.country = country

    if "is_active" in data:
        is_active = data["is_active"]
        if not isinstance(is_active, bool):
            return jsonify({"error": "is_active must be true or false"}), 400
        university.is_active = is_active

    db.session.commit()

    return jsonify(_serialize_admin_university(university))

PROGRAM_NAME_MAX = 150

PROGRAM_DEGREE_LEVEL_MAX = 50

PROGRAM_DISCIPLINE_CATEGORY_MAX = 80

def _serialize_admin_program(program):
    university = db.session.get(University, program.university_id)
    return {
        "id": program.id,
        "university_id": program.university_id,
        "university_name": university.name if university else None,
        "name": program.name,
        "degree_level": program.degree_level,
        "discipline_category": program.discipline_category,
        "is_active": program.is_active,
        "created_at": program.created_at.isoformat() if program.created_at else None,
    }

@app.route("/admin/programs", methods=["GET"])

def admin_list_programs():
    """Lists ALL programs (active and inactive), optionally filtered by
    ?university_id= - for admin management, unlike the public
    per-university GET /universities/<id>/programs, which only returns
    active ones."""
    query = Program.query
    university_id = request.args.get("university_id", type=int)
    if university_id:
        query = query.filter_by(university_id=university_id)
    programs = query.order_by(Program.name).all()
    return jsonify({"programs": [_serialize_admin_program(p) for p in programs]})

@app.route("/admin/programs", methods=["POST"])

def admin_create_program():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    university_id = data.get("university_id")
    if not isinstance(university_id, int) or isinstance(university_id, bool):
        return jsonify({"error": "university_id is required"}), 400
    if not db.session.get(University, university_id):
        return jsonify({"error": "University not found"}), 404

    name = (data.get("name") or "").strip()
    if not name or len(name) > PROGRAM_NAME_MAX:
        return jsonify({"error": f"name is required and must be {PROGRAM_NAME_MAX} characters or fewer"}), 400

    degree_level = data.get("degree_level")
    if degree_level is not None:
        if not isinstance(degree_level, str):
            return jsonify({"error": "degree_level must be a string"}), 400
        degree_level = degree_level.strip() or None
        if degree_level and len(degree_level) > PROGRAM_DEGREE_LEVEL_MAX:
            return jsonify({"error": f"degree_level must be {PROGRAM_DEGREE_LEVEL_MAX} characters or fewer"}), 400

    discipline_category = data.get("discipline_category")
    if discipline_category is not None:
        if not isinstance(discipline_category, str):
            return jsonify({"error": "discipline_category must be a string"}), 400
        discipline_category = discipline_category.strip() or None
        if discipline_category and len(discipline_category) > PROGRAM_DISCIPLINE_CATEGORY_MAX:
            return jsonify({
                "error": f"discipline_category must be {PROGRAM_DISCIPLINE_CATEGORY_MAX} characters or fewer"
            }), 400

    program = Program(
        university_id=university_id, name=name,
        degree_level=degree_level, discipline_category=discipline_category,
    )
    db.session.add(program)
    db.session.commit()

    return jsonify(_serialize_admin_program(program)), 201

@app.route("/admin/programs/<int:program_id>", methods=["PATCH"])

def admin_update_program(program_id):
    """
    Edits a program's fields and/or toggles is_active. Deactivating
    hides it from the public /universities/<id>/programs route (and
    therefore from new student signups picking a course), without
    deleting anything.
    """
    program = db.session.get(Program, program_id)
    if not program:
        return jsonify({"error": "Program not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name or len(name) > PROGRAM_NAME_MAX:
            return jsonify({"error": f"name must be 1-{PROGRAM_NAME_MAX} characters"}), 400
        program.name = name

    if "degree_level" in data:
        degree_level = data.get("degree_level")
        if degree_level is not None:
            if not isinstance(degree_level, str):
                return jsonify({"error": "degree_level must be a string"}), 400
            degree_level = degree_level.strip() or None
            if degree_level and len(degree_level) > PROGRAM_DEGREE_LEVEL_MAX:
                return jsonify({"error": f"degree_level must be {PROGRAM_DEGREE_LEVEL_MAX} characters or fewer"}), 400
        program.degree_level = degree_level

    if "discipline_category" in data:
        discipline_category = data.get("discipline_category")
        if discipline_category is not None:
            if not isinstance(discipline_category, str):
                return jsonify({"error": "discipline_category must be a string"}), 400
            discipline_category = discipline_category.strip() or None
            if discipline_category and len(discipline_category) > PROGRAM_DISCIPLINE_CATEGORY_MAX:
                return jsonify({
                    "error": f"discipline_category must be {PROGRAM_DISCIPLINE_CATEGORY_MAX} characters or fewer"
                }), 400
        program.discipline_category = discipline_category

    if "is_active" in data:
        is_active = data["is_active"]
        if not isinstance(is_active, bool):
            return jsonify({"error": "is_active must be true or false"}), 400
        program.is_active = is_active

    db.session.commit()

    return jsonify(_serialize_admin_program(program))


# ---------- Admin: groups (Chunk 10) ----------

@app.route("/admin/groups")

def admin_list_groups():
    """
    Lists groups for the admin dashboard, optionally filtered by
    ?search= (name substring) and ?status=active|inactive. Newest first.
    """
    search = (request.args.get("search") or "").strip()
    status_filter = (request.args.get("status") or "").strip().lower()
    if status_filter and status_filter not in ("active", "inactive"):
        return jsonify({"error": "status must be 'active' or 'inactive'"}), 400

    query = Group.query
    if search:
        query = query.filter(Group.name.ilike(f"%{search}%"))
    if status_filter == "active":
        query = query.filter(Group.is_active.is_(True))
    elif status_filter == "inactive":
        query = query.filter(Group.is_active.is_(False))

    groups = query.order_by(Group.created_at.desc()).all()

    return jsonify({"groups": [_serialize_group(g) for g in groups]})

@app.route("/admin/groups/<int:group_id>", methods=["PATCH"])

def admin_update_group(group_id):
    """
    Admin kill-switch: activate/deactivate a group. Deactivating hides it
    from browse/join and blocks new posts/comments/joins for existing
    members too (see the is_active checks in join_group /
    create_group_post / create_group_post_comment) - stricter than the
    Organisation.is_active pattern, which only hides new opportunities
    rather than blocking ongoing member activity.
    """
    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    if "is_active" in data:
        is_active = data["is_active"]
        if not isinstance(is_active, bool):
            return jsonify({"error": "is_active must be true or false"}), 400
        group.is_active = is_active

    db.session.commit()

    return jsonify(_serialize_group(group))



@app.route("/admin/settings", methods=["GET"])
@require_admin
def admin_get_settings():
    rows = {row.key: row.value for row in SystemSetting.query.all()}

    def integer(key, default=0):
        try:
            return int(rows.get(key, str(default)) or default)
        except (TypeError, ValueError):
            return default

    def optional_integer(key, default=None):
        raw = rows.get(key)
        if raw is None or str(raw).strip().lower() == "unlimited":
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    try:
        budget = float(rows.get("ai_monthly_budget_usd", "20.00") or "20.00")
    except (TypeError, ValueError):
        budget = 20.0

    return jsonify({
        "maintenance_mode": rows.get("maintenance_mode", "false") == "true",
        "maintenance_message": rows.get("maintenance_message", ""),
        "prepza_control_enabled": rows.get("prepza_control_enabled", "false") == "true",
        "price_notes": integer("price_notes"),
        "price_past_paper": integer("price_past_paper"),
        "price_qna": integer("price_qna"),
        "price_promotion_standard": integer("price_promotion_standard"),
        "price_promotion_featured": integer("price_promotion_featured"),
        "price_promotion_sponsored": integer("price_promotion_sponsored"),
        "ai_daily_limit_free": optional_integer("ai_daily_limit_free", 5),
        "ai_daily_limit_plus": optional_integer("ai_daily_limit_plus", 15),
        "ai_daily_limit_premium": optional_integer("ai_daily_limit_premium", None),
        "ai_daily_tutor_limit_free": optional_integer("ai_daily_tutor_limit_free", 10),
        "ai_daily_tutor_limit_plus": optional_integer("ai_daily_tutor_limit_plus", 30),
        "ai_daily_tutor_limit_premium": optional_integer("ai_daily_tutor_limit_premium", None),
        "ai_monthly_budget_usd": budget,
    })


@app.route("/admin/settings", methods=["PATCH"])
@require_csrf
@require_admin
def admin_update_settings():
    data = request.get_json(silent=True) or {}
    allowed = {
        "maintenance_mode", "maintenance_message", "prepza_control_enabled",
        "price_notes", "price_past_paper", "price_qna",
        "price_promotion_standard", "price_promotion_featured", "price_promotion_sponsored",
        "ai_daily_limit_free", "ai_daily_limit_plus", "ai_daily_limit_premium",
        "ai_daily_tutor_limit_free", "ai_daily_tutor_limit_plus", "ai_daily_tutor_limit_premium",
        "ai_monthly_budget_usd",
    }
    unknown = sorted(set(data) - allowed)
    if unknown:
        return jsonify({"error": f"Unsupported settings: {', '.join(unknown)}"}), 400

    for key, value in data.items():
        if key in {"maintenance_mode", "prepza_control_enabled"}:
            if not isinstance(value, bool):
                return jsonify({"error": f"{key} must be true or false"}), 400
            value = "true" if value else "false"
        elif key == "maintenance_message":
            if not isinstance(value, str) or len(value) > 500:
                return jsonify({"error": "maintenance_message must be a string of 500 characters or fewer"}), 400
        elif key == "ai_monthly_budget_usd":
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                return jsonify({"error": "ai_monthly_budget_usd must be a positive number"}), 400
            value = str(value)
        elif key.startswith("ai_daily_"):
            if value is None:
                value = "unlimited"
            elif not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return jsonify({"error": f"{key} must be a non-negative integer or null"}), 400
            else:
                value = str(value)
        else:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return jsonify({"error": f"{key} must be a non-negative integer"}), 400
            value = str(value)

        row = SystemSetting.query.filter_by(key=key).first()
        if not row:
            row = SystemSetting(key=key, value=str(value))
            db.session.add(row)
        else:
            row.value = str(value)

    db.session.commit()
    return admin_get_settings()
