"""Real-browser offline content/artifact persistence regression.

This complements scripts/test_browser_study_hub_offline.py. It proves that
already-ready materials survive the real online-to-offline cache path, can be
reopened through Study Materials after a network loss/reload, and do not trigger
fresh generation while offline.

It creates ready private artifacts in PostgreSQL directly, so the browser uses
the real generation-reuse endpoints without invoking an AI provider. The
document bytes are pre-saved locally; the generated-material cache itself is
populated by Prepza's UI/runtime code and then tested offline.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import shutil
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("PREPZA_BROWSER_BASE_URL", "http://localhost:5000")
COMPOSE_FILE = os.environ.get("PREPZA_COMPOSE_FILE", "docker-compose.vps.yml")
PASSWORD = "Browser!OfflineContent12345"
DOCUMENTS = [
    (1, "Offline Economics Notes"),
    (2, "Offline Statistics Notes"),
    (3, "Offline Research Methods Notes"),
]
MATERIAL_TYPES = ("summary", "flashcards", "quiz", "mind_map", "podcast")


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
from app import app, db, User, University, Program, DocumentContent, Document, GeneratedMaterial

with app.app_context():
    suffix = uuid4().hex
    university = University.query.filter_by(is_active=True).order_by(University.id.asc()).first()
    program = None
    if university is not None:
        program = Program.query.filter_by(
            university_id=university.id, is_active=True
        ).order_by(Program.id.asc()).first()

    user = User(
        email=f"browser.offline.content.{{suffix}}@test.invalid",
        password_hash=generate_password_hash({PASSWORD!r}),
        year=2,
        semester=1,
        display_name="Browser Offline Content",
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

    documents = []
    for offset, (_, title) in enumerate({DOCUMENTS!r}):
        content = DocumentContent(
            content_hash=(suffix + str(offset) + "content")[:64].ljust(64, "0"),
            storage_path=f"browser-offline-content/{{suffix}}/{{offset}}.pdf",
            file_type="pdf",
            file_size_bytes=2048,
            page_count=1,
            status="ready",
            extracted_text=f"Offline fixture content for {{title}}.",
        )
        db.session.add(content)
        db.session.flush()

        document_id = 9200000 + int(suffix[offset:offset + 5], 16) + offset
        while db.session.get(Document, document_id) is not None:
            document_id += 1000

        document = Document(
            id=document_id,
            user_id=user.id,
            document_content_id=content.id,
            title=title,
            original_filename=f"offline-{{offset}}.pdf",
            status="ready",
            is_removed=False,
        )
        db.session.add(document)
        material_specs = [
            ("summary", f"Offline summary for {{title}}"),
            ("flashcards", {{"cards": [{{"q": "Offline question", "a": "Offline answer"}}]}}),
            ("quiz", {{"questions": [{{"question": "Offline quiz question", "options": ["A", "B"], "answer_index": 0}}]}}),
            ("mind_map", {{"center": title, "branches": ["Offline branch"]}}),
            ("podcast", {{"title": title, "script": "Offline podcast script"}}),
        ]
        material_ids = {{}}
        for material_type, payload in material_specs:
            material = GeneratedMaterial(
                document_content_id=content.id,
                material_type=material_type,
                status="ready",
                payload=json.dumps(payload),
                generation_fingerprint=f"browser-offline-content:{{suffix}}:{{offset}}:{{material_type}}",
                generation_parameters={{}},
                generation_version="v2",
                scope="private",
                owner_user_id=user.id,
            )
            db.session.add(material)
            db.session.flush()
            material_ids[material_type] = material.id

        documents.append({{
            "document_id": document_id,
            "content_id": content.id,
            "title": title,
            "materials": material_ids,
        }})

    db.session.commit()
    print(json.dumps({{
        "email": user.email,
        "user_id": user.id,
        "password": {PASSWORD!r},
        "documents": documents,
    }}))
"""
    return json.loads(run_container_python(code).splitlines()[-1])


