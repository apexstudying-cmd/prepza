from __future__ import annotations

import sys
from functools import wraps
from types import ModuleType, SimpleNamespace

from flask import Flask, jsonify, request, session

import student_subscription_billing as billing


class _Result:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeSession:
    def __init__(self):
        self.statements = []
        self.commit_count = 0
        self.existing_refund_status = None

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, params))
        if "SELECT status FROM student_refund_request" in sql:
            return _Result(self.existing_refund_status)
        return _Result()

    def commit(self):
        self.commit_count += 1


def _registered_app(monkeypatch):
    economics = ModuleType("ai_economics")
    economics.get_plan = lambda _db, _plan: None
    monkeypatch.setitem(sys.modules, "ai_economics", economics)

    app = Flask("prepza-student-subscription-billing-contract")
    app.secret_key = "billing-contract-test-only"
    app.config["TESTING"] = True

    fake_session = _FakeSession()
    db = SimpleNamespace(session=fake_session)
    payment = {
        "id": 17,
        "user_id": 23,
        "amount": 499,
        "plan": "plus",
    }
    quote = {
        "eligible_standard": True,
        "refund_amount_kes": 499,
        "consumed_value_kes": 0,
        "retention_amount_kes": 0,
    }

    monkeypatch.setattr(
        billing,
        "_active_payment",
        lambda _db, user_id, payment_id=None, plan=None: (
            payment
            if user_id == 23
            and payment_id in (None, 17)
            and plan in (None, "plus")
            else None
        ),
    )
    monkeypatch.setattr(
        billing,
        "calculate_refund_quote",
        lambda _db, _payment: dict(quote),
    )

    csrf_views = []

    def require_csrf(view):
        csrf_views.append(view.__name__)

        @wraps(view)
        def guarded(*args, **kwargs):
            supplied = request.headers.get("X-CSRF-Token")
            expected = session.get("csrf_token")
            if not supplied or not expected or supplied != expected:
                return jsonify({"error": "Missing or invalid CSRF token"}), 403
            return view(*args, **kwargs)

        return guarded

    def require_admin(view):
        @wraps(view)
        def guarded(*args, **kwargs):
            if not session.get("is_admin"):
                return jsonify({"error": "Forbidden"}), 403
            return view(*args, **kwargs)

        return guarded

    billing.register_student_subscription_billing(
        app,
        db,
        Payment=object(),
        User=object(),
        require_csrf=require_csrf,
        require_admin=require_admin,
        paystack_request=lambda *_args, **_kwargs: {},
    )
    return app, fake_session, payment, quote, csrf_views


def test_refund_quote_is_read_only_and_keeps_the_existing_response(monkeypatch):
    app, fake_session, _payment, quote, _csrf_views = _registered_app(monkeypatch)
    routes = {
        (rule.rule, method)
        for rule in app.url_map.iter_rules()
        for method in rule.methods - {"HEAD", "OPTIONS"}
    }
    assert ("/subscription/refund-quote", "GET") in routes
    assert ("/subscription/refund-request", "POST") in routes

    client = app.test_client()
    anonymous = client.get("/subscription/refund-quote")
    assert anonymous.status_code == 401
    assert anonymous.get_json() == {"error": "Not logged in"}

    with client.session_transaction() as stored:
        stored["user_id"] = 23

    response = client.get("/subscription/refund-quote?payment_id=17&plan=plus")
    assert response.status_code == 200
    assert response.get_json() == quote
    assert fake_session.statements == []
    assert fake_session.commit_count == 0


def test_refund_request_keeps_csrf_validation_persistence_and_duplicate_guard(monkeypatch):
    app, fake_session, payment, quote, csrf_views = _registered_app(monkeypatch)
    assert "subscription_refund_request" in csrf_views
    client = app.test_client()

    with client.session_transaction() as stored:
        stored["user_id"] = 23
        stored["csrf_token"] = "contract-csrf-token"

    payload = {
        "payment_id": payment["id"],
        "plan": payment["plan"],
        "reason": "Please review my unused subscription.",
    }
    missing_csrf = client.post("/subscription/refund-request", json=payload)
    assert missing_csrf.status_code == 403
    assert fake_session.statements == []
    assert fake_session.commit_count == 0

    created = client.post(
        "/subscription/refund-request",
        json=payload,
        headers={"X-CSRF-Token": "contract-csrf-token"},
    )
    assert created.status_code == 201
    assert created.get_json() == {"ok": True, "status": "requested", "quote": quote}
    assert len(fake_session.statements) == 2
    select_sql, select_params = fake_session.statements[0]
    insert_sql, insert_params = fake_session.statements[1]
    assert "SELECT status FROM student_refund_request" in select_sql
    assert select_params == {"pid": payment["id"]}
    assert "INSERT INTO student_refund_request" in insert_sql
    assert "ON CONFLICT (payment_id) DO UPDATE" in insert_sql
    assert insert_params == {
        "pid": payment["id"],
        "uid": 23,
        "amount": quote["refund_amount_kes"],
        "consumed": quote["consumed_value_kes"],
        "retention": quote["retention_amount_kes"],
        "reason": payload["reason"],
    }
    assert fake_session.commit_count == 1

    fake_session.existing_refund_status = "requested"
    duplicate = client.post(
        "/subscription/refund-request",
        json=payload,
        headers={"X-CSRF-Token": "contract-csrf-token"},
    )
    assert duplicate.status_code == 409
    assert duplicate.get_json() == {
        "error": "A refund request already exists for this payment",
        "status": "requested",
    }
    assert len(fake_session.statements) == 3
    assert fake_session.commit_count == 1
