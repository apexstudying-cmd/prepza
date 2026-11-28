from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

from flask import Flask, session

from student_subscription_routes import register_student_subscription_routes


class _FakeSession:
    def __init__(self):
        self.added = []
        self.flush_count = 0
        self.commit_count = 0

    def get(self, _model, user_id):
        return SimpleNamespace(id=user_id, email="student@example.test")

    def add(self, value):
        self.added.append(value)

    def flush(self):
        self.flush_count += 1

    def commit(self):
        self.commit_count += 1


class _FakePayment:
    def __init__(self, **values):
        self.__dict__.update(values)


class _RecordingLimiter:
    def __init__(self):
        self.calls = []

    def limit(self, rule, *, key_func):
        def decorate(view):
            self.calls.append((view.__name__, rule, key_func))
            return view
        return decorate


def _registered_app(*, pending=None, status=None):
    app = Flask("prepza-student-subscription-routes")
    app.secret_key = "contract-test-only"
    app.config["TESTING"] = True
    fake_session = _FakeSession()
    db = SimpleNamespace(session=fake_session)
    limiter = _RecordingLimiter()
    csrf_calls = []
    provider_calls = []
    order_calls = []
    pending_calls = []

    def require_csrf(view):
        csrf_calls.append(view.__name__)
        return view

    def find_pending_checkout(user_id, *, plan):
        pending_calls.append((user_id, plan))
        return pending

    def create_order(payment, **kwargs):
        order_calls.append((payment, kwargs))

    def create_paystack_transaction(reference, amount, description, user, **kwargs):
        provider_calls.append((reference, amount, description, user, kwargs))
        return "provider-reference", "https://checkout.example.test/authorize"

    helpers = {
        "find_pending_checkout": find_pending_checkout,
        "create": create_order,
    }
    register_student_subscription_routes(
        app,
        db,
        User=object(),
        Payment=_FakePayment,
        limiter=limiter,
        get_remote_address=lambda: "127.0.0.1",
        require_csrf=require_csrf,
        get_user_subscription_status=lambda user_id: status or {"plan": "free", "is_active": False},
        create_paystack_transaction=create_paystack_transaction,
        student_order_helpers=helpers,
    )
    return {
        "app": app,
        "db": db,
        "session": fake_session,
        "limiter": limiter,
        "csrf_calls": csrf_calls,
        "provider_calls": provider_calls,
        "order_calls": order_calls,
        "pending_calls": pending_calls,
    }


def test_subscription_routes_keep_existing_paths_methods_and_security_decorators():
    state = _registered_app()
    app = state["app"]
    routes = {
        rule.endpoint: (rule.rule, frozenset(rule.methods - {"HEAD", "OPTIONS"}))
        for rule in app.url_map.iter_rules()
        if rule.endpoint != "static"
    }
    assert routes == {
        "subscription_plans": ("/subscription/plans", frozenset({"GET"})),
        "subscription_status": ("/subscription/status", frozenset({"GET"})),
        "subscription_upgrade": ("/subscription/upgrade", frozenset({"POST"})),
    }
    assert state["limiter"].calls[0][0:2] == ("subscription_upgrade", "1 per 20 seconds")
    assert state["csrf_calls"] == ["subscription_upgrade"]

    key_func = state["limiter"].calls[0][2]
    with app.test_request_context("/"):
        session["user_id"] = 23
        assert key_func() == "sub_upgrade:23"


def test_subscription_plans_response_keeps_admin_configured_plan_fields(monkeypatch):
    plan = {
        "plan_code": "free",
        "display_name": "Free",
        "price_kes": 0,
        "billing_period": "monthly",
        "quota_period": "month",
        "ada_monthly_units": 500000,
        "ada_daily_units": 50000,
        "ada_max_output_tokens": 2048,
        "podcast_minutes": 10,
        "summary_pages": 10,
        "questions": 20,
        "mind_map_nodes": 30,
        "flashcards": 100,
        "premium_library": False,
        "study_hub_uploads": True,
    }
    economics = ModuleType("ai_economics")
    economics.get_plans = lambda _db: [plan]
    monkeypatch.setitem(sys.modules, "ai_economics", economics)

    state = _registered_app()
    response = state["app"].test_client().get("/subscription/plans")

    assert response.status_code == 200
    assert response.get_json() == {
        "plans": [{
            "id": "free",
            "name": "Free",
            "price": 0,
            "period": None,
            "quota_period": "month",
            "ada_monthly_units": 500000,
            "ada_daily_units": 50000,
            "ada_max_output_tokens": 2048,
            "podcast_minutes": 10,
            "summary_pages": 10,
            "questions": 20,
            "mind_map_nodes": 30,
            "flashcards": 100,
            "offline_study": True,
            "premium_library": False,
            "study_hub_uploads": True,
        }]
    }


