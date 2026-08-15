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
from datetime import datetime

import requests
from pydub import AudioSegment

KOKORO_TTS_BASE_URL = os.environ.get("KOKORO_TTS_BASE_URL", "").rstrip("/")
KOKORO_SHARED_SECRET = os.environ.get("KOKORO_SHARED_SECRET")

# Placeholder - swap for real picks after listening to Kokoro's voice
# gallery (af_*/am_*/bf_*/bm_* naming: a=American, b=British, f=female,
# m=male). Nothing else in this file depends on which IDs go here.
PODCAST_VOICE_MAP = {
    "lec": "am_eric",
    "morio": "am_michael",
    "kichwa": "af_bella",
}

TURN_GAP_MS = 400  # silence stitched between speaker turns
PODCAST_AUDIO_BUCKET = "podcast-audio"


def start_podcast_audio_processing(material_id, flask_app):
    """
    Fire-and-forget: spawns a background thread that synthesizes audio
    for one GeneratedMaterial(material_type='podcast') row. `flask_app`
    is passed explicitly (not imported) - same reasoning as
    document_pipeline.start_processing, a new thread doesn't inherit
    the request's Flask context.
    """
    thread = threading.Thread(
        target=_process_in_background,
        args=(material_id, flask_app),
        daemon=True,
    )
    thread.start()


def _process_in_background(material_id, flask_app):
    with flask_app.app_context():
        try:
            process_podcast_audio(material_id)
        except Exception as e:  # noqa: BLE001 - last-resort safety net, thread has no caller to raise to
            print(f"ERROR: podcast audio synthesis crashed for material {material_id}: {e}")


def process_podcast_audio(material_id):
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

    job = _create_job(material.document_content_id, feature="podcast_audio")

    envelope["audio_status"] = "processing"
    material.payload = json.dumps(envelope)
    db.session.commit()

    try:
        if not KOKORO_TTS_BASE_URL:
            raise RuntimeError("KOKORO_TTS_BASE_URL is not configured")

        turns = envelope["script"]["turns"]
        combined = AudioSegment.empty()
        gap = AudioSegment.silent(duration=TURN_GAP_MS)

        for i, turn in enumerate(turns):
            speaker = turn["speaker"]
            voice_id = PODCAST_VOICE_MAP.get(speaker)
            if not voice_id:
                raise RuntimeError(f"No voice configured for speaker '{speaker}'")

            clip_bytes = _synthesize_turn(turn["text"], voice_id)
            clip = AudioSegment.from_file(io.BytesIO(clip_bytes), format="mp3")
            combined += clip
            if i < len(turns) - 1:
                combined += gap

        buffer = io.BytesIO()
        combined.export(buffer, format="mp3")
        audio_bytes = buffer.getvalue()
        duration_seconds = len(combined) / 1000.0

        storage_path = f"{material.document_content_id}-{material.id}.mp3"
        if not _upload_podcast_audio(storage_path, audio_bytes):
            raise RuntimeError("Failed to upload synthesized audio to storage")

        envelope["audio_status"] = "ready"
        envelope["audio_storage_path"] = storage_path
        envelope["duration_seconds"] = round(duration_seconds, 1)
        material.payload = json.dumps(envelope)
        db.session.commit()

        _complete_job(job, success=True)

    except Exception as e:
        envelope["audio_status"] = "failed"
        material.payload = json.dumps(envelope)
        db.session.commit()
        _complete_job(job, success=False, error_message=str(e))
        raise


def _synthesize_turn(text, voice_id):
    """
    Calls the Kokoro server's OpenAI-compatible speech endpoint for one
    turn of dialogue. Returns raw MP3 bytes. Raises on any non-200
    response or network failure.
    """
    headers = {"Content-Type": "application/json"}
    if KOKORO_SHARED_SECRET:
        headers["Authorization"] = f"Bearer {KOKORO_SHARED_SECRET}"

    response = requests.post(
        f"{KOKORO_TTS_BASE_URL}/v1/audio/speech",
        headers=headers,
        json={
            "model": "kokoro",
            "input": text,
            "voice": voice_id,
            "response_format": "mp3",
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.content


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


def _create_job(document_content_id, feature):
    from app import db, AiJob
    job = AiJob(
        document_content_id=document_content_id,
        feature=feature,
        status="processing",
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
