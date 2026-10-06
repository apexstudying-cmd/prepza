"""Real-browser-to-browser WebRTC calling gate for the local Docker stack.

This test is intentionally outside pytest because it needs two independent real
browser contexts, fake microphone devices, and the actual running frontend.
Run it from the repository root on the host machine while the Docker stack is
up and the app is reachable at http://127.0.0.1:5000.

Prerequisite:
    python -m pip install playwright
    python -m playwright install chromium

The test creates disposable database users/conversation through the running
app container, logs both browsers in through the real /login route, opens the
real conversation route so CallExperience is mounted, starts a voice call
through the real Prepza CallExperience, accepts it in the second browser, and
verifies that both browsers report Connected and receive a live remote audio
MediaStream track.
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
BASE_URL = os.environ.get("PREPZA_BROWSER_BASE_URL", "http://localhost:5000")
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
from app import app, db, User, Conversation, ConversationParticipant, University, Program

with app.app_context():
    suffix = uuid4().hex
    password = {PASSWORD!r}
    users = []
    try:
        # The real browser shell enforces first-run onboarding. Use an
        # existing active university/program pair so the disposable accounts
        # enter the normal authenticated app instead of being trapped at
        # "Finish setting up".
        university = University.query.filter_by(is_active=True).order_by(University.id.asc()).first()
        if university is None:
            raise RuntimeError("No active university exists for browser WebRTC fixture")
        program = Program.query.filter_by(
            university_id=university.id,
            is_active=True,
        ).order_by(Program.id.asc()).first()
        if program is None:
            raise RuntimeError(\n                "No active program exists for browser WebRTC fixture university_id="\n                + str(university.id)\n            )

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
                university_id=university.id,
                program_id=program.id,
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
    # Browser authentication creates dependent rows. Remove them before
    # deleting the disposable users.
    if user_ids:
        db.session.execute(
            db.text("DELETE FROM study_streak WHERE user_id = ANY(:user_ids)"),
            {{"user_ids": user_ids}},
        )
        db.session.execute(
            db.text("DELETE FROM user_key WHERE user_id = ANY(:user_ids)"),
            {{"user_ids": user_ids}},
        )
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

    # The Flask app marks its session cookie Secure. Chromium treats Secure
    # cookies as usable on the special localhost origin, so the default local
    # browser base URL intentionally uses http://localhost rather than the
    # numeric 127.0.0.1 address.
    #
    # Do not make a second explicit /me request here. The real frontend
    # bootstrap already calls /me after authentication; duplicating it in the
    # test adds an unrelated authenticated DB request (including the
    # last-active bookkeeping hook) before the browser UI is exercised.
    page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)


def remote_audio_track_is_live(page) -> bool:
    # The call UI can render more than one <audio> element. Check every
    # rendered element so a legitimate DOM shape cannot cause Playwright's
    # strict locator semantics to produce a false negative.
    return bool(page.locator("audio").evaluate_all(
        """audios => audios.some(audio => {
            const stream = audio.srcObject;
            if (!(stream instanceof MediaStream)) return false;
            return stream.getAudioTracks().some(track => track.readyState === 'live');
        })"""
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

                # /chats/<id> is a Flask JSON API endpoint, not the SPA route.
                # Enter through the real authenticated shell, open Chats, then
                # select the disposable conversation through the actual UI.
                caller.get_by_text("Chats", exact=True).wait_for(state="visible", timeout=10000)
                caller.get_by_text("Chats", exact=True).click()
                # Diagnose the chat-list boundary before waiting on rendered rows.
                # If the disposable conversation is absent here, the failure is
                # backend/session/list filtering rather than browser/WebRTC.
                try:
                    chats_response = caller.request.get(f"{BASE_URL}/chats")
                    print("DEBUG: /chats HTTP:", chats_response.status)
                    print("DEBUG: /chats payload:", chats_response.text()[:12000])
                except Exception as exc:
                    print("DEBUG: /chats request failed:", exc, file=sys.stderr)
                try:
                    print("DEBUG: caller URL after Chats click:", caller.url)
                    print("DEBUG: caller body after Chats click:", caller.locator("body").inner_text(timeout=3000)[:12000])
                except Exception as exc:
                    print("DEBUG: caller DOM diagnostic failed:", exc, file=sys.stderr)
                # The chat-list API is the authoritative identity check. The
                # current UI renders an unnamed direct conversation as "Conversation"
                # rather than the other participant's display name, so selecting
                # "Browser callee" would fail before WebRTC is exercised. First prove
                # the fixture conversation is present, then enter that rendered card.
                try:
                    payload = json.loads(chats_response.text())
                    chat_ids = {int(chat.get("id")) for chat in payload.get("chats", [])}
                except Exception:
                    chat_ids = set()
                expected_chat_id = int(fixture["conversation_id"])
                if expected_chat_id not in chat_ids:
                    raise AssertionError(
                        f"Fixture conversation {expected_chat_id} is missing from /chats: {sorted(chat_ids)}"
                    )
                conversation_card = caller.get_by_text("Conversation", exact=True)
                conversation_card.wait_for(timeout=10000)
                conversation_card.click()
                caller.get_by_role("button", name="Start voice call").wait_for(state="visible", timeout=10000)
                callee.wait_for_timeout(1200)
                print("PASS: caller opened the real conversation through the SPA UI while callee remained on Home")

                # The conversation UI currently exposes both a header call button and
                # a secondary call control with the same accessible name. Target the
                # explicit header title so Playwright does not enter strict-mode
                # ambiguity before WebRTC itself is exercised.
                start_voice_button = caller.get_by_title("Voice call", exact=True)
                try:
                    start_voice_button.wait_for(state="visible", timeout=15000)
                except PlaywrightTimeoutError as exc:
                    buttons = caller.locator("button").all_inner_texts()
                    body_text = caller.locator("body").inner_text(timeout=2000)
                    print("DEBUG: caller visible buttons:", buttons, file=sys.stderr)
                    print("DEBUG: caller visible text:", body_text[:6000], file=sys.stderr)
                    raise exc
                start_voice_button.click()
                print("PASS: caller started voice call through the real UI button")

                accept_button = callee.get_by_role("button", name="Accept call")
                try:
                    accept_button.wait_for(timeout=10000)
                except PlaywrightTimeoutError as exc:
                    buttons = callee.locator("button").all_inner_texts()
                    body_text = callee.locator("body").inner_text(timeout=2000)
                    print("DEBUG: callee visible buttons:", buttons, file=sys.stderr)
                    print("DEBUG: callee visible text:", body_text[:6000], file=sys.stderr)
                    raise exc
                accept_button.click()

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
