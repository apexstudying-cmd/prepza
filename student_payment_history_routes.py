"""Student payment-history route.

The endpoint retains the existing session authentication and subscription/add-on
history query. Registration is injected so the Flask entry point stays small.
"""
from __future__ import annotations

from typing import Any

from flask import jsonify, session


def register_student_payment_history_route(app: Any, Payment: Any) -> None:
    """Register the existing student payment-history endpoint."""
    @app.route("/payment-history")
    def payment_history():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        # Student billing is subscription-first. Individual content purchases are
        # legacy and must not appear as current student transactions. Keep the
        # endpoint ready for future usage/add-on payments without reviving content
        # ownership as a product model.
        payments = (
            Payment.query.filter(
                Payment.user_id == user_id,
                Payment.payment_type.in_(( "subscription", "addon" )),
            )
            .order_by(Payment.created_at.desc())
            .all()
        )

        result = []
        for p in payments:
            result.append({
                "id": p.id,
                "payment_type": p.payment_type,
                "content_title": None,
                "plan": p.plan,
                "amount": p.amount,
                "status": p.status,
                "provider": p.provider,
                "reference": p.reference,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            })

        return jsonify({"payments": result})
