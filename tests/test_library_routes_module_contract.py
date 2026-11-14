from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from flask import Flask

from library_routes import register_library_routes

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
REGISTRY_SOURCE = (ROOT / "route_registry.py").read_text(encoding="utf-8")
MODULE_SOURCE = (ROOT / "library_routes.py").read_text(encoding="utf-8")


def test_app_delegates_library_and_admin_content_material_routes() -> None:
    assert "register_library_routes(" in APP_SOURCE
    assert 'from library_routes import register_library_routes as register' in REGISTRY_SOURCE

    assert "LIBRARY_XP_ON_APPROVAL = 50" in APP_SOURCE
    assert "XP_LIBRARY_PUBLICATION_APPROVED = LIBRARY_XP_ON_APPROVAL" in APP_SOURCE
    assert "def _ensure_studyhub_document_for_publication(" not in APP_SOURCE
    assert "def _serialize_admin_content_material(" not in APP_SOURCE
    assert "from app import" not in MODULE_SOURCE
    for route in (
        '@app.route("/library/publish", methods=["POST"])',
        '@app.route("/library/my-submissions")',
        '@app.route("/library")',
        '@app.route("/library/<int:publication_id>/save", methods=["POST"])',
        '@app.route("/library/<int:publication_id>/save", methods=["DELETE"])',
        '@app.route("/library/saved")',
        '@app.route("/library/<int:publication_id>/report", methods=["POST"])',
        '@app.route("/admin/library/queue")',
        '@app.route("/admin/library/<int:publication_id>/approve", methods=["POST"])',
        '@app.route("/admin/library/<int:publication_id>/reject", methods=["POST"])',
        '@app.route("/admin/library/<int:publication_id>/remove", methods=["POST"])',
        '@app.route("/admin/library/reports")',
        '@app.route("/admin/library/reports/<int:report_id>/resolve", methods=["POST"])',
        '@app.route("/admin/content-materials")',
        '@app.route("/admin/content-materials/<int:material_id>/flag", methods=["POST"])',
        '@app.route("/admin/content-materials/<int:material_id>/unflag", methods=["POST"])',
    ):
        assert route not in APP_SOURCE
        assert route in MODULE_SOURCE


def test_library_registration_preserves_route_methods_and_admin_guards() -> None:
    app = Flask("prepza-library-routes-contract")
    identity = lambda function: function

    register_library_routes(
        app,
        SimpleNamespace(session=object()),
        User=object(),
        Document=object(),
        DocumentContent=object(),
        GeneratedMaterial=object(),
        LibraryPublication=object(),
        SavedLibraryMaterial=object(),
        LibraryReport=object(),
        SystemSetting=object(),
        University=object(),
        Program=object(),
        XpEvent=object(),
        LIBRARY_ACTIVE_STATUSES={"approved"},
        LIBRARY_DESCRIPTION_MAX=1000,
        LIBRARY_MATERIAL_TYPES={"summary"},
        LIBRARY_TITLE_MAX=150,
        LIBRARY_XP_ON_APPROVAL=50,
        _free_library_publication_ids=lambda *_args: set(),
        _student_has_premium_library=lambda *_args: False,
        _document_content_has_flagged_material=lambda *_args: False,
        _flagged_document_ids=lambda *_args: set(),
        get_user_subscription_status=lambda *_args: {},
        _can_publish_document=lambda *_args: True,
        _display_name=lambda user: "Student",
        check_and_unlock_achievements=lambda *_args: [],
        log_admin_action=lambda *_args, **_kwargs: None,
        require_csrf=identity,
        require_admin=identity,
    )

    routes = {}
    for rule in app.url_map.iter_rules():
        routes.setdefault(rule.rule, set()).update(rule.methods)
    assert "POST" in routes["/library/publish"]
    assert "GET" in routes["/library"]
    assert "POST" in routes["/library/<int:publication_id>/save"]
    assert "DELETE" in routes["/library/<int:publication_id>/save"]
    assert "GET" in routes["/admin/library/queue"]
    assert "POST" in routes["/admin/library/<int:publication_id>/approve"]
    assert "POST" in routes["/admin/content-materials/<int:material_id>/flag"]
    assert MODULE_SOURCE.count("@require_csrf") == 10
    assert MODULE_SOURCE.count("@require_admin") == 9
