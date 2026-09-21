from types import SimpleNamespace

from student_orders import order_payment_matches_snapshot


def _order(**overrides):
    row = {
        "user_id": 7,
        "item_id": 42,
        "plan": None,
        "total_amount": 250,
        "unit_amount": 250,
        "quantity": 1,
        "currency": "KES",
        "order_type": "content",
    }
    row.update(overrides)
    return row


def _payment(**overrides):
    payment = {
        "status": "success",
        "user_id": 7,
        "content_item_id": 42,
        "plan": None,
        "amount": 250,
        "payment_type": "content",
    }
    payment.update(overrides)
    return SimpleNamespace(**payment)


def test_order_payment_match_accepts_exact_content_purchase():
    assert order_payment_matches_snapshot(_order(), _payment())


def test_order_payment_match_rejects_different_content_item():
    assert not order_payment_matches_snapshot(_order(), _payment(content_item_id=99))


def test_order_payment_match_rejects_different_student():
    assert not order_payment_matches_snapshot(_order(), _payment(user_id=8))


def test_order_payment_match_rejects_amount_change():
    assert not order_payment_matches_snapshot(_order(), _payment(amount=249))


def test_order_payment_match_rejects_payment_type_change():
    assert not order_payment_matches_snapshot(_order(), _payment(payment_type="subscription"))


def test_subscription_order_requires_subscription_payment():
    order = _order(order_type="subscription", item_id=None, plan="semester", total_amount=499)
    payment = _payment(
        content_item_id=None,
        plan="semester",
        amount=499,
        payment_type="subscription",
    )
    assert order_payment_matches_snapshot(order, payment)


def test_subscription_order_rejects_content_payment():
    order = _order(order_type="subscription", item_id=None, plan="semester", total_amount=499)
    payment = _payment(
        content_item_id=None,
        plan="semester",
        amount=499,
        payment_type="content",
    )
    assert not order_payment_matches_snapshot(order, payment)


def test_order_payment_match_rejects_currency_change():
    assert not order_payment_matches_snapshot(_order(currency="USD"), _payment())


def test_order_payment_match_rejects_quantity_or_total_inconsistency():
    assert not order_payment_matches_snapshot(_order(quantity=2), _payment())
    assert not order_payment_matches_snapshot(_order(unit_amount=249), _payment())


def test_subscription_order_rejects_unknown_plan():
    order = _order(
        order_type="subscription",
        item_id=None,
        plan="gold",
        total_amount=499,
        unit_amount=499,
    )
    payment = _payment(
        content_item_id=None,
        plan="gold",
        amount=499,
        payment_type="subscription",
    )
    assert not order_payment_matches_snapshot(order, payment)


def test_subscription_order_rejects_plan_change():
    order = _order(order_type="subscription", item_id=None, plan="semester", total_amount=499)
    payment = _payment(
        content_item_id=None,
        plan="annual",
        amount=499,
        payment_type="subscription",
    )
    assert not order_payment_matches_snapshot(order, payment)


def test_content_order_rejects_missing_content_item_on_payment():
    assert not order_payment_matches_snapshot(_order(), _payment(content_item_id=None))


def test_subscription_order_rejects_content_item_on_payment():
    order = _order(order_type="subscription", item_id=None, plan="semester", total_amount=499)
    payment = _payment(
        content_item_id=42,
        plan="semester",
        amount=499,
        payment_type="subscription",
    )
    assert not order_payment_matches_snapshot(order, payment)


def test_order_payment_match_requires_successful_payment():
    assert not order_payment_matches_snapshot(_order(), _payment(status="pending"))
