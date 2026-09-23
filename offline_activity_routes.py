"""Local-first offline study activity reconciliation routes.

The client sends an absolute local daily study total rather than a one-shot
increment. The server reconciles by moving its authoritative total forward to
that target (capped at Prepza's existing 8-hour daily ceiling). Replaying the
same request after an ambiguous network failure therefore cannot double-count
the same offline study time.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

NAIROBI = ZoneInfo('Africa/Nairobi')
def _today(): return datetime.now(NAIROBI).date()

from flask import jsonify, request, session


def register_offline_activity_routes(app, db):
    from app import StudyTimeLog, StudyActivityLog, StudyStreak, require_csrf

    @app.route('/study-time/offline-baselines')
    def offline_study_time_baselines():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Not logged in'}), 401

        raw_dates = (request.args.get('dates') or '').split(',')
        dates = []
        for raw_date in raw_dates[:31]:
            value = (raw_date or '').strip()
            try:
                activity_date = datetime.strptime(value, '%Y-%m-%d').date()
            except (TypeError, ValueError):
                continue
            if activity_date > _today() or activity_date < datetime.utcnow().date() - timedelta(days=366):
                continue
            dates.append(activity_date)
        dates = sorted(set(dates))
        if not dates:
            return jsonify({'server_total_seconds_by_date': {}})

        rows = db.session.query(
            StudyTimeLog.activity_date,
            db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0),
        ).filter(
            StudyTimeLog.user_id == user_id,
            StudyTimeLog.activity_date.in_(dates),
        ).group_by(StudyTimeLog.activity_date).all()

        totals = {date.isoformat(): min(8 * 60 * 60, max(0, int(seconds or 0))) for date, seconds in rows}
        return jsonify({'server_total_seconds_by_date': totals})

    @app.route('/study-time/offline-sync', methods=['POST'])
    @require_csrf
    def sync_offline_study_time():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Not logged in'}), 401

        data = request.get_json(silent=True) or {}
        entries = data.get('entries')
        if not isinstance(entries, list) or len(entries) > 31:
            return jsonify({'error': 'entries must be a list of at most 31 daily totals'}), 400

        today = datetime.utcnow().date()
        max_day_seconds = 8 * 60 * 60
        accepted = {}
        server_totals = {}

        for item in entries:
            if not isinstance(item, dict):
                continue
            raw_date = item.get('date')
            target = item.get('total_seconds', item.get('seconds'))
            try:
                activity_date = datetime.strptime(raw_date, '%Y-%m-%d').date()
                target = int(target)
            except (TypeError, ValueError):
                continue
            if activity_date > today or activity_date < today - timedelta(days=366):
                continue
            target = max(0, min(max_day_seconds, target))

            existing_total = db.session.query(
                db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0)
            ).filter(
                StudyTimeLog.user_id == user_id,
                StudyTimeLog.activity_date == activity_date,
            ).scalar() or 0
            existing_total = min(max_day_seconds, max(0, int(existing_total)))
            new_total = max(existing_total, target)
            delta = new_total - existing_total

            if delta > 0:
                row = StudyTimeLog.query.filter_by(
                    user_id=user_id, activity_date=activity_date, feature='reading'
                ).first()
                if not row:
                    row = StudyTimeLog(
                        user_id=user_id,
                        activity_date=activity_date,
                        feature='reading',
                        study_time_seconds=0,
                    )
                    db.session.add(row)
                    db.session.flush()
                row.study_time_seconds += delta
                row.last_heartbeat_at = None

                if new_total >= 10 * 60:
                    activity = StudyActivityLog.query.filter_by(
                        user_id=user_id, document_content_id=None, activity_date=activity_date
                    ).first()
                    if not activity:
                        db.session.add(StudyActivityLog(
                            user_id=user_id, document_content_id=None, activity_date=activity_date,
                        ))

            server_totals[raw_date] = new_total
            # This is the amount by which the server advanced during this
            # request. The client uses server_totals for replay-safe marking.
            accepted[raw_date] = delta

        activity_dates = {
            row.activity_date
            for row in StudyActivityLog.query.filter_by(user_id=user_id).all()
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
        return jsonify({
            'accepted_seconds_by_date': accepted,
            'server_total_seconds_by_date': server_totals,
            'current_streak': streak.current_streak,
            'longest_streak': streak.longest_streak,
        })
