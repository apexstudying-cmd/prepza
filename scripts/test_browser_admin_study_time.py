"""Browser/runtime equality gate for student and admin Study Hub time."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from http.cookies import SimpleCookie
from uuid import uuid4

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("PREPZA_BROWSER_BASE_URL", "http://localhost:5000")
COMPOSE_FILE = os.environ.get("PREPZA_COMPOSE_FILE", "docker-compose.vps.yml")
PASSWORD = "AdminStudyTime!12345"


def run_container_python(code: str) -> str:
    # The test runs inside the app container. Docker is not installed there,
    # so invoke a second Python process in the same container instead.
    result = subprocess.run(
        [sys.executable, "-"],
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
    code = """
import json
from uuid import uuid4
from werkzeug.security import generate_password_hash
from app import app, db, User

with app.app_context():
    suffix = uuid4().hex
    users = []
    for label, is_admin in (("student-a", False), ("student-b", False), ("admin", True)):
        user = User(
            email=f"admin-study-time.{label}-{suffix}@test.invalid",
            password_hash=generate_password_hash("__PASSWORD__"),
            year=2, semester=1,
            display_name=f"Admin Study Time {label}",
            email_verified=True, is_admin=is_admin, is_suspended=False,
            profile_visibility="public", who_can_message="everyone",
            who_can_follow="everyone", read_receipts_enabled=True,
            university_id=None, program_id=None, session_version=0,
        )
        db.session.add(user)
        users.append(user)
    db.session.commit()
    print(json.dumps({
        "student_a": {"id": users[0].id, "email": users[0].email},
        "student_b": {"id": users[1].id, "email": users[1].email},
        "admin": {"id": users[2].id, "email": users[2].email},
        "password": "__PASSWORD__",
    }))
""".replace("__PASSWORD__", PASSWORD)
    return json.loads(run_container_python(code).splitlines()[-1])


def cleanup_fixture(fixture: dict) -> None:
    ids = [fixture["student_a"]["id"], fixture["student_b"]["id"], fixture["admin"]["id"]]
    code = """
