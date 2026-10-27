"""Prepza Discovery campaigns, targeting, metering and sponsored push delivery.

The organisation owns campaign configuration; Prepza owns the audience selection.
Advertisers receive aggregate campaign analytics, never the underlying student list.
"""
from __future__ import annotations

import csv
import io
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, date, time, timezone
from zoneinfo import ZoneInfo
from flask import Response, jsonify, request, session
from sqlalchemy import text
from pywebpush import webpush
from b2b_campaign_metering import record_billable_event, reverse_billable_event
from usage_billing import get_organisation_plans

PUSH_CAP_PER_48_HOURS = 1
PUSH_CAP_PER_7_DAYS = 3


def _normalize_billable_event_id(value):
    """Return a canonical UUID for retry-safe client event submissions, else None."""
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 36:
        return None
    try:
        parsed = uuid.UUID(value.strip())
    except (ValueError, AttributeError, TypeError):
        return None
    # Require the canonical UUID textual length to reject truncated/ambiguous IDs.
    return str(parsed) if len(value.strip()) == 36 else None


def _canonical_discovery_pricing(db):
    """Read sponsored-campaign economics from the canonical B2B pricing table."""
    rows = db.session.execute(text("""
        SELECT config_key, value_json
        FROM b2b_pricing_config
        WHERE is_active = TRUE
          AND config_key IN ('sponsored_campaign_minimum','home_impression_cpm','click_cpc','push_delivery_cpm')
    """)).mappings().all()
    values = {str(r["config_key"]): (r["value_json"] if isinstance(r["value_json"], dict) else {}) for r in rows}
    def amount(key):
        return int((values.get(key) or {}).get("amount_kes") or 0)
    return {
        "feed_cpm_kes": amount("home_impression_cpm"),
        "click_cpc_kes": amount("click_cpc"),
        "push_cpm_kes": amount("push_delivery_cpm"),
        "minimum_campaign_kes": amount("sponsored_campaign_minimum"),
    }


def _register_discovery_schema(db):

    if db.engine.dialect.name == "sqlite":
        return
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
            bid_kes INTEGER NOT NULL DEFAULT 0,
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
            amount_kes NUMERIC(12,4) NOT NULL DEFAULT 0,
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

def member_role(db, org_id, user_id):
    return db.session.execute(text("""
        SELECT role FROM organisation_member
        WHERE organisation_id = :oid AND user_id = :uid LIMIT 1
    """), {"oid": org_id, "uid": user_id}).scalar_one_or_none()


