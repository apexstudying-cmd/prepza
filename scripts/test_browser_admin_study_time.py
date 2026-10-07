"""Browser/runtime equality gate for student and admin Study Hub time.

This gate proves that the student-facing /study-time endpoint and the
admin /admin/operations endpoint read the same authoritative PostgreSQL
StudyTimeLog totals. It deliberately uses the real Flask application and
PostgreSQL, while Playwright verifies the values through authenticated
browser contexts.

The existing browser offline-lifecycle gate separately proves local offline
clocking/reconnect behavior. This gate proves that, after reconnect
reconciliation, the server and admin views agree.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from playwright.sync_api import sync_playwright

from app import (
    app,
    db,
    User,
    StudyTimeLog,
    StudyStreak,
    XpEvent,
    STUDY_TIME_FEATURE,
    MAX_STUDY_TIME_SECONDS_PER_DAY,
    _study_local_date,
    reconcile_study_time,
)
from werkzeug.security import generate_password_hash


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("PREPZA_BROWSER_BASE_URL", "http://localhost:5000")
COMPOSE_FILE = os.environ.get("PREPZA_COMPOSE_FILE", "docker-compose.vps.yml")
PASSWORD = "AdminStudyTime!12345"


def run_container_python(code: str) -> str:
    result = subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "exec", "-T", "app", "python", "-"],
        cwd=ROOT,
        input=code,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()


def create_fixture() -> dict:
    code = f"""
import json
from uuid import uuid4
from werkzeug.security import generate_password_hash
from app import app, db, User

with app.app_context():
    suffix = uuid4().hex
    users = []
    for label, is_admin in (
        ("student-a", False),
        ("student-b", False),
        ("admin", True),
    ):
        user = User(
            email=f"admin-study-time.{{label}}-{{suffix}}@test.invalid",
            password_hash=generate_password_hash({PASSWORD!r}),
            year=2,
            semester=1,
            display_name=f"Admin Study Time {{label}}",
            email_verified=True,
            is_admin=is_admin,
            is_suspended=False,
            profile_visibility="public",
            who_can_message="everyone",
            who_can_follow="everyone",
            read_receipts_enabled=True,
            university_id=None,
            program_id=None,
            session_version=0,
        )
        db.session.add(user)
        users.append(user)

    db.session.commit()
    print(json.dumps({{
        "student_a": {{"id": users[0].id, "email": users[0].email}},
        "student_b": {{"id": users[1].id, "email": users[1].email}},
        "admin": {{"id": users[2].id, "email": users[2].email}},
        "password": {PASSWORD!r},
    }}))
"""
    return json.loads(run_container_python(code).splitlines()[-1])


def cleanup_fixture(fixture: dict) -> None:
    code = f"""
from app import app, db, User, StudyTimeLog, StudyStreak, XpEvent

with app.app_context():
    ids = [{fixture["student_a"]["id"]}, {fixture["student_b"]["id"]}, {fixture["admin"]["id"]}]
    StudyTimeLog.query.filter(StudyTimeLog.user_id.in_(ids)).delete(synchronize_session=False)
    StudyStreak.query.filter(StudyStreak.user_id.in_(ids)).delete(synchronize_session=False)
    XpEvent.query.filter(XpEvent.user_id.in_(ids)).delete(synchronize_session=False)
    for user_id in ids:
        user = db.session.get(User, user_id)
        if user is not None:
            db.session.delete(user)
    db.session.commit()
