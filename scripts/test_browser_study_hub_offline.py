"""Real-browser Study Hub offline lifecycle regression."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("PREPZA_BROWSER_BASE_URL", "http://localhost:5000")
COMPOSE_FILE = os.environ.get("PREPZA_COMPOSE_FILE", "docker-compose.vps.yml")
PASSWORD = "Browser!StudyHub12345"
DOCUMENT_TITLE = "Offline lifecycle fixture"


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
from app import app, db, User, University, Program, DocumentContent, Document

with app.app_context():
    suffix = uuid4().hex
    university = University.query.filter_by(is_active=True).order_by(University.id.asc()).first()
    program = None
    if university is not None:
        program = Program.query.filter_by(
            university_id=university.id, is_active=True
        ).order_by(Program.id.asc()).first()

    user = User(
        email=f"browser.studyhub.{{suffix}}@test.invalid",
        password_hash=generate_password_hash({PASSWORD!r}),
        year=2,
        semester=1,
        display_name="Browser Study Hub",
        email_verified=True,
        is_admin=False,
        is_suspended=False,
        profile_visibility="public",
        who_can_message="everyone",
        who_can_follow="everyone",
        read_receipts_enabled=True,
        university_id=university.id if university else None,
        program_id=program.id if program else None,
        session_version=0,
    )
    db.session.add(user)
    db.session.flush()

    content = DocumentContent(
        content_hash=(suffix * 4)[:64],
        storage_path=f"browser-studyhub/{{suffix}}.pdf",
        file_type="pdf",
        file_size_bytes=1024,
        page_count=3,
        status="ready",
        extracted_text="Offline browser lifecycle fixture.",
    )
    db.session.add(content)
    db.session.flush()

    document_id = 9100000 + int(suffix[:6], 16)
    while db.session.get(Document, document_id) is not None:
        suffix = uuid4().hex
        document_id = 9100000 + int(suffix[:6], 16)

    document = Document(
        id=document_id,
        user_id=user.id,
        document_content_id=content.id,
        title={DOCUMENT_TITLE!r},
        original_filename="offline-studyhub-fixture.pdf",
        status="ready",
        is_removed=False,
    )
    db.session.add(document)
    db.session.commit()

    print(json.dumps({{"email": user.email, "user_id": user.id, "document_id": document.id, "password": {PASSWORD!r}}}))
"""
    return json.loads(run_container_python(code).splitlines()[-1])


