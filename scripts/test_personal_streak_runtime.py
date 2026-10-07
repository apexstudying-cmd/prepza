"""Deep runtime regression tests for personal Study Hub streak semantics."""
from __future__ import annotations

import threading
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from werkzeug.security import generate_password_hash

import app as app_module
from app import (
    XP_STREAK_MILESTONES,
    MIN_QUALIFYING_STUDY_SECONDS,
    STUDY_TIME_FEATURE,
    StudyActivityLog,
    StudyStreak,
    StudyTimeLog,
    User,
    XpEvent,
    _refresh_streak_from_study_time,
    _study_local_date,
    db,
    reconcile_study_time,
    record_study_activity,
)


@pytest.fixture(scope="module")
def runtime_user():
    with app_module.app.app_context():
        app_module.app.config.update(
            TESTING=True,
            SESSION_COOKIE_SECURE=False,
            PROPAGATE_EXCEPTIONS=True,
        )
        user = User(
            email=f"personal-streak.{uuid4().hex}@test.invalid",
            password_hash=generate_password_hash("PersonalStreak!Test123"),
            year=2,
            semester=1,
            display_name="Personal Streak Runtime",
            email_verified=True,
            is_admin=False,
            is_suspended=False,
            profile_visibility="public",
            who_can_message="everyone",
            who_can_follow="everyone",
            read_receipts_enabled=True,
            session_version=0,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        yield user_id

        XpEvent.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        StudyActivityLog.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        StudyTimeLog.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        StudyStreak.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        db.session.delete(db.session.get(User, user_id))
        db.session.commit()
        db.session.remove()


@pytest.fixture(autouse=True)
def clean_streak_state(runtime_user):
    with app_module.app.app_context():
        XpEvent.query.filter_by(user_id=runtime_user).delete(synchronize_session=False)
        StudyActivityLog.query.filter_by(user_id=runtime_user).delete(synchronize_session=False)
        StudyTimeLog.query.filter_by(user_id=runtime_user).delete(synchronize_session=False)
        StudyStreak.query.filter_by(user_id=runtime_user).delete(synchronize_session=False)
        db.session.commit()
        yield
        db.session.rollback()


def _today():
    return _study_local_date()


def _set_study_seconds(user_id: int, activity_date: date, seconds: int) -> None:
    row = StudyTimeLog.query.filter_by(
        user_id=user_id,
        activity_date=activity_date,
        feature=STUDY_TIME_FEATURE,
    ).one_or_none()
    if row is None:
        db.session.add(
            StudyTimeLog(
                user_id=user_id,
                activity_date=activity_date,
                feature=STUDY_TIME_FEATURE,
                study_time_seconds=seconds,
            )
        )
    else:
        row.study_time_seconds = seconds


def _commit_streak(user_id: int, today: date):
    streak = _refresh_streak_from_study_time(user_id, today)
    db.session.commit()
    return streak


def _logged_client(user_id: int):
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["_session_version"] = 0
    return client


def test_threshold_and_repeated_same_day_syncs(runtime_user):
    today = _today()
    with app_module.app.app_context():
        total, accepted = reconcile_study_time(
            runtime_user, MIN_QUALIFYING_STUDY_SECONDS - 1, today
        )
        db.session.commit()
        assert (total, accepted) == (
            MIN_QUALIFYING_STUDY_SECONDS - 1,
            MIN_QUALIFYING_STUDY_SECONDS - 1,
        )
        assert _commit_streak(runtime_user, today).current_streak == 0

        total, accepted = reconcile_study_time(
            runtime_user, MIN_QUALIFYING_STUDY_SECONDS - 1, today
        )
        db.session.commit()
        assert (total, accepted) == (MIN_QUALIFYING_STUDY_SECONDS - 1, 0)
        assert _commit_streak(runtime_user, today).current_streak == 0

        total, accepted = reconcile_study_time(
            runtime_user, MIN_QUALIFYING_STUDY_SECONDS, today
        )
        db.session.commit()
        assert (total, accepted) == (MIN_QUALIFYING_STUDY_SECONDS, 1)
        assert _commit_streak(runtime_user, today).current_streak == 1


def test_consecutive_days_gap_and_longest_streak(runtime_user):
    today = _today()
    with app_module.app.app_context():
        for delta in (5, 4, 3, 1, 0):
            _set_study_seconds(
                runtime_user,
                today - timedelta(days=delta),
                MIN_QUALIFYING_STUDY_SECONDS,
            )
        db.session.commit()

        streak = _commit_streak(runtime_user, today)
        assert (streak.current_streak, streak.longest_streak) == (2, 3)

        _set_study_seconds(
            runtime_user, today - timedelta(days=2), MIN_QUALIFYING_STUDY_SECONDS
        )
        db.session.commit()
        streak = _commit_streak(runtime_user, today)
        assert (streak.current_streak, streak.longest_streak) == (6, 6)


def test_milestones_are_exactly_once_and_duplicate_reach_preserves_streak(runtime_user):
    today = _today()
    with app_module.app.app_context():
        for days in (7, 14, 21, 30):
            start = today - timedelta(days=days - 1)
            for offset in range(days):
                _set_study_seconds(
                    runtime_user,
                    start + timedelta(days=offset),
                    MIN_QUALIFYING_STUDY_SECONDS,
                )
            db.session.commit()

            streak = _commit_streak(runtime_user, today)
            assert (streak.current_streak, streak.longest_streak) == (days, days)

            event = XpEvent.query.filter_by(
                user_id=runtime_user,
                event_type="streak_milestone",
                related_id=days,
            ).one()
            assert event.xp_amount == XP_STREAK_MILESTONES[days]

            _commit_streak(runtime_user, today)
            assert XpEvent.query.filter_by(
                user_id=runtime_user,
                event_type="streak_milestone",
                related_id=days,
            ).count() == 1

        # Rebuild the same streak while retaining the XP ledger. An already
        # awarded milestone must not roll back the newly-computed streak.
        StudyTimeLog.query.filter_by(user_id=runtime_user).delete(synchronize_session=False)
        StudyStreak.query.filter_by(user_id=runtime_user).delete(synchronize_session=False)
        db.session.commit()

        start = today - timedelta(days=29)
        for offset in range(30):
            _set_study_seconds(
                runtime_user,
                start + timedelta(days=offset),
                MIN_QUALIFYING_STUDY_SECONDS,
            )
        db.session.commit()

        streak = _commit_streak(runtime_user, today)
        assert (streak.current_streak, streak.longest_streak) == (30, 30)
        for days in (7, 14, 21, 30):
            assert XpEvent.query.filter_by(
                user_id=runtime_user,
                event_type="streak_milestone",
                related_id=days,
            ).count() == 1


def test_nairobi_calendar_boundary_is_authoritative(monkeypatch):
    class FrozenDateTime(datetime):
        current_utc = datetime(2026, 10, 7, 20, 59, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return cls.current_utc.replace(tzinfo=None)
            return cls.current_utc.astimezone(tz)

    monkeypatch.setattr(app_module, "datetime", FrozenDateTime)
    assert app_module._study_local_date() == date(2026, 10, 7)

    FrozenDateTime.current_utc = datetime(2026, 10, 7, 21, 0, tzinfo=timezone.utc)
    assert app_module._study_local_date() == date(2026, 10, 8)


def test_unrelated_actions_do_not_create_a_streak_day(runtime_user):
    today = _today()
    with app_module.app.app_context():
        assert record_study_activity(runtime_user) is False
        db.session.commit()
        assert _commit_streak(runtime_user, today).current_streak == 0
        assert StudyActivityLog.query.filter_by(user_id=runtime_user).count() == 0

        db.session.add(
            XpEvent(
                user_id=runtime_user,
                event_type="quiz_completed",
                xp_amount=5,
                related_id=999,
            )
        )
        db.session.commit()
        assert _commit_streak(runtime_user, today).current_streak == 0


def test_streak_route_uses_qualifying_study_time_for_calendar(runtime_user):
    today = _today()
    with app_module.app.app_context():
        _set_study_seconds(
            runtime_user,
            today - timedelta(days=2),
            MIN_QUALIFYING_STUDY_SECONDS - 1,
        )
        _set_study_seconds(
            runtime_user, today - timedelta(days=1), MIN_QUALIFYING_STUDY_SECONDS
        )
        _set_study_seconds(
            runtime_user, today, MIN_QUALIFYING_STUDY_SECONDS
        )
        db.session.commit()
        streak = _commit_streak(runtime_user, today)
        assert (streak.current_streak, streak.longest_streak) == (2, 2)

        client = _logged_client(runtime_user)
        response = client.get(f"/streak?month={today:%Y-%m}")
        assert response.status_code == 200
        body = response.get_json()
        calendar = {entry["date"]: entry for entry in body["calendar"]}

        assert calendar[(today - timedelta(days=2)).isoformat()]["studied"] is False
        assert calendar[(today - timedelta(days=1)).isoformat()]["studied"] is True
        assert calendar[today.isoformat()]["studied"] is True
        assert body["current_streak"] == 2
        assert body["longest_streak"] == 2


def test_concurrent_threshold_syncs_credit_one_day_and_one_streak(runtime_user):
    today = _today()
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        try:
            with app_module.app.app_context():
                barrier.wait(timeout=10)
                _, accepted = reconcile_study_time(
                    runtime_user, MIN_QUALIFYING_STUDY_SECONDS, today
                )
                streak = _refresh_streak_from_study_time(runtime_user, today)
                db.session.commit()
                results.append((accepted, streak.current_streak))
        except Exception as exc:
            errors.append(exc)
        finally:
            with app_module.app.app_context():
                db.session.remove()

    first = threading.Thread(target=worker)
    second = threading.Thread(target=worker)
    first.start()
    second.start()
    first.join(timeout=20)
    second.join(timeout=20)

    assert not errors
    assert len(results) == 2
    assert sorted(value for value, _ in results) == [
        0,
        MIN_QUALIFYING_STUDY_SECONDS,
    ]

    with app_module.app.app_context():
        row = StudyTimeLog.query.filter_by(
            user_id=runtime_user,
            activity_date=today,
            feature=STUDY_TIME_FEATURE,
        ).one()
        assert row.study_time_seconds == MIN_QUALIFYING_STUDY_SECONDS
        streak = StudyStreak.query.filter_by(user_id=runtime_user).one()
        assert streak.current_streak == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
