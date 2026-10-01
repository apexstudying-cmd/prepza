"""Static regression checks for abandoned AI-job recovery."""
from pathlib import Path

SOURCE = Path("app.py").read_text(encoding="utf-8")
ENV = Path(".env.example.vps").read_text(encoding="utf-8")

REQUIRED = [
    'AI_JOB_STALE_AFTER_SECONDS = max(300, int(os.environ.get("AI_JOB_STALE_AFTER_SECONDS", "3600")))',
    'def _recover_stale_ai_jobs():',
    'AiJob.status == "processing"',
    'AiJob.started_at < cutoff',
    'stale_job.status = "failed"',
    'stale_job.retry_count = int(stale_job.retry_count or 0) + 1',
    'worker stopped; retry required',
    'retry is safe.',
    '_recover_stale_ai_jobs()\n    user_id = session.get("user_id")',
]
for marker in REQUIRED:
    if marker not in SOURCE:
        raise SystemExit(f"AI job recovery regression: missing {marker!r}")

if "AI_JOB_STALE_AFTER_SECONDS=" not in ENV:
    raise SystemExit("AI job recovery regression: missing VPS environment setting")

print("AI job recovery invariants passed.")
