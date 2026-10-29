from request_observability import evaluate_alerts


def test_alert_rules_activate_at_documented_thresholds():
    assert evaluate_alerts(recent_5xx=4, recent_slow=9) == []

    alerts = evaluate_alerts(recent_5xx=5, recent_slow=10)

    assert {alert["key"] for alert in alerts} == {"http_5xx_spike", "slow_request_spike"}
    assert all(alert["window_minutes"] == 5 for alert in alerts)


def test_alert_rules_do_not_expose_request_content():
    alerts = evaluate_alerts(recent_5xx=5, recent_slow=0)
    assert alerts == [{
        "key": "http_5xx_spike",
        "severity": "critical",
        "count": 5,
        "threshold": 5,
        "window_minutes": 5,
        "message": "Five or more server-error responses were recorded in five minutes.",
    }]


def test_http_middleware_generates_server_owned_id_without_logging_private_url_data(caplog):
    import logging
    from flask import Flask
    from sqlalchemy import create_engine
    from request_observability import register_request_observability

    app = Flask("http-observability-test")
    engine = create_engine("sqlite:///:memory:")
    fake_db = type("FakeDB", (), {"engine": engine})()
    identity_admin = lambda function: function
    fake_model = type("FakeModel", (), {})
    register_request_observability(app, fake_db, identity_admin, fake_model)

    @app.get("/health/<int:record_id>")
    def health(record_id):
        return {"ok": True, "record_id": record_id}

    caplog.set_level(logging.INFO, logger="prepza.http_observability")
    with app.test_client() as client:
        response = client.get("/health/123?secret=DO_NOT_LOG", headers={"X-Request-ID": "deadbeef-1234-5678-abcd-123456789abc"})

    assert response.status_code == 200
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32
    assert all(character in "0123456789abcdef" for character in request_id)
    assert request_id != "deadbeef-1234-5678-abcd-123456789abc"
    assert "DO_NOT_LOG" not in caplog.text
    assert "123?secret" not in caplog.text
    assert request_id in caplog.text
    engine.dispose()


def test_client_request_id_is_not_trusted():
    from flask import Flask
    from sqlalchemy import create_engine
    from request_observability import register_request_observability

    app = Flask("http-observability-invalid-id-test")
    engine = create_engine("sqlite:///:memory:")
    fake_db = type("FakeDB", (), {"engine": engine})()
    register_request_observability(app, fake_db, lambda function: function, type("FakeModel", (), {}))

    @app.get("/health")
    def health():
        return {"ok": True}

    with app.test_client() as client:
        response = client.get("/health", headers={"X-Request-ID": "bad id with spaces"})

    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32
    assert " " not in request_id
    engine.dispose()



def test_http_alert_is_logged_automatically_when_threshold_is_crossed(caplog, monkeypatch):
    import json
    import logging
    from unittest.mock import Mock
    import sentry_sdk
    from flask import Flask
    from sqlalchemy import create_engine, text
    from request_observability import register_request_observability

    app = Flask("http-observability-alert-test")
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE request_observability_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id VARCHAR(64) NOT NULL,
                method VARCHAR(12) NOT NULL,
                route VARCHAR(160) NOT NULL,
                status_code INTEGER NOT NULL,
                duration_ms FLOAT,
                occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
    fake_db = type("FakeDB", (), {"engine": engine})()
    capture_message = Mock()
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setattr(sentry_sdk, "capture_message", capture_message)
    register_request_observability(app, fake_db, lambda function: function, type("FakeModel", (), {}))

    @app.get("/synthetic-5xx")
    def synthetic_failure():
        return {"error": "synthetic"}, 500

    caplog.set_level(logging.WARNING, logger="prepza.http_observability")
    with app.test_client() as client:
        for _ in range(5):
            assert client.get("/synthetic-5xx?private=never-log").status_code == 500

    alert_records = [
        json.loads(record.getMessage())
        for record in caplog.records
        if "http_observability_alert_threshold_crossed" in record.getMessage()
    ]
    assert len(alert_records) == 1
    assert alert_records[0]["alert_keys"] == ["http_5xx_spike"]
    assert alert_records[0]["recent_5xx"] == 5
    capture_message.assert_called_once()
    assert "http_5xx_spike" in capture_message.call_args.args[0]
    assert capture_message.call_args.kwargs["level"] == "error"
    assert "private" not in caplog.text
    assert "synthetic" not in caplog.text
    engine.dispose()



