"""Admin-only B2B finance and placement controls for Prepza."""
from __future__ import annotations
import json
from flask import jsonify, request, session
from sqlalchemy import text

def register_b2b_admin_routes(app, db):
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS b2b_placement_config (
            id BIGSERIAL PRIMARY KEY,
            placement_key VARCHAR(80) NOT NULL UNIQUE,
            label VARCHAR(160) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            allowed_billing_modes JSONB NOT NULL DEFAULT '[\"cpm\",\"cpc\"]'::jsonb,
            cpm_amount_minor BIGINT,
            cpc_amount_minor BIGINT,
            inventory_limit INTEGER,
            frequency_cap_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            version VARCHAR(80) NOT NULL DEFAULT 'launch-v1',
            updated_by_user_id INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    placement_defaults=[
        ("home_carousel","Home carousel",35000,2000),
        ("explore_university","Explore / university discovery",35000,2000),
        ("opportunities_feed","Opportunities feed",35000,2000),
        ("podcast_banner","Podcast-player banner",35000,2000),
    ]
    for key,label,cpm,cpc in placement_defaults:
        db.session.execute(text("""
            INSERT INTO b2b_placement_config
                (placement_key,label,cpm_amount_minor,cpc_amount_minor)
            VALUES (:key,:label,:cpm,:cpc) ON CONFLICT (placement_key) DO NOTHING
        """),{"key":key,"label":label,"cpm":cpm,"cpc":cpc})
    db.session.commit()

    def is_admin():
        uid = session.get("user_id")
        return bool(uid and (session.get("is_admin") is True or session.get("role") in ("admin", "superadmin")))

    @app.get("/api/admin/b2b/placements")
    def admin_b2b_placements():
        if not is_admin(): return jsonify({"error":"Admin access required"}),403
        rows=db.session.execute(text("""
            SELECT id,placement_key,label,is_active,allowed_billing_modes,cpm_amount_minor,
                   cpc_amount_minor,inventory_limit,frequency_cap_json,version,updated_by_user_id,
                   created_at,updated_at
            FROM b2b_placement_config ORDER BY id
        """)).mappings().all()
        return jsonify({"placements":[dict(r) for r in rows]})

    @app.post("/api/admin/b2b/placements")
    def admin_b2b_create_placement():
        if not is_admin(): return jsonify({"error":"Admin access required"}),403
        data=request.get_json(silent=True) or {}
        key=str(data.get("placement_key") or "").strip().lower().replace(" ","_")[:80]
        label=str(data.get("label") or "").strip()[:160]
        modes=data.get("allowed_billing_modes") or ["cpm","cpc"]
        try:
            cpm=None if data.get("cpm_amount_minor") is None else int(data["cpm_amount_minor"])
            cpc=None if data.get("cpc_amount_minor") is None else int(data["cpc_amount_minor"])
        except (TypeError,ValueError):
            return jsonify({"error":"Invalid placement pricing"}),400
        if not key or not label or not isinstance(modes,list) or not set(modes).issubset({"cpm","cpc"}) or not modes:
            return jsonify({"error":"Valid placement key, label and billing modes are required"}),400
        try:
            row=db.session.execute(text("""
                INSERT INTO b2b_placement_config
                    (placement_key,label,allowed_billing_modes,cpm_amount_minor,cpc_amount_minor)
                VALUES (:key,:label,CAST(:modes AS jsonb),:cpm,:cpc)
                RETURNING id
            """),{"key":key,"label":label,"modes":json.dumps(modes),"cpm":cpm,"cpc":cpc}).scalar_one()
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({"error":"Placement key already exists or could not be created"}),409
        return jsonify({"ok":True,"id":int(row)}),201

    @app.patch("/api/admin/b2b/placements/<int:placement_id>")
    def admin_b2b_update_placement(placement_id):
        if not is_admin(): return jsonify({"error":"Admin access required"}),403
        data=request.get_json(silent=True) or {}
        label=str(data.get("label") or "").strip()[:160]
        if not label: return jsonify({"error":"Label is required"}),400
        modes=data.get("allowed_billing_modes") or ["cpm","cpc"]
        if not isinstance(modes,list) or not set(modes).issubset({"cpm","cpc"}) or not modes:
            return jsonify({"error":"Billing modes must contain cpm and/or cpc"}),400
        try:
            cpm=None if data.get("cpm_amount_minor") is None else int(data["cpm_amount_minor"])
            cpc=None if data.get("cpc_amount_minor") is None else int(data["cpc_amount_minor"])
            inventory=None if data.get("inventory_limit") is None else int(data["inventory_limit"])
        except (TypeError,ValueError):
            return jsonify({"error":"Invalid placement pricing"}),400
        if "cpm" in modes and (cpm is None or cpm < 0): return jsonify({"error":"CPM rate required"}),400
        if "cpc" in modes and (cpc is None or cpc < 0): return jsonify({"error":"CPC rate required"}),400
        uid=session.get("user_id")
        row=db.session.execute(text("SELECT placement_key FROM b2b_placement_config WHERE id=:id"),{"id":placement_id}).mappings().first()
        if not row: return jsonify({"error":"Placement not found"}),404
        db.session.execute(text("""
            UPDATE b2b_placement_config
            SET label=:label,is_active=:active,allowed_billing_modes=CAST(:modes AS jsonb),
                cpm_amount_minor=:cpm,cpc_amount_minor=:cpc,inventory_limit=:inventory,
                version='admin-v1',updated_by_user_id=:uid,updated_at=CURRENT_TIMESTAMP
            WHERE id=:id
        """),{"label":label,"active":bool(data.get("is_active",True)),"modes":json.dumps(modes),
              "cpm":cpm,"cpc":cpc,"inventory":inventory,"uid":uid,"id":placement_id})
        db.session.execute(text("""
            INSERT INTO b2b_audit_log(action,actor_user_id,metadata)
            VALUES ('placement_config_updated',:uid,CAST(:meta AS jsonb))
        """),{"uid":uid,"meta":json.dumps({"placement_id":placement_id,"placement_key":row["placement_key"]})})
        db.session.commit()
        return jsonify({"ok":True})

    @app.get("/api/admin/b2b/campaigns")
    def admin_b2b_campaigns():
        if not is_admin(): return jsonify({"error":"Admin access required"}),403
        rows=db.session.execute(text("""
            SELECT id,organisation_id,opportunity_id,name,objective,placement,status,budget_kes,
                   bid_type,bid_kes,funding_status,funded_amount_minor,delivered_impressions,
                   delivered_clicks,delivered_applications,push_delivered,created_at,approved_at,
                   activated_at,exhausted_at
            FROM discovery_campaign ORDER BY created_at DESC LIMIT 500
        """)).mappings().all()
        return jsonify({"campaigns":[dict(r) for r in rows]})

    @app.get("/api/admin/b2b/payments")
    def admin_b2b_payments():
        if not is_admin(): return jsonify({"error":"Admin access required"}),403
        rows=db.session.execute(text("""
            SELECT p.id,p.organisation_id,p.campaign_id,p.provider,p.provider_reference,p.currency,
                   p.customer_amount_minor,p.campaign_amount_minor,p.processing_fee_minor,p.status,
                   p.purpose,p.paid_at,p.created_at,f.status AS funding_status
            FROM b2b_payment p LEFT JOIN b2b_campaign_funding f ON f.payment_id=p.id
            ORDER BY p.created_at DESC LIMIT 500
        """)).mappings().all()
        return jsonify({"payments":[dict(r) for r in rows]})

    @app.get("/api/admin/b2b/refunds")
    def admin_b2b_refunds():
        if not is_admin(): return jsonify({"error":"Admin access required"}),403
        rows=db.session.execute(text("""
            SELECT p.id,p.organisation_id,p.campaign_id,p.provider_reference,p.status,
                   p.campaign_amount_minor,p.created_at,p.updated_at,
                   f.status AS funding_status,f.reversed_at,f.reversal_reason
            FROM b2b_payment p LEFT JOIN b2b_campaign_funding f ON f.payment_id=p.id
            WHERE p.status='refunded' OR f.reversed_at IS NOT NULL
            ORDER BY p.updated_at DESC LIMIT 500
        """)).mappings().all()
        return jsonify({"refunds":[dict(r) for r in rows]})

    @app.get("/api/admin/b2b/reconciliation")
    def admin_b2b_reconciliation():
        if not is_admin(): return jsonify({"error":"Admin access required"}),403
        rows=db.session.execute(text("""
            SELECT p.id AS payment_id,p.provider_reference,p.campaign_id,p.status,
                   p.campaign_amount_minor,COALESCE(f.amount_minor,0) AS funding_amount_minor,
                   COALESCE((SELECT SUM(l.signed_amount_minor) FROM b2b_campaign_ledger l
                             WHERE l.payment_id=p.id AND l.entry_type='funding'),0) AS ledger_funding_minor,
                   CASE WHEN p.status IN ('paid','credited')
                              AND COALESCE(f.amount_minor,0)=p.campaign_amount_minor
                              AND COALESCE((SELECT SUM(l.signed_amount_minor) FROM b2b_campaign_ledger l
                                            WHERE l.payment_id=p.id AND l.entry_type='funding'),0)=p.campaign_amount_minor
                        THEN 'matched' ELSE 'review' END AS reconciliation_status
            FROM b2b_payment p LEFT JOIN b2b_campaign_funding f ON f.payment_id=p.id
            WHERE p.campaign_id IS NOT NULL ORDER BY p.created_at DESC LIMIT 500
        """)).mappings().all()
        return jsonify({"reconciliation":[dict(r) for r in rows]})
