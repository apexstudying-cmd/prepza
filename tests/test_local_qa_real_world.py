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
import re
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

    # A duplicate Flask rule for the same student-facing path is dangerous:
    # dispatch uses the first matching rule, so an older implementation can
    # silently bypass the reconciled targeting/security behavior.
    for path in (
        "/opportunities",
        "/opportunities/<int:opportunity_id>",
        "/opportunities/<int:opportunity_id>/save",
        "/opportunities/saved",
    ):
        matching = [
            rule.endpoint
            for rule in app.url_map.iter_rules()
            if rule.rule == path
            and "GET" in rule.methods
            if path != "/opportunities/<int:opportunity_id>/save"
        ] if path != "/opportunities/<int:opportunity_id>/save" else [
            rule.endpoint
            for rule in app.url_map.iter_rules()
            if rule.rule == path and "POST" in rule.methods
        ]
        assert len(matching) == 1, f"Duplicate student Opportunity route: {path} -> {matching}"


def test_no_duplicate_registered_route_methods():
    duplicates = {}
    for rule in app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            duplicates.setdefault((rule.rule, method), []).append(rule.endpoint)

    duplicates = {
        key: endpoints
        for key, endpoints in duplicates.items()
        if len(set(endpoints)) > 1
    }
    assert not duplicates, f"Duplicate route/method registrations: {duplicates}"


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

    approved = admin.post(
        f"/admin/opportunities/{opportunity_id}/approve",
        headers=_csrf(world["admin"].id),
    )
    assert approved.status_code == 200
    assert approved.get_json()["status"] == "approved"

    published = admin.post(
        f"/admin/opportunities/{opportunity_id}/publish",
        headers=_csrf(world["admin"].id),
    )
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


def _create_published_targeted_opportunity(world, *, title, university_ids=None, program_ids=None, years=None, semesters=None):
    now = datetime.utcnow()
    opportunity = Opportunity(
        organisation_id=world["organisation"].id,
        created_by=world["student_a"].id,
        title=title,
        description="Disposable targeting-matrix opportunity.",
        opportunity_type="internship",
        location="Nairobi",
        is_remote=False,
        application_url="https://example.invalid/matrix",
        application_instructions="QA",
        application_deadline=now + timedelta(days=5),
        expiry_date=now + timedelta(days=20),
        status="published",
        published_at=now,
        view_count=0,
    )
    db.session.add(opportunity)
    db.session.flush()

    (
        OpportunityUniversityTarget,
        OpportunityProgramTarget,
        OpportunityYearTarget,
        OpportunitySemesterTarget,
        _SavedOpportunity,
    ) = app.opportunity_targeting_models

    for university_id in university_ids or []:
        db.session.add(OpportunityUniversityTarget(
            opportunity_id=opportunity.id,
            university_id=university_id,
        ))
    for program_id in program_ids or []:
        db.session.add(OpportunityProgramTarget(
            opportunity_id=opportunity.id,
            program_id=program_id,
        ))
    for year in years or []:
        db.session.add(OpportunityYearTarget(
            opportunity_id=opportunity.id,
            year=year,
        ))
    for semester in semesters or []:
        db.session.add(OpportunitySemesterTarget(
            opportunity_id=opportunity.id,
            semester=semester,
        ))
    db.session.commit()
    return opportunity.id



def test_organisation_can_create_multiple_opportunities_under_live_rate_limit(world):
    """A legitimate organisation can create several postings without hitting the global limit."""
    owner = _client_for(world["student_a"].id)
    org_id = world["organisation"].id

    created_ids = []
    for index in range(5):
        response = owner.post(
            f"/organisations/{org_id}/opportunities",
            json={**_future_payload(), "title": f"QA Rate Limit Opportunity {index}"},
            headers=_csrf(world["student_a"].id),
        )
        assert response.status_code == 201, response.get_json()
        created_ids.append(response.get_json()["id"])

    assert len(set(created_ids)) == 5


