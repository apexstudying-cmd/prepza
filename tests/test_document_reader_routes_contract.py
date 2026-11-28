"""Behavior and ownership contracts for the native document-reader routes."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

from document_reader_routes import register_document_reader_routes


ROOT = Path(__file__).resolve().parents[1]


class FakeQuery:
    def __init__(self, item=None):
        self.item = item
        self.filters = None

    def filter_by(self, **filters):
        self.filters = filters
        return self

    def first(self):
        return self.item


class FakeProgress:
    query = FakeQuery()

    def __init__(self, user_id, document_id, page_num):
        self.user_id = user_id
        self.document_id = document_id
        self.page_num = page_num


def build_reader(*, allowed=True, progress=None, file_type="pdf", file_bytes=b"private-pdf", render_error=False):
    app = Flask("prepza-document-reader-contract")
    app.secret_key = "reader-contract"
    document = SimpleNamespace(id=7, user_id=1, document_content_id=11, is_removed=False)
    content = SimpleNamespace(
        id=11, status="ready", page_count=5, file_type=file_type,
        storage_path="private/student/document.pdf",
    )
    state = {
        "allowed": allowed,
        "study_lookups": [],
        "file_bytes": file_bytes,
        "file_calls": [],
        "render_error": render_error,
        "render_calls": [],
        "watermark_calls": [],
    }

    class FakeSession:
        def __init__(self):
            self.added = []
            self.commits = 0

        def add(self, value):
            self.added.append(value)

        def commit(self):
            self.commits += 1

    db = SimpleNamespace(session=FakeSession())

    def get_studyable_document(user_id, document_id):
        state["study_lookups"].append((user_id, document_id))
        if not state["allowed"] or document_id != document.id or content.status != "ready":
            return None
        return document, content

    def require_csrf(view):
        view._csrf_guarded = True
        return view

    def fetch_private_file_bytes(path, *, bucket):
        state["file_calls"].append((path, bucket))
        return state["file_bytes"]

    def document_reader_watermark(user_id, selected_document):
        state["watermark_calls"].append((user_id, selected_document.id))
        return "SOURCED FROM PREPZA"

    def render_watermarked_page(data, page_num, watermark, *, zoom):
        state["render_calls"].append((data, page_num, watermark, zoom))
        if state["render_error"]:
            raise RuntimeError("render failed")
        return b"rendered-png", None

    FakeProgress.query = FakeQuery(progress)
    register_document_reader_routes(
        app,
        db,
        DocumentReadingProgress=FakeProgress,
        require_csrf=require_csrf,
        get_studyable_document=get_studyable_document,
        document_reader_watermark=document_reader_watermark,
        fetch_private_file_bytes=fetch_private_file_bytes,
        render_watermarked_page=render_watermarked_page,
    )
    return app, app.test_client(), db, state


def authenticate(client):
    with client.session_transaction() as cookie_session:
        cookie_session["user_id"] = 1


def test_reader_routes_keep_original_paths_methods_and_csrf_guard():
    app, _, _, _ = build_reader()
    routes = {
        rule.endpoint: (rule.rule, frozenset(rule.methods - {"HEAD", "OPTIONS"}))
        for rule in app.url_map.iter_rules()
        if rule.endpoint != "static"
    }

    assert routes == {
        "get_document_reading": ("/documents/<int:document_id>/reading", frozenset({"GET"})),
        "save_document_reading": ("/documents/<int:document_id>/reading", frozenset({"POST"})),
        "render_document_reading_page": (
            "/documents/<int:document_id>/reading/page/<int:page_num>",
            frozenset({"GET"}),
        ),
    }
    assert getattr(app.view_functions["save_document_reading"], "_csrf_guarded", False) is True


def test_reader_progress_get_keeps_default_and_clamped_page_behavior():
    _, client, _, _ = build_reader(progress=FakeProgress(1, 7, 99))
    authenticate(client)

    response = client.get("/documents/7/reading")

    assert response.status_code == 200
    assert response.get_json() == {"document_id": 7, "page_num": 4, "page_count": 5}


def test_reader_progress_get_defaults_to_first_page_without_saved_progress():
    _, client, _, _ = build_reader()
    authenticate(client)

    response = client.get("/documents/7/reading")

    assert response.status_code == 200
    assert response.get_json() == {"document_id": 7, "page_num": 0, "page_count": 5}


def test_reader_progress_post_persists_valid_page():
    _, client, db, _ = build_reader()
    authenticate(client)

    response = client.post("/documents/7/reading", json={"page_num": 3})

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "page_num": 3}
    assert len(db.session.added) == 1
    assert db.session.added[0].user_id == 1
    assert db.session.added[0].document_id == 7
    assert db.session.added[0].page_num == 3
    assert db.session.commits == 1


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ({"page_num": True}, "page_num must be a non-negative integer"),
        ({"page_num": -1}, "page_num must be a non-negative integer"),
        ({"page_num": 5}, "page_num is outside the document"),
        ({}, "page_num must be a non-negative integer"),
    ],
)
def test_reader_progress_post_rejects_invalid_page_values(payload, expected_error):
    _, client, db, _ = build_reader()
    authenticate(client)

    response = client.post("/documents/7/reading", json=payload)

    assert response.status_code == 400
    assert response.get_json() == {"error": expected_error}
    assert db.session.added == []
    assert db.session.commits == 0


def test_reader_page_returns_private_png_with_original_cache_and_watermark_contract():
    _, client, _, state = build_reader()
    authenticate(client)

    response = client.get("/documents/7/reading/page/2")

    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.data == b"rendered-png"
    assert response.headers["Cache-Control"] == "private, no-store, max-age=0"
    assert response.headers["Content-Disposition"] == "inline"
    assert state["file_calls"] == [("private/student/document.pdf", "documents")]
    assert state["watermark_calls"] == [(1, 7)]
    assert state["render_calls"] == [(b"private-pdf", 2, "SOURCED FROM PREPZA", 1.6)]


def test_reader_page_checks_study_permission_before_private_storage():
    _, client, _, state = build_reader(allowed=False)
    authenticate(client)

    response = client.get("/documents/7/reading/page/2")

    assert response.status_code == 404
    assert response.get_json() == {"error": "Document not found"}
    assert state["file_calls"] == []
    assert state["render_calls"] == []


def test_reader_page_preserves_pdf_only_and_page_bounds_responses():
    _, client, _, _ = build_reader(file_type="docx")
    authenticate(client)
    non_pdf = client.get("/documents/7/reading/page/2")
    assert non_pdf.status_code == 415
    assert non_pdf.get_json() == {"error": "Native reading currently supports PDF documents only"}

    _, client, _, state = build_reader()
    authenticate(client)
    out_of_range = client.get("/documents/7/reading/page/5")
    assert out_of_range.status_code == 404
    assert out_of_range.get_json() == {"error": "Page not found"}
    assert state["file_calls"] == []


def test_reader_page_preserves_storage_and_render_failure_responses():
    _, client, _, state = build_reader(file_bytes=None)
    authenticate(client)
    unavailable = client.get("/documents/7/reading/page/2")
    assert unavailable.status_code == 502
    assert unavailable.get_json() == {"error": "Document file could not be loaded"}

    _, client, _, state = build_reader(render_error=True)
    authenticate(client)
    failed = client.get("/documents/7/reading/page/2")
    assert failed.status_code == 500
    assert failed.get_json() == {"error": "Document page could not be rendered"}


def test_reader_routes_require_a_session_before_document_lookup():
    _, client, _, state = build_reader()

    response = client.get("/documents/7/reading/page/2")

    assert response.status_code == 401
    assert response.get_json() == {"error": "Not logged in"}
    assert state["study_lookups"] == []


def test_reader_module_has_no_dependency_on_the_flask_entry_module():
    source = (ROOT / "document_reader_routes.py").read_text(encoding="utf-8")
    assert "from app import" not in source
    assert "import app" not in source


def test_launch_wiring_audit_tracks_document_reader_route_module_owner():
    source = (ROOT / "tools/verify_launch_wiring.py").read_text(encoding="utf-8")
    assert 'DOCUMENT_READER_ROUTES = ROOT / "document_reader_routes.py"' in source
    assert 'require_file(DOCUMENT_READER_ROUTES, "Document reader route module")' in source
    assert '"register_document_reader_routes("' in source
    assert '@app.route("/documents/<int:document_id>/reading/page/<int:page_num>")' in source