def cleanup_fixture(fixture: dict) -> None:
    document_ids = [item["document_id"] for item in fixture["documents"]]
    content_ids = [item["content_id"] for item in fixture["documents"]]
    code = f"""
from app import app, db, User, UserKey, Document, DocumentContent, DocumentReadingProgress, StudyTimeLog, StudyStreak, GeneratedMaterial

with app.app_context():
    GeneratedMaterial.query.filter(
        GeneratedMaterial.document_content_id.in_({content_ids!r})
    ).delete(synchronize_session=False)

    for document_id in {document_ids!r}:
        DocumentReadingProgress.query.filter_by(document_id=document_id).delete(synchronize_session=False)
        document = db.session.get(Document, document_id)
        if document is not None:
            db.session.delete(document)

    StudyTimeLog.query.filter_by(user_id={fixture["user_id"]}).delete(synchronize_session=False)
    StudyStreak.query.filter_by(user_id={fixture["user_id"]}).delete(synchronize_session=False)
    UserKey.query.filter_by(user_id={fixture["user_id"]}).delete(synchronize_session=False)

    for content_id in {content_ids!r}:
        content = db.session.get(DocumentContent, content_id)
        if content is not None:
            db.session.delete(content)

    user = db.session.get(User, {fixture["user_id"]})
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

    # A fresh Playwright context has no active service worker. In this app,
    # sw.js immediately activates/claims clients and sw-register.js reloads on
    # the first controllerchange. Wait for that startup reload to finish before
    # running async IndexedDB seeding; otherwise it can destroy the evaluate
    # context halfway through the fixture.
    navigation_events = []
    startup_diagnostics = {
        "service_worker_console": [],
        "script_responses": [],
        "script_request_failures": [],
        "page_errors": [],
        "devtools_worker_errors": [],
        "devtools_registration_updates": [],
        "devtools_version_updates": [],
        "playwright_service_workers": [],
        "worker_shell_requests": [],
    }

    # Page console events do not consistently expose exceptions raised inside
    # the service-worker execution context. Subscribe to Chromium's own
    # ServiceWorker protocol before navigating so failed installs and lifecycle
    # transitions are preserved even when no worker becomes active.
    try:
        devtools = page.context.new_cdp_session(page)

        def record_worker_error(event):
            startup_diagnostics["devtools_worker_errors"].append({
                key: event.get(key)
                for key in (
                    "errorMessage", "registrationId", "versionId",
                    "sourceURL", "lineNumber", "columnNumber",
                )
            })

        def record_registration_update(event):
            registrations = event.get("registrations", [])
            startup_diagnostics["devtools_registration_updates"].append([
                {
                    key: registration.get(key)
                    for key in ("registrationId", "scopeURL", "isDeleted")
                }
                for registration in registrations
            ])

        def record_worker_version_update(event):
            versions = event.get("versions", [])
            startup_diagnostics["devtools_version_updates"].append([
                {
                    key: version.get(key)
                    for key in (
                        "versionId", "registrationId", "scriptURL",
                        "runningStatus", "status", "controlledClients",
                        "targetId",
                    )
                }
                for version in versions
            ])

        devtools.on("ServiceWorker.workerErrorReported", record_worker_error)
        devtools.on("ServiceWorker.workerRegistrationUpdated", record_registration_update)
        devtools.on("ServiceWorker.workerVersionUpdated", record_worker_version_update)
        devtools.send("ServiceWorker.enable")
    except Exception as exc:
        startup_diagnostics["devtools_setup_error"] = (
            f"{type(exc).__name__}: {exc}"
        )

    def record_main_frame_navigation(frame):
        if frame == page.main_frame:
            navigation_events.append(frame.url)

    def record_startup_console(message):
        message_text = message.text
        if any(marker in message_text.lower() for marker in ("service worker", "sw.js", "sw-register.js")):
            startup_diagnostics["service_worker_console"].append(
                {"type": message.type, "text": message_text[:500]}
            )

    def record_startup_response(response):
        path = urlparse(response.url).path
        if path in {"/sw.js", "/sw-register.js"}:
            startup_diagnostics["script_responses"].append({
                "path": path,
                "status": response.status,
                "content_type": response.headers.get("content-type"),
            })

    def record_startup_request_failure(request):
        path = urlparse(request.url).path
        if path in {"/sw.js", "/sw-register.js"}:
            startup_diagnostics["script_request_failures"].append({
                "path": path,
                "failure": request.failure,
            })

    def record_service_worker(worker):
        worker_record = {
            "url": worker.url,
            "console": [],
            "close_events": 0,
        }
        startup_diagnostics["playwright_service_workers"].append(worker_record)

        def record_worker_console(message):
            worker_record["console"].append({
                "type": message.type,
                "text": message.text[:1000],
            })

        try:
            worker.on("console", record_worker_console)
        except Exception as exc:
            worker_record["console_listener_error"] = f"{type(exc).__name__}: {exc}"

        try:
            worker.on(
                "close",
                lambda *_args: worker_record.__setitem__(
                    "close_events", worker_record["close_events"] + 1
                ),
            )
        except Exception as exc:
            worker_record["close_listener_error"] = f"{type(exc).__name__}: {exc}"

    page.context.on("serviceworker", record_service_worker)

    def is_shell_asset_request(request):
        return urlparse(request.url).path in {
            "/offline.html", "/manifest.json", "/icon-192.png", "/icon-512.png"
        }

    def record_context_request(request):
        if not is_shell_asset_request(request):
            return
        worker = getattr(request, "service_worker", None)
        if worker is None:
            return
        startup_diagnostics["worker_shell_requests"].append({
            "event": "request",
            "path": urlparse(request.url).path,
            "worker_url": worker.url,
            "method": request.method,
        })

    def record_context_response(response):
        request = response.request
        if not is_shell_asset_request(request):
            return
        worker = getattr(request, "service_worker", None)
        if worker is None:
            return
        startup_diagnostics["worker_shell_requests"].append({
            "event": "response",
            "path": urlparse(response.url).path,
            "worker_url": worker.url,
            "status": response.status,
            "content_type": response.headers.get("content-type"),
        })

    def record_context_request_finished(request):
        if not is_shell_asset_request(request):
            return
        worker = getattr(request, "service_worker", None)
        if worker is None:
            return
        startup_diagnostics["worker_shell_requests"].append({
            "event": "finished",
            "path": urlparse(request.url).path,
            "worker_url": worker.url,
        })

    def record_context_request_failed(request):
        if not is_shell_asset_request(request):
            return
        worker = getattr(request, "service_worker", None)
        if worker is None:
            return
        startup_diagnostics["worker_shell_requests"].append({
            "event": "failed",
            "path": urlparse(request.url).path,
            "worker_url": worker.url,
            "failure": request.failure,
        })

    page.context.on("request", record_context_request)
    page.context.on("response", record_context_response)
    page.context.on("requestfinished", record_context_request_finished)
    page.context.on("requestfailed", record_context_request_failed)

    page.on("console", record_startup_console)
    page.on("pageerror", lambda error: startup_diagnostics["page_errors"].append(str(error)[:1000]))
    page.on("response", record_startup_response)
    page.on("requestfailed", record_startup_request_failure)
    page.on("framenavigated", record_main_frame_navigation)
    expected_url = BASE_URL.rstrip("/") + "/"
    try:
        page.goto(BASE_URL + "/", wait_until="load", timeout=15000)
    except Exception as exc:
        # The first controllerchange can reload this page and abort goto. Do
        # not treat a navigation count as proof of readiness; continue polling
        # the actual controller state and fail with lifecycle evidence if it
        # never settles.
        if page.is_closed() or page.url.rstrip("/") + "/" != expected_url:
            raise
        startup_diagnostics["initial_navigation_interruption"] = (
            f"{type(exc).__name__}: {exc}"
        )

    def read_control_state():
        return page.evaluate(
            """() => ({
              supported: 'serviceWorker' in navigator,
              controlled: Boolean(navigator.serviceWorker && navigator.serviceWorker.controller),
              readyState: document.readyState,
              url: location.href,
            })"""
        )

    # A second navigation is not a service-worker lifecycle signal: it can
    # happen before installation/activation finishes. Wait for the property
    # the test actually needs, and ensure controllerchange-triggered reloads
    # have settled before IndexedDB evaluate calls begin.
    deadline = time.monotonic() + 15
    last_control_state = None
    last_state_error = None
    controlled_and_settled = False
    while time.monotonic() < deadline:
        try:
            state = read_control_state()
            last_control_state = state
            last_state_error = None
            if (
                state.get("supported")
                and state.get("controlled")
                and state.get("readyState") == "complete"
                and state.get("url") == expected_url
            ):
                navigation_count = len(navigation_events)
                # This short stability check is not a readiness substitute;
                # control and a complete document are already required above.
                # It gives the app's controllerchange reload a chance to begin.
                page.wait_for_timeout(250)
                settled = read_control_state()
                last_control_state = settled
                if (
                    settled.get("supported")
                    and settled.get("controlled")
                    and settled.get("readyState") == "complete"
                    and settled.get("url") == expected_url
                    and len(navigation_events) == navigation_count
                ):
                    controlled_and_settled = True
                    break
        except Exception as exc:
            # A controllerchange reload may destroy the current execution
            # context between polls. Re-check the new document instead.
            last_state_error = f"{type(exc).__name__}: {exc}"
        page.wait_for_timeout(100)

    if not controlled_and_settled:
        # On failure, probe shell assets first and sample control/registration
        # state afterwards so the report is not a stale pre-probe snapshot.
        worker_state = page.evaluate(
            """async () => {
              const summarizeWorker = worker => worker ? ({
                scriptURL: worker.scriptURL,
                state: worker.state,
              }) : null;
              const probe = async path => {
                const started = performance.now();
                const abort = new AbortController();
                const timeoutId = setTimeout(() => abort.abort(), 3000);
                try {
                  const response = await fetch(path, {
                    cache: 'no-store',
                    signal: abort.signal,
                  });
                  const body = await response.arrayBuffer();
                  return {
                    path,
                    status: response.status,
                    ok: response.ok,
                    contentType: response.headers.get('content-type'),
                    bytes: body.byteLength,
                    elapsedMs: Math.round(performance.now() - started),
                  };
                } catch (error) {
                  return {
                    path,
                    error: String(error),
                    elapsedMs: Math.round(performance.now() - started),
                  };
                } finally {
                  clearTimeout(timeoutId);
                }
              };
              const assetProbes = await Promise.all([
                '/sw-register.js',
                '/sw.js',
                '/offline.html',
                '/manifest.json',
                '/icon-192.png',
                '/icon-512.png',
              ].map(probe));
              const registrations = await navigator.serviceWorker.getRegistrations();
              return {
                supported: 'serviceWorker' in navigator,
                controlled: Boolean(navigator.serviceWorker && navigator.serviceWorker.controller),
                controllerScriptURL: navigator.serviceWorker.controller?.scriptURL ?? null,
                readyState: document.readyState,
                registrationScriptPresent: Boolean(document.querySelector('script[src="/sw-register.js"]')),
                registrations: registrations.map(registration => ({
                  scope: registration.scope,
                  installing: summarizeWorker(registration.installing),
                  waiting: summarizeWorker(registration.waiting),
                  active: summarizeWorker(registration.active),
                })),
                assetProbes,
              };
            }"""
        )
        raise RuntimeError(
            "Service-worker startup did not reach a stable controlled page within 15 seconds; "
            f"main-frame navigations={navigation_events}; "
            f"last_control_state={last_control_state}; "
            f"last_state_error={last_state_error}; "
            f"final_worker_state={json.dumps(worker_state, sort_keys=True)}; "
            f"startup_diagnostics={json.dumps(startup_diagnostics, sort_keys=True)}"
        )

    # Wait for the real signed-in Home UI, not a guessed startup delay.
    page.get_by_role("button", name=re.compile(r"My Study$")).wait_for(timeout=15000)


def ensure_study_materials_documents_tab(page) -> None:
    """Wait for a real Home-or-My-Study surface, then use UI navigation if needed."""
    page.wait_for_function(
        """() => {
          const visible = element => {
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 &&
              style.display !== 'none' && style.visibility !== 'hidden' &&
              style.opacity !== '0';
          };
          const buttons = Array.from(document.querySelectorAll('button')).filter(visible);
          return buttons.some(button => (button.innerText || '').trim() === 'Documents') ||
            buttons.some(button => /My Study$/.test((button.innerText || '').trim()));
        }""",
        timeout=15000,
    )
    documents_tab = page.get_by_role("button", name="Documents", exact=True)
    if not documents_tab.is_visible():
        page.get_by_role("button", name=re.compile(r"My Study$")).click(timeout=15000)
    documents_tab.wait_for(timeout=15000)


def make_pdf(label: str) -> bytes:
    """Create a tiny valid one-page PDF without adding a test dependency."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        None,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    text = label.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode()
    objects[3] = f"<< /Length {{length}} >>\nstream\n{{stream}}\nendstream".encode()

    header = b"%PDF-1.4\n"
    body = bytearray(header)
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        if index == 4:
            rendered = objects[3].replace(b"{length}", str(len(stream)).encode()).replace(b"{stream}", stream)
        else:
            rendered = obj
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


