"""
Chunk 5 patch script (9): fixes two real mismatches between
GroupCreateScreen (frontend) and POST /groups (backend), found during
a frontend/backend review:

  1. Frontend offers Year 1-5 and "Mixed"; backend only accepted 1-4
     and had no way to represent "Mixed". Now accepts 1-5, and
     omitting/nulling year represents "Mixed".
  2. Frontend lets the creator pre-select initial members
     ("Create Group with 3 members"); backend only ever added the
     creator. Now accepts an optional member_user_ids list.

Two NOT fixed here, on purpose - not backend bugs:
  - Privacy casing ('Public' vs 'public') is a frontend-side .toLowerCase()
    /hyphen-to-underscore conversion, nothing to patch server-side.
  - Notification tap-targets: frontend wants a Screen name, backend
    gives related_type/related_id - intentional, needs a small mapping
    table on the frontend, not a schema change.

Two deliberately left for a product decision, not built blind:
  - No `username` field exists on User (only email/display_name) -
    the Follow screens' mock data assumes one. Needs a decision on
    whether to add a real username field before wiring it up.
  - Several notification types in the mock (chat, opportunities,
    achievements, AI-ready, announcements) have no backing feature
    yet - can't create real notifications for events that don't exist.

Requires patches 1-8 already applied.

Usage:
    cd ~/Desktop/prepza
    python chunk5_group_create_fixes_patch.py
    git diff app.py
"""

APP_PY = "app.py"


EDITS = [
    {
        "name": "year range + member_user_ids validation",
        "marker": "member_user_ids must be a list of at most 50 user ids",
        "anchor": '''    year = data.get("year")
    if year is not None:
        if not isinstance(year, int) or year < 1 or year > 4:
            return jsonify({"error": "year must be a number between 1 and 4"}), 400

    group = Group(''',
        "replacement": '''    year = data.get("year")
    if year is not None:
        if not isinstance(year, int) or isinstance(year, bool) or year < 1 or year > 5:
            return jsonify({"error": "year must be a number between 1 and 5, or omitted for 'Mixed'"}), 400

    member_user_ids = data.get("member_user_ids")
    if member_user_ids is not None:
        if not isinstance(member_user_ids, list) or len(member_user_ids) > 50:
            return jsonify({"error": "member_user_ids must be a list of at most 50 user ids"}), 400
        if not all(isinstance(uid, int) and not isinstance(uid, bool) for uid in member_user_ids):
            return jsonify({"error": "member_user_ids must all be integers"}), 400
        member_user_ids = sorted({uid for uid in member_user_ids if uid != user_id})
    else:
        member_user_ids = []

    group = Group(''',
    },
    {
        "name": "add initial members on create",
        "marker": "added_members = 0",
        "anchor": '''    membership = GroupMember(group_id=group.id, user_id=user_id, role="admin")
    db.session.add(membership)
    db.session.commit()

    return jsonify(_serialize_group(group, membership)), 201''',
        "replacement": '''    membership = GroupMember(group_id=group.id, user_id=user_id, role="admin")
    db.session.add(membership)

    added_members = 0
    for member_id in member_user_ids:
        # Silently skip unknown ids rather than failing the whole create -
        # a stale/typo'd id in the initial member list shouldn't block
        # group creation.
        if db.session.get(User, member_id):
            db.session.add(GroupMember(group_id=group.id, user_id=member_id, role="member"))
            added_members += 1
    group.member_count = 1 + added_members

    db.session.commit()

    return jsonify(_serialize_group(group, membership)), 201''',
    },
]


def main():
    with open(APP_PY, "r", encoding="utf-8", newline="") as f:
        content = f.read()

    assert "def create_group():" in content, (
        "create_group route not found - run chunk5_routes_groups_patch.py first."
    )
    assert "class Group(db.Model):" in content, (
        "Group model not found - run chunk5_models_patch.py first."
    )

    uses_crlf = "\r\n" in content
    applied, skipped = [], []

    for edit in EDITS:
        if edit["marker"] in content:
            skipped.append(edit["name"])
            continue

        anchor = edit["anchor"].replace("\n", "\r\n") if uses_crlf else edit["anchor"]
        replacement = edit["replacement"].replace("\n", "\r\n") if uses_crlf else edit["replacement"]

        assert anchor in content, (
            f"Anchor for '{edit['name']}' not found - has create_group() "
            f"changed since patch 3? Patch script needs updating."
        )
        assert content.count(anchor) == 1, (
            f"Anchor for '{edit['name']}' is not unique - refusing to guess which one."
        )

        content = content.replace(anchor, replacement, 1)
        applied.append(edit["name"])

    if not applied:
        print("Already patched (both fixes found) - nothing to do.")
        return

    with open(APP_PY, "w", encoding="utf-8", newline="") as f:
        f.write(content)

    print("Applied:", ", ".join(applied))
    if skipped:
        print("Already present (skipped):", ", ".join(skipped))


if __name__ == "__main__":
    main()
