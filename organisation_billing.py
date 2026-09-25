"""Paystack-backed organisation plan billing for the launch portal."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timedelta

from flask import jsonify, request, session
from sqlalchemy import text


def register_organisation_billing(app, db):
    with app.app_context():
        if db.engine.dialect.name == 'sqlite':
            return
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS organisation_plan_config (
                plan_code VARCHAR(20) PRIMARY KEY,
                monthly_fee_kes INTEGER NOT NULL,
                active_user_cap INTEGER NOT NULL,
                active_opportunities INTEGER NOT NULL DEFAULT 0,
                sponsored_campaigns INTEGER NOT NULL DEFAULT 0,
                candidate_search_window_days INTEGER NOT NULL DEFAULT 7,
                analytics_retention_days INTEGER NOT NULL DEFAULT 30,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                version INTEGER NOT NULL DEFAULT 1,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.session.execute(text("""
            INSERT INTO organisation_plan_config
                (plan_code,monthly_fee_kes,active_user_cap,active_opportunities,sponsored_campaigns,
                 candidate_search_window_days,analytics_retention_days)
            VALUES
                ('launch',2500,250,2,1,7,30),
                ('growth',7500,1000,10,3,30,90),
                ('scale',15000,3000,50,10,30,365)
            ON CONFLICT (plan_code) DO NOTHING
        """))
        db.session.execute(text("""
            ALTER TABLE organisation_billing
            ADD COLUMN IF NOT EXISTS transaction_reference VARCHAR(120),
            ADD COLUMN IF NOT EXISTS checkout_url TEXT
        """))
        db.session.commit()

    def organisation_plan(plan_code):
        return db.session.execute(text("""
            SELECT * FROM organisation_plan_config
            WHERE plan_code=:plan AND is_active=TRUE
        """), {"plan": plan_code}).mappings().first()

    def member_role(org_id, user_id):
        return db.session.execute(text("""
            SELECT role FROM organisation_member
            WHERE organisation_id = :oid AND user_id = :uid
            LIMIT 1
        """), {"oid": org_id, "uid": user_id}).scalar_one_or_none()

    def csrf_ok():
        return bool(
            session.get("csrf_token")
            and request.headers.get("X-CSRF-Token")
            and session.get("csrf_token") == request.headers.get("X-CSRF-Token")
        )

    @app.get("/api/organisations/plans")
    def organisation_plan_options():
        rows = db.session.execute(text("""
            SELECT plan_code, monthly_fee_kes, active_user_cap, active_opportunities,
                   sponsored_campaigns, candidate_search_window_days,
                   analytics_retention_days
            FROM organisation_plan_config
            WHERE is_active=TRUE
            ORDER BY CASE plan_code WHEN 'launch' THEN 1 WHEN 'growth' THEN 2 WHEN 'scale' THEN 3 ELSE 99 END
        """)).mappings().all()
        return jsonify({"plans": [dict(r) for r in rows]})

    @app.post("/api/organisations/<int:organisation_id>/plan/checkout")
    def organisation_plan_checkout(organisation_id):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        if not csrf_ok():
            return jsonify({"error": "Invalid CSRF token"}), 403
        if member_role(organisation_id, user_id) != "owner":
            return jsonify({"error": "Only the organisation owner can purchase a plan"}), 403

        secret = os.environ.get("PAYSTACK_SECRET_KEY")
        if not secret:
            return jsonify({"error": "Organisation payments are not configured yet"}), 503

        data = request.get_json(silent=True) or {}
        plan_code = str(data.get("plan") or "").strip().lower()
        plan = organisation_plan(plan_code)
        if not plan:
            return jsonify({"error": "Choose a valid paid organisation plan"}), 400

        email = db.session.execute(
            text('SELECT email FROM "user" WHERE id = :uid'),
            {"uid": user_id},
        ).scalar_one_or_none()
        if not email:
            return jsonify({"error": "Organisation owner email is required"}), 400

        reference = "org-" + str(organisation_id) + "-" + uuid.uuid4().hex[:20]
        payload = {
            "email": email,
            "amount": str(plan["monthly_fee_kes"] * 100),
            "currency": "KES",
            "reference": reference,
            "channels": ["mobile_money", "card"],
            "metadata": json.dumps({
                "organisation_id": organisation_id,
                "plan_code": plan_code,
                "type": "organisation_plan",
            }),
        }

        try:
            import requests
            response = requests.post(
                "https://api.paystack.co/transaction/initialize",
                headers={
                    "Authorization": "Bearer " + secret,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=15,
            )
            body = response.json()
        except Exception:
            return jsonify({"error": "Could not start organisation checkout"}), 502

        authorization_url = (body.get("data") or {}).get("authorization_url")
        if not response.ok or not body.get("status") or not authorization_url:
            return jsonify({"error": body.get("message") or "Paystack rejected the checkout"}), 502

        db.session.execute(text("""
            INSERT INTO organisation_billing
                (organisation_id, plan_code, status, monthly_fee_kes, active_user_cap,
                 transaction_reference, checkout_url, updated_at)
            VALUES (:oid, :plan, 'pending', :fee, :cap, :reference, :url, CURRENT_TIMESTAMP)
            ON CONFLICT (organisation_id)
            DO UPDATE SET plan_code = EXCLUDED.plan_code,
                          status = 'pending',
                          monthly_fee_kes = EXCLUDED.monthly_fee_kes,
                          active_user_cap = EXCLUDED.active_user_cap,
                          transaction_reference = EXCLUDED.transaction_reference,
                          checkout_url = EXCLUDED.checkout_url,
                          updated_at = CURRENT_TIMESTAMP
        """), {
            "oid": organisation_id,
            "plan": plan_code,
            "fee": plan["monthly_fee_kes"],
            "cap": plan["active_user_cap"],
            "reference": reference,
            "url": authorization_url,
        })
        db.session.commit()
        return jsonify({
            "ok": True,
            "plan": plan_code,
            "amount_kes": plan["monthly_fee_kes"],
            "reference": reference,
            "redirect_url": authorization_url,
        })

    @app.get("/api/organisations/<int:organisation_id>/plan/status")
    def organisation_plan_status(organisation_id):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        if member_role(organisation_id, user_id) not in ("owner", "manager"):
            return jsonify({"error": "Organisation membership required"}), 403
        row = db.session.execute(text("""
            SELECT plan_code, status, monthly_fee_kes, active_user_cap,
                   started_at, expires_at, transaction_reference
            FROM organisation_billing
            WHERE organisation_id = :oid
        """), {"oid": organisation_id}).mappings().first()
        return jsonify({"billing": dict(row) if row else {
            "plan_code": "launch",
            "status": "trial",
            "monthly_fee_kes": 2500,
            "active_user_cap": 250,
        }})

    @app.post("/api/payments/paystack/organisation-webhook")
    def paystack_organisation_webhook():
        secret = os.environ.get("PAYSTACK_SECRET_KEY")
        if not secret:
            return jsonify({"error": "Webhook not configured"}), 503

        raw = request.get_data(cache=True)
        supplied = request.headers.get("x-paystack-signature", "")
        expected = hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()
        if not supplied or not hmac.compare_digest(expected, supplied):
            return jsonify({"error": "Invalid signature"}), 401

        event = request.get_json(silent=True) or {}
        if event.get("event") != "charge.success":
            return jsonify({"ok": True})

        data = event.get("data") or {}
        metadata = data.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}

        try:
            organisation_id = int(metadata.get("organisation_id"))
        except (TypeError, ValueError):
            return jsonify({"ok": True})

        plan_code = str(metadata.get("plan_code") or "").lower()
        plan = organisation_plan(plan_code)
        reference = str(data.get("reference") or "")
        if not plan or not reference:
            return jsonify({"ok": True})

        row = db.session.execute(text("""
            SELECT transaction_reference, status, expires_at
            FROM organisation_billing
            WHERE organisation_id = :oid
            FOR UPDATE
        """), {"oid": organisation_id}).mappings().first()
        if not row or row["transaction_reference"] != reference:
            return jsonify({"ok": True})

        # Paystack may retry a webhook. A successful reference is consumed
        # exactly once; otherwise a duplicate delivery could extend a
        # 30-day plan to 60 days.
        if row["status"] == "active":
            return jsonify({"ok": True})

        expected_amount = int(plan["monthly_fee_kes"]) * 100
        try:
            paid_amount = int(data.get("amount"))
        except (TypeError, ValueError):
            return jsonify({"ok": True})
        if paid_amount != expected_amount or str(data.get("currency") or "").upper() != "KES":
            return jsonify({"ok": True})

        now = datetime.utcnow()
        current_expiry = row["expires_at"]
        base = current_expiry if current_expiry and current_expiry > now else now
        expiry = base + timedelta(days=30)

        db.session.execute(text("""
            UPDATE organisation_billing
            SET plan_code = :plan,
                status = 'active',
                monthly_fee_kes = :fee,
                active_user_cap = :cap,
                started_at = COALESCE(started_at, :now),
                expires_at = :expiry,
                updated_at = CURRENT_TIMESTAMP
            WHERE organisation_id = :oid
              AND transaction_reference = :reference
        """), {
            "plan": plan_code,
            "fee": plan["monthly_fee_kes"],
            "cap": plan["active_user_cap"],
            "now": now,
            "expiry": expiry,
            "oid": organisation_id,
            "reference": reference,
        })
        db.session.commit()
        return jsonify({"ok": True})
