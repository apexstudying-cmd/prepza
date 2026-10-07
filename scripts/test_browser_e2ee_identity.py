"""Browser E2EE identity lifecycle gate.

Proves the real frontend identity bootstrap keeps one device identity across
reload and browser restart, while a genuinely fresh device is rejected by the
server's explicit single-device replacement contract.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("PREPZA_BROWSER_BASE_URL", "http://localhost:5000")
COMPOSE_FILE = os.environ.get("PREPZA_COMPOSE_FILE", "docker-compose.vps.yml")
PASSWORD = "Browser!E2EE12345"


def run_container_python(code: str) -> str:
    result = subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "exec", "-T", "app", "python", "-"],
        cwd=ROOT,
        input=code,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()


def create_fixture() -> dict:
    code = f"""
import json
from uuid import uuid4
from werkzeug.security import generate_password_hash
from app import app, db, User, University, Program

with app.app_context():
    suffix = uuid4().hex
    university = University.query.filter_by(is_active=True).order_by(University.id.asc()).first()
    if university is None:
        raise RuntimeError("No active university exists for browser E2EE fixture")
    program = Program.query.filter_by(university_id=university.id, is_active=True).order_by(Program.id.asc()).first()
    if program is None:
        raise RuntimeError("No active program exists for browser E2EE fixture")

    user = User(
        email=f"browser.e2ee.{{suffix}}@test.invalid",
        password_hash=generate_password_hash({PASSWORD!r}),
        year=2,
        semester=1,
        display_name="Browser E2EE",
        email_verified=True,
        is_admin=False,
        is_suspended=False,
        profile_visibility="public",
        who_can_message="everyone",
        who_can_follow="everyone",
        read_receipts_enabled=True,
        university_id=university.id,
        program_id=program.id,
        session_version=0,
    )
    db.session.add(user)
    db.session.commit()
    print(json.dumps({{"email": user.email, "user_id": user.id, "password": {PASSWORD!r}}}))
"""
    return json.loads(run_container_python(code).splitlines()[-1])


def cleanup_fixture(fixture: dict) -> None:
    code = f"""
from app import app, db, User
with app.app_context():
    user = db.session.get(User, {fixture["user_id"]})
    if user is not None:
        db.session.execute(db.text("DELETE FROM user_key WHERE user_id = :user_id"), {{"user_id": user.id}})
        db.session.delete(user)
        db.session.commit()
"""
    run_container_python(code)


def login(page, fixture: dict) -> None:
    response = page.request.post(
        f"{BASE_URL}/login",
        data=json.dumps({"email": fixture["email"], "password": fixture["password"]}),
        headers={"Content-Type": "application/json"},
    )
    if not response.ok:
        raise RuntimeError(f"/login failed: {response.status} {response.text()}")
    page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)


def local_public_key(page) -> str:
    return page.evaluate(
        """async () => {
          const db = await new Promise((resolve, reject) => {
            const request = indexedDB.open('prepza-e2ee', 1);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          const record = await new Promise((resolve, reject) => {
            const request = db.transaction('identity-keys', 'readonly')
              .objectStore('identity-keys').get('self');
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          if (!record?.publicKey) throw new Error('E2EE identity was not persisted');
          const raw = await crypto.subtle.exportKey('raw', record.publicKey);
          const bytes = new Uint8Array(raw);
          let binary = '';
          for (const byte of bytes) binary += String.fromCharCode(byte);
          return btoa(binary).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');
        }"""
    )


def wait_for_identity_match(page, user_id: int, timeout_seconds: float = 8.0) -> tuple[str, str]:
    deadline = time.monotonic() + timeout_seconds
    last_local = ""
    last_server = ""
    while time.monotonic() < deadline:
        last_local = local_public_key(page)
        last_server = server_public_key(page, user_id)
        if last_local == last_server:
            return last_local, last_server
        time.sleep(0.25)
    raise AssertionError(
        "Browser E2EE identity mismatch after bootstrap convergence window: "
        f"local={last_local[:16]}... server={last_server[:16]}..."
    )


def server_public_key(page, user_id: int) -> str:
    response = page.request.get(f"{BASE_URL}/keys/{user_id}")
    if not response.ok:
        raise RuntimeError(f"/keys lookup failed: {response.status} {response.text()}")
    return response.json()["public_key"]


def main() -> int:
    if shutil.which("docker") is None:
        raise SystemExit("Docker CLI is required.")
    fixture = create_fixture()
    profile = tempfile.mkdtemp(prefix="prepza-e2ee-profile-")
    try:
        with sync_playwright() as playwright:
            args = ["--autoplay-policy=no-user-gesture-required"]
            context = playwright.chromium.launch_persistent_context(profile, headless=True, args=args)
            page = context.pages[0] if context.pages else context.new_page()

            login(page, fixture)
            first_local, first_server = wait_for_identity_match(page, fixture["user_id"])
            print("PASS: first browser identity generated, persisted, and registered")

            page.reload(wait_until="commit")
            page.wait_for_timeout(1200)
            assert local_public_key(page) == first_local
            assert server_public_key(page, fixture["user_id"]) == first_server
            print("PASS: reload preserves the same identity")

            context.close()
            context = playwright.chromium.launch_persistent_context(profile, headless=True, args=args)
            page = context.pages[0] if context.pages else context.new_page()
            login(page, fixture)
            assert local_public_key(page) == first_local
            assert server_public_key(page, fixture["user_id"]) == first_server
            print("PASS: browser restart preserves the same identity")

            fresh = playwright.chromium.launch(headless=True)
            fresh_context = fresh.new_context()
            fresh_page = fresh_context.new_page()
            login(fresh_page, fixture)
            second_local = local_public_key(fresh_page)
            assert second_local != first_local
            # The browser's real bootstrap already attempted this registration.
            # Verify the explicit server contract with a fresh authenticated
            # request using the real CSRF token from /me.
            me = fresh_page.request.get(f"{BASE_URL}/me").json()
            replacement = fresh_page.request.post(
                f"{BASE_URL}/keys/register",
                data=json.dumps({"public_key": second_local}),
                headers={"Content-Type": "application/json", "X-CSRF-Token": me["csrf_token"]},
            )
            assert replacement.status == 409
            assert replacement.json()["code"] == "IDENTITY_KEY_REPLACEMENT_REQUIRED"
            print("PASS: fresh device gets the intentional identity replacement conflict")

            fresh_context.close()
            fresh.close()
            context.close()
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        cleanup_fixture(fixture)
    print("PASS: browser E2EE identity lifecycle gate is green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