def test_opportunity_targeting_matrix_and_current_profile_changes(world):
    # The matrix deliberately uses different values for each dimension so a
    # failure cannot be hidden by two students coincidentally sharing a value.
    university_a = world["university_a"]
    university_b = world["university_b"]
    program_a = world["program_a"]
    program_b = world["program_b"]

    program_c = Program(
        university_id=university_a.id,
        name="QA Information Technology",
        degree_level="Bachelors",
        discipline_category="Computing",
        is_active=True,
    )
    db.session.add(program_c)
    db.session.flush()

    student_c = User(
        email="qa.student.c@test.invalid",
        password_hash=generate_password_hash("Qa!Password123"),
        year=3,
        semester=1,
        display_name="qa.student.c",
        email_verified=True,
        is_suspended=False,
        profile_visibility="public",
        who_can_message="everyone",
        who_can_follow="everyone",
        read_receipts_enabled=True,
        university_id=university_a.id,
        program_id=program_a.id,
        session_version=0,
    )
    student_d = User(
        email="qa.student.d@test.invalid",
        password_hash=generate_password_hash("Qa!Password123"),
        year=2,
        semester=2,
        display_name="qa.student.d",
        email_verified=True,
        is_suspended=False,
        profile_visibility="public",
        who_can_message="everyone",
        who_can_follow="everyone",
        read_receipts_enabled=True,
        university_id=university_a.id,
        program_id=program_c.id,
        session_version=0,
    )
    db.session.add_all([student_c, student_d])
    db.session.commit()

    clients = {
        "A": _client_for(world["student_a"].id),
        "B": _client_for(world["student_b"].id),
        "C": _client_for(student_c.id),
        "D": _client_for(student_d.id),
    }
    ids = {
        "A": world["student_a"].id,
        "B": world["student_b"].id,
        "C": student_c.id,
        "D": student_d.id,
    }

    # The organisation is verified by the lifecycle test immediately above.
    # Keep this assertion explicit so the matrix never silently tests an
    # unavailable organisation.
    organisation = db.session.get(Organisation, world["organisation"].id)
    assert organisation.verification_status == "verified"

    cases = [
        ("none", {}, {"A", "B", "C", "D"}),
        ("university", {"university_ids": [university_a.id]}, {"A", "C", "D"}),
        ("program", {"program_ids": [program_a.id]}, {"A", "C"}),
        ("year", {"years": [2]}, {"A", "B", "D"}),
        ("semester", {"semesters": [1]}, {"A", "B", "C"}),
        ("university_program", {"university_ids": [university_a.id], "program_ids": [program_a.id]}, {"A", "C"}),
        ("university_year", {"university_ids": [university_a.id], "years": [2]}, {"A", "D"}),
        ("university_semester", {"university_ids": [university_a.id], "semesters": [1]}, {"A", "C"}),
        ("program_year", {"program_ids": [program_a.id], "years": [2]}, {"A"}),
        ("program_semester", {"program_ids": [program_a.id], "semesters": [1]}, {"A", "C"}),
        ("year_semester", {"years": [2], "semesters": [1]}, {"A", "B"}),
        ("all_four", {
            "university_ids": [university_a.id],
            "program_ids": [program_a.id],
            "years": [2],
            "semesters": [1],
        }, {"A"}),
        ("multiple_values", {
            "university_ids": [university_a.id, university_b.id],
            "program_ids": [program_a.id, program_b.id],
            "years": [2, 3],
            "semesters": [1, 2],
        }, {"A", "B", "C"}),
    ]

    from opportunity_runtime import visible_query

    for name, targeting, expected in cases:
        opportunity_id = _create_published_targeted_opportunity(
            world,
            title=f"QA Target Matrix {name}",
            **targeting,
        )
        for student_name, student_id in ids.items():
            student = db.session.get(User, student_id)
            visible_ids = {
                opportunity.id
                for opportunity in visible_query(student).all()
            }
            assert (opportunity_id in visible_ids) == (student_name in expected), (
                name,
                student_name,
                expected,
                visible_ids,
            )

    # Current-profile changes must immediately change eligibility. The same
    # student changes program repeatedly, not just once.
    profile_client = clients["A"]
    student_a_id = world["student_a"].id

    program_target_id = _create_published_targeted_opportunity(
        world,
        title="QA Program Change Target",
        program_ids=[program_a.id],
    )

    def visible_for_profile_target():
        response = profile_client.get("/opportunities")
        assert response.status_code == 200
        return program_target_id in {
            row["id"] for row in response.get_json()["opportunities"]
        }

    assert visible_for_profile_target()

    changed = profile_client.patch(
        "/profile",
        json={"program_id": program_c.id},
        headers=_csrf(student_a_id),
    )
    assert changed.status_code == 200
    assert changed.get_json()["program_id"] == program_c.id
    assert not visible_for_profile_target()

    changed_back = profile_client.patch(
        "/profile",
        json={"program_id": program_a.id},
        headers=_csrf(student_a_id),
    )
    assert changed_back.status_code == 200
    assert changed_back.get_json()["program_id"] == program_a.id
    assert visible_for_profile_target()

    # Changing university without supplying a new program must clear the old
    # program rather than leaving an impossible University B + Program A pair.
    university_changed = profile_client.patch(
        "/profile",
        json={"university_id": university_b.id},
        headers=_csrf(student_a_id),
    )
    assert university_changed.status_code == 200
    assert university_changed.get_json()["university_id"] == university_b.id
    assert university_changed.get_json()["program_id"] is None

    stored = db.session.get(User, student_a_id)
    assert stored.university_id == university_b.id
    assert stored.program_id is None

    # Repeatedly changing to a new university + program remains valid.
    university_and_program_changed = profile_client.patch(
        "/profile",
        json={
            "university_id": university_a.id,
            "program_id": program_c.id,
        },
        headers=_csrf(student_a_id),
    )
    assert university_and_program_changed.status_code == 200
    assert university_and_program_changed.get_json()["program_id"] == program_c.id

    changed_again = profile_client.patch(
        "/profile",
        json={"program_id": program_a.id},
        headers=_csrf(student_a_id),
    )
    assert changed_again.status_code == 200
    assert changed_again.get_json()["program_id"] == program_a.id

    invalid_cross_university_program = profile_client.patch(
        "/profile",
        json={
            "university_id": university_a.id,
            "program_id": program_b.id,
        },
        headers=_csrf(student_a_id),
    )
    assert invalid_cross_university_program.status_code == 400

    final = db.session.get(User, student_a_id)
    assert final.university_id == university_a.id
    assert final.program_id == program_a.id


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


