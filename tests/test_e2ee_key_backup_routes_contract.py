from __future__ import annotations

from academic_models import Program, University
from app_factory import create_app
from auth_guards import require_csrf
from e2ee_key_backup_routes import register_e2ee_key_backup_routes
from extensions import db
from security_models import UserKey
from user_models import User


def _build_app(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("SECRET_KEY", "e2ee-key-backup-contract")
    monkeypatch.delenv("REDIS_URL", raising=False)
    app, _limiter = create_app()
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    tables = [University.__table__, Program.__table__, User.__table__, UserKey.__table__]
    with app.app_context():
        db.metadata.create_all(bind=db.engine, tables=tables)
        first = User(email="backup-first@example.test", password_hash="x")
        second = User(email="backup-second@example.test", password_hash="x")
        db.session.add_all([first, second])
        db.session.commit()
        ids = {"first": first.id, "second": second.id}
    register_e2ee_key_backup_routes(app, db, UserKey, require_csrf)
    return app, ids, tables


def _cleanup(app, tables):
    with app.app_context():
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=list(reversed(tables)))


def _authenticate(client, user_id, csrf_token="test-csrf-token"):
    with client.session_transaction() as stored:
        stored["user_id"] = user_id
        stored["csrf_token"] = csrf_token


def test_key_backup_route_preserves_session_scope_and_csrf(monkeypatch):
    app, ids, tables = _build_app(monkeypatch)
    try:
        routes = {
            rule.endpoint: (rule.rule, frozenset(rule.methods - {"HEAD", "OPTIONS"}))
            for rule in app.url_map.iter_rules()
            if rule.endpoint != "static"
        }
        assert routes == {
            "upload_key_backup": ("/keys/backup", frozenset({"POST"})),
            "get_key_backup": ("/keys/backup", frozenset({"GET"})),
        }

        client = app.test_client()
        anonymous_get = client.get("/keys/backup")
        assert anonymous_get.status_code == 401
        assert anonymous_get.get_json() == {"error": "Not logged in"}

        with client.session_transaction() as stored:
            stored["user_id"] = ids["first"]
        missing_csrf = client.post(
            "/keys/backup",
            json={"encrypted_private_key": "cipher", "kdf_salt": "salt"},
        )
        assert missing_csrf.status_code == 403
        assert missing_csrf.get_json() == {"error": "Missing or invalid CSRF token"}

        with client.session_transaction() as stored:
            stored.clear()
            stored["csrf_token"] = "test-csrf-token"
        anonymous_post = client.post(
            "/keys/backup",
            json={"encrypted_private_key": "cipher", "kdf_salt": "salt"},
            headers={"X-CSRF-Token": "test-csrf-token"},
        )
        assert anonymous_post.status_code == 401
        assert anonymous_post.get_json() == {"error": "Not logged in"}

        with app.app_context():
            db.session.add_all([
                UserKey(
                    user_id=ids["first"],
                    public_key="public-first",
                    encrypted_private_key="cipher-first",
                    kdf_salt="salt-first",
                ),
                UserKey(
                    user_id=ids["second"],
                    public_key="public-second",
                    encrypted_private_key="cipher-second",
                    kdf_salt="salt-second",
                ),
            ])
            db.session.commit()

        _authenticate(client, ids["first"])
        first_backup = client.get("/keys/backup")
        assert first_backup.status_code == 200
        assert first_backup.get_json() == {
            "encrypted_private_key": "cipher-first",
            "kdf_salt": "salt-first",
        }

        _authenticate(client, ids["second"])
        second_backup = client.get("/keys/backup")
        assert second_backup.status_code == 200
        assert second_backup.get_json() == {
            "encrypted_private_key": "cipher-second",
            "kdf_salt": "salt-second",
        }
    finally:
        _cleanup(app, tables)


def test_key_backup_route_preserves_validation_and_payload_contract(monkeypatch):
    app, ids, tables = _build_app(monkeypatch)
    try:
        client = app.test_client()
        _authenticate(client, ids["first"])
        headers = {"X-CSRF-Token": "test-csrf-token"}

        no_backup = client.get("/keys/backup")
        assert no_backup.status_code == 404
        assert no_backup.get_json() == {"error": "No backup found for this account"}

        missing_ciphertext = client.post("/keys/backup", json={"kdf_salt": "salt"}, headers=headers)
        assert missing_ciphertext.status_code == 400
        assert missing_ciphertext.get_json() == {"error": "encrypted_private_key is required"}

        missing_salt = client.post("/keys/backup", json={"encrypted_private_key": "cipher"}, headers=headers)
        assert missing_salt.status_code == 400
        assert missing_salt.get_json() == {"error": "kdf_salt is required"}

        oversized_ciphertext = client.post(
            "/keys/backup",
            json={"encrypted_private_key": "x" * 8001, "kdf_salt": "salt"},
            headers=headers,
        )
        assert oversized_ciphertext.status_code == 400
        assert oversized_ciphertext.get_json() == {
            "error": "encrypted_private_key must be 8000 characters or fewer"
        }

        oversized_salt = client.post(
            "/keys/backup",
            json={"encrypted_private_key": "cipher", "kdf_salt": "s" * 129},
            headers=headers,
        )
        assert oversized_salt.status_code == 400
        assert oversized_salt.get_json() == {
            "error": "kdf_salt must be 128 characters or fewer"
        }

        missing_identity = client.post(
            "/keys/backup",
            json={"encrypted_private_key": "cipher", "kdf_salt": "salt"},
            headers=headers,
        )
        assert missing_identity.status_code == 404
        assert missing_identity.get_json() == {
            "error": "Register a public key via /keys/register before uploading a backup"
        }

        with app.app_context():
            db.session.add(UserKey(user_id=ids["first"], public_key="public-first"))
            db.session.commit()

        saved = client.post(
            "/keys/backup",
            json={"encrypted_private_key": "ciphertext-value", "kdf_salt": "salt-value"},
            headers=headers,
        )
        assert saved.status_code == 200
        assert saved.get_json() == {"message": "Backup saved"}

        with app.app_context():
            key = UserKey.query.filter_by(user_id=ids["first"]).first()
            assert key.encrypted_private_key == "ciphertext-value"
            assert key.kdf_salt == "salt-value"

        downloaded = client.get("/keys/backup")
        assert downloaded.status_code == 200
        assert downloaded.get_json() == {
            "encrypted_private_key": "ciphertext-value",
            "kdf_salt": "salt-value",
        }
    finally:
        _cleanup(app, tables)
