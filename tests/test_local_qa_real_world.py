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
import json
import hashlib
import hmac
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
            # Route/semantic matrices may intentionally issue hundreds of
            # requests. Disable the production limiter for those tests so
            # rate limiting does not mask application behavior. A dedicated
            # test below explicitly re-enables it for the real contract.
            RATELIMIT_ENABLED=False,
        )

        _reset_database()

        # The production app seeds the canonical Free/Plus/Pro AI economics
        # rows during register_ai_economics(). This QA fixture truncates every
        # table after application startup, so re-run that same initialization
        # after the reset. Otherwise authenticated routes such as
        # /api/usage/me would see a real empty-plan state that cannot occur on
        # a freshly initialized production database.
        from ai_economics import ensure_economics_schema

        ensure_economics_schema(db)

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
    """A legitimate organisation can create several postings under the live default limit."""
    owner = _client_for(world["student_a"].id)
    org_id = world["organisation"].id
    previous = app.config.get("RATELIMIT_ENABLED", True)
    app.config["RATELIMIT_ENABLED"] = True
    try:
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
    finally:
        app.config["RATELIMIT_ENABLED"] = previous


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

    for name, targeting, expected in cases:
        opportunity_id = _create_published_targeted_opportunity(
            world,
            title=f"QA Target Matrix {name}",
            **targeting,
        )
        for student_name, student_id in ids.items():
            response = clients[student_name].get(
                "/opportunities",
                query_string={"q": f"QA Target Matrix {name}"},
            )
            assert response.status_code == 200, (name, student_name, response.status_code)
            visible_ids = {
                row["id"] for row in response.get_json()["opportunities"]
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



def test_student_economics_entitlement_lifecycle_and_quota_truth(world):
    """Exercise the real paid/free entitlement boundary and quota ledger."""
    from ai_economics import (
        get_active_entitlements,
        get_user_plan_code,
    )
    from usage_billing import check_and_consume_ai_quota

    user = User(
        email="qa.economics@test.invalid",
        password_hash=generate_password_hash("Qa!Password123"),
        year=2,
        semester=1,
        display_name="qa.economics",
        email_verified=True,
        is_suspended=False,
        profile_visibility="public",
        who_can_message="everyone",
        who_can_follow="everyone",
        read_receipts_enabled=True,
        university_id=world["university_a"].id,
        program_id=world["program_a"].id,
        session_version=0,
    )
    db.session.add(user)
    db.session.flush()

    now = datetime.utcnow()
    helpers = app.extensions["prepza_student_orders"]

    def add_subscription(plan, amount, starts_at, expires_at, *, fulfill=True):
        payment = __import__("app").Payment(
            user_id=user.id,
            content_item_id=None,
            amount=amount,
            provider="paystack",
            reference=f"qa-econ-{plan}-{payment_counter[0]}",
            provider_reference=f"qa-provider-{payment_counter[0]}",
            payment_type="subscription",
            plan=plan,
            status="success",
            subscription_starts_at=starts_at,
            subscription_expires_at=expires_at,
        )
        payment_counter[0] += 1
        db.session.add(payment)
        db.session.flush()
        helpers["create"](
            payment,
            item_title=("Plus Plan" if plan == "plus" else "Pro Plan"),
            requested_payload={"payment_type": "subscription", "plan": plan, "quantity": 1},
        )
        if fulfill:
            assert helpers["mark_paid_and_fulfilled"](payment)
        db.session.commit()
        return payment

    payment_counter = [1]

    # Money marked successful is not enough: without a fulfilled order there
    # is deliberately no paid entitlement.
    add_subscription(
        "plus", 499, now - timedelta(hours=1), now + timedelta(days=29), fulfill=False
    )
    assert get_user_plan_code(db, user.id) == "free"
    assert get_active_entitlements(db, user.id) == []

    # Once the exact order is fulfilled, Plus becomes active.
    payment = db.session.execute(
        text("SELECT * FROM payment WHERE user_id=:uid ORDER BY id DESC LIMIT 1"),
        {"uid": user.id},
    ).mappings().first()
    payment_obj = db.session.get(__import__("app").Payment, int(payment["id"]))
    assert helpers["mark_paid_and_fulfilled"](payment_obj)
    db.session.commit()

    assert get_user_plan_code(db, user.id) == "plus"
    assert len(get_active_entitlements(db, user.id)) == 1

    # Plus summary allowance is exactly 40 pages: 39 + 1 succeeds, then the
    # next page is rejected rather than allowing an over-consumption.
    ok, first = check_and_consume_ai_quota(db, user.id, "summary", 39)
    assert ok and first["remaining_units"] == 1
    ok, second = check_and_consume_ai_quota(db, user.id, "summary", 2)
    assert not ok and second["code"] == "generation_quota_exhausted"
    ok, third = check_and_consume_ai_quota(db, user.id, "summary", 1)
    assert ok and third["remaining_units"] == 0
    ok, fourth = check_and_consume_ai_quota(db, user.id, "summary", 1)
    assert not ok and fourth["code"] == "generation_quota_exhausted"

    # A paid entitlement expiring now falls back to Free immediately.
    db.session.execute(
        text("UPDATE payment SET subscription_expires_at=:expires WHERE id=:pid"),
        {"expires": now - timedelta(seconds=1), "pid": int(payment["id"])},
    )
    db.session.commit()
    assert get_user_plan_code(db, user.id) == "free"

    # A future-paid entitlement must not grant access before its start time.
    future_payment = add_subscription(
        "plus", 499, now + timedelta(days=2), now + timedelta(days=32)
    )
    assert get_user_plan_code(db, user.id) == "free"
    assert not get_active_entitlements(db, user.id)

    # Activate a Pro entitlement and prove its exact 100-page allowance.
    db.session.execute(
        text("UPDATE payment SET subscription_starts_at=:starts, subscription_expires_at=:expires WHERE id=:pid"),
        {
            "starts": now - timedelta(minutes=1),
            "expires": now + timedelta(days=29),
            "pid": future_payment.id,
        },
    )
    db.session.commit()
    assert get_user_plan_code(db, user.id) == "plus"

    pro_payment = add_subscription(
        "pro", 999, now - timedelta(seconds=30), now + timedelta(days=29)
    )
    assert get_user_plan_code(db, user.id) == "pro"

    # With Plus + Pro simultaneously active, total allowance is additive but
    # one generation can never exceed the largest single plan allowance.
    ok, stack_probe = check_and_consume_ai_quota(db, user.id, "summary", 101)
    assert not ok and stack_probe["code"] == "generation_size_limit"
    ok, stack_use = check_and_consume_ai_quota(db, user.id, "summary", 100)
    assert ok and stack_use["remaining_units"] == 40

    # The public usage endpoint must agree with the actual entitlement ledger,
    # including paid request counts.
    client = _client_for(user.id)
    usage_response = client.get("/api/usage/me")
    assert usage_response.status_code == 200
    payload = usage_response.get_json()
    assert payload["plan"] == "pro"
    assert payload["usage"]["summary"]["units"] == 100
    assert payload["usage"]["summary"]["unit_limit"] == 140
    assert payload["usage"]["summary"]["remaining_units"] == 40
    assert payload["usage"]["summary"]["requests"] == 1

    # The future entitlement remains part of the stack only when its period is
    # actually active; expiry/start boundaries are evaluated against now.
    db.session.execute(
        text("UPDATE payment SET subscription_expires_at=:expires WHERE id=:pid"),
        {"expires": now - timedelta(seconds=1), "pid": int(pro_payment.id)},
    )
    db.session.commit()
    assert get_user_plan_code(db, user.id) == "plus"


def test_paystack_checkout_uses_base_plan_price_and_provider_success_is_idempotent(world, monkeypatch):
    """Verify Paystack uses the product price, while provider fees stay outside entitlement economics."""
    import app as app_module

    from ai_economics import get_plan, get_user_plan_code

    user = User(
        email="qa.paystack@test.invalid",
        password_hash=generate_password_hash("Qa!Password123"),
        year=2,
        semester=1,
        display_name="qa.paystack",
        email_verified=True,
        is_suspended=False,
        profile_visibility="public",
        who_can_message="everyone",
        who_can_follow="everyone",
        read_receipts_enabled=True,
        university_id=world["university_a"].id,
        program_id=world["program_a"].id,
        session_version=0,
    )
    db.session.add(user)
    db.session.commit()

    calls = []

    def fake_paystack_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET" and path == "/plan/QA_PLUS":
            return {
                "status": True,
                "data": {
                    "amount": int(get_plan(db, "plus")["price_kes"]) * 100,
                    "interval": "monthly",
                    "currency": "KES",
                },
            }
        if method == "POST" and path == "/transaction/initialize":
            return {
                "status": True,
                "data": {
                    "authorization_url": "https://checkout.example.invalid/qa",
                    "reference": "qa-provider-ref",
                },
            }
        if method == "GET" and path == "/transaction/verify/qa-paystack-1":
            return {
                "status": True,
                "data": {
                    "id": 9001,
                    "status": "success",
                    "amount": int(get_plan(db, "plus")["price_kes"]) * 100,
                    "currency": "KES",
                },
            }
        raise AssertionError((method, path, kwargs))

    monkeypatch.setattr(app_module, "paystack_request", fake_paystack_request)

    provider_reference, authorization_url = app_module.create_paystack_transaction(
        "qa-paystack-1",
        int(get_plan(db, "plus")["price_kes"]),
        "Prepza Plus Plan",
        user,
        paystack_plan_code="QA_PLUS",
    )
    assert provider_reference == "qa-provider-ref"
    assert authorization_url.endswith("/qa")

    init_payload = next(
        kwargs["json"] for method, path, kwargs in calls
        if method == "POST" and path == "/transaction/initialize"
    )
    assert init_payload["amount"] == int(get_plan(db, "plus")["price_kes"]) * 100
    assert init_payload["currency"] == "KES"
    assert init_payload["reference"] == "qa-paystack-1"
    # Paystack's dashboard "pass fees to customers" setting is intentionally
    # outside Prepza's product price. Prepza must never inflate its order or
    # entitlement amount by guessing the provider fee.
    assert "transaction_charge" not in init_payload
    assert "bearer" not in init_payload

    payment = app_module.Payment(
        user_id=user.id,
        content_item_id=None,
        amount=int(get_plan(db, "plus")["price_kes"]),
        provider="paystack",
        reference="qa-paystack-1",
        provider_reference="qa-provider-ref",
        payment_type="subscription",
        plan="plus",
        status="pending",
    )
    db.session.add(payment)
    db.session.flush()
    app_module._student_order_helpers["create"](
        payment,
        item_title="Plus Plan",
        requested_payload={"payment_type": "subscription", "plan": "plus", "quantity": 1},
    )
    db.session.commit()

    first = app_module.sync_paystack_payment_status("qa-paystack-1")
    assert first.status == "success"
    assert first.provider_reference == "9001"
    assert get_user_plan_code(db, user.id) == "plus"

    payment_id = first.id
    entitlement_start = first.subscription_starts_at
    entitlement_end = first.subscription_expires_at

    second = app_module.sync_paystack_payment_status("qa-paystack-1")
    assert second.id == payment_id
    assert second.subscription_starts_at == entitlement_start
    assert second.subscription_expires_at == entitlement_end

    orders = db.session.execute(
        text("SELECT status FROM student_order WHERE payment_id=:pid"),
        {"pid": payment_id},
    ).scalars().all()
    assert orders == ["fulfilled"]


def test_paystack_webhook_rejects_bad_signature_retries_then_deduplicates_entitlement(world, monkeypatch):
    """Exercise signed webhook delivery, transient verification failure, retry and duplicate replay."""
    import app as app_module
    from ai_economics import get_plan, get_user_plan_code

    user = User(
        email="qa.paystack.webhook@test.invalid",
        password_hash=generate_password_hash("Qa!WebhookPassword123"),
        year=2,
        semester=1,
        display_name="qa.paystack.webhook",
        email_verified=True,
        is_suspended=False,
        profile_visibility="public",
        who_can_message="everyone",
        who_can_follow="everyone",
        read_receipts_enabled=True,
        university_id=world["university_a"].id,
        program_id=world["program_a"].id,
        session_version=0,
    )
    db.session.add(user)
    db.session.flush()

    price = int(get_plan(db, "plus")["price_kes"])
    reference = "qa-webhook-retry-entitlement"
    payment = app_module.Payment(
        user_id=user.id,
        content_item_id=None,
        amount=price,
        provider="paystack",
        reference=reference,
        provider_reference="qa-provider-ref",
        payment_type="subscription",
        plan="plus",
        status="pending",
    )
    db.session.add(payment)
    db.session.flush()
    app_module._student_order_helpers["create"](
        payment,
        item_title="Plus Plan",
        requested_payload={"payment_type": "subscription", "plan": "plus", "quantity": 1},
    )
    db.session.commit()

    secret = "ci-only-webhook-secret"
    monkeypatch.setattr(app_module, "PAYSTACK_SECRET_KEY", secret)
    calls = []
    transient = {"fail_next": True}

    def fake_paystack_request(method, path, **kwargs):
        calls.append((method, path))
        if method == "GET" and path == f"/transaction/verify/{reference}":
            if transient["fail_next"]:
                transient["fail_next"] = False
                raise RuntimeError("simulated temporary verification timeout")
            return {
                "status": True,
                "data": {
                    "id": 99123,
                    "status": "success",
                    "amount": price * 100,
                    "currency": "KES",
                },
            }
        raise AssertionError((method, path, kwargs))

    monkeypatch.setattr(app_module, "paystack_request", fake_paystack_request)
    payload = {"event": "charge.success", "data": {"reference": reference}}
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    client = app_module.app.test_client()

    invalid = client.post(
        "/payment/paystack/webhook",
        data=raw_body,
        content_type="application/json",
        headers={"X-Paystack-Signature": "not-a-valid-signature"},
    )
    assert invalid.status_code == 401
    assert calls == [], "invalid signature must be rejected before provider verification"

    first_delivery = client.post(
        "/payment/paystack/webhook",
        data=raw_body,
        content_type="application/json",
        headers={"X-Paystack-Signature": signature},
    )
    assert first_delivery.status_code == 500
    db.session.expire_all()
    pending = app_module.Payment.query.filter_by(reference=reference).one()
    assert pending.status == "pending"
    assert get_user_plan_code(db, user.id) == "free"
    assert len(calls) == 1

    retry = client.post(
        "/payment/paystack/webhook",
        data=raw_body,
        content_type="application/json",
        headers={"X-Paystack-Signature": signature},
    )
    assert retry.status_code == 200
    db.session.expire_all()
    paid = app_module.Payment.query.filter_by(reference=reference).one()
    assert paid.status == "success"
    assert paid.provider_reference == "99123"
    assert paid.subscription_starts_at is not None
    assert paid.subscription_expires_at is not None
    assert get_user_plan_code(db, user.id) == "plus"
    entitlement_start = paid.subscription_starts_at
    entitlement_end = paid.subscription_expires_at
    payment_id = paid.id
    assert len(calls) == 2

    duplicate = client.post(
        "/payment/paystack/webhook",
        data=raw_body,
        content_type="application/json",
        headers={"X-Paystack-Signature": signature},
    )
    assert duplicate.status_code == 200
    db.session.expire_all()
    replayed = app_module.Payment.query.filter_by(reference=reference).one()
    assert replayed.id == payment_id
    assert replayed.subscription_starts_at == entitlement_start
    assert replayed.subscription_expires_at == entitlement_end
    assert get_user_plan_code(db, user.id) == "plus"
    assert len(calls) == 2, "duplicate successful webhook must not re-verify or extend entitlement again"
    order_statuses = db.session.execute(
        text("SELECT status FROM student_order WHERE payment_id=:pid"),
        {"pid": payment_id},
    ).scalars().all()
    assert order_statuses == ["fulfilled"]

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


def test_b2b_prepaid_metering_protects_advertiser_balance_and_locks_campaign_pricing(world):
    """Verify billable views/clicks debit prepaid funds exactly and caps protect repeats."""
    from b2b_campaign_metering import record_billable_event

    now = datetime.utcnow()
    campaign = db.session.execute(
        text("""
            INSERT INTO discovery_campaign
                (organisation_id, opportunity_id, name, objective, placement, status,
                 budget_kes, bid_type, bid_kes, target_json, starts_at, ends_at)
            VALUES
                (:oid, NULL, 'QA prepaid economics', 'reach', 'feed', 'active',
                 5000, 'both', 350, CAST(:target AS jsonb), :starts, :ends)
            RETURNING id
        """),
        {
            "oid": world["organisation"].id,
            "target": json.dumps({"billing_modes": ["cpm", "cpc"]}),
            "starts": now - timedelta(minutes=1),
            "ends": now + timedelta(days=1),
        },
    ).scalar_one()
    db.session.execute(
        text("""
            UPDATE discovery_campaign
            SET funding_status='funded',
                funded_amount_minor=500000,
                pricing_version='qa-v1',
                pricing_snapshot=CAST(:snapshot AS jsonb)
            WHERE id=:cid
        """),
        {
            "cid": campaign,
            "snapshot": json.dumps({
                "home_impression_cpm": {"value": {"amount_kes": 350, "per": 1000}, "version": "qa-v1"},
                "click_cpc": {"value": {"amount_kes": 20}, "version": "qa-v1"},
                "home_frequency_cap": {"value": {"max_impressions": 1000, "window_days": 7}, "version": "qa-v1"},
                "click_frequency_cap": {"value": {"max_clicks": 1, "window_days": 1}, "version": "qa-v1"},
            }),
        },
    )
    db.session.commit()

    student_id = world["student_a"].id

    # A qualifying sponsored view costs exactly KES 0.35 at KES 350 CPM.
    first_view = record_billable_event(
        db, campaign, student_id, "impression", "feed", "qa-impression-1"
    )
    assert first_view["ok"]
    assert first_view["amount_minor"] == 35

    # Re-sending the exact event key cannot charge twice.
    duplicate_view = record_billable_event(
        db, campaign, student_id, "impression", "feed", "qa-impression-1"
    )
    assert duplicate_view["ok"] and duplicate_view["duplicate"]
    assert duplicate_view["amount_minor"] == 35

    # The first qualifying click costs exactly KES 20.
    first_click = record_billable_event(
        db, campaign, student_id, "click", "feed", "qa-click-1"
    )
    assert first_click["ok"]
    assert first_click["amount_minor"] == 2000

    # Repeated clicks from the same student are capped at one billable click
    # per rolling day, so an attacker cannot drain prepaid funds by hammering
    # the same CTA.
    second_click = record_billable_event(
        db, campaign, student_id, "click", "feed", "qa-click-2"
    )
    assert not second_click["ok"]
    assert second_click["reason"] == "student_frequency_cap"

    # Changing the global admin CPC price does not rewrite the already-funded
    # campaign's pricing snapshot.
    db.session.execute(
        text("""
            UPDATE b2b_pricing_config
            SET value_json=CAST(:value AS jsonb), version='qa-admin-v2'
            WHERE config_key='click_cpc'
        """),
        {"value": json.dumps({"amount_kes": 99})},
    )
    db.session.commit()

    campaign_price = db.session.execute(
        text("""
            SELECT (pricing_snapshot->'click_cpc'->'value'->>'amount_kes')::INTEGER
            FROM discovery_campaign WHERE id=:cid
        """),
        {"cid": campaign},
    ).scalar_one()
    assert campaign_price == 20

    # CPM arithmetic remains exact: 1,000 billable impressions at KES 350
    # consume KES 350 total. Use a separate campaign with a high test cap.
    cpm_campaign = db.session.execute(
        text("""
            INSERT INTO discovery_campaign
                (organisation_id, name, objective, placement, status, budget_kes,
                 bid_type, bid_kes, target_json, starts_at, ends_at,
                 funding_status, funded_amount_minor, pricing_version, pricing_snapshot)
            VALUES
                (:oid, 'QA CPM 1000', 'reach', 'feed', 'active', 350,
                 'cpm', 350, CAST(:target AS jsonb), :starts, :ends,
                 'funded', 35000, 'qa-cpm-v1', CAST(:snapshot AS jsonb))
            RETURNING id
        """),
        {
            "oid": world["organisation"].id,
            "target": json.dumps({"billing_modes": ["cpm"]}),
            "starts": now - timedelta(minutes=1),
            "ends": now + timedelta(days=1),
            "snapshot": json.dumps({
                "home_impression_cpm": {"value": {"amount_kes": 350, "per": 1000}, "version": "qa-cpm-v1"},
                "home_frequency_cap": {"value": {"max_impressions": 1000, "window_days": 7}, "version": "qa-cpm-v1"},
            }),
        },
    ).scalar_one()
    db.session.commit()

    for i in range(1000):
        result = record_billable_event(
            db, cpm_campaign, student_id, "impression", "feed", f"qa-cpm-{i}"
        )
        assert result["ok"]

    ledger_balance = db.session.execute(
        text("""
            SELECT COALESCE(SUM(signed_amount_minor), 0)
            FROM b2b_campaign_ledger WHERE campaign_id=:cid
        """),
        {"cid": cpm_campaign},
    ).scalar_one()
    # The ledger records spend as negative signed entries. A fully consumed
    # KES 350 prepaid campaign therefore has -35,000 minor units in the ledger,
    # while the campaign's derived remaining balance is exactly zero.
    assert int(ledger_balance) == -35000
    campaign_balance = db.session.execute(
        text("""
            SELECT funding_status, funded_amount_minor +
                   COALESCE((
                       SELECT SUM(signed_amount_minor)
                       FROM b2b_campaign_ledger
                       WHERE campaign_id=:cid
                   ), 0) AS remaining_minor
            FROM discovery_campaign
            WHERE id=:cid
        """),
        {"cid": cpm_campaign},
    ).mappings().first()
    assert campaign_balance["funding_status"] == "exhausted"
    assert int(campaign_balance["remaining_minor"]) == 0

    db.session.commit()



def test_b2b_paystack_campaign_checkout_uses_mock_provider_and_separates_campaign_value(world, monkeypatch):
    """Exercise the real B2B checkout route while replacing every Paystack HTTP call."""
    import b2b_campaign_payments as b2b_payment_module

    now = datetime.utcnow()
    owner = world["student_a"]
    organisation = Organisation(
        name="QA Mock Paystack Advertiser",
        description="Disposable provider contract fixture",
        contact_email="qa.mock.paystack@test.invalid",
        verification_status="verified",
        is_active=True,
        created_by=owner.id,
        created_at=now,
        updated_at=now,
    )
    db.session.add(organisation)
    db.session.flush()
    db.session.add(OrganisationMember(
        organisation_id=organisation.id,
        user_id=owner.id,
        role="owner",
    ))
    campaign_id = db.session.execute(text("""
        INSERT INTO discovery_campaign
            (organisation_id, opportunity_id, name, objective, placement, status,
             budget_kes, bid_type, bid_kes, target_json, starts_at, ends_at, funding_status)
        VALUES
            (:oid, NULL, 'QA Mock Paystack Campaign', 'reach', 'home_carousel', 'draft',
             5000, 'both', 350, CAST(:target AS jsonb), :starts, :ends, 'unfunded')
        RETURNING id
    """), {
        "oid": organisation.id,
        "target": json.dumps({"billing_modes": ["cpm", "cpc"]}),
        "starts": now - timedelta(minutes=1),
        "ends": now + timedelta(days=2),
    }).scalar_one()
    db.session.commit()

    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_mock_only_not_a_real_secret")
    monkeypatch.setenv("PAYSTACK_CUSTOMER_FEE_PASSING_ENABLED", "true")
    monkeypatch.setenv("BASE_URL", "https://prepza.test.invalid")
    calls = []

    class FakePaystackResponse:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_request(method, url, *, headers, timeout, **kwargs):
        calls.append({
            "method": method,
            "url": url,
            "headers": headers,
            "timeout": timeout,
            **kwargs,
        })
        if method == "POST" and url == "https://api.paystack.co/transaction/initialize":
            return FakePaystackResponse({
                "status": True,
                "message": "Authorization URL created",
                "data": {
                    "authorization_url": "https://checkout.example.invalid/test-only",
                    "access_code": "mock-access-code",
                    "reference": "mock-provider-reference",
                },
            })
        if method == "GET" and url.endswith(f"/transaction/verify/{body_reference[0]}"):
            return FakePaystackResponse({
                "status": True,
                "message": "Verification successful",
                "data": {
                    "status": "success",
                    "currency": "KES",
                    "requested_amount": 500000,
                    "amount": 500000,
                    "fees": 15000,
                },
            })
        raise AssertionError(f"Unexpected Paystack boundary call: {method} {url}")

    monkeypatch.setattr(b2b_payment_module.requests, "request", fake_request)
    client = _client_for(owner.id)
    response = client.post(
        f"/api/organisations/{organisation.id}/discovery/campaigns/{campaign_id}/payment",
        headers=_csrf(owner.id),
    )

    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["ok"] is True
    assert body["authorization_url"] == "https://checkout.example.invalid/test-only"
    assert body["campaign_amount_minor"] == 500000
    assert body["reference"].startswith(f"PZA-CAMP-{campaign_id}-")
    assert body["customer_fee_mode"] == "paystack_pass_through"

    assert len(calls) == 1
    body_reference = [body["reference"]]
    call = calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://api.paystack.co/transaction/initialize"
    assert call["headers"]["Authorization"] == "Bearer sk_test_mock_only_not_a_real_secret"
    checkout = call["json"]
    assert checkout["amount"] == "500000"
    assert checkout["currency"] == "KES"
    assert checkout["reference"] == body["reference"]
    assert checkout["callback_url"] == "https://prepza.test.invalid/organisation-payment-callback"
    metadata = json.loads(checkout["metadata"])
    assert metadata["purpose"] == "sponsored_campaign"
    assert metadata["campaign_id"] == campaign_id
    assert metadata["organisation_id"] == organisation.id
    assert metadata["campaign_amount_minor"] == 500000
    assert "bearer" not in checkout

    payment = db.session.execute(text("""
        SELECT status, customer_amount_minor, campaign_amount_minor, processing_fee_minor, purpose
        FROM b2b_payment WHERE campaign_id=:cid
    """), {"cid": campaign_id}).mappings().one()
    assert payment["status"] == "pending"
    assert int(payment["customer_amount_minor"]) == 500000
    assert int(payment["campaign_amount_minor"]) == 500000
    assert int(payment["processing_fee_minor"]) == 0
    assert payment["purpose"] == "sponsored_campaign"

    campaign = db.session.execute(text("""
        SELECT status, funding_status, funded_amount_minor, pricing_snapshot
        FROM discovery_campaign WHERE id=:cid
    """), {"cid": campaign_id}).mappings().one()
    assert campaign["status"] == "pending_payment"
    assert campaign["funding_status"] == "payment_pending"
    assert int(campaign["funded_amount_minor"] or 0) == 0
    snapshot = campaign["pricing_snapshot"]
    assert isinstance(snapshot, dict)
    assert "home_impression_cpm" in snapshot and "click_cpc" in snapshot

    # A webhook with a bad signature must not contact the provider verifier.
    import hashlib
    import hmac
    payload = {
        "event": "charge.success",
        "data": {
            "reference": body["reference"],
            "metadata": {
                "purpose": "sponsored_campaign",
                "campaign_id": campaign_id,
                "organisation_id": organisation.id,
                "campaign_amount_minor": 500000,
            },
        },
    }
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    invalid = client.post(
        "/payment/paystack/b2b-webhook",
        data=raw_body,
        content_type="application/json",
        headers={"x-paystack-signature": "invalid"},
    )
    assert invalid.status_code == 401
    assert len(calls) == 1, "invalid signature must be rejected before provider verification"

    signature = hmac.new(
        b"sk_test_mock_only_not_a_real_secret",
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    success = client.post(
        "/payment/paystack/b2b-webhook",
        data=raw_body,
        content_type="application/json",
        headers={"x-paystack-signature": signature},
    )
    assert success.status_code == 200, success.get_json()
    assert success.get_json()["ok"] is True
    assert success.get_json()["funded_amount_minor"] == 500000
    assert len(calls) == 2
    assert calls[1]["method"] == "GET"
    assert calls[1]["url"].endswith(f"/transaction/verify/{body['reference']}")

    funding = db.session.execute(text("""
        SELECT COUNT(*) AS count, COALESCE(SUM(amount_minor),0) AS amount_minor
        FROM b2b_campaign_funding WHERE campaign_id=:cid
    """), {"cid": campaign_id}).mappings().one()
    assert int(funding["count"]) == 1
    assert int(funding["amount_minor"]) == 500000
    funding_ledger = db.session.execute(text("""
        SELECT COUNT(*) AS count, COALESCE(SUM(signed_amount_minor),0) AS amount_minor
        FROM b2b_campaign_ledger WHERE campaign_id=:cid AND entry_type='funding'
    """), {"cid": campaign_id}).mappings().one()
    assert int(funding_ledger["count"]) == 1
    assert int(funding_ledger["amount_minor"]) == 500000
    db.session.expire_all()
    campaign_after_success = db.session.execute(text("""
        SELECT status, funding_status, funded_amount_minor
        FROM discovery_campaign WHERE id=:cid
    """), {"cid": campaign_id}).mappings().one()
    assert campaign_after_success["status"] == "active"
    assert campaign_after_success["funding_status"] == "funded"
    assert int(campaign_after_success["funded_amount_minor"]) == 500000

    # Paystack can deliver the exact event more than once. The signed duplicate
    # must be acknowledged without re-verifying, funding again, or adding a
    # second ledger row.
    duplicate = client.post(
        "/payment/paystack/b2b-webhook",
        data=raw_body,
        content_type="application/json",
        headers={"x-paystack-signature": signature},
    )
    assert duplicate.status_code == 200
    assert duplicate.get_json()["duplicate"] is True
    assert len(calls) == 2
    funding_count = db.session.execute(text("""
        SELECT COUNT(*) FROM b2b_campaign_funding WHERE campaign_id=:cid
    """), {"cid": campaign_id}).scalar_one()
    ledger_count = db.session.execute(text("""
        SELECT COUNT(*) FROM b2b_campaign_ledger
        WHERE campaign_id=:cid AND entry_type='funding'
    """), {"cid": campaign_id}).scalar_one()
    assert int(funding_count) == 1 and int(ledger_count) == 1

    # Refund webhooks can also be delivered more than once. The ledger key
    # prevents a second campaign debit; the payment's cumulative refunded
    # amount must be idempotent too.
    refund_payload = {
        "event": "refund.processed",
        "data": {
            "transaction_reference": body["reference"],
            "amount": 10000,
            "refund_reference": "qa-refund-duplicate-1",
        },
    }
    refund_raw = json.dumps(refund_payload, separators=(",", ":")).encode("utf-8")
    refund_signature = hmac.new(
        b"sk_test_mock_only_not_a_real_secret", refund_raw, hashlib.sha512
    ).hexdigest()
    first_refund = client.post(
        "/payment/paystack/b2b-webhook",
        data=refund_raw,
        content_type="application/json",
        headers={"x-paystack-signature": refund_signature},
    )
    assert first_refund.status_code == 200, first_refund.get_json()

    duplicate_refund = client.post(
        "/payment/paystack/b2b-webhook",
        data=refund_raw,
        content_type="application/json",
        headers={"x-paystack-signature": refund_signature},
    )
    assert duplicate_refund.status_code == 200, duplicate_refund.get_json()
    assert duplicate_refund.get_json()["duplicate"] is True

    payment_after_refund = db.session.execute(text("""
        SELECT refunded_amount_minor, status, refund_status
        FROM b2b_payment WHERE campaign_id=:cid
    """), {"cid": campaign_id}).mappings().one()
    assert int(payment_after_refund["refunded_amount_minor"]) == 10000
    assert payment_after_refund["status"] == "refunded"
    assert payment_after_refund["refund_status"] == "processed"
    refund_rows = db.session.execute(text("""
        SELECT COUNT(*) FROM b2b_campaign_ledger
        WHERE campaign_id=:cid AND entry_type='refund'
    """), {"cid": campaign_id}).scalar_one()
    assert int(refund_rows) == 1

    # Two distinct partial refunds can have the same amount. When the provider
    # payload has no explicit refund id, stable payload identity must still
    # distinguish them while deduplicating a replay of each payload.
    second_refund_payload = {
        "event": "refund.processed",
        "data": {
            "transaction_reference": body["reference"],
            "amount": 10000,
            "created_at": "2026-10-27T12:30:00Z",
        },
    }
    second_refund_raw = json.dumps(
        second_refund_payload, separators=(",", ":")
    ).encode("utf-8")
    second_refund_signature = hmac.new(
        b"sk_test_mock_only_not_a_real_secret",
        second_refund_raw,
        hashlib.sha512,
    ).hexdigest()
    second_refund = client.post(
        "/payment/paystack/b2b-webhook",
        data=second_refund_raw,
        content_type="application/json",
        headers={"x-paystack-signature": second_refund_signature},
    )
    assert second_refund.status_code == 200, second_refund.get_json()

    second_refund_replay = client.post(
        "/payment/paystack/b2b-webhook",
        data=second_refund_raw,
        content_type="application/json",
        headers={"x-paystack-signature": second_refund_signature},
    )
    assert second_refund_replay.status_code == 200, second_refund_replay.get_json()
    assert second_refund_replay.get_json()["duplicate"] is True

    payment_after_second_refund = db.session.execute(text("""
        SELECT refunded_amount_minor FROM b2b_payment WHERE campaign_id=:cid
    """), {"cid": campaign_id}).scalar_one()
    assert int(payment_after_second_refund) == 20000
    refund_rows_after_second = db.session.execute(text("""
        SELECT COUNT(*) FROM b2b_campaign_ledger
        WHERE campaign_id=:cid AND entry_type='refund'
    """), {"cid": campaign_id}).scalar_one()
    assert int(refund_rows_after_second) == 2



def test_b2b_campus_report_shows_aggregate_only_at_ten_reached_accounts(world):
    """Verify campus aggregate appears at the threshold without student-level fields."""
    from b2b_campaign_metering import record_billable_event

    now = datetime.utcnow()
    test_users = []
    for index in range(10):
        user = User(
            email=f"qa.campus.report.{index}@test.invalid",
            password_hash=generate_password_hash("Qa!Campus123"),
            year=2,
            semester=1,
            display_name=f"QA Campus Student {index}",
            email_verified=True,
            is_admin=False,
            is_suspended=False,
            profile_visibility="public",
            who_can_message="everyone",
            who_can_follow="everyone",
            read_receipts_enabled=True,
            university_id=world["university_a"].id,
            program_id=world["program_a"].id,
            session_version=0,
        )
        db.session.add(user)
        test_users.append(user)
    db.session.flush()

    campaign_id = db.session.execute(text("""
        INSERT INTO discovery_campaign
            (organisation_id, opportunity_id, name, objective, placement, status,
             budget_kes, bid_type, bid_kes, target_json, starts_at, ends_at,
             funding_status, funded_amount_minor, pricing_version, pricing_snapshot)
        VALUES
            (:oid, NULL, 'QA Campus Aggregate Report', 'reach', 'home_carousel', 'active',
             5000, 'both', 350, CAST(:target AS jsonb), :starts, :ends,
             'funded', 500000, 'qa-campus-v1', CAST(:snapshot AS jsonb))
        RETURNING id
    """), {
        "oid": world["organisation"].id,
        "target": json.dumps({"billing_modes": ["cpm", "cpc"]}),
        "starts": now - timedelta(minutes=1),
        "ends": now + timedelta(days=2),
        "snapshot": json.dumps({
            "home_impression_cpm": {"value": {"amount_kes": 350, "per": 1000}, "version": "qa-campus-v1"},
            "click_cpc": {"value": {"amount_kes": 20}, "version": "qa-campus-v1"},
            "home_frequency_cap": {"value": {"max_impressions": 100, "window_days": 7}, "version": "qa-campus-v1"},
            "click_frequency_cap": {"value": {"max_clicks": 1, "window_days": 1}, "version": "qa-campus-v1"},
        }),
    }).scalar_one()
    db.session.commit()

    for user in test_users:
        impression = record_billable_event(
            db, campaign_id, user.id, "impression", "home_carousel",
            f"qa-campus-impression-{user.id}",
        )
        assert impression["ok"] is True, impression
        click = record_billable_event(
            db, campaign_id, user.id, "click", "home_carousel",
            f"qa-campus-click-{user.id}",
        )
        assert click["ok"] is True, click
    db.session.commit()

    client = _client_for(world["student_a"].id)
    report_response = client.get(
        f"/api/organisations/{world['organisation'].id}/discovery/report?campaign_id={campaign_id}"
    )
    assert report_response.status_code == 200, report_response.get_data(as_text=True)
    report = report_response.get_json()
    assert report["period"]["timezone"] == "Africa/Nairobi"
    assert report["filters"]["campaign_id"] == campaign_id
    assert report["filters"]["university_id"] is None
    assert len(report["campaigns"]) == 1
    campaign = report["campaigns"][0]
    assert campaign["unique_reach"] == 10
    assert campaign["impressions"] == 10
    assert campaign["raw_clicks"] == 10
    assert campaign["unique_clicks"] == 10
    assert campaign["billable_clicks"] == 10
    assert campaign["ctr_percent"] == 100.0
    assert campaign["unique_ctr_percent"] == 100.0
    assert campaign["net_spend_kes"] == 203.5
    assert len(campaign["campus_breakdown"]) == 1
    campus = campaign["campus_breakdown"][0]
    assert campus["campus_id"] == world["university_a"].id
    assert campus["campus_name"] == "QA University A"
    assert campus["unique_reach"] == 10
    assert campus["impressions"] == 10
    assert campus["raw_clicks"] == 10
    assert campus["billable_clicks"] == 10
    assert campus["net_spend_kes"] == 203.5
    assert all(not any(key in row for key in ("user_id", "student_id", "email"))
               for row in report["campaigns"])
    assert all(not any(key in row for key in ("user_id", "student_id", "email"))
               for row in campaign["campus_breakdown"])

    campus_filtered = client.get(
        f"/api/organisations/{world['organisation'].id}/discovery/report"
        f"?campaign_id={campaign_id}&university_id={world['university_a'].id}"
    )
    assert campus_filtered.status_code == 200
    filtered_campaigns = campus_filtered.get_json()["campaigns"]
    assert len(filtered_campaigns) == 1
    assert filtered_campaigns[0]["unique_reach"] == 10
    assert filtered_campaigns[0]["campus_breakdown"][0]["campus_id"] == world["university_a"].id

    csv_response = client.get(
        f"/api/organisations/{world['organisation'].id}/discovery/report"
        f"?campaign_id={campaign_id}&format=csv"
    )
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.headers.get("content-type", "")
    csv_body = csv_response.get_data(as_text=True)
    assert "campaign,,,10" in csv_body
    assert f"campus,QA University A,{world['university_a'].id},10" in csv_body
    assert "203.5" in csv_body


def test_shop_free_first_listing_paid_second_posting_fee_and_direct_contact(world, monkeypatch):
    """Exercise Shop through listing, mocked Paystack fee, moderation, browse and chat."""
    import base64
    from io import BytesIO
    import app as app_module
    import object_storage
    import shop_marketplace

    seller_id = world["student_a"].id
    buyer_id = world["student_b"].id
    admin_id = world["admin"].id
    seller = _client_for(seller_id)
    buyer = _client_for(buyer_id)
    admin = _client_for(admin_id)

    # Isolated object storage: no live R2 bucket or credentials are used.
    monkeypatch.setattr(object_storage, "r2_put_bytes", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        object_storage,
        "r2_presigned_get",
        lambda logical_bucket, key, expires_in=60: "https://images.example.invalid/" + key,
    )

    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/pWQAAAAASUVORK5CYII="
    )
    invalid_price_payload = {
        "title": "QA invalid price item",
        "description": "This payload must never create a valid listing.",
        "category": "Electronics",
        "condition": "good",
        "price_kes": -1,
        "location_area": "Near campus",
        "whatsapp_number": "",
    }
    invalid_price = seller.post("/api/shop/listings", json=invalid_price_payload, headers=_csrf(seller_id))
    assert invalid_price.status_code == 400

    listing_payload = {
        "title": "QA scientific calculator",
        "description": "A useful calculator in good condition for testing.",
        "category": "Electronics",
        "condition": "good",
        "price_kes": 1200,
        "location_area": "Near campus",
        "whatsapp_number": "0712345678",
    }

    first = seller.post("/api/shop/listings", json=listing_payload, headers=_csrf(seller_id))
    assert first.status_code == 201
    first_listing = first.get_json()["listing"]
    assert first_listing["is_free_post"] is True
    assert first_listing["posting_fee_kes"] == 0
    assert first_listing["status"] == "draft"

    invalid_upload = seller.post(
        f"/api/shop/listings/{first_listing['id']}/images",
        data={"image": (BytesIO(b"not an image",), "fake.png")},
        headers=_csrf(seller_id),
        content_type="multipart/form-data",
    )
    assert invalid_upload.status_code == 400

    upload = seller.post(
        f"/api/shop/listings/{first_listing['id']}/images",
        data={"image": (BytesIO(png_bytes), "calculator.png")},
        headers=_csrf(seller_id),
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201, upload.get_json()
    published = seller.post(
        f"/api/shop/listings/{first_listing['id']}/publish",
        headers=_csrf(seller_id),
    )
    assert published.status_code == 200
    assert published.get_json()["listing"]["status"] == "pending_review"

    first_approval = admin.post(
        f"/api/shop/admin/listings/{first_listing['id']}/moderate",
        json={"action": "approve"},
        headers=_csrf(admin_id),
    )
    assert first_approval.status_code == 200, first_approval.get_json()
    assert first_approval.get_json()["listing"]["status"] == "active"

    second_payload = dict(listing_payload)
    second_payload.update({
        "title": "QA used course textbook",
        "category": "Books & study",
        "price_kes": 450,
    })
    second = seller.post("/api/shop/listings", json=second_payload, headers=_csrf(seller_id))
    assert second.status_code == 201
    second_listing = second.get_json()["listing"]
    assert second_listing["is_free_post"] is False
    assert second_listing["posting_fee_kes"] == 100
    assert second_listing["posting_fee_paid"] is False

    second_upload = seller.post(
        f"/api/shop/listings/{second_listing['id']}/images",
        data={"image": (BytesIO(png_bytes), "textbook.png")},
        headers=_csrf(seller_id),
        content_type="multipart/form-data",
    )
    assert second_upload.status_code == 201, second_upload.get_json()

    fake_provider_result = {"status": "success", "amount": 10000, "currency": "KES"}

    def fake_paystack_request(method, path, **kwargs):
        if method == "POST" and path == "/transaction/initialize":
            reference = kwargs["json"]["reference"]
            return {
                "status": True,
                "data": {
                    "authorization_url": "https://checkout.example.invalid/" + reference,
                    "reference": reference,
                },
            }
        if method == "GET" and path.startswith("/transaction/verify/"):
            reference = path.rsplit("/", 1)[1]
            payment = app_module.Payment.query.filter_by(reference=reference).first()
            assert payment is not None
            return {
                "status": True,
                "data": {
                    "id": 900000000 + payment.id,
                    "status": fake_provider_result["status"],
                    "amount": fake_provider_result["amount"],
                    "currency": fake_provider_result["currency"],
                    "reference": reference,
                },
            }
        raise AssertionError(f"Unexpected mocked Paystack call: {method} {path}")

    monkeypatch.setattr(app_module, "paystack_request", fake_paystack_request)
    checkout = seller.post(
        f"/api/shop/listings/{second_listing['id']}/checkout",
        headers=_csrf(seller_id),
    )
    assert checkout.status_code == 200, checkout.get_json()
    checkout_data = checkout.get_json()
    assert checkout_data["redirect_url"].startswith("https://checkout.example.invalid/")
    reference = checkout_data["reference"]

    callback = seller.get("/shop/payment/callback?reference=" + reference, follow_redirects=False)
    assert callback.status_code == 302
    payment_status = seller.get("/api/shop/payments/" + reference)
    assert payment_status.status_code == 200
    assert payment_status.get_json()["status"] == "success"
    assert payment_status.get_json()["listing"]["posting_fee_paid"] is True
    assert payment_status.get_json()["listing"]["status"] == "draft"
    # Callback/webhook retries must not charge twice or move the listing twice.
    duplicate_verify = app_module.sync_paystack_payment_status(reference)
    assert duplicate_verify.status == "success"
    assert db.session.get(shop_marketplace._ShopListing, second_listing["id"]).posting_fee_paid is True

    second_publish = seller.post(
        f"/api/shop/listings/{second_listing['id']}/publish",
        headers=_csrf(seller_id),
    )
    assert second_publish.status_code == 200
    assert second_publish.get_json()["listing"]["status"] == "pending_review"

    second_approval = admin.post(
        f"/api/shop/admin/listings/{second_listing['id']}/moderate",
        json={"action": "approve"},
        headers=_csrf(admin_id),
    )
    assert second_approval.status_code == 200
    assert second_approval.get_json()["listing"]["status"] == "active"

    browse = buyer.get("/api/shop/listings?q=QA")
    assert browse.status_code == 200
    visible_ids = {item["id"] for item in browse.get_json()["listings"]}
    assert first_listing["id"] in visible_ids
    assert second_listing["id"] in visible_ids

    detail = buyer.get(f"/api/shop/listings/{first_listing['id']}")
    assert detail.status_code == 200
    assert detail.get_json()["listing"]["whatsapp_url"] == "https://wa.me/254712345678"

    # In-app seller contact uses the existing chat route and CSRF/privacy checks.
    chat = buyer.post(
        "/chats",
        json={"is_group": False, "participant_ids": [seller_id]},
        headers=_csrf(buyer_id),
    )
    assert chat.status_code in (200, 201)
    assert chat.get_json()["id"] > 0

    # Saving and reporting use server-owned listing identity and admin resolution.
    saved_response = buyer.post(
        f"/api/shop/listings/{first_listing['id']}/save",
        headers=_csrf(buyer_id),
    )
    assert saved_response.status_code == 200
    saved_list = buyer.get("/api/shop/saved")
    assert first_listing["id"] in {item["id"] for item in saved_list.get_json()["listings"]}

    report_response = buyer.post(
        f"/api/shop/listings/{first_listing['id']}/report",
        json={"reason": "misleading", "details": "QA moderation report."},
        headers=_csrf(buyer_id),
    )
    assert report_response.status_code == 201
    queue = admin.get("/api/shop/admin/queue")
    assert queue.status_code == 200
    report_id = next(item["id"] for item in queue.get_json()["reports"] if item["listing_id"] == first_listing["id"])
    resolved = admin.post(f"/api/shop/admin/reports/{report_id}/resolve", headers=_csrf(admin_id))
    assert resolved.status_code == 200

    # A provider-successful amount mismatch must be quarantined, not treated
    # as a paid KES 100 posting fee or an ordinary retryable checkout.
    third_payload = dict(listing_payload)
    third_payload.update({"title": "QA mismatched fee listing", "price_kes": 100})
    third = seller.post("/api/shop/listings", json=third_payload, headers=_csrf(seller_id))
    assert third.status_code == 201
    third_listing = third.get_json()["listing"]
    assert third_listing["posting_fee_kes"] == 100
    third_checkout = seller.post(
        f"/api/shop/listings/{third_listing['id']}/checkout",
        headers=_csrf(seller_id),
    )
    assert third_checkout.status_code == 200
    mismatch_reference = third_checkout.get_json()["reference"]
    fake_provider_result.update({"status": "success", "amount": 5000, "currency": "KES"})
    mismatch_callback = seller.get(
        "/shop/payment/callback?reference=" + mismatch_reference,
        follow_redirects=False,
    )
    assert mismatch_callback.status_code == 302
    mismatch_status = seller.get("/api/shop/payments/" + mismatch_reference)
    assert mismatch_status.status_code == 200
    assert mismatch_status.get_json()["status"] == "mismatched"
    assert mismatch_status.get_json()["listing"]["posting_fee_paid"] is False
    assert mismatch_status.get_json()["listing"]["status"] == "payment_review"
    mismatch_publish = seller.post(
        f"/api/shop/listings/{third_listing['id']}/publish",
        headers=_csrf(seller_id),
    )
    assert mismatch_publish.status_code == 409
    payment_review_queue = admin.get("/api/shop/admin/queue")
    assert third_listing["id"] in {
        item["id"] for item in payment_review_queue.get_json()["payment_reviews"]
    }

    # A different account cannot mutate the seller's listing.
    forbidden_edit = buyer.patch(
        f"/api/shop/listings/{first_listing['id']}",
        json=listing_payload,
        headers=_csrf(buyer_id),
    )
    assert forbidden_edit.status_code == 404

