#!/usr/bin/env python3
"""Small, dependency-free HTTP load harness for Prepza.

Use against a staging deployment first:
  python scripts/load_test.py --url https://staging.example.com --path /health --concurrency 20 --requests 200

It intentionally does not invent authenticated credentials or mutate data. It
measures an explicit URL supplied by the operator. Production execution should
only happen after the deployment/configuration gate is approved.
"""
from __future__ import annotations

import argparse
import statistics
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def one_request(url: str, timeout: float) -> tuple[float, int, str | None]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            response.read(4096)
            return time.perf_counter() - started, response.status, None
    except urllib.error.HTTPError as exc:
        return time.perf_counter() - started, exc.code, str(exc)
    except Exception as exc:  # noqa: BLE001
        return time.perf_counter() - started, 0, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--path", default="/health")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()

    if args.requests <= 0 or args.concurrency <= 0:
        parser.error("requests and concurrency must be positive")

    url = args.url.rstrip("/") + (args.path if args.path.startswith("/") else "/" + args.path)
    started = time.perf_counter()
    samples: list[float] = []
    statuses: dict[int, int] = {}
    errors: list[str] = []
    lock = threading.Lock()

    def run():
        result = one_request(url, args.timeout)
        with lock:
            latency, status, error = result
            samples.append(latency)
            statuses[status] = statuses.get(status, 0) + 1
            if error and len(errors) < 10:
                errors.append(error)

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(run) for _ in range(args.requests)]
        for future in as_completed(futures):
            future.result()

    elapsed = max(time.perf_counter() - started, 1e-9)
    samples_ms = sorted(value * 1000 for value in samples)
    p95 = samples_ms[min(len(samples_ms) - 1, int(len(samples_ms) * 0.95))] if samples_ms else 0
    success = sum(count for status, count in statuses.items() if 200 <= status < 400)

    print(f"target={url}")
    print(f"requests={len(samples)} concurrency={args.concurrency}")
    print(f"elapsed_s={elapsed:.3f} throughput_rps={len(samples) / elapsed:.2f}")
    print(f"success={success} failure={len(samples) - success}")
    print(f"p50_ms={statistics.median(samples_ms) if samples_ms else 0:.1f} p95_ms={p95:.1f}")
    print(f"statuses={statuses}")
    if errors:
        print("sample_errors:")
        for error in errors:
            print(f"  {error}")
    return 0 if success == len(samples) else 2


if __name__ == "__main__":
    raise SystemExit(main())
