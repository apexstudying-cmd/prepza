"""Central, admin-configurable AI economics for Prepza."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import text

PLAN_DEFAULTS = {
    "free": {
        "display_name": "Free", "price_kes": 0, "billing_period": "month", "quota_period": "month",
        "ada_monthly_units": 500_000, "ada_daily_units": 20_000, "ada_max_output_tokens": 800,
        "podcast_minutes": 10, "summary_pages": 10, "questions": 20, "mind_map_nodes": 30, "flashcards": 100,
        "offline_study": False, "premium_library": False, "study_hub_uploads": True,
    },
    "plus": {
        "display_name": "Plus", "price_kes": 499, "billing_period": "month", "quota_period": "month",
        "ada_monthly_units": 2_500_000, "ada_daily_units": 100_000, "ada_max_output_tokens": 1_200,
        "podcast_minutes": 120, "summary_pages": 40, "questions": 100, "mind_map_nodes": 150, "flashcards": 300,
        "offline_study": True, "premium_library": True, "study_hub_uploads": True,
    },
    "pro": {
        "display_name": "Pro", "price_kes": 999, "billing_period": "month", "quota_period": "month",
        "ada_monthly_units": 6_000_000, "ada_daily_units": 250_000, "ada_max_output_tokens": 1_600,
        "podcast_minutes": 350, "summary_pages": 100, "questions": 210, "mind_map_nodes": 350, "flashcards": 600,
        "offline_study": True, "premium_library": True, "study_hub_uploads": True,
    },
}

ADA_UNIT_WEIGHTS = {
    "normal_input": Decimal("1"),
    "cache_write": Decimal("1.25"),
    "cached_input": Decimal("0.1"),
    "output": Decimal("6"),
}

def ensure_economics_schema(db):
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS student_plan_config (
            plan_code VARCHAR(20) PRIMARY KEY, display_name VARCHAR(40) NOT NULL,
            price_kes INTEGER NOT NULL DEFAULT 0, billing_period VARCHAR(20) NOT NULL DEFAULT 'month',
            quota_period VARCHAR(20) NOT NULL DEFAULT 'month', ada_monthly_units BIGINT NOT NULL DEFAULT 0,
            ada_daily_units BIGINT NOT NULL DEFAULT 0, ada_max_output_tokens INTEGER NOT NULL DEFAULT 800,
            podcast_minutes INTEGER NOT NULL DEFAULT 0, summary_pages INTEGER NOT NULL DEFAULT 0,
            questions INTEGER NOT NULL DEFAULT 0, mind_map_nodes INTEGER NOT NULL DEFAULT 0,
            flashcards INTEGER NOT NULL DEFAULT 0, offline_study BOOLEAN NOT NULL DEFAULT FALSE,
            premium_library BOOLEAN NOT NULL DEFAULT FALSE, study_hub_uploads BOOLEAN NOT NULL DEFAULT TRUE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_by INTEGER
        )
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS ada_usage_day (
            user_id INTEGER NOT NULL, usage_date DATE NOT NULL, ada_units BIGINT NOT NULL DEFAULT 0,
            requests INTEGER NOT NULL DEFAULT 0, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, usage_date)
        )
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS ada_usage_month (
            user_id INTEGER NOT NULL, period_start DATE NOT NULL, ada_units BIGINT NOT NULL DEFAULT 0,
            requests INTEGER NOT NULL DEFAULT 0, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, period_start)
        )
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS ada_request_usage (
            id BIGSERIAL PRIMARY KEY, user_id INTEGER NOT NULL, plan_code VARCHAR(20) NOT NULL,
            model VARCHAR(100) NOT NULL, provider VARCHAR(40), input_tokens INTEGER NOT NULL DEFAULT 0,
            cached_tokens INTEGER NOT NULL DEFAULT 0, cache_write_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0, ada_units BIGINT NOT NULL DEFAULT 0,
            cost_usd NUMERIC(14,8) NOT NULL DEFAULT 0, request_key VARCHAR(120),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.session.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_ada_request_usage_user_created
        ON ada_request_usage (user_id, created_at)
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS ai_economics_change_log (
            id BIGSERIAL PRIMARY KEY,
            admin_user_id INTEGER NOT NULL,
            plan_code VARCHAR(20) NOT NULL,
            changes JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    for code, cfg in PLAN_DEFAULTS.items():
        db.session.execute(text("""
            INSERT INTO student_plan_config (
                plan_code, display_name, price_kes, billing_period, quota_period,
                ada_monthly_units, ada_daily_units, ada_max_output_tokens,
                podcast_minutes, summary_pages, questions, mind_map_nodes,
                flashcards, offline_study, premium_library, study_hub_uploads
            ) VALUES (
                :plan_code, :display_name, :price_kes, :billing_period, :quota_period,
                :ada_monthly_units, :ada_daily_units, :ada_max_output_tokens,
                :podcast_minutes, :summary_pages, :questions, :mind_map_nodes,
                :flashcards, :offline_study, :premium_library, :study_hub_uploads
            ) ON CONFLICT (plan_code) DO NOTHING
        """), {"plan_code": code, **cfg})
    db.session.commit()

def get_plan(db, plan_code):
    row = db.session.execute(text("""
        SELECT * FROM student_plan_config WHERE plan_code = :plan_code AND is_active = TRUE
    """), {"plan_code": plan_code}).mappings().first()
    return dict(row) if row else None

def get_user_plan_code(db, user_id):
    """Return only the plan whose paid entitlement period contains now."""
    row = db.session.execute(text("""
        SELECT p.plan
        FROM payment p
        JOIN student_order so ON so.payment_id = p.id
        WHERE p.user_id = :uid
          AND p.payment_type = 'subscription'
          AND p.status = 'success'
          AND p.subscription_starts_at IS NOT NULL
          AND p.subscription_expires_at IS NOT NULL
          AND p.subscription_starts_at <= CURRENT_TIMESTAMP
          AND p.subscription_expires_at > CURRENT_TIMESTAMP
          AND so.user_id = p.user_id
          AND so.order_type = 'subscription'
          AND so.status = 'fulfilled'
          AND so.plan = p.plan
          AND so.item_id IS NULL
          AND so.quantity = 1
          AND so.currency = 'KES'
        ORDER BY p.subscription_starts_at DESC, p.id DESC
        LIMIT 1
    """), {"uid": user_id}).scalar_one_or_none()
    return {"plus": "plus", "pro": "pro"}.get(row, "free")


def get_plans(db):
    rows = db.session.execute(text("""
        SELECT * FROM student_plan_config WHERE is_active = TRUE
        ORDER BY CASE plan_code WHEN 'free' THEN 1 WHEN 'plus' THEN 2 WHEN 'pro' THEN 3 ELSE 99 END
    """)).mappings().all()
    return [dict(row) for row in rows]

def _period_start():
    now = datetime.utcnow()
    return date(now.year, now.month, 1)


def get_active_entitlement_period(db, user_id, plan_code):
    """
    Return the paid subscription period currently granting this plan.

    Paid monthly quotas must follow the student's actual paid entitlement
    month, not the calendar month. This is especially important when a
    student upgrades mid-month: the Pro allowance starts when Pro starts and
    lasts for that Pro paid period.
    """
    if plan_code not in ("plus", "pro"):
        return None
    row = db.session.execute(text("""
        SELECT p.id, p.subscription_starts_at, p.subscription_expires_at
        FROM payment p
        JOIN student_order so ON so.payment_id = p.id
        WHERE p.user_id=:uid
          AND p.payment_type='subscription'
          AND p.plan=:plan
          AND p.status='success'
          AND p.subscription_starts_at IS NOT NULL
          AND p.subscription_expires_at IS NOT NULL
          AND p.subscription_starts_at <= CURRENT_TIMESTAMP
          AND p.subscription_expires_at > CURRENT_TIMESTAMP
          AND so.user_id=p.user_id
          AND so.order_type='subscription'
          AND so.status='fulfilled'
          AND so.plan=p.plan
          AND so.item_id IS NULL
          AND so.quantity=1
          AND so.currency='KES'
        ORDER BY p.subscription_starts_at DESC, p.id DESC
        LIMIT 1
    """), {"uid": user_id, "plan": plan_code}).mappings().first()
    return dict(row) if row else None


def get_usage_period(db, user_id, plan_code):
    active = get_active_entitlement_period(db, user_id, plan_code)
    if active:
        # Date is only the storage key; enforcement still verifies the
        # active payment period from the authoritative payment row.
        return active["id"], active["subscription_starts_at"].date()
    return None, _period_start()


def calculate_ada_units(input_tokens=0, cached_tokens=0, cache_write_tokens=0, output_tokens=0):
    normal = max(0, int(input_tokens or 0))
    cached = max(0, int(cached_tokens or 0))
    cache_write = max(0, int(cache_write_tokens or 0))
    output = max(0, int(output_tokens or 0))
    units = (
        Decimal(normal) * ADA_UNIT_WEIGHTS["normal_input"]
        + Decimal(cache_write) * ADA_UNIT_WEIGHTS["cache_write"]
        + Decimal(cached) * ADA_UNIT_WEIGHTS["cached_input"]
        + Decimal(output) * ADA_UNIT_WEIGHTS["output"]
    )
    return int(units.to_integral_value(rounding="ROUND_CEILING"))

def reserve_ada_budget(db, user_id, plan_code, estimated_units):
    plan = get_plan(db, plan_code)
    if not plan:
        return False, {"code": "unknown_plan"}
    estimated_units = max(1, int(estimated_units))
    today = date.today()
    entitlement_payment_id, month = get_usage_period(db, user_id, plan_code)
    db.session.execute(text("""
        INSERT INTO ada_usage_day (user_id, usage_date) VALUES (:uid, :day)
        ON CONFLICT (user_id, usage_date) DO NOTHING
    """), {"uid": user_id, "day": today})
    db.session.execute(text("""
        INSERT INTO ada_usage_month (user_id, period_start) VALUES (:uid, :period)
        ON CONFLICT (user_id, period_start) DO NOTHING
    """), {"uid": user_id, "period": month})
    day = db.session.execute(text("""
        SELECT ada_units FROM ada_usage_day WHERE user_id=:uid AND usage_date=:day FOR UPDATE
    """), {"uid": user_id, "day": today}).scalar_one()
    month_used = db.session.execute(text("""
        SELECT ada_units FROM ada_usage_month WHERE user_id=:uid AND period_start=:period FOR UPDATE
    """), {"uid": user_id, "period": month}).scalar_one()
    # Daily is a safety valve, not the student's entitlement. A first request
    # may exceed the soft daily ceiling; once the day has already accumulated
    # usage, stop additional requests at the ceiling. The monthly wallet is
    # the hard entitlement.
    daily_limit = int(plan["ada_daily_units"])
    if int(day) > 0 and int(day) + estimated_units > daily_limit:
        db.session.rollback()
        return False, {
            "code": "ada_daily_limit",
            "remaining_units": max(0, daily_limit - int(day)),
        }
    if int(month_used) + estimated_units > int(plan["ada_monthly_units"]):
        db.session.rollback()
        return False, {"code": "ada_monthly_limit", "remaining_units": max(0, int(plan["ada_monthly_units"]) - int(month_used))}
    db.session.execute(text("""
        UPDATE ada_usage_day SET ada_units=ada_units+:units, updated_at=CURRENT_TIMESTAMP
        WHERE user_id=:uid AND usage_date=:day
    """), {"uid": user_id, "day": today, "units": estimated_units})
    db.session.execute(text("""
        UPDATE ada_usage_month SET ada_units=ada_units+:units, updated_at=CURRENT_TIMESTAMP
        WHERE user_id=:uid AND period_start=:period
    """), {"uid": user_id, "period": month, "units": estimated_units})
    db.session.commit()
    return True, {"reserved_units": estimated_units}

def refund_ada_budget(db, user_id, plan_code, units):
    """Return an unused reservation to the same entitlement wallet it came from.

    The previous implementation always used the Free/calendar-month wallet,
    which could refund a failed paid Ada request into the wrong period.
    """
    units = max(0, int(units or 0))
    if not units:
        return
    today = date.today()
    _payment_id, month = get_usage_period(db, user_id, plan_code)
    db.session.execute(text("""
        UPDATE ada_usage_day SET ada_units=GREATEST(0, ada_units-:units), updated_at=CURRENT_TIMESTAMP
        WHERE user_id=:uid AND usage_date=:day
    """), {"uid": user_id, "day": today, "units": units})
    db.session.execute(text("""
        UPDATE ada_usage_month SET ada_units=GREATEST(0, ada_units-:units), updated_at=CURRENT_TIMESTAMP
        WHERE user_id=:uid AND period_start=:period
    """), {"uid": user_id, "period": month, "units": units})
    db.session.commit()

def record_ada_usage(db, user_id, plan_code, model, provider, input_tokens, cached_tokens,
                     cache_write_tokens, output_tokens, cost_usd=0, request_key=None, reserved_units=0):
    units = calculate_ada_units(input_tokens, cached_tokens, cache_write_tokens, output_tokens)
    delta = units - max(0, int(reserved_units or 0))
    entitlement_payment_id, month = get_usage_period(db, user_id, plan_code)
    today = date.today()
    db.session.execute(text("""
        INSERT INTO ada_request_usage (
            user_id, plan_code, model, provider, input_tokens, cached_tokens, cache_write_tokens,
            output_tokens, ada_units, cost_usd, request_key
        ) VALUES (:uid,:plan,:model,:provider,:input,:cached,:cache_write,:output,:units,:cost,:request_key)
    """), {"uid":user_id,"plan":plan_code,"model":model,"provider":provider,"input":int(input_tokens or 0),
           "cached":int(cached_tokens or 0),"cache_write":int(cache_write_tokens or 0),
           "output":int(output_tokens or 0),"units":units,"cost":float(cost_usd or 0),"request_key":request_key})
    db.session.execute(text("""
        INSERT INTO ada_usage_day (user_id, usage_date, ada_units, requests)
        VALUES (:uid,:day,:units,1)
        ON CONFLICT (user_id, usage_date) DO UPDATE SET
            ada_units=GREATEST(0, ada_usage_day.ada_units+EXCLUDED.ada_units),
            requests=ada_usage_day.requests+1, updated_at=CURRENT_TIMESTAMP
    """), {"uid":user_id,"day":today,"units":delta})
    db.session.execute(text("""
        INSERT INTO ada_usage_month (user_id, period_start, ada_units, requests)
        VALUES (:uid,:period,:units,1)
        ON CONFLICT (user_id, period_start) DO UPDATE SET
            ada_units=GREATEST(0, ada_usage_month.ada_units+EXCLUDED.ada_units),
            requests=ada_usage_month.requests+1, updated_at=CURRENT_TIMESTAMP
    """), {"uid":user_id,"period":month,"units":delta})

    # Record the final, successful Ada consumption against the exact paid
    # subscription payment. This is separate from the monthly wallet because
    # the wallet resets and cannot prove which subscription payment was used.
    if plan_code in ("plus", "pro") and units > 0:
        payment_id = entitlement_payment_id
        if payment_id:
            db.session.execute(text("""
                INSERT INTO student_entitlement_usage
                    (user_id,payment_id,feature,units,request_count,metadata)
                VALUES (:uid,:pid,'ada',:units,1,CAST(:metadata AS jsonb))
            """), {
                "uid": user_id, "pid": payment_id, "units": units,
                "metadata": __import__("json").dumps({
                    "model": model, "provider": provider, "request_key": request_key,
                    "input_tokens": int(input_tokens or 0),
                    "cached_tokens": int(cached_tokens or 0),
                    "cache_write_tokens": int(cache_write_tokens or 0),
                    "output_tokens": int(output_tokens or 0),
                    "provisional": False,
                }),
            })
    db.session.commit()
    return units

def get_ada_usage(db, user_id, plan_code):
    plan = get_plan(db, plan_code)
    month, today = _period_start(), date.today()
    day = db.session.execute(text("""
        SELECT ada_units, requests FROM ada_usage_day WHERE user_id=:uid AND usage_date=:day
    """), {"uid":user_id,"day":today}).mappings().first()
    month_row = db.session.execute(text("""
        SELECT ada_units, requests FROM ada_usage_month WHERE user_id=:uid AND period_start=:period
    """), {"uid":user_id,"period":month}).mappings().first()
    day_used = int((day or {}).get("ada_units", 0) or 0)
    month_used = int((month_row or {}).get("ada_units", 0) or 0)
    return {
        "daily_used": day_used, "daily_limit": int(plan["ada_daily_units"]),
        "monthly_used": month_used, "monthly_limit": int(plan["ada_monthly_units"]),
        "daily_remaining": max(0, int(plan["ada_daily_units"])-day_used),
        "monthly_remaining": max(0, int(plan["ada_monthly_units"])-month_used),
        "entitlement_payment_id": entitlement_payment_id,
        "entitlement_period_start": month.isoformat(),
    }

def validate_plan_patch(payload):
    allowed = set(PLAN_DEFAULTS["free"]) - {"display_name"}
    errors, cleaned = {}, {}
    integer_fields = {"price_kes","ada_monthly_units","ada_daily_units","ada_max_output_tokens",
                      "podcast_minutes","summary_pages","questions","mind_map_nodes","flashcards"}
    boolean_fields = {"offline_study","premium_library","study_hub_uploads"}
    string_fields = {"billing_period","quota_period"}
    for key, value in payload.items():
        if key == "display_name":
            value = str(value).strip()
            if not value or len(value) > 40: errors[key] = "display_name must be 1-40 characters"
            else: cleaned[key] = value
        elif key in integer_fields:
            try:
                value = int(value)
                if value < 0: raise ValueError
                cleaned[key] = value
            except (TypeError, ValueError): errors[key] = "must be a non-negative integer"
        elif key in boolean_fields:
            if not isinstance(value, bool): errors[key] = "must be boolean"
            else: cleaned[key] = value
        elif key in string_fields:
            value = str(value).strip().lower()
            if value != "month": errors[key] = "billing period must be month"
            else: cleaned[key] = value
        elif key not in allowed:
            errors[key] = "field is not admin-editable"
    return cleaned, errors


def _admin_allowed():
    from flask import session
    import os
    uid = session.get("user_id")
    if not uid:
        return False
    if session.get("is_admin") is True or session.get("role") in ("admin", "superadmin"):
        return True
    configured = {int(x.strip()) for x in os.environ.get("PREPZA_ADMIN_USER_IDS", "").split(",") if x.strip().isdigit()}
    return int(uid) in configured


def register_ai_economics(app, db):
    ensure_economics_schema(db)
    from flask import jsonify, request, session

    @app.get("/api/admin/ai-economics/plans")
    def admin_ai_economics_plans():
        if not _admin_allowed():
            return jsonify({"error": "Admin access required"}), 403
        return jsonify({"currency": "KES", "plans": get_plans(db),
                        "unit_weights": {k: str(v) for k, v in ADA_UNIT_WEIGHTS.items()}})

    @app.patch("/api/admin/ai-economics/plans/<plan_code>")
    def admin_update_ai_economics_plan(plan_code):
        if not _admin_allowed():
            return jsonify({"error": "Admin access required"}), 403
        if not (session.get("csrf_token") and request.headers.get("X-CSRF-Token") == session.get("csrf_token")):
            return jsonify({"error": "Invalid CSRF token"}), 403
        payload = request.get_json(silent=True) or {}
        cleaned, errors = validate_plan_patch(payload)
        if errors:
            return jsonify({"error": "Invalid plan configuration", "fields": errors}), 400
        if not cleaned:
            return jsonify({"error": "No editable fields supplied"}), 400
        if not get_plan(db, plan_code):
            return jsonify({"error": "Unknown plan"}), 404
        cleaned["updated_by"] = session.get("user_id")
        assignments = ", ".join(f"{key} = :{key}" for key in cleaned)
        db.session.execute(text(f"""
            UPDATE student_plan_config
            SET {assignments}, updated_at = CURRENT_TIMESTAMP
            WHERE plan_code = :plan_code
        """), {"plan_code": plan_code, **cleaned})
        db.session.execute(text("""
            INSERT INTO ai_economics_change_log (admin_user_id, plan_code, changes)
            VALUES (:admin_user_id, :plan_code, CAST(:changes AS jsonb))
        """), {
            "admin_user_id": int(session.get("user_id")),
            "plan_code": plan_code,
            "changes": __import__("json").dumps(cleaned),
        })
        db.session.commit()
        return jsonify({"ok": True, "plan": get_plan(db, plan_code)})

    @app.get("/api/ai-economics/plan")
    def current_ai_economics_plan():
        uid = session.get("user_id")
        if not uid:
            return jsonify({"error": "Not logged in"}), 401
        plan_code = get_user_plan_code(db, uid)
        plan = get_plan(db, plan_code)
        public_plan = {
            "plan_code": plan["plan_code"],
            "display_name": plan["display_name"],
            "price_kes": int(plan["price_kes"]),
            "billing_period": plan["billing_period"],
            "quota_period": plan["quota_period"],
            "podcast_minutes": int(plan["podcast_minutes"]),
            "summary_pages": int(plan["summary_pages"]),
            "questions": int(plan["questions"]),
            "mind_map_nodes": int(plan["mind_map_nodes"]),
            "flashcards": int(plan["flashcards"]),
            "offline_study": bool(plan["offline_study"]),
            "premium_library": bool(plan["premium_library"]),
            "study_hub_uploads": bool(plan["study_hub_uploads"]),
        }
        usage = get_ada_usage(db, uid, plan_code)
        if usage["monthly_used"] >= usage["monthly_limit"]:
            ada_status = "monthly_exhausted"
        elif usage["daily_used"] >= usage["daily_limit"]:
            ada_status = "daily_pause"
        else:
            ada_status = "available"
        ada_label = {
            "free": "Ada — Limited",
            "plus": "Ada — 5× more usage",
            "pro": "Ada — 12× more usage",
        }[plan_code]
        return jsonify({"plan": public_plan, "ada": {
            "label": ada_label,
            "status": ada_status,
        }})

    @app.get("/api/admin/ai-economics/usage")
    def admin_ai_economics_usage():
        if not _admin_allowed():
            return jsonify({"error": "Admin access required"}), 403
        row = db.session.execute(text("""
            SELECT COUNT(*) AS requests,
                   COALESCE(SUM(input_tokens),0) AS input_tokens,
                   COALESCE(SUM(cached_tokens),0) AS cached_tokens,
                   COALESCE(SUM(cache_write_tokens),0) AS cache_write_tokens,
                   COALESCE(SUM(output_tokens),0) AS output_tokens,
                   COALESCE(SUM(ada_units),0) AS ada_units,
                   COALESCE(SUM(cost_usd),0) AS cost_usd
            FROM ada_request_usage
            WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
        """)).mappings().one()
        return jsonify({key: (float(value) if key == "cost_usd" else int(value or 0))
                        for key, value in row.items()})
