"""Canonical B2B sponsored-campaign financial foundation for G1."""
from __future__ import annotations
import json
from flask import jsonify, request, session
from sqlalchemy import text

def _register_b2b_campaign_finance_schema(db):

    if db.engine.dialect.name == "sqlite":
        return
    db.session.execute(text("""
        ALTER TABLE discovery_campaign
        ADD COLUMN IF NOT EXISTS currency VARCHAR(3) NOT NULL DEFAULT 'KES',
        ADD COLUMN IF NOT EXISTS funding_status VARCHAR(30) NOT NULL DEFAULT 'unfunded',
        ADD COLUMN IF NOT EXISTS funded_amount_minor BIGINT NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS pricing_version VARCHAR(80),
        ADD COLUMN IF NOT EXISTS pricing_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
        ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP,
        ADD COLUMN IF NOT EXISTS activated_at TIMESTAMP,
        ADD COLUMN IF NOT EXISTS exhausted_at TIMESTAMP
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS b2b_payment (
            id BIGSERIAL PRIMARY KEY,
            organisation_id INTEGER NOT NULL,
            campaign_id BIGINT,
            provider VARCHAR(30) NOT NULL DEFAULT 'paystack',
            provider_reference VARCHAR(160) NOT NULL UNIQUE,
            currency VARCHAR(3) NOT NULL DEFAULT 'KES',
            customer_amount_minor BIGINT NOT NULL,
            campaign_amount_minor BIGINT NOT NULL DEFAULT 0,
            processing_fee_minor BIGINT NOT NULL DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            purpose VARCHAR(40) NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            paid_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_b2b_payment_org_created ON b2b_payment (organisation_id, created_at DESC)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_b2b_payment_campaign_created ON b2b_payment (campaign_id, created_at DESC)"))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS b2b_campaign_funding (
            id BIGSERIAL PRIMARY KEY, campaign_id BIGINT NOT NULL, payment_id BIGINT NOT NULL UNIQUE,
            amount_minor BIGINT NOT NULL, currency VARCHAR(3) NOT NULL DEFAULT 'KES',
            status VARCHAR(30) NOT NULL DEFAULT 'credited', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reversed_at TIMESTAMP, reversal_reason TEXT
        )
    """))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_b2b_campaign_funding_campaign ON b2b_campaign_funding (campaign_id, created_at DESC)"))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS b2b_campaign_ledger (
            id BIGSERIAL PRIMARY KEY, campaign_id BIGINT NOT NULL, entry_type VARCHAR(40) NOT NULL,
            signed_amount_minor BIGINT NOT NULL, currency VARCHAR(3) NOT NULL DEFAULT 'KES',
            idempotency_key VARCHAR(220) NOT NULL UNIQUE, payment_id BIGINT, funding_id BIGINT,
            delivery_event_id BIGINT, reversal_of_entry_id BIGINT, actor_user_id INTEGER,
            description TEXT, metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_b2b_campaign_ledger_campaign_created ON b2b_campaign_ledger (campaign_id, created_at DESC)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_b2b_campaign_ledger_payment ON b2b_campaign_ledger (payment_id)"))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS b2b_pricing_config (
            id BIGSERIAL PRIMARY KEY, config_key VARCHAR(80) NOT NULL UNIQUE, value_json JSONB NOT NULL,
            currency VARCHAR(3) NOT NULL DEFAULT 'KES', version VARCHAR(80) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE, updated_by_user_id INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    defaults = [
        ("sponsored_campaign_minimum", {"amount_kes": 5000}),
        ("home_impression_cpm", {"amount_kes": 350, "per": 1000}),
        ("click_cpc", {"amount_kes": 20}),
        ("push_delivery_cpm", {"amount_kes": 1500, "per": 1000}),
        ("home_frequency_cap", {"max_impressions": 3, "window_days": 7}),
        ("home_sponsored_inventory", {"max_slots": 7}),
        ("push_frequency_cap", {"max_deliveries": 3, "window_days": 7}),
    ]
    for key, value in defaults:
        db.session.execute(text("""
            INSERT INTO b2b_pricing_config (config_key, value_json, version)
            VALUES (:key, CAST(:value AS jsonb), 'launch-v1') ON CONFLICT (config_key) DO NOTHING
        """), {"key": key, "value": json.dumps(value)})
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS b2b_audit_log (
            id BIGSERIAL PRIMARY KEY, organisation_id INTEGER, campaign_id BIGINT, actor_user_id INTEGER,
            action VARCHAR(60) NOT NULL, from_state VARCHAR(40), to_state VARCHAR(40), reason TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_b2b_audit_campaign_created ON b2b_audit_log (campaign_id, created_at DESC)"))
    db.session.commit()


def register_b2b_campaign_finance(app, db):
    with app.app_context():
        _register_b2b_campaign_finance_schema(db)

    def is_admin():
        uid = session.get("user_id")
        if not uid:
            return False
        row = db.session.execute(text('SELECT is_admin FROM "user" WHERE id=:uid'), {"uid": uid}).scalar()
        return bool(row)

    @app.get("/api/admin/b2b/pricing")
    def admin_b2b_pricing():
        if not is_admin(): return jsonify({"error": "Admin access required"}), 403
        rows = db.session.execute(text("""
            SELECT config_key,value_json,currency,version,is_active,updated_by_user_id,updated_at
            FROM b2b_pricing_config WHERE is_active=TRUE ORDER BY config_key
        """)).mappings().all()
        return jsonify({"pricing":[dict(r) for r in rows]})


    @app.patch("/api/admin/b2b/pricing/<string:config_key>")
    def admin_update_b2b_pricing(config_key):
        if not is_admin():
            return jsonify({"error": "Admin access required"}), 403
        token = session.get("csrf_token")
        if not token or request.headers.get("X-CSRF-Token") != token:
            return jsonify({"error": "Invalid CSRF token"}), 403
        key = str(config_key or "").strip()
        row = db.session.execute(text("""
            SELECT config_key, value_json, currency, version
            FROM b2b_pricing_config
            WHERE config_key=:key AND is_active=TRUE
            FOR UPDATE
        """), {"key": key}).mappings().first()
        if not row:
            return jsonify({"error": "Pricing key not found"}), 404
        data = request.get_json(silent=True) or {}
        value = data.get("value")
        if not isinstance(value, dict):
            return jsonify({"error": "value must be an object"}), 400
        if "amount_kes" in value:
            try:
                amount = int(value["amount_kes"])
            except (TypeError, ValueError):
                return jsonify({"error": "amount_kes must be an integer"}), 400
            if amount < 0:
                return jsonify({"error": "amount_kes cannot be negative"}), 400
            value["amount_kes"] = amount
        if "per" in value:
            try:
                value["per"] = int(value["per"])
            except (TypeError, ValueError):
                return jsonify({"error": "per must be an integer"}), 400
            if value["per"] <= 0:
                return jsonify({"error": "per must be positive"}), 400
        if "max_impressions" in value:
            value["max_impressions"] = max(0, int(value["max_impressions"]))
        if "max_slots" in value:
            value["max_slots"] = max(0, int(value["max_slots"]))
        if "max_deliveries" in value:
            value["max_deliveries"] = max(0, int(value["max_deliveries"]))
        uid = int(session["user_id"])
        version = db.session.execute(text("""
            SELECT 'admin-' || CAST(EXTRACT(EPOCH FROM CURRENT_TIMESTAMP) AS BIGINT)::text
        """)).scalar_one()
        db.session.execute(text("""
            UPDATE b2b_pricing_config
            SET value_json=CAST(:value AS jsonb), version=:version,
                updated_by_user_id=:uid, updated_at=CURRENT_TIMESTAMP
            WHERE config_key=:key AND is_active=TRUE
        """), {"value": json.dumps(value), "version": str(version), "uid": uid, "key": key})
        db.session.execute(text("""
            INSERT INTO b2b_audit_log(action, actor_user_id, metadata)
            VALUES ('pricing_config_updated', :uid, CAST(:metadata AS jsonb))
        """), {"uid": uid, "metadata": json.dumps({
            "config_key": key, "previous_value": row["value_json"],
            "new_value": value, "previous_version": row["version"],
            "new_version": str(version)
        })})
        db.session.commit()
        return jsonify({
            "ok": True, "config_key": key, "value": value,
            "version": str(version), "currency": row["currency"]
        }), 200

    @app.get("/api/admin/b2b/campaigns/<int:campaign_id>/ledger")
    def admin_b2b_campaign_ledger(campaign_id):
        if not is_admin(): return jsonify({"error":"Admin access required"}),403
        rows=db.session.execute(text("""
            SELECT id,entry_type,signed_amount_minor,currency,idempotency_key,payment_id,funding_id,
                   delivery_event_id,reversal_of_entry_id,actor_user_id,description,metadata,created_at
            FROM b2b_campaign_ledger WHERE campaign_id=:cid ORDER BY id ASC
        """),{"cid":campaign_id}).mappings().all()
        total=sum(int(r["signed_amount_minor"]) for r in rows)
        return jsonify({"campaign_id":campaign_id,"currency":"KES","balance_minor":total,"balance_kes":total/100,
                        "ledger":[dict(r) for r in rows]})

    @app.get("/api/admin/b2b/overview")
    def admin_b2b_overview():
        if not is_admin(): return jsonify({"error":"Admin access required"}),403
        totals=db.session.execute(text("""
            SELECT COUNT(*) AS campaigns,
                   COALESCE(SUM(CASE WHEN status='active' THEN 1 ELSE 0 END),0) AS active,
                   COALESCE(SUM(CASE WHEN funding_status='exhausted' THEN 1 ELSE 0 END),0) AS exhausted,
                   COALESCE(SUM(funded_amount_minor),0) AS funded_minor
            FROM discovery_campaign
        """)).mappings().one()
        ledger=db.session.execute(text("""
            SELECT COALESCE(SUM(signed_amount_minor),0) FROM b2b_campaign_ledger
        """)).scalar_one()
        payments=db.session.execute(text("""
            SELECT
              COALESCE(SUM(CASE WHEN status IN ('paid','credited') THEN campaign_amount_minor ELSE 0 END),0) AS campaign_value_minor,
              COALESCE(SUM(CASE WHEN status IN ('paid','credited') THEN processing_fee_minor ELSE 0 END),0) AS processing_fee_minor,
              COALESCE(SUM(CASE WHEN status='refunded' THEN campaign_amount_minor ELSE 0 END),0) AS refunded_campaign_minor
            FROM b2b_payment
        """)).mappings().one()
        return jsonify({
            "currency":"KES","campaigns":int(totals["campaigns"]),
            "active_campaigns":int(totals["active"]),
            "exhausted_campaigns":int(totals["exhausted"]),
            "campaign_funding_kes":int(totals["funded_minor"])/100,
            "ledger_net_balance_kes":int(ledger)/100,
            "paid_campaign_value_kes":int(payments["campaign_value_minor"])/100,
            "customer_processing_fees_kes":int(payments["processing_fee_minor"])/100,
            "refunded_campaign_value_kes":int(payments["refunded_campaign_minor"])/100,
            "processing_fees_are_customer_costs":True
        })
