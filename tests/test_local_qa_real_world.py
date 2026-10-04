"""
Real-world local QA scenarios for Prepza.

Run only against a disposable PostgreSQL database whose name ends in
"_test" or "_qa". The suite creates its own test world, exercises the real
Flask routes, and truncates the disposable database afterwards.

External providers (email, OpenAI, Paystack, R2, Google) are intentionally
not contacted by this first layer. Controlled-provider tests come later.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from werkzeug.security import generate_password_hash

from app import (
    app,
    db,
    Opportunity,
    Organisation,
    OrganisationMember,
    Program,
    University,
    User,
)


TEST_DB_SUFFIXES = ("_test", "_qa")


def _assert_disposable_database():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.fail("DATABASE_URL must point to the disposable QA database")

    database = make_url(url).database or ""
    if not database.endswith(TEST_DB_SUFFIXES):
        pytest.fail(
            f"Refusing to run QA tests against database '{database}'. "
            "Use a database ending in _test or _qa."
        )


def _reset_database():
    inspector = inspect(db.engine)
    tables = [
        name
        for name in inspector.get_table_names(schema="public")
        if name != "alembic_version"
    ]
    if not tables:
        return

    quoted = ", ".join(
        'public."' + name.replace('"', '""') + '"'
        for name in tables
    )
    db.session.execute(
        text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")
    )
    db.session.commit()
    db.session.remove()


@pytest.fixture(scope="module", autouse=True)
def qa_database():
    _assert_disposable_database()

    required_tables = {
        "user",
        "university",
        "program",
        "organisation",
        "organisation_member",
        "opportunity",
        "opportunity_university_target",
        "opportunity_program_target",
        "opportunity_year_target",
        "opportunity_semester_target",
        "saved_opportunity",
    }
    with app.app_context():
        actual = set(inspect(db.engine).get_table_names(schema="public"))
        missing = sorted(required_tables - actual)
        if missing:
            pytest.fail(f"QA database is missing required tables: {missing}")

        app.config.update(
            TESTING=True,
            SESSION_COOKIE_SECURE=False,
            PROPAGATE_EXCEPTIONS=True,
        )

        _reset_database()
        try:
            yield
        finally:
            db.session.remove()
            _reset_database()
            db.engine.dispose()


@pytest.fixture(scope="module")
def world(qa_database):
    now = datetime.utcnow()

    university_a = University(
        name="QA University A",
        short_code="QA-U-A",
        country="Kenya",
        is_active=True,
    )
    university_b = University(
        name="QA University B",
        short_code="QA-U-B",
        country="Kenya",
        is_active=True,
    )
    db.session.add_all([university_a, university_b])
    db.session.flush()

    program_a = Program(
        university_id=university_a.id,
        name="QA Computer Science",
        degree_level="Bachelors",
        discipline_category="Computing",
        is_active=True,
    )
    program_b = Program(
        university_id=university_b.id,
        name="QA Business Administration",
        degree_level="Bachelors",
        discipline_category="Business",
        is_active=True,
    )
    db.session.add_all([program_a, program_b])
    db.session.flush()

    def build_user(
        email: str,
        *,
        admin: bool = False,
        university_id=None,
        program_id=None,
    ):
        return User(
            email=email,
            password_hash=generate_password_hash("Qa!Password123"),
            year=2,
            semester=1,
            display_name=email.split("@")[0],
            email_verified=True,
            is_admin=admin,
            is_suspended=False,
            profile_visibility="public",
            who_can_message="everyone",
            who_can_follow="everyone",
            read_receipts_enabled=True,
            university_id=university_id,
            program_id=program_id,
            session_version=0,
        )

    student_a = build_user(
        "qa.student.a@test.invalid",
        university_id=university_a.id,
        program_id=program_a.id,
    )
    student_b = build_user(
        "qa.student.b@test.invalid",
        university_id=university_b.id,
        program_id=program_b.id,
    )
    admin = build_user(
        "qa.admin@test.invalid",
        admin=True,
        university_id=university_a.id,
        program_id=program_a.id,
    )

    db.session.add_all([student_a, student_b, admin])
    db.session.flush()

    organisation = Organisation(
        name="QA Organisation",
        description="Disposable local QA organisation",
        contact_email="qa.organisation@test.invalid",
        verification_status="pending",
        is_active=True,
        created_by=student_a.id,
        created_at=now,
        updated_at=now,
    )
    db.session.add(organisation)
    db.session.flush()

    membership = OrganisationMember(
        organisation_id=organisation.id,
        user_id=student_a.id,
        role="owner",
    )
    db.session.add(membership)
    db.session.commit()

    return {
        "university_a": university_a,
        "university_b": university_b,
        "program_a": program_a,
        "program_b": program_b,
        "student_a": student_a,
        "student_b": student_b,
        "admin": admin,
        "organisation": organisation,
    }


def _client_for(user_id: int):
    client = app.test_client()
    user = db.session.get(User, user_id)
    if not user:
        raise AssertionError(f"Test user {user_id} does not exist")

    with client.session_transaction() as session:
        session["user_id"] = user.id
        session["_session_version"] = user.session_version
        session["csrf_token"] = f"qa-csrf-{user.id}"

    return client


def _csrf(user_id: int):
    return {"X-CSRF-Token": f"qa-csrf-{user_id}"}


def _future_payload():
    deadline = (datetime.utcnow() + timedelta(days=7)).replace(microsecond=0)
    expiry = (deadline + timedelta(days=30)).replace(microsecond=0)
    return {
        "title": "QA Internship",
        "description": "Disposable opportunity used by the local QA lab.",
        "opportunity_type": "internship",
        "location": "Nairobi",
        "is_remote": False,
        "application_url": "https://example.invalid/qa",
        "application_instructions": "This is a test opportunity.",
        "application_deadline": deadline.isoformat(),
        "expiry_date": expiry.isoformat(),
    }


def test_route_inventory_contains_critical_boundaries():
    routes = {
        (rule.rule, method)
        for rule in app.url_map.iter_rules()
        for method in rule.methods
        if method not in {"HEAD", "OPTIONS"}
    }

    expected = {
        ("/health", "GET"),
        ("/me", "GET"),
        ("/groups", "POST"),
        ("/groups", "GET"),
        ("/chats", "GET"),
        ("/opportunities", "GET"),
        ("/admin/opportunities", "GET"),
        ("/organisations/<int:organisation_id>/opportunities", "POST"),
        (
            "/organisations/<int:organisation_id>/opportunities/"
            "<int:opportunity_id>/submit",
            "POST",
        ),
    }

    missing = sorted(expected - routes)
    assert not missing, f"Critical registered routes are missing: {missing}"


def test_public_and_authenticated_session_boundaries(world):
    anonymous = app.test_client()

    health = anonymous.get("/health")
    assert health.status_code == 200

    me_anonymous = anonymous.get("/me")
    assert me_anonymous.status_code == 401

    client = _client_for(world["student_a"].id)
    me = client.get("/me")
    assert me.status_code == 200
    assert me.get_json()["id"] == world["student_a"].id

    logout = client.post("/logout")
    assert logout.status_code == 200
    assert client.get("/me").status_code == 401


def test_university_and_program_lookup_are_real_routes(world):
    client = app.test_client()

    universities = client.get("/universities")
    assert universities.status_code == 200

    programs = client.get(
        f"/universities/{world['university_a'].id}/programs"
    )
    assert programs.status_code == 200
    assert any(row["id"] == world["program_a"].id for row in programs.get_json())


def test_group_creation_is_end_to_end(world):
    client = _client_for(world["student_a"].id)

    response = client.post(
        "/groups",
        json={
            "name": "QA Study Group",
            "description": "Disposable integration-test group",
            "privacy": "public",
            "university_id": world["university_a"].id,
            "program_id": world["program_a"].id,
            "year": 2,
        },
        headers=_csrf(world["student_a"].id),
    )

    assert response.status_code == 201
    group_id = response.get_json()["id"]

    listed = client.get("/groups")
    assert listed.status_code == 200
    assert any(row["id"] == group_id for row in listed.get_json()["groups"])

    detail = client.get(f"/groups/{group_id}")
    assert detail.status_code == 200


def test_organisation_opportunity_lifecycle_and_targeting(world):
    owner = _client_for(world["student_a"].id)
    admin = _client_for(world["admin"].id)
    outsider = _client_for(world["student_b"].id)

    org_id = world["organisation"].id

    created = owner.post(
        f"/organisations/{org_id}/opportunities",
        json=_future_payload(),
        headers=_csrf(world["student_a"].id),
    )
    assert created.status_code == 201
    opportunity_id = created.get_json()["id"]
    assert created.get_json()["status"] == "draft"

    targeted = owner.patch(
        f"/organisations/{org_id}/opportunities/"
        f"{opportunity_id}/targeting",
        json={
            "university_ids": [world["university_a"].id],
            "program_ids": [world["program_a"].id],
            "years": [2],
            "semesters": [1],
        },
        headers=_csrf(world["student_a"].id),
    )
    assert targeted.status_code == 200
    assert targeted.get_json()["targeting"]["years"] == [2]

    blocked = owner.post(
        f"/organisations/{org_id}/opportunities/{opportunity_id}/submit",
        headers=_csrf(world["student_a"].id),
    )
    assert blocked.status_code == 400

    forbidden_verify = outsider.post(
        f"/admin/organisations/{org_id}/verify"
    )
    assert forbidden_verify.status_code == 403

    verified = admin.post(
        f"/admin/organisations/{org_id}/verify",
        headers=_csrf(world["admin"].id),
    )
    assert verified.status_code == 200
    assert verified.get_json()["verification_status"] == "verified"

    submitted = owner.post(
        f"/organisations/{org_id}/opportunities/{opportunity_id}/submit",
        headers=_csrf(world["student_a"].id),
    )
    assert submitted.status_code == 200
    assert submitted.get_json()["status"] == "pending_review"

    forbidden_queue = outsider.get("/admin/opportunities")
    assert forbidden_queue.status_code == 403

    queue = admin.get("/admin/opportunities")
    assert queue.status_code == 200
    assert any(
        row["id"] == opportunity_id
        for row in queue.get_json()["opportunities"]
    )

    approved = admin.post(\n        f"/admin/opportunities/{opportunity_id}/approve",\n        headers=_csrf(world["admin"].id),\n    )
    assert approved.status_code == 200
    assert approved.get_json()["status"] == "approved"

    published = admin.post(f"/admin/opportunities/{opportunity_id}/publish")
    assert published.status_code == 200
    assert published.get_json()["status"] == "published"

    visible = owner.get("/opportunities")
    assert visible.status_code == 200
    assert any(
        row["id"] == opportunity_id
        for row in visible.get_json()["opportunities"]
    )

    detail = owner.get(f"/opportunities/{opportunity_id}")
    assert detail.status_code == 200

    hidden = outsider.get("/opportunities")
    assert hidden.status_code == 200
    assert not any(
        row["id"] == opportunity_id
        for row in hidden.get_json()["opportunities"]
    )

    hidden_detail = outsider.get(f"/opportunities/{opportunity_id}")
    assert hidden_detail.status_code == 404


def test_csrf_and_session_version_fail_closed(world):
    client = _client_for(world["student_a"].id)

    missing_csrf = client.post(
        "/groups",
        json={"name": "Should Fail", "privacy": "public"},
    )
    assert missing_csrf.status_code == 403

    user = db.session.get(User, world["student_a"].id)
    user.session_version += 1
    db.session.commit()

    assert client.get("/me").status_code == 401


def test_duplicate_opportunity_save_is_race_safe(world):
    (
        OpportunityUniversityTarget,
        OpportunityProgramTarget,
        OpportunityYearTarget,
        OpportunitySemesterTarget,
        SavedOpportunity,
    ) = app.opportunity_targeting_models

    now = datetime.utcnow()
    opportunity = Opportunity(
        organisation_id=world["organisation"].id,
        created_by=world["student_a"].id,
        title="QA Concurrent Save Opportunity",
        description="Concurrency test",
        opportunity_type="internship",
        location="Nairobi",
        is_remote=False,
        application_url="https://example.invalid/concurrency",
        application_instructions="QA",
        application_deadline=now + timedelta(days=5),
        expiry_date=now + timedelta(days=20),
        status="published",
        published_at=now,
        view_count=0,
    )
    db.session.add(opportunity)
    db.session.flush()

    db.session.add_all([
        OpportunityUniversityTarget(
            opportunity_id=opportunity.id,
            university_id=world["university_a"].id,
        ),
        OpportunityProgramTarget(
            opportunity_id=opportunity.id,
            program_id=world["program_a"].id,
        ),
        OpportunityYearTarget(opportunity_id=opportunity.id, year=2),
        OpportunitySemesterTarget(opportunity_id=opportunity.id, semester=1),
    ])
    db.session.commit()

    student_id = world["student_a"].id
    opportunity_id = opportunity.id

    def save_once():
        from app import db as thread_db

        with app.app_context():
            try:
                client = _client_for(student_id)
                response = client.post(
                    f"/opportunities/{opportunity_id}/save",
                    headers=_csrf(student_id),
                )
                return response.status_code
            finally:
                thread_db.session.remove()

    statuses = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(save_once) for _ in range(10)]
        for future in as_completed(futures):
            statuses.append(future.result())

    assert all(status == 200 for status in statuses), statuses

    db.session.expire_all()
    saved_count = SavedOpportunity.query.filter_by(
        user_id=student_id,
        opportunity_id=opportunity_id,
    ).count()
    assert saved_count == 1


def test_concurrent_organisation_reads(world):
    url = f"/organisations/{world['organisation'].id}/opportunities"
    student_id = world["student_a"].id

    def read_once():
        from app import db as thread_db

        with app.app_context():
            try:
                client = _client_for(student_id)
                response = client.get(url)
                return response.status_code
            finally:
                thread_db.session.remove()

    statuses = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(read_once) for _ in range(20)]
        for future in as_completed(futures):
            statuses.append(future.result())

    assert statuses == [200] * 20
