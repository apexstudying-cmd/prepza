"""Admin infrastructure and pay-as-you-grow monitoring.

Read-only telemetry for the operator dashboard. It never changes a provider
plan automatically. The goal is to show measured usage, known free-tier
ceilings, estimated spend, and explicit upgrade signals before a bill arrives.
"""
from datetime import datetime, timedelta
from flask import jsonify, session
from sqlalchemy import func


def register_infrastructure_monitoring(app, db, require_admin, SystemSetting,
                                       User, DocumentContent, AiUsageLog,
                                       Payment, StudyActivityLog, StudyTimeLog):
    SUPABASE = {
        "database": {"limit": 500 * 1024 * 1024, "label": "Database", "unit": "bytes"},
        "storage": {"limit": 1 * 1024 * 1024 * 1024, "label": "File storage", "unit": "bytes"},
        "egress": {"limit": 5, "label": "Egress", "unit": "gb"},
        "realtime_messages": {"limit": 2_000_000, "label": "Realtime messages", "unit": "messages"},
        "realtime_connections": {"limit": 200, "label": "Realtime peak connections", "unit": "connections"},
    }

    def _pct(used, limit):
        if not limit:
            return None
        return round((float(used) / float(limit)) * 100, 2)

    def _status(pct):
        if pct is None:
            return "unknown"
        if pct >= 100:
            return "limit"
        if pct >= 90:
            return "action_soon"
        if pct >= 75:
            return "watch"
        return "ok"

    @app.route("/admin/infrastructure")
    @require_admin
    def admin_infrastructure():
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        day_start = now - timedelta(days=1)
        week_start = now - timedelta(days=7)
        month_days = (datetime(now.year + (1 if now.month == 12 else 0),
                               1 if now.month == 12 else now.month + 1, 1) - month_start).days
        elapsed_days = max((now - month_start).days + 1, 1)

        db_bytes = int(db.session.execute(
            db.text("SELECT pg_database_size(current_database())")
        ).scalar() or 0)
        storage_bytes = int(db.session.query(
            func.coalesce(func.sum(DocumentContent.file_size_bytes), 0)
        ).scalar() or 0)

        ai_rows = db.session.query(
            func.count(AiUsageLog.id),
            func.coalesce(func.sum(AiUsageLog.cost_usd), 0),
            func.coalesce(func.sum(AiUsageLog.input_tokens), 0),
            func.coalesce(func.sum(AiUsageLog.output_tokens), 0),
        ).filter(AiUsageLog.created_at >= month_start).one()
        ai_requests, ai_spend, input_tokens, output_tokens = ai_rows
        ai_spend = float(ai_spend or 0)
        ai_projected = round(ai_spend / elapsed_days * month_days, 2)

        budget_row = SystemSetting.query.filter_by(key="ai_monthly_budget_usd").first()
        try:
            ai_budget = float(budget_row.value) if budget_row and budget_row.value else None
        except (TypeError, ValueError):
            ai_budget = None
        ai_budget_pct = _pct(ai_spend, ai_budget) if ai_budget else None

        active_1d = int(db.session.query(func.count(User.id)).filter(
            User.last_active_at >= day_start).scalar() or 0)
        active_7d = int(db.session.query(func.count(User.id)).filter(
            User.last_active_at >= week_start).scalar() or 0)
        active_30d = int(db.session.query(func.count(User.id)).filter(
            User.last_active_at >= month_start).scalar() or 0)

        study_1d = int(db.session.query(
            func.count(func.distinct(StudyActivityLog.user_id))
        ).filter(StudyActivityLog.activity_date == now.date()).scalar() or 0)
        study_seconds_1d = int(db.session.query(
            func.coalesce(func.sum(StudyTimeLog.study_time_seconds), 0)
        ).filter(StudyTimeLog.activity_date == now.date()).scalar() or 0)

        revenue = int(db.session.query(
            func.coalesce(func.sum(Payment.amount), 0)
        ).filter(Payment.status == "success", Payment.created_at >= month_start).scalar() or 0)

        # Paystack fees are variable, so these are estimates from the
        # recorded provider/channel metadata, never an accounting figure.
        success_payments = Payment.query.filter(
            Payment.status == "success", Payment.created_at >= month_start
        ).all()
        estimated_fees = 0.0
        for payment in success_payments:
            provider = (payment.provider or "").lower()
            if provider != "paystack":
                continue
            # phone_number is the best available launch-era indicator for
            # M-PESA; card transactions are otherwise conservatively treated
            # as local cards.
            rate = 0.015 if payment.phone_number else 0.029
            estimated_fees += float(payment.amount or 0) * rate

        by_feature = []
        rows = db.session.query(
            AiUsageLog.request_type,
            func.count(AiUsageLog.id),
            func.coalesce(func.sum(AiUsageLog.cost_usd), 0),
        ).filter(AiUsageLog.created_at >= month_start).group_by(
            AiUsageLog.request_type
        ).order_by(func.coalesce(func.sum(AiUsageLog.cost_usd), 0).desc()).all()
        for feature, requests, cost in rows:
            by_feature.append({
                "feature": feature,
                "requests": int(requests),
                "cost_usd": round(float(cost or 0), 4),
            })

        database_pct = _pct(db_bytes, SUPABASE["database"]["limit"])
        storage_pct = _pct(storage_bytes, SUPABASE["storage"]["limit"])

        return jsonify({
            "generated_at": now.isoformat() + "Z",
            "active_users": {"today": active_1d, "last_7d": active_7d, "last_30d": active_30d},
            "study": {
                "students_today": study_1d,
                "study_seconds_today": study_seconds_1d,
                "study_minutes_today": round(study_seconds_1d / 60, 1),
            },
            "database": {
                "used_bytes": db_bytes,
                "limit_bytes": SUPABASE["database"]["limit"],
                "percent": database_pct,
                "status": _status(database_pct),
            },
            "storage": {
                "used_bytes": storage_bytes,
                "limit_bytes": SUPABASE["storage"]["limit"],
                "percent": storage_pct,
                "status": _status(storage_pct),
            },
            "supabase_limits": {
                "egress_gb": SUPABASE["egress"]["limit"],
                "realtime_messages": SUPABASE["realtime_messages"]["limit"],
                "realtime_peak_connections": SUPABASE["realtime_connections"]["limit"],
            },
            "ai": {
                "requests_mtd": int(ai_requests or 0),
                "input_tokens_mtd": int(input_tokens or 0),
                "output_tokens_mtd": int(output_tokens or 0),
                "spend_mtd_usd": round(ai_spend, 4),
                "projected_month_end_usd": ai_projected,
                "budget_usd": ai_budget,
                "budget_percent": ai_budget_pct,
                "status": _status(ai_budget_pct) if ai_budget else "monitor",
                "by_feature": by_feature,
            },
            "payments": {
                "revenue_mtd_kes": revenue,
                "estimated_paystack_fees_mtd_kes": round(estimated_fees, 2),
                "estimated_net_after_paystack_kes": round(revenue - estimated_fees, 2),
                "note": "Estimated only; reconcile against Paystack settlement records.",
            },
            "known_limits": {
                "render_hobby_build_minutes": 500,
                "render_hobby_bandwidth_gb": 5,
                "render_runtime_metrics": "Use Render Billing/Service Metrics; not exposed to the app without a Render API key.",
                "brevo_free_daily_emails": 300,
                "supabase_free_egress_gb": 5,
                "supabase_free_cached_egress_gb": 5,
                "supabase_free_realtime_messages": 2_000_000,
                "supabase_free_realtime_peak_connections": 200,
            },
            "upgrade_policy": {
                "automatic_billing": False,
                "message": "Prepza never changes provider plans automatically. Upgrade only when a measured threshold is reached or the current tier blocks a required launch function.",
            },
        })


    @app.route("/documents/<int:document_id>/study-materials")
    def document_study_materials(document_id):
        """List all saved AI artifact variants for a document."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        from app import Document, GeneratedMaterial, _can_study_document
        document = db.session.get(Document, document_id)
        if not document or not _can_study_document(user_id, document):
            return jsonify({"error": "Document not found"}), 404
        if not document.document_content_id:
            return jsonify({"document_id": document_id, "materials": []})

        rows = (
            GeneratedMaterial.query
            .filter(
                GeneratedMaterial.document_content_id == document.document_content_id,
                GeneratedMaterial.generation_version == "v2",
                GeneratedMaterial.status.in_(["ready", "generating"]),
            )
            .order_by(GeneratedMaterial.updated_at.desc())
            .all()
        )
        visible = []
        for material in rows:
            if material.scope == "private" and material.owner_user_id != user_id:
                continue
            if material.scope not in {"private", "shared"}:
                continue
            visible.append({
                "material_id": material.id,
                "material_type": material.material_type,
                "status": material.status,
                "parameters": material.generation_parameters or {},
                "generation_version": material.generation_version,
                "generation_fingerprint": material.generation_fingerprint,
                "created_at": material.created_at.isoformat() if material.created_at else None,
                "updated_at": material.updated_at.isoformat() if material.updated_at else None,
            })
        return jsonify({"document_id": document_id, "materials": visible})

    @app.route("/documents/<int:document_id>/study-materials/<int:material_id>")
    def document_study_material(document_id, material_id):
        """Return one exact saved artifact variant for replay/viewing."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        from app import Document, GeneratedMaterial, _can_study_document
        document = db.session.get(Document, document_id)
        if not document or not _can_study_document(user_id, document):
            return jsonify({"error": "Document not found"}), 404
        material = db.session.get(GeneratedMaterial, material_id)
        if not material or material.document_content_id != document.document_content_id:
            return jsonify({"error": "Study material not found"}), 404
        if material.status != "ready" or not material.payload:
            return jsonify({"error": "Study material is not ready yet"}), 409
        if material.scope == "private" and material.owner_user_id != user_id:
            return jsonify({"error": "Study material not found"}), 404
        if material.scope not in {"private", "shared"}:
            return jsonify({"error": "Study material not found"}), 404

        import json
        try:
            payload = json.loads(material.payload)
        except (TypeError, ValueError):
            return jsonify({"error": "Study material payload is invalid"}), 500

        return jsonify({
            "document_id": document_id,
            "material_id": material.id,
            "material_type": material.material_type,
            "status": material.status,
            "parameters": material.generation_parameters or {},
            "generation_fingerprint": material.generation_fingerprint,
            "created_at": material.created_at.isoformat() if material.created_at else None,
            "updated_at": material.updated_at.isoformat() if material.updated_at else None,
            "payload": payload,
        })
