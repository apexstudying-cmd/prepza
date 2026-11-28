"""Existing Flask routes for a student's notification feed.

The app owns its global application/model lifecycle. Registration receives
those dependencies explicitly so this module does not import the partially
initialized app module or alter endpoint behavior.
"""

import os
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

def register_notification_preference_routes(
    app,
    db,
    PushSubscription,
    require_csrf,
    get_or_create_notification_prefs,
):
    """Register preference and push-subscription routes without owning shared helpers."""
    @app.route("/notification-preferences")
    def get_notification_preferences():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        prefs = get_or_create_notification_prefs(user_id)
        db.session.commit()

        return jsonify({
            "community_enabled": prefs.community_enabled,
            "messages_enabled": prefs.messages_enabled,
        })


    @app.route("/notification-preferences", methods=["PATCH"])
    @require_csrf
    def update_notification_preferences():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        data = request.get_json(silent=True) or {}
        prefs = get_or_create_notification_prefs(user_id)

        if "community_enabled" in data:
            if not isinstance(data["community_enabled"], bool):
                return jsonify({"error": "community_enabled must be a boolean"}), 400
            prefs.community_enabled = data["community_enabled"]

        if "messages_enabled" in data:
            if not isinstance(data["messages_enabled"], bool):
                return jsonify({"error": "messages_enabled must be a boolean"}), 400
            prefs.messages_enabled = data["messages_enabled"]

        db.session.commit()

        return jsonify({
            "community_enabled": prefs.community_enabled,
            "messages_enabled": prefs.messages_enabled,
        })


    @app.route("/push/vapid-public-key")
    def get_vapid_public_key():
        """
        Public, unauthenticated - the frontend needs this before a push
        subscription can be created, same reasoning as /universities being
        public before a session exists.
        """
        public_key = os.environ.get("VAPID_PUBLIC_KEY")
        if not public_key:
            return jsonify({"error": "Push notifications are not configured"}), 503
        return jsonify({"public_key": public_key})


    @app.route("/push/subscribe", methods=["POST"])
    @require_csrf
    def push_subscribe():
        """
        Upserts a push subscription for the logged-in user, keyed on endpoint
        (not user_id) - a device re-subscribing gets a fresh endpoint from the
        browser, so the same physical device never creates duplicate rows, but
        a user can have many rows across devices.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Request body must be valid JSON"}), 400

        endpoint = (data.get("endpoint") or "").strip()
        keys = data.get("keys") or {}
        p256dh_key = (keys.get("p256dh") or "").strip()
        auth_key = (keys.get("auth") or "").strip()

        if not endpoint or not p256dh_key or not auth_key:
            return jsonify({"error": "endpoint and keys.p256dh and keys.auth are required"}), 400

        existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
        if existing:
            existing.user_id = user_id
            existing.p256dh_key = p256dh_key
            existing.auth_key = auth_key
        else:
            db.session.add(PushSubscription(
                user_id=user_id, endpoint=endpoint,
                p256dh_key=p256dh_key, auth_key=auth_key,
            ))
        db.session.commit()

        return jsonify({"message": "Subscribed"}), 201


    @app.route("/push/subscribe", methods=["DELETE"])
    @require_csrf
    def push_unsubscribe():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        data = request.get_json(silent=True) or {}
        endpoint = (data.get("endpoint") or "").strip()
        if not endpoint:
            return jsonify({"error": "endpoint is required"}), 400

        sub = PushSubscription.query.filter_by(endpoint=endpoint, user_id=user_id).first()
        if sub:
            db.session.delete(sub)
            db.session.commit()

        return jsonify({"message": "Unsubscribed"})
