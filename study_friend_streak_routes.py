from datetime import datetime, timedelta
import os
import uuid
from zoneinfo import ZoneInfo
from flask import jsonify, session
from sqlalchemy import text

MIN_SHARED_STUDY_MINUTES = 10
MAX_ACTIVE_SHARED_STREAKS = 5


def consecutive_shared_days(today, qualifying_days):
    """Count consecutive shared study days, allowing today to remain in progress."""
    days = set(qualifying_days)
    start = today if today in days else today - timedelta(days=1)
    if start not in days:
        return 0
    count = 0
    day = start
    while day in days:
        count += 1
        day -= timedelta(days=1)
    return count

def register_study_friend_streak_routes(app, db):
    from app import Conversation, ConversationParticipant, StudyTimeLog, User, require_csrf
    if getattr(app, "_prepza_study_friend_streak_registered", False):
        return

    tz_name = os.environ.get("PREPZA_TIMEZONE", "Africa/Nairobi")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Africa/Nairobi")

    def local_today():
        return datetime.now(tz).date()

    def ensure_schema():
        """Compatibility hook: shared-streak schema is managed by Alembic."""
        return

    def pair(user_id, peer_id):
        return min(int(user_id), int(peer_id)), max(int(user_id), int(peer_id))

    def lock_user(user_id):
        # Serialize invite/accept operations for each account so concurrent
        # requests cannot race past the active/pending streak limit.
        db.session.execute(
            text('SELECT id FROM public."user" WHERE id=:u FOR UPDATE'),
            {"u": user_id},
        ).first()

    def active_count(user_id):
        return int(db.session.execute(text("""
            SELECT COUNT(*) FROM study_friend_streak
            WHERE status='active' AND (user_a_id=:u OR user_b_id=:u)
        """), {"u": user_id}).scalar() or 0)

    def member(conversation_id, user_id):
        return ConversationParticipant.query.filter_by(
            conversation_id=conversation_id, user_id=user_id, left_at=None
        ).first()

    def peer_id(conversation, user_id):
        if not conversation or conversation.is_group:
            return None
        ids = [
            p.user_id for p in ConversationParticipant.query.filter_by(
                conversation_id=conversation.id, left_at=None
            ).all() if p.user_id != user_id
        ]
        return ids[0] if len(ids) == 1 else None

    def studied(user_id, day):
        seconds = db.session.query(
            db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0)
        ).filter(
            StudyTimeLog.user_id == user_id,
            StudyTimeLog.activity_date == day,
        ).scalar() or 0
        return int(seconds) >= MIN_SHARED_STUDY_MINUTES * 60

    def refresh(row):
        today = local_today()
        since = today - timedelta(days=366 * 2)
        rows = db.session.query(
            StudyTimeLog.user_id,
            StudyTimeLog.activity_date,
            db.func.sum(StudyTimeLog.study_time_seconds),
        ).filter(
            StudyTimeLog.user_id.in_([row["user_a_id"], row["user_b_id"]]),
            StudyTimeLog.activity_date >= since,
            StudyTimeLog.activity_date <= today,
        ).group_by(StudyTimeLog.user_id, StudyTimeLog.activity_date).all()
        qualifying_by_user = {row["user_a_id"]: set(), row["user_b_id"]: set()}
        for user_id, activity_date, seconds in rows:
            if int(seconds or 0) >= MIN_SHARED_STUDY_MINUTES * 60:
                qualifying_by_user[int(user_id)].add(activity_date)
        shared_days = qualifying_by_user[row["user_a_id"]] & qualifying_by_user[row["user_b_id"]]
        streak = consecutive_shared_days(today, shared_days)
        last_shared = max(shared_days) if shared_days else None
        if row["status"] == "active":
            db.session.execute(text("""
                UPDATE study_friend_streak
                SET current_streak=:s,
                    longest_streak=GREATEST(longest_streak,:s),
                    last_shared_date=:d,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=:id
            """), {"s": streak, "d": last_shared, "id": row["id"]})
            db.session.commit()
        return streak

    def serialize(row, viewer_id):
        pid = row["user_b_id"] if row["user_a_id"] == viewer_id else row["user_a_id"]
        peer = db.session.get(User, pid)
        current = refresh(row)
        today = local_today()
        you = studied(viewer_id, today)
        friend = studied(pid, today)
        return {
            "id": str(row["id"]),
            "status": row["status"],
            "invited_by": int(row["invited_by"]),
            "peer_id": pid,
            "peer_name": getattr(peer, "display_name", None) or "Study partner",
            "current_streak": current,
            "longest_streak": int(row["longest_streak"] or 0),
            "today": {"you_studied": you, "friend_studied": friend, "both_studied": you and friend},
            "minimum_minutes": MIN_SHARED_STUDY_MINUTES,
        }

    def load_for_conversation(conversation_id, user_id):
        conversation = db.session.get(Conversation, conversation_id)
        pid = peer_id(conversation, user_id)
        if not pid:
            return None, None
        a, b = pair(user_id, pid)
        row = db.session.execute(text("""
            SELECT * FROM study_friend_streak
            WHERE user_a_id=:a AND user_b_id=:b
        """), {"a": a, "b": b}).mappings().first()
        return pid, row

    @app.get("/chats/<int:conversation_id>/study-streak")
    def get_study_streak(conversation_id):
        user_id = session.get("user_id")
        if not user_id or not member(conversation_id, user_id):
            return jsonify({"error": "Conversation not found"}), 404
        ensure_schema()
        pid, row = load_for_conversation(conversation_id, user_id)
        if not pid:
            return jsonify({"supported": False, "streak": None})
        return jsonify({"supported": True, "streak": serialize(row, user_id) if row else None})

    @app.post("/chats/<int:conversation_id>/study-streak")
    @require_csrf
    def invite_study_streak(conversation_id):
        user_id = session.get("user_id")
        if not user_id or not member(conversation_id, user_id):
            return jsonify({"error": "Conversation not found"}), 404
        ensure_schema()
        pid, row = load_for_conversation(conversation_id, user_id)
        if not pid:
            return jsonify({"error": "Shared streaks currently support one-to-one chats"}), 400
        if row:
            return jsonify({"error": "A shared streak already exists for this chat"}), 409
        lock_user(user_id)
        count = db.session.execute(text("""
            SELECT COUNT(*) FROM study_friend_streak
            WHERE status IN ('active','pending') AND (user_a_id=:u OR user_b_id=:u)
        """), {"u": user_id}).scalar() or 0
        if int(count) >= MAX_ACTIVE_SHARED_STREAKS:
            return jsonify({"error": "You already have the maximum number of active shared streaks"}), 409
        a, b = pair(user_id, pid)
        db.session.execute(text("""
            INSERT INTO study_friend_streak(id,user_a_id,user_b_id,invited_by,status)
            VALUES(:id,:a,:b,:u,'pending')
            ON CONFLICT(user_a_id,user_b_id) DO NOTHING
        """), {"id": str(uuid.uuid4()), "a": a, "b": b, "u": user_id})
        db.session.commit()
        return jsonify({"status": "pending", "minimum_minutes": MIN_SHARED_STUDY_MINUTES}), 201

    @app.post("/chats/<int:conversation_id>/study-streak/accept")
    @require_csrf
    def accept_study_streak(conversation_id):
        user_id = session.get("user_id")
        if not user_id or not member(conversation_id, user_id):
            return jsonify({"error": "Conversation not found"}), 404
        ensure_schema()
        pid, row = load_for_conversation(conversation_id, user_id)
        if not row or row["status"] != "pending" or row["invited_by"] == user_id:
            return jsonify({"error": "No pending shared streak invitation"}), 404
        lock_user(user_id)
        if active_count(user_id) >= MAX_ACTIVE_SHARED_STREAKS:
            return jsonify({"error": "You already have the maximum number of active shared streaks"}), 409
        updated = db.session.execute(text("""
            UPDATE study_friend_streak
            SET status='active', updated_at=CURRENT_TIMESTAMP
            WHERE id=:id AND status='pending' AND invited_by != :u
        """), {"id": row["id"], "u": user_id})
        if updated.rowcount != 1:
            db.session.rollback()
            return jsonify({"error": "Invitation is no longer pending"}), 409
        db.session.commit()
        return jsonify({"status": "active", "minimum_minutes": MIN_SHARED_STUDY_MINUTES})

    @app.post("/chats/<int:conversation_id>/study-streak/decline")
    @require_csrf
    def decline_study_streak(conversation_id):
        user_id = session.get("user_id")
        if not user_id or not member(conversation_id, user_id):
            return jsonify({"error": "Conversation not found"}), 404
        ensure_schema()
        _, row = load_for_conversation(conversation_id, user_id)
        if not row or row["status"] != "pending" or row["invited_by"] == user_id:
            return jsonify({"error": "No pending shared streak invitation"}), 404
        db.session.execute(text("""
            DELETE FROM study_friend_streak
            WHERE id=:id AND status='pending'
        """), {"id": row["id"]})
        db.session.commit()
        return jsonify({"status": "declined"})

    app._prepza_study_friend_streak_registered = True
