"""Operator-facing admin health and provider telemetry."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os
import requests
from flask import jsonify

RENDER_API = "https://api.render.com/v1"


def _last_value(series):
    if not isinstance(series, list) or not series:
        return None
    values = series[0].get("values") or []
    if not values:
        return None
    return values[-1].get("value")


def _provider_metric(api_key, endpoint, service_id):
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=15)
    try:
        response = requests.get(
            f"{RENDER_API}{endpoint}",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            params={
                "resource": service_id,
                "startTime": start.isoformat(),
                "endTime": now.isoformat(),
                "resolutionSeconds": 60,
            },
            timeout=5,
        )
        response.raise_for_status()
        return _last_value(response.json())
    except Exception as exc:
        return {"error": str(exc)[:180]}


def register_admin_operations(app, db, require_admin):
    @app.get("/admin/operations")
    @require_admin
    def admin_operations():
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)

        def scalar(sql, params=None):
            try:
                return db.session.execute(db.text(sql), params or {}).scalar()
            except Exception:
                db.session.rollback()
                return None

        db_ok = scalar("SELECT 1") == 1
        db_size = int(scalar("SELECT pg_database_size(current_database())") or 0) if db_ok else None
        db_connections = scalar(
            "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()"
        ) if db_ok else None
        db_connection_limit = scalar("SELECT current_setting('max_connections')::integer") if db_ok else None

        total_students = scalar('SELECT count(*) FROM "user" WHERE COALESCE(is_admin,FALSE)=FALSE')
        active_today = scalar('SELECT count(*) FROM "user" WHERE last_active_at >= :cutoff',
                              {"cutoff": day_ago})
        active_7d = scalar('SELECT count(*) FROM "user" WHERE last_active_at >= :cutoff',
                           {"cutoff": week_ago})

        # Study Hub time is a separate, authoritative signal from
        # last_active_at. These figures come from StudyTimeLog, so the
        # admin dashboard reports the same totals the student sees after
        # server reconciliation.
        study_tz = ZoneInfo(os.environ.get("PREPZA_TIMEZONE", "Africa/Nairobi"))
        study_date = datetime.now(study_tz).date()
        study_week_start = study_date - timedelta(days=6)

        study_today = scalar(
            """SELECT COALESCE(SUM(st.study_time_seconds),0)
               FROM study_time_log st
               JOIN "user" u ON u.id = st.user_id
               WHERE st.activity_date = :study_date
                 AND st.feature = 'study_hub'
                 AND COALESCE(u.is_admin,FALSE)=FALSE""",
            {"study_date": study_date},
        )
        study_7d = scalar(
            """SELECT COALESCE(SUM(st.study_time_seconds),0)
               FROM study_time_log st
               JOIN "user" u ON u.id = st.user_id
               WHERE st.activity_date >= :start_date
                 AND st.activity_date <= :study_date
                 AND st.feature = 'study_hub'
                 AND COALESCE(u.is_admin,FALSE)=FALSE""",
            {"start_date": study_week_start, "study_date": study_date},
        )
        students_studied_today = scalar(
            """SELECT count(DISTINCT st.user_id)
               FROM study_time_log st
               JOIN "user" u ON u.id = st.user_id
               WHERE st.activity_date = :study_date
                 AND st.feature = 'study_hub'
                 AND st.study_time_seconds > 0
                 AND COALESCE(u.is_admin,FALSE)=FALSE""",
            {"study_date": study_date},
        )
        students_qualifying_today = scalar(
            """SELECT count(DISTINCT st.user_id)
               FROM study_time_log st
               JOIN "user" u ON u.id = st.user_id
               WHERE st.activity_date = :study_date
                 AND st.feature = 'study_hub'
                 AND st.study_time_seconds >= 600
                 AND COALESCE(u.is_admin,FALSE)=FALSE""",
            {"study_date": study_date},
        )
        study_top_students = db.session.execute(db.text(
            """SELECT u.id, u.display_name, u.email, u.last_active_at,
                      COALESCE(st.study_seconds_today,0) AS study_seconds_today,
                      COALESCE(sw.study_seconds_7d,0) AS study_seconds_7d
               FROM "user" u
               LEFT JOIN (
                 SELECT user_id, SUM(study_time_seconds) AS study_seconds_today
                 FROM study_time_log
                 WHERE activity_date = :study_date
                   AND feature = 'study_hub'
                 GROUP BY user_id
               ) st ON st.user_id = u.id
               LEFT JOIN (
                 SELECT user_id, SUM(study_time_seconds) AS study_seconds_7d
                 FROM study_time_log
                 WHERE activity_date >= :start_date
                   AND activity_date <= :study_date
                   AND feature = 'study_hub'
                 GROUP BY user_id
               ) sw ON sw.user_id = u.id
               WHERE COALESCE(u.is_admin,FALSE)=FALSE
                 AND (COALESCE(st.study_seconds_today,0) > 0
                      OR u.last_active_at >= :active_cutoff)
               ORDER BY COALESCE(st.study_seconds_today,0) DESC,
                        u.last_active_at DESC NULLS LAST
               LIMIT 50"""
        ), {
            "start_date": study_week_start,
            "study_date": study_date,
            "active_cutoff": day_ago,
        }).mappings().all()

        ai = {}
        for status in ("queued", "processing", "completed", "failed"):
            ai[status] = scalar(
                "SELECT count(*) FROM ai_job WHERE status=:status", {"status": status}
            )
        podcast_queued = scalar(
            "SELECT count(*) FROM ai_job WHERE feature='podcast' AND status IN ('queued','processing')"
        )
        ai_spend = scalar(
            "SELECT COALESCE(sum(cost_usd),0) FROM ai_usage_log WHERE created_at >= :cutoff",
            {"cutoff": week_ago},
        )

        b2b_active = scalar("SELECT count(*) FROM discovery_campaign WHERE status='active'")
        b2b_events_24h = scalar(
            "SELECT count(*) FROM discovery_event WHERE created_at >= :cutoff",
            {"cutoff": day_ago},
        )
        b2b_spend_24h = scalar(
            """SELECT COALESCE(sum(-signed_amount_minor),0)
               FROM b2b_campaign_ledger
               WHERE entry_type LIKE 'delivery_%'
                 AND created_at >= :cutoff""",
            {"cutoff": day_ago},
        )

        render = {
            "configured": bool(os.environ.get("RENDER_API_KEY") and os.environ.get("RENDER_SERVICE_ID")),
            "service_id": os.environ.get("RENDER_SERVICE_ID") or None,
            "status": "not_configured",
            "service": None,
            "cpu_percent": None,
            "memory_percent": None,
            "http_requests": None,
            "bandwidth_gb": None,
            "instance_count": None,
            "error": None,
        }
        render_key = os.environ.get("RENDER_API_KEY")
        render_service = os.environ.get("RENDER_SERVICE_ID")
        if render_key and render_service:
            try:
                service_response = requests.get(
                    f"{RENDER_API}/services/{render_service}",
                    headers={"Authorization": f"Bearer {render_key}", "Accept": "application/json"},
                    timeout=5,
                )
                service_response.raise_for_status()
                service = service_response.json()
                render["service"] = {
                    "id": service.get("id"),
                    "name": service.get("name"),
                    "branch": service.get("branch"),
                    "suspended": service.get("suspended"),
                    "dashboard_url": service.get("dashboardUrl"),
                    "plan": (service.get("serviceDetails") or {}).get("plan"),
                    "region": (service.get("serviceDetails") or {}).get("region"),
                    "instances": (service.get("serviceDetails") or {}).get("numInstances"),
                }
                render["status"] = "ok" if service.get("suspended") != "suspended" else "suspended"
                render["cpu_percent"] = _provider_metric(render_key, "/metrics/cpu", render_service)
                render["memory_percent"] = _provider_metric(render_key, "/metrics/memory", render_service)
                render["http_requests"] = _provider_metric(render_key, "/metrics/http-requests", render_service)
                render["bandwidth_gb"] = _provider_metric(render_key, "/metrics/bandwidth", render_service)
                render["instance_count"] = _provider_metric(render_key, "/metrics/instance-count", render_service)
            except Exception as exc:
                render["status"] = "error"
                render["error"] = str(exc)[:240]

        supabase = {
            "database_measured": db_size is not None,
            "database_bytes": db_size,
            "active_connections": db_connections,
            "connection_limit": db_connection_limit,
            "management_billing": "not_connected",
            "message": "Database usage is measured here. Supabase plan billing/quotas remain authoritative in Supabase until a management API connection is configured.",
        }

        checks = [
            {"key": "database", "label": "Postgres", "status": "ok" if db_ok else "error"},
            {"key": "render", "label": "Render", "status": render["status"]},
            {"key": "ai_queue", "label": "AI queue", "status": "ok" if ai.get("failed", 0) == 0 else "attention"},
            {"key": "podcast", "label": "Podcast queue", "status": "ok" if (podcast_queued or 0) < 50 else "attention"},
            {"key": "b2b", "label": "B2B delivery", "status": "ok"},
        ]

        return jsonify({
            "generated_at": now.isoformat() + "Z",
            "checks": checks,
            "students": {
                "total": int(total_students or 0),
                "active_today": int(active_today or 0),
                "active_7d": int(active_7d or 0),
                "studied_today": int(students_studied_today or 0),
                "qualifying_today": int(students_qualifying_today or 0),
                "study_seconds_today": int(study_today or 0),
                "study_seconds_7d": int(study_7d or 0),
                "study_top_students": [
                    {
                        "id": int(row["id"]),
                        "display_name": row["display_name"],
                        "email": row["email"],
                        "last_active_at": row["last_active_at"].isoformat() if row["last_active_at"] else None,
                        "study_seconds_today": int(row["study_seconds_today"] or 0),
                        "study_seconds_7d": int(row["study_seconds_7d"] or 0),
                    }
                    for row in study_top_students
                ],
            },
            "database": {"ok": db_ok, "size_bytes": db_size, "active_connections": db_connections, "connection_limit": db_connection_limit},
            "supabase": supabase,
            "ai": {**{k: int(v or 0) for k, v in ai.items()}, "podcast_queued_or_processing": int(podcast_queued or 0), "spend_7d_usd": round(float(ai_spend or 0), 4)},
            "b2b": {"active_campaigns": int(b2b_active or 0), "events_24h": int(b2b_events_24h or 0), "delivery_spend_24h_minor": int(b2b_spend_24h or 0)},
            "render": render,
            "release": {
                "main_branch": "main",
                "provider_plan_changes_automatic": False,
                "message": "This dashboard reports measured state. It never upgrades Render or Supabase automatically.",
            },
        })
