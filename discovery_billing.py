"""Prepza Discovery campaigns, targeting, metering and sponsored push delivery.

The organisation owns campaign configuration; Prepza owns the audience selection.
Advertisers receive aggregate campaign analytics, never the underlying student list.
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta, date
from flask import jsonify, request, session
from sqlalchemy import text
from pywebpush import webpush
from b2b_campaign_metering import record_billable_event, reverse_billable_event

DISCOVERY_PRICING = {
    "feed_cpm_kes": 350,
    "click_cpc_kes": 20,
    "push_cpm_kes": 1500,
    "minimum_campaign_kes": 5000,
}

PUSH_CAP_PER_48_HOURS = 1
PUSH_CAP_PER_7_DAYS = 3


def register_discovery(app, db):
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS discovery_campaign (
            id BIGSERIAL PRIMARY KEY,
            organisation_id INTEGER NOT NULL,
            opportunity_id INTEGER,
            name VARCHAR(200) NOT NULL,
            objective VARCHAR(30) NOT NULL DEFAULT 'reach',
            placement VARCHAR(30) NOT NULL DEFAULT 'feed',
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            budget_kes INTEGER NOT NULL DEFAULT 0,
            bid_type VARCHAR(20) NOT NULL DEFAULT 'cpm',
            bid_kes INTEGER NOT NULL DEFAULT 350,
            target_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            delivered_impressions INTEGER NOT NULL DEFAULT 0,
            delivered_clicks INTEGER NOT NULL DEFAULT 0,
            delivered_applications INTEGER NOT NULL DEFAULT 0,
            push_delivered INTEGER NOT NULL DEFAULT 0,
            starts_at TIMESTAMP,
            ends_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS discovery_event (
            id BIGSERIAL PRIMARY KEY,
            campaign_id BIGINT NOT NULL,
            user_id INTEGER NOT NULL,
            event_key VARCHAR(180) NOT NULL UNIQUE,
            event_type VARCHAR(30) NOT NULL,
            placement VARCHAR(30) NOT NULL,
            amount_kes INTEGER NOT NULL DEFAULT 0,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.session.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_discovery_event_campaign_created
        ON discovery_event (campaign_id, created_at)
    """))
    db.session.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_discovery_event_user_type_created
        ON discovery_event (user_id, event_type, created_at)
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS organisation_usage_invoice (
            id BIGSERIAL PRIMARY KEY,
            organisation_id INTEGER NOT NULL,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            usage_type VARCHAR(40) NOT NULL DEFAULT 'discovery',
            amount_kes INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            payment_reference VARCHAR(120),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP,
            UNIQUE (organisation_id, period_start, period_end, usage_type)
        )
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS discovery_push_delivery (
            id BIGSERIAL PRIMARY KEY,
            campaign_id BIGINT NOT NULL,
            user_id INTEGER NOT NULL,
            subscription_endpoint TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'queued',
            provider_response TEXT,
            sent_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (campaign_id, user_id)
        )
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS student_opportunity_discovery (
            user_id INTEGER PRIMARY KEY REFERENCES "user"(id) ON DELETE CASCADE,
            discoverable BOOLEAN NOT NULL DEFAULT FALSE,
            consent_version VARCHAR(40) NOT NULL DEFAULT 'g5-v1',
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS student_opportunity_discovery_audit (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            discoverable BOOLEAN NOT NULL,
            consent_version VARCHAR(40) NOT NULL,
            source VARCHAR(40) NOT NULL DEFAULT 'settings',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.session.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_student_opportunity_discovery_audit_user_created
        ON student_opportunity_discovery (user_id, updated_at)
    """))
    db.session.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_student_opportunity_discovery_audit_log_user_created
        ON student_opportunity_discovery_audit (user_id, created_at)
    """))

    db.session.commit()

    def csrf_ok():
        return bool(session.get("csrf_token") and request.headers.get("X-CSRF-Token")
                    and session.get("csrf_token") == request.headers.get("X-CSRF-Token"))

    def member_role(org_id, user_id):
        return db.session.execute(text("""
            SELECT role FROM organisation_member
            WHERE organisation_id = :oid AND user_id = :uid LIMIT 1
        """), {"oid": org_id, "uid": user_id}).scalar_one_or_none()

    def org_access(org_id, user_id, owner_only=False):
        role = member_role(org_id, user_id)
        return role == "owner" if owner_only else role in ("owner", "manager")

    def org_plan(org_id):
        row = db.session.execute(text("""
            SELECT plan_code, status, expires_at
            FROM organisation_billing WHERE organisation_id = :oid
        """), {"oid": org_id}).mappings().first()
        if not row:
            return "launch", "trial", None
        return str(row["plan_code"]), str(row["status"]), row["expires_at"]

    ALLOWED_TARGET_KEYS = {"university_ids", "program_ids", "years", "active_days"}

    def normalize_target(raw_target):
        if not isinstance(raw_target, dict):
            return {}
        if set(raw_target.keys()) - ALLOWED_TARGET_KEYS:
            raise ValueError("Unsupported targeting criteria")
        target = {}
        for key in ("university_ids", "program_ids", "years"):
            values = raw_target.get(key)
            if values is None:
                continue
            if not isinstance(values, list):
                raise ValueError(f"{key} must be a list")
            cleaned = sorted({int(x) for x in values if str(x).isdigit()})
            if len(cleaned) > 100:
                raise ValueError(f"{key} contains too many values")
            target[key] = cleaned
        if raw_target.get("active_days") is not None:
            days = int(raw_target["active_days"])
            if not 1 <= days <= 90:
                raise ValueError("active_days must be between 1 and 90")
            target["active_days"] = days
        return target

    def eligible_users(target):
        target = normalize_target(target)
        clauses = []
        params = {}
        if target.get("university_ids"):
            clauses.append("u.university_id = ANY(:university_ids)")
            params["university_ids"] = target["university_ids"]
        if target.get("program_ids"):
            clauses.append("u.program_id = ANY(:program_ids)")
            params["program_ids"] = target["program_ids"]
        if target.get("years"):
            clauses.append("u.year = ANY(:years)")
            params["years"] = target["years"]
        # Explicit consent is mandatory; an organisation cannot opt a student in.
        clauses.append("COALESCE(sd.discoverable, FALSE) = TRUE")
        days = max(1, min(90, int(target.get("active_days", 30) or 30)))
        params["since_date"] = date.today() - timedelta(days=days - 1)
        clauses.append("""
            EXISTS (
                SELECT 1 FROM product_activity_day pad
                WHERE pad.user_id = u.id
                  AND pad.activity_date >= :since_date
                  AND (pad.engaged_seconds >= 30 OR pad.core_actions > 0)
            )
        """)
        # The account table is intentionally joined only inside Prepza.
        query = f"""
            SELECT u.id
            FROM "user" u
            LEFT JOIN student_opportunity_discovery sd ON sd.user_id = u.id
            WHERE {' AND '.join(clauses)}
        """
        rows = db.session.execute(text(query), params).all()
        return [int(r[0]) for r in rows]

    def campaign_usage(row):
        if row["bid_type"] == "cpc":
            return int(row["delivered_clicks"] or 0) * int(row["bid_kes"])
        if row["placement"] == "push":
            return (int(row["push_delivered"] or 0) * int(row["bid_kes"]) + 999) // 1000
        return (int(row["delivered_impressions"] or 0) * int(row["bid_kes"]) + 999) // 1000

    def sync_org_invoice(organisation_id):
        # G3: sponsored campaigns are prepaid. Never create a second monthly
        # usage invoice for delivery events; the canonical campaign ledger is
        # the billing source of truth. Organisation subscription billing remains
        # separate.
        base = db.session.execute(text("""
            SELECT COALESCE(monthly_fee_kes,0)
            FROM organisation_billing WHERE organisation_id=:oid
        """), {"oid": organisation_id}).scalar_one_or_none() or 0
        return int(base), 0, False

    def campaign_row(campaign_id):
        return db.session.execute(text("""
            SELECT * FROM discovery_campaign WHERE id = :id
        """), {"id": campaign_id}).mappings().first()

    def target_matches(user_id, target):
        target = normalize_target(target)
        clauses = ["u.id = :uid"]
        params = {"uid": user_id}
        if target.get("university_ids"):
            clauses.append("u.university_id = ANY(:university_ids)")
            params["university_ids"] = target["university_ids"]
        if target.get("program_ids"):
            clauses.append("u.program_id = ANY(:program_ids)")
            params["program_ids"] = target["program_ids"]
        if target.get("years"):
            clauses.append("u.year = ANY(:years)")
            params["years"] = target["years"]
        # Re-check consent at delivery time; stale clients cannot bypass it.
        clauses.append("COALESCE(sd.discoverable, FALSE) = TRUE")
        params["since_date"] = date.today() - timedelta(days=max(1, min(90, int(target.get("active_days", 30) or 30))) - 1)
        clauses.append("""EXISTS (
            SELECT 1 FROM product_activity_day pad
            WHERE pad.user_id = u.id AND pad.activity_date >= :since_date
              AND (pad.engaged_seconds >= 30 OR pad.core_actions > 0)
        )""")
        return bool(db.session.execute(text(f"""
            SELECT 1 FROM "user" u
            LEFT JOIN student_opportunity_discovery sd ON sd.user_id = u.id
            WHERE {' AND '.join(clauses)} LIMIT 1
        """), params).first())

    def push_subscription_rows(user_ids):
        if not user_ids:
            return []
        # Discover the existing push table shape rather than duplicating it.
        table = db.session.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='public' AND table_name IN
            ('push_subscription','push_subscriptions','web_push_subscription')
            ORDER BY CASE table_name
              WHEN 'push_subscription' THEN 1
              WHEN 'push_subscriptions' THEN 2 ELSE 3 END
            LIMIT 1
        """)).scalar_one_or_none()
        if not table:
            return []
        cols = db.session.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:table
        """), {"table": table}).scalars().all()
        user_col = "user_id" if "user_id" in cols else ("student_id" if "student_id" in cols else None)
        endpoint_col = "endpoint" if "endpoint" in cols else None
        if not user_col or not endpoint_col:
            return []
        key_col = "keys" if "keys" in cols else None
        p256dh_col = "p256dh" if "p256dh" in cols else None
        auth_col = "auth" if "auth" in cols else None
        selected = f"{user_col}, {endpoint_col}"
        if key_col: selected += f", {key_col}"
        elif p256dh_col and auth_col: selected += f", {p256dh_col}, {auth_col}"
        rows = db.session.execute(text(
            f"SELECT {selected} FROM {table} WHERE {user_col} = ANY(:ids)"
        ), {"ids": user_ids}).all()
        out=[]
        for r in rows:
            if not r[1]:
                continue
            keys = None
            if key_col and len(r) > 2:
                keys = r[2]
            elif p256dh_col and auth_col and len(r) > 3:
                keys = {"p256dh": r[2], "auth": r[3]}
            out.append({"user_id": int(r[0]), "endpoint": r[1], "keys": keys})
        return out

    @app.get("/api/opportunities/preferences")
    def opportunity_discovery_preferences():
        uid = session.get("user_id")
        if not uid:
            return jsonify({"error": "Not logged in"}), 401
        row = db.session.execute(text("""
            SELECT discoverable, consent_version, updated_at
            FROM student_opportunity_discovery
            WHERE user_id=:uid
        """), {"uid": uid}).mappings().first()
        return jsonify({
            "relevant_opportunities_enabled": bool(row and row["discoverable"]),
            "consent_version": row["consent_version"] if row else "g5-v1",
            "updated_at": row["updated_at"].isoformat() if row and row["updated_at"] else None,
        })

    @app.patch("/api/opportunities/preferences")
    def update_opportunity_discovery_preferences():
        uid = session.get("user_id")
        if not uid:
            return jsonify({"error": "Not logged in"}), 401
        if not csrf_ok():
            return jsonify({"error": "Valid CSRF token required"}), 403
        data = request.get_json(silent=True) or {}
        enabled = data.get("relevant_opportunities_enabled")
        if not isinstance(enabled, bool):
            return jsonify({"error": "relevant_opportunities_enabled must be a boolean"}), 400
        db.session.execute(text("""
            INSERT INTO student_opportunity_discovery (user_id, discoverable, consent_version)
            VALUES (:uid, :enabled, 'g5-v1')
            ON CONFLICT (user_id) DO UPDATE
            SET discoverable=EXCLUDED.discoverable,
                consent_version=EXCLUDED.consent_version,
                updated_at=CURRENT_TIMESTAMP
        """), {"uid": uid, "enabled": enabled})
        db.session.execute(text("""
            INSERT INTO student_opportunity_discovery_audit
                (user_id, discoverable, consent_version, source)
            VALUES (:uid, :enabled, 'g5-v1', 'settings')
        """), {"uid": uid, "enabled": enabled})
        db.session.commit()
        return jsonify({
            "ok": True,
            "relevant_opportunities_enabled": enabled,
            "consent_version": "g5-v1",
        })

    @app.get("/api/organisations/<int:organisation_id>/discovery/pricing")
    def discovery_pricing(organisation_id):
        uid = session.get("user_id")
        if not uid or not org_access(organisation_id, uid):
            return jsonify({"error": "Organisation membership required"}), 403
        return jsonify({"currency": "KES", "pricing": DISCOVERY_PRICING,
                        "push_frequency": {"max_per_48_hours": PUSH_CAP_PER_48_HOURS,
                                           "max_per_7_days": PUSH_CAP_PER_7_DAYS}})

    @app.post("/api/organisations/<int:organisation_id>/discovery/audience-estimate")
    def discovery_audience_estimate(organisation_id):
        uid = session.get("user_id")
        if not uid or not org_access(organisation_id, uid):
            return jsonify({"error":"Organisation membership required"}), 403
        data = request.get_json(silent=True) or {}
        raw_target = data.get("target") if isinstance(data.get("target"), dict) else {}
        try:
            target = normalize_target(raw_target)
            count = len(eligible_users(target))
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid targeting criteria"}), 400
        return jsonify({
            "audience_estimate": count if count >= 10 else None,
            "audience_estimate_available": count >= 10,
            "target": target,
        })

    @app.post("/api/organisations/<int:organisation_id>/discovery/campaigns")
    def create_discovery_campaign(organisation_id):
        uid = session.get("user_id")
        if not uid:
            return jsonify({"error": "Not logged in"}), 401
        if not csrf_ok() or not org_access(organisation_id, uid, owner_only=True):
            return jsonify({"error": "Organisation owner and valid CSRF token required"}), 403
        data = request.get_json(silent=True) or {}
        name = str(data.get("name") or "").strip()[:200]
        placement = str(data.get("placement") or "feed").lower()
        objective = str(data.get("objective") or "reach").lower()
        billing_modes = ["cpm", "cpc"]
        try:
            budget = int(data.get("budget_kes") or 0)
        except (TypeError, ValueError):
            budget = 0
        raw_target = data.get("target") if isinstance(data.get("target"), dict) else {}
        try:
            target = normalize_target(raw_target)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid targeting criteria"}), 400
        if not name or placement not in ("feed", "push", "feed_push"):
            return jsonify({"error": "Campaign name and valid placement are required"}), 400
        opportunity_id = data.get("opportunity_id")
        if opportunity_id is not None:
            try: opportunity_id = int(opportunity_id)
            except (TypeError, ValueError): return jsonify({"error":"Invalid opportunity"}), 400
            opp = db.session.execute(text("SELECT id,status,organisation_id,expiry_date FROM opportunity WHERE id=:id AND organisation_id=:oid"), {"id": opportunity_id, "oid": organisation_id}).mappings().first()
            if not opp or opp["status"] != "published" or opp["expiry_date"] <= datetime.utcnow():
                return jsonify({"error":"Only a published, active organisation opportunity can be sponsored"}), 400
        if objective not in ("reach", "traffic", "applications"):
            return jsonify({"error": "Invalid campaign objective"}), 400
        if placement == "push":
            billing_modes = ["cpm"]
        bid_type = "both" if len(billing_modes) == 2 else billing_modes[0]
        if budget < DISCOVERY_PRICING["minimum_campaign_kes"]:
            return jsonify({"error": f"Minimum campaign budget is KES {DISCOVERY_PRICING['minimum_campaign_kes']:,}"}), 400
        bid = DISCOVERY_PRICING["push_cpm_kes"] if placement == "push" else DISCOVERY_PRICING["feed_cpm_kes"]
        start = data.get("starts_at")
        end = data.get("ends_at")
        try:
            duration_days = int(data.get("duration_days") or data.get("active_days") or 30)
        except (TypeError, ValueError):
            duration_days = 30
        if duration_days not in (7, 30, 90):
            return jsonify({"error":"Campaign maximum delivery window must be 7, 30, or 90 days"}), 400
        if not end:
            from datetime import datetime as _dt, timedelta as _td
            base_start = _dt.fromisoformat(str(start).replace('Z','+00:00')) if start else _dt.utcnow()
            if getattr(base_start, 'tzinfo', None): base_start = base_start.replace(tzinfo=None)
            end = (base_start + _td(days=duration_days)).isoformat()
        plan_code, status, expires_at = org_plan(organisation_id)
        if status in ("suspended", "expired", "past_due"):
            return jsonify({"error": "Organisation billing is not active"}), 402
        audience = eligible_users(target)
        if len(audience) < 10:
            return jsonify({"error": "Target audience must contain at least 10 consented eligible students"}), 400
        db.session.execute(text("""
            INSERT INTO discovery_campaign
                (organisation_id, opportunity_id, name, objective, placement, status,
                 budget_kes, bid_type, bid_kes, target_json, starts_at, ends_at)
            VALUES (:oid, :opp, :name, :objective, :placement, 'draft',
                    :budget, :bid_type, :bid, CAST(:target AS jsonb), :starts, :ends)
        """), {"oid": organisation_id, "opp": opportunity_id, "name": name,
               "objective": objective, "placement": placement, "budget": budget,
               "bid_type": bid_type, "bid": bid, "target": json.dumps({**target, "billing_modes": billing_modes}),
               "starts": start, "ends": end})
        db.session.commit()
        return jsonify({"ok": True, "audience_estimate": len(audience), "campaign": dict(campaign_row(
            db.session.execute(text("SELECT MAX(id) FROM discovery_campaign WHERE organisation_id=:oid"), {"oid": organisation_id}).scalar_one()
        ))}), 201

    @app.get("/api/organisations/<int:organisation_id>/discovery/campaigns")
    def list_discovery_campaigns(organisation_id):
        uid = session.get("user_id")
        if not uid or not org_access(organisation_id, uid):
            return jsonify({"error": "Organisation membership required"}), 403
        rows = db.session.execute(text("""
            SELECT id, name, objective, placement, status, budget_kes, bid_type, bid_kes,
                   delivered_impressions, delivered_clicks, delivered_applications,
                   push_delivered, starts_at, ends_at, created_at
            FROM discovery_campaign WHERE organisation_id=:oid ORDER BY created_at DESC LIMIT 100
        """), {"oid": organisation_id}).mappings().all()
        return jsonify({"campaigns": [dict(r) for r in rows]})

    @app.get("/api/organisations/<int:organisation_id>/discovery/campaigns/<int:campaign_id>")
    def discovery_campaign_detail(organisation_id, campaign_id):
        uid = session.get("user_id")
        if not uid or not org_access(organisation_id, uid):
            return jsonify({"error": "Organisation membership required"}), 403
        row = db.session.execute(text("""
            SELECT * FROM discovery_campaign
            WHERE id=:cid AND organisation_id=:oid
        """), {"cid": campaign_id, "oid": organisation_id}).mappings().first()
        if not row:
            return jsonify({"error": "Campaign not found"}), 404
        target = normalize_target(row["target_json"] or {})
        count = len(eligible_users(target))
        return jsonify({
            "campaign": dict(row),
            "audience_estimate": count if count >= 10 else None,
            "audience_estimate_available": count >= 10,
        })

    @app.patch("/api/organisations/<int:organisation_id>/discovery/campaigns/<int:campaign_id>")
    def update_discovery_campaign(organisation_id, campaign_id):
        uid = session.get("user_id")
        if not uid or not csrf_ok() or not org_access(organisation_id, uid, owner_only=True):
            return jsonify({"error": "Organisation owner and valid CSRF token required"}), 403
        data = request.get_json(silent=True) or {}
        requested = str(data.get("status") or "").lower()
        row = campaign_row(campaign_id)
        if not row or int(row["organisation_id"]) != organisation_id:
            return jsonify({"error": "Campaign not found"}), 404

        current = str(row["status"] or "draft")
        funding = str(row["funding_status"] or "unfunded")
        transitions = {
            "draft": {"pending_payment", "cancelled"},
            "pending_payment": {"draft", "cancelled"},
            "active": {"paused", "completed", "cancelled"},
            "paused": {"active", "completed", "cancelled"},
            "completed": set(),
            "cancelled": set(),
        }
        if requested not in transitions.get(current, set()):
            return jsonify({"error": f"Invalid state transition: {current} -> {requested}"}), 409

        if requested == "active" and funding not in ("funded", "credited"):
            return jsonify({"error": "Campaign must be fully funded before activation"}), 409
        if requested == "active":
            try:
                if len(eligible_users(normalize_target(row["target_json"] or {}))) < 10:
                    return jsonify({"error": "Campaign cannot activate with fewer than 10 consented eligible students"}), 409
            except (ValueError, TypeError):
                return jsonify({"error": "Campaign targeting is invalid"}), 409

        if requested == "active":
            now = datetime.utcnow()
            db.session.execute(text("""
                UPDATE discovery_campaign
                SET status='active', activated_at=COALESCE(activated_at,:now), updated_at=CURRENT_TIMESTAMP
                WHERE id=:cid AND organisation_id=:oid AND funding_status IN ('funded','credited')
                  AND status='paused'
            """), {"cid": campaign_id, "oid": organisation_id, "now": now})
        elif requested == "paused":
            db.session.execute(text("""
                UPDATE discovery_campaign SET status='paused', updated_at=CURRENT_TIMESTAMP
                WHERE id=:cid AND organisation_id=:oid AND status='active'
            """), {"cid": campaign_id, "oid": organisation_id})
        elif requested in ("completed", "cancelled"):
            db.session.execute(text("""
                UPDATE discovery_campaign SET status=:status, updated_at=CURRENT_TIMESTAMP
                WHERE id=:cid AND organisation_id=:oid AND status IN ('active','paused','pending_payment','draft')
            """), {"status": requested, "cid": campaign_id, "oid": organisation_id})
        else:
            db.session.execute(text("""
                UPDATE discovery_campaign SET status=:status, updated_at=CURRENT_TIMESTAMP
                WHERE id=:cid AND organisation_id=:oid AND status=:current
            """), {"status": requested, "cid": campaign_id, "oid": organisation_id, "current": current})
        db.session.commit()
        return jsonify({"ok": True, "from": current, "to": requested})

    @app.post("/api/discovery/campaigns/<int:campaign_id>/impression")
    def discovery_impression(campaign_id):
        uid = session.get("user_id")
        if not uid:
            return jsonify({"error": "Not logged in"}), 401
        row = campaign_row(campaign_id)
        if not row:
            return jsonify({"error": "Campaign unavailable"}), 404
        target = row["target_json"] or {}
        if not target_matches(uid, target):
            return jsonify({"eligible": False}), 200
        data = request.get_json(silent=True) or {}
        supplied_key = str(data.get("event_id") or "").strip()
        event_key = f"imp:{campaign_id}:{uid}:{supplied_key[:100]}" if supplied_key else f"imp:{campaign_id}:{uid}:{secrets.token_hex(16)}"
        result = record_billable_event(db, campaign_id, uid, "impression", row["placement"], event_key)
        if result.get("ok"):
            db.session.commit()
            return jsonify({"eligible": True, "recorded": not result.get("duplicate"), "amount_minor": result.get("amount_minor", 0),
                            "remaining_minor": result.get("remaining_minor")}), 200
        db.session.rollback()
        if result.get("reason") in ("campaign_budget_exhausted", "campaign_not_funded", "student_frequency_cap"):
            return jsonify({"eligible": False, "code": result["reason"], "remaining_minor": result.get("remaining_minor", 0)}), 200
        if result.get("reason") == "campaign_inactive":
            return jsonify({"error": "Campaign unavailable"}), 404
        return jsonify({"eligible": False, "code": result.get("reason", "meter_rejected")}), 200


    @app.post("/api/discovery/campaigns/<int:campaign_id>/click")
    def discovery_click(campaign_id):
        uid = session.get("user_id")
        if not uid:
            return jsonify({"error": "Not logged in"}), 401
        row = campaign_row(campaign_id)
        if not row:
            return jsonify({"error": "Campaign unavailable"}), 404
        if not target_matches(uid, row["target_json"] or {}):
            return jsonify({"eligible": False}), 200
        event_key = f"click:{campaign_id}:{uid}:{secrets.token_hex(16)}"
        result = record_billable_event(db, campaign_id, uid, "click", row["placement"], event_key)
        if result.get("ok"):
            db.session.commit()
            return jsonify({"eligible": True, "recorded": True, "amount_minor": result.get("amount_minor", 0),
                            "remaining_minor": result.get("remaining_minor")}), 200
        db.session.rollback()
        if result.get("reason") in ("campaign_budget_exhausted", "campaign_not_funded"):
            return jsonify({"eligible": False, "code": result["reason"], "remaining_minor": result.get("remaining_minor", 0)}), 200
        if result.get("reason") == "campaign_inactive":
            return jsonify({"error": "Campaign unavailable"}), 404
        return jsonify({"eligible": False, "code": result.get("reason", "meter_rejected")}), 200


    @app.post("/api/discovery/campaigns/<int:campaign_id>/application")
    def discovery_application(campaign_id):
        uid = session.get("user_id")
        if not uid:
            return jsonify({"error": "Not logged in"}), 401
        row = campaign_row(campaign_id)
        if not row or row["status"] != "active":
            return jsonify({"error": "Campaign unavailable"}), 404
        if not target_matches(uid, row["target_json"] or {}):
            return jsonify({"eligible": False}), 200
        key = f"application:{campaign_id}:{uid}:{secrets.token_hex(16)}"
        db.session.execute(text("""
            INSERT INTO discovery_event
                (campaign_id,user_id,event_key,event_type,placement,amount_kes,metadata)
            VALUES (:cid,:uid,:key,'application',:placement,0,CAST(:meta AS jsonb))
        """), {"cid": campaign_id, "uid": uid, "key": key, "placement": row["placement"],
               "meta": json.dumps({"verified": True, "billable": False})})
        db.session.execute(text("""
            UPDATE discovery_campaign SET delivered_applications=delivered_applications+1,
              updated_at=CURRENT_TIMESTAMP WHERE id=:cid
        """), {"cid": campaign_id})
        db.session.commit()
        return jsonify({"eligible": True, "recorded": True})


    @app.get("/api/organisations/<int:organisation_id>/discovery/billing-preview")
    def discovery_billing_preview(organisation_id):
        uid = session.get("user_id")
        if not uid or not org_access(organisation_id, uid):
            return jsonify({"error":"Organisation membership required"}), 403
        total, usage, paid = sync_org_invoice(organisation_id)
        base = db.session.execute(text("""SELECT COALESCE(monthly_fee_kes,0) FROM organisation_billing WHERE organisation_id=:oid"""), {"oid":organisation_id}).scalar_one_or_none() or 0
        return jsonify({"currency":"KES","base_plan_kes":int(base),"discovery_usage_kes":int(usage),"current_invoice_kes":int(total),"invoice_locked":bool(paid)})

    @app.get("/api/organisations/<int:organisation_id>/discovery/campaigns/<int:campaign_id>/invoice-preview")
    def discovery_invoice_preview(organisation_id, campaign_id):
        uid = session.get("user_id")
        if not uid or not org_access(organisation_id, uid):
            return jsonify({"error": "Organisation membership required"}), 403
        row = campaign_row(campaign_id)
        if not row or int(row["organisation_id"]) != organisation_id:
            return jsonify({"error": "Campaign not found"}), 404
        ledger_net_minor = db.session.execute(text("""
            SELECT COALESCE(SUM(signed_amount_minor),0)
            FROM b2b_campaign_ledger WHERE campaign_id=:cid
        """), {"cid": campaign_id}).scalar_one()
        funded_minor = int(row["funded_amount_minor"] or 0)
        remaining_minor = max(0, funded_minor + int(ledger_net_minor))
        spent_minor = max(0, -int(ledger_net_minor))
        return jsonify({
            "currency": "KES",
            "spent_kes": spent_minor / 100,
            "budget_kes": int(row["budget_kes"]),
            "funded_kes": funded_minor / 100,
            "remaining_kes": remaining_minor / 100,
            "billing_basis": "append-only prepaid campaign ledger",
        })

    @app.post("/api/organisations/<int:organisation_id>/discovery/campaigns/<int:campaign_id>/push")
    def discovery_send_push(organisation_id, campaign_id):
        uid = session.get("user_id")
        if not uid or not csrf_ok() or not org_access(organisation_id, uid, owner_only=True):
            return jsonify({"error": "Organisation owner and valid CSRF token required"}), 403
        row = campaign_row(campaign_id)
        if not row or int(row["organisation_id"]) != organisation_id:
            return jsonify({"error": "Campaign not found"}), 404
        if row["placement"] not in ("push", "feed_push") or row["status"] != "active":
            return jsonify({"error": "Campaign is not active push inventory"}), 400
        if str(row["funding_status"] or "") not in ("funded", "credited"):
            return jsonify({"error": "Campaign is not funded"}), 402

        target = row["target_json"] or {}
        user_ids = eligible_users(target)
        # Final frequency enforcement happens inside the atomic metering
        # transaction. Keep all otherwise eligible recipients in the queue so
        # concurrent campaigns cannot bypass or accidentally double-apply caps.
        allowed_ids = list(user_ids)

        subscriptions = push_subscription_rows(allowed_ids)
        queued = 0
        for sub in subscriptions:
            inserted = db.session.execute(text("""
                INSERT INTO discovery_push_delivery
                    (campaign_id,user_id,subscription_endpoint,status)
                VALUES (:cid,:uid,:endpoint,'queued')
                ON CONFLICT (campaign_id,user_id) DO NOTHING
                RETURNING id
            """), {"cid": campaign_id, "uid": sub["user_id"], "endpoint": sub["endpoint"]}).first()
            if inserted:
                queued += 1
        db.session.commit()

        sent = 0
        failed = 0
        skipped = 0
        vapid_private = os.environ.get("VAPID_PRIVATE_KEY")
        vapid_public = os.environ.get("VAPID_PUBLIC_KEY")
        vapid_email = os.environ.get("VAPID_CLAIMS_EMAIL")
        key_by_endpoint = {sub["endpoint"]: sub.get("keys") for sub in subscriptions}

        if vapid_private and vapid_public and vapid_email and queued:
            pending = db.session.execute(text("""
                SELECT id,user_id,subscription_endpoint FROM discovery_push_delivery
                WHERE campaign_id=:cid AND status='queued' LIMIT 500
            """), {"cid": campaign_id}).mappings().all()
            payload = json.dumps({"title": row["name"], "body": "A new opportunity matched your Prepza interests.", "campaign_id": campaign_id})

            for item in pending:
                event_key = f"push:{campaign_id}:{int(item['user_id'])}:{int(item['id'])}"
                reserve = record_billable_event(
                    db, campaign_id, int(item["user_id"]), "push_delivery",
                    row["placement"], event_key
                )
                if not reserve.get("ok"):
                    db.session.rollback()
                    db.session.execute(text("""
                        UPDATE discovery_push_delivery
                        SET status='budget_exhausted', provider_response=:reason
                        WHERE id=:id AND status='queued'
                    """), {"id": int(item["id"]), "reason": reserve.get("reason", "meter_rejected")})
                    db.session.commit()
                    skipped += 1
                    continue

                try:
                    keys = key_by_endpoint.get(item["subscription_endpoint"]) or {}
                    if isinstance(keys, str):
                        try:
                            keys = json.loads(keys)
                        except Exception:
                            keys = {}
                    webpush(subscription_info={
                        "endpoint": item["subscription_endpoint"], "keys": keys
                    }, data=payload, vapid_private_key=vapid_private,
                    vapid_claims={"sub": vapid_email})
                except Exception as exc:
                    db.session.rollback()
                    reverse_billable_event(db, event_key, "push_delivery_failed")
                    db.session.execute(text("""
                        UPDATE discovery_push_delivery
                        SET status='failed', provider_response=:response
                        WHERE id=:id AND status='queued'
                    """), {"id": int(item["id"]), "response": str(exc)[:500]})
                    db.session.commit()
                    failed += 1
                    continue

                db.session.execute(text("""
                    UPDATE discovery_push_delivery
                    SET status='sent', sent_at=CURRENT_TIMESTAMP
                    WHERE id=:id AND status='queued'
                """), {"id": int(item["id"])})
                db.session.commit()
                sent += 1

        return jsonify({
            "ok": True,
            "eligible_recipients": len(allowed_ids),
            "queued": queued,
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
            "billing": "atomic prepaid delivery metering",
            "note": "Each successful push delivery consumes prepaid campaign balance and is frequency-capped."
        })


    @app.get("/api/opportunity-discovery")
    def legacy_discovery_preference_get():
        uid=session.get("user_id")
        if not uid: return jsonify({"error":"Not logged in"}),401
        value=db.session.execute(text("SELECT COALESCE(discoverable,FALSE) FROM student_opportunity_discovery WHERE user_id=:uid"),{"uid":uid}).scalar_one_or_none()
        return jsonify({"discoverable":bool(value)})

    @app.post("/api/opportunity-discovery")
    def legacy_discovery_preference_set():
        uid=session.get("user_id")
        if not uid: return jsonify({"error":"Not logged in"}),401
        if not csrf_ok(): return jsonify({"error":"Invalid CSRF token"}),403
        data=request.get_json(silent=True) or {}
        value=bool(data.get("discoverable"))
        db.session.execute(text("""
            INSERT INTO student_opportunity_discovery(user_id,discoverable,updated_at)
            VALUES(:uid,:value,CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET discoverable=:value,updated_at=CURRENT_TIMESTAMP
        """),{"uid":uid,"value":value})
        db.session.commit()
        return jsonify({"ok":True,"discoverable":value})

    @app.get("/api/discovery/preferences")
    def discovery_preferences():
        uid = session.get("user_id")
        if not uid: return jsonify({"error":"Not logged in"}), 401
        value = db.session.execute(text("SELECT COALESCE(discoverable,FALSE) FROM student_opportunity_discovery WHERE user_id=:uid"), {"uid":uid}).scalar_one_or_none()
        return jsonify({"discoverable": bool(value)})

    @app.patch("/api/discovery/preferences")
    def update_discovery_preferences():
        uid = session.get("user_id")
        if not uid: return jsonify({"error":"Not logged in"}), 401
        if not csrf_ok(): return jsonify({"error":"Invalid CSRF token"}), 403
        data=request.get_json(silent=True) or {}
        discoverable=bool(data.get("discoverable"))
        db.session.execute(text("""
            INSERT INTO student_opportunity_discovery(user_id,discoverable,updated_at)
            VALUES(:uid,:value,CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET discoverable=:value,updated_at=CURRENT_TIMESTAMP
        """), {"uid":uid,"value":discoverable})
        db.session.commit()
        return jsonify({"ok":True,"discoverable":discoverable})

    @app.get("/api/discovery/feed")
    def discovery_feed():
        uid = session.get("user_id")
        if not uid:
            return jsonify({"error": "Not logged in"}), 401
        rows = db.session.execute(text("""
            SELECT id, organisation_id, opportunity_id, name, objective, placement,
                   bid_type, bid_kes, target_json
            FROM discovery_campaign
            WHERE status='active'
              AND funding_status IN ('funded','credited')
              AND placement IN ('feed','feed_push')
              AND (starts_at IS NULL OR starts_at <= CURRENT_TIMESTAMP)
              AND (ends_at IS NULL OR ends_at >= CURRENT_TIMESTAMP)
              AND delivered_impressions < GREATEST(1, budget_kes * 1000 / GREATEST(1,bid_kes))
            ORDER BY updated_at DESC LIMIT 50
        """)).mappings().all()
        feed=[]
        for r in rows:
            if not target_matches(uid, r["target_json"] or {}):
                continue
            feed.append({
                "campaign_id": int(r["id"]), "organisation_id": int(r["organisation_id"]),
                "opportunity_id": int(r["opportunity_id"]) if r["opportunity_id"] else None,
                "name": r["name"], "objective": r["objective"], "placement": r["placement"],
            })
            if len(feed) >= 10:
                break
        return jsonify({"campaigns": feed})

    @app.get("/api/admin/discovery/pricing")
    def admin_discovery_pricing():
        uid = session.get("user_id")
        allowed = session.get("is_admin") is True or session.get("role") in ("admin","superadmin")
        configured = {int(x.strip()) for x in os.environ.get("PREPZA_ADMIN_USER_IDS","").split(",") if x.strip().isdigit()}
        if not uid or not (allowed or int(uid) in configured):
            return jsonify({"error":"Admin access required"}), 403
        return jsonify({"pricing": DISCOVERY_PRICING, "push_caps": {"48h": PUSH_CAP_PER_48_HOURS, "7d": PUSH_CAP_PER_7_DAYS}})

    @app.get("/api/organisations/<int:organisation_id>/discovery/summary")
    def discovery_summary(organisation_id):
        uid = session.get("user_id")
        if not uid or not org_access(organisation_id, uid):
            return jsonify({"error": "Organisation membership required"}), 403
        rows = db.session.execute(text("""
            SELECT id,name,status,budget_kes,bid_type,bid_kes,placement,
                   delivered_impressions,delivered_clicks,delivered_applications,push_delivered
            FROM discovery_campaign WHERE organisation_id=:oid ORDER BY created_at DESC
        """), {"oid": organisation_id}).mappings().all()
        total_spend_minor = 0
        enriched = []
        for r in rows:
            net = db.session.execute(text("""
                SELECT COALESCE(SUM(signed_amount_minor),0)
                FROM b2b_campaign_ledger WHERE campaign_id=:cid
            """), {"cid": int(r["id"])}).scalar_one()
            funded = db.session.execute(text("""
                SELECT COALESCE(funded_amount_minor,0)
                FROM discovery_campaign WHERE id=:cid
            """), {"cid": int(r["id"])}).scalar_one() or 0
            spent_minor = max(0, -int(net))
            remaining_minor = max(0, int(funded) + int(net))
            item = dict(r)
            item.update({
                "funded_kes": int(funded) / 100,
                "spent_kes": spent_minor / 100,
                "remaining_kes": remaining_minor / 100,
            })
            enriched.append(item)
            total_spend_minor += spent_minor
        return jsonify({"currency": "KES", "pricing": DISCOVERY_PRICING,
                        "campaigns": enriched, "prepaid_ledger_spend_kes": total_spend_minor / 100})

    return None
