import json
import secrets
from datetime import datetime

from flask import jsonify, session
from sqlalchemy import text


ORDER_STATUSES = (
    "pending",
    "paid",
    "fulfilled",
    "failed",
    "refunded",
    "cancelled",
)


def order_payment_matches_snapshot(order_row, payment):
    """Return True only when a successful payment still matches its order."""
    expected_item_id = order_row["item_id"]
    payment_item_id = payment.content_item_id
    expected_plan = order_row["plan"]
    payment_plan = payment.plan
    expected_total = int(order_row["total_amount"])
    payment_amount = int(payment.amount or 0)
    expected_user_id = int(order_row["user_id"])
    payment_user_id = int(payment.user_id or 0)

    return not (
        expected_user_id != payment_user_id
        or expected_total != payment_amount
        or order_row["currency"] != "KES"
        or payment_item_id != expected_item_id
        or payment_plan != expected_plan
        or (
            order_row["order_type"] == "content"
            and (expected_item_id is None or payment.payment_type != "content")
        )
        or (
            order_row["order_type"] == "subscription"
            and (payment.payment_type != "subscription" or expected_item_id is not None)
        )
    )


def _order_number():
    # Human-readable support reference; database UNIQUE constraint is the
    # final collision guard.
    return f"PZA-ORD-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"


