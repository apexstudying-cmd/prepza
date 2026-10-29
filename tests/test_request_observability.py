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
