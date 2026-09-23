"""G3: atomic prepaid campaign metering.

Every billable delivery is settled against the campaign's prepaid balance
inside one PostgreSQL transaction. The ledger is the source of truth for
spend; campaign counters are denormalized reporting fields.
"""
from __future__ import annotations
import json
from decimal import Decimal
from sqlalchemy import text
from datetime import datetime

EVENT_TYPES = {"impression", "click", "push_delivery"}

def _unit_price_minor(campaign, event_type):
    placement = str(campaign["placement"] or "")
    bid_type = str(campaign["bid_type"] or "")
    target = campaign["target_json"] or {}
    billing_modes = target.get("billing_modes") if isinstance(target, dict) else None
    if not isinstance(billing_modes, list): billing_modes = ["cpm"] if bid_type == "cpm" else ["cpc"] if bid_type == "cpc" else ["cpm","cpc"] if bid_type == "both" else []
    snapshot = campaign["pricing_snapshot"] or {}
    if event_type == "push_delivery":
        snap = ((snapshot.get("push_delivery_cpm") or {}).get("value") or {}).get("amount_kes")
    elif event_type == "impression":
        snap = ((snapshot.get("home_impression_cpm") or {}).get("value") or {}).get("amount_kes")
    else:
        snap = ((snapshot.get("click_cpc") or {}).get("value") or {}).get("amount_kes")
    bid_kes = int(snap if snap is not None else (campaign["bid_kes"] or 0))
    if event_type == "click":
        if "cpc" not in billing_modes:
            return 0
        return bid_kes * 100
    if event_type == "push_delivery":
        if placement not in ("push", "feed_push"):
            return 0
        return int((Decimal(bid_kes) * Decimal(100) / Decimal(1000)).to_integral_value())
    if event_type == "impression":
        if "cpm" not in billing_modes or placement not in ("feed", "feed_push"):
            return 0
        return int((Decimal(bid_kes) * Decimal(100) / Decimal(1000)).to_integral_value())
    return 0

def record_billable_event(db, campaign_id, user_id, event_type, placement, event_key):
    """Atomically check balance, insert event+ledger, and update counters."""
    if event_type not in EVENT_TYPES:
        return {"ok": False, "reason": "invalid_event_type"}
    with db.session.begin_nested():
        campaign = db.session.execute(text("""
            SELECT * FROM discovery_campaign WHERE id=:cid FOR UPDATE
        """), {"cid": campaign_id}).mappings().first()
        if not campaign:
            return {"ok": False, "reason": "campaign_missing"}
        if campaign["status"] != "active":
            return {"ok": False, "reason": "campaign_inactive"}
        if str(campaign["funding_status"] or "") not in ("funded", "credited"):
            return {"ok": False, "reason": "campaign_not_funded"}
        if campaign["starts_at"] and campaign["starts_at"] > datetime.utcnow():
            return {"ok": False, "reason": "campaign_not_started"}
        if campaign["ends_at"] and campaign["ends_at"] < datetime.utcnow():
            return {"ok": False, "reason": "campaign_ended"}

        price = _unit_price_minor(campaign, event_type)
        if price <= 0:
            return {"ok": False, "reason": "event_not_billable"}
        if str(campaign["currency"] or "KES").upper() != "KES":
            return {"ok": False, "reason": "unsupported_currency"}

        existing = db.session.execute(text("""
            SELECT id, amount_kes FROM discovery_event
            WHERE event_key=:key
        """), {"key": event_key}).mappings().first()
        if existing:
            return {"ok": True, "duplicate": True, "amount_minor": int(existing["amount_kes"] or 0) * 100}

        # Serialize events for the same student so a rolling frequency cap
        # cannot be bypassed by two simultaneous requests.
        if event_type in ("impression", "push_delivery"):
            db.session.execute(text('SELECT id FROM "user" WHERE id=:uid FOR UPDATE'), {"uid": user_id})
            cap = 3
            count_type = "impression" if event_type == "impression" else "push_delivery"
            recent_count = db.session.execute(text("""
                SELECT COUNT(*) FROM discovery_event
                WHERE user_id=:uid AND campaign_id=:cid AND event_type=:etype
                  AND created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
                  AND COALESCE((metadata->>'reversed')::boolean,FALSE)=FALSE
            """), {"uid": user_id, "cid": campaign_id, "etype": count_type}).scalar_one()
            if int(recent_count) >= cap:
                return {"ok": False, "reason": "student_frequency_cap"}

        spent = db.session.execute(text("""
            SELECT COALESCE(SUM(signed_amount_minor),0)
            FROM b2b_campaign_ledger
            WHERE campaign_id=:cid
        """), {"cid": campaign_id}).scalar_one()
        funded = int(campaign["funded_amount_minor"] or 0)
        remaining = funded + int(spent)
        if remaining < price:
            db.session.execute(text("""
                UPDATE discovery_campaign
                SET funding_status='exhausted',
                    exhausted_at=COALESCE(exhausted_at,CURRENT_TIMESTAMP),
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=:cid
            """), {"cid": campaign_id})
            return {"ok": False, "reason": "campaign_budget_exhausted", "remaining_minor": max(0, remaining)}

        amount_kes = Decimal(price) / Decimal(100)
        db.session.execute(text("""
            INSERT INTO discovery_event
                (campaign_id,user_id,event_key,event_type,placement,amount_kes,metadata)
            VALUES (:cid,:uid,:key,:etype,:placement,:amount,CAST(:meta AS jsonb))
        """), {
            "cid": campaign_id, "uid": user_id, "key": event_key,
            "etype": event_type, "placement": placement,
            "amount": float(amount_kes),
            "meta": json.dumps({"billable": True, "amount_minor": price, "meter_version": "g3-v2"})
        })
        db.session.execute(text("""
            INSERT INTO b2b_campaign_ledger
                (campaign_id,entry_type,signed_amount_minor,currency,idempotency_key,
                 delivery_event_id,description,metadata)
            VALUES (:cid,:etype,:amount,'KES',:idem,
                    (SELECT id FROM discovery_event WHERE event_key=:key),
                    'Sponsored campaign delivery charge',CAST(:meta AS jsonb))
        """), {
            "cid": campaign_id, "etype": f"delivery_{event_type}",
            "amount": -price, "idem": f"delivery:{event_key}",
            "key": event_key,
            "meta": json.dumps({"user_id": user_id, "amount_minor": price, "meter_version": "g3-v2"})
        })
        if event_type == "impression":
            counter = "delivered_impressions"
        elif event_type == "click":
            counter = "delivered_clicks"
        else:
            counter = "push_delivered"
        db.session.execute(text(f"""
            UPDATE discovery_campaign
            SET {counter}={counter}+1, updated_at=CURRENT_TIMESTAMP
            WHERE id=:cid
        """), {"cid": campaign_id})

        new_remaining = remaining - price
        if new_remaining == 0:
            db.session.execute(text("""
                UPDATE discovery_campaign
                SET funding_status='exhausted', exhausted_at=COALESCE(exhausted_at,CURRENT_TIMESTAMP)
                WHERE id=:cid
            """), {"cid": campaign_id})
        return {"ok": True, "amount_minor": price, "remaining_minor": new_remaining}

