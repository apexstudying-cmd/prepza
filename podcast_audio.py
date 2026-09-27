"""
podcast_audio.py - Phase 2 of the Podcast feature: audio synthesis.

Takes an already-generated podcast SCRIPT (GeneratedMaterial.material_type
== 'podcast', payload.script.turns - see ai_service.generate_document_
podcast_script) and synthesizes one audio file: one TTS call per script
turn against a self-hosted Kokoro server, stitched together with short
pauses between speakers, uploaded to the active private object store (R2 when configured), with the result
written back onto the SAME GeneratedMaterial row (audio_status/
audio_storage_path/duration_seconds) rather than a new row.

Mirrors document_pipeline.py's background-thread pattern exactly:
start_processing spawns a daemon thread, which pushes its own Flask
app context (a new thread has no access to the request's context) and
calls the synchronous process function, with a top-level try/except as
a last-resort safety net since a background thread has no caller to
raise to. Job bookkeeping (_create_job/_complete_job) also mirrors
document_pipeline.py's AiJob helpers, using feature="podcast_audio".

for real choices once you've actually listened to the voice gallery -
nothing else in this file needs to change when you do.
"""

import io
import os
import json
import threading
import subprocess
import tempfile
from datetime import datetime

import requests
from pydub import AudioSegment
import imageio_ffmpeg
AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()

# Default production voice mapping. The script generator emits only lec,
# morio, and kichwa; every turn is mapped before synthesis.
PODCAST_VOICE_MAP = {
    "lec": os.environ.get("PREPZA_PODCAST_VOICE_LEC", "bm_george").strip(),
    "morio": os.environ.get("PREPZA_PODCAST_VOICE_MORIO", "am_adam").strip(),
    "kichwa": os.environ.get("PREPZA_PODCAST_VOICE_KICHWA", "af_sarah").strip(),
}
if any(not voice for voice in PODCAST_VOICE_MAP.values()):
    raise RuntimeError("Every podcast speaker must have a configured TTS voice")

TURN_GAP_MS = 400  # silence stitched between speaker turns
PODCAST_AUDIO_BUCKET = "podcast-audio"


