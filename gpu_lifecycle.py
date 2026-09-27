"""On-demand Vast.ai lifecycle for Prepza's standalone Kokoro A2000 worker."""
import json
import os
from datetime import datetime, timedelta
import requests

VAST_API_BASE_URL = os.environ.get("VAST_API_BASE_URL", "https://console.vast.ai/api/v0").rstrip("/")
VAST_API_KEY = os.environ.get("VAST_API_KEY", "").strip()
VAST_GPU_NAME = os.environ.get("VAST_GPU_NAME", "RTX_A2000").strip()
VAST_MAX_DPH_USD = float(os.environ.get("VAST_MAX_DPH_USD", "0.10"))
VAST_MIN_RELIABILITY = float(os.environ.get("VAST_MIN_RELIABILITY", "0.90"))
VAST_DISK_GB = int(os.environ.get("VAST_DISK_GB", "12"))
VAST_IDLE_SECONDS = max(60, int(os.environ.get("VAST_IDLE_SECONDS", "300")))
VAST_INSTANCE_LABEL = os.environ.get("VAST_INSTANCE_LABEL", "prepza-kokoro-a2000").strip()
VAST_WORKER_IMAGE = os.environ.get("VAST_WORKER_IMAGE", "ghcr.io/apexstudying-cmd/prepza-kokoro-worker:main").strip()

def _headers():
    if not VAST_API_KEY:
        raise RuntimeError("VAST_API_KEY is not configured")
    return {"Authorization": "Bearer " + VAST_API_KEY, "Content-Type": "application/json"}

def _request(method, path, **kwargs):
    response = requests.request(method, VAST_API_BASE_URL + path, headers=_headers(), timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()

def _state():
    from app import SystemSetting, db
    row = SystemSetting.query.filter_by(key="kokoro_gpu_state").first()
    if not row:
        row = SystemSetting(key="kokoro_gpu_state", value=json.dumps({
            "provider": "vast", "gpu": VAST_GPU_NAME, "status": "off",
            "instance_id": None, "offer_id": None, "price_usd_per_hour": None,
            "created_at": None, "last_job_at": None, "last_idle_at": None, "last_error": None,
        }))
        db.session.add(row)
        db.session.commit()
    try:
        state = json.loads(row.value or "{}")
    except (TypeError, ValueError):
        state = {}
    return row, state

def _save_state(row, state):
    from app import db
    row.value = json.dumps(state, separators=(",", ":"))
    db.session.commit()

def _instances():
    data = _request("GET", "/instances/")
    instances = data.get("instances", data)
    return instances if isinstance(instances, list) else []

def _instance_status(instance_id):
    data = _request("GET", "/instances/" + str(int(instance_id)) + "/")
    inner = data.get("instances")
    if isinstance(inner, list) and inner:
        return inner[0]
    if isinstance(inner, dict):
        return inner
    return data

def _find_offer():
    query = {
        "gpu_name": {"eq": VAST_GPU_NAME}, "num_gpus": {"eq": 1},
        "gpu_frac": {"eq": 1.0}, "rentable": {"eq": True}, "rented": {"eq": False},
        "dph_total": {"lte": VAST_MAX_DPH_USD},
        "reliability": {"gte": VAST_MIN_RELIABILITY}, "type": "on-demand",
        "order": [["dph_total", "asc"]], "limit": 20,
    }
    data = _request("GET", "/bundles/", params={"q": json.dumps(query)})
    offers = data.get("offers") or []
    exact = [
        o for o in offers
        if str(o.get("gpu_name", "")).strip().upper() == VAST_GPU_NAME.upper()
        and int(o.get("num_gpus", 1) or 1) == 1
        and float(o.get("dph_total", 999)) <= VAST_MAX_DPH_USD
    ]
    return sorted(exact, key=lambda o: float(o.get("dph_total", 999)))[0] if exact else None

def _worker_env():
    required = ["PREPZA_INTERNAL_BASE_URL", "KOKORO_WORKER_TOKEN", "R2_ENDPOINT_URL",
                "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise RuntimeError("Missing GPU worker environment: " + ", ".join(missing))
    return {key: os.environ[key] for key in required}

def _create_instance(offer):
    payload = {
        "client_id": "me", "image": VAST_WORKER_IMAGE, "disk": VAST_DISK_GB,
        "label": VAST_INSTANCE_LABEL, "runtype": "args", "args": [], "env": _worker_env(),
        "force": False,
    }
    result = _request("PUT", "/asks/" + str(int(offer["id"])) + "/", json=payload)
    if not result.get("success") or not result.get("new_contract"):
        raise RuntimeError("Vast.ai instance creation failed: " + str(result))
    return int(result["new_contract"])

def ensure_worker_capacity():
    if not VAST_API_KEY:
        return {"status": "disabled", "reason": "VAST_API_KEY is not configured"}
    from app import AiJob
    active = AiJob.query.filter_by(feature="podcast_audio").filter(
        AiJob.status.in_(("pending", "processing"))
    ).count()
    if active == 0:
        return {"status": "idle", "instance_id": None}

    row, state = _state()
    if state.get("instance_id"):
        try:
            info = _instance_status(state["instance_id"])
            actual = str(info.get("actual_status") or info.get("status") or "").lower()
            if actual in {"running", "loading", "created", "starting"}:
                state["status"] = "running" if actual == "running" else "starting"
                state["last_error"] = None
                _save_state(row, state)
                return {"status": state["status"], "instance_id": state["instance_id"]}
        except Exception as exc:
            state["last_error"] = str(exc)[:500]

    offer = _find_offer()
    if not offer:
        state["status"] = "error"
        state["last_error"] = (
            "No " + VAST_GPU_NAME + " offer found at <= $" +
            format(VAST_MAX_DPH_USD, ".3f") + "/hr and reliability >= " +
            format(VAST_MIN_RELIABILITY, ".2f")
        )
        _save_state(row, state)
        raise RuntimeError(state["last_error"])

    instance_id = _create_instance(offer)
    now = datetime.utcnow().isoformat() + "Z"
    state.update({
        "status": "starting", "instance_id": instance_id, "offer_id": int(offer["id"]),
        "price_usd_per_hour": float(offer.get("dph_total") or 0),
        "created_at": now, "last_job_at": now, "last_error": None,
    })
    _save_state(row, state)
    return {"status": "starting", "instance_id": instance_id}

def mark_job_activity():
    row, state = _state()
    state["last_job_at"] = datetime.utcnow().isoformat() + "Z"
    state["last_error"] = None
    _save_state(row, state)

def destroy_if_idle():
    if not VAST_API_KEY:
        return {"status": "disabled"}
    from app import AiJob
    active = AiJob.query.filter_by(feature="podcast_audio").filter(
        AiJob.status.in_(("pending", "processing"))
    ).count()
    if active:
        return {"status": "busy", "active_jobs": active}

    row, state = _state()
    instance_id = state.get("instance_id")
    if not instance_id:
        state["status"] = "off"
        _save_state(row, state)
        return {"status": "off"}

    last = state.get("last_job_at") or state.get("created_at")
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "")) if last else datetime.utcnow()
    except (TypeError, ValueError):
        last_dt = datetime.utcnow()
    idle_seconds = int((datetime.utcnow() - last_dt).total_seconds())
    if idle_seconds < VAST_IDLE_SECONDS:
        return {"status": "waiting_idle", "instance_id": instance_id, "idle_seconds": idle_seconds}

    try:
        _request("DELETE", "/instances/" + str(int(instance_id)) + "/")
        state.update({
            "status": "off", "instance_id": None, "offer_id": None,
            "price_usd_per_hour": None, "last_idle_at": datetime.utcnow().isoformat() + "Z",
        })
        _save_state(row, state)
        return {"status": "destroyed"}
    except Exception as exc:
        state["status"] = "error"
        state["last_error"] = str(exc)[:500]
        _save_state(row, state)
        raise

