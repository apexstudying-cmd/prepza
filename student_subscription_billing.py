"""Student subscription lifecycle, recurring billing, refunds, and cancellation.

This module owns policy and lifecycle state; Paystack remains the payment
provider of record. Standard refunds are intentionally narrower than any
statutory consumer remedy: legal/exception review must remain possible.
"""

from __future__ import annotations

import math
import os
from datetime import datetime
from decimal import Decimal
from flask import jsonify, request, session
from sqlalchemy import text


def ensure_subscription_schema(db):
    """Idempotent safety net; the migration remains the deploy/audit artifact.

    The runtime application uses PostgreSQL. Realtime/security tests deliberately
    boot the Flask app against an in-memory SQLite database, so PostgreSQL-only
    DDL must not run during test-module import.
    """
    if db.engine.url.get_backend_name() == "sqlite":
        return
    # Payment period boundaries are part of the entitlement contract. Keep
    # this additive safety-net in sync with the deploy migration so an older
    # database cannot boot into code that references a missing column.
    db.session.execute(text("""
        ALTER TABLE payment
        ADD COLUMN IF NOT EXISTS subscription_starts_at TIMESTAMP NULL
    """))
    db.session.execute(text("""
        ALTER TABLE payment
        ADD COLUMN IF NOT EXISTS subscription_allowance_snapshot JSONB NULL
    """))
    # Backfill legacy successful subscription rows as independent
    # entitlement periods. Purchases may overlap; one payment must never
    # consume or extend another payment's entitlement period.
    db.session.execute(text("""
        UPDATE payment
        SET subscription_starts_at = COALESCE(created_at, CURRENT_TIMESTAMP)
        WHERE payment_type = 'subscription'
          AND status = 'success'
          AND subscription_expires_at IS NOT NULL
          AND subscription_starts_at IS NULL
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS student_subscription (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES "user"(id),
            plan VARCHAR(20) NOT NULL CHECK (plan IN ('plus','pro')),
            paystack_plan_code VARCHAR(80) NOT NULL,
            paystack_subscription_code VARCHAR(100) UNIQUE,
            paystack_email_token VARCHAR(200),
            paystack_customer_code VARCHAR(100),
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
            next_payment_at TIMESTAMP NULL,
            current_period_start TIMESTAMP NULL,
            current_period_end TIMESTAMP NULL,
            initial_payment_id INTEGER NULL REFERENCES payment(id),
            latest_payment_id INTEGER NULL REFERENCES payment(id),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, paystack_plan_code)
        )
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS student_entitlement_usage (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES "user"(id),
            payment_id INTEGER NULL REFERENCES payment(id),
            feature VARCHAR(40) NOT NULL,
            units BIGINT NOT NULL CHECK (units > 0),
            request_count INTEGER NOT NULL DEFAULT 1 CHECK (request_count > 0),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS student_refund_request (
            id BIGSERIAL PRIMARY KEY,
            payment_id INTEGER NOT NULL UNIQUE REFERENCES payment(id),
            user_id INTEGER NOT NULL REFERENCES "user"(id),
            requested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(30) NOT NULL DEFAULT 'requested',
            requested_amount INTEGER NULL,
            approved_amount INTEGER NULL,
            consumed_value_kes INTEGER NOT NULL DEFAULT 0,
            retention_amount_kes INTEGER NOT NULL DEFAULT 0,
            reason VARCHAR(500),
            admin_user_id INTEGER NULL REFERENCES "user"(id),
            admin_reason VARCHAR(500),
            paystack_refund_id VARCHAR(100),
            paystack_status VARCHAR(30),
            paystack_transaction_reference VARCHAR(120),
            paystack_refund_reference VARCHAR(120),
            provider_message VARCHAR(500),
            processed_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_student_subscription_user_status ON student_subscription(user_id,status)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_student_entitlement_usage_payment ON student_entitlement_usage(payment_id,created_at)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_student_entitlement_usage_user_created ON student_entitlement_usage(user_id,created_at)"))
    db.session.execute(text("ALTER TABLE student_refund_request ADD COLUMN IF NOT EXISTS paystack_transaction_reference VARCHAR(120)"))
    db.session.execute(text("ALTER TABLE student_refund_request ADD COLUMN IF NOT EXISTS paystack_refund_reference VARCHAR(120)"))
    db.session.execute(text("ALTER TABLE student_refund_request ADD COLUMN IF NOT EXISTS provider_message VARCHAR(500)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_student_refund_request_user ON student_refund_request(user_id,requested_at)"))
    db.session.execute(text("""
        INSERT INTO system_setting(key,value) VALUES
          ('student_refund_window_hours','24'),
          ('student_refund_retention_percent','20'),
          ('student_refund_full_zero_usage','true')
        ON CONFLICT(key) DO NOTHING
    """))
    db.session.commit()


STANDARD_REFUND_STATUS = ("requested", "approved", "rejected", "paystack_pending",
                          "paystack_processing", "needs_attention", "processed", "failed")
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


def _active_payment(db, user_id, payment_id=None, plan=None):
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
          AND (:payment_id IS NULL OR p.id=:payment_id)
          AND (:plan IS NULL OR p.plan=:plan)
        ORDER BY p.subscription_starts_at DESC NULLS LAST, p.id DESC
        LIMIT 1
    """), {"uid": user_id, "payment_id": payment_id, "plan": plan}).mappings().first()


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
    plan = payment_row.get("subscription_allowance_snapshot") if hasattr(payment_row, "get") else None
    if not plan:
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
    if not within_window:
        retention = 0
        refund = 0
    elif consumed_value == 0 and full_zero_usage:
        retention = 0
        refund = amount
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

    initial_payment_id = db.session.execute(text("""
        SELECT id FROM payment
        WHERE user_id=:uid AND payment_type='subscription'
          AND plan=:plan AND status='success'
        ORDER BY id DESC LIMIT 1
    """), {"uid": user.id, "plan": local_plan}).scalar_one_or_none()
    _upsert_subscription(
        db, user_id=user.id, plan=local_plan, plan_code=plan_code,
        subscription_code=subscription_code,
        email_token=data.get("email_token"),
        customer_code=customer.get("customer_code"),
        status=data.get("status") or "active",
        next_payment_at=data.get("next_payment_date"),
        initial_payment_id=initial_payment_id,
        latest_payment_id=initial_payment_id,
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
    if not reference:
        return False

    local = None
    if subscription_code:
        local = db.session.execute(text("""
            SELECT * FROM student_subscription
            WHERE paystack_subscription_code=:code
            LIMIT 1
        """), {"code": subscription_code}).mappings().first()
    if not local:
        customer_code = customer.get("customer_code")
        if customer_code:
            local = db.session.execute(text("""
                SELECT * FROM student_subscription
                WHERE paystack_customer_code=:customer_code
                  AND status IN ('active','non-renewing','attention')
                ORDER BY id DESC LIMIT 1
            """), {"customer_code": customer_code}).mappings().first()
    if not local:
        return False

    existing = db.session.execute(
        text("SELECT id FROM payment WHERE reference=:reference LIMIT 1"),
        {"reference": reference},
    ).scalar_one_or_none()
    if existing:
        return True

    raw_amount = data.get("amount") or (data.get("transaction") or {}).get("amount")
    currency = (data.get("currency") or (data.get("transaction") or {}).get("currency") or "").upper()
    if currency != "KES" or raw_amount is None:
        return False
    try:
        amount_kobo = int(raw_amount)
    except (TypeError, ValueError):
        return False
    if amount_kobo <= 0 or amount_kobo % 100 != 0:
        return False
    amount_kes = amount_kobo // 100

    # Never let a signed provider webhook silently create a subscription at
    # the wrong price. The local economics config and the Paystack plan must
    # agree before a renewal can extend access.
    plan = _plan(db, local["plan"])
    expected_amount = int((plan or {}).get("price_kes") or 0)
    if expected_amount <= 0 or amount_kes != expected_amount:
        return False

    from app import Payment
    # The reference is the provider's transaction identity. Two webhook
    # deliveries can race: both may observe no row before one commits.
    # Flush inside a narrow IntegrityError guard so the losing delivery
    # becomes an idempotent no-op instead of returning a webhook 500.
    from sqlalchemy.exc import IntegrityError
    payment = Payment(
        user_id=local["user_id"], content_item_id=None, amount=amount_kes,
        provider="paystack", reference=reference,
        provider_reference=str(data.get("id") or ""),
        payment_type="subscription", plan=local["plan"], status="success",
    )
    db.session.add(payment)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        duplicate = db.session.execute(
            text("SELECT id FROM payment WHERE reference=:reference LIMIT 1"),
            {"reference": reference},
        ).scalar_one_or_none()
        if duplicate:
            return True
        raise

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
    # Each successful renewal creates its own independent paid entitlement month.
    from app import compute_new_subscription_expiry
    from app import compute_new_subscription_period
    starts_at, expires_at = compute_new_subscription_period(local["user_id"], local["plan"])
    payment.subscription_starts_at = starts_at
    payment.subscription_expires_at = expires_at
    from app import _subscription_allowance_snapshot
    payment.subscription_allowance_snapshot = _subscription_allowance_snapshot(payment.plan)
    fulfilled = helpers["mark_paid_and_fulfilled"](payment)
    if not fulfilled:
        # The provider charge is already successful. Do NOT roll it back locally:
        # doing so would erase the money trail needed for reconciliation/refund
        # handling. The order remains failed and the successful payment stays
        # visible for manual recovery.
        db.session.commit()
        return False

    _upsert_subscription(
        db, user_id=local["user_id"], plan=local["plan"],
        plan_code=local["paystack_plan_code"],
        subscription_code=subscription_code,
        customer_code=customer.get("customer_code"),
        status="active", latest_payment_id=payment.id,
    )
    db.session.commit()
    return True


def _refund_transaction_reference(data):
    """Extract the canonical Paystack transaction reference from refund webhooks."""
    transaction_reference = data.get("transaction_reference")
    if transaction_reference:
        return transaction_reference
    transaction = data.get("transaction") or {}
    if isinstance(transaction, dict) and transaction.get("reference"):
        return transaction["reference"]
    return data.get("reference")


def handle_refund_webhook(db, event, payload):
    data = payload.get("data") or {}
    refund_id = data.get("id")
    reference = _refund_transaction_reference(data)
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
        "refund.needs-attention": "needs_attention",
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
            paystack_transaction_reference=COALESCE(:transaction_reference,paystack_transaction_reference),
            paystack_refund_reference=COALESCE(:refund_reference,paystack_refund_reference),
            provider_message=COALESCE(:provider_message,provider_message),
            processed_at=CASE WHEN :status='processed' THEN CURRENT_TIMESTAMP ELSE processed_at END,
            updated_at=CURRENT_TIMESTAMP
        WHERE payment_id=:payment_id
    """), {
        "status": status,
        "refund_id": str(refund_id) if refund_id else None,
        "paystack_status": data.get("status"),
        "transaction_reference": reference,
        "refund_reference": data.get("refund_reference") or data.get("reference"),
        "provider_message": data.get("message") or data.get("failure_reason"),
        "payment_id": payment_id,
    })
    # The webhook route does not own a transaction commit. Persist the
    # provider-state transition immediately so pending/processing/failed
    # refund events cannot disappear when the request ends.
    db.session.commit()

    if event == "refund.processed":
        # A provider-confirmed processed refund revokes the entitlement tied
        # to that payment. Keep unexpected amount differences visible for
        # manual reconciliation, but do not restore paid access.
        expected_amount = db.session.execute(text("""
            SELECT approved_amount
            FROM student_refund_request
            WHERE payment_id=:pid
        """), {"pid": payment_id}).scalar_one_or_none()
        provider_amount = data.get("amount")
        amount_mismatch = False
        if expected_amount is not None and provider_amount is not None:
            try:
                amount_mismatch = int(provider_amount) != int(expected_amount) * 100
            except (TypeError, ValueError):
                amount_mismatch = True
        if amount_mismatch:
            db.session.execute(text("""
                UPDATE student_refund_request
                SET status='needs_attention',
                    provider_message=COALESCE(provider_message,'Processed refund amount did not match the approved amount'),
                    updated_at=CURRENT_TIMESTAMP
                WHERE payment_id=:pid
            """), {"pid": payment_id})
            # Paystack has nevertheless confirmed that money was refunded.
            # Entitlement must therefore be revoked; the amount discrepancy
            # remains an admin reconciliation issue, not an access grant.
        # Any processed refund revokes the entitlement created by the
        # refunded payment. This is intentional: the customer no longer
        # retains the paid subscription purchased with refunded money.
        #
        # If older paid subscription periods exist, recomputation restores
        # access only from those non-refunded payments. Thus:
        #   current payment refunded -> current access removed
        #   earlier payment still valid -> access falls back to that period
        db.session.execute(text("""
            UPDATE payment
            SET status = 'refunded'
            WHERE id=:pid
        """), {"pid": payment_id})

        db.session.execute(text("""
            UPDATE student_order
            SET status='refunded',
                refunded_at=COALESCE(refunded_at,CURRENT_TIMESTAMP),
                updated_at=CURRENT_TIMESTAMP
            WHERE payment_id=:pid AND status <> 'cancelled'
        """), {"pid": payment_id})

        # If this payment earned an ambassador commission, void the
        # commission when it has not yet been bundled into a payout. A refund
        # must not leave an earned-but-unfunded referral commission payable.
        from app import Referral
        db.session.execute(text("""
            UPDATE referral
            SET voided_at=COALESCE(voided_at,CURRENT_TIMESTAMP),
                void_reason=COALESCE(void_reason,'Qualifying payment refunded'),
                updated_at=CURRENT_TIMESTAMP
            WHERE first_payment_id=:pid
              AND payout_id IS NULL
              AND voided_at IS NULL
        """), {"pid": payment_id})

        # Full or partial refund: rebuild paid subscription expiry from
        # remaining non-refunded subscription payments. A partial refund
        # therefore also removes the entitlement tied to this purchase.
        from app import recompute_subscription_expiries
        payment_type_user = db.session.execute(text("""
            SELECT payment_type,user_id FROM payment WHERE id=:pid
        """), {"pid": payment_id}).mappings().first()
        if payment_type_user and payment_type_user["payment_type"] == "subscription":
            recompute_subscription_expiries(payment_type_user["user_id"])

        db.session.commit()
        return True

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
    ensure_subscription_schema(db)
    from ai_economics import get_plan

    @app.get("/subscription/refund-policy")
    def subscription_refund_policy():
        window_hours, retention_pct, full_zero_usage = _policy(db)
        return jsonify({
            "standard_window_hours": window_hours,
            "full_refund_if_zero_usage": full_zero_usage,
            "retention_percent_after_usage": float(retention_pct),
            "currency": "KES",
            "summary": (
                "Within the standard refund window, zero paid entitlement consumed "
                "qualifies for a full refund. If paid entitlement was consumed, the "
                "standard refund deducts the calculated consumed value plus the "
                "published service-retention component. Statutory or exceptional "
                "refund rights are not removed by this standard policy."
            ),
        })

    @app.get("/subscription/refund-quote")
    def subscription_refund_quote():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        requested_payment_id = request.args.get("payment_id", type=int)
        requested_plan = request.args.get("plan")
        if requested_plan not in (None, "plus", "pro"):
            return jsonify({"error": "Invalid subscription plan"}), 400
        payment = _active_payment(db, user_id, requested_payment_id, requested_plan)
        if not payment:
            return jsonify({"error": "No active paid subscription found for the requested entitlement"}), 404
        return jsonify(calculate_refund_quote(db, payment))

    @app.post("/subscription/refund-request")
    @require_csrf
    def subscription_refund_request():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        payload = request.get_json(silent=True) or {}
        requested_payment_id = payload.get("payment_id")
        requested_plan = payload.get("plan")
        try:
            requested_payment_id = int(requested_payment_id) if requested_payment_id is not None else None
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid payment_id"}), 400
        if requested_plan not in (None, "plus", "pro"):
            return jsonify({"error": "Invalid subscription plan"}), 400
        payment = _active_payment(db, user_id, requested_payment_id, requested_plan)
        if not payment:
            return jsonify({"error": "No active paid subscription found for the requested entitlement"}), 404

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
        payload = request.get_json(silent=True) or {}
        requested_plan = payload.get("plan")
        if requested_plan not in (None, "plus", "pro"):
            return jsonify({"error": "Invalid subscription plan"}), 400
        row = db.session.execute(text("""
            SELECT * FROM student_subscription
            WHERE user_id=:uid AND status IN ('active','attention','non-renewing')
              AND (:plan IS NULL OR plan=:plan)
            ORDER BY CASE WHEN :plan IS NOT NULL THEN 0 ELSE 1 END, id DESC
            LIMIT 1
        """), {"uid": user_id, "plan": requested_plan}).mappings().first()
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
        active_expiry = db.session.execute(text("""
            SELECT p.subscription_expires_at
            FROM payment p
            WHERE p.user_id=:uid
              AND p.payment_type='subscription'
              AND p.plan=:plan
              AND p.status='success'
              AND p.subscription_expires_at > CURRENT_TIMESTAMP
            ORDER BY p.subscription_starts_at DESC NULLS LAST, p.id DESC
            LIMIT 1
        """), {"uid": user_id, "plan": row["plan"]}).scalar_one_or_none()
        db.session.execute(text("""
            UPDATE student_subscription
            SET cancel_at_period_end=TRUE,status='non-renewing',
                current_period_end=:period_end,updated_at=CURRENT_TIMESTAMP
            WHERE id=:id
        """), {"id": row["id"], "period_end": active_expiry})
        db.session.commit()
        return jsonify({
            "ok": True,
            "cancelled": True,
            "access_until": active_expiry.isoformat() if active_expiry else None,
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

    def _reconcile_paystack_refund(refund_row):
        """Reconcile a provider refund before any retry so a delayed webhook cannot cause a second refund."""
        provider_refund_id = refund_row.get("paystack_refund_id")
        if not provider_refund_id:
            return None
        provider = paystack_request("GET", f"/refund/{provider_refund_id}")
        data = provider.get("data") or {}
        status = str(data.get("status") or "").lower()
        event = {
            "pending": "refund.pending",
            "processing": "refund.processing",
            "needs-attention": "refund.needs-attention",
            "failed": "refund.failed",
            "processed": "refund.processed",
        }.get(status)
        if not event:
            return status or None
        payload = {
            "data": {
                **data,
                "id": data.get("id") or provider_refund_id,
                "transaction_reference": refund_row.get("reference"),
                "refund_reference": data.get("refund_reference") or data.get("reference"),
            }
        }
        handle_refund_webhook(db, event, payload)
        return status


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
        if row["status"] not in ("requested", "approved", "failed"):
            return jsonify({"error": f"Refund is not executable from status {row['status']}"}), 400
        if row["status"] == "failed" and row["paystack_refund_id"]:
            try:
                provider_status = _reconcile_paystack_refund(row)
            except Exception as exc:
                db.session.rollback()
                return jsonify({"error": "Could not reconcile the previous Paystack refund before retry", "detail": str(exc)}), 502
            if provider_status and provider_status != "failed":
                db.session.commit()
                return jsonify({"ok": True, "status": provider_status, "message": "Provider status was reconciled; no new refund was created."}), 200
        if row["payment_status"] != "success":
            return jsonify({"error": "Underlying payment is no longer refundable"}), 400

        payment = db.session.execute(text("""
            SELECT * FROM payment WHERE id=:pid FOR UPDATE
        """), {"pid": row["payment_id"]}).mappings().first()
        quote = calculate_refund_quote(db, payment)
        amount = int(row["approved_amount"] or quote["refund_amount_kes"])
        if amount <= 0 or amount > int(payment["amount"]):
            return jsonify({"error": "Calculated refund amount is invalid", "quote": quote}), 400

        # A refund must never leave a recurring subscription capable of
        # charging the student again. Disable renewal before initiating the
        # refund; current paid access is separately revoked only when the
        # refund is actually processed.
        recurring = db.session.execute(text("""
            SELECT * FROM student_subscription
            WHERE user_id=:uid AND plan=:plan AND status IN ('active','attention')
            ORDER BY id DESC LIMIT 1
        """), {"uid": payment["user_id"], "plan": payment["plan"]}).mappings().first()
        if recurring and recurring["paystack_subscription_code"]:
            try:
                paystack_request("POST", "/subscription/disable", json={
                    "code": recurring["paystack_subscription_code"],
                    "token": recurring["paystack_email_token"],
                })
            except Exception as exc:
                db.session.rollback()
                return jsonify({
                    "error": "Could not stop recurring renewal before refund",
                    "detail": str(exc),
                }), 502
            db.session.execute(text("""
                UPDATE student_subscription
                SET cancel_at_period_end=TRUE,status='non-renewing',
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=:id
            """), {"id": recurring["id"]})

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
                paystack_transaction_reference=:transaction_reference,
                paystack_refund_reference=:refund_reference,
                provider_message=:provider_message,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=:id
        """), {
            "id": refund_id, "amount": amount, "admin_id": session.get("user_id"),
            "reason": ((request.get_json(silent=True) or {}).get("reason") or "")[:500],
            "refund_id": str(data.get("id")) if data.get("id") else None,
            "paystack_status": data.get("status") or "pending",
            "transaction_reference": payment["reference"],
            "refund_reference": data.get("refund_reference") or data.get("reference"),
            "provider_message": data.get("message") or data.get("failure_reason"),
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
