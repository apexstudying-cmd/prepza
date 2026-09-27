"""Compatibility facade for the Kokoro GPU autoscaler.

The implementation lives in gpu_autoscaler.py. Keeping this module preserves
the existing podcast integration points while moving lifecycle state and
scaling decisions to the hardened autoscaler.
"""
from gpu_autoscaler import (
    admin_snapshot,
    destroy_if_idle,
    ensure_worker_capacity,
    heartbeat,
    mark_job_activity,
    recover_stale_workers,
    scaling_snapshot,
    snapshot,
)

__all__ = [
    "admin_snapshot", "destroy_if_idle", "ensure_worker_capacity",
    "heartbeat", "mark_job_activity", "recover_stale_workers",
    "scaling_snapshot", "snapshot",
]
