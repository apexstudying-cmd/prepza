import io
import os
import subprocess
import tempfile
import threading
import time
from typing import Any

import boto3
import requests
from fastapi import FastAPI
from pydub import AudioSegment
import uvicorn

PREPZA_INTERNAL_BASE_URL = os.environ["PREPZA_INTERNAL_BASE_URL"].rstrip("/")
PREPZA_INTERNAL_TOKEN = os.environ["PREPZA_INTERNAL_TOKEN"]
R2_ENDPOINT_URL = os.environ["R2_ENDPOINT_URL"]
R2_ACCESS_KEY_ID = os.environ["R2_ACCESS_KEY_ID"]
R2_SECRET_ACCESS_KEY = os.environ["R2_SECRET_ACCESS_KEY"]
R2_BUCKET = os.environ.get("R2_BUCKET", "podcast-audio")

POLL_SECONDS = max(1, float(os.environ.get("POLL_SECONDS", "2")))
KOKORO_LOCAL_URL = os.environ.get("KOKORO_LOCAL_URL", "http://127.0.0.1:8880").rstrip("/")
KOKORO_MODEL = os.environ.get("KOKORO_MODEL", "kokoro")
KOKORO_TIMEOUT_SECONDS = max(30, int(os.environ.get("KOKORO_TIMEOUT_SECONDS", "120")))
HEALTH_PORT = int(os.environ.get("WORKER_HEALTH_PORT", "8080"))

app = FastAPI(title="Prepza Kokoro GPU Worker")

s3 = boto3.client(
    "s3",
    endpoint_url=R2_ENDPOINT_URL,
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {PREPZA_INTERNAL_TOKEN}",
        "Content-Type": "application/json",
    }


def _claim_job() -> dict[str, Any] | None:
    response = requests.post(
        f"{PREPZA_INTERNAL_BASE_URL}/internal/kokoro/jobs/claim",
        headers=_headers(),
        timeout=20,
    )
    if response.status_code == 204:
        return None
    response.raise_for_status()
    return response.json()


def _report(job_id: int, **payload: Any) -> None:
    response = requests.post(
        f"{PREPZA_INTERNAL_BASE_URL}/internal/kokoro/jobs/{job_id}/progress",
        headers=_headers(),
        json=payload,
        timeout=20,
    )
    response.raise_for_status()


def _complete(job_id: int, **payload: Any) -> None:
    response = requests.post(
        f"{PREPZA_INTERNAL_BASE_URL}/internal/kokoro/jobs/{job_id}/complete",
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()


def _fail(job_id: int, error_message: str) -> None:
    try:
        _complete(job_id, success=False, error_message=error_message[:500])
    except Exception:
        # The worker must keep polling even if Prepza is temporarily unreachable.
        pass


def _synthesize_turn(text: str, voice_id: str) -> bytes:
    response = requests.post(
        f"{KOKORO_LOCAL_URL}/v1/audio/speech",
        json={
            "model": KOKORO_MODEL,
            "voice": voice_id,
            "input": text,
            "response_format": "wav",
        },
        timeout=KOKORO_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.content


def _fit_audio_to_duration(combined: AudioSegment, target_seconds: float) -> tuple[AudioSegment, float]:
    if not target_seconds or target_seconds <= 0:
        return combined, 1.0

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
        fitted = combined[:target_ms] if source_ms > target_ms else combined + AudioSegment.silent(target_ms - source_ms)
        return fitted, ratio

    with tempfile.TemporaryDirectory(prefix="prepza-kokoro-") as tmp:
        source_path = os.path.join(tmp, "source.wav")
        fitted_path = os.path.join(tmp, "fitted.wav")
        combined.export(source_path, format="wav")
        # FFmpeg atempo is intentionally used instead of regenerating speech.
        command = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
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
            fitted += AudioSegment.silent(target_ms - len(fitted))
        return fitted, ratio


def _upload(path: str, audio_bytes: bytes) -> None:
    s3.put_object(
        Bucket=R2_BUCKET,
        Key=path,
        Body=audio_bytes,
        ContentType="audio/mpeg",
        CacheControl="private, max-age=31536000",
    )


def _process(job: dict[str, Any]) -> None:
    job_id = int(job["job_id"])
    turns = job["turns"]
    target_duration_seconds = float(job.get("target_duration_seconds") or 0)
    storage_path = job["storage_path"]

    _report(job_id, progress_percent=5, progress_stage="preparing")

    combined = AudioSegment.empty()
    gap = AudioSegment.silent(duration=400)
    total_turns = max(1, len(turns))

    for index, turn in enumerate(turns):
        clip_bytes = _synthesize_turn(turn["text"], turn["voice"])
        clip = AudioSegment.from_file(io.BytesIO(clip_bytes), format="wav")
        combined += clip
        if index < len(turns) - 1:
            combined += gap
        percent = 10 + int(((index + 1) / total_turns) * 70)
        _report(
            job_id,
            progress_percent=percent,
            progress_stage=f"synthesizing speaker turns ({index + 1}/{total_turns})",
        )

    _report(job_id, progress_percent=82, progress_stage="fitting audio to requested duration")
    combined, correction_ratio = _fit_audio_to_duration(combined, target_duration_seconds)

    _report(job_id, progress_percent=90, progress_stage="exporting final audio")
    buffer = io.BytesIO()
    combined.export(buffer, format="mp3", bitrate="128k")
    audio_bytes = buffer.getvalue()
    duration_seconds = len(combined) / 1000.0

    if target_duration_seconds and abs(duration_seconds - target_duration_seconds) > 0.05:
        raise RuntimeError(
            f"Podcast duration verification failed: requested {target_duration_seconds:.1f}s, "
            f"got {duration_seconds:.1f}s"
        )

    _upload(storage_path, audio_bytes)
    _report(job_id, progress_percent=98, progress_stage="verifying final duration")
    _complete(
        job_id,
        success=True,
        storage_path=storage_path,
        duration_seconds=round(duration_seconds, 3),
        requested_duration_seconds=round(target_duration_seconds, 3) if target_duration_seconds else None,
        duration_verified=bool(
            target_duration_seconds and abs(duration_seconds - target_duration_seconds) <= 0.05
        ),
        duration_correction_ratio=round(correction_ratio, 6),
    )


def _poll_loop() -> None:
    while True:
        try:
            job = _claim_job()
            if job:
                try:
                    _process(job)
                except Exception as exc:
                    _fail(int(job["job_id"]), str(exc))
            else:
                time.sleep(POLL_SECONDS)
        except Exception:
            # Prepza can be restarting or briefly unavailable. Never crash the GPU
            # process because the control plane is temporarily offline.
            time.sleep(POLL_SECONDS)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "prepza-kokoro-worker"}


if __name__ == "__main__":
    threading.Thread(target=_poll_loop, name="prepza-kokoro-poller", daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=HEALTH_PORT)
