"""Existing Flask routes for a student's notification feed.

The app owns its global application/model lifecycle. Registration receives
those dependencies explicitly so this module does not import the partially
initialized app module or alter endpoint behavior.
"""

from datetime import datetime, timedelta

from flask import jsonify, request, session
from sqlalchemy import and_


def register_notification_routes(app, db, Notification, require_csrf):
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

        # Announcements less than 24h old are pinned to the top of the feed,
        # newest-first among themselves, ahead of everything else - after 24h
        # an announcement just falls back into normal chronological order.
        # A plain boolean SQL expression (not case()) keeps this portable
        # across SQLAlchemy versions, same reasoning as the case()-avoidance
        # elsewhere in this file.
        pin_cutoff = datetime.utcnow() - timedelta(hours=24)
        is_pinned_announcement = and_(
            Notification.type == "announcement",
            Notification.created_at >= pin_cutoff,
        )

        notifications = (
            Notification.query.filter_by(user_id=user_id)
            .order_by(is_pinned_announcement.desc(), Notification.created_at.desc())
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
