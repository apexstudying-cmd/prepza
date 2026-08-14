"""
Chunk 5 patch script (3): adds Group routes (create, browse, mine,
detail, join, leave). Requires chunk5_models_patch.py to have been
applied first (needs Group/GroupMember to exist).

Safe to re-run: if the routes are already present, it exits without
changing anything.

Usage:
    cd ~/Desktop/prepza
    python chunk5_routes_groups_patch.py
    git diff app.py
"""

APP_PY = "app.py"

ANCHOR = '''    report.status = resolution
    report.admin_notes = admin_notes
    report.reviewed_by = acting_admin_id
    report.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"id": report.id, "status": report.status})


# ---------- Content routes (student-facing) ----------'''

MARKER = "def create_group():"

NEW_ROUTES = '''    report.status = resolution
    report.admin_notes = admin_notes
    report.reviewed_by = acting_admin_id
    report.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"id": report.id, "status": report.status})


# ---------- Groups ----------

GROUP_NAME_MAX = 150
GROUP_DESCRIPTION_MAX = 1000
GROUP_PRIVACY_VALUES = {"public", "private", "course_only"}


def _serialize_group(group, membership=None):
    unit = db.session.get(Unit, group.unit_id) if group.unit_id else None
    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "privacy": group.privacy,
        "university_id": group.university_id,
        "program_id": group.program_id,
        "unit_id": group.unit_id,
        "unit_code": unit.code if unit else None,
        "year": group.year,
        "member_count": group.member_count,
        "created_by": group.created_by,
        "created_at": group.created_at.isoformat() if group.created_at else None,
        "is_member": membership is not None,
        "role": membership.role if membership else None,
    }


@app.route("/groups", methods=["POST"])
@require_csrf
def create_group():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    name = (data.get("name") or "").strip()
    if not name or len(name) > GROUP_NAME_MAX:
        return jsonify({"error": f"name is required and must be {GROUP_NAME_MAX} characters or fewer"}), 400

    description = data.get("description")
    if description is not None:
        if not isinstance(description, str):
            return jsonify({"error": "description must be a string"}), 400
        description = description.strip() or None
        if description and len(description) > GROUP_DESCRIPTION_MAX:
            return jsonify({"error": f"description must be {GROUP_DESCRIPTION_MAX} characters or fewer"}), 400

    privacy = (data.get("privacy") or "public").strip().lower()
    if privacy not in GROUP_PRIVACY_VALUES:
        return jsonify({"error": "privacy must be one of: " + ", ".join(sorted(GROUP_PRIVACY_VALUES))}), 400

    university_id = data.get("university_id")
    if university_id is not None:
        if not isinstance(university_id, int) or not db.session.get(University, university_id):
            return jsonify({"error": "Invalid university_id"}), 400

    program_id = data.get("program_id")
    if program_id is not None:
        if not isinstance(program_id, int) or not db.session.get(Program, program_id):
            return jsonify({"error": "Invalid program_id"}), 400

    unit_id = data.get("unit_id")
    if unit_id is not None:
        if not isinstance(unit_id, int) or not db.session.get(Unit, unit_id):
            return jsonify({"error": "Invalid unit_id"}), 400

    year = data.get("year")
    if year is not None:
        if not isinstance(year, int) or year < 1 or year > 4:
            return jsonify({"error": "year must be a number between 1 and 4"}), 400

    group = Group(
        name=name,
        description=description,
        privacy=privacy,
        university_id=university_id,
        program_id=program_id,
        unit_id=unit_id,
        year=year,
        created_by=user_id,
        member_count=1,
    )
    db.session.add(group)
    db.session.flush()  # assign group.id before the membership row references it

    membership = GroupMember(group_id=group.id, user_id=user_id, role="admin")
    db.session.add(membership)
    db.session.commit()

    return jsonify(_serialize_group(group, membership)), 201


@app.route("/groups")
def browse_groups():
    """
    Browse/discover groups. Private groups are excluded entirely - no
    invite/request flow exists yet, so surfacing them would just be a
    dead end. Course-only groups ARE listed (not yet restricted to
    matching students - that's a later refinement, not a security
    boundary, since course_only groups still require an explicit join).
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    query = Group.query.filter(Group.privacy != "private")

    q = (request.args.get("q") or "").strip()
    if q:
        query = query.filter(Group.name.ilike(f"%{q}%"))

    unit_id = request.args.get("unit_id", type=int)
    if unit_id:
        query = query.filter(Group.unit_id == unit_id)

    university_id = request.args.get("university_id", type=int)
    if university_id:
        query = query.filter(Group.university_id == university_id)

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 20

    groups = (
        query.order_by(Group.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    group_ids = [g.id for g in groups]
    memberships = {
        m.group_id: m
        for m in GroupMember.query.filter(
            GroupMember.user_id == user_id, GroupMember.group_id.in_(group_ids)
        ).all()
    } if group_ids else {}

    return jsonify({
        "page": page,
        "groups": [_serialize_group(g, memberships.get(g.id)) for g in groups],
    })


@app.route("/groups/mine")
def my_groups():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    memberships = (
        GroupMember.query.filter_by(user_id=user_id)
        .order_by(GroupMember.joined_at.desc())
        .all()
    )

    result = []
    for m in memberships:
        group = db.session.get(Group, m.group_id)
        if not group:
            continue
        result.append(_serialize_group(group, m))

    return jsonify({"groups": result})


@app.route("/groups/<int:group_id>")
def get_group(group_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()

    if group.privacy == "private" and not membership:
        # Hide existence of private groups from non-members rather than
        # a 403 that would confirm the group exists.
        return jsonify({"error": "Group not found"}), 404

    return jsonify(_serialize_group(group, membership))


@app.route("/groups/<int:group_id>/join", methods=["POST"])
@require_csrf
def join_group(group_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    existing = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
    if existing:
        return jsonify({"message": "Already a member", "role": existing.role}), 200

    if group.privacy == "private":
        # No invite/request flow yet.
        return jsonify({"error": "This group is invite-only"}), 403

    membership = GroupMember(group_id=group_id, user_id=user_id, role="member")
    db.session.add(membership)
    group.member_count = (group.member_count or 0) + 1
    db.session.commit()

    return jsonify({
        "message": "Joined",
        "role": membership.role,
        "member_count": group.member_count,
    }), 201


@app.route("/groups/<int:group_id>/leave", methods=["POST"])
@require_csrf
def leave_group(group_id):
    """
    A sole admin can't leave while other members remain - there's no
    promote-another-admin endpoint yet, so this would strand the group.
    If they're the last member overall, leaving is allowed (the group
    is simply left empty for now - cleanup/deletion is a later item).
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
    if not membership:
        return jsonify({"message": "Not a member"}), 200

    if membership.role == "admin":
        other_admins = GroupMember.query.filter(
            GroupMember.group_id == group_id,
            GroupMember.role == "admin",
            GroupMember.user_id != user_id,
        ).count()
        other_members = GroupMember.query.filter(
            GroupMember.group_id == group_id,
            GroupMember.user_id != user_id,
        ).count()
        if other_admins == 0 and other_members > 0:
            return jsonify({
                "error": "You're the only admin - promote another member to admin before leaving"
            }), 400

    db.session.delete(membership)
    group.member_count = max(0, (group.member_count or 1) - 1)
    db.session.commit()

    return jsonify({"message": "Left group", "member_count": group.member_count})'''


