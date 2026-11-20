"""Read-only administrative audit-log route registration."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from flask import jsonify, request


def register_admin_audit_routes(
    app: Any,
    db: Any,
    AuditLog: Any,
    User: Any,
    require_admin: Any,
) -> None:
    """Register the existing admin audit-log endpoint without changing its contract."""

    @app.route("/admin/audit-logs")
    @require_admin
    def admin_list_audit_logs():
        """List recent audit entries with the existing filters and pagination."""
        try:
            days = int(request.args.get("days", 30))
        except ValueError:
            days = 30
        days = max(1, min(days, 365))
        window_start = datetime.utcnow() - timedelta(days=days)

        query = AuditLog.query.filter(AuditLog.created_at >= window_start)

        actor_id = request.args.get("actor_id", type=int)
        if actor_id:
            query = query.filter(AuditLog.actor_id == actor_id)

        action_filter = (request.args.get("action") or "").strip()
        if action_filter:
            query = query.filter(AuditLog.action.ilike(f"%{action_filter}%"))

        target_type = (request.args.get("target_type") or "").strip()
        if target_type:
            query = query.filter(AuditLog.target_type == target_type)

        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        per_page = 50

        entries = (
            query.order_by(AuditLog.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        result = []
        for entry in entries:
            actor = db.session.get(User, entry.actor_id) if entry.actor_id else None
            parsed_details = None
            if entry.details:
                try:
                    parsed_details = json.loads(entry.details)
                except (TypeError, ValueError):
                    parsed_details = entry.details
            result.append({
                "id": entry.id,
                "actor_id": entry.actor_id,
                "actor_email": actor.email if actor else None,
                "action": entry.action,
                "target_type": entry.target_type,
                "target_id": entry.target_id,
                "details": parsed_details,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            })

        return jsonify({"page": page, "logs": result})
