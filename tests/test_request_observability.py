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


def test_http_middleware_adds_correlation_header_without_logging_private_url_data(caplog):
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
        response = client.get("/health/123?secret=DO_NOT_LOG", headers={"X-Request-ID": "safe-request-id-1234"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "safe-request-id-1234"
    assert "DO_NOT_LOG" not in caplog.text
    assert "123?secret" not in caplog.text
    assert "safe-request-id-1234" in caplog.text
    engine.dispose()


def test_invalid_client_request_id_is_replaced():
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