def register_student_orders(app, db, Payment, ContentItem, User, require_csrf=None):
    """Register the student order ledger and exact-fulfillment endpoints.

    The order is an immutable snapshot of what the student requested at
    checkout. Payment/provider records remain authoritative for money;
    this ledger is authoritative for the student's requested item and
    fulfillment state.
    """

    def create_order_for_payment(payment, *, item_title=None, requested_payload=None, checkout_url=None):
        if not payment or not payment.user_id:
            raise ValueError("A student order requires a user-owned payment")

        if payment.payment_type == "content":
            item = db.session.get(ContentItem, payment.content_item_id) if payment.content_item_id else None
            if not item:
                raise ValueError("Cannot create content order without a valid content item")
            order_type = "content"
            item_id = item.id
            title_snapshot = item_title or item.title
            plan = None
            quantity = 1
        elif payment.payment_type == "subscription":
            order_type = "subscription"
            item_id = None
            title_snapshot = item_title or ("Plus Plan" if payment.plan == "semester" else "Pro Plan")
            plan = payment.plan
            quantity = 1
        else:
            raise ValueError(f"Unsupported student order payment type: {payment.payment_type}")

        existing = db.session.execute(
            text("SELECT id, order_number FROM student_order WHERE payment_id = :payment_id"),
            {"payment_id": payment.id},
        ).mappings().first()
        if existing:
            return dict(existing)

        payload = requested_payload or {
            "payment_type": payment.payment_type,
            "content_item_id": payment.content_item_id,
            "plan": payment.plan,
            "quantity": quantity,
        }

        row = db.session.execute(
            text("""
                INSERT INTO student_order
                    (order_number, user_id, payment_id, order_type, item_id,
                     item_title_snapshot, plan, quantity, unit_amount,
                     total_amount, currency, requested_payload, checkout_url, status,
                     created_at, updated_at)
                VALUES
                    (:order_number, :user_id, :payment_id, :order_type, :item_id,
                     :title, :plan, :quantity, :unit_amount,
                     :total_amount, 'KES', CAST(:requested_payload AS jsonb), :checkout_url, 'pending',
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (payment_id) DO NOTHING
                RETURNING id, order_number
            """),
            {
                "order_number": _order_number(),
                "user_id": payment.user_id,
                "payment_id": payment.id,
                "order_type": order_type,
                "item_id": item_id,
                "title": title_snapshot,
                "plan": plan,
                "quantity": quantity,
                "unit_amount": payment.amount,
                "total_amount": payment.amount * quantity,
                "requested_payload": json.dumps(payload),
                "checkout_url": checkout_url,
            },
        ).mappings().first()

        if row:
            return dict(row)

        existing = db.session.execute(
            text("SELECT id, order_number FROM student_order WHERE payment_id = :payment_id"),
            {"payment_id": payment.id},
        ).mappings().first()
        return dict(existing) if existing else None

    def find_pending_checkout(user_id, *, content_item_id=None, plan=None):
        if content_item_id is not None:
            row = db.session.execute(
                text("""
                    SELECT o.order_number, o.checkout_url, p.reference
                    FROM student_order o
                    JOIN payment p ON p.id = o.payment_id
                    WHERE o.user_id = :user_id
                      AND o.item_id = :item_id
                      AND o.order_type = 'content'
                      AND o.currency = 'KES'
                      AND o.status = 'pending'
                      AND p.status = 'pending'
                    ORDER BY o.created_at DESC
                    LIMIT 1
                """), {"user_id": user_id, "item_id": content_item_id}
            ).mappings().first()
        else:
            row = db.session.execute(
                text("""
                    SELECT o.order_number, o.checkout_url, p.reference
                    FROM student_order o
                    JOIN payment p ON p.id = o.payment_id
                    WHERE o.user_id = :user_id
                      AND o.plan = :plan
                      AND o.order_type = 'subscription'
                      AND o.status = 'pending'
                      AND p.status = 'pending'
                    ORDER BY o.created_at DESC
                    LIMIT 1
                """), {"user_id": user_id, "plan": plan}
            ).mappings().first()
        return dict(row) if row else None

    def mark_order_paid_and_fulfilled(payment):
        if not payment:
            return False

        row = db.session.execute(
            text("SELECT * FROM student_order WHERE payment_id = :payment_id FOR UPDATE"),
            {"payment_id": payment.id},
        ).mappings().first()
        if not row:
            # A successful payment without an order is deliberately NOT
            # fulfilled. New checkouts must always have an order ledger row.
            return False

        if row["status"] in ("refunded", "cancelled", "failed"):
            # Never resurrect an order after a terminal state.
            return False

        # The order snapshot is the fulfillment authority. Never let mutable
        # Payment fields silently redirect a successful payment to a different
        # student, content item, plan, amount, or currency.
        if not order_payment_matches_snapshot(row, payment):
            payment.status = "failed"
            db.session.execute(
                text("""
                    UPDATE student_order
                    SET status = 'failed',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :order_id
                      AND status IN ('pending', 'paid', 'fulfilled')
                """),
                {"order_id": row["id"]},
            )
            return False

        # Fulfillment references the immutable order snapshot, not mutable
        # payment fields. This prevents later payment-row changes from
        # changing what the student actually purchased.
        fulfillment = {
            "payment_id": payment.id,
            "content_item_id": row["item_id"],
            "plan": row["plan"],
            "user_id": row["user_id"],
            "quantity": row["quantity"],
            "fulfilled_exactly_as_requested": True,
        }
        db.session.execute(
            text("""
                UPDATE student_order
                SET status = 'fulfilled',
                    paid_at = COALESCE(paid_at, CURRENT_TIMESTAMP),
                    fulfilled_at = COALESCE(fulfilled_at, CURRENT_TIMESTAMP),
                    fulfillment_payload = CAST(:payload AS jsonb),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :order_id
                  AND status IN ('pending', 'paid', 'fulfilled')
            """),
            {"order_id": row["id"], "payload": json.dumps(fulfillment)},
        )
        return True

    def mark_order_failed(payment_id):
        db.session.execute(
            text("""
                UPDATE student_order
                SET status = 'failed', updated_at = CURRENT_TIMESTAMP
                WHERE payment_id = :payment_id
                  AND status = 'pending'
            """),
            {"payment_id": payment_id},
        )

    def mark_order_refunded(payment_id):
        db.session.execute(
            text("""
                UPDATE student_order
                SET status = 'refunded',
                    refunded_at = COALESCE(refunded_at, CURRENT_TIMESTAMP),
                    updated_at = CURRENT_TIMESTAMP
                WHERE payment_id = :payment_id
                  AND status <> 'cancelled'
            """),
            {"payment_id": payment_id},
        )

    def serialize(row):
        if not row:
            return None
        def decode(value):
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except (TypeError, ValueError):
                    return value
            return value
        return {
            "id": row["id"],
            "order_number": row["order_number"],
            "payment_id": row["payment_id"],
            "order_type": row["order_type"],
            "item_id": row["item_id"],
            "item_title": row["item_title_snapshot"],
            "plan": row["plan"],
            "quantity": row["quantity"],
            "unit_amount": row["unit_amount"],
            "total_amount": row["total_amount"],
            "currency": row["currency"],
            "checkout_url": row["checkout_url"],
            "status": row["status"],
            "requested": decode(row["requested_payload"]),
            "fulfillment": decode(row["fulfillment_payload"]),
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "paid_at": row["paid_at"].isoformat() if row["paid_at"] else None,
            "fulfilled_at": row["fulfilled_at"].isoformat() if row["fulfilled_at"] else None,
            "refunded_at": row["refunded_at"].isoformat() if row["refunded_at"] else None,
        }

    @app.get("/orders")
    def student_orders():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        rows = db.session.execute(
            text("""
                SELECT *
                FROM student_order
                WHERE user_id = :user_id
                ORDER BY created_at DESC, id DESC
            """),
            {"user_id": user_id},
        ).mappings().all()
        return jsonify({"orders": [serialize(row) for row in rows]})

    @app.get("/orders/<int:order_id>")
    def student_order_detail(order_id):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        row = db.session.execute(
            text("""
                SELECT *
                FROM student_order
                WHERE id = :order_id AND user_id = :user_id
            """),
            {"order_id": order_id, "user_id": user_id},
        ).mappings().first()
        if not row:
            return jsonify({"error": "Order not found"}), 404
        return jsonify({"order": serialize(row)})

    # Expose helpers to the payment/refund routes without creating a second
    # module-level global API.
    app.extensions["prepza_student_orders"] = {
        "create": create_order_for_payment,
        "find_pending_checkout": find_pending_checkout,
        "mark_paid_and_fulfilled": mark_order_paid_and_fulfilled,
        "mark_failed": mark_order_failed,
        "mark_refunded": mark_order_refunded,
    }

    return app.extensions["prepza_student_orders"]