def build_audio_fingerprint(envelope, target_duration_seconds):
    canonical = {
        "version": "kokoro-a2000-v1",
        "target_duration_seconds": round(float(target_duration_seconds or 0), 3),
        "voices": PODCAST_VOICE_MAP,
        "turns": [
            {
                "speaker": str(turn.get("speaker") or ""),
                "text": str(turn.get("text") or ""),
            }
            for turn in (envelope.get("script", {}).get("turns") or [])
        ],
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def start_podcast_audio_processing(material_id, flask_app, notification_id=None):
    """
    Queue exactly one podcast-audio job for the standalone GPU worker.

    This deliberately does not start a Flask daemon thread and never calls
    a Render TTS service.
    """
    from app import db, GeneratedMaterial, AiJob

    material = (
        GeneratedMaterial.query
        .filter_by(id=material_id)
        .with_for_update()
        .first()
    )
    if not material or material.material_type != "podcast":
        raise RuntimeError(f"Podcast material {material_id} is not valid")

    envelope = json.loads(material.payload or "{}")
    if envelope.get("audio_status") == "ready":
        db.session.commit()
        return {"job_id": None, "status": "ready", "reused": True}

    turns = envelope.get("script", {}).get("turns") or []
    if not turns:
        raise RuntimeError("Podcast script has no speaker turns")

    parameters = material.generation_parameters or {}
    target_duration_seconds = float(parameters.get("duration_minutes", 0) or 0) * 60
    audio_fingerprint = build_audio_fingerprint(envelope, target_duration_seconds)

    # Exact ready-artifact fast path across podcast material variants.
    # This runs before any new GPU job is created.
    for candidate in (
        GeneratedMaterial.query
        .filter(
            GeneratedMaterial.document_content_id == material.document_content_id,
            GeneratedMaterial.material_type == "podcast",
            GeneratedMaterial.status == "ready",
            GeneratedMaterial.id != material.id,
        )
        .order_by(GeneratedMaterial.updated_at.desc())
        .limit(50)
    ):
        try:
            candidate_envelope = json.loads(candidate.payload or "{}")
        except (TypeError, ValueError):
            continue
        if (
            candidate_envelope.get("audio_status") == "ready"
            and candidate_envelope.get("audio_storage_path")
            and candidate_envelope.get("audio_fingerprint") == audio_fingerprint
        ):
            envelope["audio_status"] = "ready"
            envelope["audio_storage_path"] = candidate_envelope["audio_storage_path"]
            envelope["duration_seconds"] = candidate_envelope.get("duration_seconds")
            envelope["requested_duration_seconds"] = candidate_envelope.get("requested_duration_seconds")
            envelope["duration_verified"] = candidate_envelope.get("duration_verified", False)
            envelope["duration_correction_ratio"] = candidate_envelope.get("duration_correction_ratio", 1.0)
            envelope["audio_fingerprint"] = audio_fingerprint
            material.payload = json.dumps(envelope)
            db.session.commit()
            _complete_generation_notification(
                notification_id,
                material.id,
                success=True,
                duration_seconds=material.payload and envelope.get("duration_seconds"),
            )
            return {"job_id": None, "status": "ready", "reused": True}

    existing_job = (
        AiJob.query
        .filter(
            AiJob.document_content_id == material.document_content_id,
            AiJob.feature == "podcast_audio",
            AiJob.status.in_(("pending", "processing")),
            AiJob.generation_parameters["material_id"].as_integer() == material.id,
        )
        .order_by(AiJob.id.desc())
        .first()
    )
    if existing_job:
        db.session.commit()
        return {"job_id": existing_job.id, "status": existing_job.status, "reused": False}

    storage_path = f"{material.document_content_id}-{material.id}.mp3"
    generation_parameters = {
        "material_id": material.id,
        "turns": [
            {
                "text": str(turn.get("text") or ""),
                "voice": PODCAST_VOICE_MAP.get(str(turn.get("speaker") or "")),
            }
            for turn in turns
        ],
        "target_duration_seconds": target_duration_seconds,
        "storage_path": storage_path,
        "audio_fingerprint": audio_fingerprint,
        "audio_algorithm_version": "kokoro-a2000-v1",
    }
    if any(not item["voice"] for item in generation_parameters["turns"]):
        raise RuntimeError("Podcast script contains a speaker without a configured Kokoro voice")

    job = AiJob(
        document_content_id=material.document_content_id,
        user_id=material.owner_user_id,
        feature="podcast_audio",
        status="pending",
        notification_id=notification_id,
        progress_percent=0,
        progress_stage="queued for Kokoro GPU",
        material_id=material.id,
        generation_parameters=generation_parameters,
    )
    db.session.add(job)
    db.session.commit()
    return {"job_id": job.id, "status": "pending", "reused": False}



def _complete_generation_notification(notification_id, material_id, *, success, duration_seconds=None, error_message=None):
    if not notification_id:
        return
    try:
        from app import db, Notification, send_push_notification, Document, GeneratedMaterial
        notification = db.session.get(Notification, notification_id)
        if not notification:
            return
        if success:
            notification.type = "podcast_ready"
            notification.title = "Your podcast is ready"
            minutes = int(round((duration_seconds or 0) / 60))
            notification.body = (
                f"Your {minutes}-minute study podcast is ready to listen."
                if minutes else "Your study podcast is ready to listen."
            )
        else:
            notification.type = "podcast_failed"
            notification.title = "Podcast generation couldn't finish"
            notification.body = "Your podcast could not be completed. You can try again from the study hub."
        material = db.session.get(GeneratedMaterial, material_id)
        document = Document.query.filter_by(
            document_content_id=material.document_content_id if material else None,
            user_id=notification.user_id,
            is_removed=False,
        ).first()
        notification.related_type = "document"
        notification.related_id = document.id if document else None
        notification.is_read = False
        db.session.commit()
        send_push_notification(
            notification.user_id,
            notification.title,
            notification.body or "",
            data={"screen": "podcast-player", "document_id": notification.related_id},
        )
    except Exception as exc:
        print(f"WARNING: could not finalize podcast notification {notification_id}: {exc}")

def _upload_podcast_audio(storage_path, audio_bytes, bucket=PODCAST_AUDIO_BUCKET):
    """
    Uploads generated audio bytes directly to the private podcast-audio
    Supabase Storage bucket, using the service role key - same
    authenticated-REST pattern as app.py's existing Storage helpers
    (fetch_private_file_bytes / create_signed_upload_url), just POSTing
    bytes instead of GETting them or requesting a client upload URL,
    since this is server-generated content, not a client upload.
    """
    try:
        from object_storage import r2_enabled, r2_put_bytes
        if r2_enabled():
            return bool(r2_put_bytes(bucket, storage_path, audio_bytes, "audio/mpeg"))
    except Exception as e:
        print(f"ERROR uploading podcast audio to R2 {bucket}/{storage_path}: {e}")
        return False

    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not supabase_url or not service_key:
        print("WARNING: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set")
        return False

    upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{storage_path}"
    headers = {
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
        "Content-Type": "audio/mpeg",
        "x-upsert": "true",
    }

    try:
        response = requests.post(upload_url, headers=headers, data=audio_bytes)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"ERROR uploading podcast audio to {bucket}/{storage_path}: {e}")
        return False


def _update_job_progress(job, percent, stage):
    from app import db
    job.progress_percent = max(0, min(100, int(percent)))
    job.progress_stage = stage
    db.session.commit()


def _create_job(document_content_id, feature, notification_id=None):
    from app import db, AiJob
    job = AiJob(
        document_content_id=document_content_id,
        feature=feature,
        status="processing",
        notification_id=notification_id,
        started_at=datetime.utcnow(),
        progress_percent=0,
        progress_stage="queued",
    )
    db.session.add(job)
    db.session.commit()
    return job


def _complete_job(job, success, error_message=None):
    from app import db
    job.status = "completed" if success else "failed"
    job.completed_at = datetime.utcnow()
    if error_message:
        job.error_message = error_message[:500]
    db.session.commit()
