from datetime import datetime, timedelta
import os
from zoneinfo import ZoneInfo
from flask import jsonify, session
from sqlalchemy import text

MIN_SHARED_STUDY_MINUTES = 10
MAX_ACTIVE_SHARED_STREAKS = 5

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
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS study_friend_streak (
                id BIGSERIAL PRIMARY KEY,
                user_a_id INTEGER NOT NULL,
                user_b_id INTEGER NOT NULL,
                invited_by INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                current_streak INTEGER NOT NULL DEFAULT 0,
                longest_streak INTEGER NOT NULL DEFAULT 0,
                last_shared_date DATE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_a_id, user_b_id)
            )
        """))
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS study_friend_streak_activity (
                id VARCHAR(36) PRIMARY KEY,
                streak_id BIGINT NOT NULL,
                user_a_id INTEGER NOT NULL,
                user_b_id INTEGER NOT NULL,
                activity_date DATE NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(streak_id, activity_date)
            )
        """))
        db.session.commit()

    def pair(user_id, peer_id):
        return min(int(user_id), int(peer_id)), max(int(user_id), int(peer_id))

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
        streak = 0
        last_shared = None
        for offset in range(366 * 2):
            day = today - timedelta(days=offset)
            qualifies = studied(row["user_a_id"], day) and studied(row["user_b_id"], day)
            if qualifies:
                streak += 1
                if last_shared is None:
                    last_shared = day
            elif streak:
                break
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
            "id": int(row["id"]),
            "status": row["status"],
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
        count = db.session.execute(text("""
            SELECT COUNT(*) FROM study_friend_streak
            WHERE status='active' AND (user_a_id=:u OR user_b_id=:u)
        """), {"u": user_id}).scalar() or 0
        if int(count) >= MAX_ACTIVE_SHARED_STREAKS:
            return jsonify({"error": "You already have the maximum number of active shared streaks"}), 409
        a, b = pair(user_id, pid)
        db.session.execute(text("""
            INSERT INTO study_friend_streak(user_a_id,user_b_id,invited_by,status)
            VALUES(:a,:b,:u,'pending')
        """), {"a": a, "b": b, "u": user_id})
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
        db.session.execute(text("""
            UPDATE study_friend_streak
            SET status='active', updated_at=CURRENT_TIMESTAMP
            WHERE id=:id
        """), {"id": row["id"]})
        db.session.commit()
        return jsonify({"status": "active", "minimum_minutes": MIN_SHARED_STUDY_MINUTES})

    app._prepza_study_friend_streak_registered = True