def register_discovery(app, db):
    with app.app_context():
        _register_discovery_schema(db)

    def org_access(org_id, user_id, owner_only=False):
        role = member_role(db, org_id, user_id)
        return role == "owner" if owner_only else role in ("owner", "manager")

    def org_plan(org_id):
        row = db.session.execute(text("""
            SELECT plan_code, status, expires_at
            FROM organisation_billing WHERE organisation_id = :oid
        """), {"oid": org_id}).mappings().first()
        if not row:
            return "launch", "trial", None
        return str(row["plan_code"]), str(row["status"]), row["expires_at"]

    # billing_modes lives alongside audience dimensions in target_json because
    # the existing prepaid meter freezes both audience and billing eligibility
    # with the campaign snapshot. Keep it through normalization instead of
    # rejecting every campaign created by this same route.
    ALLOWED_TARGET_KEYS = {"university_ids", "program_ids", "years", "active_days", "billing_modes"}

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
        billing_modes = raw_target.get("billing_modes")
        if billing_modes is not None:
            if not isinstance(billing_modes, list) or not billing_modes:
                raise ValueError("billing_modes must be a non-empty list")
            normalized_modes = []
            for mode in billing_modes:
                value = str(mode).strip().lower()
                if value not in ("cpm", "cpc"):
                    raise ValueError("billing_modes may contain only cpm and cpc")
                if value not in normalized_modes:
                    normalized_modes.append(value)
            target["billing_modes"] = normalized_modes
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
        return jsonify({"currency": "KES", "pricing": _canonical_discovery_pricing(db),
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
        if not name or placement not in ("feed", "home_carousel", "explore", "trending", "opportunities_feed", "feed_push", "podcast", "push"):
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
        pricing = _canonical_discovery_pricing(db)
        if budget < pricing["minimum_campaign_kes"]:
            return jsonify({"error": f"Minimum campaign budget is KES {pricing['minimum_campaign_kes']:,}"}), 400
        bid = pricing["push_cpm_kes"] if placement == "push" else pricing["feed_cpm_kes"]
        start = data.get("starts_at")
        end = data.get("ends_at")
        try:
            duration_days = int(data.get("duration_days") or data.get("active_days") or 30)
        except (TypeError, ValueError):
            duration_days = 30
        if duration_days not in (7, 30, 90):
            return jsonify({"error":"Campaign maximum delivery window must be 7, 30, or 90 days"}), 400
        from datetime import datetime as _dt, timedelta as _td
        base_start = _dt.fromisoformat(str(start).replace('Z','+00:00')) if start else _dt.utcnow()
        if getattr(base_start, 'tzinfo', None): base_start = base_start.replace(tzinfo=None)
        canonical_end = base_start + _td(days=duration_days)
        if end:
            try:
                supplied_end = _dt.fromisoformat(str(end).replace('Z','+00:00'))
                if getattr(supplied_end, 'tzinfo', None): supplied_end = supplied_end.replace(tzinfo=None)
            except ValueError:
                return jsonify({"error":"Invalid campaign end time"}), 400
            if supplied_end != canonical_end:
                return jsonify({"error":"Campaign end must match the selected 7, 30, or 90-day window"}), 400
        end = canonical_end.isoformat()
        org_state = db.session.execute(text("SELECT verification_status,is_active FROM organisation WHERE id=:oid"), {"oid": organisation_id}).mappings().first()
        if not org_state or org_state["verification_status"] != "verified" or not org_state["is_active"]:
            return jsonify({"error":"Organisation verification must be complete before paid sponsorships can be created"}), 403
        plan_code, status, expires_at = org_plan(organisation_id)
        if status in ("suspended", "expired", "past_due"):
            return jsonify({"error": "Organisation billing is not active"}), 402
        plan_limits = get_organisation_plans(db).get(plan_code, get_organisation_plans(db).get("launch", {}))
        active_sponsorships = db.session.execute(text("""
            SELECT COUNT(*) FROM discovery_campaign
            WHERE organisation_id=:oid
              AND status IN ('draft','pending_payment','active','paused')
        """), {"oid": organisation_id}).scalar_one()
        if int(active_sponsorships) >= int(plan_limits.get("sponsored_campaigns", 1)):
            return jsonify({"error": f"Your {plan_code.title()} organisation plan has reached its sponsored-campaign capacity. Upgrade your plan or finish an existing campaign first."}), 403
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
        supplied_key = _normalize_billable_event_id(data.get("event_id"))
        if not supplied_key:
            return jsonify({"error": "A stable event_id UUID is required"}), 400
        event_key = f"imp:{campaign_id}:{uid}:{supplied_key}"
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
        data = request.get_json(silent=True) or {}
        supplied_key = _normalize_billable_event_id(data.get("event_id"))
        if not supplied_key:
            return jsonify({"error": "A stable event_id UUID is required"}), 400

        event_key = f"click:{campaign_id}:{uid}:{supplied_key}"
        raw_event_key = f"rawclick:{campaign_id}:{uid}:{supplied_key}"

        # Match the meter's campaign -> user lock order. This makes the
        # 750ms anti-double-tap window race-safe for concurrent requests.
        db.session.execute(
            text("SELECT id FROM discovery_campaign WHERE id=:cid FOR UPDATE"),
            {"cid": campaign_id},
        ).first()
        db.session.execute(
            text('SELECT id FROM "user" WHERE id=:uid FOR UPDATE'),
            {"uid": uid},
        ).first()

        previous_raw = db.session.execute(text("""
            SELECT metadata FROM discovery_event WHERE event_key=:key
        """), {"key": raw_event_key}).mappings().first()
        if previous_raw:
            metadata = previous_raw["metadata"] if isinstance(previous_raw["metadata"], dict) else {}
            return jsonify({
                "eligible": True,
                "recorded": True,
                "duplicate": True,
                "billable": bool(metadata.get("billable")),
                "amount_minor": int(metadata.get("amount_minor") or 0),
                "billing_reason": metadata.get("billing_reason"),
            }), 200

        latest_raw = db.session.execute(text("""
            SELECT created_at FROM discovery_event
            WHERE campaign_id=:cid AND user_id=:uid AND event_type='click_raw'
            ORDER BY created_at DESC LIMIT 1
        """), {"cid": campaign_id, "uid": uid}).scalar_one_or_none()
        if latest_raw:
            if isinstance(latest_raw, str):
                try:
                    latest_raw = datetime.fromisoformat(latest_raw)
                except ValueError:
                    latest_raw = None
            if latest_raw is not None:
                if getattr(latest_raw, "tzinfo", None) is not None:
                    latest_raw = latest_raw.astimezone(timezone.utc).replace(tzinfo=None)
                if datetime.utcnow() - latest_raw < timedelta(milliseconds=750):
                    return jsonify({
                        "eligible": True, "recorded": False,
                        "debounced": True, "billable": False,
                    }), 200

        result = record_billable_event(
            db, campaign_id, uid, "click", row["placement"], event_key
        )
        reason = result.get("reason")
        raw_click_is_valid = bool(result.get("ok")) or reason in (
            "student_frequency_cap", "campaign_budget_exhausted", "campaign_not_funded"
        )
        if not raw_click_is_valid:
            db.session.rollback()
            if reason == "campaign_inactive":
                return jsonify({"error": "Campaign unavailable"}), 404
            if reason == "click_without_impression":
                return jsonify({"eligible": False, "code": reason}), 200
            return jsonify({
                "eligible": False,
                "code": reason or "meter_rejected",
                "remaining_minor": result.get("remaining_minor", 0),
            }), 200

        # Raw interaction analytics is deliberately separate from billable
        # click events. Rate-limited taps can appear in reporting without
        # becoming ledger entries or changing delivered_clicks.
        campus_id = db.session.execute(
            text('SELECT university_id FROM "user" WHERE id=:uid'),
            {"uid": uid},
        ).scalar_one_or_none()
        raw_metadata = {
            "raw_click": True,
            "billable": bool(result.get("ok")),
            "billing_reason": None if result.get("ok") else reason,
            "amount_minor": int(result.get("amount_minor") or 0),
            "client_event_id": supplied_key,
            "campus_id": int(campus_id) if campus_id is not None else None,
            "meter_version": "b2b-click-telemetry-v1",
        }
        db.session.execute(text("""
            INSERT INTO discovery_event
                (campaign_id,user_id,event_key,event_type,placement,amount_kes,metadata)
            VALUES (:cid,:uid,:key,'click_raw',:placement,0,CAST(:metadata AS jsonb))
            ON CONFLICT (event_key) DO NOTHING
        """), {
            "cid": campaign_id, "uid": uid, "key": raw_event_key,
            "placement": row["placement"], "metadata": json.dumps(raw_metadata),
        })
        db.session.commit()
        return jsonify({
            "eligible": True,
            "recorded": True,
            "billable": bool(result.get("ok")),
            "amount_minor": int(result.get("amount_minor") or 0),
            "billing_reason": reason,
            "remaining_minor": result.get("remaining_minor"),
        }), 200


    def _discovery_report_window():
        """Convert Nairobi calendar dates to UTC-naive database timestamps."""
        today = datetime.now(ZoneInfo("Africa/Nairobi")).date()
        try:
            end_day = date.fromisoformat(request.args.get("end_date") or today.isoformat())
            start_day = date.fromisoformat(
                request.args.get("start_date") or (end_day - timedelta(days=29)).isoformat()
            )
        except (TypeError, ValueError):
            return None, None, "start_date and end_date must use YYYY-MM-DD"
        if start_day > end_day:
            return None, None, "start_date must be on or before end_date"
        if (end_day - start_day).days > 365:
            return None, None, "Report range cannot exceed 366 calendar days"
        tz = ZoneInfo("Africa/Nairobi")
        start_utc = datetime.combine(start_day, time.min, tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)
        end_utc = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)
        return (start_day, end_day, start_utc, end_utc), None, None


    @app.get("/api/organisations/<int:organisation_id>/discovery/report")
    def discovery_advertiser_report(organisation_id):
        uid = session.get("user_id")
        if not uid or not org_access(organisation_id, uid):
            return jsonify({"error": "Organisation membership required"}), 403
        window, _unused, error = _discovery_report_window()
        if error:
            return jsonify({"error": error}), 400
        start_day, end_day, start_utc, end_utc = window
        raw_campaign_filter = request.args.get("campaign_id")
        raw_university_filter = request.args.get("university_id")
        campaign_id_filter = request.args.get("campaign_id", type=int)
        university_id_filter = request.args.get("university_id", type=int)
        if raw_campaign_filter not in (None, "") and (
            campaign_id_filter is None or campaign_id_filter <= 0
        ):
            return jsonify({"error": "campaign_id must be a positive integer"}), 400
        if raw_university_filter not in (None, "") and (
            university_id_filter is None or university_id_filter <= 0
        ):
            return jsonify({"error": "university_id must be a positive integer"}), 400
        rows = db.session.execute(text("""
            WITH event_totals AS (
                SELECT campaign_id,
                    COUNT(*) FILTER (
                        WHERE event_type='impression'
                          AND COALESCE((metadata->>'reversed')::boolean,FALSE)=FALSE
                    ) AS impressions,
                    COUNT(DISTINCT user_id) FILTER (
                        WHERE event_type='impression'
                          AND COALESCE((metadata->>'reversed')::boolean,FALSE)=FALSE
                    ) AS unique_reach,
                    COUNT(*) FILTER (WHERE event_type='click_raw') AS raw_clicks,
                    COUNT(DISTINCT user_id) FILTER (WHERE event_type='click_raw') AS unique_clicks,
                    COUNT(*) FILTER (
                        WHERE event_type='click'
                          AND COALESCE((metadata->>'reversed')::boolean,FALSE)=FALSE
                    ) AS billable_clicks,
                    COUNT(DISTINCT user_id) FILTER (
                        WHERE event_type='click'
                          AND COALESCE((metadata->>'reversed')::boolean,FALSE)=FALSE
                    ) AS unique_billable_clickers
                FROM discovery_event
                WHERE created_at >= :start_utc AND created_at < :end_utc
                  AND (:university_id IS NULL OR
                       COALESCE(NULLIF(metadata->>'campus_id','')::integer,0)=:university_id)
                GROUP BY campaign_id
            ),
            ledger_totals AS (
                SELECT l.campaign_id,
                    GREATEST(0,
                        -COALESCE(SUM(l.signed_amount_minor) FILTER (
                            WHERE entry_type IN (
                                'delivery_impression','delivery_click','delivery_push_delivery'
                            ) OR entry_type='delivery_reversal'
                        ),0)
                    ) AS net_spend_minor
                FROM b2b_campaign_ledger l
                LEFT JOIN discovery_event de ON de.id=l.delivery_event_id
                WHERE l.created_at >= :start_utc AND l.created_at < :end_utc
                  AND (:university_id IS NULL OR
                       COALESCE(NULLIF(de.metadata->>'campus_id','')::integer,0)=:university_id)
                GROUP BY l.campaign_id
            )
            SELECT c.id AS campaign_id, c.name AS campaign_name, c.placement,
                   COALESCE(e.impressions,0) AS impressions,
                   COALESCE(e.unique_reach,0) AS unique_reach,
                   COALESCE(e.raw_clicks,0) AS raw_clicks,
                   COALESCE(e.unique_clicks,0) AS unique_clicks,
                   COALESCE(e.billable_clicks,0) AS billable_clicks,
                   COALESCE(e.unique_billable_clickers,0) AS unique_billable_clickers,
                   COALESCE(l.net_spend_minor,0) AS net_spend_minor
            FROM discovery_campaign c
            LEFT JOIN event_totals e ON e.campaign_id=c.id
            LEFT JOIN ledger_totals l ON l.campaign_id=c.id
            WHERE c.organisation_id=:oid
              AND (:campaign_id IS NULL OR c.id=:campaign_id)
            ORDER BY c.id DESC
        """), {
            "oid": organisation_id,
            "start_utc": start_utc,
            "end_utc": end_utc,
            "campaign_id": campaign_id_filter,
            "university_id": university_id_filter,
        }).mappings().all()

        # Campus reporting is aggregated at the campaign/campus level.
        # A campus row is suppressed unless at least ten distinct accounts
        # saw the campaign in the selected period. Student ids/emails are
        # never serialized to advertiser reports.
        campus_rows = db.session.execute(text("""
            WITH campus_events AS (
                SELECT campaign_id,
                    COALESCE(NULLIF(metadata->>'campus_id','')::integer,0) AS campus_id,
                    COUNT(*) FILTER (
                        WHERE event_type='impression'
                          AND COALESCE((metadata->>'reversed')::boolean,FALSE)=FALSE
                    ) AS impressions,
                    COUNT(DISTINCT user_id) FILTER (
                        WHERE event_type='impression'
                          AND COALESCE((metadata->>'reversed')::boolean,FALSE)=FALSE
                    ) AS unique_reach,
                    COUNT(*) FILTER (WHERE event_type='click_raw') AS raw_clicks,
                    COUNT(DISTINCT user_id) FILTER (WHERE event_type='click_raw') AS unique_clicks,
                    COUNT(*) FILTER (
                        WHERE event_type='click'
                          AND COALESCE((metadata->>'reversed')::boolean,FALSE)=FALSE
                    ) AS billable_clicks,
                    COUNT(DISTINCT user_id) FILTER (
                        WHERE event_type='click'
                          AND COALESCE((metadata->>'reversed')::boolean,FALSE)=FALSE
                    ) AS unique_billable_clickers
                FROM discovery_event
                WHERE created_at >= :start_utc AND created_at < :end_utc
                  AND (:university_id IS NULL OR
                       COALESCE(NULLIF(metadata->>'campus_id','')::integer,0)=:university_id)
                GROUP BY campaign_id, COALESCE(NULLIF(metadata->>'campus_id','')::integer,0)
            ),
            campus_ledger AS (
                SELECT e.campaign_id,
                    COALESCE(NULLIF(e.metadata->>'campus_id','')::integer,0) AS campus_id,
                    GREATEST(0, -COALESCE(SUM(l.signed_amount_minor) FILTER (
                        WHERE l.entry_type IN (
                            'delivery_impression','delivery_click','delivery_push_delivery','delivery_reversal'
                        )
                    ),0)) AS net_spend_minor
                FROM b2b_campaign_ledger l
                JOIN discovery_event e ON e.id=l.delivery_event_id
                WHERE l.created_at >= :start_utc AND l.created_at < :end_utc
                GROUP BY e.campaign_id,
                    COALESCE(NULLIF(e.metadata->>'campus_id','')::integer,0)
            )
            SELECT ce.campaign_id, ce.campus_id, u.name AS campus_name,
                   COALESCE(ce.impressions,0) AS impressions,
                   COALESCE(ce.unique_reach,0) AS unique_reach,
                   COALESCE(ce.raw_clicks,0) AS raw_clicks,
                   COALESCE(ce.unique_clicks,0) AS unique_clicks,
                   COALESCE(ce.billable_clicks,0) AS billable_clicks,
                   COALESCE(ce.unique_billable_clickers,0) AS unique_billable_clickers,
                   COALESCE(cl.net_spend_minor,0) AS net_spend_minor
            FROM campus_events ce
            JOIN discovery_campaign c ON c.id=ce.campaign_id
            LEFT JOIN university u ON u.id=NULLIF(ce.campus_id,0)
            LEFT JOIN campus_ledger cl
              ON cl.campaign_id=ce.campaign_id AND cl.campus_id=ce.campus_id
            WHERE c.organisation_id=:oid
              AND (:campaign_id IS NULL OR c.id=:campaign_id)
            ORDER BY ce.campaign_id, u.name
        """), {
            "oid": organisation_id,
            "start_utc": start_utc,
            "end_utc": end_utc,
            "campaign_id": campaign_id_filter,
            "university_id": university_id_filter,
        }).mappings().all()

        campus_by_campaign = {}
        for campus in campus_rows:
            campus_id = int(campus["campus_id"] or 0)
            unique_reach = int(campus["unique_reach"] or 0)
            # No campus id/name is exposed when the cohort is too small or
            # historical events lack campus attribution.
            if campus_id <= 0 or unique_reach < 10:
                continue
            impressions = int(campus["impressions"] or 0)
            raw_clicks = int(campus["raw_clicks"] or 0)
            unique_clicks = int(campus["unique_clicks"] or 0)
            billable_clicks = int(campus["billable_clicks"] or 0)
            unique_billable_clickers = int(campus["unique_billable_clickers"] or 0)
            campus_by_campaign.setdefault(int(campus["campaign_id"]), []).append({
                "campus_id": campus_id,
                "campus_name": campus["campus_name"] or "University",
                "unique_reach": unique_reach,
                "impressions": impressions,
                "raw_clicks": raw_clicks,
                "unique_clicks": unique_clicks,
                "billable_clicks": billable_clicks,
                "unique_billable_clickers": unique_billable_clickers,
                "billable_ctr_percent": round(billable_clicks * 100 / impressions, 2) if impressions else 0.0,
                "raw_ctr_percent": round(raw_clicks * 100 / impressions, 2) if impressions else 0.0,
                "unique_ctr_percent": round(unique_clicks * 100 / unique_reach, 2) if unique_reach else 0.0,
                "unique_billable_ctr_percent": round(unique_billable_clickers * 100 / unique_reach, 2) if unique_reach else 0.0,
                "net_spend_kes": round(int(campus["net_spend_minor"] or 0) / 100, 2),
            })

        campaigns = []
        for row in rows:
            # An explicit campus-filtered report is suppressed below the
            # minimum cohort size rather than leaking a small campus count.
            if university_id_filter is not None and int(row["unique_reach"] or 0) < 10:
                continue
            impressions = int(row["impressions"] or 0)
            raw_clicks = int(row["raw_clicks"] or 0)
            unique_clicks = int(row["unique_clicks"] or 0)
            billable_clicks = int(row["billable_clicks"] or 0)
            unique_billable_clickers = int(row["unique_billable_clickers"] or 0)
            raw_ctr = round(raw_clicks * 100 / impressions, 2) if impressions else 0.0
            billable_ctr = round(billable_clicks * 100 / impressions, 2) if impressions else 0.0
            unique_reach = int(row["unique_reach"] or 0)
            unique_ctr = round(unique_clicks * 100 / unique_reach, 2) if unique_reach else 0.0
            unique_billable_ctr = (
                round(unique_billable_clickers * 100 / unique_reach, 2) if unique_reach else 0.0
            )
            campaigns.append({
                "campaign_id": int(row["campaign_id"]),
                "campaign_name": row["campaign_name"],
                "placement": row["placement"],
                "impressions": impressions,
                "unique_reach": unique_reach,
                "campus_breakdown": campus_by_campaign.get(int(row["campaign_id"]), []),
                "raw_clicks": raw_clicks,
                "unique_clicks": unique_clicks,
                "billable_clicks": billable_clicks,
                "unique_billable_clickers": unique_billable_clickers,
                # The legacy short name is explicitly defined as billable CTR,
                # so reporting and invoice reconciliation cannot accidentally
                # treat capped/raw interactions as charges.
                "ctr_percent": billable_ctr,
                "billable_ctr_percent": billable_ctr,
                "raw_ctr_percent": raw_ctr,
                "unique_ctr_percent": unique_ctr,
                "unique_billable_ctr_percent": unique_billable_ctr,
                "net_spend_kes": round(int(row["net_spend_minor"] or 0) / 100, 2),
            })

        if request.args.get("format", "").lower() == "csv":
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow([
                "Scope", "Campus", "Campus ID", "Unique reach",
                "Campaign ID", "Campaign", "Placement", "Impressions", "Raw clicks",
                "Unique clickers", "Billable clicks", "Unique billable clickers",
                "Billable CTR (%)", "Raw CTR (%)", "Unique CTR (%)",
                "Unique billable CTR (%)", "Net delivery spend (KES)",
            ])
            for item in campaigns:
                writer.writerow([
                    "campaign", "", "", item["unique_reach"],
                    item["campaign_id"], item["campaign_name"], item["placement"],
                    item["impressions"], item["raw_clicks"], item["unique_clicks"],
                    item["billable_clicks"], item["unique_billable_clickers"],
                    item["billable_ctr_percent"], item["raw_ctr_percent"],
                    item["unique_ctr_percent"], item["unique_billable_ctr_percent"],
                    item["net_spend_kes"],
                ])
                for campus in item["campus_breakdown"]:
                    writer.writerow([
                        "campus", campus["campus_name"], campus["campus_id"], campus["unique_reach"],
                        item["campaign_id"], item["campaign_name"], item["placement"],
                        campus["impressions"], campus["raw_clicks"], campus["unique_clicks"],
                        campus["billable_clicks"], campus["unique_billable_clickers"],
                        campus["billable_ctr_percent"], campus["raw_ctr_percent"],
                        campus["unique_ctr_percent"], campus["unique_billable_ctr_percent"],
                        campus["net_spend_kes"],
                    ])
            filename = f"prepza-discovery-report-{start_day:%Y%m%d}-{end_day:%Y%m%d}.csv"
            return Response(
                output.getvalue(),
                mimetype="text/csv; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        return jsonify({
            "organisation_id": int(organisation_id),
            "period": {
                "start_date": start_day.isoformat(),
                "end_date": end_day.isoformat(),
                "timezone": "Africa/Nairobi",
            },
            "currency": "KES",
            "billing_basis": "prepaid campaign ledger",
            "filters": {
                "campaign_id": campaign_id_filter,
                "university_id": university_id_filter,
            },
            "campaigns": campaigns,
        })

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


    def legacy_discovery_preference_get():
        uid=session.get("user_id")
        if not uid: return jsonify({"error":"Not logged in"}),401
        value=db.session.execute(text("SELECT COALESCE(discoverable,FALSE) FROM student_opportunity_discovery WHERE user_id=:uid"),{"uid":uid}).scalar_one_or_none()
        return jsonify({"discoverable":bool(value)})

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
        requested_placement = str(request.args.get("placement") or "opportunities").strip().lower()
        if requested_placement not in ("home_carousel", "explore", "trending", "podcast", "opportunities"):
            requested_placement = "opportunities"
        rows = db.session.execute(text("""
            SELECT c.id, c.organisation_id, c.opportunity_id, c.name, c.objective, c.placement,
                   c.bid_type, c.bid_kes, c.target_json, c.pricing_snapshot,
                   o.title AS opportunity_title, o.description AS opportunity_description,
                   o.opportunity_type, o.location, o.is_remote, o.application_url,
                   o.application_instructions, o.application_deadline, o.expiry_date,
                   o.published_at, o.view_count,
                   org.name AS organisation_name, org.logo_url AS organisation_logo_url,
                   org.website AS organisation_website
            FROM discovery_campaign c
            JOIN opportunity o ON o.id=c.opportunity_id
            JOIN organisation org ON org.id=c.organisation_id
            WHERE c.status='active'
              AND c.funding_status IN ('funded','credited')
              AND (
                (:requested_placement='home_carousel' AND c.placement='home_carousel')
                OR (:requested_placement='explore' AND c.placement='explore')
                OR (:requested_placement='trending' AND c.placement='trending')
                OR (:requested_placement='podcast' AND c.placement='podcast')
                OR (:requested_placement='opportunities'
                    AND c.placement IN ('feed','home_carousel','explore','trending','opportunities_feed','feed_push','podcast'))
              )
              AND (c.starts_at IS NULL OR c.starts_at <= CURRENT_TIMESTAMP)
              AND (c.ends_at IS NULL OR c.ends_at >= CURRENT_TIMESTAMP)
              AND c.delivered_impressions < GREATEST(1, c.budget_kes * 1000 / GREATEST(1,c.bid_kes))
              AND o.status='published'
              AND o.expiry_date>CURRENT_TIMESTAMP
              AND org.verification_status='verified'
              AND org.is_active=TRUE
              AND (
                :requested_placement='opportunities'
                OR (
                  SELECT COUNT(*) FROM discovery_event e
                  WHERE e.campaign_id=c.id
                    AND e.user_id=:uid
                    AND e.event_type='impression'
                    AND e.created_at >= CURRENT_TIMESTAMP - (
                      GREATEST(1, COALESCE(
                        (c.pricing_snapshot->'home_frequency_cap'->'value'->>'window_days')::INTEGER,
                        7
                      )) || ' days'
                    )::interval
                    AND COALESCE((e.metadata->>'reversed')::boolean,FALSE)=FALSE
                ) < GREATEST(1, COALESCE(
                    (c.pricing_snapshot->'home_frequency_cap'->'value'->>'max_impressions')::INTEGER,
                    5
                ))
              )
            ORDER BY c.updated_at DESC LIMIT 50
        """), {"uid": uid, "requested_placement": requested_placement}).mappings().all()
        feed=[]
        for r in rows:
            if not target_matches(uid, r["target_json"] or {}):
                continue
            feed.append({
                "campaign_id": int(r["id"]),
                "organisation_id": int(r["organisation_id"]),
                "opportunity_id": int(r["opportunity_id"]) if r["opportunity_id"] else None,
                "name": r["name"],
                "objective": r["objective"],
                "placement": r["placement"],
                "featured": requested_placement in ("home_carousel", "explore", "trending", "podcast"),
                "opportunity": {
                    "id": int(r["opportunity_id"]),
                    "title": r["opportunity_title"],
                    "description": r["opportunity_description"],
                    "opportunity_type": r["opportunity_type"],
                    "location": r["location"],
                    "is_remote": bool(r["is_remote"]),
                    "application_url": r["application_url"],
                    "application_instructions": r["application_instructions"],
                    "application_deadline": r["application_deadline"].isoformat() if r["application_deadline"] else None,
                    "expiry_date": r["expiry_date"].isoformat() if r["expiry_date"] else None,
                    "published_at": r["published_at"].isoformat() if r["published_at"] else None,
                    "view_count": int(r["view_count"] or 0),
                    "organisation": {
                        "id": int(r["organisation_id"]),
                        "name": r["organisation_name"],
                        "logo_url": r["organisation_logo_url"],
                        "website": r["organisation_website"],
                    },
                    "promotion_type": "sponsored",
                    "saved": False,
                },
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
        return jsonify({"pricing": _canonical_discovery_pricing(db), "push_caps": {"48h": PUSH_CAP_PER_48_HOURS, "7d": PUSH_CAP_PER_7_DAYS}})

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
        return jsonify({"currency": "KES", "pricing": _canonical_discovery_pricing(db),
                        "campaigns": enriched, "prepaid_ledger_spend_kes": total_spend_minor / 100})

    return None
