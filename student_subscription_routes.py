"""Student-facing subscription plan, status and checkout routes.

This module owns the HTTP route layer only. Entitlement calculation,
Paystack verification, and subscription lifecycle policy remain in their
existing service/helper owners.
"""
from __future__ import annotations

import os
import secrets
from typing import Any

from flask import jsonify, request, session


def register_student_subscription_routes(
    app: Any,
    db: Any,
    *,
    User: Any,
    Payment: Any,
    limiter: Any,
    get_remote_address: Any,
    require_csrf: Any,
    get_user_subscription_status: Any,
    create_paystack_transaction: Any,
    student_order_helpers: Any,
) -> None:
    """Register the existing student plan, status and upgrade endpoints."""

    @app.route("/subscription/plans")
    def subscription_plans():
        # Student-facing subscription cards are sourced from the same
        # admin-configurable plan table used by entitlement enforcement.
        from ai_economics import get_plans
        plans = []
        for plan in get_plans(db):
            plans.append({
                "id": plan["plan_code"],
                "name": plan["display_name"],
                "price": int(plan["price_kes"]),
                "period": plan["billing_period"] if plan["plan_code"] != "free" else None,
                "quota_period": plan["quota_period"],
                "ada_monthly_units": int(plan["ada_monthly_units"]),
                "ada_daily_units": int(plan["ada_daily_units"]),
                "ada_max_output_tokens": int(plan["ada_max_output_tokens"]),
                "podcast_minutes": int(plan["podcast_minutes"]),
                "summary_pages": int(plan["summary_pages"]),
                "questions": int(plan["questions"]),
                "mind_map_nodes": int(plan["mind_map_nodes"]),
                "flashcards": int(plan["flashcards"]),
                "offline_study": True,
                "premium_library": bool(plan["premium_library"]),
                "study_hub_uploads": bool(plan["study_hub_uploads"]),
            })
        return jsonify({"plans": plans})

    @app.route("/subscription/status")
    def subscription_status():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        return jsonify(get_user_subscription_status(user_id))

    @app.route("/subscription/upgrade", methods=["POST"])
    @limiter.limit(
        "1 per 20 seconds",
        key_func=lambda: f"sub_upgrade:{session.get('user_id', get_remote_address())}",
    )
    @require_csrf
    def subscription_upgrade():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        data = request.get_json(silent=True) or {}
        plan = data.get("plan")
        if plan not in ("plus", "pro"):
            return jsonify({"error": "plan must be 'plus' or 'pro'"}), 400

        from ai_economics import get_plan
        plan_config = get_plan(db, plan)
        price = int(plan_config["price_kes"]) if plan_config else 0
        if price <= 0:
            return jsonify({"error": "This plan is not currently available"}), 400

        paystack_plan_code = os.environ.get(
            "PAYSTACK_PLUS_PLAN_CODE" if plan == "plus" else "PAYSTACK_PRO_PLAN_CODE"
        )
        if not paystack_plan_code:
            return jsonify({
                "error": "Recurring billing is not configured for this plan yet. "
                         "Admin must add the matching Paystack plan code."
            }), 503

        pending = student_order_helpers["find_pending_checkout"](user_id, plan=plan)
        if pending and pending.get("checkout_url"):
            return jsonify({
                "redirect_url": pending["checkout_url"],
                "reference": pending["reference"],
                "order_number": pending["order_number"],
                "recovered": True,
            })

        user = db.session.get(User, user_id)
        reference = f"PZA-sub-{plan}-{secrets.token_hex(6)}"

        plan_name = "Plus" if plan == "plus" else "Pro"
        try:
            provider_reference, authorization_url = create_paystack_transaction(
                reference, price, f"Prepza {plan_name} Plan", user,
                paystack_plan_code=paystack_plan_code,
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 502

        payment = Payment(
            user_id=user_id,
            content_item_id=None,
            phone_number=data.get("phone_number"),
            amount=price,
            provider="paystack",
            reference=reference,
            provider_reference=provider_reference,
            payment_type="subscription",
            plan=plan,
            status="pending",
        )
        db.session.add(payment)
        db.session.flush()
        student_order_helpers["create"](payment, item_title=("Plus Plan" if plan == "plus" else "Pro Plan"), checkout_url=authorization_url, requested_payload={
            "payment_type": "subscription",
            "plan": plan,
            "plan_name": "Plus" if plan == "plus" else "Pro",
            "quantity": 1,
        })
        db.session.commit()

        return jsonify({
            # Same alias reasoning as pay_for_content() in the Flask entry module.
            "redirect_url": authorization_url,
            "reference": reference,
        })
