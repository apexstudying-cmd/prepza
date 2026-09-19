"""
podcast_audio.py - Phase 2 of the Podcast feature: audio synthesis.

Takes an already-generated podcast SCRIPT (GeneratedMaterial.material_type
== 'podcast', payload.script.turns - see ai_service.generate_document_
podcast_script) and synthesizes one audio file: one TTS call per script
turn against a self-hosted Kokoro server, stitched together with short
pauses between speakers, uploaded to Supabase Storage, with the result
written back onto the SAME GeneratedMaterial row (audio_status/
audio_storage_path/duration_seconds) rather than a new row.

Mirrors document_pipeline.py's background-thread pattern exactly:
start_processing spawns a daemon thread, which pushes its own Flask
app context (a new thread has no access to the request's context) and
calls the synchronous process function, with a top-level try/except as
a last-resort safety net since a background thread has no caller to
raise to. Job bookkeeping (_create_job/_complete_job) also mirrors
document_pipeline.py's AiJob helpers, using feature="podcast_audio".

TTS backend: whichever Kokoro-compatible server KOKORO_TTS_BASE_URL
points at - a Hugging Face Space (free CPU Basic tier) running the
community kokoro-fastapi Docker image, exposing an OpenAI-compatible
/v1/audio/speech endpoint. KOKORO_SHARED_SECRET, if set, is sent as a
bearer token - the Space is on a public URL with no auth of its own,
so this is a lightweight abuse guard (stop random strangers from
burning the free quota), not real security.

Requires `pydub` and a bundled ffmpeg (e.g. `imageio-ffmpeg`) in
requirements.txt for audio stitching - see project notes.

PODCAST_VOICE_MAP below uses placeholder Kokoro voice IDs. Swap them
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

KOKORO_TTS_BASE_URL = os.environ.get("KOKORO_TTS_BASE_URL", "").rstrip("/")
KOKORO_SHARED_SECRET = os.environ.get("KOKORO_SHARED_SECRET")

# Placeholder - swap for real picks after listening to Kokoro's voice
# gallery (af_*/am_*/bf_*/bm_* naming: a=American, b=British, f=female,
# m=male). Nothing else in this file depends on which IDs go here.
PODCAST_VOICE_MAP = {
    "lec": "bm_george",
    "morio": "am_adam",
    "kichwa": "af_sarah",
}

TURN_GAP_MS = 400  # silence stitched between speaker turns
PODCAST_AUDIO_BUCKET = "podcast-audio"


def start_podcast_audio_processing(material_id, flask_app, notification_id=None):
    """
    Fire-and-forget: spawns a background thread that synthesizes audio
    for one GeneratedMaterial(material_type='podcast') row. `flask_app`
    is passed explicitly (not imported) - same reasoning as
    document_pipeline.start_processing, a new thread doesn't inherit
    the request's Flask context.
    """
    thread = threading.Thread(
        target=_process_in_background,
        args=(material_id, flask_app, notification_id),
        daemon=True,
    )
    thread.start()


def _process_in_background(material_id, flask_app, notification_id=None):
    with flask_app.app_context():
        try:
            process_podcast_audio(material_id, notification_id=notification_id)
        except Exception as e:  # noqa: BLE001 - last-resort safety net, thread has no caller to raise to
            print(f"ERROR: podcast audio synthesis crashed for material {material_id}: {e}")


def _fit_audio_to_duration(combined, target_seconds):
    """Correct duration with pitch-preserving FFmpeg; never regenerate AI/TTS."""
    if not target_seconds or target_seconds <= 0:
        return combined, None
    target_ms = int(round(target_seconds * 1000))
    source_ms = len(combined)
    if source_ms <= 0:
        raise RuntimeError("Synthesized podcast audio is empty")
    ratio = source_ms / target_ms
    if ratio < 0.70 or ratio > 1.40:
        raise RuntimeError(
            f"Podcast TTS duration {source_ms / 1000:.1f}s is too far from "
            f"requested {target_seconds:.1f}s for safe audio correction"
        )
    if abs(source_ms - target_ms) <= 100:
        return (combined[:target_ms] if source_ms > target_ms else combined + AudioSegment.silent(target_ms - source_ms)), ratio
    with tempfile.TemporaryDirectory(prefix="prepza-podcast-") as tmp:
        source_path = os.path.join(tmp, "source.wav")
        fitted_path = os.path.join(tmp, "fitted.wav")
        combined.export(source_path, format="wav")
        command = [
            AudioSegment.converter, "-y", "-hide_banner", "-loglevel", "error",
            "-i", source_path, "-filter:a", f"atempo={ratio:.8f}",
            "-ar", "44100", "-ac", "2", fitted_path,
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg duration correction failed: {result.stderr[-500:]}")
        fitted = AudioSegment.from_file(fitted_path, format="wav")
        if len(fitted) > target_ms:
            fitted = fitted[:target_ms]
        elif len(fitted) < target_ms:
            fitted += AudioSegment.silent(duration=target_ms - len(fitted))
        return fitted, ratio


def process_podcast_audio(material_id, notification_id=None):
    """
    Synchronous audio-synthesis pipeline for one GeneratedMaterial row.
    Safe to call directly (e.g. from an admin retry endpoint) without
    going through start_podcast_audio_processing's background thread.

    A single failed TTS turn fails the whole episode rather than
    producing a podcast with a missing line - partial audio isn't a
    usable product, better to retry the whole thing.
    """
    from app import db, GeneratedMaterial

    material = db.session.get(GeneratedMaterial, material_id)
    if not material or material.material_type != "podcast":
        print(f"ERROR: podcast audio requested for invalid material {material_id}")
        return

    envelope = json.loads(material.payload)
    if envelope.get("audio_status") == "ready":
        return  # already done - avoid redoing work if triggered twice

    job = _create_job(material.document_content_id, feature="podcast_audio", notification_id=notification_id)

    envelope["audio_status"] = "processing"
    material.payload = json.dumps(envelope)
    db.session.commit()

    try:
        if not KOKORO_TTS_BASE_URL:
            raise RuntimeError("KOKORO_TTS_BASE_URL is not configured")

        turns = envelope["script"]["turns"]
        parameters = material.generation_parameters or {}
        target_duration_seconds = float(parameters.get("duration_minutes", 0) or 0) * 60
        combined = AudioSegment.empty()
        gap = AudioSegment.silent(duration=TURN_GAP_MS)

        for i, turn in enumerate(turns):
            speaker = turn["speaker"]
            voice_id = PODCAST_VOICE_MAP.get(speaker)
            if not voice_id:
                raise RuntimeError(f"No voice configured for speaker '{speaker}'")

            clip_bytes = _synthesize_turn(turn["text"], voice_id)
            clip = AudioSegment.from_file(io.BytesIO(clip_bytes), format="wav")
            combined += clip
            if i < len(turns) - 1:
                combined += gap

        combined, correction_ratio = _fit_audio_to_duration(combined, target_duration_seconds)

        buffer = io.BytesIO()
        combined.export(buffer, format="mp3", bitrate="128k")
        audio_bytes = buffer.getvalue()
        duration_seconds = len(combined) / 1000.0
        if target_duration_seconds and abs(duration_seconds - target_duration_seconds) > 0.05:
            raise RuntimeError(
                f"Podcast duration verification failed: requested {target_duration_seconds:.1f}s, "
                f"got {duration_seconds:.1f}s"
            )

        storage_path = f"{material.document_content_id}-{material.id}.mp3"
        if not _upload_podcast_audio(storage_path, audio_bytes):
            raise RuntimeError("Failed to upload synthesized audio to storage")

        envelope["audio_status"] = "ready"
        envelope["audio_storage_path"] = storage_path
        envelope["duration_seconds"] = round(duration_seconds, 3)
        envelope["requested_duration_seconds"] = round(target_duration_seconds, 3) if target_duration_seconds else None
        envelope["duration_verified"] = bool(target_duration_seconds and abs(duration_seconds - target_duration_seconds) <= 0.05)
        envelope["duration_correction_ratio"] = round(correction_ratio, 6) if correction_ratio else 1.0
        material.payload = json.dumps(envelope)
        db.session.commit()

        _complete_job(job, success=True)
        _complete_generation_notification(notification_id, material.id, success=True, duration_seconds=duration_seconds)

    except Exception as e:
        envelope["audio_status"] = "failed"
        material.payload = json.dumps(envelope)
        db.session.commit()
        _complete_job(job, success=False, error_message=str(e))
        _complete_generation_notification(notification_id, material.id, success=False, error_message=str(e))
        raise


def _synthesize_turn(text, voice_id):
    """
    Calls our own prepza-tts server's /synthesize endpoint for one turn
    of dialogue. NOT OpenAI-compatible - this is a custom minimal
    ONNX-based Kokoro server (separate "prepza-tts" repo/Render
    service), not the abandoned kokoro-fastapi Docker image, so the
    endpoint path and request body are both different from what an
    OpenAI-compatible TTS API would expect. Returns raw WAV bytes.
    Raises on any non-200 response or network failure.
    """
    headers = {"Content-Type": "application/json"}
    if KOKORO_SHARED_SECRET:
        headers["Authorization"] = f"Bearer {KOKORO_SHARED_SECRET}"

    response = requests.post(
        f"{KOKORO_TTS_BASE_URL}/synthesize",
        headers=headers,
        json={
            "text": text,
            "voice": voice_id,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.content



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


def _create_job(document_content_id, feature, notification_id=None):
    from app import db, AiJob
    job = AiJob(
        document_content_id=document_content_id,
        feature=feature,
        status="processing",
        notification_id=notification_id,
        started_at=datetime.utcnow(),
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