from app import app, db, User, UserKey, StudyTimeLog, StudyStreak, XpEvent
with app.app_context():
    ids = __IDS__
    StudyTimeLog.query.filter(StudyTimeLog.user_id.in_(ids)).delete(synchronize_session=False)
    StudyStreak.query.filter(StudyStreak.user_id.in_(ids)).delete(synchronize_session=False)
    XpEvent.query.filter(XpEvent.user_id.in_(ids)).delete(synchronize_session=False)
    # UserKey has a deliberate non-cascading FK to User, matching the
    # production account-deletion contract. Remove fixture-owned E2EE
    # identity rows before deleting the fixture users.
    # UserKey deliberately has a non-cascading FK to User. Commit child-row
    # deletion before loading/deleting parent users so ORM autoflush cannot
    # race the FK cleanup.
    UserKey.query.filter(UserKey.user_id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    db.session.expire_all()
    for user_id in ids:
        user = db.session.get(User, user_id)
        if user is not None:
            db.session.delete(user)
    db.session.commit()
""".replace("__IDS__", repr(ids))
    run_container_python(code)


@pytest.fixture(scope="module")
def fixture():
    data = create_fixture()
    yield data
    cleanup_fixture(data)


def clear_study_time(user_id: int) -> None:
    """Reset only this fixture student's study rows before an isolated case."""
    code = """
from app import app, db, StudyTimeLog
with app.app_context():
    StudyTimeLog.query.filter_by(user_id=__USER_ID__).delete(synchronize_session=False)
    db.session.commit()
print("OK")
""".replace("__USER_ID__", str(user_id))
    assert run_container_python(code).splitlines()[-1] == "OK"

def browser_login(page, email: str, password: str) -> None:
    response = page.request.post(
        f"{BASE_URL}/login",
        data=json.dumps({"email": email, "password": password}),
        headers={"Content-Type": "application/json"},
    )
    if not response.ok:
        raise RuntimeError(f"/login failed: {response.status} {response.text()}")

    # Flask marks the production session cookie Secure. Because this disposable
    # QA browser talks to the app over internal HTTP, Chromium may refuse to
    # store that Set-Cookie header at all. Read the real cookie from the login
    # response, then re-add the same value to this test context with Secure
    # disabled. Production configuration remains unchanged.
    set_cookie = response.headers.get("set-cookie")
    if not set_cookie:
        raise RuntimeError("Expected /login to return a session Set-Cookie header")

    parsed = SimpleCookie()
    parsed.load(set_cookie)
    morsel = parsed.get("session")
    if morsel is None:
        raise RuntimeError(
            "Expected /login Set-Cookie to contain the session cookie; "
            f"header={set_cookie!r}"
        )

    cookie = {
        "name": "session",
        "value": morsel.value,
        "url": BASE_URL,
        "path": morsel["path"] or "/",
        "secure": False,
        "httpOnly": bool(morsel["httponly"]),
    }
    same_site = (morsel["samesite"] or "").lower()
    if same_site in {"lax", "strict", "none"}:
        cookie["sameSite"] = same_site.capitalize()

    page.context.clear_cookies(name="session")
    page.context.add_cookies([cookie])
    # page.request shares cookies with this browser context, so authenticated
    # API requests use the real session. Production configuration remains Secure.


def browser_json(page, path: str) -> dict:
    response = page.request.get(BASE_URL + path)
    if not response.ok:
        raise RuntimeError(f"GET {path} failed: {response.status} {response.text}")
    return response.json()


def student_view(page) -> dict:
    return browser_json(page, "/study-time?period=day")


def admin_view(page) -> dict:
    return browser_json(page, "/admin/operations")


def sync_with_known_session(user_id: int, total_seconds: int) -> dict:
    code = """
import json
from app import app
with app.app_context():
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = __USER_ID__
        session["_session_version"] = 0
        session["csrf_token"] = "admin-study-time-test-csrf"
    response = client.post(
        "/study-time/sync",
        json={"total_seconds": __TOTAL__},
        headers={"X-CSRF-Token": "admin-study-time-test-csrf"},
    )
    print(json.dumps({"status": response.status_code, "body": response.get_json()}))
""".replace("__USER_ID__", str(user_id)).replace("__TOTAL__", str(total_seconds))
    result = json.loads(run_container_python(code).splitlines()[-1])
    assert result["status"] == 200, result
    return result["body"]


def test_student_and_admin_views_agree_after_reconnect_reconciliation(fixture):
    """25s online -> offline +20s -> reconnect at 45s -> both views say 45s."""
    student_id = fixture["student_a"]["id"]
    clear_study_time(student_id)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        student_context = browser.new_context()
        admin_context = browser.new_context()
        try:
            student_page = student_context.new_page()
            admin_page = admin_context.new_page()
            browser_login(student_page, fixture["student_a"]["email"], fixture["password"])
            browser_login(admin_page, fixture["admin"]["email"], fixture["password"])
            baseline = admin_view(admin_page)["students"]["study_seconds_today"]

            # The dedicated browser offline lifecycle gate proves the local
            # clock continues while disconnected. Here we verify that an
            # absolute 45s reconnect total reconciles into PostgreSQL.
            assert sync_with_known_session(student_id, 25)["total_seconds"] == 25
            result = sync_with_known_session(student_id, 45)
            assert result["total_seconds"] == 45
            assert result["accepted_seconds"] == 20

            student = student_view(student_page)
            admin = admin_view(admin_page)
            assert student["total_seconds"] == 45
            assert admin["students"]["study_seconds_today"] == baseline + 45
            row = next(x for x in admin["students"]["study_top_students"] if int(x["id"]) == student_id)
            assert row["study_seconds_today"] == 45
        finally:
            student_context.close()
            admin_context.close()
            browser.close()

def test_two_simultaneous_syncs_do_not_double_credit(fixture):
    student_id = fixture["student_a"]["id"]
    sync_with_known_session(student_id, 100)

    code = """
import json
import threading
from app import app, StudyTimeLog, STUDY_TIME_FEATURE, _study_local_date

barrier = threading.Barrier(2)
results = []
errors = []

def sync_once():
    with app.app_context():
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = __USER_ID__
            session["_session_version"] = 0
            session["csrf_token"] = "admin-study-time-test-csrf"
        barrier.wait(timeout=10)
        response = client.post(
            "/study-time/sync",
            json={"total_seconds": 140},
            headers={"X-CSRF-Token": "admin-study-time-test-csrf"},
        )
        results.append((response.status_code, response.get_json()))

def worker():
    try:
        sync_once()
    except Exception as exc:
        errors.append(repr(exc))

threads = [threading.Thread(target=worker) for _ in range(2)]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join(timeout=20)

assert not errors, errors
assert len(results) == 2
assert all(status == 200 for status, _ in results)
assert sorted(body["accepted_seconds"] for _, body in results) == [0, 40]

with app.app_context():
    row = StudyTimeLog.query.filter_by(
        user_id=__USER_ID__, activity_date=_study_local_date(), feature=STUDY_TIME_FEATURE
    ).one()
    assert row.study_time_seconds == 140

print("OK")
""".replace("__USER_ID__", str(student_id))
    assert run_container_python(code).splitlines()[-1] == "OK"


def test_daily_ceiling_is_identical_in_student_and_admin_views(fixture):
    student_id = fixture["student_a"]["id"]
    clear_study_time(student_id)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-features=HttpsUpgrades"],
        )
        student_context = browser.new_context()
        admin_context = browser.new_context()
        try:
            student_page = student_context.new_page()
            admin_page = admin_context.new_page()
            browser_login(student_page, fixture["student_a"]["email"], fixture["password"])
            browser_login(admin_page, fixture["admin"]["email"], fixture["password"])
            baseline = admin_view(admin_page)["students"]["study_seconds_today"]
            sync_with_known_session(student_id, 999999999)
            student = student_view(student_page)
            admin = admin_view(admin_page)
            assert student["total_seconds"] == 43200
            assert admin["students"]["study_seconds_today"] == baseline + 43200
        finally:
            student_context.close()
            admin_context.close()
            browser.close()


