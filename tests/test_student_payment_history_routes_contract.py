from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from flask import Flask

from student_payment_history_routes import register_student_payment_history_route


class _Column:
    def __init__(self, name):
        self.name = name

    def __eq__(self, value):
        return ("eq", self.name, value)

    def in_(self, values):
        return ("in", self.name, tuple(values))

    def desc(self):
        return ("desc", self.name)


class _Query:
    def __init__(self, items):
        self.items = list(items)
        self.filter_args = ()
        self.order_args = ()

    def filter(self, *criteria):
        self.filter_args = criteria
        for kind, field, value in criteria:
            if kind == "eq":
                self.items = [item for item in self.items if getattr(item, field) == value]
            elif kind == "in":
                self.items = [item for item in self.items if getattr(item, field) in value]
        return self

    def order_by(self, *ordering):
        self.order_args = ordering
        for kind, field in ordering:
            if kind == "desc":
                self.items.sort(key=lambda item: getattr(item, field), reverse=True)
        return self

    def all(self):
        return self.items


class _Payment:
    user_id = _Column("user_id")
    payment_type = _Column("payment_type")
    created_at = _Column("created_at")


def _payment(*, id, user_id, payment_type, created_at, plan, amount, status, provider, reference):
    return SimpleNamespace(
        id=id,
        user_id=user_id,
        payment_type=payment_type,
        created_at=created_at,
        plan=plan,
        amount=amount,
        status=status,
        provider=provider,
        reference=reference,
    )


def test_payment_history_keeps_get_route_session_auth_filter_order_and_payload():
    app = Flask("prepza-payment-history-contract")
    app.secret_key = "contract-test-only"
    app.config["TESTING"] = True
    created = datetime.fromisoformat
    _Payment.query = _Query([
        _payment(id=10, user_id=23, payment_type="subscription", created_at=created("2026-11-18T08:00:00"), plan="plus", amount=499, status="success", provider="paystack", reference="sub-10"),
        _payment(id=11, user_id=23, payment_type="addon", created_at=created("2026-11-18T07:00:00"), plan="addon", amount=100, status="pending", provider="paystack", reference="addon-11"),
        _payment(id=12, user_id=23, payment_type="content", created_at=created("2026-11-18T06:00:00"), plan=None, amount=50, status="success", provider="paystack", reference="legacy-12"),
        _payment(id=13, user_id=24, payment_type="subscription", created_at=created("2026-11-18T09:00:00"), plan="pro", amount=999, status="success", provider="paystack", reference="other-13"),
    ])
    register_student_payment_history_route(app, _Payment)
    client = app.test_client()

    routes = {
        rule.endpoint: (rule.rule, frozenset(rule.methods - {"HEAD", "OPTIONS"}))
        for rule in app.url_map.iter_rules()
        if rule.endpoint != "static"
    }
    assert routes == {"payment_history": ("/payment-history", frozenset({"GET"}))}

    anonymous = client.get("/payment-history")
    assert anonymous.status_code == 401
    assert anonymous.get_json() == {"error": "Not logged in"}

    with client.session_transaction() as stored:
        stored["user_id"] = 23
    authenticated = client.get("/payment-history")
    assert authenticated.status_code == 200
    assert authenticated.get_json() == {
        "payments": [
            {
                "id": 10,
                "payment_type": "subscription",
                "content_title": None,
                "plan": "plus",
                "amount": 499,
                "status": "success",
                "provider": "paystack",
                "reference": "sub-10",
                "created_at": "2026-11-18T08:00:00",
            },
            {
                "id": 11,
                "payment_type": "addon",
                "content_title": None,
                "plan": "addon",
                "amount": 100,
                "status": "pending",
                "provider": "paystack",
                "reference": "addon-11",
                "created_at": "2026-11-18T07:00:00",
            },
        ]
    }

    query = _Payment.query
    assert query.filter_args == (
        ("eq", "user_id", 23),
        ("in", "payment_type", ("subscription", "addon")),
    )
    assert query.order_args == (("desc", "created_at"),)