def main():
    with open(APP_PY, "r", encoding="utf-8", newline="") as f:
        content = f.read()

    if MARKER in content:
        print("Already patched (create_group route found) - nothing to do.")
        return

    assert "class Group(db.Model):" in content, (
        "Group model not found - run chunk5_models_patch.py first."
    )

    uses_crlf = "\r\n" in content
    anchor = ANCHOR.replace("\n", "\r\n") if uses_crlf else ANCHOR
    new_routes = NEW_ROUTES.replace("\n", "\r\n") if uses_crlf else NEW_ROUTES

    assert anchor in content, (
        "Anchor block not found in app.py - has admin_resolve_library_report() "
        "or the Content routes comment moved/changed? Patch script needs updating."
    )
    assert content.count(anchor) == 1, "Anchor block is not unique - refusing to guess which one."

    new_content = content.replace(anchor, new_routes, 1)

    assert new_content != content, "Replacement had no effect - aborting."
    assert new_content.count(MARKER) == 1, "Sanity check failed after patch."

    with open(APP_PY, "w", encoding="utf-8", newline="") as f:
        f.write(new_content)

    print("Patched app.py - added POST /groups, GET /groups, GET /groups/mine, "
          "GET /groups/<id>, POST /groups/<id>/join, POST /groups/<id>/leave.")


if __name__ == "__main__":
    main()