"""
    run_container_python(code)


@pytest.fixture(scope="module")
def fixture():
    data = create_fixture()
    yield data
    cleanup_fixture(data)


def browser_login(page, email: str, password: str) -> None:
    response = page.request.post(
        f"{BASE_URL}/login",
        data=json.dumps({"email": email, "password": password}),
        headers={"Content-Type": "application/json"},
    )
    if not response.ok:
        raise RuntimeError(f"/login failed: {response.status} {response.text()}")
    page.goto(BASE_URL + "/", wait_until="domcontentloaded")


def browser_json(page, method: str, path: str) -> dict:
    response = getattr(page.request, method.lower())(BASE_URL + path)
    if not response.ok:
        raise RuntimeError(f"{method} {path} failed: {response.status} {response.text()}")
    return response.json()


def student_view(page) -> dict:
    return browser_json(page, "GET", "/study-time?period=day")


def admin_view(page) -> dict:
    return browser_json(page, "GET", "/admin/operations")


def sync_with_known_session(user_id: int, total_seconds: int) -> dict:
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["_session_version"] = 0
        session["csrf_token"] = "admin-study-time-test-csrf"

    response = client.post(
        "/study-time/sync",
        json={"total_seconds": total_seconds},
        headers={"X-CSRF-Token": "admin-study-time-test-csrf"},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def test_student_and_admin_views_agree_after_reconnect_reconciliation(fixture):
    """25s online -> offline +20s -> reconnect at 45s -> both views say 45s."""
    student_id = fixture["student_a"]["id"]

    first = sync_with_known_session(student_id, 25)
    assert first["total_seconds"] == 25

    # The browser offline lifecycle gate proves the local clock continues
    # while disconnected. Here we model the resulting reconnect payload:
    # the client has accumulated another 20 seconds and sends its absolute
    # local total back to the authoritative server.
    second = sync_with_known_session(student_id, 45)
    assert second["total_seconds"] == 45
    assert second["accepted_seconds"] == 20

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        student_context = browser.new_context()
        admin_context = browser.new_context()
        try:
            student_page = student_context.new_page()
            admin_page = admin_context.new_page()
            browser_login(student_page, fixture["student_a"]["email"], fixture["password"])
            browser_login(admin_page, fixture["admin"]["email"], fixture["password"])

            student = student_view(student_page)
            admin = admin_view(admin_page)

            assert student["total_seconds"] == 45
            assert admin["students"]["study_seconds_today"] == 45
            row = next(
                item for item in admin["students"]["study_top_students"]
                if int(item["id"]) == student_id
            )
            assert row["study_seconds_today"] == 45
        finally:
            student_context.close()
            admin_context.close()
            browser.close()


def test_two_simultaneous_syncs_do_not_double_credit(fixture):
    student_id = fixture["student_a"]["id"]

    # Establish the same baseline the browser would have after a prior
    # reconnect.
    sync_with_known_session(student_id, 100)

    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        try:
            barrier.wait(timeout=10)
            results.append(sync_with_known_session(student_id, 140))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert not errors
    assert sorted(item["accepted_seconds"] for item in results) == [0, 40]

    with app.app_context():
        row = StudyTimeLog.query.filter_by(
            user_id=student_id,
            activity_date=_study_local_date(),
            feature=STUDY_TIME_FEATURE,
        ).one()
        assert row.study_time_seconds == 140


def test_daily_ceiling_is_identical_in_student_and_admin_views(fixture):
    student_id = fixture["student_a"]["id"]
    sync_with_known_session(student_id, MAX_STUDY_TIME_SECONDS_PER_DAY + 99999)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        student_context = browser.new_context()
        admin_context = browser.new_context()
        try:
            student_page = student_context.new_page()
            admin_page = admin_context.new_page()
            browser_login(student_page, fixture["student_a"]["email"], fixture["password"])
            browser_login(admin_page, fixture["admin"]["email"], fixture["password"])

            student = student_view(student_page)
            admin = admin_view(admin_page)

            assert student["total_seconds"] == MAX_STUDY_TIME_SECONDS_PER_DAY
            assert admin["students"]["study_seconds_today"] == MAX_STUDY_TIME_SECONDS_PER_DAY
        finally:
            student_context.close()
            admin_context.close()
            browser.close()


def test_nairobi_day_boundary_is_used_by_admin(fixture):
    student_id = fixture["student_a"]["id"]

    with app.app_context():
        today = _study_local_date()
        yesterday = today - timedelta(days=1)
        StudyTimeLog.query.filter_by(user_id=student_id).delete()
        db.session.add_all([
            StudyTimeLog(
                user_id=student_id,
                activity_date=yesterday,
                feature=STUDY_TIME_FEATURE,
                study_time_seconds=90,
            ),
            StudyTimeLog(
                user_id=student_id,
                activity_date=today,
                feature=STUDY_TIME_FEATURE,
                study_time_seconds=30,
            ),
        ])
        db.session.commit()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        try:
            page = context.new_page()
            browser_login(page, fixture["admin"]["email"], fixture["password"])
            admin = admin_view(page)
            assert admin["students"]["study_seconds_today"] == 30
            assert admin["students"]["study_seconds_7d"] == 120
        finally:
            context.close()
            browser.close()


def test_admin_accounts_are_excluded_and_students_are_isolated(fixture):
    student_a = fixture["student_a"]["id"]
    student_b = fixture["student_b"]["id"]
    admin_id = fixture["admin"]["id"]

    with app.app_context():
        today = _study_local_date()
        StudyTimeLog.query.filter(
            StudyTimeLog.user_id.in_([student_a, student_b, admin_id])
        ).delete(synchronize_session=False)
        db.session.add_all([
            StudyTimeLog(user_id=student_a, activity_date=today, feature=STUDY_TIME_FEATURE, study_time_seconds=40),
            StudyTimeLog(user_id=student_b, activity_date=today, feature=STUDY_TIME_FEATURE, study_time_seconds=70),
            StudyTimeLog(user_id=admin_id, activity_date=today, feature=STUDY_TIME_FEATURE, study_time_seconds=9000),
        ])
        db.session.commit()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        try:
            page = context.new_page()
            browser_login(page, fixture["admin"]["email"], fixture["password"])
            admin = admin_view(page)

            assert admin["students"]["study_seconds_today"] == 110
            ids = {int(item["id"]) for item in admin["students"]["study_top_students"]}
            assert student_a in ids
            assert student_b in ids
            assert admin_id not in ids

            rows = {
                int(item["id"]): item["study_seconds_today"]
                for item in admin["students"]["study_top_students"]
            }
            assert rows[student_a] == 40
            assert rows[student_b] == 70
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
