"""Real-browser-to-browser WebRTC calling gate for the local Docker stack.

This test is intentionally outside pytest because it needs two independent real
browser contexts, fake microphone devices, and the actual running frontend.
Run it from the repository root on the host machine while the Docker stack is
up and the app is reachable at http://127.0.0.1:5000.

Prerequisite:
    python -m pip install playwright
    python -m playwright install chromium

The test creates disposable database users/conversation through the running
app container, logs both browsers in through the real /login route, starts a
voice call through the real Prepza CallExperience, accepts it in the second
browser, and verifies that both browsers report Connected and receive a live
remote audio MediaStream track.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("PREPZA_BROWSER_BASE_URL", "http://127.0.0.1:5000")
COMPOSE_FILE = os.environ.get("PREPZA_COMPOSE_FILE", "docker-compose.vps.yml")
PASSWORD = "Browser!Call12345"


def run_container_python(code: str) -> str:
    command = [
        "docker", "compose", "-f", COMPOSE_FILE,
        "exec", "-T", "app", "python", "-",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        input=code,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Container fixture command failed:\n"
            + completed.stdout
            + completed.stderr
        )
    return completed.stdout.strip()


def create_fixture() -> dict:
    code = f"""
import json
from uuid import uuid4
from werkzeug.security import generate_password_hash
from app import app, db, User, Conversation, ConversationParticipant

with app.app_context():
    suffix = uuid4().hex
    password = {PASSWORD!r}
    users = []
    try:
        for role in ("caller", "callee"):
            user = User(
                email=f"browser.webrtc.{{role}}.{{suffix}}@test.invalid",
                password_hash=generate_password_hash(password),
                year=2,
                semester=1,
                display_name=f"Browser {{role}}",
                email_verified=True,
                is_admin=False,
                is_suspended=False,
                profile_visibility="public",
                who_can_message="everyone",
                who_can_follow="everyone",
                read_receipts_enabled=True,
                university_id=None,
                program_id=None,
                session_version=0,
            )
            db.session.add(user)
            users.append(user)

        db.session.flush()

        conversation = Conversation(
            is_group=False,
            name=None,
            created_by=users[0].id,
            status="accepted",
            e2ee_mode="legacy",
            key_epoch=0,
        )
        db.session.add(conversation)
        db.session.flush()
        db.session.add_all([
            ConversationParticipant(conversation_id=conversation.id, user_id=users[0].id, role="member"),
            ConversationParticipant(conversation_id=conversation.id, user_id=users[1].id, role="member"),
        ])
        db.session.commit()

        print(json.dumps({{
            "caller_email": users[0].email,
            "callee_email": users[1].email,
            "conversation_id": conversation.id,
            "password": password,
        }}))
    except Exception:
        db.session.rollback()
        raise
"""
    raw = run_container_python(code)
    return json.loads(raw.splitlines()[-1])


def cleanup_fixture(fixture: dict) -> None:
    code = f"""
from app import app, db, User, Conversation, ConversationParticipant

with app.app_context():
    emails = [{fixture["caller_email"]!r}, {fixture["callee_email"]!r}]
    users = User.query.filter(User.email.in_(emails)).all()
    user_ids = [u.id for u in users]
    conversations = Conversation.query.filter(Conversation.created_by.in_(user_ids)).all()
    for conversation in conversations:
        ConversationParticipant.query.filter_by(conversation_id=conversation.id).delete()
        db.session.delete(conversation)
    for user in users:
        db.session.delete(user)
    db.session.commit()
"""
    run_container_python(code)


def login(page, email: str, password: str) -> None:
    response = page.request.post(
        f"{BASE_URL}/login",
        data=json.dumps({"email": email, "password": password}),
        headers={"Content-Type": "application/json"},
    )
    if not response.ok:
        raise RuntimeError(f"/login failed with HTTP {response.status}: {response.text()}")
    page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)


def remote_audio_track_is_live(page) -> bool:
    return bool(page.locator("audio").evaluate(
        """audio => {
            const stream = audio.srcObject;
            if (!(stream instanceof MediaStream)) return false;
            return stream.getAudioTracks().some(track => track.readyState === 'live');
        }"""
    ))


def main() -> int:
    if shutil.which("docker") is None:
        raise SystemExit("Docker CLI is required.")
    fixture = create_fixture()
    print("PASS: disposable browser-call users and conversation created")

    try:
        with sync_playwright() as playwright:
            chromium_path = os.environ.get("PREPZA_CHROMIUM_PATH")
            launch_kwargs = {
                "headless": True,
                "args": [
                    "--use-fake-device-for-media-stream",
                    "--use-fake-ui-for-media-stream",
                    "--autoplay-policy=no-user-gesture-required",
                ],
            }
            if chromium_path:
                launch_kwargs["executable_path"] = chromium_path

            browser = playwright.chromium.launch(**launch_kwargs)
            try:
                caller_context = browser.new_context(
                    permissions=["microphone", "camera"],
                )
                callee_context = browser.new_context(
                    permissions=["microphone", "camera"],
                )
                caller = caller_context.new_page()
                callee = callee_context.new_page()

                login(caller, fixture["caller_email"], fixture["password"])
                login(callee, fixture["callee_email"], fixture["password"])
                print("PASS: two independent real browser contexts authenticated")

                # The callee's user ID is needed by the actual signaling
                # payload. Fetch it from the authenticated /me response.
                callee_id = callee.request.get(f"{BASE_URL}/me").json()["id"]

                # CallExperience is mounted by the chat shell and listens for
                # this same event used by the real Start voice call UI button.
                caller.evaluate(
                    """detail => window.dispatchEvent(
                        new CustomEvent('prepza-start-call', { detail })
                    )""",
                    {
                        "conversationId": fixture["conversation_id"],
                        "peerId": callee_id,
                        "peerName": "Browser callee",
                        "kind": "voice",
                    },
                )

                callee.get_by_role("button", name="Accept call").wait_for(timeout=10000)
                callee.get_by_role("button", name="Accept call").click()

                caller.get_by_text("Connected", exact=False).first.wait_for(timeout=20000)
                callee.get_by_text("Connected", exact=False).first.wait_for(timeout=20000)
                print("PASS: both real browsers reached WebRTC Connected state")

                deadline = time.time() + 10
                while time.time() < deadline:
                    if remote_audio_track_is_live(caller) and remote_audio_track_is_live(callee):
                        break
                    caller.wait_for_timeout(250)
                else:
                    raise AssertionError("Remote MediaStream audio track was not live in both browsers")

                print("PASS: caller and callee both received a live remote audio MediaStream track")
                print("PASS: real browser -> Socket.IO signaling -> RTCPeerConnection -> browser media path is green")
                caller_context.close()
                callee_context.close()
            finally:
                browser.close()
        return 0
    except (PlaywrightTimeoutError, AssertionError, RuntimeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        cleanup_fixture(fixture)


if __name__ == "__main__":
    raise SystemExit(main())