def reverse_billable_event(db, event_key, reason="delivery_failed"):
    """Reverse a previously reserved delivery charge exactly once."""
    with db.session.begin_nested():
        row = db.session.execute(text("""
            SELECT id,campaign_id FROM discovery_event WHERE event_key=:key FOR UPDATE
        """), {"key": event_key}).mappings().first()
        if not row:
            return {"ok": False, "reason": "event_missing"}
        idem = f"reversal:{event_key}"
        already = db.session.execute(text("""
            SELECT id FROM b2b_campaign_ledger WHERE idempotency_key=:idem
        """), {"idem": idem}).scalar_one_or_none()
        if already:
            return {"ok": True, "duplicate": True}
        charge = db.session.execute(text("""
            SELECT signed_amount_minor FROM b2b_campaign_ledger
            WHERE idempotency_key=:idem
        """), {"idem": f"delivery:{event_key}"}).scalar_one_or_none()
        if charge is None or int(charge) >= 0:
            return {"ok": False, "reason": "charge_missing"}
        amount = -int(charge)
        db.session.execute(text("""
            INSERT INTO b2b_campaign_ledger
                (campaign_id,entry_type,signed_amount_minor,currency,idempotency_key,
                 delivery_event_id,description,metadata)
            VALUES (:cid,'delivery_reversal',:amount,'KES',:idem,:eid,
                    'Reversal of failed sponsored delivery',CAST(:meta AS jsonb))
        """), {
            "cid": int(row["campaign_id"]), "amount": amount, "idem": idem,
            "eid": int(row["id"]), "meta": json.dumps({"reason": reason, "meter_version": "g3-v1"})
        })
        db.session.execute(text("""
            UPDATE discovery_event SET metadata=metadata || CAST(:meta AS jsonb)
            WHERE id=:eid
        """), {"eid": int(row["id"]), "meta": json.dumps({"reversed": True, "reversal_reason": reason})})
        db.session.execute(text("""
            UPDATE discovery_campaign
            SET exhausted_at=NULL,
                funding_status=CASE WHEN funding_status='exhausted' THEN 'funded' ELSE funding_status END,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=:cid
        """), {"cid": int(row["campaign_id"])})
        return {"ok": True, "reversed_minor": amount}
