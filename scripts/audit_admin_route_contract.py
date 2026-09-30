#!/usr/bin/env python3
"""Static check for frontend/backend admin route drift."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src" / "App.tsx"
BACKEND_FILES = [ROOT / "app.py"]
BACKEND_FILES += [ROOT / p for p in (
    "admin_operations.py",
    "infrastructure_monitoring.py",
    "auth_otp.py",
    "b2b_admin_routes.py",
    "opportunity_runtime.py",
    "prepza_control.py",
)]

frontend = FRONTEND.read_text(encoding="utf-8")
frontend_paths = set(
    p.replace("?", "")
    for p in re.findall(r"""[`'"]((?:/admin|/api/admin)[^\`'"]*)[`'"]""", frontend)
    if "${" not in p
)

backend_paths = set()
route_re = re.compile(r"""@app\.(?:route|get|post|put|patch|delete|options|head)\(\s*["']([^"']+)["']""")
for path in BACKEND_FILES:
    if path.exists():
        backend_paths.update(route_re.findall(path.read_text(encoding="utf-8")))

def normalize(path: str) -> str:
    path = re.sub(r"\?.*$", "", path)
    path = re.sub(r"/<[^>]+>", "/<var>", path)
    return path.rstrip("/") or "/"

normalized_backend = {normalize(p) for p in backend_paths}
missing = sorted({p for p in frontend_paths if normalize(p) not in normalized_backend})

if missing:
    print("ADMIN ROUTE DRIFT: missing backend routes")
    print("\n".join(missing))
    sys.exit(1)

print(f"ADMIN ROUTE CONTRACT OK: {len(frontend_paths)} frontend admin paths resolved")
