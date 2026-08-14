"""
Chunk 5 patch script (5): adds Group Files (share an existing Document
into a group) and Group Members (list + promote/demote + kick) routes.
Requires patches 1-4 already applied.

The promote/demote route is what finally unblocks the sole-admin
leave_group restriction from patch 3 - an admin can promote a member
to admin, then leave.

Safe to re-run: exits without changes if already applied.

Usage:
    cd ~/Desktop/prepza
    python chunk5_routes_group_files_members_patch.py
    git diff app.py
"""

APP_PY = "app.py"

ANCHOR = '''    return jsonify({
        "message": "Unvoted" if existing else "Not voted",
        "vote_count": GroupQuestionVote.query.filter_by(group_post_id=post_id).count(),
    })


# ---------- Content routes (student-facing) ----------

@app.route("/units")'''

MARKER = "def list_group_members(group_id):"

NEW_CONTENT = '''    return jsonify({
        "message": "Unvoted" if existing else "Not voted",
        "vote_count": GroupQuestionVote.query.filter_by(group_post_id=post_id).count(),
    })


# ---------- Group members ----------

def _serialize_group_member(membership):
    user = db.session.get(User, membership.user_id)
    return {
        "user_id": membership.user_id,
        "display_name": _display_name(user) if user else "Deleted user",
        "role": membership.role,
        "joined_at": membership.joined_at.isoformat() if membership.joined_at else None,
    }


@app.route("/groups/<int:group_id>/members")
def list_group_members(group_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    members = GroupMember.query.filter_by(group_id=group_id).all()
    members.sort(key=lambda m: (0 if m.role == "admin" else 1, m.joined_at or datetime.min))

    return jsonify({"members": [_serialize_group_member(m) for m in members]})


@app.route("/groups/<int:group_id>/members/<int:target_user_id>", methods=["PATCH"])
@require_csrf
def update_group_member_role(group_id, target_user_id):
    """
    Promote a member to admin, or demote an admin to member. Admin-only.
    Refuses to demote the last remaining admin - they'd need to promote
    someone else first (this is also how a sole admin unblocks
    themselves from the leave_group restriction).
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    requester = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
    if not requester or requester.role != "admin":
        return jsonify({"error": "Only group admins can change member roles"}), 403

    target = GroupMember.query.filter_by(group_id=group_id, user_id=target_user_id).first()
    if not target:
        return jsonify({"error": "Member not found"}), 404

    data = request.get_json(silent=True) or {}
    role = (data.get("role") or "").strip().lower()
    if role not in ("admin", "member"):
        return jsonify({"error": "role must be 'admin' or 'member'"}), 400

    if role == "member" and target.role == "admin":
        other_admins = GroupMember.query.filter(
            GroupMember.group_id == group_id,
            GroupMember.role == "admin",
            GroupMember.user_id != target_user_id,
        ).count()
        if other_admins == 0:
            return jsonify({"error": "Can't demote the only admin - promote someone else first"}), 400

    target.role = role
    db.session.commit()

    return jsonify(_serialize_group_member(target))


@app.route("/groups/<int:group_id>/members/<int:target_user_id>", methods=["DELETE"])
@require_csrf
def remove_group_member(group_id, target_user_id):
    """
    Admin-only kick. Self-removal is deliberately rejected here - use
    POST /groups/<id>/leave instead, which has its own sole-admin
    protection. An admin target must be demoted first (kicking an
    admin outright would bypass that protection entirely).
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if target_user_id == user_id:
        return jsonify({"error": "Use POST /groups/<id>/leave to remove yourself"}), 400

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    requester = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
    if not requester or requester.role != "admin":
        return jsonify({"error": "Only group admins can remove members"}), 403

    target = GroupMember.query.filter_by(group_id=group_id, user_id=target_user_id).first()
    if not target:
        return jsonify({"error": "Member not found"}), 404

    if target.role == "admin":
        return jsonify({"error": "Demote this admin before removing them"}), 400

    db.session.delete(target)
    group.member_count = max(0, (group.member_count or 1) - 1)
    db.session.commit()

    return jsonify({"message": "Member removed", "member_count": group.member_count})


# ---------- Group files ----------

def _serialize_group_file(group_file):
    document = db.session.get(Document, group_file.document_id)
    content = (
        db.session.get(DocumentContent, document.document_content_id)
        if document and document.document_content_id else None
    )
    sharer = db.session.get(User, group_file.shared_by_user_id)
    view_url = None
    if content and content.status == "ready":
        view_url = get_signed_url(content.storage_path, bucket="documents")
    return {
        "id": group_file.id,
        "group_id": group_file.group_id,
        "document_id": group_file.document_id,
        "title": document.title if document else None,
        "file_type": content.file_type if content else None,
        "file_size_bytes": content.file_size_bytes if content else None,
        "page_count": content.page_count if content else None,
        "view_url": view_url,
        "shared_by": _display_name(sharer) if sharer else "Deleted user",
        "shared_by_user_id": group_file.shared_by_user_id,
        "created_at": group_file.created_at.isoformat() if group_file.created_at else None,
    }


@app.route("/groups/<int:group_id>/files", methods=["POST"])
@require_csrf
def share_group_file(group_id):
    """
    Shares one of the caller's OWN ready Documents into the group's
    Files tab. Does not touch storage - just links the existing
    Document row, same dedup-friendly pattern as the rest of the app.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    if not membership:
        return jsonify({"error": "You must join this group first"}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    document_id = data.get("document_id")
    if not isinstance(document_id, int) or isinstance(document_id, bool):
        return jsonify({"error": "document_id is required"}), 400

    document = db.session.get(Document, document_id)
    if not document or document.user_id != user_id or document.is_removed:
        return jsonify({"error": "Document not found"}), 404

    content = (
        db.session.get(DocumentContent, document.document_content_id)
        if document.document_content_id else None
    )
    effective_status = content.status if (content and document.status != "uploading") else document.status
    if effective_status != "ready":
        return jsonify({"error": f"Document is not ready to share (status: {effective_status})"}), 400

    existing = GroupFile.query.filter_by(group_id=group_id, document_id=document_id).first()
    if existing:
        return jsonify(_serialize_group_file(existing)), 200

    group_file = GroupFile(group_id=group_id, document_id=document_id, shared_by_user_id=user_id)
    db.session.add(group_file)
    db.session.commit()

    return jsonify(_serialize_group_file(group_file)), 201


@app.route("/groups/<int:group_id>/files")
def list_group_files(group_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    files = (
        GroupFile.query.filter_by(group_id=group_id)
        .order_by(GroupFile.created_at.desc())
        .all()
    )

    return jsonify({"files": [_serialize_group_file(f) for f in files]})


@app.route("/groups/<int:group_id>/files/<int:file_id>", methods=["DELETE"])
@require_csrf
def remove_group_file(group_id, file_id):
    """Removable by whoever shared it, or by any group admin."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    group_file = db.session.get(GroupFile, file_id)
    if not group_file or group_file.group_id != group_id:
        return jsonify({"error": "File not found"}), 404

    membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
    is_admin = bool(membership and membership.role == "admin")

    if group_file.shared_by_user_id != user_id and not is_admin:
        return jsonify({"error": "Only the person who shared this file or a group admin can remove it"}), 403

    db.session.delete(group_file)
    db.session.commit()

    return jsonify({"message": "File removed"})


# ---------- Content routes (student-facing) ----------

@app.route("/units")'''


