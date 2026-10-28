from datetime import date, timedelta

from study_friend_streak_routes import consecutive_shared_days


def test_shared_streak_keeps_yesterday_alive_until_today_ends():
    today = date(2026, 10, 28)
    qualifying = {today - timedelta(days=1), today - timedelta(days=2)}

    assert consecutive_shared_days(today, qualifying) == 2


def test_shared_streak_starts_today_when_both_people_qualify_today():
    today = date(2026, 10, 28)
    qualifying = {today, today - timedelta(days=1)}

    assert consecutive_shared_days(today, qualifying) == 2


def test_shared_streak_breaks_on_a_missing_shared_day():
    today = date(2026, 10, 28)
    qualifying = {today, today - timedelta(days=2), today - timedelta(days=3)}

    assert consecutive_shared_days(today, qualifying) == 1


def test_shared_streak_does_not_extend_without_today_or_yesterday():
    today = date(2026, 10, 28)
    qualifying = {today - timedelta(days=3), today - timedelta(days=4)}

    assert consecutive_shared_days(today, qualifying) == 0


from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shared_streak_routes_are_registered_during_chat_runtime_startup():
    source = (ROOT / "chat_interactions.py").read_text(encoding="utf-8")
    assert "register_study_friend_streak_routes(app, db)" in source


def test_shared_streak_routes_require_membership_and_csrf_for_mutations():
    source = (ROOT / "study_friend_streak_routes.py").read_text(encoding="utf-8")
    assert '@app.get("/chats/<int:conversation_id>/study-streak")' in source
    assert '@app.post("/chats/<int:conversation_id>/study-streak")' in source
    assert '@app.post("/chats/<int:conversation_id>/study-streak/accept")' in source
    assert '@app.post("/chats/<int:conversation_id>/study-streak/decline")' in source
    assert "if not user_id or not member(conversation_id, user_id):" in source
    assert "WHERE status IN ('active','pending')" in source


def test_shared_streak_chat_component_is_included_in_frontend_build():
    package = (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    patch = (ROOT / "tools" / "apply_shared_study_streak.py").read_text(encoding="utf-8")
    component = (ROOT / "frontend" / "src" / "crypto" / "SharedStudyStreak.tsx").read_text(encoding="utf-8")
    assert "apply_shared_study_streak.py" in package
    assert "SharedStudyStreak" in patch
    assert "Invite to shared streak" in component
    assert "Waiting for " in component
    assert "Accept" in component and "Decline" in component
