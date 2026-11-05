"""Guard the public application shell and health endpoints during route extraction."""

from pathlib import Path
from tempfile import TemporaryDirectory

from flask import Flask

from public_shell_routes import register_public_shell_routes


class FakeLimiter:
    def exempt(self, function):
        function._rate_limit_exempt = True
        return function


class FakeSession:
    def __init__(self):
        self.fail = False
        self.statements = []

    def execute(self, statement):
        if self.fail:
            raise RuntimeError("database unavailable")
        self.statements.append(str(statement))
        return None


class FakeDb:
    def __init__(self):
        self.session = FakeSession()


def _client(static_dir):
    app = Flask(__name__, static_folder=str(static_dir), static_url_path="")
    db = FakeDb()
    limiter = FakeLimiter()
    sweeps = []
    register_public_shell_routes(app, db, limiter, lambda: sweeps.append("sweep"))
    return app.test_client(), app, db, sweeps


def test_public_shell_registrar_keeps_original_paths_methods_and_endpoint_names():
    with TemporaryDirectory() as directory:
        _, app, _, _ = _client(directory)

    routes = {
        (rule.rule, rule.endpoint, frozenset(rule.methods))
        for rule in app.url_map.iter_rules()
    }
    for path, endpoint in (("/", "home"), ("/sw.js", "service_worker"), ("/health", "health")):
        assert (path, endpoint, frozenset({"GET", "HEAD", "OPTIONS"})) in routes


def test_home_serves_the_existing_index_document_from_the_app_static_folder():
    with TemporaryDirectory() as directory:
        Path(directory, "index.html").write_text("<main>Prepza</main>", encoding="utf-8")
        client, _, _, _ = _client(directory)

        response = client.get("/")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "<main>Prepza</main>"


def test_service_worker_keeps_root_scope_javascript_content_type_and_cache_policy():
    with TemporaryDirectory() as directory:
        Path(directory, "sw.js").write_text("self.addEventListener('install', () => {})", encoding="utf-8")
        client, _, _, _ = _client(directory)

        response = client.get("/sw.js")

    assert response.status_code == 200
    assert response.mimetype == "application/javascript"
    assert response.headers["Cache-Control"] == "no-cache"
    assert "self.addEventListener" in response.get_data(as_text=True)


def test_health_keeps_database_probe_sweep_and_success_response():
    with TemporaryDirectory() as directory:
        client, app, db, sweeps = _client(directory)

        response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
    assert db.session.statements == ["SELECT 1"]
    assert sweeps == ["sweep"]
    assert app.view_functions["health"]._rate_limit_exempt is True


def test_health_keeps_existing_503_response_when_database_probe_fails():
    with TemporaryDirectory() as directory:
        client, _, db, sweeps = _client(directory)
        db.session.fail = True

        response = client.get("/health")

    assert response.status_code == 503
    assert response.get_json() == {"status": "error"}
    assert sweeps == []


def test_public_shell_routes_are_registered_at_the_original_app_initialization_point():
    root = Path(__file__).resolve().parents[1]
    app_source = (root / "app.py").read_text(encoding="utf-8")
    registrar = "register_public_shell_routes(app, db, limiter, lambda: _sweep_expired_opportunities_safe())"
    register_at = app_source.index(registrar)

    assert register_at > app_source.index("def track_last_active(")
    assert register_at < app_source.index("register_academic_catalog_routes(app, University, Program)")
    for path in ('@app.route("/")', '@app.route("/sw.js")', '@app.route("/health")'):
        assert path not in app_source
    for name in ("def home(", "def service_worker(", "def health("):
        assert name not in app_source


def test_public_shell_module_does_not_import_the_partially_initialized_app_module():
    source = (Path(__file__).resolve().parents[1] / "public_shell_routes.py").read_text(encoding="utf-8")
    assert "from app import" not in source
    assert "import app" not in source
    for route in ('@app.route("/")', '@app.route("/sw.js")', '@app.route("/health")'):
        assert route in source
