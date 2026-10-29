"""Privacy-safe HTTP correlation, slow/error event capture, and admin alert summary."""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timedelta

from flask import g, jsonify, request
from sqlalchemy import inspect, text

logger = logging.getLogger("prepza.http_observability")
SLOW_REQUEST_MS = 5000
ALERT_WINDOW_MINUTES = 5
HTTP_5XX_ALERT_THRESHOLD = 5
SLOW_REQUEST_ALERT_THRESHOLD = 10


def evaluate_alerts(*, recent_5xx: int, recent_slow: int) -> list[dict]:
    """Pure, deterministic threshold rules shared by the dashboard and tests."""
    alerts = []
    if recent_5xx >= HTTP_5XX_ALERT_THRESHOLD:
        alerts.append({
            "key": "http_5xx_spike",
            "severity": "critical",
            "count": int(recent_5xx),
            "threshold": HTTP_5XX_ALERT_THRESHOLD,
            "window_minutes": ALERT_WINDOW_MINUTES,
            "message": "Five or more server-error responses were recorded in five minutes.",
        })
    if recent_slow >= SLOW_REQUEST_ALERT_THRESHOLD:
        alerts.append({
            "key": "slow_request_spike",
            "severity": "warning",
            "count": int(recent_slow),
            "threshold": SLOW_REQUEST_ALERT_THRESHOLD,
            "window_minutes": ALERT_WINDOW_MINUTES,
            "message": "Ten or more requests exceeded the five-second latency threshold in five minutes.",
        })
    return alerts


def _request_id():
    # Generate the authoritative ID server-side rather than trusting a client
    # value that could deliberately collide with another request's trace.
    # Never log the URL query string, request body, cookies, user ID, or IP.
    return uuid.uuid4().hex


def register_request_observability(app, db, require_admin, RequestObservabilityEvent):
    """Register correlation headers/logs, bounded event storage, and admin JSON dashboard."""
    if getattr(app, "_prepza_request_observability_registered", False):
        return
    app._prepza_request_observability_registered = True

    @app.before_request
    def _begin_observed_request():
        g.prepza_request_id = _request_id()
        g.prepza_request_started = time.monotonic()

    @app.after_request
    def _finish_observed_request(response):
        request_id = getattr(g, "prepza_request_id", None) or uuid.uuid4().hex
        started = getattr(g, "prepza_request_started", None)
        duration_ms = round(max(0.0, time.monotonic() - started) * 1000, 2) if started is not None else None
        response.headers["X-Request-ID"] = request_id
        route_name = request.url_rule.rule if request.url_rule else "unmatched"
        status_code = int(response.status_code)

        record = {
            "event": "http_request_completed",
            "request_id": request_id,
            "method": request.method,
            "route": route_name,
            "status_code": status_code,
            "duration_ms": duration_ms,
        }
        logger.info(json.dumps(record, separators=(",", ":"), sort_keys=True))

        if status_code >= 500 or (duration_ms is not None and duration_ms >= SLOW_REQUEST_MS):
            try:
                # Deployments apply SQL migrations separately from app startup.
                # Keep telemetry non-invasive while the additive table is absent.
                if not inspect(db.engine).has_table("request_observability_event"):
                    return response
                # Use a separate engine transaction. Never commit the request's
                # application session as a side effect of telemetry collection.
                with db.engine.begin() as connection:
                    connection.execute(text("""
                        INSERT INTO request_observability_event
                            (request_id, method, route, status_code, duration_ms, occurred_at)
                        VALUES
                            (:request_id, :method, :route, :status_code, :duration_ms, CURRENT_TIMESTAMP)
                    """), {
                        "request_id": request_id,
                        "method": request.method[:12],
                        "route": route_name[:160],
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                    })
                    connection.execute(text(
                        "DELETE FROM request_observability_event WHERE occurred_at < :cutoff"
                    ), {"cutoff": datetime.utcnow() - timedelta(days=14)})
            except Exception as exc:  # telemetry must never change the response
                logger.warning(json.dumps({
                    "event": "http_observability_persist_failed",
                    "request_id": request_id,
                    "exception_type": type(exc).__name__,
                }, separators=(",", ":"), sort_keys=True))
        return response

    @app.route("/admin/observability", methods=["GET"])
    @require_admin
    def admin_observability():
        now = datetime.utcnow()
        recent_start = now - timedelta(minutes=ALERT_WINDOW_MINUTES)
        hour_start = now - timedelta(hours=1)
        try:
            if not inspect(db.engine).has_table("request_observability_event"):
                return jsonify({
                    "status": "unavailable",
                    "error": "Request observability schema is not ready",
                }), 503
            recent = RequestObservabilityEvent.query.filter(
                RequestObservabilityEvent.occurred_at >= recent_start
            ).all()
            hour_events = (
                RequestObservabilityEvent.query
                .filter(RequestObservabilityEvent.occurred_at >= hour_start)
                .order_by(RequestObservabilityEvent.occurred_at.desc())
                .limit(50)
                .all()
            )
        except Exception:
            db.session.rollback()
            return jsonify({
                "status": "unavailable",
                "error": "Request observability schema is not ready",
            }), 503

        recent_5xx = sum(1 for event in recent if event.status_code >= 500)
        recent_slow = sum(
            1 for event in recent
            if event.duration_ms is not None and event.duration_ms >= SLOW_REQUEST_MS
        )
        alerts = evaluate_alerts(recent_5xx=recent_5xx, recent_slow=recent_slow)
        if alerts:
            logger.warning(json.dumps({
                "event": "http_observability_alert_active",
                "alert_keys": [alert["key"] for alert in alerts],
                "recent_5xx": recent_5xx,
                "recent_slow": recent_slow,
            }, separators=(",", ":"), sort_keys=True))

        return jsonify({
            "status": "ok",
            "window_minutes": ALERT_WINDOW_MINUTES,
            "summary": {
                "recent_5xx": recent_5xx,
                "recent_slow": recent_slow,
                "events_last_hour": len(hour_events),
            },
            "alerts": alerts,
            "recent_events": [{
                "request_id": event.request_id,
                "method": event.method,
                "route": event.route,
                "status_code": event.status_code,
                "duration_ms": event.duration_ms,
                "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            } for event in hour_events],
        })