def make_wav() -> bytes:
    """Return a tiny valid PCM WAV used only to prove the cached audio blob is real."""
    sample_rate = 8000
    samples = b"\x00\x00" * 800
    data_size = len(samples)
    riff_size = 36 + data_size
    return (
        b"RIFF"
        + riff_size.to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + sample_rate.to_bytes(4, "little")
        + (sample_rate * 2).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + data_size.to_bytes(4, "little")
        + samples
    )


def seed_offline_content(page, fixture: dict) -> None:
    """Save only the source documents locally; let Prepza populate material caches."""
    documents = fixture["documents"]
    pdfs = [base64.b64encode(make_pdf(title)).decode() for _, title in DOCUMENTS]

    page.evaluate(
        """async ({userId, documents, pdfs}) => {
          localStorage.setItem('prepza-offline-user-id', String(userId));
          const decode = base64 => Uint8Array.from(atob(base64), c => c.charCodeAt(0));

          const openDb = (name, version, stores) => new Promise((resolve, reject) => {
            const request = indexedDB.open(name, version);
            request.onupgradeneeded = () => {
              const db = request.result;
              for (const store of stores) {
                if (!db.objectStoreNames.contains(store)) db.createObjectStore(store, { keyPath: 'key' });
              }
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });

          const putRows = (db, name, rows) => new Promise((resolve, reject) => {
            const tx = db.transaction(name, 'readwrite');
            const store = tx.objectStore(name);
            for (const row of rows) store.put(row);
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
          });

          const clearStore = (db, name) => new Promise((resolve, reject) => {
            const tx = db.transaction(name, 'readwrite');
            tx.objectStore(name).clear();
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
          });

          const metaRows = documents.map((doc, index) => ({
            key: String(userId) + ':' + String(doc.document_id),
            userId,
            documentId: doc.document_id,
            title: doc.title,
            fileType: 'pdf',
            pageCount: 1,
            contentHash: 'offline-real-' + String(doc.document_id),
            savedAt: Date.now() + index,
            assetUrls: [],
          }));
          const assetRows = documents.map((doc, index) => ({
            key: String(userId) + ':' + String(doc.document_id),
            userId,
            documentId: doc.document_id,
            blob: new Blob([decode(pdfs[index])], { type: 'application/pdf' }),
            contentHash: 'offline-real-' + String(doc.document_id),
            savedAt: Date.now() + index,
          }));

          // Create all stores in one upgrade handler, then start with empty
          // material/audio stores. Those stores must be populated by Prepza's
          // real online replay/cache code below, not by this fixture.
          const sharedDb = await openDb(
            'prepza-offline-v2',
            4,
            ['savedStudyHub', 'generatedMaterials', 'generatedAudio'],
          );
          try {
            await putRows(sharedDb, 'savedStudyHub', metaRows);
            await clearStore(sharedDb, 'generatedMaterials');
            await clearStore(sharedDb, 'generatedAudio');
          } finally {
            sharedDb.close();
          }

          const assetDb = await openDb('prepza-offline-study-v1', 1, ['documents']);
          try {
            await putRows(assetDb, 'documents', assetRows);
          } finally {
            assetDb.close();
          }
        }""",
        {
            "userId": fixture["user_id"],
            "documents": documents,
            "pdfs": pdfs,
        },
    )


