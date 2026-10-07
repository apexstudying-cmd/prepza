"""Runtime regression tests for the single Study Hub study-time contract."""
from __future__ import annotations

import threading
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from werkzeug.security import generate_password_hash

from app import (
    app,
    db,
    User,
    StudyTimeLog,
    StudyStreak,
    XpEvent,
    STUDY_TIME_FEATURE,
    MAX_STUDY_TIME_SECONDS_PER_DAY,
    MIN_QUALIFYING_STUDY_SECONDS,
    reconcile_study_time,
    _refresh_streak_from_study_time,
    _study_local_date,
    XP_STREAK_MILESTONES,
)


@pytest.fixture(scope="module")
def runtime_user():
    with app.app_context():
        app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False, PROPAGATE_EXCEPTIONS=True)
        user = User(
            email=f"study-time.{uuid4().hex}@test.invalid",
            password_hash=generate_password_hash("StudyTime!Test123"),
            year=2,
            semester=1,
            display_name="Study Time Runtime",
            email_verified=True,
            is_admin=False,
            is_suspended=False,
            profile_visibility="public",
            who_can_message="everyone",
            who_can_follow="everyone",
            read_receipts_enabled=True,
            university_id=None,
            program_id=None,
            session_version=0,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        yield user_id

        StudyTimeLog.query.filter_by(user_id=user_id).delete()
        StudyStreak.query.filter_by(user_id=user_id).delete()
        XpEvent.query.filter_by(user_id=user_id).delete()
        db.session.delete(db.session.get(User, user_id))
        db.session.commit()
        db.session.remove()


def _today():
    from app import _study_local_date
    return _study_local_date()

@pytest.fixture(autouse=True)
def clean_study_time(runtime_user):
    with app.app_context():
        StudyTimeLog.query.filter_by(user_id=runtime_user).delete()
        StudyStreak.query.filter_by(user_id=runtime_user).delete()
        db.session.commit()
        yield
        db.session.rollback()


def test_absolute_sync_is_monotonic_and_replay_safe(runtime_user):
    with app.app_context():
        first, accepted = reconcile_study_time(runtime_user, 1800, _today())
        db.session.commit()
        assert first == 1800
        assert accepted == 1800

        replayed, accepted = reconcile_study_time(runtime_user, 1800, _today())
        db.session.commit()
        assert replayed == 1800
        assert accepted == 0

        advanced, accepted = reconcile_study_time(runtime_user, 2400, _today())
        db.session.commit()
        assert advanced == 2400
        assert accepted == 600


def test_server_caps_client_target_at_daily_ceiling(runtime_user):
    with app.app_context():
        total, accepted = reconcile_study_time(
            runtime_user, MAX_STUDY_TIME_SECONDS_PER_DAY + 99999, _today()
        )
        db.session.commit()
        assert total == MAX_STUDY_TIME_SECONDS_PER_DAY
        assert accepted == MAX_STUDY_TIME_SECONDS_PER_DAY


def test_study_hub_uses_one_feature_row_not_document_rows(runtime_user):
    with app.app_context():
        reconcile_study_time(runtime_user, 600, _today())
        db.session.commit()
        rows = StudyTimeLog.query.filter_by(
            user_id=runtime_user, activity_date=_today()
        ).all()
        assert len(rows) == 1
        assert rows[0].feature == STUDY_TIME_FEATURE


def test_concurrent_reconciliation_does_not_double_credit(runtime_user):
    # Both requests intentionally target the same absolute total. Only one
    # transaction may advance the row; the other must observe the locked
    # server value and accept zero.
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        try:
            with app.app_context():
                barrier.wait(timeout=10)
                total, accepted = reconcile_study_time(runtime_user, 3000, _today())
                db.session.commit()
                results.append((total, accepted))
        except Exception as exc:
            errors.append(exc)
        finally:
            with app.app_context():
                db.session.remove()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert not errors
    assert len(results) == 2
    assert sorted(accepted for _, accepted in results) == [0, 3000]

    with app.app_context():
        row = StudyTimeLog.query.filter_by(
            user_id=runtime_user, activity_date=_today(), feature=STUDY_TIME_FEATURE
        ).one()
        assert row.study_time_seconds == 3000




def test_personal_streak_requires_the_full_ten_minutes(runtime_user):
    """9:59 is not a study day; 10:00 is exactly the qualifying boundary."""
    with app.app_context():
        today = _today()
        reconcile_study_time(runtime_user, MIN_QUALIFYING_STUDY_SECONDS - 1, today)
        db.session.commit()
        streak = _refresh_streak_from_study_time(runtime_user, today)
        assert streak.current_streak == 0
        assert streak.longest_streak == 0
        db.session.commit()

        reconcile_study_time(runtime_user, MIN_QUALIFYING_STUDY_SECONDS, today)
        db.session.commit()
        streak = _refresh_streak_from_study_time(runtime_user, today)
        assert streak.current_streak == 1
        assert streak.longest_streak == 1
        assert streak.last_study_date == today
        db.session.commit()


def test_personal_streak_consecutive_days_gaps_and_longest_are_exact(runtime_user):
    with app.app_context():
        today = _today()
        qualifying_dates = {
            today - timedelta(days=5),
            today - timedelta(days=4),
            today - timedelta(days=3),
            today - timedelta(days=1),
            today,
        }
        for activity_date in sorted(qualifying_dates):
            db.session.add(
                StudyTimeLog(
                    user_id=runtime_user,
                    activity_date=activity_date,
                    feature=STUDY_TIME_FEATURE,
                    study_time_seconds=MIN_QUALIFYING_STUDY_SECONDS,
                )
            )
        db.session.commit()

        streak = _refresh_streak_from_study_time(runtime_user, today)
        assert streak.current_streak == 2
        assert streak.longest_streak == 3
        assert streak.last_study_date == today
        db.session.commit()


def test_personal_streak_milestones_award_exact_xp_once(runtime_user):
    with app.app_context():
        today = _today()
        for offset in range(30):
            activity_date = today - timedelta(days=29 - offset)
            db.session.add(
                StudyTimeLog(
                    user_id=runtime_user,
                    activity_date=activity_date,
                    feature=STUDY_TIME_FEATURE,
                    study_time_seconds=MIN_QUALIFYING_STUDY_SECONDS,
                )
            )
        db.session.commit()

        # Walk the streak forward one day at a time so every milestone is
        # reached through the same transition the production sync uses.
        for offset in range(30):
            activity_date = today - timedelta(days=29 - offset)
            streak = _refresh_streak_from_study_time(runtime_user, activity_date)
            assert streak.current_streak == offset + 1
            db.session.commit()

        events = (
            XpEvent.query
            .filter_by(user_id=runtime_user, event_type="streak_milestone")
            .order_by(XpEvent.related_id.asc())
            .all()
        )
        assert [(event.related_id, event.xp_amount) for event in events] == [
            (days, XP_STREAK_MILESTONES[days])
            for days in sorted(XP_STREAK_MILESTONES)
        ]

        # Replaying the same 30-day history cannot create duplicate milestone
        # XP because XpEvent is uniquely keyed by user/type/related_id.
        for activity_date in (today - timedelta(days=1), today):
            _refresh_streak_from_study_time(runtime_user, activity_date)
            db.session.commit()

        replayed_count = XpEvent.query.filter_by(
            user_id=runtime_user, event_type="streak_milestone"
        ).count()
        assert replayed_count == len(XP_STREAK_MILESTONES)


def test_unrelated_xp_does_not_create_a_streak_day(runtime_user):
    with app.app_context():
        from app import award_xp

        assert award_xp(runtime_user, "quiz_completed", 20, related_id=12345)
        db.session.commit()

        streak = _refresh_streak_from_study_time(runtime_user, _today())
        assert streak.current_streak == 0
        assert streak.longest_streak == 0
        assert streak.last_study_date is None
        db.session.commit()


def test_streak_uses_nairobi_calendar_boundary(runtime_user, monkeypatch):
    """The streak calendar must switch dates at midnight Nairobi, not UTC."""
    import app as app_module

    real_datetime = app_module.datetime

    class FrozenDateTime(real_datetime):
        frozen_utc = real_datetime(2026, 10, 7, 20, 59, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            current = cls.frozen_utc
            return current.astimezone(tz) if tz else current

    monkeypatch.setattr(app_module, "datetime", FrozenDateTime)
    assert _study_local_date() == date(2026, 10, 7)

    FrozenDateTime.frozen_utc = real_datetime(2026, 10, 7, 21, 0, tzinfo=timezone.utc)
    assert _study_local_date() == date(2026, 10, 8)


def test_sync_endpoint_requires_auth_and_csrf(runtime_user):
    client = app.test_client()
    assert client.post("/study-time/sync", json={"total_seconds": 100}).status_code == 401

    with client.session_transaction() as session:
        session["user_id"] = runtime_user
        session["_session_version"] = 0
        session["csrf_token"] = "runtime-study-csrf"

    response = client.post(
        "/study-time/sync",
        json={"total_seconds": 100},
        headers={"X-CSRF-Token": "runtime-study-csrf"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["total_seconds"] >= 100
    assert body["accepted_seconds"] >= 0


def test_legacy_heartbeat_is_retired(runtime_user):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = runtime_user
        session["_session_version"] = 0
        session["csrf_token"] = "runtime-study-csrf"

    response = client.post(
        "/study-time/heartbeat",
        json={"feature": "reading", "document_id": 123},
        headers={"X-CSRF-Token": "runtime-study-csrf"},
    )
    assert response.status_code == 410


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
