"""Browser-return route for Paystack-hosted checkout.

This route is deliberately limited to the user-facing redirect. The signed
webhook in app.py remains the authoritative payment event processor.
"""
from __future__ import annotations

from typing import Any, Callable

from flask import redirect, request


def register_paystack_callback_route(
    app: Any,
    sync_paystack_payment_status: Callable[[str], Any],
) -> None:
    """Register the existing best-effort Paystack browser callback."""

    @app.route("/payment/paystack/callback")
    def paystack_callback():
        reference = request.args.get("reference") or request.args.get("trxref")
        status = "error"
        if reference:
            try:
                payment = sync_paystack_payment_status(reference)
                status = payment.status if payment else "error"
            except Exception as exc:
                print("Paystack callback sync error:", str(exc))

        return redirect(f"/?payment_status={status}")
