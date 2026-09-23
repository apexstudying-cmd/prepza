"""G2: Paystack payment -> prepaid sponsored-campaign funding.

Payment processing fees are kept separate from campaign value. Launch assumes
Paystack's customer-fee pass-through is enabled for the Prepza Kenya account;
otherwise campaign checkout is blocked rather than silently reducing campaign
budget.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from decimal import Decimal, ROUND_CEILING

import requests
from flask import jsonify, request, session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def register_b2b_campaign_payments(app, db):
    def csrf_ok():
        token = session.get("csrf_token")
        return bool(token and request.headers.get("X-CSRF-Token") == token)

    def member_role(org_id, user_id):
        return db.session.execute(text("""
            SELECT role FROM organisation_member
            WHERE organisation_id=:oid AND user_id=:uid LIMIT 1
        """), {"oid": org_id, "uid": user_id}).scalar_one_or_none()

    def org_owner(org_id, user_id):
        return member_role(org_id, user_id) == "owner"

    def pricing(key):
        row = db.session.execute(text("""
            SELECT value_json, version FROM b2b_pricing_config
            WHERE config_key=:key AND is_active=TRUE
            ORDER BY id DESC LIMIT 1
        """), {"key": key}).mappings().first()
        return (row["value_json"] if row else None, row["version"] if row else None)

    def fee_passing_enabled():
        return os.environ.get("PAYSTACK_CUSTOMER_FEE_PASSING_ENABLED", "").strip().lower() == "true"

    def paystack_headers():
        secret = os.environ.get("PAYSTACK_SECRET_KEY")
        if not secret:
            raise RuntimeError("PAYSTACK_SECRET_KEY is not configured")
        return {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}

    def paystack_request(method, path, **kwargs):
        response = requests.request(
            method, f"https://api.paystack.co{path}",
            headers=paystack_headers(), timeout=20, **kwargs
        )
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code >= 400 or not body.get("status"):
            message = body.get("message") or f"Paystack request failed ({response.status_code})"
            raise RuntimeError(message)
        return body.get("data") or {}

    def provider_signature_valid():
        secret = os.environ.get("PAYSTACK_SECRET_KEY")
        supplied = request.headers.get("x-paystack-signature", "")
        if not secret or not supplied:
            return False
        raw = request.get_data(cache=True)
        expected = hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, supplied)

    def campaign_for_update(campaign_id, organisation_id):
        return db.session.execute(text("""
            SELECT * FROM discovery_campaign
            WHERE id=:cid AND organisation_id=:oid FOR UPDATE
        """), {"cid": campaign_id, "oid": organisation_id}).mappings().first()

    def parse_metadata(data):
        meta = data.get("metadata")
        if isinstance(meta, dict):
            return meta
        if isinstance(meta, str):
            try:
                parsed = json.loads(meta)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def mark_audit(org_id, campaign_id, actor_id, action, from_state=None, to_state=None, reason=None, metadata=None):
        db.session.execute(text("""
            INSERT INTO b2b_audit_log
                (organisation_id,campaign_id,actor_user_id,action,from_state,to_state,reason,metadata)
            VALUES (:oid,:cid,:uid,:action,:from_state,:to_state,:reason,CAST(:metadata AS jsonb))
        """), {
            "oid": org_id, "cid": campaign_id, "uid": actor_id, "action": action,
            "from_state": from_state, "to_state": to_state, "reason": reason,
            "metadata": json.dumps(metadata or {}),
        })

    def initialize_paystack(campaign, organisation_id, user_id):
        if not fee_passing_enabled():
            raise RuntimeError(
                "Customer payment-fee pass-through is not enabled for this Paystack account. "
                "Enable it with Paystack/support before accepting campaign payments."
            )
        secret = os.environ.get("PAYSTACK_SECRET_KEY")
        if not secret:
            raise RuntimeError("PAYSTACK_SECRET_KEY is not configured")

        amount_minor = int(campaign["budget_kes"]) * 100
        reference = f"PZA-CAMP-{int(campaign['id'])}-{secrets.token_hex(8)}"
        metadata = json.dumps({
            "purpose": "sponsored_campaign",
            "campaign_id": int(campaign["id"]),
            "organisation_id": int(organisation_id),
            "campaign_amount_minor": amount_minor,
            "pricing_version": campaign["pricing_version"],
        })
        data = paystack_request("POST", "/transaction/initialize", json={
            "email": db.session.execute(
                text('SELECT email FROM "user" WHERE id=:uid'), {"uid": user_id}
            ).scalar_one(),
            "amount": str(amount_minor),
            "currency": "KES",
            "reference": reference,
            "callback_url": f"{os.environ.get('BASE_URL', '').rstrip('/')}/organisation-payment-callback",
            "metadata": metadata,
        })

        db.session.execute(text("""
            INSERT INTO b2b_payment
                (organisation_id,campaign_id,provider,provider_reference,currency,
                 customer_amount_minor,campaign_amount_minor,processing_fee_minor,
                 status,purpose,metadata)
            VALUES (:oid,:cid,'paystack',:reference,'KES',:customer_amount,
                    :campaign_amount,0,'pending','sponsored_campaign',CAST(:metadata AS jsonb))
        """), {
            "oid": organisation_id, "cid": int(campaign["id"]), "reference": reference,
            "customer_amount": amount_minor, "campaign_amount": amount_minor,
            "metadata": metadata,
        })
        db.session.execute(text("""
            UPDATE discovery_campaign
            SET funding_status='payment_pending', updated_at=CURRENT_TIMESTAMP
            WHERE id=:cid AND organisation_id=:oid
        """), {"cid": int(campaign["id"]), "oid": organisation_id})
        mark_audit(
            organisation_id, int(campaign["id"]), user_id, "payment_initialized",
            from_state=str(campaign["funding_status"]), to_state="payment_pending",
            metadata={"provider_reference": reference, "campaign_amount_minor": amount_minor},
        )
        db.session.commit()
        return {
            "authorization_url": data.get("authorization_url"),
            "access_code": data.get("access_code"),
            "reference": reference,
            "campaign_amount_minor": amount_minor,
            "customer_fee_mode": "paystack_pass_through",
        }

    @app.post("/api/organisations/<int:organisation_id>/discovery/campaigns/<int:campaign_id>/payment")
    def b2b_campaign_payment_initialize(organisation_id, campaign_id):
        uid = session.get("user_id")
        if not uid:
            return jsonify({"error": "Not logged in"}), 401
        if not csrf_ok() or not org_owner(organisation_id, uid):
            return jsonify({"error": "Organisation owner and valid CSRF token required"}), 403

        campaign = campaign_for_update(campaign_id, organisation_id)
        if not campaign:
            return jsonify({"error": "Campaign not found"}), 404
        if campaign["status"] not in ("draft", "pending_payment"):
            return jsonify({"error": "Campaign is not available for payment in its current state"}), 409
        if campaign["funding_status"] == "payment_pending":
            pending = db.session.execute(text("""
                SELECT provider_reference FROM b2b_payment
                WHERE campaign_id=:cid AND status='pending'
                ORDER BY id DESC LIMIT 1
            """), {"cid": campaign_id}).scalar_one_or_none()
            if pending:
                return jsonify({"error": "A campaign payment is already pending", "reference": pending}), 409
        if campaign["funding_status"] in ("funded", "credited"):
            return jsonify({"error": "Campaign is already funded"}), 409

        minimum, _ = pricing("sponsored_campaign_minimum")
        minimum_kes = int((minimum or {}).get("amount_kes") or 5000)
        budget_kes = int(campaign["budget_kes"] or 0)
        if budget_kes < minimum_kes:
            return jsonify({"error": f"Minimum campaign budget is KES {minimum_kes:,}"}), 400

        # Snapshot launch economics before money is accepted. Later admin edits
        # cannot silently change the economics of this already-created campaign.
        current_pricing = {}
        for key in ("sponsored_campaign_minimum", "home_impression_cpm", "click_cpc",
                    "push_delivery_cpm", "home_frequency_cap", "home_sponsored_inventory",
                    "push_frequency_cap"):
            value, version = pricing(key)
            current_pricing[key] = {"value": value, "version": version}

        db.session.execute(text("""
            UPDATE discovery_campaign
            SET pricing_version=:version,
                pricing_snapshot=CAST(:snapshot AS jsonb),
                status='pending_payment',
                updated_at=CURRENT_TIMESTAMP
            WHERE id=:cid AND organisation_id=:oid
        """), {
            "version": "launch-v1",
            "snapshot": json.dumps(current_pricing),
            "cid": campaign_id, "oid": organisation_id,
        })
        db.session.commit()

        try:
            fresh = campaign_for_update(campaign_id, organisation_id)
            result = initialize_paystack(fresh, organisation_id, uid)
            return jsonify({"ok": True, **result}), 200
        except Exception as exc:
            db.session.rollback()
            return jsonify({"error": str(exc)}), 502

    def fulfill_successful_payment(reference, event_data):
        payment = db.session.execute(text("""
            SELECT * FROM b2b_payment
            WHERE provider='paystack' AND provider_reference=:reference
            FOR UPDATE
        """), {"reference": reference}).mappings().first()
        if not payment:
            return {"ok": False, "ignored": True, "reason": "unknown_reference"}

        if payment["status"] in ("paid", "credited"):
            return {"ok": True, "duplicate": True}

        campaign = db.session.execute(text("""
            SELECT * FROM discovery_campaign WHERE id=:cid FOR UPDATE
        """), {"cid": int(payment["campaign_id"])}).mappings().first()
        if not campaign:
            db.session.execute(text("""
                UPDATE b2b_payment SET status='needs_attention', updated_at=CURRENT_TIMESTAMP
                WHERE id=:pid
            """), {"pid": int(payment["id"])})
            db.session.commit()
            return {"ok": False, "reason": "campaign_missing"}

        verified = paystack_request("GET", f"/transaction/verify/{reference}")
        if str(verified.get("status", "")).lower() != "success":
            db.session.rollback()
            return {"ok": False, "reason": "provider_not_success"}

        currency = str(verified.get("currency") or "").upper()
        requested_amount = int(verified.get("requested_amount") or 0)
        paid_amount = int(verified.get("amount") or 0)
        provider_fee = verified.get("fees")
        provider_fee = int(provider_fee) if provider_fee is not None else 0
        expected_campaign = int(payment["campaign_amount_minor"])

        if currency != "KES" or requested_amount != expected_campaign or paid_amount < expected_campaign:
            db.session.execute(text("""
                UPDATE b2b_payment SET status='amount_mismatch',
                    customer_amount_minor=:customer_amount,
                    processing_fee_minor=:processing_fee,
                    metadata=metadata || CAST(:extra AS jsonb),
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=:pid
            """), {
                "pid": int(payment["id"]), "customer_amount": paid_amount,
                "processing_fee": max(0, paid_amount - expected_campaign),
                "extra": json.dumps({"provider_verification": {
                    "currency": currency, "requested_amount": requested_amount,
                    "amount": paid_amount, "fees": provider_fee
                }}),
            })
            db.session.commit()
            return {"ok": False, "reason": "amount_or_currency_mismatch"}

        # The campaign gets exactly the frozen campaign amount. Provider fees
        # are customer-side economics and never reduce prepaid campaign value.
        existing_funding = db.session.execute(text("""
            SELECT id FROM b2b_campaign_funding WHERE payment_id=:pid
        """), {"pid": int(payment["id"])}).scalar_one_or_none()
        if existing_funding:
            db.session.execute(text("""
                UPDATE b2b_payment SET status='credited', paid_at=COALESCE(paid_at,CURRENT_TIMESTAMP),
                    customer_amount_minor=:customer_amount, processing_fee_minor=:fee,
                    updated_at=CURRENT_TIMESTAMP WHERE id=:pid
            """), {"pid": int(payment["id"]), "customer_amount": paid_amount,
                   "fee": max(0, paid_amount - expected_campaign)})
            db.session.commit()
            return {"ok": True, "duplicate": True}

        try:
            funding_id = db.session.execute(text("""
                INSERT INTO b2b_campaign_funding
                    (campaign_id,payment_id,amount_minor,currency,status)
                VALUES (:cid,:pid,:amount,'KES','credited')
                RETURNING id
            """), {"cid": int(payment["campaign_id"]), "pid": int(payment["id"]),
                   "amount": expected_campaign}).scalar_one()

            db.session.execute(text("""
                INSERT INTO b2b_campaign_ledger
                    (campaign_id,entry_type,signed_amount_minor,currency,idempotency_key,
                     payment_id,funding_id,description,metadata)
                VALUES (:cid,'funding',:amount,'KES',:key,:pid,:fid,
                        'Sponsored campaign prepaid funding',CAST(:metadata AS jsonb))
            """), {
                "cid": int(payment["campaign_id"]), "amount": expected_campaign,
                "key": f"funding:{reference}", "pid": int(payment["id"]), "fid": int(funding_id),
                "metadata": json.dumps({"provider_reference": reference,
                    "customer_amount_minor": paid_amount,
                    "processing_fee_minor": max(0, paid_amount - expected_campaign),
                    "provider_fee_minor": provider_fee}),
            })
        except IntegrityError:
            db.session.rollback()
            existing = db.session.execute(text("""
                SELECT id FROM b2b_campaign_funding WHERE payment_id=:pid
            """), {"pid": int(payment["id"])}).scalar_one_or_none()
            if existing:
                return {"ok": True, "duplicate": True}
            raise

        db.session.execute(text("""
            UPDATE b2b_payment
            SET status='paid', paid_at=COALESCE(paid_at,CURRENT_TIMESTAMP),
                customer_amount_minor=:customer_amount,
                processing_fee_minor=:fee, updated_at=CURRENT_TIMESTAMP
            WHERE id=:pid
        """), {"pid": int(payment["id"]), "customer_amount": paid_amount,
               "fee": max(0, paid_amount - expected_campaign)})
        db.session.execute(text("""
            UPDATE discovery_campaign
            SET funding_status='funded',
                funded_amount_minor=funded_amount_minor+:amount,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=:cid
        """), {"cid": int(payment["campaign_id"]), "amount": expected_campaign})
        mark_audit(
            int(payment["organisation_id"]), int(payment["campaign_id"]), None,
            "payment_funded", from_state=str(campaign["funding_status"]), to_state="funded",
            metadata={"provider_reference": reference, "campaign_amount_minor": expected_campaign,
                      "processing_fee_minor": max(0, paid_amount - expected_campaign)},
        )
        db.session.commit()
        return {"ok": True, "funded_amount_minor": expected_campaign}

    @app.post("/payment/paystack/b2b-webhook")
    def b2b_paystack_webhook():
        if not provider_signature_valid():
            return jsonify({"error": "Invalid Paystack signature"}), 401
        payload = request.get_json(silent=True) or {}
        if payload.get("event") != "charge.success":
            return jsonify({"ok": True, "ignored": True}), 200
        data = payload.get("data") or {}
        reference = str(data.get("reference") or "").strip()
        metadata = parse_metadata(data)
        if not reference or metadata.get("purpose") != "sponsored_campaign":
            return jsonify({"ok": True, "ignored": True}), 200
        try:
            result = fulfill_successful_payment(reference, data)
            return jsonify(result), 200
        except Exception:
            db.session.rollback()
            app.logger.exception("B2B Paystack webhook fulfillment failed")
            return jsonify({"error": "Temporary processing failure"}), 500

    @app.get("/api/organisations/<int:organisation_id>/discovery/campaigns/<int:campaign_id>/payment-status")
    def b2b_campaign_payment_status(organisation_id, campaign_id):
        uid = session.get("user_id")
        if not uid or not member_role(organisation_id, uid):
            return jsonify({"error": "Organisation membership required"}), 403
        campaign = db.session.execute(text("""
            SELECT id,status,funding_status,funded_amount_minor,exhausted_at,
                   approved_at,activated_at FROM discovery_campaign
            WHERE id=:cid AND organisation_id=:oid
        """), {"oid": organisation_id, "cid": campaign_id}).mappings().first()
        if not campaign:
            return jsonify({"error": "Campaign not found"}), 404
        row = db.session.execute(text("""
            SELECT id,provider_reference,status,customer_amount_minor,campaign_amount_minor,
                   processing_fee_minor,paid_at,created_at
            FROM b2b_payment
            WHERE organisation_id=:oid AND campaign_id=:cid
            ORDER BY id DESC LIMIT 1
        """), {"oid": organisation_id, "cid": campaign_id}).mappings().first()
        return jsonify({
            "campaign": dict(campaign),
            "payment": dict(row) if row else None,
            "status": dict(campaign).get("funding_status") if not row else row["status"]
        }), 200

    def b2b_campaign_payment_status(organisation_id, campaign_id):
        uid = session.get("user_id")
        if not uid or not member_role(organisation_id, uid):
            return jsonify({"error": "Organisation membership required"}), 403
        row = db.session.execute(text("""
            SELECT id,provider_reference,status,customer_amount_minor,campaign_amount_minor,
                   processing_fee_minor,paid_at,created_at
            FROM b2b_payment
            WHERE organisation_id=:oid AND campaign_id=:cid
            ORDER BY id DESC LIMIT 1
        """), {"oid": organisation_id, "cid": campaign_id}).mappings().first()
        if not row:
            return jsonify({"status": "unfunded"}), 200
        return jsonify({"payment": dict(row)}), 200
