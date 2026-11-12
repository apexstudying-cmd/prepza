from __future__ import annotations

import os
from pathlib import Path

from app_factory import create_app
from extensions import db
from route_registry import register_foundation_routes

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
REGISTRY_SOURCE = (ROOT / "route_registry.py").read_text(encoding="utf-8") if (ROOT / "route_registry.py").exists() else ""


def test_app_delegates_foundation_route_registration_in_original_order() -> None:
    assert "from route_registry import register_foundation_routes" in APP_SOURCE
    assert "register_foundation_routes(app, db)" in APP_SOURCE
    assert "register_usage_billing(app, db)" not in APP_SOURCE
    assert "register_ai_economics(app, db)" not in APP_SOURCE
    assert "kokoro_control.register(app)" not in APP_SOURCE

    expected = (
        "kokoro_control.register(app)",
        "register_usage_billing(app, db)",
        "register_ai_economics(app, db)",
        "register_organisation_billing(app, db)",
        "register_discovery(app, db)",
        "register_b2b_campaign_finance(app, db)",
        "register_b2b_admin_routes(app, db)",
        "register_b2b_campaign_payments(app, db)",
        "register_b2b_organisation_portal(app, db)",
    )
    positions = [REGISTRY_SOURCE.index(item) for item in expected]
    assert positions == sorted(positions)


def test_foundation_route_registry_registers_against_a_fresh_sqlite_app(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("SECRET_KEY", "route-registry-contract")
    monkeypatch.delenv("REDIS_URL", raising=False)
    app, _limiter = create_app()

    before = len(list(app.url_map.iter_rules()))
    register_foundation_routes(app, db)
    after = len(list(app.url_map.iter_rules()))

    assert after > before
    assert "kokoro_control" in app.blueprints
    assert any(rule.rule == "/internal/kokoro/jobs/claim" for rule in app.url_map.iter_rules())