def test_external_alert_delivery_is_disabled_without_sentry_configuration(monkeypatch):
    from unittest.mock import Mock
    import sentry_sdk
    from request_observability import _dispatch_external_alerts

    monkeypatch.delenv("SENTRY_DSN", raising=False)
    capture_message = Mock()
    monkeypatch.setattr(sentry_sdk, "capture_message", capture_message)

    _dispatch_external_alerts([{
        "key": "http_5xx_spike",
        "severity": "critical",
        "count": 5,
        "threshold": 5,
        "window_minutes": 5,
        "message": "Synthetic test alert.",
    }])

    capture_message.assert_not_called()


def test_sentry_event_scrubber_removes_request_and_user_secrets():
    from request_observability import scrub_sentry_event

    event = {
        "message": "Prepza HTTP observability alert http_5xx_spike",
        "request": {
            "url": "https://prepza.example/api/route?token=DO_NOT_SEND",
            "query_string": "token=DO_NOT_SEND",
            "data": "{\"student_message\":\"DO_NOT_SEND\"}",
            "cookies": {"session": "DO_NOT_SEND"},
            "headers": {"Authorization": "Bearer DO_NOT_SEND", "X-Request-ID": "opaque-id"},
            "method": "POST",
        },
        "user": {
            "id": "student-123",
            "email": "student@example.test",
            "ip_address": "192.0.2.10",
        },
        "extra": {"prompt": "DO_NOT_SEND"},
    }

    scrubbed = scrub_sentry_event(event, {})

    assert scrubbed["message"] == event["message"]
    assert scrubbed["request"]["url"] == "https://prepza.example/unmatched"
    assert scrubbed["request"]["method"] == "POST"
    assert "query_string" not in scrubbed["request"]
    assert "data" not in scrubbed["request"]
    assert "cookies" not in scrubbed["request"]
    assert "headers" not in scrubbed["request"]
    assert "user" not in scrubbed or not scrubbed["user"]
    assert "extra" not in scrubbed
    assert "DO_NOT_SEND" not in str(scrubbed)



def test_sentry_scrubber_removes_request_payload_and_uses_route_template():
    from flask import Flask, jsonify, request
    from request_observability import scrub_sentry_event

    app = Flask("sentry-privacy-test")

    @app.get("/documents/<int:document_id>")
    def synthetic_document(document_id):
        event = {
            "request": {
                "url": request.url,
                "query_string": "token=private-token",
                "data": "private student prompt",
                "cookies": {"session": "private-cookie"},
                "headers": {"Authorization": "private-header"},
                "env": {"REMOTE_ADDR": "192.0.2.10"},
            },
            "user": {
                "id": "private-user-id",
                "email": "student@example.invalid",
                "username": "private-username",
                "ip_address": "192.0.2.10",
            },
            "contexts": {"request": {"url": "private-context"}},
            "breadcrumbs": [{"message": "private prompt text"}],
            "extra": {"document_text": "private page text"},
        }
        return jsonify(scrub_sentry_event(event, None))

    response = app.test_client().get("/documents/123?token=private-token")
    assert response.status_code == 200
    data = response.get_json()
    assert data["request"]["url"].endswith("/documents/<int:document_id>")
    assert "token" not in data["request"]["url"]
    assert not {"query_string", "data", "cookies", "headers", "env"} & set(data["request"])
    assert "user" not in data
    assert "request" not in data["contexts"]
    assert "breadcrumbs" not in data
    assert "extra" not in data
