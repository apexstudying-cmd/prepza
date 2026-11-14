from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"
APP = FRONTEND / "src" / "App.tsx"
BACKEND = ROOT / "app.py"
APP_FACTORY = ROOT / "app_factory.py"
ROUTE_REGISTRY = ROOT / "route_registry.py"
STUDY_ROUTES = ROOT / "gamification_routes.py"
MANIFEST = FRONTEND / "public" / "manifest.json"

errors = []

def require_file(path, label):
    if not path.exists():
        errors.append(f"{label} missing: {path}")

require_file(APP, "App.tsx")
require_file(BACKEND, "Flask app.py")
require_file(APP_FACTORY, "Flask app factory")
require_file(ROUTE_REGISTRY, "backend route registry")
require_file(STUDY_ROUTES, "Study activity route module")
require_file(FRONTEND / "src" / "StudyActivityScreen.tsx", "StudyActivityScreen")
require_file(FRONTEND / "src" / "share" / "StudyShareSheet.tsx", "StudyShareSheet")
require_file(FRONTEND / "public" / "manifest.json", "PWA manifest")
require_file(FRONTEND / "public" / "sw.js", "service worker")
require_file(FRONTEND / "public" / "icon-192.png", "192px app icon")
require_file(FRONTEND / "public" / "icon-512.png", "512px app icon")
require_file(DIST / "index.html", "Vite dist/index.html")

if APP.exists():
    app_text = APP.read_text(encoding="utf-8")
    for needle, label in [
        ("./StudyActivityScreen", "unified Study screen import"),
        ("case 'study-activity'", "unified Study screen route"),
        ("StudyShareSheet", "study share sheet"),
        ("unreadChats", "chat unread badge wiring"),
        ("exploreAttention", "Explore attention wiring"),
    ]:
        if needle not in app_text:
            errors.append(f"App.tsx missing {label}: {needle}")

if BACKEND.exists():
    backend_text = BACKEND.read_text(encoding="utf-8")
    for needle, label in [
        ("register_gamification_routes(", "study activity route registration"),
        ('@app.route("/ambassador/referral-qr")', "ambassador QR endpoint"),
        ("register_foundation_routes(app, db)", "foundation route registry call"),
    ]:
        if needle not in backend_text:
            errors.append(f"app.py missing {label}: {needle}")

if STUDY_ROUTES.exists():
    study_route_text = STUDY_ROUTES.read_text(encoding="utf-8")
    for needle, label in [
        ('@app.route("/streak")', "streak endpoint"),
        ('@app.route("/study-time")', "study-time endpoint"),
        ('@app.route("/profile/posts")', "profile posts endpoint"),
        ('def study_time_sync(', "Study Hub sync handler"),
    ]:
        if needle not in study_route_text:
            errors.append(f"gamification_routes.py missing {label}: {needle}")

if APP_FACTORY.exists():
    factory_text = APP_FACTORY.read_text(encoding="utf-8")
    for needle, label in [
        ('static_folder="frontend/dist"', "Flask static frontend directory"),
        ('static_url_path=""', "root-mounted static asset path"),
        ("def create_app()", "Flask application factory"),
    ]:
        if needle not in factory_text:
            errors.append(f"app_factory.py missing {label}: {needle}")

if ROUTE_REGISTRY.exists():
    registry_text = ROUTE_REGISTRY.read_text(encoding="utf-8")
    for needle, label in [
        ("def register_foundation_routes(", "foundation route registrar"),
        ("register_usage_billing(app, db)", "usage billing registration"),
        ("register_organisation_billing(app, db)", "organisation billing registration"),
        ("register_discovery(app, db)", "discovery billing registration"),
    ]:
        if needle not in registry_text:
            errors.append(f"route_registry.py missing {label}: {needle}")

if MANIFEST.exists():
    import json
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        icon_sources = {x.get("src") for x in manifest.get("icons", [])}
        for required in ("/icon-192.png", "/icon-512.png"):
            if required not in icon_sources:
                errors.append(f"manifest missing icon: {required}")
    except Exception as exc:
        errors.append(f"manifest.json is invalid JSON: {exc}")

if DIST.exists():
    index = (DIST / "index.html").read_text(encoding="utf-8", errors="replace")
    if not re.search(r'<script[^>]+src="[^"]+.js"', index):
        errors.append("dist/index.html does not reference a built JavaScript bundle")
    if not (DIST / "manifest.json").exists():
        errors.append("dist/manifest.json missing from Vite output")

if errors:
    print("LAUNCH WIRING CHECK FAILED")
    for error in errors:
        print(" - " + error)
    sys.exit(1)

print("LAUNCH WIRING CHECK PASSED")
print(" - Vite produced dist/index.html and a JavaScript bundle")
print(" - App.tsx routes/imports are present")
print(" - Flask app factory, production routes, and route-registry billing registrations are present")
print(" - PWA manifest, icons, and service worker source are present")
