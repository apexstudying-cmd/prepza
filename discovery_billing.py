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

    def eligible_users(target):
        params = {}
        if target.get("university_ids"):
            clauses.append("u.university_id = ANY(:university_ids)")
            params["university_ids"] = [int(x) for x in target["university_ids"] if str(x).isdigit()]
        if target.get("program_ids"):
            clauses.append("u.program_id = ANY(:program_ids)")
            params["program_ids"] = [int(x) for x in target["program_ids"] if str(x).isdigit()]
        if target.get("years"):
            clauses.append("u.year = ANY(:years)")
            params["years"] = [int(x) for x in target["years"] if str(x).isdigit()]
        if target.get("discoverable") is not False:
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

    def campaign_row(campaign_id):
        return db.session.execute(text("""
            SELECT * FROM discovery_campaign WHERE id = :id
        """), {"id": campaign_id}).mappings().first()

    def target_matches(user_id, target):
        clauses = ["u.id = :uid"]
        params = {"uid": user_id}
        if target.get("university_ids"):
            clauses.append("u.university_id = ANY(:university_ids)")
            params["university_ids"] = [int(x) for x in target["university_ids"]]
        if target.get("program_ids"):
            clauses.append("u.program_id = ANY(:program_ids)")
            params["program_ids"] = [int(x) for x in target["program_ids"]]
        if target.get("years"):
            clauses.append("u.year = ANY(:years)")
            params["years"] = [int(x) for x in target["years"]]
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
        target = data.get("target") if isinstance(data.get("target"), dict) else {}
        try:
            count = len(eligible_users(target))
        except Exception:
            count = 0
        return jsonify({"audience_estimate": count, "target": target})

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
        bid_type = str(data.get("bid_type") or "cpm").lower()
        try:
            budget = int(data.get("budget_kes") or 0)
        except (TypeError, ValueError):
            budget = 0
        target = data.get("target") if isinstance(data.get("target"), dict) else {}
        if not name or placement not in ("feed", "push", "feed_push"):
            return jsonify({"error": "Campaign name and valid placement are required"}), 400
        if objective not in ("reach", "traffic", "applications"):
            return jsonify({"error": "Invalid campaign objective"}), 400
        if bid_type not in ("cpm", "cpc"):
            return jsonify({"error": "Invalid billing type"}), 400
        if budget < DISCOVERY_PRICING["minimum_campaign_kes"]:
            return jsonify({"error": f"Minimum campaign budget is KES {DISCOVERY_PRICING['minimum_campaign_kes']:,}"}), 400
        if placement == "push" and bid_type != "cpm":
            return jsonify({"error": "Push campaigns use delivered-recipient CPM"}), 400
        if placement == "feed_push" and bid_type == "cpc":
            bid = DISCOVERY_PRICING["click_cpc_kes"]
        else:
            bid = DISCOVERY_PRICING["push_cpm_kes"] if placement == "push" else DISCOVERY_PRICING["feed_cpm_kes"]
        if placement == "feed_push":
            bid = DISCOVERY_PRICING["feed_cpm_kes"]
        start = data.get("starts_at")
        end = data.get("ends_at")
        plan_code, status, expires_at = org_plan(organisation_id)
        if status in ("suspended", "expired", "past_due"):
            return jsonify({"error": "Organisation billing is not active"}), 402
        audience = eligible_users(target)
        db.session.execute(text("""
            INSERT INTO discovery_campaign
                (organisation_id, opportunity_id, name, objective, placement, status,
                 budget_kes, bid_type, bid_kes, target_json, starts_at, ends_at)
            VALUES (:oid, :opp, :name, :objective, :placement, 'draft',
                    :budget, :bid_type, :bid, CAST(:target AS jsonb), :starts, :ends)
        """), {"oid": organisation_id, "opp": data.get("opportunity_id"), "name": name,
               "objective": objective, "placement": placement, "budget": budget,
               "bid_type": bid_type, "bid": bid, "target": json.dumps(target),
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
        target = row["target_json"] or {}
        return jsonify({"campaign": dict(row), "audience_estimate": len(eligible_users(target))})

    @app.patch("/api/organisations/<int:organisation_id>/discovery/campaigns/<int:campaign_id>")
    def update_discovery_campaign(organisation_id, campaign_id):
        uid = session.get("user_id")
        if not uid or not csrf_ok() or not org_access(organisation_id, uid, owner_only=True):
            return jsonify({"error": "Organisation owner and valid CSRF token required"}), 403
        data = request.get_json(silent=True) or {}
        allowed = {"draft", "pending_payment", "active", "paused", "completed", "cancelled"}
        status = str(data.get("status") or "").lower()
        if status not in allowed:
            return jsonify({"error": "Invalid campaign status"}), 400
        row = campaign_row(campaign_id)
        if not row or int(row["organisation_id"]) != organisation_id:
            return jsonify({"error": "Campaign not found"}), 404
        db.session.execute(text("""
            UPDATE discovery_campaign SET status=:status, updated_at=CURRENT_TIMESTAMP
            WHERE id=:cid AND organisation_id=:oid
        """), {"status": status, "cid": campaign_id, "oid": organisation_id})
        db.session.commit()
        return jsonify({"ok": True})

    @app.post("/api/discovery/campaigns/<int:campaign_id>/impression")
    def discovery_impression(campaign_id):
        uid = session.get("user_id")
        if not uid:
            return jsonify({"error": "Not logged in"}), 401
        row = campaign_row(campaign_id)
        if not row or row["status"] != "active":
            return jsonify({"error": "Campaign unavailable"}), 404
        if campaign_usage(row) >= int(row["budget_kes"]):
            return jsonify({"eligible": False, "code": "campaign_budget_exhausted"}), 200
        target = row["target_json"] or {}
        if not target_matches(uid, target):
            return jsonify({"eligible": False}), 200
        day = date.today().isoformat()
        event_key = f"imp:{campaign_id}:{uid}:{day}:{row['placement']}"
        inserted = db.session.execute(text("""
            INSERT INTO discovery_event
                (campaign_id,user_id,event_key,event_type,placement,amount_kes,metadata)
            VALUES (:cid,:uid,:key,'impression',:placement,0,CAST(:meta AS jsonb))
            ON CONFLICT (event_key) DO NOTHING
            RETURNING id
        """), {"cid": campaign_id, "uid": uid, "key": event_key,
               "placement": row["placement"], "meta": json.dumps({"verified": True})}).first()
        if inserted:
            db.session.execute(text("""
                UPDATE discovery_campaign
                SET delivered_impressions=delivered_impressions+1, updated_at=CURRENT_TIMESTAMP
                WHERE id=:cid
            """), {"cid": campaign_id})
            db.session.commit()
        return jsonify({"eligible": True, "recorded": bool(inserted)})

    @app.post("/api/discovery/campaigns/<int:campaign_id>/click")
    def discovery_click(campaign_id):
        uid = session.get("user_id")
        if not uid:
            return jsonify({"error": "Not logged in"}), 401
        row = campaign_row(campaign_id)
        if not row or row["status"] != "active":
            return jsonify({"error": "Campaign unavailable"}), 404
        if not target_matches(uid, row["target_json"] or {}):
            return jsonify({"eligible": False}), 200
        if campaign_usage(row) >= int(row["budget_kes"]):
            return jsonify({"eligible": False, "code": "campaign_budget_exhausted"}), 200
        key = f"click:{campaign_id}:{uid}:{secrets.token_hex(8)}"
        amount = int(row["bid_kes"]) if row["bid_type"] == "cpc" else 0
        db.session.execute(text("""
            INSERT INTO discovery_event
                (campaign_id,user_id,event_key,event_type,placement,amount_kes,metadata)
            VALUES (:cid,:uid,:key,'click',:placement,:amount,CAST(:meta AS jsonb))
        """), {"cid": campaign_id, "uid": uid, "key": key, "placement": row["placement"],
               "amount": amount, "meta": json.dumps({"billable": row["bid_type"] == "cpc"})})
        db.session.execute(text("""
            UPDATE discovery_campaign SET delivered_clicks=delivered_clicks+1,
              updated_at=CURRENT_TIMESTAMP WHERE id=:cid
        """), {"cid": campaign_id})
        db.session.commit()
        return jsonify({"eligible": True, "recorded": True})

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
        key = f"application:{campaign_id}:{uid}:{secrets.token_hex(8)}"
        db.session.execute(text("""
            INSERT INTO discovery_event
                (campaign_id,user_id,event_key,event_type,placement,amount_kes,metadata)
            VALUES (:cid,:uid,:key,'application',:placement,0,CAST(:meta AS jsonb))
        """), {"cid": campaign_id, "uid": uid, "key": key, "placement": row["placement"],
               "amount": 0, "meta": json.dumps({"verified": True})})
        db.session.execute(text("""
            UPDATE discovery_campaign SET delivered_applications=delivered_applications+1,
              updated_at=CURRENT_TIMESTAMP WHERE id=:cid
        """), {"cid": campaign_id})
        db.session.commit()
        return jsonify({"eligible": True, "recorded": True})

    @app.get("/api/organisations/<int:organisation_id>/discovery/campaigns/<int:campaign_id>/invoice-preview")
    def discovery_invoice_preview(organisation_id, campaign_id):
        uid = session.get("user_id")
        if not uid or not org_access(organisation_id, uid):
            return jsonify({"error": "Organisation membership required"}), 403
        row = campaign_row(campaign_id)
        if not row or int(row["organisation_id"]) != organisation_id:
            return jsonify({"error": "Campaign not found"}), 404
        impressions = int(row["delivered_impressions"] or 0)
        clicks = int(row["delivered_clicks"] or 0)
        push = int(row["push_delivered"] or 0)
        usage = campaign_usage(row)
        return jsonify({
            "currency": "KES", "usage_charge_kes": min(max(0, usage), int(row["budget_kes"])),
            "budget_kes": int(row["budget_kes"]),
            "remaining_kes": max(0, int(row["budget_kes"]) - usage),
            "billing_basis": "verified delivery events",
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
        target = row["target_json"] or {}
        user_ids = eligible_users(target)
        now = datetime.utcnow()
        allowed_ids = []
        for user_id in user_ids:
            recent = db.session.execute(text("""
                SELECT COUNT(*) FROM discovery_push_delivery
                WHERE user_id=:uid AND status='sent'
                  AND sent_at >= CURRENT_TIMESTAMP - INTERVAL '48 hours'
            """), {"uid": user_id}).scalar_one()
            weekly = db.session.execute(text("""
                SELECT COUNT(*) FROM discovery_push_delivery
                WHERE user_id=:uid AND status='sent'
                  AND sent_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
            """), {"uid": user_id}).scalar_one()
            if int(recent) < PUSH_CAP_PER_48_HOURS and int(weekly) < PUSH_CAP_PER_7_DAYS:
                allowed_ids.append(user_id)

        subscriptions = push_subscription_rows(allowed_ids)
        # Queue first; an external worker/payment provider can call this endpoint
        # again safely because (campaign,user) is unique.
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
        vapid_private = os.environ.get("VAPID_PRIVATE_KEY")
        vapid_public = os.environ.get("VAPID_PUBLIC_KEY")
        vapid_email = os.environ.get("VAPID_CLAIMS_EMAIL")
        if vapid_private and vapid_public and vapid_email and queued:
            try:
                from pywebpush import webpush
                pending = db.session.execute(text("""
                    SELECT id,user_id,subscription_endpoint FROM discovery_push_delivery
                    WHERE campaign_id=:cid AND status='queued' LIMIT 500
                """), {"cid": campaign_id}).mappings().all()
                payload = json.dumps({"title": row["name"], "body": "A new opportunity matched your Prepza interests.", "campaign_id": campaign_id})
                for item in pending:
                    try:
                        keys = item.get("keys") or {}
                        if isinstance(keys, str):
                            try: keys = json.loads(keys)
                            except Exception: keys = {}
                        webpush(subscription_info={"endpoint": item["subscription_endpoint"], "keys": keys}, data=payload,
                                vapid_private_key=vapid_private, vapid_claims={"sub": vapid_email})
                    except Exception:
                        continue
                    db.session.execute(text("""
                        UPDATE discovery_push_delivery SET status='sent', sent_at=CURRENT_TIMESTAMP WHERE id=:id
                    """), {"id": item["id"]})
                    sent += 1
                if sent:
                    db.session.execute(text("""
                        UPDATE discovery_campaign SET push_delivered=push_delivered+:sent, updated_at=CURRENT_TIMESTAMP WHERE id=:cid
                    """), {"cid": campaign_id, "sent": sent})
                db.session.commit()
            except Exception:
                # Queue remains intact; a worker can deliver later when VAPID is configured.
                pass
        return jsonify({"ok": True, "eligible_recipients": len(allowed_ids),
                        "queued": queued, "sent": sent, "note": "Delivery is frequency-capped and billed by delivered recipient."})

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
        total_spend = 0
        for r in rows:
            charge = campaign_usage(r)
            total_spend += min(charge, int(r["budget_kes"]))
        return jsonify({"currency": "KES", "pricing": DISCOVERY_PRICING,
                        "campaigns": [dict(r) for r in rows], "estimated_usage_spend_kes": total_spend})

    return None