def mock_ready_podcast_audio(route, unexpected_posts: list[str]) -> None:
    """Give the UI ready audio without invoking any provider/GPU service."""
    request = route.request
    if request.method != "GET":
        unexpected_posts.append(request.url)
        route.fulfill(
            status=409,
            content_type="application/json",
            body=json.dumps({"error": "Unexpected podcast audio generation in fixture"}),
        )
        return

    material_id = parse_qs(urlparse(request.url).query).get("material_id", ["0"])[0]
    route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({
            "audio_status": "ready",
            "audio_url": f"/offline-fixture-audio/{material_id}",
            "duration_seconds": 0.1,
        }),
    )


def mock_podcast_wav(route) -> None:
    route.fulfill(status=200, content_type="audio/wav", body=make_wav())


def wait_for_cached_podcast(page, fixture: dict, document_id: int, material_id: int) -> None:
    page.wait_for_function(
        """async ({userId, documentId, materialId}) => {
          const openDb = () => new Promise((resolve, reject) => {
            const request = indexedDB.open('prepza-offline-v2', 4);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          const readAll = (db, storeName) => new Promise((resolve, reject) => {
            const tx = db.transaction(storeName, 'readonly');
            const request = tx.objectStore(storeName).getAll();
            request.onsuccess = () => resolve(request.result || []);
            request.onerror = () => reject(request.error);
          });
          const db = await openDb();
          try {
            const materials = await readAll(db, 'generatedMaterials');
            const audio = await readAll(db, 'generatedAudio');
            const materialPath = '/documents/' + documentId + '/materials/' + materialId;
            const audioPath = '/documents/' + documentId + '/podcast-audio?material_id=' + materialId;
            const canonicalMaterial = materials.some(row =>
              row.path === materialPath &&
              row.payload?.type === 'podcast' &&
              row.payload?.status === 'ready' &&
              row.payload?.material_id === materialId
            );
            const audioDescriptor = materials.some(row =>
              row.path === audioPath &&
              row.payload?.audio_status === 'ready' &&
              row.payload?.audio_url === '/offline-fixture-audio/' + materialId
            );
            const audioBlob = audio.some(row =>
              row.userId === String(userId) &&
              row.sourceUrl === '/offline-fixture-audio/' + materialId &&
              row.blob instanceof Blob &&
              row.blob.size > 0
            );
            return canonicalMaterial && audioDescriptor && audioBlob;
          } finally {
            db.close();
          }
        }""",
        {
            "userId": fixture["user_id"],
            "documentId": document_id,
            "materialId": material_id,
        },
        timeout=15000,
    )



