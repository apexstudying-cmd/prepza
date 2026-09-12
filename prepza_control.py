"""Narrow, read-only control surface for trusted Prepza developer tooling.

Every request requires both the admin-controlled database switch and a
separate Render-managed bearer secret. The first release is intentionally
read-only; write actions must be added as explicit, audited operations later.
"""

import hashlib
import hmac
import os
from datetime import datetime

from flask import jsonify, request


CONTROL_SETTING_KEY = "prepza_control_enabled"
CONTROL_TOKEN_ENV = "PREPZA_CONTROL_TOKEN"


def register_control_routes(
    app,
    db,
    SystemSetting,
    User,
    Document,
    DocumentContent,
    GeneratedMaterial,
    log_admin_action,
    limiter,
):
    """Register the protected control API on the existing Flask app."""

    def _enabled():
        setting = db.session.query(SystemSetting).filter_by(key=CONTROL_SETTING_KEY).first()
        return bool(setting and setting.value == "true")

    def _token():
        return os.environ.get(CONTROL_TOKEN_ENV, "").strip()

    def _authorized():
        if not _enabled():
            return False, (jsonify({"error": "Prepza control API is disabled"}), 503)
        configured = _token()
        if not configured:
            return False, (jsonify({"error": "Prepza control API is not configured"}), 503)
        header = request.headers.get("Authorization", "")
        scheme, _, supplied = header.partition(" ")
        if scheme.lower() != "bearer" or not supplied:
            return False, (jsonify({"error": "Authorization required"}), 401)
        if not hmac.compare_digest(supplied, configured):
            return False, (jsonify({"error": "Invalid authorization"}), 401)
        return True, None

    def _audit(action, details=None):
        try:
            digest = hashlib.sha256(request.headers.get("Authorization", "").encode()).hexdigest()[:16]
            log_admin_action(
                None,
                f"control_api_{action}",
                target_type="control_api",
                details={"token_fingerprint": digest, **(details or {})},
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception("Failed to write control API audit log")

    def _guard():
        ok, response = _authorized()
        return None if ok else response

    @app.route("/internal/control/v1/health", methods=["GET"])
    @limiter.limit("30 per minute")
    def control_health():
        denied = _guard()
        if denied:
            return denied
        _audit("health_checked")
        return jsonify({
            "status": "ok",
            "service": "prepza-control",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })

    @app.route("/internal/control/v1/status", methods=["GET"])
    @limiter.limit("30 per minute")
    def control_status():
        denied = _guard()
        if denied:
            return denied
        _audit("status_read")
        return jsonify({
            "enabled": True,
            "configured": True,
            "mode": "read_only",
            "capabilities": [
                "health",
                "status",
                "system_overview",
                "user_summary",
                "document_summary",
                "document_materials",
            ],
        })

    @app.route("/internal/control/v1/system/overview", methods=["GET"])
    @limiter.limit("20 per minute")
    def control_system_overview():
        denied = _guard()
        if denied:
            return denied
        _audit("system_overview_read")
        return jsonify({
            "users": User.query.count(),
            "documents": Document.query.filter_by(is_removed=False).count(),
            "document_contents": DocumentContent.query.count(),
            "generated_materials": GeneratedMaterial.query.count(),
            "ready_generated_materials": GeneratedMaterial.query.filter_by(status="ready").count(),
        })

    @app.route("/internal/control/v1/users/<int:user_id>/summary", methods=["GET"])
    @limiter.limit("20 per minute")
    def control_user_summary(user_id):
        denied = _guard()
        if denied:
            return denied
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        document_count = Document.query.filter_by(user_id=user_id, is_removed=False).count()
        _audit("user_summary_read", {"user_id": user_id})
        return jsonify({
            "id": user.id,
            "display_name": user.display_name,
            "year": user.year,
            "semester": user.semester,
            "university_id": user.university_id,
            "program_id": user.program_id,
            "is_admin": bool(user.is_admin),
            "is_suspended": bool(user.is_suspended),
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "document_count": document_count,
        })

    @app.route("/internal/control/v1/documents/<int:document_id>/summary", methods=["GET"])
    @limiter.limit("30 per minute")
    def control_document_summary(document_id):
        denied = _guard()
        if denied:
            return denied
        document = db.session.get(Document, document_id)
        if not document:
            return jsonify({"error": "Document not found"}), 404
        content = db.session.get(DocumentContent, document.document_content_id) if document.document_content_id else None
        _audit("document_summary_read", {"document_id": document_id})
        return jsonify({
            "id": document.id,
            "owner_user_id": document.user_id,
            "title": document.title,
            "original_filename": document.original_filename,
            "status": document.status,
            "is_removed": bool(document.is_removed),
            "created_at": document.created_at.isoformat() if document.created_at else None,
            "content": {
                "id": content.id if content else None,
                "status": content.status if content else None,
                "file_type": content.file_type if content else None,
                "file_size_bytes": content.file_size_bytes if content else None,
                "page_count": content.page_count if content else None,
                "error_message": content.error_message if content else None,
            },
        })

    @app.route("/internal/control/v1/documents/<int:document_id>/materials", methods=["GET"])
    @limiter.limit("20 per minute")
    def control_document_materials(document_id):
        denied = _guard()
        if denied:
            return denied
        document = db.session.get(Document, document_id)
        if not document or not document.document_content_id:
            return jsonify({"error": "Document not found"}), 404
        materials = (
            GeneratedMaterial.query
            .filter_by(document_content_id=document.document_content_id)
            .order_by(GeneratedMaterial.created_at.desc())
            .all()
        )
        _audit("document_materials_read", {"document_id": document_id})
        return jsonify({
            "document_id": document_id,
            "materials": [{
                "id": material.id,
                "material_type": material.material_type,
                "status": material.status,
                "scope": material.scope,
                "owner_user_id": material.owner_user_id,
                "generation_version": material.generation_version,
                "generation_parameters": material.generation_parameters,
                "created_at": material.created_at.isoformat() if material.created_at else None,
                "updated_at": material.updated_at.isoformat() if material.updated_at else None,
                "error_message": material.error_message,
            } for material in materials],
        })
