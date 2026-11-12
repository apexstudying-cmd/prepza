from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

from flask import Blueprint, Flask

from route_registry import register_foundation_routes

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
REGISTRY_SOURCE = (ROOT / "route_registry.py").read_text(encoding="utf-8")


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


def test_foundation_route_registry_preserves_registration_order_and_blueprint(monkeypatch) -> None:
    app = Flask("prepza-route-registry-contract")
    order: list[str] = []
    module_specs = (
        ("kokoro_control", "register", "kokoro_control"),
        ("usage_billing", "register_usage_billing", "usage_billing"),
        ("ai_economics", "register_ai_economics", "ai_economics"),
        ("organisation_billing", "register_organisation_billing", "organisation_billing"),
        ("discovery_billing", "register_discovery", "discovery"),
        ("b2b_campaign_finance", "register_b2b_campaign_finance", "b2b_campaign_finance"),
        ("b2b_admin_routes", "register_b2b_admin_routes", "b2b_admin_routes"),
        ("b2b_campaign_payments", "register_b2b_campaign_payments", "b2b_campaign_payments"),
        ("b2b_organisation_portal", "register_b2b_organisation_portal", "b2b_organisation_portal"),
    )

    for module_name, function_name, label in module_specs:
        module = ModuleType(module_name)

        if module_name == "kokoro_control":
            def register(target_app, label=label):
                order.append(label)
                blueprint = Blueprint("kokoro_control", __name__, url_prefix="/internal/kokoro")
                blueprint.add_url_rule("/jobs/claim", endpoint="claim", view_func=lambda: "")
                target_app.register_blueprint(blueprint)
            module.register = register
        else:
            def register(target_app, _db, label=label):
                order.append(label)
                target_app.add_url_rule(
                    f"/contract/{label}",
                    endpoint=f"contract_{label}",
                    view_func=lambda: "",
                )
            setattr(module, function_name, register)

        monkeypatch.setitem(sys.modules, module_name, module)

    register_foundation_routes(app, object())

    assert order == [spec[2] for spec in module_specs]
    assert "kokoro_control" in app.blueprints
    assert any(rule.rule == "/internal/kokoro/jobs/claim" for rule in app.url_map.iter_rules())
    assert len(list(app.url_map.iter_rules())) == 10
