"""Real-browser offline content/artifact persistence regression.

This complements scripts/test_browser_study_hub_offline.py. It proves that
multiple saved documents and already-entitled generated artifacts can be
reopened and used after a network loss/reload, rather than merely proving that
the Study Hub clock survives offline.

The test intentionally does not call a real AI provider. It seeds realistic
ready-artifact payloads into the browser's production IndexedDB shape, then
exercises the same Study Materials/document/artifact UI that students use.
The generation endpoints are observed while offline and must not be called.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

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
        [
            "docker",
            "compose",
            "-f",
            COMPOSE_FILE,
            "exec",
            "-T",
            "app",
            "python",
            "-",
        ],
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
    for offset, title in {DOCUMENTS!r}:
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
            original_filename=f"offline-{offset}.pdf",
            status="ready",
            is_removed=False,
        )
        db.session.add(document)
        documents.append({{
            "document_id": document_id,
            "content_id": content.id,
            "title": title,
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
from app import app, db, User, UserKey, Document, DocumentContent, DocumentReadingProgress, StudyTimeLog, StudyStreak

with app.app_context():
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

    page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    page.wait_for_timeout(1200)


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
    documents = fixture["documents"]
    pdfs = [
        base64.b64encode(make_pdf(title)).decode()
        for _, title in DOCUMENTS
    ]
    wav = base64.b64encode(make_wav()).decode()

    page.evaluate(
        """({userId, documents, pdfs, wavBase64, materialTypes}) => {
          localStorage.setItem('prepza-offline-user-id', String(userId));

          const open = (name, version, store) => new Promise((resolve, reject) => {
            const request = indexedDB.open(name, version);
            request.onupgradeneeded = () => {
              const db = request.result;
              if (!db.objectStoreNames.contains(store)) {
                db.createObjectStore(store, { keyPath: 'key' });
              }
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });

          const decode = base64 => Uint8Array.from(atob(base64), c => c.charCodeAt(0));

          const put = (dbName, version, storeName, rows) =>
            open(dbName, version, storeName).then(db => new Promise((resolve, reject) => {
              const tx = db.transaction(storeName, 'readwrite');
              const store = tx.objectStore(storeName);
              for (const row of rows) store.put(row);
              tx.oncomplete = () => { db.close(); resolve(); };
              tx.onerror = () => reject(tx.error);
            }));

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

          const materialRows = [];
          for (let docIndex = 0; docIndex < documents.length; docIndex++) {
            const doc = documents[docIndex];
            for (const type of materialTypes) {
              const materialId = doc.document_id * 10 + materialTypes.indexOf(type) + 1;
              let payload;
              if (type === 'summary') {
                payload = { material_id: materialId, type, status: 'ready', payload: 'Offline summary for ' + doc.title };
              } else if (type === 'flashcards') {
                payload = { material_id: materialId, type, status: 'ready', payload: { cards: [{ q: 'Offline question', a: 'Offline answer' }] } };
              } else if (type === 'quiz') {
                payload = { material_id: materialId, type, status: 'ready', payload: { questions: [{ question: 'Offline quiz question', options: ['A', 'B'], answer_index: 0 }] } };
              } else if (type === 'mind_map') {
                payload = { material_id: materialId, type, status: 'ready', payload: { center: doc.title, branches: [{ label: 'Offline branch' }] } };
              } else {
                payload = { material_id: materialId, type, status: 'ready', payload: { script: 'Offline podcast script', audio_url: '/offline-fixture-audio/' + String(materialId), duration_seconds: 0.1 } };
              }
              materialRows.push({
                key: String(userId) + ':/documents/' + String(doc.document_id) + '/materials/' + String(materialId) + ':null:' + String(Date.now()) + ':' + Math.random().toString(36).slice(2),
                path: '/documents/' + String(doc.document_id) + '/materials/' + String(materialId),
                requestBody: null,
                payload,
                savedAt: Date.now(),
              });
              if (type === 'podcast') {
                materialRows.push({
                  key: String(userId) + ':/documents/' + String(doc.document_id) + '/podcast-audio?material_id=' + String(materialId) + ':null:' + String(Date.now()) + ':' + Math.random().toString(36).slice(2),
                  path: '/documents/' + String(doc.document_id) + '/podcast-audio?material_id=' + String(materialId),
                  requestBody: null,
                  payload: { audio_status: 'ready', audio_url: '/offline-fixture-audio/' + String(materialId), duration_seconds: 0.1 },
                  savedAt: Date.now(),
                });
              }
            }
          }

          const audioRows = documents.flatMap(doc => {
            const materialId = doc.document_id * 10 + materialTypes.indexOf('podcast') + 1;
            const sourceUrl = '/offline-fixture-audio/' + String(materialId);
            return [{
              key: String(userId) + ':' + sourceUrl,
              userId: String(userId),
              sourceUrl,
              blob: new Blob([decode(wavBase64)], { type: 'audio/wav' }),
              savedAt: Date.now(),
            }];
          });

          return Promise.all([
            put('prepza-offline-v2', 3, 'savedStudyHub', metaRows),
            put('prepza-offline-study-v1', 1, 'documents', assetRows),
            put('prepza-offline-v2', 3, 'generatedMaterials', materialRows),
            put('prepza-offline-v2', 3, 'generatedAudio', audioRows),
          ]);
        }""",
        {
            "userId": fixture["user_id"],
            "documents": documents,
            "pdfs": pdfs,
            "wavBase64": wav,
            "materialTypes": list(MATERIAL_TYPES),
        },
    )


def assert_offline_document(page, title: str) -> None:
    page.get_by_text(title, exact=True).wait_for(timeout=15000)
    page.get_by_text(title, exact=True).click()
    page.get_by_text("OFFLINE", exact=True).wait_for(timeout=15000)
    page.get_by_text("Offline study copy", exact=True).wait_for(timeout=15000)
    print(f"PASS: real document bytes open offline for {title}")
    page.get_by_role("button").filter(has=page.locator("svg")).first.click(timeout=5000)
    page.wait_for_timeout(500)


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

            # Establish the normal Study Materials surface before taking the
            # browser offline. The offline list is then rendered entirely from
            # the saved local package.
            page.evaluate(
                """({documentId}) => {
                  sessionStorage.setItem('prepza-navigation-state', JSON.stringify({
                    stack: ['home', 'study-materials'],
                    activeConversationId: null,
                    activeDocumentId: documentId,
                    activeGroupId: null,
                    activeProfileUserId: null,
                    activeOpportunityId: null,
                  }));
                }""",
                {"documentId": fixture["documents"][0]["document_id"]},
            )
            page.reload(wait_until="domcontentloaded")
            page.get_by_text("My Study", exact=True).wait_for(timeout=15000)

            context.set_offline(True)
            page.reload(wait_until="domcontentloaded")
            page.get_by_text("My Study", exact=True).wait_for(timeout=15000)

            body = page.locator("body").inner_text(timeout=5000)
            for _, title in DOCUMENTS:
                if title not in body:
                    raise AssertionError(f"Offline Study Materials did not retain document: {title}")
            print("PASS: multiple saved documents remain listed offline")

            # Capture forbidden generation attempts. The browser is offline,
            # so the correct implementation must satisfy generationRequest from
            # the already-cached material and return before calling POST.
            generation_posts = []
            def observe_request(request):
                if request.method == "POST" and any(
                    marker in request.url
                    for marker in ("/summarize", "/flashcards", "/quiz", "/mind-map", "/podcast-script")
                ):
                    generation_posts.append(request.url)
            page.on("request", observe_request)

            # Verify every document's actual Blob-backed reader copy.
            for _, title in DOCUMENTS:
                assert_offline_document(page, title)

            # Return to Study Materials after each document and verify a real
            # artifact from every document, plus each supported material type.
            # The material list is scoped to the selected document, so each loop
            # explicitly selects the document first. This is deliberately UI-level:
            # the test does not merely count IndexedDB rows.
            page.get_by_text("My Study", exact=True).wait_for(timeout=15000)
            for _, document_title in DOCUMENTS:
                page.get_by_role("button", name=document_title, exact=True).click(timeout=15000)
                page.get_by_role("button", name="Study Materials", exact=True).click(timeout=15000)
                for type_label, expected_text in [
                    ("Summary", "Offline summary"),
                    ("Flashcards", "Offline question"),
                    ("Practice Questions", "Offline quiz question"),
                    ("Mind Map", "Offline branch"),
                ]:
                    page.get_by_role("button", name=type_label, exact=False).first.click(timeout=15000)
                    page.get_by_text(expected_text, exact=False).wait_for(timeout=15000)
                    print(f"PASS: {type_label} opens offline for {document_title}")
                    page.go_back(wait_until="commit")
                    page.get_by_text("My Study", exact=True).wait_for(timeout=15000)
                    page.get_by_role("button", name="Study Materials", exact=True).click(timeout=15000)
                page.get_by_role("button", name="Documents", exact=True).click(timeout=15000)

            # Podcast is tested separately because it has both JSON metadata and
            # a binary audio Blob. The player must resolve the cached descriptor
            # and then the actual Blob-backed object URL without the network.
            page.get_by_role("button", name=DOCUMENTS[0][1], exact=True).click(timeout=15000)
            page.get_by_role("button", name="Study Materials", exact=True).click(timeout=15000)
            page.get_by_role("button", name="Podcast", exact=False).first.click(timeout=15000)
            page.locator("audio").wait_for(timeout=15000)
            audio_src = page.locator("audio").get_attribute("src") or ""
            if not audio_src.startswith("blob:"):
                raise AssertionError(f"Offline podcast did not resolve to a local Blob URL: {audio_src}")
            print("PASS: generated podcast metadata and actual audio Blob open offline")

            if generation_posts:
                raise AssertionError(
                    "Offline artifact replay attempted generation POSTs: "
                    + ", ".join(generation_posts)
                )
            print("PASS: offline artifact replay made no generation POST requests")

            # Reload while still offline and repeat the most important proof:
            # local documents and generated materials survive a real browser reload,
            # not just SPA navigation.
            page.reload(wait_until="domcontentloaded")
            page.get_by_text("My Study", exact=True).wait_for(timeout=15000)
            body_after_reload = page.locator("body").inner_text(timeout=5000)
            for _, title in DOCUMENTS:
                if title not in body_after_reload:
                    raise AssertionError(f"Document disappeared after offline reload: {title}")
            print("PASS: multiple documents and their offline package survive reload")

            # These are product-owned limits, not browser/vendor quotas. Browser
            # quotas are separate and browser-specific; this verifies that the
            # exact application caps remain encoded in the implementation.
            generated_source = (ROOT / "frontend" / "src" / "offline" / "generatedMaterials.ts").read_text(encoding="utf-8")
            study_source = (ROOT / "frontend" / "src" / "offline" / "studyHubOffline.ts").read_text(encoding="utf-8")
            assert "MAX_GENERATED_ROWS = 80" in generated_source
            assert "MAX_GENERATED_PAYLOAD_BYTES = 512 * 1024" in generated_source
            assert "MAX_AUDIO_CACHE_BYTES = 80 * 1024 * 1024" in generated_source
            assert "MAX_SINGLE_AUDIO_BYTES = 25 * 1024 * 1024" in generated_source
            assert "MAX_SINGLE_ASSET_BYTES = 75 * 1024 * 1024" in study_source
            assert "MAX_TOTAL_ASSET_BYTES = 250 * 1024 * 1024" in study_source
            print("PASS: offline document/artifact storage limits are the intended 75MB/doc, 250MB total, 80 material rows, 512KB/material payload, 25MB/audio and 80MB/audio-cache caps")

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
