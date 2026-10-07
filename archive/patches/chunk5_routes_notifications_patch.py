"""
Chunk 5 patch script (7): adds Notification routes - list, unread
count (for a badge), mark-read (single + all), delete. Requires
patches 1-6 already applied (needs Follow/Notification models and
follow_summary route).

Safe to re-run: exits without changes if already applied.

Usage:
    cd ~/Desktop/prepza
    python chunk5_routes_notifications_patch.py
    git diff app.py
"""

APP_PY = "app.py"

ANCHOR = '''    return jsonify({
        "user_id": target_user_id,
        "followers_count": Follow.query.filter_by(followed_id=target_user_id).count(),
        "following_count": Follow.query.filter_by(follower_id=target_user_id).count(),
        "is_following": Follow.query.filter_by(
            follower_id=user_id, followed_id=target_user_id
        ).first() is not None,
        "is_followed_by": Follow.query.filter_by(
            follower_id=target_user_id, followed_id=user_id
        ).first() is not None,
    })


# ---------- Content routes (student-facing) ----------

@app.route("/units")'''

MARKER = "def list_notifications():"

NEW_CONTENT = '''    return jsonify({
        "user_id": target_user_id,
        "followers_count": Follow.query.filter_by(followed_id=target_user_id).count(),
        "following_count": Follow.query.filter_by(follower_id=target_user_id).count(),
        "is_following": Follow.query.filter_by(
            follower_id=user_id, followed_id=target_user_id
        ).first() is not None,
        "is_followed_by": Follow.query.filter_by(
            follower_id=target_user_id, followed_id=user_id
        ).first() is not None,
    })


# ---------- Notifications ----------

def _serialize_notification(notification):
    return {
        "id": notification.id,
        "type": notification.type,
        "title": notification.title,
        "body": notification.body,
        "related_type": notification.related_type,
        "related_id": notification.related_id,
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
    }


@app.route("/notifications")
def list_notifications():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 20

    notifications = (
        Notification.query.filter_by(user_id=user_id)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return jsonify({
        "page": page,
        "notifications": [_serialize_notification(n) for n in notifications],
    })


@app.route("/notifications/unread-count")
def notifications_unread_count():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    return jsonify({"unread_count": count})


@app.route("/notifications/<int:notification_id>/read", methods=["POST"])
@require_csrf
def mark_notification_read(notification_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    notification = db.session.get(Notification, notification_id)
    if not notification or notification.user_id != user_id:
        return jsonify({"error": "Notification not found"}), 404

    if not notification.is_read:
        notification.is_read = True
        db.session.commit()

    return jsonify(_serialize_notification(notification))


@app.route("/notifications/read-all", methods=["POST"])
@require_csrf
def mark_all_notifications_read():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    updated_count = (
        Notification.query.filter_by(user_id=user_id, is_read=False)
        .update({"is_read": True})
    )
    db.session.commit()

    return jsonify({"message": "Marked all as read", "updated_count": updated_count})


@app.route("/notifications/<int:notification_id>", methods=["DELETE"])
@require_csrf
def delete_notification(notification_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    notification = db.session.get(Notification, notification_id)
    if not notification or notification.user_id != user_id:
        return jsonify({"error": "Notification not found"}), 404

    db.session.delete(notification)
    db.session.commit()

    return jsonify({"message": "Notification deleted"})


# ---------- Content routes (student-facing) ----------

@app.route("/units")'''


def main():
    with open(APP_PY, "r", encoding="utf-8", newline="") as f:
        content = f.read()

    if MARKER in content:
        print("Already patched (list_notifications route found) - nothing to do.")
        return

    assert "class Notification(db.Model):" in content, (
        "Notification model not found - run chunk5_models_patch.py first."
    )
    assert "def follow_summary(target_user_id):" in content, (
        "Follow routes not found - run chunk5_routes_follows_patch.py first."
    )

    uses_crlf = "\r\n" in content
    anchor = ANCHOR.replace("\n", "\r\n") if uses_crlf else ANCHOR
    new_content_block = NEW_CONTENT.replace("\n", "\r\n") if uses_crlf else NEW_CONTENT

    assert anchor in content, (
        "Anchor block not found in app.py - has follow_summary() or the "
        "/units route moved/changed? Patch script needs updating."
    )
    assert content.count(anchor) == 1, "Anchor block is not unique - refusing to guess which one."

    new_content = content.replace(anchor, new_content_block, 1)

    assert new_content != content, "Replacement had no effect - aborting."
    assert new_content.count(MARKER) == 1, "Sanity check failed after patch."

    with open(APP_PY, "w", encoding="utf-8", newline="") as f:
        f.write(new_content)

    print("Patched app.py - added notification list/unread-count/"
          "mark-read/mark-all-read/delete routes.")


if __name__ == "__main__":
    main()
