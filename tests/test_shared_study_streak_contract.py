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