def _safe_probe_path(rule):
    """Build a non-mutating probe URL for a Flask rule."""
    path = rule.rule
    for name, converter in rule._converters.items():
        token = re.compile(r"<[^>]*:" + re.escape(name) + r">")
        if converter.__class__.__name__ == "IntegerConverter":
            replacement = "1"
        elif converter.__class__.__name__ == "UUIDConverter":
            replacement = "00000000-0000-0000-0000-000000000001"
        elif converter.__class__.__name__ == "FloatConverter":
            replacement = "1.0"
        else:
            replacement = "qa"
        path = token.sub(replacement, path)
    return path


def test_every_registered_route_dispatches_without_server_error():
    """Smoke-test the full runtime route surface without mutating app state.

    OPTIONS verifies Flask registration for every application route. GET/HEAD
    probes are attempted only where the route declares them. A non-2xx status
    is not inherently a failure here because authentication, missing records,
    validation, redirects, and other legitimate boundaries can reject a
    probe.

    Some routes intentionally return 503 when an optional production
    integration is not configured in the disposable QA environment. Those
    explicit configuration gates are allowed; unexpected 5xx responses still
    fail the audit.
    """
    client = app.test_client()
    failures = []
    expected_configuration_503 = {
        "/auth/google",
        "/push/vapid-public-key",
        "/internal/control/v1/health",
        "/internal/control/v1/status",
        "/internal/control/v1/system/overview",
        "/internal/control/v1/users/1/summary",
        "/internal/control/v1/documents/1/summary",
        "/internal/control/v1/documents/1/materials",
    }

    def _unexpected_server_error(response, path):
        if response.status_code < 500:
            return False
        if response.status_code == 503 and path in expected_configuration_503:
            return False
        return True

    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue

        path = _safe_probe_path(rule)

        try:
            options = client.options(path)
            if _unexpected_server_error(options, path):
                failures.append(
                    f"OPTIONS {path} -> {options.status_code}"
                )

            if "GET" in rule.methods:
                response = client.get(path, follow_redirects=False)
                if _unexpected_server_error(response, path):
                    failures.append(
                        f"GET {path} ({rule.endpoint}) -> {response.status_code}"
                    )

            if "HEAD" in rule.methods:
                response = client.head(path, follow_redirects=False)
                if _unexpected_server_error(response, path):
                    failures.append(
                        f"HEAD {path} ({rule.endpoint}) -> {response.status_code}"
                    )
        except Exception as exc:
            failures.append(
                f"{rule.endpoint} {path}: {type(exc).__name__}: {exc}"
            )

    assert not failures, (
        "Registered route smoke probes reached an unexpected server error or raised: "
        + "; ".join(failures)
    )
