"""Authenticated route dispatch matrix for Prepza.

The baseline route smoke test probes the application without a session. This
matrix repeats every GET/HEAD application route with real QA student/admin
sessions so authentication-dependent code paths are exercised as well.
"""

from __future__ import annotations

import re

from test_local_qa_real_world import _client_for, qa_database, world

from app import app


EXPECTED_CONFIGURATION_503 = {
    "/auth/google",
    "/push/vapid-public-key",
    "/internal/control/v1/health",
    "/internal/control/v1/status",
    "/internal/control/v1/system/overview",
    "/internal/control/v1/users/1/summary",
    "/internal/control/v1/documents/1/summary",
    "/internal/control/v1/documents/1/materials",
}


def _probe_path(rule):
    path = rule.rule
    for name, converter in rule._converters.items():
        token = re.compile(r"<[^>]*:" + re.escape(name) + r">")
        converter_name = converter.__class__.__name__
        if converter_name == "IntegerConverter":
            replacement = "1"
        elif converter_name == "UUIDConverter":
            replacement = "00000000-0000-0000-0000-000000000001"
        elif converter_name == "FloatConverter":
            replacement = "1.0"
        else:
            replacement = "qa"
        path = token.sub(replacement, path)
    return path


def _unexpected_5xx(response, path):
    if response.status_code < 500:
        return False
    return not (
        response.status_code == 503
        and path in EXPECTED_CONFIGURATION_503
    )


def test_every_get_route_dispatches_for_authenticated_student_and_admin(world):
    """Authenticated GET/HEAD paths must not unexpectedly crash."""
    helpers = __import__(
        "test_local_qa_real_world",
        fromlist=["_client_for"],
    )
    student = helpers._client_for(world["student_a"].id)
    admin = helpers._client_for(world["admin"].id)

    failures = []
    clients = (
        ("student", student),
        ("admin", admin),
    )

    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue

        path = _probe_path(rule)

        for role, client in clients:
            if "GET" in rule.methods:
                response = client.get(path, follow_redirects=False)
                if _unexpected_5xx(response, path):
                    failures.append(
                        f"{role} GET {path} ({rule.endpoint}) -> "
                        f"{response.status_code}"
                    )

            if "HEAD" in rule.methods:
                response = client.head(path, follow_redirects=False)
                if _unexpected_5xx(response, path):
                    failures.append(
                        f"{role} HEAD {path} ({rule.endpoint}) -> "
                        f"{response.status_code}"
                    )

    assert not failures, "\n".join(failures)
