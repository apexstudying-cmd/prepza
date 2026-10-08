"""Route-level security matrix for the registered Prepza Flask surface.

This layer complements the dispatch smoke test. It verifies the global admin
security contract across every registered /admin route without exercising the
protected business operation itself.

Run through tools/run_local_qa.py so the disposable-database guard remains
active.
"""

from __future__ import annotations

import re

from test_local_qa_real_world import _client_for, qa_database, world

from app import app, db, User


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


def _admin_rules():
    return [
        rule
        for rule in app.url_map.iter_rules()
        if rule.endpoint != "static" and rule.rule.startswith("/admin")
    ]


def test_every_admin_get_route_rejects_anonymous_and_non_admin_users(world):
    """Every GET /admin route must fail closed for anonymous and students."""
    anonymous = app.test_client()
    student = _client_for(world["student_a"].id)

    failures = []
    for rule in _admin_rules():
        if "GET" not in rule.methods:
            continue

        path = _probe_path(rule)
        for label, client in (("anonymous", anonymous), ("student", student)):
            response = client.get(path, follow_redirects=False)
            if response.status_code not in {401, 403}:
                failures.append(
                    f"{label} GET {path} ({rule.endpoint}) -> "
                    f"{response.status_code}, expected 401/403"
                )

    assert not failures, "\n".join(failures)


def test_every_admin_mutation_fails_without_csrf_for_all_non_admins_and_admin(
    world,
):
    """Every admin mutation must require both admin identity and CSRF."""
    anonymous = app.test_client()
    student = _client_for(world["student_a"].id)
    admin = _client_for(world["admin"].id)

    failures = []
    clients = (
        ("anonymous", anonymous),
        ("student", student),
        ("admin", admin),
    )

    for rule in _admin_rules():
        mutation_methods = sorted(
            rule.methods & {"POST", "PATCH", "PUT", "DELETE"}
        )
        if not mutation_methods:
            continue

        path = _probe_path(rule)
        for label, client in clients:
            for method in mutation_methods:
                response = client.open(
                    path,
                    method=method,
                    follow_redirects=False,
                )
                if response.status_code not in {401, 403}:
                    failures.append(
                        f"{label} {method} {path} ({rule.endpoint}) -> "
                        f"{response.status_code}, expected 401/403 without CSRF"
                    )

    assert not failures, "\n".join(failures)


def test_revoked_admin_cannot_continue_using_existing_session(world):
    """Admin authorization is re-checked against the live User row."""
    admin = _client_for(world["admin"].id)

    assert admin.get("/admin/users").status_code == 200

    user = db.session.get(User, world["admin"].id)
    user.is_admin = False
    db.session.commit()

    try:
        response = admin.get("/admin/users")
        assert response.status_code == 403
    finally:
        user.is_admin = True
        db.session.commit()
