import hmac
import os
from datetime import datetime

from flask import Blueprint, jsonify, request


bp = Blueprint("kokoro_control", __name__, url_prefix="/internal/kokoro")


def _authorized(token_name="KOKORO_WORKER_TOKEN") -> bool:
    expected = (os.environ.get(token_name) or "").strip()
    supplied = request.headers.get("Authorization", "")
    if not expected or not supplied.startswith("Bearer "):
        return False
    actual = supplied[7:].strip()
    return bool(actual) and hmac.compare_digest(actual, expected)


def register(app):
    app.register_blueprint(bp)


@bp.before_request
def require_worker_auth():
    # Worker endpoints and autoscaler endpoints use separate secrets.
    # A compromised worker token must not grant permission to provision GPUs.
    if request.path.endswith("/reconcile") or request.path.endswith("/recover"):
        if not _authorized("KOKORO_CONTROL_TOKEN"):
            return jsonify({"error": "Unauthorized"}), 401
    elif not _authorized("KOKORO_WORKER_TOKEN"):
        return jsonify({"error": "Unauthorized"}), 401


@bp.post("/jobs/claim")
def claim_job():
    """
    Atomically claim exactly one pending podcast-audio job.

    PostgreSQL SELECT ... FOR UPDATE SKIP LOCKED lets multiple future
    workers consume the same queue without two workers claiming the same
    job. One A2000 worker is the initial production configuration.
    """
    from app import AiJob, db

    worker_id = str((request.get_json(silent=True) or {}).get("worker_id") or "").strip()
    if not worker_id:
        return jsonify({"error": "worker_id is required"}), 400
    try:
        job = (
            AiJob.query
            .filter_by(feature="podcast_audio", status="pending")
            .order_by(AiJob.id.asc())
            .with_for_update(skip_locked=True)
            .first()
        )
        if not job:
            return ("", 204)

        params = dict(job.generation_parameters or {})
        job.status = "processing"
        job.claimed_worker_id = worker_id
        job.started_at = datetime.utcnow()
        job.progress_percent = 1
        job.progress_stage = "claimed by Kokoro GPU worker"
        db.session.commit()
        try:
            import gpu_lifecycle
            gpu_lifecycle.mark_job_activity()
        except Exception:
            pass

        return jsonify({
            "job_id": job.id,
            "material_id": job.material_id,
            "turns": params.get("turns") or [],
            "target_duration_seconds": params.get("target_duration_seconds") or 0,
            "storage_path": params.get("storage_path"),
            "audio_fingerprint": params.get("audio_fingerprint"),
        }), 200
    except Exception:
        db.session.rollback()
        app.logger.exception("Kokoro worker failed to claim a podcast job")
        return jsonify({"error": "Could not claim job"}), 500


@bp.post("/jobs/<int:job_id>/progress")
def update_progress(job_id):
    from app import AiJob, db

    data = request.get_json(silent=True) or {}
    job = db.session.get(AiJob, job_id)
    if not job or job.feature != "podcast_audio":
        return jsonify({"error": "Job not found"}), 404
    worker_id = str(data.get("worker_id") or "").strip()
    if not worker_id or not job.claimed_worker_id or worker_id != job.claimed_worker_id:
        return jsonify({"error": "Job claim identity is required and must match the claiming worker"}), 409
    if job.status != "processing":
        return jsonify({"error": "Job is not processing"}), 409

    try:
        percent = int(data.get("progress_percent", job.progress_percent or 0))
    except (TypeError, ValueError):
        percent = job.progress_percent or 0

    job.progress_percent = max(0, min(99, percent))
    job.progress_stage = str(data.get("progress_stage") or "working")[:80]
    db.session.commit()
    return jsonify({"ok": True}), 200