def admin_snapshot():
    row, state = _state()
    instance_id = state.get("instance_id")
    provider = {"configured": bool(VAST_API_KEY), "reachable": False, "instance": None}
    if VAST_API_KEY and instance_id:
        try:
            provider["instance"] = _instance_status(instance_id)
            provider["reachable"] = True
        except Exception as exc:
            state["last_error"] = str(exc)[:500]
            _save_state(row, state)
    return {
        "provider": "Vast.ai", "gpu": VAST_GPU_NAME, "status": state.get("status", "off"),
        "instance_id": state.get("instance_id"), "offer_id": state.get("offer_id"),
        "price_usd_per_hour": state.get("price_usd_per_hour"),
        "idle_timeout_seconds": VAST_IDLE_SECONDS, "last_job_at": state.get("last_job_at"),
        "last_idle_at": state.get("last_idle_at"), "last_error": state.get("last_error"),
        "configured": bool(VAST_API_KEY), "provider_reachable": provider["reachable"],
        "provider_instance": provider["instance"],
    }

def scaling_snapshot():
    """Read-only queue pressure and measured worker-throughput telemetry.

    This does not rent, resize, or destroy anything. It gives the admin
    surface enough measured information to choose the next worker count.
    """
    from app import AiJob

    pending_jobs = (
        AiJob.query
        .filter_by(feature="podcast_audio", status="pending")
        .order_by(AiJob.created_at.asc())
        .all()
    )
    processing = int(
        AiJob.query.filter_by(feature="podcast_audio", status="processing").count()
    )
    pending = len(pending_jobs)

    now = datetime.utcnow()
    oldest_pending_age = None
    if pending_jobs and pending_jobs[0].created_at:
        oldest_pending_age = max(0, int((now - pending_jobs[0].created_at).total_seconds()))

    completed = (
        AiJob.query
        .filter(
            AiJob.feature == "podcast_audio",
            AiJob.status == "completed",
            AiJob.started_at.isnot(None),
            AiJob.completed_at.isnot(None),
        )
        .order_by(AiJob.completed_at.desc())
        .limit(100)
        .all()
    )
    durations = sorted(
        max(0.0, (job.completed_at - job.started_at).total_seconds())
        for job in completed
    )
    median_duration = None
    if durations:
        middle = len(durations) // 2
        median_duration = (
            durations[middle]
            if len(durations) % 2
            else (durations[middle - 1] + durations[middle]) / 2
        )

    max_workers = max(1, int(os.environ.get("KOKORO_MAX_GPU_WORKERS", "1")))
    queue_depth = pending + processing
    desired_workers = min(max_workers, queue_depth) if queue_depth else 0

    return {
        "pending_jobs": pending,
        "processing_jobs": processing,
        "queue_depth": queue_depth,
        "oldest_pending_age_seconds": oldest_pending_age,
        "completed_samples": len(durations),
        "median_completed_job_seconds": round(median_duration, 2) if median_duration is not None else None,
        "current_worker_limit": max_workers,
        "desired_workers": desired_workers,
        "scaling_mode": os.environ.get("KOKORO_SCALING_MODE", "manual"),
        "policy": (
            "one active inference slot per GPU worker; scale worker count for queue pressure "
            "before increasing VRAM unless measured per-job VRAM exceeds the current GPU capacity"
        ),
    }