def test_nairobi_day_boundary_is_used_by_admin(fixture):
    student_id = fixture["student_a"]["id"]
    clear_study_time(student_id)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-features=HttpsUpgrades"],
        )
        context = browser.new_context()
        try:
            page = context.new_page()
            browser_login(page, fixture["admin"]["email"], fixture["password"])
            baseline = admin_view(page)["students"]

            code = """
from app import app, db, StudyTimeLog, STUDY_TIME_FEATURE, _study_local_date
from datetime import timedelta
with app.app_context():
    today = _study_local_date()
    yesterday = today - timedelta(days=1)
    StudyTimeLog.query.filter_by(user_id=__USER_ID__).delete()
    db.session.add_all([
        StudyTimeLog(user_id=__USER_ID__, activity_date=yesterday, feature=STUDY_TIME_FEATURE, study_time_seconds=90),
        StudyTimeLog(user_id=__USER_ID__, activity_date=today, feature=STUDY_TIME_FEATURE, study_time_seconds=30),
    ])
    db.session.commit()
print("OK")
""".replace("__USER_ID__", str(student_id))
            assert run_container_python(code).splitlines()[-1] == "OK"

            admin = admin_view(page)
            assert admin["students"]["study_seconds_today"] == baseline["study_seconds_today"] + 30
            assert admin["students"]["study_seconds_7d"] == baseline["study_seconds_7d"] + 120
        finally:
            context.close()
            browser.close()

def test_admin_accounts_are_excluded_and_students_are_isolated(fixture):
    student_a = fixture["student_a"]["id"]
    student_b = fixture["student_b"]["id"]
    admin_id = fixture["admin"]["id"]

    clear_study_time(student_a)
    clear_study_time(student_b)
    clear_study_time(admin_id)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-features=HttpsUpgrades"],
        )
        context = browser.new_context()
        try:
            page = context.new_page()
            browser_login(page, fixture["admin"]["email"], fixture["password"])
            # Take the aggregate baseline before introducing the fixture's
            # student/admin study rows. The endpoint intentionally reports
            # all non-admin students globally.
            baseline = admin_view(page)["students"]["study_seconds_today"]

            code = """
from app import app, db, StudyTimeLog, STUDY_TIME_FEATURE, _study_local_date
with app.app_context():
    today = _study_local_date()
    ids = [__A__, __B__, __ADMIN__]
    StudyTimeLog.query.filter(StudyTimeLog.user_id.in_(ids)).delete(synchronize_session=False)
    db.session.add_all([
        StudyTimeLog(user_id=__A__, activity_date=today, feature=STUDY_TIME_FEATURE, study_time_seconds=40),
        StudyTimeLog(user_id=__B__, activity_date=today, feature=STUDY_TIME_FEATURE, study_time_seconds=70),
        StudyTimeLog(user_id=__ADMIN__, activity_date=today, feature=STUDY_TIME_FEATURE, study_time_seconds=9000),
    ])
    db.session.commit()
print("OK")
""".replace("__A__", str(student_a)).replace("__B__", str(student_b)).replace("__ADMIN__", str(admin_id))
            assert run_container_python(code).splitlines()[-1] == "OK"

            admin = admin_view(page)
            assert admin["students"]["study_seconds_today"] == baseline + 110
            ids = {int(x["id"]) for x in admin["students"]["study_top_students"]}
            assert student_a in ids and student_b in ids and admin_id not in ids
            rows = {int(x["id"]): x["study_seconds_today"] for x in admin["students"]["study_top_students"]}
            assert rows[student_a] == 40
            assert rows[student_b] == 70
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# /admin/operations intentionally reports a global non-admin-student aggregate.
# Browser assertions therefore compare fixture contributions against a live baseline
# and assert exact fixture-student rows instead of assuming an empty database.