def main():
    with open(APP_PY, "r", encoding="utf-8", newline="") as f:
        content = f.read()

    if MARKER in content:
        print("Already patched (list_group_members route found) - nothing to do.")
        return

    assert "class GroupFile(db.Model):" in content, (
        "GroupFile model not found - run chunk5_models_patch.py first."
    )
    assert "def unvote_group_post(group_id, post_id):" in content, (
        "Group post routes not found - run chunk5_routes_group_posts_patch.py first."
    )

    uses_crlf = "\r\n" in content
    anchor = ANCHOR.replace("\n", "\r\n") if uses_crlf else ANCHOR
    new_content_block = NEW_CONTENT.replace("\n", "\r\n") if uses_crlf else NEW_CONTENT

    assert anchor in content, (
        "Anchor block not found in app.py - has unvote_group_post() or the "
        "/units route moved/changed? Patch script needs updating."
    )
    assert content.count(anchor) == 1, "Anchor block is not unique - refusing to guess which one."

    new_content = content.replace(anchor, new_content_block, 1)

    assert new_content != content, "Replacement had no effect - aborting."
    assert new_content.count(MARKER) == 1, "Sanity check failed after patch."

    with open(APP_PY, "w", encoding="utf-8", newline="") as f:
        f.write(new_content)

    print("Patched app.py - added group members routes (list/promote/demote/"
          "kick) and group files routes (share/list/remove).")


if __name__ == "__main__":
    main()
