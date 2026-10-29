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



def test_http_alert_is_logged_automatically_when_threshold_is_crossed(caplog):
    import json
    import logging
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
    assert "private" not in caplog.text
    assert "synthetic" not in caplog.text
    engine.dispose()
