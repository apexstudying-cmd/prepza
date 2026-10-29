"""Privacy-safe HTTP correlation, slow/error event capture, and admin alert summary."""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from flask import g, has_request_context, jsonify, request
from sqlalchemy import inspect, text

logger = logging.getLogger("prepza.http_observability")

def scrub_sentry_event(event, hint):
    """Remove request/user payloads before any Sentry event leaves the process.

    Sentry's Flask integration may attach request context even to a generic
    alert message. Preserve only the matched route template, never arbitrary
    path parameters, and drop query, body, cookies, headers, breadcrumbs,
    extras, and direct user identifiers.
    """
    if not isinstance(event, dict):
        return event

    sanitized = dict(event)
    request_data = sanitized.get("request")
    if isinstance(request_data, dict):
        request_data = dict(request_data)
        url = request_data.get("url")
        if isinstance(url, str):
            try:
                parsed = urlsplit(url)
                route_template = (
                    request.url_rule.rule
                    if has_request_context() and request.url_rule
                    else "unmatched"
                )
                request_data["url"] = urlunsplit(
                    (parsed.scheme, parsed.netloc, route_template, "", "")
                )
            except ValueError:
                request_data.pop("url", None)
        for key in ("query_string", "data", "cookies", "headers", "env"):
            request_data.pop(key, None)
        sanitized["request"] = request_data

    user_data = sanitized.get("user")
    if isinstance(user_data, dict):
        user_data = dict(user_data)
        for key in ("id", "email", "username", "ip_address", "name"):
            user_data.pop(key, None)
        if user_data:
            sanitized["user"] = user_data
        else:
            sanitized.pop("user", None)

    contexts = sanitized.get("contexts")
    if isinstance(contexts, dict):
        contexts = dict(contexts)
        contexts.pop("request", None)
        sanitized["contexts"] = contexts

    # Breadcrumbs/extras can accidentally retain student prompts or page text.
    sanitized.pop("breadcrumbs", None)
    sanitized.pop("extra", None)
    return sanitized

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


def _dispatch_external_alerts(alerts):
    """Send threshold-crossing metadata to Sentry when the existing DSN is configured."""
    if not os.environ.get("SENTRY_DSN"):
        return
    try:
        import sentry_sdk
    except Exception as exc:
        logger.warning(json.dumps({
            "event": "http_observability_alert_delivery_failed",
            "alert_keys": [alert["key"] for alert in alerts],
            "exception_type": type(exc).__name__,
        }, separators=(",", ":"), sort_keys=True))
        return

    for alert in alerts:
        try:
            sentry_sdk.capture_message(
                "Prepza HTTP observability alert "
                f"{alert['key']}: {alert['count']} events in "
                f"{alert['window_minutes']} minutes (threshold {alert['threshold']}).",
                level="error" if alert["severity"] == "critical" else "warning",
            )
        except Exception as exc:
            # Never let the external alert sink change the HTTP response.
            logger.warning(json.dumps({
                "event": "http_observability_alert_delivery_failed",
                "alert_key": alert["key"],
                "exception_type": type(exc).__name__,
            }, separators=(",", ":"), sort_keys=True))


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
                crossed = []
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

                    # Evaluate alert thresholds at the event that crosses them,
                    # not only when an administrator happens to open the panel.
                    recent_start = datetime.utcnow() - timedelta(minutes=ALERT_WINDOW_MINUTES)
                    recent_5xx = connection.execute(text("""
                        SELECT COUNT(*) FROM request_observability_event
                        WHERE occurred_at >= :recent_start AND status_code >= 500
                    """), {"recent_start": recent_start}).scalar_one()
                    recent_slow = connection.execute(text("""
                        SELECT COUNT(*) FROM request_observability_event
                        WHERE occurred_at >= :recent_start AND duration_ms >= :slow_ms
                    """), {
                        "recent_start": recent_start,
                        "slow_ms": SLOW_REQUEST_MS,
                    }).scalar_one()
                    crossed = [
                        alert for alert in evaluate_alerts(
                            recent_5xx=recent_5xx, recent_slow=recent_slow
                        )
                        if (
                            alert["key"] == "http_5xx_spike"
                            and recent_5xx == HTTP_5XX_ALERT_THRESHOLD
                        ) or (
                            alert["key"] == "slow_request_spike"
                            and recent_slow == SLOW_REQUEST_ALERT_THRESHOLD
                        )
                    ]
                # Emit logs and external alerts only after the event transaction
                # commits, and never hold a database connection during dispatch.
                if crossed:
                    logger.warning(json.dumps({
                        "event": "http_observability_alert_threshold_crossed",
                        "alert_keys": [alert["key"] for alert in crossed],
                        "recent_5xx": recent_5xx,
                        "recent_slow": recent_slow,
                        "window_minutes": ALERT_WINDOW_MINUTES,
                    }, separators=(",", ":"), sort_keys=True))
                    _dispatch_external_alerts(crossed)
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
            recent_query = RequestObservabilityEvent.query.filter(
                RequestObservabilityEvent.occurred_at >= recent_start
            )
            recent_5xx = recent_query.filter(
                RequestObservabilityEvent.status_code >= 500
            ).count()
            recent_slow = recent_query.filter(
                RequestObservabilityEvent.duration_ms >= SLOW_REQUEST_MS
            ).count()
            hour_event_count = RequestObservabilityEvent.query.filter(
                RequestObservabilityEvent.occurred_at >= hour_start
            ).count()
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

        alerts = evaluate_alerts(recent_5xx=recent_5xx, recent_slow=recent_slow)

        return jsonify({
            "status": "ok",
            "window_minutes": ALERT_WINDOW_MINUTES,
            "summary": {
                "recent_5xx": recent_5xx,
                "recent_slow": recent_slow,
                "events_last_hour": hour_event_count,
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
