"""PostgreSQL-backed runtime regression for the E2EE identity registration contract."""

import base64

import pytest

from app import app, db
from runtime_test_fixtures import runtime_test_users


def _public_key(seed: int) -> str:
    # A deterministic, syntactically valid uncompressed P-256-shaped payload.
    raw = bytes([0x04]) + bytes(((seed + index) % 256 for index in range(64)))
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


@pytest.fixture
def runtime_users():
    with runtime_test_users() as users:
        yield users


def _client_for(user):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user.id
        session["_session_version"] = user.session_version
        session["csrf_token"] = f"csrf-{user.id}"
    return client


def test_identity_registration_is_idempotent_and_rejects_replacement(runtime_users):
    client = _client_for(runtime_users["primary"])
    first = _public_key(10)

    response = client.post(
        "/keys/register",
        json={"public_key": first},
        headers={"X-CSRF-Token": f"csrf-{runtime_users['primary'].id}"},
    )
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "already_registered": False}

    replay = client.post(
        "/keys/register",
        json={"public_key": first},
        headers={"X-CSRF-Token": f"csrf-{runtime_users['primary'].id}"},
    )
    assert replay.status_code == 200
    assert replay.get_json() == {"ok": True, "already_registered": True}

    replacement = client.post(
        "/keys/register",
        json={"public_key": _public_key(200)},
        headers={"X-CSRF-Token": f"csrf-{runtime_users['primary'].id}"},
    )
    assert replacement.status_code == 409
    assert replacement.get_json()["code"] == "IDENTITY_KEY_REPLACEMENT_REQUIRED"


def test_identity_registration_requires_auth_and_valid_key(runtime_users):
    anonymous = app.test_client()
    response = anonymous.post(
        "/keys/register",
        json={"public_key": _public_key(1)},
    )
    assert response.status_code == 401

    client = _client_for(runtime_users["peer"])
    bad = client.post(
        "/keys/register",
        json={"public_key": "not-a-p256-key"},
        headers={"X-CSRF-Token": f"csrf-{runtime_users['peer'].id}"},
    )
    assert bad.status_code == 400

    malformed_shape = client.post(
        "/keys/register",
        json={"public_key": base64.urlsafe_b64encode(b"too-short").decode().rstrip("=")},
        headers={"X-CSRF-Token": f"csrf-{runtime_users['peer'].id}"},
    )
    assert malformed_shape.status_code == 400


def test_registered_public_key_is_visible_to_authenticated_chat_peer(runtime_users):
    owner = _client_for(runtime_users["primary"])
    peer = _client_for(runtime_users["peer"])
    key = _public_key(77)

    register = owner.post(
        "/keys/register",
        json={"public_key": key},
        headers={"X-CSRF-Token": f"csrf-{runtime_users['primary'].id}"},
    )
    assert register.status_code == 200

    response = peer.get(f"/keys/{runtime_users['primary'].id}")
    assert response.status_code == 200
    assert response.get_json() == {"public_key": key}


def test_identity_cleanup_can_remove_device_record(runtime_users):
    user_id = runtime_users["primary"].id
    db.session.execute(
        db.text("DELETE FROM user_key WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    db.session.commit()
    row = db.session.execute(
        db.text("SELECT public_key FROM user_key WHERE user_id = :user_id"),
        {"user_id": user_id},
    ).scalar_one_or_none()
    assert row is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
