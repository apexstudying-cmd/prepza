"""Student-facing ambassador and referral routes.

Dependencies are injected by the application route registry so this module
does not import the Flask entry point or own application-wide state.
"""
from __future__ import annotations

import re
from datetime import datetime

from flask import Response, jsonify, request, session
from sqlalchemy import func


def register_ambassador_routes(
    app,
    db,
    *,
    User,
    Ambassador,
    Referral,
    AmbassadorPayout,
    limiter,
    require_csrf,
    base_url,
    get_ambassador_settings,
    compute_ambassador_tier,
    generate_referral_code,
) -> None:
    """Register the existing ambassador endpoints at their original startup point."""
    AMBASSADOR_PAYOUT_DESTINATION_REGEX = re.compile(r"^\+?\d{9,15}$")


    def _serialize_ambassador_referral(referral):
        return {
            "id": referral.id,
            "status": referral.status,
            "channel": referral.channel,
            "verified_at": referral.verified_at.isoformat() if referral.verified_at else None,
            "activated_at": referral.activated_at.isoformat() if referral.activated_at else None,
            "converted": referral.first_payment_id is not None,
            "first_payment_at": referral.first_payment_at.isoformat() if referral.first_payment_at else None,
            "commission_rate_applied": referral.commission_rate_applied,
            "commission_amount": referral.commission_amount,
            "unlock_at": referral.unlock_at.isoformat() if referral.unlock_at else None,
            "voided": referral.voided_at is not None,
            "payout_id": referral.payout_id,
            "created_at": referral.created_at.isoformat() if referral.created_at else None,
        }


    def _generate_unique_referral_code(display_name):
        for _ in range(10):
            code = generate_referral_code(display_name)
            if not Ambassador.query.filter_by(referral_code=code).first():
                return code
        raise RuntimeError("Could not generate a unique referral code after 10 attempts")


    @app.route("/ambassador/apply", methods=["POST"])
    @limiter.limit("5 per hour")
    @require_csrf
    def ambassador_apply():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        settings = get_ambassador_settings()
        if not settings["enabled"]:
            return jsonify({"error": "The ambassador program is not currently accepting applications"}), 503

        user = db.session.get(User, user_id)
        existing = Ambassador.query.filter_by(user_id=user_id).first()

        if existing:
            if existing.status in ("pending", "active"):
                return jsonify({"error": f"You already have a {existing.status} ambassador application"}), 409
            if existing.status == "suspended":
                return jsonify({"error": "Your ambassador account is suspended - contact support to be reinstated"}), 403
            # rejected -> reset back to pending rather than creating a duplicate
            # row, keeping the referral_code stable if it was ever shared.
            existing.status = "pending"
            existing.applied_at = datetime.utcnow()
            existing.rejection_reason = None
            existing.reviewed_by = None
            existing.reviewed_at = None
            db.session.commit()
            return jsonify({
                "id": existing.id, "status": existing.status, "referral_code": existing.referral_code,
            }), 200

        referral_code = _generate_unique_referral_code(user.display_name)
        ambassador = Ambassador(user_id=user_id, referral_code=referral_code, status="pending")
        db.session.add(ambassador)
        db.session.commit()

        return jsonify({
            "id": ambassador.id, "status": ambassador.status, "referral_code": ambassador.referral_code,
        }), 201


    @app.route("/ambassador/status")
    def ambassador_status():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        ambassador = Ambassador.query.filter_by(user_id=user_id).first()
        if not ambassador:
            return jsonify({"enrolled": False})

        return jsonify({
            "enrolled": True,
            "status": ambassador.status,
            "referral_code": ambassador.referral_code,
            "applied_at": ambassador.applied_at.isoformat() if ambassador.applied_at else None,
            "rejection_reason": ambassador.rejection_reason if ambassador.status == "rejected" else None,
        })


    @app.route("/ambassador/dashboard")
    def ambassador_dashboard():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        ambassador = Ambassador.query.filter_by(user_id=user_id).first()
        if not ambassador or ambassador.status not in ("active", "suspended"):
            return jsonify({"error": "You are not an active ambassador"}), 403

        referrals = Referral.query.filter_by(ambassador_id=ambassador.id).all()
        referred_count = len(referrals)
        verified_count = sum(1 for r in referrals if r.status in ("verified", "activated"))
        activated_count = sum(1 for r in referrals if r.status == "activated")
        converted = [r for r in referrals if r.first_payment_id and not r.voided_at]
        paying_count = len(converted)
        conversion_rate = round((paying_count / referred_count) * 100, 1) if referred_count else 0.0

        now = datetime.utcnow()
        pending_amount = sum(
            (r.commission_amount or 0) for r in converted
            if r.payout_id is None and r.unlock_at and r.unlock_at > now
        )
        available_amount = sum(
            (r.commission_amount or 0) for r in converted
            if r.payout_id is None and r.unlock_at and r.unlock_at <= now
        )
        paid_amount = db.session.query(func.coalesce(func.sum(AmbassadorPayout.amount), 0)).filter(
            AmbassadorPayout.ambassador_id == ambassador.id, AmbassadorPayout.status == "paid",
        ).scalar()

        settings = get_ambassador_settings()
        current_tier, current_pct = compute_ambassador_tier(paying_count, settings)
        next_threshold = (
            settings["tier2_threshold"] if current_tier == 1
            else settings["tier3_threshold"] if current_tier == 2
            else None
        )

        return jsonify({
            "referral_code": ambassador.referral_code,
            "referral_link": f"{base_url}/signup?ref={ambassador.referral_code}",
            "status": ambassador.status,
            "tier": current_tier,
            "commission_pct": current_pct,
            "next_tier_at": next_threshold,
            "funnel": {
                "referred": referred_count,
                "verified": verified_count,
                "activated": activated_count,
                "paying": paying_count,
                "conversion_rate": conversion_rate,
            },
            "earnings": {
                "pending_kes": pending_amount,
                "available_kes": available_amount,
                "paid_kes": paid_amount,
            },
            "min_payout_kes": settings["min_payout_kes"],
            "payout_hold_days": settings["payout_hold_days"],
        })


    @app.route("/ambassador/referral-qr")
    def ambassador_referral_qr():
        """Return the logged-in active ambassador's referral link as a self-contained SVG QR."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        ambassador = Ambassador.query.filter_by(user_id=user_id).first()
        if not ambassador or ambassador.status not in ("active", "suspended"):
            return jsonify({"error": "You are not an active ambassador"}), 403

        referral_link = f"{base_url}/signup?ref={ambassador.referral_code}&via=qr"
        import qrcode
        from qrcode.image.svg import SvgPathImage
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
        qr.add_data(referral_link)
        qr.make(fit=True)
        image = qr.make_image(image_factory=SvgPathImage)
        svg = image.to_string()
        return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "private, max-age=300"})


    @app.route("/ambassador/referrals")
    def ambassador_referrals():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        ambassador = Ambassador.query.filter_by(user_id=user_id).first()
        if not ambassador:
            return jsonify({"error": "You are not enrolled in the ambassador program"}), 403

        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        per_page = 20

        referrals = (
            Referral.query.filter_by(ambassador_id=ambassador.id)
            .order_by(Referral.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        return jsonify({"page": page, "referrals": [_serialize_ambassador_referral(r) for r in referrals]})


    @app.route("/ambassador/payouts")
    def ambassador_payouts():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        ambassador = Ambassador.query.filter_by(user_id=user_id).first()
        if not ambassador:
            return jsonify({"error": "You are not enrolled in the ambassador program"}), 403

        payouts = (
            AmbassadorPayout.query.filter_by(ambassador_id=ambassador.id)
            .order_by(AmbassadorPayout.requested_at.desc())
            .all()
        )

        return jsonify({"payouts": [
            {
                "id": p.id,
                "amount": p.amount,
                "status": p.status,
                "payout_destination": p.payout_destination,
                "requested_at": p.requested_at.isoformat() if p.requested_at else None,
                "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
                "rejection_reason": p.rejection_reason,
                "paid_at": p.paid_at.isoformat() if p.paid_at else None,
            }
            for p in payouts
        ]})


    @app.route("/ambassador/payouts/request", methods=["POST"])
    @limiter.limit("5 per hour")
    @require_csrf
    def ambassador_request_payout():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        ambassador = Ambassador.query.filter_by(user_id=user_id).first()
        if not ambassador or ambassador.status != "active":
            return jsonify({"error": "You are not an active ambassador"}), 403

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Request body must be valid JSON"}), 400

        payout_destination = (data.get("payout_destination") or "").strip()
        if not AMBASSADOR_PAYOUT_DESTINATION_REGEX.match(payout_destination):
            return jsonify({"error": "payout_destination must be a valid phone number"}), 400

        recipient_first_name = (data.get("recipient_first_name") or "").strip()
        recipient_last_name = (data.get("recipient_last_name") or "").strip()
        if not recipient_first_name or len(recipient_first_name) > 100:
            return jsonify({"error": "recipient_first_name is required and must be 100 characters or fewer"}), 400
        if not recipient_last_name or len(recipient_last_name) > 100:
            return jsonify({"error": "recipient_last_name is required and must be 100 characters or fewer"}), 400

        # An existing pending/approved request already in flight - don't let
        # a student stack multiple requests before the last one is resolved.
        in_flight = AmbassadorPayout.query.filter(
            AmbassadorPayout.ambassador_id == ambassador.id,
            AmbassadorPayout.status.in_(("pending", "approved")),
        ).first()
        if in_flight:
            return jsonify({"error": f"You already have a payout request {in_flight.status}"}), 409

        now = datetime.utcnow()
        eligible = Referral.query.filter(
            Referral.ambassador_id == ambassador.id,
            Referral.first_payment_id.isnot(None),
            Referral.voided_at.is_(None),
            Referral.payout_id.is_(None),
            Referral.unlock_at.isnot(None),
            Referral.unlock_at <= now,
        ).all()

        total = sum((r.commission_amount or 0) for r in eligible)
        settings = get_ambassador_settings()
        if total < settings["min_payout_kes"]:
            return jsonify({
                "error": f"Available balance (KES {total}) is below the minimum payout of KES {settings['min_payout_kes']}"
            }), 400

        payout = AmbassadorPayout(
            ambassador_id=ambassador.id,
            amount=total,
            payout_destination=payout_destination,
            recipient_first_name=recipient_first_name,
            recipient_last_name=recipient_last_name,
            status="pending",
        )
        db.session.add(payout)
        db.session.flush()  # assign payout.id before referrals reference it

        for referral in eligible:
            referral.payout_id = payout.id

        db.session.commit()

        return jsonify({"id": payout.id, "amount": payout.amount, "status": payout.status}), 201