def main() -> int:
    if shutil.which("docker") is None:
        raise SystemExit("Docker CLI is required.")

    fixture = create_fixture()
    browser = None
    context = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            login(page, fixture)
            seed_offline_content(page, fixture)

            # Guard every online generation endpoint: only a POST carrying the
            # exact selected material ID may reach Flask. Without that header the
            # browser returns 412 here, before the route can enqueue an AI job.
            online_reuse_posts = []
            unguarded_generation_posts = []

            def guard_generation_reuse(route):
                request = route.request
                endpoint = urlparse(request.url).path.rsplit("/", 1)[-1]
                guarded_endpoints = {
                    "summarize", "flashcards", "quiz", "mind-map",
                    "podcast-script", "podcast-audio",
                }
                if request.method != "POST" or endpoint not in guarded_endpoints:
                    route.continue_()
                    return
                material_id = request.headers.get("x-prepza-material-id", "")
                online_reuse_posts.append({
                    "url": request.url,
                    "material_id": material_id,
                })
                if not material_id.isdigit() or int(material_id) <= 0:
                    unguarded_generation_posts.append(request.url)
                    route.fulfill(
                        status=412,
                        content_type="application/json",
                        body=json.dumps({"error": "Test blocked POST without selected ready material ID"}),
                    )
                    return
                route.continue_()

            page.route(
                re.compile(r".*/documents/\d+/(summarize|flashcards|quiz|mind-map|podcast-script|podcast-audio)(?:\?.*)?$"),
                guard_generation_reuse,
            )

            # First exercise the actual online UI against ready PostgreSQL rows.
            # Their exact-ID endpoints return existing artifacts, so no provider
            # or GPU generation is involved. The app must cache canonical records.
            page.get_by_role("button", name=re.compile(r"My Study$")).click(timeout=15000)
            page.get_by_role("button", name="Documents", exact=True).wait_for(timeout=15000)
            page.get_by_role("button", name="Study Materials", exact=True).click(timeout=15000)

            for _, document_title in DOCUMENTS:
                for type_label, expected_text in [
                    ("Summary", "Offline summary"),
                    ("Flashcards", "Offline question"),
                    ("Practice Questions", "Offline quiz question"),
                    ("Mind Map", "Offline branch"),
                ]:
                    material_button = page.get_by_role(
                        "button",
                        name=re.compile(rf"{re.escape(type_label)}.*From: {re.escape(document_title)}"),
                    ).first
                    material_button.click(timeout=15000)
                    page.get_by_text(expected_text, exact=False).wait_for(timeout=15000)
                    print(f"PASS: existing online {type_label} opens for {document_title}")
                    page.go_back(wait_until="commit")
                    # StudyMaterialsScreen remounts on return and selects Documents.
                    page.get_by_role("button", name="Study Materials", exact=True).click(timeout=15000)

            if unguarded_generation_posts:
                raise AssertionError(
                    "Test blocked a generation POST that lacked X-Prepza-Material-ID: "
                    + ", ".join(unguarded_generation_posts)
                )
            if len(online_reuse_posts) < 12:
                raise AssertionError(
                    f"Expected at least 12 exact-material online reuse POSTs, got {len(online_reuse_posts)}: "
                    + json.dumps(online_reuse_posts)
                )
            print(
                f"PASS: {len(online_reuse_posts)} online material requests carried exact IDs; "
                "unguarded AI generation requests were blocked"
            )

            # Podcast's ready descriptor/audio are stubbed at the HTTP boundary.
            # This gives the real player valid audio while making a provider/GPU
            # request impossible. The runtime itself must persist both descriptor
            # and blob before the browser goes offline.
            unexpected_audio_posts = []

            def serve_ready_podcast(route):
                mock_ready_podcast_audio(route, unexpected_audio_posts)

            def serve_podcast_wav(route):
                mock_podcast_wav(route)

            page.route("**/documents/*/podcast-audio*", serve_ready_podcast)
            page.route("**/offline-fixture-audio/*", serve_podcast_wav)
            podcast_material_id = fixture["documents"][0]["materials"]["podcast"]
            podcast_button = page.get_by_role(
                "button",
                name=re.compile(rf"Podcast.*From: {re.escape(DOCUMENTS[0][1])}"),
            ).first
            podcast_button.click(timeout=15000)
            page.locator("audio").wait_for(timeout=15000)
            wait_for_cached_podcast(
                page,
                fixture,
                fixture["documents"][0]["document_id"],
                podcast_material_id,
            )
            if unexpected_audio_posts:
                raise AssertionError(
                    "A ready podcast tried to start audio generation: "
                    + ", ".join(unexpected_audio_posts)
                )
            print("PASS: online podcast replay caches its private script, ready descriptor, and audio Blob")

            # Return to the real list, then remove the HTTP stubs so offline replay
            # cannot pass by accidentally receiving their fake online responses.
            page.go_back(wait_until="commit")
            page.get_by_role("button", name="Documents", exact=True).wait_for(timeout=15000)
            page.get_by_role("button", name="Study Materials", exact=True).click(timeout=15000)
            page.unroute("**/documents/*/podcast-audio*", serve_ready_podcast)
            page.unroute("**/offline-fixture-audio/*", serve_podcast_wav)

            generation_posts = []

            def observe_request(request):
                if request.method == "POST" and any(
                    marker in request.url
                    for marker in ("/summarize", "/flashcards", "/quiz", "/mind-map", "/podcast-script", "/podcast-audio")
                ):
                    generation_posts.append(request.url)

            page.on("request", observe_request)
            context.set_offline(True)
            page.reload(wait_until="domcontentloaded")

            # Wait for React to render after reload. Continue from either
            # restored My Study or Home using the visible, real UI.
            ensure_study_materials_documents_tab(page)

            for _, title in DOCUMENTS:
                page.get_by_text(title, exact=True).wait_for(timeout=15000)
            body = page.locator("body").inner_text(timeout=5000)
            for _, title in DOCUMENTS:
                if title not in body:
                    raise AssertionError(f"Offline Study Materials did not retain document: {title}")
            print("PASS: multiple saved documents remain listed offline")

            # The app itself populated generatedMaterials. Replaying these rows
            # offline must never call a generation POST.
            page.get_by_role("button", name="Study Materials", exact=True).click(timeout=15000)
            for _, document_title in DOCUMENTS:
                for type_label, expected_text in [
                    ("Summary", "Offline summary"),
                    ("Flashcards", "Offline question"),
                    ("Practice Questions", "Offline quiz question"),
                    ("Mind Map", "Offline branch"),
                ]:
                    material_button = page.get_by_role(
                        "button",
                        name=re.compile(rf"{re.escape(type_label)}.*From: {re.escape(document_title)}"),
                    ).first
                    material_button.click(timeout=15000)
                    page.get_by_text(expected_text, exact=False).wait_for(timeout=15000)
                    print(f"PASS: {type_label} replays offline for {document_title}")
                    page.go_back(wait_until="commit")
                    page.get_by_role("button", name="Study Materials", exact=True).click(timeout=15000)

            # Podcast must now resolve from its cached descriptor and Blob, with
            # both the audio HTTP stub and normal network unavailable.
            podcast_button = page.get_by_role(
                "button",
                name=re.compile(rf"Podcast.*From: {re.escape(DOCUMENTS[0][1])}"),
            ).first
            podcast_button.click(timeout=15000)
            page.locator("audio").wait_for(timeout=15000)
            audio_src = page.locator("audio").get_attribute("src") or ""
            if not audio_src.startswith("blob:"):
                raise AssertionError(f"Offline podcast did not resolve to a local Blob URL: {audio_src}")
            print("PASS: cached podcast descriptor and actual audio Blob open offline")

            page.go_back(wait_until="commit")
            page.get_by_role("button", name="Documents", exact=True).wait_for(timeout=15000)
            page.get_by_role("button", name="Study Materials", exact=True).click(timeout=15000)

            if generation_posts:
                raise AssertionError(
                    "Offline artifact replay attempted generation POSTs: "
                    + ", ".join(generation_posts)
                )
            print("PASS: offline artifact replay made no generation POST requests")

            # A cold browser reload while still offline must not lose the cached
            # documents, generated materials, audio descriptor, or actual audio.
            page.reload(wait_until="domcontentloaded")
            ensure_study_materials_documents_tab(page)
            for _, title in DOCUMENTS:
                page.get_by_text(title, exact=True).wait_for(timeout=15000)
            body_after_reload = page.locator("body").inner_text(timeout=5000)
            for _, title in DOCUMENTS:
                if title not in body_after_reload:
                    raise AssertionError(f"Document disappeared after offline reload: {title}")
            print("PASS: multiple documents survive offline reload")

            page.get_by_role("button", name="Study Materials", exact=True).click(timeout=15000)
            for type_label, expected_text in [
                ("Summary", "Offline summary"),
                ("Flashcards", "Offline question"),
                ("Practice Questions", "Offline quiz question"),
                ("Mind Map", "Offline branch"),
            ]:
                material_button = page.get_by_role(
                    "button",
                    name=re.compile(rf"{re.escape(type_label)}.*From: {re.escape(DOCUMENTS[0][1])}"),
                ).first
                material_button.click(timeout=15000)
                page.get_by_text(expected_text, exact=False).wait_for(timeout=15000)
                print(f"PASS: {type_label} survives reload and reopens offline")
                page.go_back(wait_until="commit")
                page.get_by_role("button", name="Study Materials", exact=True).click(timeout=15000)

            podcast_button = page.get_by_role(
                "button",
                name=re.compile(rf"Podcast.*From: {re.escape(DOCUMENTS[0][1])}"),
            ).first
            podcast_button.click(timeout=15000)
            page.locator("audio").wait_for(timeout=15000)
            reload_audio_src = page.locator("audio").get_attribute("src") or ""
            if not reload_audio_src.startswith("blob:"):
                raise AssertionError(f"Offline podcast lost its cached Blob after reload: {reload_audio_src}")
            print("PASS: Podcast survives reload and reopens from its cached Blob")

            # These are product-owned storage limits. Browser/IndexedDB quotas
            # differ by browser and remain separate from Prepza's own caps.
            generated_source = (ROOT / "frontend" / "src" / "offline" / "generatedMaterials.ts").read_text(encoding="utf-8")
            study_source = (ROOT / "frontend" / "src" / "offline" / "studyHubOffline.ts").read_text(encoding="utf-8")
            assert "MAX_GENERATED_ROWS = 80" in generated_source
            assert "MAX_GENERATED_PAYLOAD_BYTES = 512 * 1024" in generated_source
            assert "MAX_AUDIO_CACHE_BYTES = 80 * 1024 * 1024" in generated_source
            assert "MAX_SINGLE_AUDIO_BYTES = 25 * 1024 * 1024" in generated_source
            assert "MAX_SINGLE_ASSET_BYTES = 75 * 1024 * 1024" in study_source
            assert "MAX_TOTAL_ASSET_BYTES = 250 * 1024 * 1024" in study_source
            print("PASS: storage limits match 75MB/doc, 250MB total, 80 material rows, 512KB/material, 25MB/audio and 80MB/audio-cache")

            print("PASS: browser Study Hub offline content/artifact gate is green")
            return 0

    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        cleanup_fixture(fixture)


if __name__ == "__main__":
    raise SystemExit(main())