def cleanup_fixture(fixture: dict) -> None:
    code = f"""
from app import app, db, User, UserKey, Document, DocumentContent, DocumentReadingProgress, StudyTimeLog, StudyStreak

with app.app_context():
    user = db.session.get(User, {fixture["user_id"]})
    document = db.session.get(Document, {fixture["document_id"]})
    content_id = document.document_content_id if document else None

    if document is not None:
        DocumentReadingProgress.query.filter_by(document_id=document.id).delete(synchronize_session=False)
    StudyTimeLog.query.filter_by(user_id={fixture["user_id"]}).delete(synchronize_session=False)
    StudyStreak.query.filter_by(user_id={fixture["user_id"]}).delete(synchronize_session=False)
    UserKey.query.filter_by(user_id={fixture["user_id"]}).delete(synchronize_session=False)

    if document is not None:
        db.session.delete(document)
    if content_id:
        content = db.session.get(DocumentContent, content_id)
        if content is not None:
            db.session.delete(content)
    if user is not None:
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


def seed_offline_package(page, user_id: int, document_id: int) -> None:
    page.evaluate(
        """({userId, documentId, title}) => {
          localStorage.setItem('prepza-offline-user-id', String(userId));

          const open = (name, version, store) => new Promise((resolve, reject) => {
            const request = indexedDB.open(name, version);
            request.onupgradeneeded = () => {
              const db = request.result;
              if (!db.objectStoreNames.contains(store)) db.createObjectStore(store, { keyPath: 'key' });
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });

          return Promise.all([
            open('prepza-offline-v2', 3, 'savedStudyHub').then(db => new Promise((resolve, reject) => {
              const tx = db.transaction('savedStudyHub', 'readwrite');
              tx.objectStore('savedStudyHub').put({
                key: String(userId) + ':' + String(documentId),
                userId,
                documentId,
                title,
                fileType: 'pdf',
                pageCount: 3,
                contentHash: 'offline-' + String(documentId),
                savedAt: Date.now(),
                assetUrls: [],
              });
              tx.oncomplete = () => { db.close(); resolve(); };
              tx.onerror = () => reject(tx.error);
            })),
            open('prepza-offline-study-v1', 1, 'documents').then(db => new Promise((resolve, reject) => {
              const tx = db.transaction('documents', 'readwrite');
              tx.objectStore('documents').put({
                key: String(userId) + ':' + String(documentId),
                userId,
                documentId,
                blob: new Blob(['offline study fixture'], { type: 'application/pdf' }),
                contentHash: 'offline-' + String(documentId),
                savedAt: Date.now(),
              });
              tx.oncomplete = () => { db.close(); resolve(); };
              tx.onerror = () => reject(tx.error);
            })),
          ]);
        }""",
        {"userId": user_id, "documentId": document_id, "title": DOCUMENT_TITLE},
    )


def read_local_seconds(page, user_id: int) -> int:
    return int(
        page.evaluate(
            """userId => {
              const key = 'prepza-study-hub-activity-v1:' + String(userId);
              const raw = localStorage.getItem(key);
              if (!raw) return 0;
              const state = JSON.parse(raw);
              const parts = new Intl.DateTimeFormat('en-CA', {
                timeZone: 'Africa/Nairobi',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
              }).formatToParts(new Date());
              const values = Object.fromEntries(parts.map(p => [p.type, p.value]));
              const day = values.year + '-' + values.month + '-' + values.day;
              return Number(state && state.days && state.days[day] && state.days[day].seconds || 0);
            }""",
            user_id,
        )
    )


def read_server_seconds(page) -> int:
    response = page.request.get(f"{BASE_URL}/study-time?period=day")
    if not response.ok:
        raise RuntimeError(f"/study-time failed: {response.status} {response.text()}")
    body = response.json()
    return int(body.get("total_seconds") or 0)


def main() -> int:
    if shutil.which("docker") is None:
        raise SystemExit("Docker CLI is required.")

    fixture = create_fixture()
    context = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()

            # Let the real tracker run normally, but allow the test to advance
            # performance time past the two-minute inactivity window without
            # sleeping for two minutes.
            context.add_init_script(
                """
                (() => {
                  const originalNow = performance.now.bind(performance);
                  Object.defineProperty(performance, 'now', {
                    configurable: true,
                    value: () => originalNow() + (window.__prepzaPerfOffsetMs || 0),
                  });
                })();
                """
            )

            page = context.new_page()
            login(page, fixture)
            seed_offline_package(page, fixture["user_id"], fixture["document_id"])

            page.evaluate(
                """({documentId}) => {
                  sessionStorage.setItem('prepza-navigation-state', JSON.stringify({
                    stack: ['home', 'document-study'],
                    activeConversationId: null,
                    activeDocumentId: documentId,
                    activeGroupId: null,
                    activeProfileUserId: null,
                    activeOpportunityId: null,
                  }));
                }""",
                {"documentId": fixture["document_id"]},
            )

            page.reload(wait_until="domcontentloaded")
            page.get_by_text(DOCUMENT_TITLE, exact=True).wait_for(timeout=15000)
            try:
                page.get_by_role("button", name="Continue Reading", exact=True).wait_for(timeout=15000)
            except PlaywrightTimeoutError:
                print("DIAGNOSTIC: Study Hub title was visible but Continue Reading was not.")
                print("DIAGNOSTIC URL:", page.url)
                print("DIAGNOSTIC BODY:", page.locator("body").inner_text(timeout=5000)[:6000])
                raise
            print("PASS: real browser opened the local-first Study Hub document")

            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(1200)
            controlled = page.evaluate(
                "() => Boolean(navigator.serviceWorker && navigator.serviceWorker.controller)"
            )
            if not controlled:
                raise AssertionError("Study Hub browser session is not controlled by the service worker")
            print("PASS: application shell is controlled by the service worker")

            page.wait_for_timeout(7000)
            online_local = read_local_seconds(page, fixture["user_id"])
            if online_local < 4:
                raise AssertionError(f"Study Hub tracker recorded too little visible time: {online_local}s")
            print(f"PASS: visible Study Hub activity persisted locally ({online_local}s)")

            page.evaluate(
                """() => {
                  Object.defineProperty(document, 'visibilityState', {
                    configurable: true,
                    value: 'hidden',
                  });
                  document.dispatchEvent(new Event('visibilitychange'));
                }"""
            )
            hidden_baseline = read_local_seconds(page, fixture["user_id"])
            page.wait_for_timeout(7000)
            hidden_after = read_local_seconds(page, fixture["user_id"])
            if hidden_after > hidden_baseline + 1:
                raise AssertionError(
                    f"Study Hub credited hidden-tab time: before={hidden_baseline}s after={hidden_after}s"
                )
            print("PASS: visibility hidden stops Study Hub crediting")

            page.evaluate(
                """() => {
                  Object.defineProperty(document, 'visibilityState', {
                    configurable: true,
                    value: 'visible',
                  });
                  document.dispatchEvent(new Event('visibilitychange'));
                }"""
            )
            page.wait_for_timeout(6000)
            visible_after = read_local_seconds(page, fixture["user_id"])
            if visible_after <= hidden_after:
                raise AssertionError("Study Hub did not resume after visibility returned")
            print("PASS: Study Hub resumes after visibility returns")

            inactivity_baseline = read_local_seconds(page, fixture["user_id"])
            page.evaluate("() => { window.__prepzaPerfOffsetMs = 121000; }")
            page.wait_for_timeout(6000)
            inactivity_after = read_local_seconds(page, fixture["user_id"])
            if inactivity_after > inactivity_baseline + 1:
                raise AssertionError(
                    f"Study Hub credited time after the inactivity window: before={inactivity_baseline}s after={inactivity_after}s"
                )
            print("PASS: two-minute inactivity rule stops Study Hub crediting")

            page.dispatch_event("body", "pointerdown")
            page.wait_for_timeout(6000)
            resumed_after_idle = read_local_seconds(page, fixture["user_id"])
            if resumed_after_idle <= inactivity_after:
                raise AssertionError("Study Hub did not resume after fresh interaction")
            print("PASS: fresh interaction resumes Study Hub tracking")

            page.get_by_text("Continue Reading", exact=True).click()
            page.wait_for_timeout(1500)
            page.go_back(wait_until="domcontentloaded")
            page.get_by_text(DOCUMENT_TITLE, exact=True).wait_for(timeout=15000)
            print("PASS: browser back returned to the same Study Hub document context")

            before_offline = read_local_seconds(page, fixture["user_id"])
            context.set_offline(True)
            page.wait_for_timeout(5000)
            offline_local = read_local_seconds(page, fixture["user_id"])
            if offline_local <= before_offline:
                raise AssertionError("Study Hub did not continue accumulating while offline")
            print(f"PASS: local Study Hub clock continued offline ({offline_local}s)")

            page.reload(wait_until="domcontentloaded", timeout=15000)
            page.get_by_text(DOCUMENT_TITLE, exact=True).wait_for(timeout=15000)
            offline_reload_local = read_local_seconds(page, fixture["user_id"])
            if offline_reload_local < offline_local:
                raise AssertionError("Offline Study Hub total regressed after page reload")
            print("PASS: offline reload preserved Study Hub state and local package")

            context.set_offline(False)
            page.wait_for_timeout(5000)
            server_seconds = read_server_seconds(page)
            local_seconds = read_local_seconds(page, fixture["user_id"])
            if server_seconds < local_seconds - 2:
                raise AssertionError(
                    f"Reconnect did not reconcile Study Hub time: local={local_seconds}s server={server_seconds}s"
                )
            print(f"PASS: reconnect reconciled Study Hub time (local={local_seconds}s server={server_seconds}s)")

            print("PASS: browser Study Hub offline lifecycle gate is green")
            return 0

    except (PlaywrightTimeoutError, AssertionError, RuntimeError) as exc:
        print(f"FAIL: {exc}")
        return 1
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        cleanup_fixture(fixture)


if __name__ == "__main__":
    raise SystemExit(main())
