"""Harden PWA delivery and fail builds when install-critical assets are broken."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
DIST = ROOT / "frontend" / "dist"


def patch_app_headers() -> None:
    text = APP.read_text(encoding="utf-8")
    marker = '    if request.path.startswith("/assets/"):\n'
    if marker not in text:
        raise SystemExit("PWA hardening: expected static cache header anchor was not found in app.py")

    block = '''    # PWA control documents must never be served from an intermediary/browser
    # HTTP cache. A stale index/manifest/service-worker registration can make a
    # successful Render deployment look like an old release on a phone.
    if request.path in {"/", "/index.html", "/manifest.json", "/sw.js", "/sw-register.js"}:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

'''
    if 'PWA control documents must never be served' not in text:
        text = text.replace(marker, block + marker, 1)
        APP.write_text(text, encoding="utf-8")


def assert_png(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"PWA delivery: missing required icon {path}")
    data = path.read_bytes()
    if len(data) < 100 or data[:8] != b"\\x89PNG\\r\\n\\x1a\\n":
        raise SystemExit(
            f"PWA delivery: {path} is not a real PNG (it may be an unresolved Git LFS pointer)"
        )


def audit_dist() -> None:
    if not DIST.exists():
        raise SystemExit("PWA delivery: frontend/dist was not produced")

    required = [
        DIST / "index.html",
        DIST / "manifest.json",
        DIST / "sw.js",
        DIST / "sw-register.js",
        DIST / "offline.html",
        DIST / "icon-192.png",
        DIST / "icon-512.png",
    ]
    for path in required:
        if not path.exists():
            raise SystemExit(f"PWA delivery: missing build artifact {path.relative_to(ROOT)}")

    assert_png(DIST / "icon-192.png")
    assert_png(DIST / "icon-512.png")

    manifest = (DIST / "manifest.json").read_text(encoding="utf-8")
    for key in ('"name"', '"short_name"', '"start_url"', '"scope"', '"display"', '"icons"'):
        if key not in manifest:
            raise SystemExit(f"PWA delivery: manifest is missing {key}")

    sw = (DIST / "sw.js").read_text(encoding="utf-8")
    if "self.addEventListener('fetch'" not in sw and 'self.addEventListener("fetch"' not in sw:
        raise SystemExit("PWA delivery: service worker has no fetch handler")

    registration = (DIST / "sw-register.js").read_text(encoding="utf-8")
    if "navigator.serviceWorker.register('/sw.js')" not in registration:
        raise SystemExit("PWA delivery: service-worker registration anchor is missing")


if __name__ == "__main__":
    patch_app_headers()
    if DIST.exists():
        audit_dist()
    print("PWA delivery hardening: OK")
