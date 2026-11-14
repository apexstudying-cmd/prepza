from __future__ import annotations

from pathlib import Path

from flask import Flask

from gamification_routes import register_gamification_routes

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
REGISTRY_SOURCE = (ROOT / "route_registry.py").read_text(encoding="utf-8")
MODULE_SOURCE = (ROOT / "gamification_routes.py").read_text(encoding="utf-8")


def test_app_delegates_study_activity_routes_to_the_feature_module() -> None:
    assert "register_gamification_routes(" in APP_SOURCE
    assert 'from gamification_routes import register_gamification_routes as register' in REGISTRY_SOURCE
    for route in (
        'app.route("/gamification/summary")',
        'app.route("/xp/progress")',
        'app.route("/profile/posts")',
        'app.route("/streak")',
        'app.route("/study-time/sync", methods=["POST"])',
        'app.route("/study-time/heartbeat", methods=["POST"])',
        'app.route("/study-time")',
        'app.route("/achievements")',
    ):
        assert route not in APP_SOURCE
        assert route in MODULE_SOURCE


def test_study_activity_registration_preserves_route_surface_and_guards() -> None:
    app = Flask("prepza-gamification-contract")

    class Limiter:
        def limit(self, *_args, **_kwargs):
            return lambda function: function

    def identity(function):
        return function

    register_gamification_routes(
        app,
        db=object(),
        XpEvent=object(),
        get_level_info=lambda *_args: {},
        _refresh_streak_from_study_time=lambda *_args: object(),
        Document=object(),
        Follow=object(),
        XP_HISTORY_LABELS={},
        HOW_TO_EARN_XP=[],
        _study_local_date=lambda: None,
        StudyTimeLog=object(),
        STUDY_TIME_FEATURE="study_hub",
        MIN_QUALIFYING_STUDY_SECONDS=60,
        User=object(),
        XP_STREAK_MILESTONES={},
        limiter=Limiter(),
        login_required=identity,
        require_csrf=identity,
        MAX_STUDY_TIME_SECONDS_PER_DAY=86400,
        reconcile_study_time=lambda *_args: (0, 0),
        UserAchievement=object(),
        ACHIEVEMENT_DEFINITIONS=[],
    )

    routes = {rule.rule: rule.methods for rule in app.url_map.iter_rules()}
    assert {
        "/gamification/summary",
        "/xp/progress",
        "/profile/posts",
        "/streak",
        "/study-time/sync",
        "/study-time/heartbeat",
        "/study-time",
        "/achievements",
    }.issubset(routes)
    assert "POST" in routes["/study-time/sync"]
    assert "POST" in routes["/study-time/heartbeat"]
    assert "@login_required" in MODULE_SOURCE
    assert "@require_csrf" in MODULE_SOURCE
    assert "@limiter.limit(" in MODULE_SOURCE
