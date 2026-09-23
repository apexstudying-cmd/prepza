from datetime import datetime, timedelta
import os
import uuid
from zoneinfo import ZoneInfo

from flask import jsonify, session
from sqlalchemy import text

MIN_SHARED_STUDY_MINUTES = 10
MAX_ACTIVE_SHARED_STREAKS = 5


def register_study_friend_streak_routes(app, db):
    from app import Conversation, ConversationParticipant, StudyTimeLog, User, require_csrf

    if getattr(app, "_prepza_study_friend_streak_registered", False):
        return

    def ensure_schema():
        # Idempotent bootstrap for the repo's no-Alembic deployment model.
        # String UUID ids work on both PostgreSQL and SQLite. Commit the
        # CREATE TABLE work before any compatibility ALTER so an already-
        # migrated database cannot roll the new tables back when the column
        # already exists.
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS study_friend_streak_activity (
                id VARCHAR(36) PRIMARY KEY,
                streak_id VARCHAR(36) NOT NULL,
                user_id INTEGER NOT NULL,
                friend_user_id INTEGER NOT NULL,
                activity_date DATE NOT NULL,
                streak_day INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(streak_id, user_id, activity_date)
            )
        """))
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS study_friend_streak (
                id VARCHAR(36) PRIMARY KEY,
                user_a_id INTEGER NOT NULL,
                user_b_id INTEGER NOT NULL,
                invited_by INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                current_streak INTEGER NOT NULL DEFAULT 0,
                longest_streak INTEGER NOT NULL DEFAULT 0,
                last_shared_date DATE,
                weekend_pause BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_a_id, user_b_id)
            )
        """))
        db.session.commit()

        # Existing installations need the new setting without a destructive migration.
        dialect = db.engine.dialect.name
        if dialect == "sqlite":
            columns = {
                row[1] for row in db.session.execute(text("PRAGMA table_info(study_friend_streak)")).all()
            }
        else:
            columns = {
                row[0] for row in db.session.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name='study_friend_streak'
                """)).all()
            }
        if "weekend_pause" not in columns:
            db.session.execute(text(
                "ALTER TABLE study_friend_streak ADD COLUMN weekend_pause BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            db.session.commit()

    timezone_name = os.environ.get("PREPZA_TIMEZONE", "Africa/Nairobi")
    try:
        APP_TIMEZONE = ZoneInfo(timezone_name)
    except Exception:
        APP_TIMEZONE = ZoneInfo("UTC")

    def local_today():
        return datetime.now(APP_TIMEZONE).date()

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
            p.user_id
            for p in ConversationParticipant.query.filter_by(
                conversation_id=conversation.id, left_at=None
            ).all()
            if p.user_id != user_id
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

    def is_counted_day(day, weekend_pause):
        return not (weekend_pause and day.weekday() >= 5)

    def refresh(row):
        today = local_today()
        pause = bool(row["weekend_pause"])
        streak = 0
        last_shared = None
        started = False

        for offset in range(366 * 2):
            day = today - timedelta(days=offset)
            if not is_counted_day(day, pause):
                continue
            qualifies = studied(row["user_a_id"], day) and studied(row["user_b_id"], day)
            if qualifies:
                started = True
                streak += 1
                if last_shared is None:
                    last_shared = day
            elif started:
                break

        if row["status"] == "active":
            # Persist the shared day as a study-activity event. The underlying
            # study minutes remain each student's own StudyTimeLog; this record
            # captures the social streak milestone without double-counting time.
            if streak and last_shared:
                db.session.execute(text("""
                    INSERT INTO study_friend_streak_activity
                    (id,streak_id,user_id,friend_user_id,activity_date,streak_day)
                    VALUES(:id,:sid,:uid,:fid,:day,:streak_day)
                    ON CONFLICT (streak_id,user_id,activity_date) DO NOTHING
                """), {
                    "id": str(uuid.uuid4()), "sid": row["id"],
                    "uid": row["user_a_id"], "fid": row["user_b_id"],
                    "day": last_shared, "streak_day": streak,
                })
                db.session.execute(text("""
                    INSERT INTO study_friend_streak_activity
                    (id,streak_id,user_id,friend_user_id,activity_date,streak_day)
                    VALUES(:id,:sid,:uid,:fid,:day,:streak_day)
                    ON CONFLICT (streak_id,user_id,activity_date) DO NOTHING
                """), {
                    "id": str(uuid.uuid4()), "sid": row["id"],
                    "uid": row["user_b_id"], "fid": row["user_a_id"],
                    "day": last_shared, "streak_day": streak,
                })
            db.session.execute(text("""
                UPDATE study_friend_streak
                SET current_streak=:s,
                    longest_streak=CASE WHEN longest_streak < :s THEN :s ELSE longest_streak END,
                    last_shared_date=:d,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=:id
            """), {"s": streak, "d": last_shared, "id": row["id"]})
            db.session.commit()
            row = db.session.execute(
                text("SELECT * FROM study_friend_streak WHERE id=:id"),
                {"id": row["id"]},
            ).mappings().first()
        return streak, row

    def serialize(row, viewer_id, conversation_id=None):
        pid = row["user_b_id"] if row["user_a_id"] == viewer_id else row["user_a_id"]
        peer = db.session.get(User, pid)
        today = local_today()
        you, friend = studied(viewer_id, today), studied(pid, today)
        current, refreshed = refresh(row)
        return {
            "id": refreshed["id"],
            "conversation_id": conversation_id,
            "status": refreshed["status"],
            "can_accept": refreshed["status"] == "pending" and int(refreshed["invited_by"]) != int(viewer_id),
            "peer_id": pid,
            "peer_name": getattr(peer, "display_name", None) or "Study partner",
            "current_streak": current,
            "longest_streak": int(refreshed["longest_streak"] or 0),
            "weekend_pause": bool(refreshed["weekend_pause"]),
            "today": {
                "you_studied": you,
                "friend_studied": friend,
                "both_studied": you and friend,
            },
            "minimum_minutes": MIN_SHARED_STUDY_MINUTES,
        }

    @app.get("/chats/<int:conversation_id>/study-streak")
    def get_study_streak(conversation_id):
        user_id = session.get("user_id")
        if not user_id or not member(conversation_id, user_id):
            return jsonify({"error": "Conversation not found"}), 404
        conversation = db.session.get(Conversation, conversation_id)
        pid = peer_id(conversation, user_id)
        if not pid:
            return jsonify({"supported": False, "streak": None})
        ensure_schema()
        a, b = pair(user_id, pid)
        row = db.session.execute(
            text("SELECT * FROM study_friend_streak WHERE user_a_id=:a AND user_b_id=:b"),
            {"a": a, "b": b},
        ).mappings().first()
        return jsonify({
            "supported": True,
            "streak": serialize(row, user_id, conversation_id) if row else None,
        })

    @app.get("/study-friend-streaks")
    def list_study_friend_streaks():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        ensure_schema()
        rows = db.session.execute(text("""
            SELECT * FROM study_friend_streak
            WHERE user_a_id=:u OR user_b_id=:u
            ORDER BY updated_at DESC
            LIMIT 5
        """), {"u": user_id}).mappings().all()

        result = []
        for row in rows:
            pid = row["user_b_id"] if row["user_a_id"] == user_id else row["user_a_id"]
            conversation = None
            conversations = (
                ConversationParticipant.query.filter_by(user_id=user_id, left_at=None)
                .all()
            )
            for participant in conversations:
                candidate = db.session.get(Conversation, participant.conversation_id)
                if not candidate or candidate.is_group:
                    continue
                peer_ids = [
                    p.user_id for p in ConversationParticipant.query.filter_by(
                        conversation_id=candidate.id, left_at=None
                    ).all()
                ]
                if len(peer_ids) == 2 and pid in peer_ids:
                    conversation = candidate
                    break
            result.append(serialize(row, user_id, conversation.id if conversation else None))
        return jsonify({"streaks": result})

    @app.post("/chats/<int:conversation_id>/study-streak")
    @require_csrf
    def invite_study_streak(conversation_id):
        user_id = session.get("user_id")
        if not user_id or not member(conversation_id, user_id):
            return jsonify({"error": "Conversation not found"}), 404
        conversation = db.session.get(Conversation, conversation_id)
        pid = peer_id(conversation, user_id)
        if not pid:
            return jsonify({"error": "Shared streaks currently support one-to-one chats"}), 400
        ensure_schema()
        a, b = pair(user_id, pid)
        if db.session.execute(
            text("SELECT 1 FROM study_friend_streak WHERE user_a_id=:a AND user_b_id=:b"),
            {"a": a, "b": b},
        ).first():
            return jsonify({"error": "A shared streak already exists for this chat"}), 409

        count = db.session.execute(text("""
            SELECT COUNT(*) FROM study_friend_streak
            WHERE status='active' AND (user_a_id=:u OR user_b_id=:u)
        """), {"u": user_id}).scalar() or 0
        if int(count) >= MAX_ACTIVE_SHARED_STREAKS:
            return jsonify({"error": "You already have 5 active shared streaks"}), 409

        # Start is an invitation; neither student's study time is retroactively credited.
        weekend_pause = bool((__import__("flask").request.get_json(silent=True) or {}).get("weekend_pause", False))
        db.session.execute(text("""
            INSERT INTO study_friend_streak
            (id,user_a_id,user_b_id,invited_by,status,weekend_pause)
            VALUES(:id,:a,:b,:u,'pending',:pause)
        """), {
            "id": str(uuid.uuid4()), "a": a, "b": b, "u": user_id,
            "pause": weekend_pause,
        })
        db.session.commit()
        return jsonify({"status": "pending", "weekend_pause": weekend_pause}), 201

    @app.post("/chats/<int:conversation_id>/study-streak/accept")
    @require_csrf
    def accept_study_streak(conversation_id):
        user_id = session.get("user_id")
        if not user_id or not member(conversation_id, user_id):
            return jsonify({"error": "Conversation not found"}), 404
        conversation = db.session.get(Conversation, conversation_id)
        pid = peer_id(conversation, user_id)
        if not pid:
            return jsonify({"error": "Shared streaks currently support one-to-one chats"}), 400
        ensure_schema()
        a, b = pair(user_id, pid)
        row = db.session.execute(text(
            "SELECT * FROM study_friend_streak WHERE user_a_id=:a AND user_b_id=:b"
        ), {"a": a, "b": b}).mappings().first()
        if not row or row["status"] != "pending" or row["invited_by"] == user_id:
            return jsonify({"error": "No pending shared streak invitation"}), 404
        db.session.execute(text("""
            UPDATE study_friend_streak
            SET status='active', updated_at=CURRENT_TIMESTAMP
            WHERE id=:id
        """), {"id": row["id"]})
        db.session.commit()
        return jsonify({"status": "active", "weekend_pause": bool(row["weekend_pause"])}), 200

    @app.post("/chats/<int:conversation_id>/study-streak/settings")
    @require_csrf
    def update_study_streak_settings(conversation_id):
        user_id = session.get("user_id")
        if not user_id or not member(conversation_id, user_id):
            return jsonify({"error": "Conversation not found"}), 404
        conversation = db.session.get(Conversation, conversation_id)
        pid = peer_id(conversation, user_id)
        if not pid:
            return jsonify({"error": "Shared streaks currently support one-to-one chats"}), 400
        payload = __import__("flask").request.get_json(silent=True) or {}
        if not isinstance(payload.get("weekend_pause"), bool):
            return jsonify({"error": "weekend_pause must be true or false"}), 400
        ensure_schema()
        a, b = pair(user_id, pid)
        row = db.session.execute(text(
            "SELECT * FROM study_friend_streak WHERE user_a_id=:a AND user_b_id=:b"
        ), {"a": a, "b": b}).mappings().first()
        if not row or row["status"] != "active":
            return jsonify({"error": "No active shared streak"}), 404
        db.session.execute(text("""
            UPDATE study_friend_streak
            SET weekend_pause=:pause, updated_at=CURRENT_TIMESTAMP
            WHERE id=:id
        """), {"pause": payload["weekend_pause"], "id": row["id"]})
        db.session.commit()
        refreshed = db.session.execute(
            text("SELECT * FROM study_friend_streak WHERE id=:id"),
            {"id": row["id"]},
        ).mappings().first()
        return jsonify({"streak": serialize(refreshed, user_id, conversation_id)}), 200

    app._prepza_study_friend_streak_registered = True
