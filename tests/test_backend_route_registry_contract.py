from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

from flask import Blueprint, Flask

from route_registry import register_ambassador_routes, register_document_reader_routes, register_foundation_routes

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
REGISTRY_SOURCE = (ROOT / "route_registry.py").read_text(encoding="utf-8")


def test_app_delegates_foundation_route_registration_in_original_order() -> None:
    assert "from route_registry import (" in APP_SOURCE
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


def test_app_delegates_all_later_route_registrations_to_registry_in_order() -> None:
    expected_calls = (
        "_student_order_helpers, _student_subscription_billing = register_account_billing_routes(",
        "register_public_shell_route(",
        "register_academic_catalog_route(",
        "register_notification_feature_routes(",
        "register_opportunity_feature_routes(",
        "register_chat_feature_routes(",
        "register_control_feature_routes(",
        "register_admin_reconciled_routes(app)",
        "register_runtime_feature_routes(",
    )
    positions = [APP_SOURCE.index(item) for item in expected_calls]
    assert positions == sorted(positions)

    expected_functions = (
        "register_account_billing_routes",
        "register_public_shell_route",
        "register_academic_catalog_route",
        "register_notification_feature_routes",
        "register_opportunity_feature_routes",
        "register_chat_feature_routes",
        "register_control_feature_routes",
        "register_admin_reconciled_routes",
        "register_runtime_feature_routes",
    )
    for function_name in expected_functions:
        assert f"def {function_name}(" in REGISTRY_SOURCE

    for direct_call in (
        "register_email_otp(app",
        "register_admin_operations(app",
        "register_infrastructure_monitoring(",
        "register_public_shell_routes(app",
        "register_academic_catalog_routes(app",
        "register_notification_routes(app",
        "register_opportunity_runtime(app",
        "register_e2ee_chat_routes(app",
        "register_control_routes(",
        "register_offline_activity_routes(app",
        "register_e2ee_production_hardening(app",
        "register_shop_routes(app",
        "register_study_retrieval_routes(app",
        "register_request_observability(app",
    ):
        assert direct_call not in APP_SOURCE



def test_ambassador_routes_are_owned_by_the_feature_module_in_original_order() -> None:
    assert "register_ambassador_routes(" in APP_SOURCE
    assert "def ambassador_apply(" not in APP_SOURCE
    assert "def ambassador_request_payout(" not in APP_SOURCE
    assert "AMBASSADOR_PAYOUT_DESTINATION_REGEX" not in APP_SOURCE
    assert "def get_ambassador_settings(" in APP_SOURCE
    assert "def compute_ambassador_tier(" in APP_SOURCE
    assert "def generate_referral_code(" in APP_SOURCE
    assert "from ambassador_routes import register_ambassador_routes as register" in REGISTRY_SOURCE

    expected_calls = (
        "register_notification_preference_routes(",
        "register_ambassador_routes(",
        "register_opportunity_feature_routes(",
    )
    positions = [APP_SOURCE.rindex(call) for call in expected_calls]
    assert positions == sorted(positions)


def test_ambassador_route_registry_preserves_paths_methods_and_security_decorators() -> None:
    app = Flask("prepza-ambassador-route-contract")
    limiter_calls: list[tuple[str, str]] = []
    csrf_calls: list[str] = []

    class RecordingLimiter:
        def limit(self, rule: str):
            def decorate(view):
                limiter_calls.append((view.__name__, rule))
                return view
            return decorate

    def require_csrf(view):
        csrf_calls.append(view.__name__)
        return view

    register_ambassador_routes(
        app,
        object(),
        User=object(),
        Ambassador=object(),
        Referral=object(),
        AmbassadorPayout=object(),
        limiter=RecordingLimiter(),
        require_csrf=require_csrf,
        base_url="https://prepza.example",
        get_ambassador_settings=lambda: {},
        compute_ambassador_tier=lambda *_: (1, 10),
        generate_referral_code=lambda *_: "PREPZA123",
    )

    routes = {
        rule.endpoint: (rule.rule, frozenset(rule.methods - {"HEAD", "OPTIONS"}))
        for rule in app.url_map.iter_rules()
        if rule.endpoint != "static"
    }
    assert routes == {
        "ambassador_apply": ("/ambassador/apply", frozenset({"POST"})),
        "ambassador_status": ("/ambassador/status", frozenset({"GET"})),
        "ambassador_dashboard": ("/ambassador/dashboard", frozenset({"GET"})),
        "ambassador_referral_qr": ("/ambassador/referral-qr", frozenset({"GET"})),
        "ambassador_referrals": ("/ambassador/referrals", frozenset({"GET"})),
        "ambassador_payouts": ("/ambassador/payouts", frozenset({"GET"})),
        "ambassador_request_payout": ("/ambassador/payouts/request", frozenset({"POST"})),
    }
    assert limiter_calls == [
        ("ambassador_apply", "5 per hour"),
        ("ambassador_request_payout", "5 per hour"),
    ]
    assert csrf_calls == ["ambassador_apply", "ambassador_request_payout"]



def test_launch_wiring_audit_tracks_the_ambassador_route_module_owner() -> None:
    launch_wiring = (ROOT / "tools" / "verify_launch_wiring.py").read_text(encoding="utf-8")
    assert 'AMBASSADOR_ROUTES = ROOT / "ambassador_routes.py"' in launch_wiring
    assert '"register_ambassador_routes("' in launch_wiring
    assert "if AMBASSADOR_ROUTES.exists():" in launch_wiring
    assert '@app.route("/ambassador/referral-qr")' in launch_wiring



def test_document_reader_routes_are_owned_by_the_feature_module_at_the_original_registration_point() -> None:
    assert "register_document_reader_routes(" in APP_SOURCE
    assert "def get_document_reading(" not in APP_SOURCE
    assert "def save_document_reading(" not in APP_SOURCE
    assert "def render_document_reading_page(" not in APP_SOURCE
    assert "def _get_studyable_document(" in APP_SOURCE
    assert "def _document_reader_watermark(" in APP_SOURCE
    assert "from document_reader_routes import register_document_reader_routes as register" in REGISTRY_SOURCE

    registration = APP_SOURCE.rindex("register_document_reader_routes(")
    helper = APP_SOURCE.index("def _get_studyable_document(")
    next_document_route = APP_SOURCE.index('@app.route("/documents/<int:document_id>", methods=["PATCH"])')
    assert helper < registration < next_document_route


def test_document_reader_registry_forwards_explicit_dependencies(monkeypatch) -> None:
    app = Flask("prepza-document-reader-registry-contract")
    db = object()
    dependencies = {
        "DocumentReadingProgress": object(),
        "require_csrf": object(),
        "get_studyable_document": object(),
        "document_reader_watermark": object(),
        "fetch_private_file_bytes": object(),
        "render_watermarked_page": object(),
    }
    calls = {}
    module = ModuleType("document_reader_routes")

    def register(target_app, target_db, **kwargs):
        calls["args"] = (target_app, target_db)
        calls["kwargs"] = kwargs

    module.register_document_reader_routes = register
    monkeypatch.setitem(sys.modules, "document_reader_routes", module)

    register_document_reader_routes(app, db, **dependencies)

    assert calls == {"args": (app, db), "kwargs": dependencies}
