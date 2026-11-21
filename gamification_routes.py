"""Study activity, XP, streak and achievement HTTP routes.

Route bodies are preserved from app.py and registered in their original order.
Dependencies are injected so this feature module never imports the application.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from flask import jsonify, request, session
from flask_limiter.util import get_remote_address
from sqlalchemy import func


def register_gamification_routes(
    app: Any,
    *,
    db: Any,
    XpEvent: Any,
    get_level_info: Any,
    _refresh_streak_from_study_time: Any,
    Document: Any,
    Follow: Any,
    XP_HISTORY_LABELS: Any,
    HOW_TO_EARN_XP: Any,
    _study_local_date: Any,
    StudyTimeLog: Any,
    STUDY_TIME_FEATURE: Any,
    MIN_QUALIFYING_STUDY_SECONDS: Any,
    User: Any,
    XP_STREAK_MILESTONES: Any,
    limiter: Any,
    login_required: Any,
    require_csrf: Any,
    MAX_STUDY_TIME_SECONDS_PER_DAY: Any,
    reconcile_study_time: Any,
    UserAchievement: Any,
    ACHIEVEMENT_DEFINITIONS: Any,
) -> None:
    """Register the existing study activity routes without changing contracts."""
    @app.route("/gamification/summary")
    def gamification_summary():
        """
        Lightweight combined payload for surfaces that show XP/streak as
        small stat pills rather than the full detail screens - the Home
        streak banner and the Profile stat row (Streak / XP / Docs /
        Followers) in the current frontend.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        xp_total = db.session.query(func.coalesce(func.sum(XpEvent.xp_amount), 0)).filter(
            XpEvent.user_id == user_id
        ).scalar()
        level_info = get_level_info(xp_total)
        streak = _refresh_streak_from_study_time(user_id)
        db.session.commit()  # persist a lazily-created StudyStreak row, if any

        documents_count = Document.query.filter_by(user_id=user_id, is_removed=False).count()
        followers_count = Follow.query.filter_by(followed_id=user_id).count()

        return jsonify({
            "xp_total": xp_total,
            "level": level_info["level"],
            "level_title": level_info["title"],
            "current_streak": streak.current_streak,
            "longest_streak": streak.longest_streak,
            "documents_count": documents_count,
            "followers_count": followers_count,
        })


    @app.route("/xp/progress")
    def xp_progress():
        """Powers XPProgressScreen: the level ring, and a paginated feed of
        recent XP-earning events."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        xp_total = db.session.query(func.coalesce(func.sum(XpEvent.xp_amount), 0)).filter(
            XpEvent.user_id == user_id
        ).scalar()
        level_info = get_level_info(xp_total)

        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        per_page = 20

        events = (
            XpEvent.query.filter_by(user_id=user_id)
            .order_by(XpEvent.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        history = []
        for e in events:
            icon, label = XP_HISTORY_LABELS.get(e.event_type, ("⭐", e.event_type.replace("_", " ").title()))
            history.append({
                "icon": icon,
                "label": label,
                "xp": e.xp_amount,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            })

        return jsonify({
            "level": level_info["level"],
            "level_title": level_info["title"],
            "xp_total": xp_total,
            "xp_into_level": level_info["xp_into_level"],
            "xp_for_level_gap": level_info["xp_for_level_gap"],
            "next_level_xp": level_info["next_level_xp"],
            "page": page,
            "history": history,
            "how_to_earn": HOW_TO_EARN_XP,
        })


    STREAK_MILESTONE_LABELS = {7: "7-Day Scholar", 14: "14-Day Achiever", 21: "21-Day Legend", 30: "30-Day Master"}


    @app.route("/profile/posts")
    def profile_posts():
        """Return the authenticated student's real profile posts.
        The social-post composer is not enabled yet, so an empty result is
        preferable to fabricated demo content in a production profile."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        return jsonify({"posts": [], "composer_enabled": False})


    @app.route("/streak")
    def streak_detail():
        """Powers StudyStreakScreen: current/longest streak, a
        month-by-month activity calendar (GitHub-contributions style,
        navigable via ?month=YYYY-MM), and milestone progress."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        today = _study_local_date()
        streak = _refresh_streak_from_study_time(user_id, today)
        db.session.commit()

        month_param = request.args.get("month")
        view_first_day = None
        if month_param:
            try:
                y_str, m_str = month_param.split("-")
                view_first_day = datetime(int(y_str), int(m_str), 1).date()
            except (ValueError, TypeError):
                view_first_day = None
        if view_first_day is None:
            view_first_day = today.replace(day=1)

        if view_first_day.month == 12:
            next_month_first_day = view_first_day.replace(year=view_first_day.year + 1, month=1)
        else:
            next_month_first_day = view_first_day.replace(month=view_first_day.month + 1)
        view_last_day = next_month_first_day - timedelta(days=1)

        active_dates = {
            activity_date
            for activity_date, study_seconds in (
                db.session.query(
                    StudyTimeLog.activity_date,
                    db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0),
                )
                .filter(
                    StudyTimeLog.user_id == user_id,
                    StudyTimeLog.feature == STUDY_TIME_FEATURE,
                    StudyTimeLog.activity_date >= view_first_day,
                    StudyTimeLog.activity_date <= view_last_day,
                )
                .group_by(StudyTimeLog.activity_date)
                .all()
            )
            if int(study_seconds or 0) >= MIN_QUALIFYING_STUDY_SECONDS
        }

        # Per-day study duration (summed across all StudyTimeLog features)
        # for the viewed month, so the frontend can shade each calendar
        # tile by how long the student studied that day - GitHub-style
        # contribution intensity - rather than a flat studied/not-studied
        # boolean.
        study_seconds_by_date = dict(
            db.session.query(
                StudyTimeLog.activity_date,
                db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0),
            )
            .filter(
                StudyTimeLog.user_id == user_id,
                StudyTimeLog.activity_date >= view_first_day,
                StudyTimeLog.activity_date <= view_last_day,
            )
            .group_by(StudyTimeLog.activity_date)
            .all()
        )

        calendar = []
        num_days_in_month = (view_last_day - view_first_day).days + 1
        for i in range(num_days_in_month):
            day = view_first_day + timedelta(days=i)
            calendar.append({
                "date": day.isoformat(),
                "studied": day in active_dates,
                "is_future": day > today,
                "study_seconds": int(study_seconds_by_date.get(day, 0)),
            })

        # Bound backward navigation by account creation, not first study
        # activity - a brand-new account whose only activity is this month
        # would otherwise have earliest_month == calendar_month and
        # permanently disable the prev button on load. Matches GitHub's
        # own contribution calendar, which scrolls back through empty
        # months to account creation, not just to first contribution.
        user = db.session.get(User, user_id)
        account_created = user.created_at.date() if (user and user.created_at) else today
        earliest_month = account_created.strftime("%Y-%m")

        milestones = [
            {
                "days": days,
                "label": STREAK_MILESTONE_LABELS[days],
                "xp": f"+{xp} XP",
                "done": streak.longest_streak >= days,
            }
            for days, xp in sorted(XP_STREAK_MILESTONES.items())
        ]

        return jsonify({
            "current_streak": streak.current_streak,
            "longest_streak": streak.longest_streak,
            "calendar_month": view_first_day.strftime("%Y-%m"),
            "calendar_start_weekday": (view_first_day.weekday() + 1) % 7,  # 0=Sun..6=Sat to match S M T W T F S header
            "earliest_month": earliest_month,
            "calendar": calendar,
            "milestones": milestones,
        })


    @app.route("/study-time/sync", methods=["POST"])
    @limiter.limit(
        "20 per hour",
        key_func=lambda: f"study-sync:{session.get('user_id', get_remote_address())}",
    )
    @login_required
    @require_csrf
    def study_time_sync():
        """
        Synchronize one absolute Study Hub total for the authenticated student.

        This replaces the old per-document 20-second heartbeat. The client
        accumulates active Study Hub time locally and sends an absolute daily
        target. The server only accepts the forward difference and serializes
        concurrent syncs per account.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        data = request.get_json(silent=True) or {}
        try:
            target_seconds = int(data.get("total_seconds"))
        except (TypeError, ValueError):
            return jsonify({"error": "total_seconds must be an integer"}), 400

        if target_seconds < 0:
            return jsonify({"error": "total_seconds must be non-negative"}), 400
        if target_seconds > MAX_STUDY_TIME_SECONDS_PER_DAY:
            target_seconds = MAX_STUDY_TIME_SECONDS_PER_DAY

        today = _study_local_date()
        server_seconds, accepted = reconcile_study_time(user_id, target_seconds, today)
        study_day_active = server_seconds >= MIN_QUALIFYING_STUDY_SECONDS

        if accepted:
            _refresh_streak_from_study_time(user_id, today)
        else:
            _refresh_streak_from_study_time(user_id, today)

        db.session.commit()
        return jsonify({
            "study_time_seconds_today": int(server_seconds),
            "total_seconds": int(server_seconds),
            "accepted_seconds": int(accepted),
            "qualifying_study_seconds": MIN_QUALIFYING_STUDY_SECONDS,
            "study_day_active": study_day_active,
        })


    @app.route("/study-time/heartbeat", methods=["POST"])
    def study_time_heartbeat_legacy():
        """The old per-document heartbeat is intentionally disabled."""
        return jsonify({
            "error": "The per-document study heartbeat was retired; use /study-time/sync."
        }), 410


    @app.route("/study-time")
    def study_time_summary():
        """
        Powers TimeStudiedScreen. Study Hub is one authoritative learning
        total; by_feature is retained as a compatibility shape and contains
        only the study_hub total.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        period = request.args.get("period", "week")
        today = _study_local_date()
        if period == "day":
            start_date = today
        elif period == "month":
            start_date = today.replace(day=1)
        else:
            period = "week"
            start_date = today - timedelta(days=today.weekday())

        rows = db.session.query(
            StudyTimeLog.feature,
            db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0),
        ).filter(
            StudyTimeLog.user_id == user_id,
            StudyTimeLog.activity_date >= start_date,
            StudyTimeLog.activity_date <= today,
            StudyTimeLog.feature == STUDY_TIME_FEATURE,
        ).group_by(StudyTimeLog.feature).all()

        by_feature = {feature: seconds for feature, seconds in rows}
        total_seconds = sum(by_feature.values())

        return jsonify({
            "period": period,
            "total_seconds": total_seconds,
            "by_feature": by_feature,
        })


    @app.route("/achievements")
    def list_achievements():
        """Powers AchievementsScreen: full catalog split into
        unlocked/in-progress, with progress counters for locked ones."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        unlocked_rows = {
            row.achievement_code: row.unlocked_at
            for row in UserAchievement.query.filter_by(user_id=user_id).all()
        }

        result = []
        for a in ACHIEVEMENT_DEFINITIONS:
            code = a["code"]
            is_done = code in unlocked_rows
            progress = a["total"] if is_done else a["check"](user_id)
            result.append({
                "code": code,
                "icon": a["icon"],
                "name": a["name"],
                "desc": a["desc"],
                "done": is_done,
                "unlocked_at": unlocked_rows[code].isoformat() if is_done else None,
                "progress": progress,
                "total": a["total"],
            })

        return jsonify({
            "unlocked_count": len(unlocked_rows),
            "total_count": len(ACHIEVEMENT_DEFINITIONS),
            "achievements": result,
        })
