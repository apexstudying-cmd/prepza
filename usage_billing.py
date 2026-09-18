"""Launch-grade usage, AI quota, and organisation audience metering.

This module is deliberately additive. It uses small PostgreSQL tables and
registers Flask routes/hooks after app.py has created db. It does not replace
the existing Payment/Opportunity models.

Product rules:
- A signup is not an active user.
- An engaged active user is a signed-in user with a visible heartbeat/session
  and at least 30 seconds of foreground engagement OR a meaningful core action.
- DAU/WAU/MAU are derived from daily activity rows.
- Student AI quotas are enforced server-side before generation.
- Organisation audience reporting exposes aggregate active counts, not a
  person's exact live presence.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, date
from flask import jsonify, request, session
from sqlalchemy import text


STUDENT_PLANS = {
    "free": {
        "price_kes": 0,
        "billing_period": "month",
        "quota_period": "month",
        "summary_generations": 3,
        "summary_max_pages": 2,
        "podcast_generations": 1,
        "podcast_max_minutes": 5,
        "flashcard_generations": 3,
        "flashcard_max_cards": 10,
        "quiz_generations": 2,
        "quiz_max_questions": 10,
        "mind_map_generations": 2,
        "mind_map_max_nodes": 6,
        "tutor_messages": 20,
    },
    "premium": {
        "price_kes": 599,
        "billing_period": "semester",
        "quota_period": "month",
        "summary_generations": 30,
        "summary_max_pages": 10,
        "podcast_generations": 4,
        "podcast_max_minutes": 30,
        "flashcard_generations": 30,
        "flashcard_max_cards": 50,
        "quiz_generations": 20,
        "quiz_max_questions": 30,
        "mind_map_generations": 20,
        "mind_map_max_nodes": 12,
        "tutor_messages": 300,
    },
}

# Organisation subscription is audience-access pricing, not ad RPM.
# Sponsored inventory is separately priced on a CPM basis.
ORGANISATION_PLANS = {
    "launch": {
        "monthly_fee_kes": 2500,
        "active_user_cap": 250,
        "active_opportunities": 2,
        "sponsored_campaigns": 1,
        "candidate_search_window_days": 7,
        "analytics_retention_days": 30,
    },
    "growth": {
        "monthly_fee_kes": 7500,
        "active_user_cap": 1000,
        "active_opportunities": 10,
        "sponsored_campaigns": 3,
        "candidate_search_window_days": 30,
        "analytics_retention_days": 90,
    },
    "scale": {
        "monthly_fee_kes": 15000,
        "active_user_cap": 3000,
        "active_opportunities": 50,
        "sponsored_campaigns": 10,
        "candidate_search_window_days": 30,
        "analytics_retention_days": 365,
    },
}

SPONSORED_CPM_KES = 250
SPONSORED_MIN_CAMPAIGN_KES = 2500

FEATURES = {
    "summary": ("summary_generations", "summary_max_pages"),
    "podcast": ("podcast_generations", "podcast_max_minutes"),
    "flashcards": ("flashcard_generations", "flashcard_max_cards"),
    "quiz": ("quiz_generations", "quiz_max_questions"),
    "mind_map": ("mind_map_generations", "mind_map_max_nodes"),
}

DEFAULT_GENERATION_UNITS = {
    "summary": 2,
    "podcast": 5,
    "flashcards": 10,
    "quiz": 10,
    "mind_map": 6,
}


def _ensure_schema(db):
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS student_ai_usage (
            user_id INTEGER NOT NULL,
            period_start DATE NOT NULL,
            feature VARCHAR(40) NOT NULL,
            units INTEGER NOT NULL DEFAULT 0,
            requests INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, period_start, feature)
        )
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS product_activity_day (
            user_id INTEGER NOT NULL,
            activity_date DATE NOT NULL,
            sessions INTEGER NOT NULL DEFAULT 0,
            engaged_seconds INTEGER NOT NULL DEFAULT 0,
            core_actions INTEGER NOT NULL DEFAULT 0,
            last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, activity_date)
        )
    """))
    db.session.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_product_activity_day_date_user
        ON product_activity_day (activity_date, user_id)
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS organisation_billing (
            organisation_id INTEGER PRIMARY KEY,
            plan_code VARCHAR(30) NOT NULL DEFAULT 'launch',
            status VARCHAR(20) NOT NULL DEFAULT 'trial',
            monthly_fee_kes INTEGER,
            active_user_cap INTEGER,
            started_at TIMESTAMP,
            expires_at TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS organisation_campaign_meter (
            organisation_id INTEGER NOT NULL,
            period_start DATE NOT NULL,
            impressions INTEGER NOT NULL DEFAULT 0,
            clicks INTEGER NOT NULL DEFAULT 0,
            applications INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (organisation_id, period_start)
        )
    """))
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS student_opportunity_discovery (
            user_id INTEGER PRIMARY KEY,
            discoverable BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.session.commit()


def _period_start(plan):
    """Return the quota period start without tying usage to billing cadence."""
    now = datetime.utcnow()
    if plan.get("quota_period") == "annual":
        return date(now.year, 1, 1)
    return date(now.year, now.month, 1)


def _csrf_ok():
    expected = session.get("csrf_token")
    supplied = request.headers.get("X-CSRF-Token")
    return bool(expected and supplied and expected == supplied)


def _current_student_plan(db, user_id):
    row = db.session.execute(text("""
        SELECT plan, subscription_expires_at
        FROM payment
        WHERE user_id = :uid
          AND payment_type = 'subscription'
          AND status = 'success'
          AND subscription_expires_at IS NOT NULL
        ORDER BY subscription_expires_at DESC
        LIMIT 1
    """), {"uid": user_id}).mappings().first()
    if row and row["subscription_expires_at"] and row["subscription_expires_at"] > datetime.utcnow():
        return "premium"
    return "free"


def _usage_row(db, user_id, feature):
    plan_code = _current_student_plan(db, user_id)
    plan = STUDENT_PLANS[plan_code]
    return db.session.execute(text("""
        SELECT units, requests
        FROM student_ai_usage
        WHERE user_id = :uid AND period_start = :period AND feature = :feature
    """), {"uid": user_id, "period": _period_start(plan), "feature": feature}).mappings().first()


def check_and_consume_ai_quota(db, user_id, feature, units):
    """Atomically consume a generation allowance before an AI call."""
    if feature not in FEATURES:
        return True, {"feature": feature}

    try:
        units = int(units)
    except (TypeError, ValueError):
        return False, {"error": "Invalid generation amount"}
    if units <= 0:
        return False, {"error": "Generation amount must be positive"}

    plan_code = _current_student_plan(db, user_id)
    plan = STUDENT_PLANS[plan_code]
    request_limit_key, unit_limit_key = FEATURES[feature]
    max_requests = int(plan[request_limit_key])
    max_units = int(plan[unit_limit_key])

    if units > max_units:
        return False, {
            "error": f"This plan supports at most {max_units} {('pages' if feature == 'summary' else 'minutes' if feature == 'podcast' else 'cards' if feature == 'flashcards' else 'questions' if feature == 'quiz' else 'nodes')} per generation.",
            "code": "generation_size_limit",
            "feature": feature,
            "plan": plan_code,
            "max_units": max_units,
        }

    period = _period_start(plan)
    db.session.execute(text("""
        INSERT INTO student_ai_usage
            (user_id, period_start, feature, units, requests, updated_at)
        VALUES (:uid, :period, :feature, 0, 0, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id, period_start, feature) DO NOTHING
    """), {"uid": user_id, "period": period, "feature": feature})

    row = db.session.execute(text("""
        SELECT units, requests
        FROM student_ai_usage
        WHERE user_id = :uid AND period_start = :period AND feature = :feature
        FOR UPDATE
    """), {"uid": user_id, "period": period, "feature": feature}).mappings().first()

    used_requests = int(row["requests"] or 0)
    used_units = int(row["units"] or 0)
    total_unit_limit = max_units * max_requests

    if used_requests >= max_requests or used_units + units > total_unit_limit:
        db.session.rollback()
        return False, {
            "error": "You have reached this plan's generation allowance.",
            "code": "generation_quota_exhausted",
            "feature": feature,
            "plan": plan_code,
            "used_requests": used_requests,
            "request_limit": max_requests,
            "used_units": used_units,
            "unit_limit": total_unit_limit,
        }

    db.session.execute(text("""
        UPDATE student_ai_usage
        SET units = units + :units,
            requests = requests + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :uid AND period_start = :period AND feature = :feature
    """), {
        "uid": user_id, "period": period, "feature": feature, "units": units,
    })
    db.session.commit()

    return True, {
        "feature": feature,
        "plan": plan_code,
        "used_requests": used_requests + 1,
        "request_limit": max_requests,
        "used_units": used_units + units,
        "unit_limit": total_unit_limit,
        "max_units_per_generation": max_units,
        "period_start": period,
    }

def refund_ai_quota(db, user_id, feature, units, period_start=None):
    """Return a previously reserved generation allowance after a failed call."""
    if feature not in FEATURES:
        return
    try:
        units = max(1, int(units))
    except (TypeError, ValueError):
        return
    plan_code = _current_student_plan(db, user_id)
    plan = STUDENT_PLANS[plan_code]
    period = period_start or _period_start(plan)
    db.session.execute(text("""
        UPDATE student_ai_usage
        SET units = GREATEST(0, units - :units),
            requests = GREATEST(0, requests - 1),
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :uid AND period_start = :period AND feature = :feature
    """), {"uid": user_id, "period": period, "feature": feature, "units": units})
    db.session.commit()


def _active_user_ids(db, since_date):
    rows = db.session.execute(text("""
        SELECT DISTINCT user_id
        FROM product_activity_day
        WHERE activity_date >= :since_date
          AND (engaged_seconds >= 30 OR core_actions > 0)
    """), {"since_date": since_date}).all()
    return {int(row[0]) for row in rows}


def _online_user_count(db):
    row = db.session.execute(text("""
        SELECT COUNT(*)
        FROM product_activity_day
        WHERE activity_date = CURRENT_DATE
          AND last_seen_at >= CURRENT_TIMESTAMP - INTERVAL '2 minutes'
          AND (engaged_seconds >= 30 OR core_actions > 0)
    """)).scalar_one()
    return int(row or 0)


def register_usage_billing(app, db):
    _ensure_schema(db)

    @app.post("/api/analytics/heartbeat")
    def analytics_heartbeat():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        if not _csrf_ok():
            return jsonify({"error": "Invalid CSRF token"}), 403

        data = request.get_json(silent=True) or {}
        try:
            engagement_seconds = max(0, min(120, int(data.get("engagement_seconds", 0))))
            core_actions = max(0, min(20, int(data.get("core_actions", 0))))
            session_start = bool(data.get("session_start", False))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid activity payload"}), 400

        today = date.today()
        db.session.execute(text("""
            INSERT INTO product_activity_day
                (user_id, activity_date, sessions, engaged_seconds, core_actions, last_seen_at)
            VALUES (:uid, :day, :sessions, :seconds, :actions, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, activity_date)
            DO UPDATE SET
                sessions = product_activity_day.sessions + EXCLUDED.sessions,
                engaged_seconds = product_activity_day.engaged_seconds + EXCLUDED.engaged_seconds,
                core_actions = product_activity_day.core_actions + EXCLUDED.core_actions,
                last_seen_at = CURRENT_TIMESTAMP
        """), {
            "uid": user_id, "day": today,
            "sessions": 1 if session_start else 0,
            "seconds": engagement_seconds, "actions": core_actions,
        })
        db.session.commit()
        return jsonify({"ok": True})

    @app.post("/api/opportunity-discovery")
    def opportunity_discovery():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        if not _csrf_ok():
            return jsonify({"error": "Invalid CSRF token"}), 403
        data = request.get_json(silent=True) or {}
        discoverable = bool(data.get("discoverable", False))
        db.session.execute(text("""
            INSERT INTO student_opportunity_discovery
                (user_id, discoverable, updated_at)
            VALUES (:uid, :discoverable, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id)
            DO UPDATE SET discoverable = EXCLUDED.discoverable,
                          updated_at = CURRENT_TIMESTAMP
        """), {"uid": user_id, "discoverable": discoverable})
        db.session.commit()
        return jsonify({"discoverable": discoverable})

    @app.get("/api/opportunity-discovery")
    def get_opportunity_discovery():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        value = db.session.execute(text("""
            SELECT discoverable
            FROM student_opportunity_discovery
            WHERE user_id = :uid
        """), {"uid": user_id}).scalar_one_or_none()
        return jsonify({"discoverable": bool(value)})

    @app.get("/api/organisations/<int:organisation_id>/candidates")
    def organisation_candidates(organisation_id):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        role = _org_member(organisation_id, user_id)
        if role not in ("owner", "manager"):
            return jsonify({"error": "Organisation membership required"}), 403

        # Only students who explicitly opted into opportunity discovery are
        # returned. Activity is aggregated to recent active days/sessions;
        # exact online timestamps are never exposed.
        days = request.args.get("days", default=7, type=int)
        days = max(1, min(30, days))
        billing_row = db.session.execute(text("""
            SELECT plan_code, active_user_cap, status, expires_at
            FROM organisation_billing
            WHERE organisation_id = :oid
        """), {"oid": organisation_id}).mappings().first()
        if billing_row and billing_row["status"] == "active" and billing_row["expires_at"] and billing_row["expires_at"] <= datetime.utcnow():
            db.session.execute(text("""
                UPDATE organisation_billing
                SET status = 'expired', updated_at = CURRENT_TIMESTAMP
                WHERE organisation_id = :oid AND status = 'active'
            """), {"oid": organisation_id})
            db.session.commit()
            return jsonify({"error": "Organisation plan has expired", "code": "organisation_plan_expired"}), 402
        if billing_row and billing_row["status"] == "pending":
            return jsonify({"error": "Complete organisation plan payment before accessing candidate discovery", "code": "organisation_plan_pending"}), 402
        plan_code = str((billing_row or {}).get("plan_code") or "launch")
        plan = ORGANISATION_PLANS.get(plan_code, ORGANISATION_PLANS["launch"])
        candidate_limit = int(plan["active_user_cap"] or 5000)

        rows = db.session.execute(text("""
            SELECT
                u.id,
                u.display_name,
                u.university_id,
                un.name AS university_name,
                u.program_id,
                p.name AS program_name,
                u.year,
                u.semester,
                COUNT(a.activity_date) AS active_days,
                COALESCE(SUM(a.sessions), 0) AS sessions
            FROM "user" AS u
            JOIN student_opportunity_discovery AS d
              ON d.user_id = u.id AND d.discoverable = TRUE
            LEFT JOIN product_activity_day AS a
              ON a.user_id = u.id
             AND a.activity_date >= CURRENT_DATE - :days
             AND (a.engaged_seconds >= 30 OR a.core_actions > 0)
            LEFT JOIN university AS un ON un.id = u.university_id
            LEFT JOIN program AS p ON p.id = u.program_id
            WHERE u.is_suspended = FALSE
            GROUP BY u.id, u.display_name, u.university_id, un.name,
                     u.program_id, p.name, u.year, u.semester
            HAVING COUNT(a.activity_date) > 0
            ORDER BY active_days DESC, sessions DESC, u.id DESC
            LIMIT :candidate_limit
        """), {"days": days - 1, "candidate_limit": candidate_limit}).mappings().all()

        return jsonify({
            "window_days": days,
            "plan": plan_code,
            "candidate_limit": candidate_limit,
            "candidates": [
                {
                    "id": int(row["id"]),
                    "display_name": row["display_name"],
                    "university_id": row["university_id"],
                    "university_name": row["university_name"],
                    "program_id": row["program_id"],
                    "program_name": row["program_name"],
                    "year": row["year"],
                    "semester": row["semester"],
                    "active_days": int(row["active_days"] or 0),
                    "sessions": int(row["sessions"] or 0),
                }
                for row in rows
            ],
        })

    @app.get("/api/usage/me")
    def usage_me():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        plan_code = _current_student_plan(db, user_id)
        plan = STUDENT_PLANS[plan_code]
        usage = {}
        for feature in FEATURES:
            row = _usage_row(db, user_id, feature)
            usage[feature] = {
                "requests": int(row["requests"]) if row else 0,
                "units": int(row["units"]) if row else 0,
            }
        return jsonify({
            "plan": plan_code,
            "price_kes": plan["price_kes"],
            "billing_period": plan["billing_period"],
            "limits": plan,
            "usage": usage,
            "period_start": _period_start(plan).isoformat(),
        })

    @app.get("/api/student-plans")
    def student_plans():
        # These defaults match the current student subscription UI pricing:
        # KES 599/semester and KES 999/annual. The current student checkout
        # is a hosted payment flow; keep pricing in one server-owned layer
        # before adding another payment provider.
        plans = [
            {"code": "free", **STUDENT_PLANS["free"]},
            {
                "code": "premium",
                **STUDENT_PLANS["premium"],
                "price_options": {
                    "semester": 599,
                    "annual": 999,
                },
            },
        ]
        return jsonify({"currency": "KES", "plans": plans})

    # Enforce the existing generation endpoints without requiring the
    # frontend to invent a second billing API. The request is rejected before
    # an AI call starts, and the existing route then remains responsible for
    # generation/persistence.
    # Generation quotas are enforced inside ai_reusable_generation.py
    # after artifact reuse has been ruled out, so cached/shared material
    # never consumes a student's allowance.

    def _org_member(org_id, user_id):
        return db.session.execute(text("""
            SELECT role
            FROM organisation_member
            WHERE organisation_id = :oid AND user_id = :uid
            LIMIT 1
        """), {"oid": org_id, "uid": user_id}).scalar_one_or_none()

    @app.get("/api/organisations/<int:organisation_id>/audience")
    def organisation_audience(organisation_id):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        role = _org_member(organisation_id, user_id)
        if role not in ("owner", "manager"):
            return jsonify({"error": "Organisation membership required"}), 403

        today = date.today()
        dau = len(_active_user_ids(db, today))
        wau = len(_active_user_ids(db, today - timedelta(days=6)))
        mau = len(_active_user_ids(db, today - timedelta(days=29)))

        row = db.session.execute(text("""
            SELECT plan_code, status, monthly_fee_kes, active_user_cap
            FROM organisation_billing
            WHERE organisation_id = :oid
        """), {"oid": organisation_id}).mappings().first()
        billing = dict(row) if row else {
            "plan_code": "launch", "status": "trial",
            "monthly_fee_kes": ORGANISATION_PLANS["launch"]["monthly_fee_kes"],
            "active_user_cap": ORGANISATION_PLANS["launch"]["active_user_cap"],
        }

        return jsonify({
            "audience": {
                "dau": dau,
                "wau": wau,
                "mau": mau,
                "definition": "Active means meaningful foreground engagement (30+ seconds) or a core action; signup/login alone does not count.",
            },
            "billing": billing,
            "pricing_model": {
                "basis": "active_user_band_plus_campaign_spend",
                "subscription_is_not_per_signup": True,
                "sponsored_cpm_kes": SPONSORED_CPM_KES,
                "sponsored_min_campaign_kes": SPONSORED_MIN_CAMPAIGN_KES,
                "plans": ORGANISATION_PLANS,
                "note": "Organisation subscription buys audience access, candidate discovery and analytics capacity. Sponsored campaigns are metered separately by verified impressions; CPM is the advertiser metric, while RPM is publisher-side revenue.",
            },
        })

    @app.get("/api/organisations/<int:organisation_id>/active-users")
    def organisation_active_users(organisation_id):
        """Returns aggregate reach only. Individual active/online presence is
        intentionally not exposed by this endpoint."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        role = _org_member(organisation_id, user_id)
        if role not in ("owner", "manager"):
            return jsonify({"error": "Organisation membership required"}), 403

        today = date.today()
        dau = len(_active_user_ids(db, today))
        wau = len(_active_user_ids(db, today - timedelta(days=6)))
        mau = len(_active_user_ids(db, today - timedelta(days=29)))
        online_now = _online_user_count(db)
        return jsonify({
            "dau": dau,
            "wau": wau,
            "mau": mau,
            "online_now": online_now,
            "online_note": "Online now is an aggregate count based on a recent foreground heartbeat; individual live presence is not exposed to organisations.",
            "active_definition": "At least 30 seconds of foreground engagement in a day or a core product action. Signup/login alone does not count.",
        })


    return None