def test_subscription_status_keeps_manual_session_authentication_and_payload():
    expected = {
        "plan": "plus",
        "is_active": True,
        "starts_at": "2026-11-01T00:00:00",
        "expires_at": "2026-12-01T00:00:00",
        "cancel_at_period_end": False,
        "recurring": True,
    }
    state = _registered_app(status=expected)
    client = state["app"].test_client()

    anonymous = client.get("/subscription/status")
    assert anonymous.status_code == 401
    assert anonymous.get_json() == {"error": "Not logged in"}

    with client.session_transaction() as stored:
        stored["user_id"] = 23
    authenticated = client.get("/subscription/status")
    assert authenticated.status_code == 200
    assert authenticated.get_json() == expected


def test_subscription_upgrade_recovers_existing_pending_checkout_without_provider_call(monkeypatch):
    economics = ModuleType("ai_economics")
    economics.get_plan = lambda _db, plan: {"price_kes": 499} if plan == "plus" else None
    monkeypatch.setitem(sys.modules, "ai_economics", economics)
    monkeypatch.setenv("PAYSTACK_PLUS_PLAN_CODE", "PLN_plus_test")
    pending = {
        "checkout_url": "https://checkout.example.test/existing",
        "reference": "PZA-sub-plus-existing",
        "order_number": "PZA-ORD-0001",
    }
    state = _registered_app(pending=pending)
    client = state["app"].test_client()
    with client.session_transaction() as stored:
        stored["user_id"] = 23

    response = client.post("/subscription/upgrade", json={"plan": "plus"})

    assert response.status_code == 200
    assert response.get_json() == {
        "redirect_url": pending["checkout_url"],
        "reference": pending["reference"],
        "order_number": pending["order_number"],
        "recovered": True,
    }
    assert state["provider_calls"] == []
    assert state["session"].added == []
    assert state["order_calls"] == []
    assert state["pending_calls"] == [(23, "plus")]


def test_subscription_upgrade_creates_the_same_pending_payment_and_order_snapshot(monkeypatch):
    economics = ModuleType("ai_economics")
    economics.get_plan = lambda _db, plan: {"price_kes": 499} if plan == "plus" else None
    monkeypatch.setitem(sys.modules, "ai_economics", economics)
    monkeypatch.setenv("PAYSTACK_PLUS_PLAN_CODE", "PLN_plus_test")
    state = _registered_app()
    client = state["app"].test_client()
    with client.session_transaction() as stored:
        stored["user_id"] = 23

    response = client.post(
        "/subscription/upgrade",
        json={"plan": "plus", "phone_number": "0712345678"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["redirect_url"] == "https://checkout.example.test/authorize"
    assert body["reference"].startswith("PZA-sub-plus-")
    assert set(body) == {"redirect_url", "reference"}

    assert len(state["provider_calls"]) == 1
    reference, amount, description, user, options = state["provider_calls"][0]
    assert reference == body["reference"]
    assert amount == 499
    assert description == "Prepza Plus Plan"
    assert user.email == "student@example.test"
    assert options == {"paystack_plan_code": "PLN_plus_test"}

    assert len(state["session"].added) == 1
    payment = state["session"].added[0]
    assert payment.user_id == 23
    assert payment.content_item_id is None
    assert payment.phone_number == "0712345678"
    assert payment.amount == 499
    assert payment.provider == "paystack"
    assert payment.reference == body["reference"]
    assert payment.provider_reference == "provider-reference"
    assert payment.payment_type == "subscription"
    assert payment.plan == "plus"
    assert payment.status == "pending"
    assert state["session"].flush_count == 1
    assert state["session"].commit_count == 1

    assert len(state["order_calls"]) == 1
    order_payment, order_kwargs = state["order_calls"][0]
    assert order_payment is payment
    assert order_kwargs == {
        "item_title": "Plus Plan",
        "checkout_url": "https://checkout.example.test/authorize",
        "requested_payload": {
            "payment_type": "subscription",
            "plan": "plus",
            "plan_name": "Plus",
            "quantity": 1,
        },
    }


def test_subscription_upgrade_rejects_unauthenticated_invalid_unavailable_and_unconfigured_requests(monkeypatch):
    economics = ModuleType("ai_economics")
    economics.get_plan = lambda _db, plan: {"price_kes": 0} if plan == "plus" else None
    monkeypatch.setitem(sys.modules, "ai_economics", economics)
    monkeypatch.delenv("PAYSTACK_PLUS_PLAN_CODE", raising=False)
    state = _registered_app()
    client = state["app"].test_client()

    anonymous = client.post("/subscription/upgrade", json={"plan": "plus"})
    assert anonymous.status_code == 401

    with client.session_transaction() as stored:
        stored["user_id"] = 23

    invalid = client.post("/subscription/upgrade", json={"plan": "premium"})
    assert invalid.status_code == 400
    assert invalid.get_json() == {"error": "plan must be 'plus' or 'pro'"}

    unavailable = client.post("/subscription/upgrade", json={"plan": "plus"})
    assert unavailable.status_code == 400
    assert unavailable.get_json() == {"error": "This plan is not currently available"}

    economics.get_plan = lambda _db, plan: {"price_kes": 499}
    unconfigured = client.post("/subscription/upgrade", json={"plan": "plus"})
    assert unconfigured.status_code == 503
    assert "Recurring billing is not configured" in unconfigured.get_json()["error"]
    assert state["provider_calls"] == []
    assert state["session"].added == []