@bp.post("/jobs/<int:job_id>/complete")
def complete_job(job_id):
    from app import AiJob, GeneratedMaterial, db
    import json

    data = request.get_json(silent=True) or {}
    job = db.session.get(AiJob, job_id)
    if not job or job.feature != "podcast_audio":
        return jsonify({"error": "Job not found"}), 404

    worker_id = str(data.get("worker_id") or "").strip()
    if not worker_id or not job.claimed_worker_id or worker_id != job.claimed_worker_id:
        return jsonify({"error": "Job claim identity is required and must match the claiming worker"}), 409

    # Completion is intentionally idempotent. A retry from a worker after
    # a lost HTTP response must not create a second material or corrupt the
    # existing ready artifact.
    if job.status == "completed":
        return jsonify({"ok": True, "already_completed": True}), 200

    material_id = job.material_id
    material = db.session.get(GeneratedMaterial, material_id) if material_id else None
    if not material:
        job.status = "failed"
        job.completed_at = datetime.utcnow()
        job.error_message = "Podcast material no longer exists"
        db.session.commit()
        return jsonify({"error": "Podcast material not found"}), 404

    success = bool(data.get("success"))
    envelope = json.loads(material.payload or "{}")

    if success:
        storage_path = str(data.get("storage_path") or "").strip()
        duration_seconds = data.get("duration_seconds")
        requested_duration_seconds = data.get("requested_duration_seconds")
        duration_verified = bool(data.get("duration_verified"))

        if not storage_path or duration_seconds is None:
            return jsonify({"error": "Successful completion is missing audio metadata"}), 400

        envelope["audio_status"] = "ready"
        envelope["audio_storage_path"] = storage_path
        envelope["duration_seconds"] = round(float(duration_seconds), 3)
        envelope["requested_duration_seconds"] = (
            round(float(requested_duration_seconds), 3)
            if requested_duration_seconds is not None else None
        )
        envelope["duration_verified"] = duration_verified
        envelope["duration_correction_ratio"] = round(float(data.get("duration_correction_ratio") or 1.0), 6)
        envelope["audio_fingerprint"] = (job.generation_parameters or {}).get("audio_fingerprint")

        material.payload = json.dumps(envelope)
        job.status = "completed"
        job.progress_percent = 100
        job.progress_stage = "ready"
        job.completed_at = datetime.utcnow()
        job.error_message = None
        db.session.commit()

        try:
            from podcast_audio import _complete_generation_notification
            _complete_generation_notification(
                job.notification_id,
                material.id,
                success=True,
                duration_seconds=float(duration_seconds),
            )
        except Exception as exc:
            app.logger.warning("Kokoro success notification failed: %s", exc)

        return jsonify({"ok": True}), 200

    error_message = str(data.get("error_message") or "Kokoro GPU worker failed")[:500]
    envelope["audio_status"] = "failed"
    material.payload = json.dumps(envelope)
    job.status = "failed"
    job.progress_stage = "failed"
    job.completed_at = datetime.utcnow()
    job.error_message = error_message
    db.session.commit()

    try:
        from podcast_audio import _complete_generation_notification
        _complete_generation_notification(
            job.notification_id,
            material.id,
            success=False,
            error_message=error_message,
        )
    except Exception as exc:
        app.logger.warning("Kokoro failure notification failed: %s", exc)

    return jsonify({"ok": True}), 200


@bp.post("/worker/idle")
def worker_idle():
    """Worker asks the control plane to destroy itself after the queue is idle."""
    try:
        import gpu_lifecycle
        return jsonify(gpu_lifecycle.destroy_if_idle()), 200
    except Exception as exc:
        return jsonify({"error": str(exc)[:500]}), 500

@bp.get("/worker/status")
def worker_status():
    try:
        import gpu_lifecycle
        return jsonify(gpu_lifecycle.admin_snapshot()), 200
    except Exception as exc:
        return jsonify({"error": str(exc)[:500]}), 500


@bp.post("/worker/heartbeat")
def worker_heartbeat():
    data = request.get_json(silent=True) or {}
    worker_id = str(data.get("worker_id") or "").strip()
    if not worker_id:
        return jsonify({"error": "worker_id is required"}), 400
    try:
        import gpu_autoscaler
        return jsonify(gpu_autoscaler.heartbeat(
            worker_id,
            data.get("vram_used_gb"),
            data.get("vram_total_gb"),
            str(data.get("status") or "running")[:32],
        )), 200
    except Exception as exc:
        return jsonify({"error": str(exc)[:500]}), 500


@bp.post("/reconcile")
def reconcile():
    try:
        import gpu_autoscaler
        return jsonify(gpu_autoscaler.reconcile()), 200
    except Exception as exc:
        return jsonify({"error": str(exc)[:500]}), 500


@bp.post("/recover")
def recover():
    try:
        import gpu_autoscaler
        return jsonify(gpu_autoscaler.recover_stale_workers()), 200
    except Exception as exc:
        return jsonify({"error": str(exc)[:500]}), 500


@bp.get("/scaling")
def scaling():
    try:
        import gpu_autoscaler
        return jsonify(gpu_autoscaler.snapshot()), 200
    except Exception as exc:
        return jsonify({"error": str(exc)[:500]}), 500
