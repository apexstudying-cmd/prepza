"""
Authentication/authorization regression tests for the Prepza production-readiness gate.

These tests deliberately attack the server-side boundaries with different users:
- horizontal tenant isolation (organisation A vs organisation B)
- vertical privilege isolation (student vs admin)
- session invalidation after logout/session-version rotation
- suspended-account fail-closed behavior
- CSRF protection on state-changing organisation actions

They reuse the disposable QA world from test_local_qa_real_world.py.
"""

from datetime import datetime, timedelta

from sqlalchemy import text

from app import db, Organisation, OrganisationMember, Opportunity, User, app
from tests.test_local_qa_real_world import _client_for, _csrf, _future_payload


def _create_second_organisation(world):
    now = datetime.utcnow()
    second = Organisation(
        name="QA Organisation B",
        description="Second disposable tenant for horizontal authorization tests",
        contact_email="qa.organisation.b@test.invalid",
        verification_status="pending",
        is_active=True,
        created_by=world["student_b"].id,
        created_at=now,
        updated_at=now,
    )
    db.session.add(second)
    db.session.flush()

    db.session.add(
        OrganisationMember(
            organisation_id=second.id,
            user_id=world["student_b"].id,
            role="owner",
        )
    )
    db.session.commit()
    return second


def test_student_cannot_cross_organisation_boundary(world):
    """A logged-in student cannot use another tenant's numeric IDs as an IDOR."""
    org_a = world["organisation"]
    org_b = _create_second_organisation(world)

    owner_b = _client_for(world["student_b"].id)
    outsider_a = _client_for(world["student_a"].id)

    created_b = owner_b.post(
        f"/organisations/{org_b.id}/opportunities",
        json={**_future_payload(), "title": "QA Tenant B Opportunity"},
        headers=_csrf(world["student_b"].id),
    )
    assert created_b.status_code == 201
    opportunity_b_id = created_b.get_json()["id"]

    # User A must not create or mutate resources inside organisation B.
    create_cross_tenant = outsider_a.post(
        f"/organisations/{org_b.id}/opportunities",
        json={**_future_payload(), "title": "ILLEGAL CROSS TENANT"},
        headers=_csrf(world["student_a"].id),
    )
    assert create_cross_tenant.status_code in {403, 404}

    targeting_cross_tenant = outsider_a.patch(
        f"/organisations/{org_b.id}/opportunities/{opportunity_b_id}/targeting",
        json={
            "university_ids": [world["university_a"].id],
            "program_ids": [world["program_a"].id],
            "years": [2],
            "semesters": [1],
        },
        headers=_csrf(world["student_a"].id),
    )
    assert targeting_cross_tenant.status_code in {403, 404}

    submit_cross_tenant = outsider_a.post(
        f"/organisations/{org_b.id}/opportunities/{opportunity_b_id}/submit",
        headers=_csrf(world["student_a"].id),
    )
    assert submit_cross_tenant.status_code in {403, 404}

    # The legitimate tenant owner still owns the object after the failed probes.
    owner_detail = owner_b.get(f"/organisations/{org_b.id}/opportunities")
    assert owner_detail.status_code == 200
    assert any(
        row["id"] == opportunity_b_id
        for row in owner_detail.get_json()["opportunities"]
    )

    # Keep the test explicit about the two different tenant IDs; otherwise a
    # fixture bug could make a false-positive authorization test.
    assert org_a.id != org_b.id


def test_student_cannot_cross_vertical_admin_boundary(world):
    """A normal student cannot reach privileged administrative mutations."""
    student = _client_for(world["student_a"].id)

    checks = [
        ("GET", "/admin/opportunities"),
        ("GET", "/admin/content"),
        ("GET", "/admin/users"),
        ("GET", "/admin/analytics"),
        ("GET", "/admin/auth/otp"),
    ]

    for method, path in checks:
        response = student.open(path, method=method)
        assert response.status_code in {401, 403}, (method, path, response.status_code)

    # A privileged mutation must also fail, not merely the admin dashboards.
    response = student.post(
        f"/admin/organisations/{world['organisation'].id}/verify",
        headers=_csrf(world["student_a"].id),
    )
    assert response.status_code in {401, 403}


def test_logout_and_session_version_rotation_invalidate_old_session(world):
    """Both explicit logout and server-side session rotation must fail closed."""
    client = _client_for(world["student_a"].id)

    assert client.get("/me").status_code == 200

    logged_out = client.post("/logout")
    assert logged_out.status_code == 200
    assert client.get("/me").status_code == 401

    # A fresh session for the same account is valid before rotation.
    fresh = _client_for(world["student_a"].id)
    assert fresh.get("/me").status_code == 200

    user = db.session.get(User, world["student_a"].id)
    old_version = user.session_version
    user.session_version = old_version + 1
    db.session.commit()

    # The old cookie contains the previous version and must no longer
    # authenticate even though the account itself remains active.
    assert fresh.get("/me").status_code == 401

    # A newly established session using the current version remains valid.
    current = _client_for(world["student_a"].id)
    assert current.get("/me").status_code == 200


def test_suspended_account_cannot_continue_using_existing_session(world):
    """Suspension must revoke access at the server boundary, not just the UI."""
    client = _client_for(world["student_a"].id)
    assert client.get("/me").status_code == 200

    user = db.session.get(User, world["student_a"].id)
    user.is_suspended = True
    db.session.commit()

    assert client.get("/me").status_code == 401

    # Restore fixture state for any later tests that reuse the module world.
    user.is_suspended = False
    db.session.commit()


def test_state_changing_organisation_actions_require_csrf(world):
    """Authentication alone is not enough for browser state-changing requests."""
    owner = _client_for(world["student_a"].id)
    org_id = world["organisation"].id

    response = owner.post(
        f"/organisations/{org_id}/opportunities",
        json=_future_payload(),
    )
    assert response.status_code == 403

    # A valid CSRF token from another user must not be accepted either.
    foreign_token = owner.post(
        f"/organisations/{org_id}/opportunities",
        json={**_future_payload(), "title": "FOREIGN CSRF TOKEN"},
        headers=_csrf(world["student_b"].id),
    )
    assert foreign_token.status_code == 403
