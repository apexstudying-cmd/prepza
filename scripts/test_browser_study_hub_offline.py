"""Real-browser Study Hub offline lifecycle regression."""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

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


def make_pdf(label: str) -> bytes:
    """Create a tiny valid one-page PDF so the browser proves local rendering."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        None,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    safe_label = label.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 18 Tf 72 720 Td ({safe_label}) Tj ET".encode()
    objects[3] = b"<< /Length {length} >>\nstream\n{stream}\nendstream"
    header = b"%PDF-1.4\n"
    body = bytearray(header)
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        rendered = (
            objects[3].replace(b"{length}", str(len(stream)).encode()).replace(b"{stream}", stream)
            if index == 4 else obj
        )
        offsets.append(len(body))
        body.extend(f"{index} 0 obj\n".encode())
        body.extend(rendered)
        body.extend(b"\nendobj\n")
    xref_offset = len(body)
    body.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    body.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        body.extend(f"{offset:010d} 00000 n \n".encode())
    body.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(body)


def seed_offline_package(page, user_id: int, document_id: int) -> None:
    pdf_base64 = base64.b64encode(make_pdf(DOCUMENT_TITLE)).decode("ascii")
    page.evaluate(
        """({userId, documentId, title, pdfBase64}) => {
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
                blob: new Blob([Uint8Array.from(atob(pdfBase64), character => character.charCodeAt(0))], { type: 'application/pdf' }),
                contentHash: 'offline-' + String(documentId),
                savedAt: Date.now(),
              });
              tx.oncomplete = () => { db.close(); resolve(); };
              tx.onerror = () => reject(tx.error);
            })),
          ]);
        }""",
        {"userId": user_id, "documentId": document_id, "title": DOCUMENT_TITLE, "pdfBase64": pdf_base64},
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
            # performance time past the five-minute inactivity window without
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
                page.get_by_role("button", name="Continue →", exact=True).wait_for(timeout=15000)
            except PlaywrightTimeoutError:
                print("DIAGNOSTIC: Study Hub title was visible but Continue Reading was not.")
                print("DIAGNOSTIC URL:", page.url)
                print("DIAGNOSTIC BODY:", page.locator("body").inner_text(timeout=5000)[:6000])
                raise
            # Guard the local-first navigation from the moment My Study opens.
            # A valid local Blob must be enough to render the uploaded PDF online;
            # detail/progress/page endpoints are blocked and counted as regressions.
            source_document_requests = []
            def block_saved_document_requests(route):
                request = route.request
                path = urlparse(request.url).path
                source_path = re.fullmatch(
                    rf"/documents/{fixture['document_id']}(?:/reading(?:/page/\d+)?)?",
                    path,
                )
                if request.method == "GET" and source_path:
                    source_document_requests.append(request.url)
                    route.fulfill(
                        status=412,
                        content_type="application/json",
                        body='{"error":"Local Study Hub reader must not fetch the saved source document"}',
                    )
                    return
                route.continue_()

            page.route(
                re.compile(rf".*/documents/{fixture['document_id']}(?:/reading(?:/page/\d+)?)?$"),
                block_saved_document_requests,
            )
            page.get_by_role("button", name="Continue →", exact=True).click()
            page.get_by_role("button", name=re.compile(r"Continue Reading")).wait_for(timeout=15000)
            print("PASS: real browser opened the local-first Study Hub document")

            page.get_by_role("button", name=re.compile(r"Continue Reading")).click(timeout=15000)
            page.get_by_text("Offline study copy", exact=True).wait_for(timeout=15000)
            page.get_by_text("OFFLINE", exact=True).wait_for(timeout=15000)
            # PdfStudyCanvas changes the accessible name from 'PDF' to the real
            # page count only after it successfully parses and renders the Blob.
            page.locator('canvas[aria-label="Page 1 of 1"]').wait_for(timeout=15000)
            if page.get_by_role("alert").count():
                raise AssertionError(
                    "Local Study Hub Blob was selected but the PDF reader reported an error: "
                    + page.get_by_role("alert").first.inner_text()
                )
            if source_document_requests:
                raise AssertionError(
                    "Local My Study reader tried to fetch the saved source from Flask: "
                    + ", ".join(source_document_requests)
                )
            print("PASS: online My Study reader rendered the local PDF Blob with zero source-document GETs")

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
            page.evaluate("() => { window.__prepzaPerfOffsetMs = 301000; }")
            page.wait_for_timeout(6000)
            inactivity_after = read_local_seconds(page, fixture["user_id"])
            if inactivity_after > inactivity_baseline + 1:
                raise AssertionError(
                    f"Study Hub credited time after the inactivity window: before={inactivity_baseline}s after={inactivity_after}s"
                )
            print("PASS: five-minute inactivity rule stops Study Hub crediting")

            page.dispatch_event("body", "pointerdown")
            page.wait_for_timeout(6000)
            resumed_after_idle = read_local_seconds(page, fixture["user_id"])
            if resumed_after_idle <= inactivity_after:
                raise AssertionError("Study Hub did not resume after fresh interaction")
            print("PASS: fresh interaction resumes Study Hub tracking")

            # Podcast playback is a deliberate exception to foreground inactivity:
            # if an audio element is genuinely playing, Study Hub credits playback
            # even when the document is hidden. Pausing/ending audio must stop crediting.
            podcast_before = read_local_seconds(page, fixture["user_id"])
            page.evaluate(
                """() => {
                  const audio = document.createElement('audio');
                  audio.id = 'prepza-podcast-qa-audio';
                  Object.defineProperty(audio, 'paused', { configurable: true, value: false });
                  Object.defineProperty(audio, 'ended', { configurable: true, value: false });
                  document.body.appendChild(audio);
                  window.__prepzaQaPodcastAudio = audio;
                  audio.dispatchEvent(new Event('play'));
                  Object.defineProperty(document, 'visibilityState', {
                    configurable: true,
                    value: 'hidden',
                  });
                  document.dispatchEvent(new Event('visibilitychange'));
                }"""
            )
            page.wait_for_timeout(6000)
            podcast_hidden_playing = read_local_seconds(page, fixture["user_id"])
            if podcast_hidden_playing <= podcast_before:
                raise AssertionError("Study Hub did not credit podcast playback while hidden")
            print("PASS: podcast playback continues Study Hub crediting while hidden")

            podcast_pause_baseline = podcast_hidden_playing
            page.evaluate(
                """() => {
                  const audio = window.__prepzaQaPodcastAudio;
                  Object.defineProperty(audio, 'paused', { configurable: true, value: true });
                  audio.dispatchEvent(new Event('pause'));
                }"""
            )
            page.wait_for_timeout(6000)
            podcast_paused = read_local_seconds(page, fixture["user_id"])
            if podcast_paused > podcast_pause_baseline + 1:
                raise AssertionError("Study Hub credited time after podcast playback was paused")
            print("PASS: paused podcast stops Study Hub crediting")

            page.evaluate(
                """() => {
                  const audio = window.__prepzaQaPodcastAudio;
                  audio.remove();
                  window.__prepzaQaPodcastAudio = null;
                  Object.defineProperty(document, 'visibilityState', {
                    configurable: true,
                    value: 'visible',
                  });
                  document.dispatchEvent(new Event('visibilitychange'));
                }"""
            )
            print("PASS: podcast activity lifecycle returned to normal Study Hub tracking")

            # Browser Back returns to the Home surface. Re-enter the same
            # saved Study Hub document through the real UI before testing the
            # offline lifecycle; otherwise the tracker is intentionally inactive
            # because Home is not a Study Hub screen.
            page.wait_for_timeout(500)
            page.go_back(wait_until="domcontentloaded")
            page.get_by_text(DOCUMENT_TITLE, exact=True).wait_for(timeout=15000)
            page.get_by_role("button", name="Continue →", exact=True).click()
            page.wait_for_timeout(1000)
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

            reconnect_target = read_local_seconds(page, fixture["user_id"])
            context.set_offline(False)
            page.wait_for_timeout(5000)
            server_seconds = read_server_seconds(page)
            local_seconds = read_local_seconds(page, fixture["user_id"])
            if server_seconds < reconnect_target - 1:
                raise AssertionError(
                    f"Reconnect did not reconcile Study Hub time: target={reconnect_target}s local_now={local_seconds}s server={server_seconds}s"
                )
            print(f"PASS: reconnect reconciled Study Hub time (target={reconnect_target}s local_now={local_seconds}s server={server_seconds}s)")

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
