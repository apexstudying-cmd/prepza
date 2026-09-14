"""Local-first offline study activity reconciliation routes.

Loaded by the production realtime_server entrypoint so offline study time can
be reconciled without changing the large legacy app.py file. The client sends
only unsynced deltas; the server caps each calendar day's accepted total at
Prepza's existing 8-hour anti-gaming ceiling.
"""
from datetime import datetime, timedelta

from flask import jsonify, request, session


def register_offline_activity_routes(app, db):
    from app import StudyTimeLog, StudyActivityLog, StudyStreak, require_csrf

    @app.route('/study-time/offline-sync', methods=['POST'])
    @require_csrf
    def sync_offline_study_time():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Not logged in'}), 401
        data = request.get_json(silent=True) or {}
        entries = data.get('entries')
        if not isinstance(entries, list) or len(entries) > 31:
            return jsonify({'error': 'entries must be a list of at most 31 daily deltas'}), 400

        today = datetime.utcnow().date()
        accepted = {}
        max_day_seconds = 8 * 60 * 60

        for item in entries:
            if not isinstance(item, dict):
                continue
            raw_date = item.get('date')
            seconds = item.get('seconds')
            try:
                activity_date = datetime.strptime(raw_date, '%Y-%m-%d').date()
                seconds = int(seconds)
            except (TypeError, ValueError):
                continue
            if activity_date > today or activity_date < today - timedelta(days=366):
                continue
            if seconds <= 0:
                continue

            existing_total = db.session.query(db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0)).filter(
                StudyTimeLog.user_id == user_id,
                StudyTimeLog.activity_date == activity_date,
            ).scalar() or 0
            room = max(0, max_day_seconds - int(existing_total))
            amount = min(seconds, room)
            if amount <= 0:
                accepted[raw_date] = 0
                continue

            row = StudyTimeLog.query.filter_by(
                user_id=user_id, activity_date=activity_date, feature='reading'
            ).first()
            if not row:
                row = StudyTimeLog(user_id=user_id, activity_date=activity_date, feature='reading', study_time_seconds=0)
                db.session.add(row)
                db.session.flush()
            row.study_time_seconds += amount
            # A synced offline day has no meaningful server heartbeat baseline;
            # leave this null so the next live heartbeat starts cleanly.
            row.last_heartbeat_at = None

            activity = StudyActivityLog.query.filter_by(
                user_id=user_id, document_content_id=None, activity_date=activity_date
            ).first()
            if not activity:
                db.session.add(StudyActivityLog(user_id=user_id, document_content_id=None, activity_date=activity_date))
            accepted[raw_date] = amount

        # Rebuild the user's streak from actual activity dates. This makes
        # offline study on yesterday count when the device reconnects today.
        activity_dates = {
            row.activity_date for row in StudyActivityLog.query.filter_by(user_id=user_id).all()
        }
        streak = StudyStreak.query.filter_by(user_id=user_id).first()
        if not streak:
            streak = StudyStreak(user_id=user_id)
            db.session.add(streak)
            db.session.flush()
        current = 0
        cursor = today
        while cursor in activity_dates:
            current += 1
            cursor -= timedelta(days=1)
        longest = streak.longest_streak or 0
        cursor = today
        run = 0
        while cursor in activity_dates:
            run += 1
            longest = max(longest, run)
            cursor -= timedelta(days=1)
        streak.current_streak = current
        streak.longest_streak = longest
        streak.last_study_date = max(activity_dates) if activity_dates else None

        db.session.commit()
        return jsonify({'accepted_seconds_by_date': accepted, 'current_streak': streak.current_streak, 'longest_streak': streak.longest_streak})
