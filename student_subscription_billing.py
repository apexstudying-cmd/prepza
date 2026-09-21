"""Student subscription lifecycle, recurring billing, refunds, and cancellation.

This module owns policy and lifecycle state; Paystack remains the payment
provider of record. Standard refunds are intentionally narrower than any
statutory consumer remedy: legal/exception review must remain possible.
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta
from decimal import Decimal
from flask import jsonify, request, session
from sqlalchemy import text


STANDARD_REFUND_STATUS = ("requested", "approved", "rejected", "paystack_pending",
                          "paystack_processing", "processed", "failed")
FEATURE_WEIGHTS = {
    "ada": Decimal("0.50"),
    "podcast": Decimal("0.15"),
    "summary": Decimal("0.10"),
    "quiz": Decimal("0.10"),
    "mind_map": Decimal("0.05"),
    "flashcards": Decimal("0.10"),
}
FEATURE_ALLOWANCE_KEYS = {
    "ada": "ada_monthly_units",
    "podcast": "podcast_minutes",
    "summary": "summary_pages",
    "quiz": "questions",
    "mind_map": "mind_map_nodes",
    "flashcards": "flashcards",
}


def _setting(db, key, default):
    row = db.session.execute(
        text("SELECT value FROM system_setting WHERE key=:key"),
        {"key": key},
    ).scalar_one_or_none()
    return row if row is not None else default


def _policy(db):
    try:
        window_hours = max(0, int(_setting(db, "student_refund_window_hours", "24")))
    except (TypeError, ValueError):
        window_hours = 24
    try:
        retention_pct = Decimal(str(_setting(db, "student_refund_retention_percent", "20")))
        retention_pct = max(Decimal("0"), min(Decimal("100"), retention_pct))
    except Exception:
        retention_pct = Decimal("20")
    full_zero_usage = str(_setting(db, "student_refund_full_zero_usage", "true")).lower() == "true"
    return window_hours, retention_pct, full_zero_usage


def _active_payment(db, user_id):
    return db.session.execute(text("""
        SELECT p.*
        FROM payment p
        JOIN student_order so ON so.payment_id=p.id
        WHERE p.user_id=:uid
          AND p.payment_type='subscription'
          AND p.status='success'
          AND so.status='fulfilled'
          AND p.subscription_expires_at IS NOT NULL
          AND p.subscription_expires_at > CURRENT_TIMESTAMP
        ORDER BY p.subscription_expires_at DESC, p.id DESC
        LIMIT 1
    """), {"uid": user_id}).mappings().first()


def _plan(db, plan_code):
    from ai_economics import get_plan
    return get_plan(db, plan_code)


def record_entitlement_usage(db, user_id, feature, units, payment_id=None, metadata=None):
    """Immutable evidence used for refund decisions and support/audit."""
    try:
        units = int(units)
    except (TypeError, ValueError):
        return False
    if units <= 0:
        return False
    if feature not in FEATURE_ALLOWANCE_KEYS:
        return False
    if payment_id is None:
        active = _active_payment(db, user_id)
        payment_id = active["id"] if active else None
    db.session.execute(text("""
        INSERT INTO student_entitlement_usage
            (user_id, payment_id, feature, units, request_count, metadata)
        VALUES (:uid,:pid,:feature,:units,1,CAST(:metadata AS jsonb))
    """), {
        "uid": user_id,
        "pid": payment_id,
        "feature": feature,
        "units": units,
        "metadata": __import__("json").dumps(metadata or {}),
    })
    db.session.commit()
    return True


def _consumption_breakdown(db, payment_row):
    plan = _plan(db, payment_row["plan"])
    if not plan:
        return {"consumed_value_kes": 0, "features": {}}

    rows = db.session.execute(text("""
        SELECT feature, COALESCE(SUM(units),0) AS units
        FROM student_entitlement_usage
        WHERE payment_id=:pid
        GROUP BY feature
    """), {"pid": payment_row["id"]}).mappings().all()

    consumed = {r["feature"]: int(r["units"] or 0) for r in rows}
    value = Decimal("0")
    details = {}
    for feature, weight in FEATURE_WEIGHTS.items():
        allowance = int(plan[FEATURE_ALLOWANCE_KEYS[feature]] or 0)
        used = consumed.get(feature, 0)
        ratio = Decimal("0") if allowance <= 0 else min(Decimal("1"), Decimal(used) / Decimal(allowance))
        allocated = (Decimal(payment_row["amount"]) * weight)
        feature_value = (allocated * ratio)
        value += feature_value
        details[feature] = {
            "used": used,
            "allowance": allowance,
            "ratio": float(ratio),
            "allocated_value_kes": float(allocated.quantize(Decimal("0.01"))),
            "consumed_value_kes": float(feature_value.quantize(Decimal("0.01"))),
        }

    return {
        "consumed_value_kes": int(value.to_integral_value(rounding="ROUND_CEILING")),
        "features": details,
    }


def calculate_refund_quote(db, payment_row, requested_at=None):
    """Return the published standard-policy quote for one paid subscription."""
    requested_at = requested_at or datetime.utcnow()
    window_hours, retention_pct, full_zero_usage = _policy(db)
    created_at = payment_row["created_at"] or requested_at
    age_seconds = max(0, (requested_at - created_at).total_seconds())
    within_window = age_seconds <= window_hours * 3600

    breakdown = _consumption_breakdown(db, payment_row)
    consumed_value = breakdown["consumed_value_kes"]
    amount = int(payment_row["amount"])
    if consumed_value == 0 and full_zero_usage:
        retention = 0
        refund = amount
    elif not within_window:
        retention = 0
        refund = 0
    else:
        retention = int(math.ceil(amount * float(retention_pct) / 100.0))
        refund = max(0, amount - consumed_value - retention)

    return {
        "eligible_standard": bool(within_window and (consumed_value == 0 or refund > 0)),
        "within_window": within_window,
        "window_hours": window_hours,
        "age_hours": round(age_seconds / 3600, 2),
        "consumed_value_kes": consumed_value,
        "retention_percent": float(retention_pct),
        "retention_amount_kes": retention,
        "refund_amount_kes": refund,
        "original_amount_kes": amount,
        "breakdown": breakdown["features"],
        "policy_note": (
            "Zero paid entitlement consumed qualifies for a full standard refund. "
            "If entitlement was consumed, the standard refund deducts the calculated "
            "consumed value and the published service-retention component."
        ),
    }


def _upsert_subscription(db, *, user_id, plan, plan_code=None, subscription_code=None,
                          email_token=None, customer_code=None, status=None,
                          next_payment_at=None, initial_payment_id=None, latest_payment_id=None):
    if not plan_code:
        plan_code = os.environ.get("PAYSTACK_PLUS_PLAN_CODE" if plan == "plus" else "PAYSTACK_PRO_PLAN_CODE")
    if not plan_code:
        return None
    existing = db.session.execute(text("""
        SELECT * FROM student_subscription
        WHERE user_id=:uid AND paystack_plan_code=:plan_code
        FOR UPDATE
    """), {"uid": user_id, "plan_code": plan_code}).mappings().first()
    if existing:
        db.session.execute(text("""
            UPDATE student_subscription
            SET paystack_subscription_code=COALESCE(:subscription_code,paystack_subscription_code),
                paystack_email_token=COALESCE(:email_token,paystack_email_token),
                paystack_customer_code=COALESCE(:customer_code,paystack_customer_code),
                status=COALESCE(:status,status),
                next_payment_at=COALESCE(:next_payment_at,next_payment_at),
                initial_payment_id=COALESCE(initial_payment_id,:initial_payment_id),
                latest_payment_id=COALESCE(:latest_payment_id,latest_payment_id),
                updated_at=CURRENT_TIMESTAMP
            WHERE id=:id
        """), {
            "id": existing["id"], "subscription_code": subscription_code,
            "email_token": email_token, "customer_code": customer_code,
            "status": status, "next_payment_at": next_payment_at,
            "initial_payment_id": initial_payment_id,
            "latest_payment_id": latest_payment_id,
        })
        return existing["id"]
    row = db.session.execute(text("""
        INSERT INTO student_subscription
            (user_id,plan,paystack_plan_code,paystack_subscription_code,
             paystack_email_token,paystack_customer_code,status,
             next_payment_at,initial_payment_id,latest_payment_id)
        VALUES (:uid,:plan,:plan_code,:subscription_code,:email_token,:customer_code,
                COALESCE(:status,'active'),:next_payment_at,:initial_payment_id,:latest_payment_id)
        RETURNING id
    """), {
        "uid": user_id, "plan": plan, "plan_code": plan_code,
        "subscription_code": subscription_code, "email_token": email_token,
        "customer_code": customer_code, "status": status,
        "next_payment_at": next_payment_at,
        "initial_payment_id": initial_payment_id, "latest_payment_id": latest_payment_id,
    }).scalar_one()
    return row


def handle_subscription_created(db, payload):
    data = payload.get("data") or {}
    customer = data.get("customer") or {}
    subscription_code = data.get("subscription_code")
    plan_data = data.get("plan") or {}
    plan_code = plan_data.get("plan_code") or data.get("plan_code")
    email = customer.get("email")
    if not subscription_code or not email:
        return False

    from app import User
    user = User.query.filter_by(email=email).first()
    if not user:
        return False
    local_plan = None
    if plan_code == os.environ.get("PAYSTACK_PLUS_PLAN_CODE"):
        local_plan = "plus"
    elif plan_code == os.environ.get("PAYSTACK_PRO_PLAN_CODE"):
        local_plan = "pro"
    if not local_plan:
        return False

    _upsert_subscription(
        db, user_id=user.id, plan=local_plan, plan_code=plan_code,
        subscription_code=subscription_code,
        email_token=data.get("email_token"),
        customer_code=customer.get("customer_code"),
        status=data.get("status") or "active",
        next_payment_at=data.get("next_payment_date"),
    )
    db.session.commit()
    return True


def handle_recurring_charge(db, payload):
    """Create the local payment/order for a successful automatic renewal."""
    data = payload.get("data") or {}
    subscription = data.get("subscription") or {}
    customer = data.get("customer") or {}
    subscription_code = subscription.get("subscription_code") or data.get("subscription_code")
    reference = data.get("reference") or (data.get("transaction") or {}).get("reference")
    if not subscription_code or not reference:
        return False

    local = db.session.execute(text("""
        SELECT * FROM student_subscription
        WHERE paystack_subscription_code=:code
        LIMIT 1
    """), {"code": subscription_code}).mappings().first()
    if not local:
        return False

    existing = db.session.execute(
        text("SELECT id FROM payment WHERE reference=:reference LIMIT 1"),
        {"reference": reference},
    ).scalar_one_or_none()
    if existing:
        return True

    amount_kes = int(data.get("amount") or (data.get("transaction") or {}).get("amount") or 0) // 100
    currency = (data.get("currency") or (data.get("transaction") or {}).get("currency") or "").upper()
    if currency != "KES" or amount_kes <= 0:
        return False

    from app import Payment
    payment = Payment(
        user_id=local["user_id"], content_item_id=None, amount=amount_kes,
        provider="paystack", reference=reference,
        provider_reference=str(data.get("id") or ""),
        payment_type="subscription", plan=local["plan"], status="success",
    )
    db.session.add(payment)
    db.session.flush()

    helpers = db.app.extensions["prepza_student_orders"] if hasattr(db, "app") else None
    if helpers is None:
        # Flask-SQLAlchemy does not expose app on db; import the Flask app.
        from app import _student_order_helpers
        helpers = _student_order_helpers

    helpers["create"](
        payment,
        item_title=("Plus Plan" if local["plan"] == "plus" else "Pro Plan"),
        requested_payload={
            "payment_type": "subscription",
            "plan": local["plan"],
            "renewal": True,
            "paystack_subscription_code": subscription_code,
            "quantity": 1,
        },
    )
    # Renewal starts a new paid entitlement month after the current expiry.
    from app import compute_new_subscription_expiry
    payment.subscription_expires_at = compute_new_subscription_expiry(local["user_id"], local["plan"])
    helpers["mark_paid_and_fulfilled"](payment)

    _upsert_subscription(
        db, user_id=local["user_id"], plan=local["plan"],
        plan_code=local["paystack_plan_code"],
        subscription_code=subscription_code,
        customer_code=customer.get("customer_code"),
        status="active", latest_payment_id=payment.id,
    )
    db.session.commit()
    return True


def handle_refund_webhook(db, event, payload):
    data = payload.get("data") or {}
    refund_id = data.get("id")
    transaction = data.get("transaction") or {}
    reference = transaction.get("reference") if isinstance(transaction, dict) else None
    if not reference:
        reference = data.get("reference")
    if not reference:
        return False

    payment_id = db.session.execute(
        text("SELECT id FROM payment WHERE reference=:reference LIMIT 1"),
        {"reference": reference},
    ).scalar_one_or_none()
    if not payment_id:
        return False

    mapping = {
        "refund.pending": "paystack_pending",
        "refund.processing": "paystack_processing",
        "refund.processed": "processed",
        "refund.failed": "failed",
    }
    status = mapping.get(event)
    if not status:
        return False

    db.session.execute(text("""
        UPDATE student_refund_request
        SET status=:status,
            paystack_refund_id=COALESCE(:refund_id,paystack_refund_id),
            paystack_status=:paystack_status,
            processed_at=CASE WHEN :status='processed' THEN CURRENT_TIMESTAMP ELSE processed_at END,
            updated_at=CURRENT_TIMESTAMP
        WHERE payment_id=:payment_id
    """), {
        "status": status, "refund_id": str(refund_id) if refund_id else None,
        "paystack_status": data.get("status"), "payment_id": payment_id,
    })
    if event == "refund.processed":
        db.session.execute(text("""
            UPDATE payment SET status='refunded' WHERE id=:pid
        """), {"pid": payment_id})
        db.session.execute(text("""
            UPDATE student_order
            SET status='refunded', refunded_at=COALESCE(refunded_at,CURRENT_TIMESTAMP),
                updated_at=CURRENT_TIMESTAMP
            WHERE payment_id=:pid AND status <> 'cancelled'
        """), {"pid": payment_id})
    db.session.commit()
    return True


def handle_subscription_webhook(db, event, payload):
    data = payload.get("data") or {}
    code = data.get("subscription_code")
    if not code and isinstance(data.get("subscription"), dict):
        code = data["subscription"].get("subscription_code")
    if not code:
        return False
    status = {
        "subscription.not_renew": "non-renewing",
        "subscription.disable": "disabled",
    }.get(event)
    if not status:
        return False
    db.session.execute(text("""
        UPDATE student_subscription
        SET status=:status,
            cancel_at_period_end=CASE WHEN :status='non-renewing' THEN TRUE ELSE cancel_at_period_end END,
            updated_at=CURRENT_TIMESTAMP
        WHERE paystack_subscription_code=:code
    """), {"status": status, "code": code})
    db.session.commit()
    return True


def register_student_subscription_billing(app, db, Payment, User, require_csrf, require_admin, paystack_request):
    from ai_economics import get_plan

    @app.get("/subscription/refund-quote")
    def subscription_refund_quote():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        payment = _active_payment(db, user_id)
        if not payment:
            return jsonify({"error": "No active paid subscription found"}), 404
        return jsonify(calculate_refund_quote(db, payment))

    @app.post("/subscription/refund-request")
    @require_csrf
    def subscription_refund_request():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        payment = _active_payment(db, user_id)
        if not payment:
            return jsonify({"error": "No active paid subscription found"}), 404

        existing = db.session.execute(
            text("SELECT status FROM student_refund_request WHERE payment_id=:pid"),
            {"pid": payment["id"]},
        ).scalar_one_or_none()
        if existing and existing not in ("rejected", "failed"):
            return jsonify({"error": "A refund request already exists for this payment", "status": existing}), 409

        quote = calculate_refund_quote(db, payment)
        if not quote["eligible_standard"]:
            return jsonify({
                "error": "This payment is not eligible for the standard refund policy.",
                "quote": quote,
            }), 400

        reason = ((request.get_json(silent=True) or {}).get("reason") or "").strip()[:500]
        db.session.execute(text("""
            INSERT INTO student_refund_request
                (payment_id,user_id,status,requested_amount,consumed_value_kes,
                 retention_amount_kes,reason)
            VALUES (:pid,:uid,'requested',:amount,:consumed,:retention,:reason)
            ON CONFLICT (payment_id) DO UPDATE SET
                status='requested',requested_at=CURRENT_TIMESTAMP,
                requested_amount=EXCLUDED.requested_amount,
                consumed_value_kes=EXCLUDED.consumed_value_kes,
                retention_amount_kes=EXCLUDED.retention_amount_kes,
                reason=EXCLUDED.reason,updated_at=CURRENT_TIMESTAMP
        """), {
            "pid": payment["id"], "uid": user_id,
            "amount": quote["refund_amount_kes"],
            "consumed": quote["consumed_value_kes"],
            "retention": quote["retention_amount_kes"],
            "reason": reason,
        })
        db.session.commit()
        return jsonify({"ok": True, "status": "requested", "quote": quote}), 201

    @app.post("/subscription/cancel")
    @require_csrf
    def subscription_cancel():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        row = db.session.execute(text("""
            SELECT * FROM student_subscription
            WHERE user_id=:uid AND status IN ('active','attention','non-renewing')
            ORDER BY id DESC LIMIT 1
        """), {"uid": user_id}).mappings().first()
        if not row:
            return jsonify({"error": "No Paystack recurring subscription is linked to this account"}), 404
        if row["cancel_at_period_end"]:
            return jsonify({"ok": True, "cancelled": True, "expires_at": row["current_period_end"]}), 200
        try:
            paystack_request("POST", "/subscription/disable", json={
                "code": row["paystack_subscription_code"],
                "token": row["paystack_email_token"],
            })
        except Exception as exc:
            return jsonify({"error": "Could not cancel recurring billing with Paystack", "detail": str(exc)}), 502
        db.session.execute(text("""
            UPDATE student_subscription
            SET cancel_at_period_end=TRUE,status='non-renewing',updated_at=CURRENT_TIMESTAMP
            WHERE id=:id
        """), {"id": row["id"]})
        db.session.commit()
        return jsonify({
            "ok": True,
            "cancelled": True,
            "access_until": row["current_period_end"],
            "message": "Renewal has been cancelled. Current paid access remains active until expiry.",
        })

    @app.get("/admin/subscription-refunds")
    @require_admin
    def admin_subscription_refunds():
        rows = db.session.execute(text("""
            SELECT r.*, p.reference, p.amount, p.plan, p.created_at AS payment_created_at,
                   u.email
            FROM student_refund_request r
            JOIN payment p ON p.id=r.payment_id
            JOIN "user" u ON u.id=r.user_id
            ORDER BY r.requested_at DESC LIMIT 100
        """)).mappings().all()
        return jsonify({"refunds": [dict(r) for r in rows]})

    @app.post("/admin/subscription-refunds/<int:refund_id>/execute")
    @require_csrf
    @require_admin
    def admin_execute_subscription_refund(refund_id):
        row = db.session.execute(text("""
            SELECT r.*, p.reference, p.amount, p.status AS payment_status,
                   p.provider_reference, p.plan, p.user_id
            FROM student_refund_request r
            JOIN payment p ON p.id=r.payment_id
            WHERE r.id=:id
            FOR UPDATE
        """), {"id": refund_id}).mappings().first()
        if not row:
            return jsonify({"error": "Refund request not found"}), 404
        if row["status"] not in ("requested", "approved"):
            return jsonify({"error": f"Refund is not executable from status {row['status']}"}), 400
        if row["payment_status"] != "success":
            return jsonify({"error": "Underlying payment is no longer refundable"}), 400

        payment = db.session.execute(text("""
            SELECT * FROM payment WHERE id=:pid FOR UPDATE
        """), {"pid": row["payment_id"]}).mappings().first()
        quote = calculate_refund_quote(db, payment)
        amount = int(row["approved_amount"] or quote["refund_amount_kes"])
        if amount <= 0 or amount > int(payment["amount"]):
            return jsonify({"error": "Calculated refund amount is invalid", "quote": quote}), 400

        try:
            result = paystack_request("POST", "/refund", json={
                "transaction": payment["reference"] or payment["provider_reference"],
                "amount": amount * 100,
                "currency": "KES",
                "customer_note": "Prepza subscription refund",
                "merchant_note": f"Prepza refund for payment {payment['id']}",
            })
        except Exception as exc:
            db.session.rollback()
            return jsonify({"error": "Paystack refund initiation failed", "detail": str(exc)}), 502

        data = result.get("data") or {}
        db.session.execute(text("""
            UPDATE student_refund_request
            SET status='paystack_pending', approved_amount=:amount,
                admin_user_id=:admin_id, admin_reason=:reason,
                paystack_refund_id=:refund_id, paystack_status=:paystack_status,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=:id
        """), {
            "id": refund_id, "amount": amount, "admin_id": session.get("user_id"),
            "reason": ((request.get_json(silent=True) or {}).get("reason") or "")[:500],
            "refund_id": str(data.get("id")) if data.get("id") else None,
            "paystack_status": data.get("status") or "pending",
        })
        # Do NOT mark the payment refunded yet. Paystack's webhook is the
        # authoritative confirmation that the processor actually processed it.
        db.session.commit()
        return jsonify({
            "ok": True,
            "status": "paystack_pending",
            "refund_amount_kes": amount,
            "paystack_status": data.get("status") or "pending",
        })

    return {
        "record_usage": record_entitlement_usage,
        "quote": calculate_refund_quote,
        "subscription_created": handle_subscription_created,
        "recurring_charge": handle_recurring_charge,
        "refund_webhook": handle_refund_webhook,
        "subscription_webhook": handle_subscription_webhook,
    }
