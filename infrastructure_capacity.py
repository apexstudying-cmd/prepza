"""Infrastructure capacity planning helpers for Prepza admin.

These are planning formulas, not automatic scaling decisions. Actual CPU/RAM
recommendations must be validated against Render telemetry and load tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Optional


@dataclass(frozen=True)
class CapacityInputs:
    daily_active_users: int
    peak_concurrency: int
    requests_per_active_user_per_day: float = 60.0
    peak_multiplier: float = 10.0
    cpu_seconds_per_request: float = 0.05
    memory_mb_per_concurrent_request: float = 0.5
    base_ram_gb: float = 0.35
    ram_headroom: float = 0.50


def estimate_capacity(i: CapacityInputs) -> dict:
    """Return transparent estimates; every assumption is exposed."""
    seconds_per_day = 86400.0
    avg_rps = (i.daily_active_users * i.requests_per_active_user_per_day) / seconds_per_day
    peak_rps = avg_rps * i.peak_multiplier
    cpu_cores_required = peak_rps * i.cpu_seconds_per_request
    cpu_cores_with_headroom = cpu_cores_required * 1.5

    concurrent_ram_gb = (
        i.base_ram_gb
        + (i.peak_concurrency * i.memory_mb_per_concurrent_request / 1024.0)
    )
    ram_gb_required = concurrent_ram_gb * (1.0 + i.ram_headroom)

    return {
        "avg_rps": round(avg_rps, 3),
        "peak_rps": round(peak_rps, 3),
        "cpu_cores_required": round(cpu_cores_required, 3),
        "cpu_cores_with_headroom": round(cpu_cores_with_headroom, 3),
        "ram_gb_required": round(ram_gb_required, 3),
        "assumptions": {
            "daily_active_users": i.daily_active_users,
            "peak_concurrency": i.peak_concurrency,
            "requests_per_active_user_per_day": i.requests_per_active_user_per_day,
            "peak_multiplier": i.peak_multiplier,
            "cpu_seconds_per_request": i.cpu_seconds_per_request,
            "memory_mb_per_concurrent_request": i.memory_mb_per_concurrent_request,
            "base_ram_gb": i.base_ram_gb,
            "ram_headroom": i.ram_headroom,
        },
    }


def render_fit(cpu_cores: float, ram_gb: float) -> str:
    """Map a measured requirement to the smallest known Render shape."""
    plans = [
        ("0.5c-512mb", 0.5, 0.5),
        ("1c-2g", 1.0, 2.0),
        ("2c-4g", 2.0, 4.0),
        ("4c-8g", 4.0, 8.0),
        ("4c-16g", 4.0, 16.0),
        ("8c-32g", 8.0, 32.0),
    ]
    for plan, cpu, ram in plans:
        if cpu >= cpu_cores and ram >= ram_gb:
            return plan
    return "custom/consult Render"


def thousand_dau_baseline() -> dict:
    """Conservative starting model for ~1,000 DAU, not 1,000 simultaneous users."""
    result = estimate_capacity(
        CapacityInputs(
            daily_active_users=1000,
            peak_concurrency=100,
            requests_per_active_user_per_day=60,
            peak_multiplier=10,
            cpu_seconds_per_request=0.05,
            memory_mb_per_concurrent_request=0.5,
            base_ram_gb=0.35,
            ram_headroom=0.50,
        )
    )
    result["recommended_start"] = "1c-2g"
    result["note"] = (
        "Validate with real Render CPU/RAM and p95 latency before scaling. "
        "1,000 DAU is not equivalent to 1,000 simultaneous requests."
    )
    return result
