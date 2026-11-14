"""Social follow and public-profile routes.

Route bodies are retained verbatim under an injected registration boundary.
Notification helpers are passed as callables because their shared definitions
remain later in app.py and are resolved when a request is handled.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from flask import jsonify, request, session
from sqlalchemy import func


def register_social_follow_routes(
    app: Any,
    db: Any,
    *,
    User: Any,
    Follow: Any,
    FollowRequest: Any,
    Notification: Any,
    University: Any,
    Program: Any,
    Document: Any,
    XpEvent: Any,
    StudyTimeLog: Any,
    _display_name: Any,
    get_signed_url: Any,
    should_notify: Any,
    send_push_notification: Any,
    require_csrf: Any,
) -> None:
    """Register the existing follow, request and public-profile endpoints."""
    def _serialize_follow_user(user, viewer_user_id):
        return {
            "user_id": user.id,
            "display_name": _display_name(user),
            "is_following": Follow.query.filter_by(
                follower_id=viewer_user_id, followed_id=user.id
            ).first() is not None,
        }


    @app.route("/users/<int:target_user_id>/follow", methods=["POST"])
    @require_csrf
    def follow_user(target_user_id):
        """
        Follows a user immediately, UNLESS the target has
        who_can_follow='approval_required' - in that case this creates
        (or reuses/reopens) a pending FollowRequest and notifies the
        target instead of creating a Follow row directly. The frontend
        should treat a 202 response as "requested, not yet following".
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        if target_user_id == user_id:
            return jsonify({"error": "You can't follow yourself"}), 400

        target = db.session.get(User, target_user_id)
        if not target or target.is_suspended:
            return jsonify({"error": "User not found"}), 404

        existing = Follow.query.filter_by(follower_id=user_id, followed_id=target_user_id).first()
        if existing:
            return jsonify({
                "message": "Already following",
                "followers_count": Follow.query.filter_by(followed_id=target_user_id).count(),
            }), 200

        if target.who_can_follow == "approval_required":
            pending = FollowRequest.query.filter_by(requester_id=user_id, target_id=target_user_id).first()
            if pending and pending.status == "pending":
                return jsonify({"message": "Follow request already sent", "status": "pending"}), 200
            if pending:
                pending.status = "pending"
                pending.responded_at = None
            else:
                pending = FollowRequest(requester_id=user_id, target_id=target_user_id, status="pending")
                db.session.add(pending)
            requester = db.session.get(User, user_id)
            if should_notify(target_user_id, "community"):
                db.session.add(Notification(
                    user_id=target_user_id,
                    type="follow_request",
                    title="New follow request",
                    body=f"{_display_name(requester)} wants to follow you",
                    related_type="user",
                    related_id=user_id,
                ))
                send_push_notification(
                    target_user_id,
                    "New follow request",
                    f"{_display_name(requester)} wants to follow you",
                )
            db.session.commit()
            return jsonify({"message": "Follow request sent", "status": "pending"}), 202

        db.session.add(Follow(follower_id=user_id, followed_id=target_user_id))
        follower = db.session.get(User, user_id)
        if should_notify(target_user_id, "community"):
            db.session.add(Notification(
                user_id=target_user_id,
                type="new_follower",
                title="New follower",
                body=f"{_display_name(follower)} started following you",
                related_type="user",
                related_id=user_id,
            ))
            send_push_notification(
                target_user_id,
                "New follower",
                f"{_display_name(follower)} started following you",
            )
        db.session.commit()

        return jsonify({
            "message": "Followed",
            "followers_count": Follow.query.filter_by(followed_id=target_user_id).count(),
        }), 201


    @app.route("/follow-requests")
    def list_follow_requests():
        """Pending follow requests directed AT the logged-in user."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        requests = (
            FollowRequest.query.filter_by(target_id=user_id, status="pending")
            .order_by(FollowRequest.created_at.desc())
            .all()
        )

        result = []
        for r in requests:
            requester = db.session.get(User, r.requester_id)
            result.append({
                "id": r.id,
                "requester_id": r.requester_id,
                "requester_display_name": _display_name(requester) if requester else "Deleted user",
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })

        return jsonify({"requests": result})


    @app.route("/follow-requests/<int:request_id>/accept", methods=["POST"])
    @require_csrf
    def accept_follow_request(request_id):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        req = db.session.get(FollowRequest, request_id)
        if not req or req.target_id != user_id:
            return jsonify({"error": "Follow request not found"}), 404
        if req.status != "pending":
            return jsonify({"error": f"Request is not pending (status: {req.status})"}), 400

        req.status = "accepted"
        req.responded_at = datetime.utcnow()

        existing_follow = Follow.query.filter_by(follower_id=req.requester_id, followed_id=user_id).first()
        if not existing_follow:
            db.session.add(Follow(follower_id=req.requester_id, followed_id=user_id))
            target = db.session.get(User, user_id)
            if should_notify(req.requester_id, "community"):
                db.session.add(Notification(
                    user_id=req.requester_id,
                    type="new_follower",
                    title="Follow request accepted",
                    body=f"{_display_name(target)} accepted your follow request",
                    related_type="user",
                    related_id=user_id,
                ))
                send_push_notification(
                    req.requester_id,
                    "Follow request accepted",
                    f"{_display_name(target)} accepted your follow request",
                )

        db.session.commit()

        return jsonify({
            "message": "Accepted",
            "followers_count": Follow.query.filter_by(followed_id=user_id).count(),
        })


    @app.route("/follow-requests/<int:request_id>/decline", methods=["POST"])
    @require_csrf
    def decline_follow_request(request_id):
        """
        Declines a pending follow request. Deliberately does NOT notify
        the requester - same silent-decline convention private accounts
        elsewhere use, so declining doesn't feel like a public rejection.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        req = db.session.get(FollowRequest, request_id)
        if not req or req.target_id != user_id:
            return jsonify({"error": "Follow request not found"}), 404
        if req.status != "pending":
            return jsonify({"error": f"Request is not pending (status: {req.status})"}), 400

        req.status = "declined"
        req.responded_at = datetime.utcnow()
        db.session.commit()

        return jsonify({"message": "Declined"})


    @app.route("/users/<int:target_user_id>/follow", methods=["DELETE"])
    @require_csrf
    def unfollow_user(target_user_id):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        existing = Follow.query.filter_by(follower_id=user_id, followed_id=target_user_id).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()

        return jsonify({
            "message": "Unfollowed" if existing else "Not following",
            "followers_count": Follow.query.filter_by(followed_id=target_user_id).count(),
        })


    @app.route("/users/<int:target_user_id>/followers")
    def list_followers(target_user_id):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        target = db.session.get(User, target_user_id)
        if not target:
            return jsonify({"error": "User not found"}), 404

        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        per_page = 20

        rows = (
            Follow.query.filter_by(followed_id=target_user_id)
            .order_by(Follow.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        followers = [db.session.get(User, r.follower_id) for r in rows]

        return jsonify({
            "page": page,
            "followers": [_serialize_follow_user(u, user_id) for u in followers if u],
        })


    @app.route("/users/<int:target_user_id>/following")
    def list_following(target_user_id):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        target = db.session.get(User, target_user_id)
        if not target:
            return jsonify({"error": "User not found"}), 404

        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        per_page = 20

        rows = (
            Follow.query.filter_by(follower_id=target_user_id)
            .order_by(Follow.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        following = [db.session.get(User, r.followed_id) for r in rows]

        return jsonify({
            "page": page,
            "following": [_serialize_follow_user(u, user_id) for u in following if u],
        })


    @app.route("/users/<int:target_user_id>/follow-summary")
    def follow_summary(target_user_id):
        """Counts + relationship flags for a profile header."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        target = db.session.get(User, target_user_id)
        if not target:
            return jsonify({"error": "User not found"}), 404

        return jsonify({
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


    @app.route("/users/<int:target_user_id>/public-profile")
    def get_public_profile(target_user_id):
        """
        Lightweight public profile fields for VIEWING another student -
        distinct from /me (your own full profile, includes email) and from
        follow_summary above (just counts/relationship flags). Deliberately
        excludes email and any other contact/sensitive fields - only what a
        student's profile card needs to render for someone who isn't them.
        Suspended users 404 the same way follow_summary treats a missing
        user, so this can't be used to confirm a suspended account exists.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        target = db.session.get(User, target_user_id)
        if not target or target.is_suspended:
            return jsonify({"error": "User not found"}), 404

        if target.profile_visibility == "private" and target.id != user_id:
            return jsonify({
                "user_id": target.id,
                "display_name": _display_name(target),
                "is_private": True,
            })

        university = db.session.get(University, target.university_id) if target.university_id else None
        program = db.session.get(Program, target.program_id) if target.program_id else None

        documents_count = Document.query.filter_by(user_id=target_user_id, is_removed=False).count()
        xp_total = db.session.query(func.coalesce(func.sum(XpEvent.xp_amount), 0)).filter(
            XpEvent.user_id == target_user_id
        ).scalar()

        today = datetime.utcnow().date()
        week_start = today - timedelta(days=today.weekday())
        weekly_study_seconds = db.session.query(
            db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0)
        ).filter(
            StudyTimeLog.user_id == target_user_id,
            StudyTimeLog.activity_date >= week_start,
            StudyTimeLog.activity_date <= today,
        ).scalar()

        return jsonify({
            "user_id": target.id,
            "display_name": _display_name(target),
            "avatar_url": get_signed_url(target.avatar_storage_path, expires_in=3600, bucket="avatars") if target.avatar_storage_path else None,
            "bio": target.bio,
            "year": target.year,
            "university_name": university.name if university else None,
            "program_name": program.name if program else None,
            "documents_count": documents_count,
            "xp_total": int(xp_total),
            "weekly_study_seconds": int(weekly_study_seconds or 0),
            "is_private": False,
        })
