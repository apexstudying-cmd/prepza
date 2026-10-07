"""
Chunk 5 patch script (8, final): wires actual Notification creation
into the group actions already shipped in patches 4-6. Until now the
only thing that created a Notification row was follow_user.

Adds notifications for:
  - someone comments on your group post/question
  - someone likes your post
  - someone votes on your question
  - you get promoted to group admin

This edits inside four existing functions (not just appending), so
it's four separate anchor/replace pairs applied in sequence. Each is
independently idempotent - if a given edit's marker is already
present, that one is skipped, so partial re-runs are safe.

Requires patches 1-7 already applied.

Usage:
    cd ~/Desktop/prepza
    python chunk5_notification_wiring_patch.py
    git diff app.py
"""

APP_PY = "app.py"


EDITS = [
    {
        "name": "comment notification",
        "marker": 'type="group_comment"',
        "anchor": '''    comment = GroupPostComment(group_post_id=post_id, user_id=user_id, body=body)
    db.session.add(comment)
    db.session.commit()

    return jsonify(_serialize_group_post_comment(comment)), 201''',
        "replacement": '''    comment = GroupPostComment(group_post_id=post_id, user_id=user_id, body=body)
    db.session.add(comment)

    if post.user_id != user_id:
        commenter = db.session.get(User, user_id)
        group = db.session.get(Group, group_id)
        db.session.add(Notification(
            user_id=post.user_id,
            type="group_comment",
            title="New comment" if post.post_type == "post" else "New reply",
            body=f"{_display_name(commenter)} commented on your {post.post_type} in {group.name if group else 'a group'}",
            related_type="group_post",
            related_id=post.id,
        ))

    db.session.commit()

    return jsonify(_serialize_group_post_comment(comment)), 201''',
    },
    {
        "name": "like notification",
        "marker": 'type="group_like"',
        "anchor": '''    existing = GroupPostLike.query.filter_by(group_post_id=post_id, user_id=user_id).first()
    if not existing:
        db.session.add(GroupPostLike(group_post_id=post_id, user_id=user_id))
        db.session.commit()

    return jsonify({
        "message": "Already liked" if existing else "Liked",
        "like_count": GroupPostLike.query.filter_by(group_post_id=post_id).count(),
    }), (200 if existing else 201)''',
        "replacement": '''    existing = GroupPostLike.query.filter_by(group_post_id=post_id, user_id=user_id).first()
    if not existing:
        db.session.add(GroupPostLike(group_post_id=post_id, user_id=user_id))
        if post.user_id != user_id:
            liker = db.session.get(User, user_id)
            db.session.add(Notification(
                user_id=post.user_id,
                type="group_like",
                title="New like",
                body=f"{_display_name(liker)} liked your post",
                related_type="group_post",
                related_id=post.id,
            ))
        db.session.commit()

    return jsonify({
        "message": "Already liked" if existing else "Liked",
        "like_count": GroupPostLike.query.filter_by(group_post_id=post_id).count(),
    }), (200 if existing else 201)''',
    },
    {
        "name": "vote notification",
        "marker": 'type="group_vote"',
        "anchor": '''    existing = GroupQuestionVote.query.filter_by(group_post_id=post_id, user_id=user_id).first()
    if not existing:
        db.session.add(GroupQuestionVote(group_post_id=post_id, user_id=user_id))
        db.session.commit()

    return jsonify({
        "message": "Already voted" if existing else "Voted",
        "vote_count": GroupQuestionVote.query.filter_by(group_post_id=post_id).count(),
    }), (200 if existing else 201)''',
        "replacement": '''    existing = GroupQuestionVote.query.filter_by(group_post_id=post_id, user_id=user_id).first()
    if not existing:
        db.session.add(GroupQuestionVote(group_post_id=post_id, user_id=user_id))
        if post.user_id != user_id:
            voter = db.session.get(User, user_id)
            db.session.add(Notification(
                user_id=post.user_id,
                type="group_vote",
                title="New vote",
                body=f"{_display_name(voter)} voted on your question",
                related_type="group_post",
                related_id=post.id,
            ))
        db.session.commit()

    return jsonify({
        "message": "Already voted" if existing else "Voted",
        "vote_count": GroupQuestionVote.query.filter_by(group_post_id=post_id).count(),
    }), (200 if existing else 201)''',
    },
    {
        "name": "promotion notification",
        "marker": 'type="group_promoted"',
        "anchor": '''    target.role = role
    db.session.commit()

    return jsonify(_serialize_group_member(target))''',
        "replacement": '''    was_admin = target.role == "admin"
    target.role = role

    if role == "admin" and not was_admin:
        group = db.session.get(Group, group_id)
        db.session.add(Notification(
            user_id=target_user_id,
            type="group_promoted",
            title="You're now an admin",
            body=f"You were made an admin of {group.name if group else 'a group'}",
            related_type="group",
            related_id=group_id,
        ))

    db.session.commit()

    return jsonify(_serialize_group_member(target))''',
    },
]


def main():
    with open(APP_PY, "r", encoding="utf-8", newline="") as f:
        content = f.read()

    assert "class Notification(db.Model):" in content, (
        "Notification model not found - run chunk5_models_patch.py first."
    )
    assert "def mark_all_notifications_read():" in content, (
        "Notification routes not found - run chunk5_routes_notifications_patch.py first."
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
            f"Anchor for '{edit['name']}' not found - has that function "
            f"changed since patches 4-6? Patch script needs updating."
        )
        assert content.count(anchor) == 1, (
            f"Anchor for '{edit['name']}' is not unique - refusing to guess which one."
        )

        content = content.replace(anchor, replacement, 1)
        applied.append(edit["name"])

    if not applied:
        print("Already patched (all notification triggers found) - nothing to do.")
        return

    with open(APP_PY, "w", encoding="utf-8", newline="") as f:
        f.write(content)

    print("Applied:", ", ".join(applied) if applied else "none")
    if skipped:
        print("Already present (skipped):", ", ".join(skipped))


if __name__ == "__main__":
    main()
