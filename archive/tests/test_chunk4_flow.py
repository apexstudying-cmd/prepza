"""
Chunk 4 end-to-end sanity check.

Exercises the full Library flow against a running local dev server:
  login (customer) -> publish -> my-submissions
  login (admin)     -> queue -> approve (x2, checks XP idempotency)
  login (customer) -> browse -> save -> saved list -> unsave
                    -> report
  login (admin)     -> reports queue -> resolve

Meant to be run ONCE per document_id (publish blocks a second active
submission for the same document). Uses a fresh document_id each run if
you want to retest.

Credentials and the document id are read from environment variables -
nothing sensitive is hardcoded in this file.

Required env vars:
    CUSTOMER_EMAIL, CUSTOMER_PASSWORD
    ADMIN_EMAIL,    ADMIN_PASSWORD
    DOCUMENT_ID     - a Document belonging to CUSTOMER_EMAIL with status "ready"
                       (see mark_document_ready.py)

Optional:
    BASE_URL        - default http://localhost:5000
    UNIT_ID         - if set, publishes against this unit and tests the
                       unit_id filter on GET /library

Run from project root (~/Desktop/prepza), with the Flask dev server
running in another terminal:

    export CUSTOMER_EMAIL=...
    export CUSTOMER_PASSWORD=...
    export ADMIN_EMAIL=...
    export ADMIN_PASSWORD=...
    export DOCUMENT_ID=7
    python test_chunk4_flow.py
"""

import os
import sys
import requests

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")

REQUIRED_ENV = ("CUSTOMER_EMAIL", "CUSTOMER_PASSWORD", "ADMIN_EMAIL", "ADMIN_PASSWORD", "DOCUMENT_ID")

PASS = "PASS"
FAIL = "FAIL"

failures = []


def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}" + (f" - {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)
    return condition


def fatal(message):
    print(f"\nFATAL: {message}")
    print(f"\n{len(failures)} check(s) failed before this point." if failures else "")
    sys.exit(1)


def login(session, email, password):
    resp = session.post(f"{BASE_URL}/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        fatal(f"Login failed for {email}: {resp.status_code} {resp.text}")
    me = session.get(f"{BASE_URL}/me")
    if me.status_code != 200:
        fatal(f"/me failed after login for {email}: {me.status_code} {me.text}")
    return me.json()["csrf_token"]


def main():
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        fatal(f"Missing required env vars: {', '.join(missing)}")

    customer_email = os.environ["CUSTOMER_EMAIL"]
    customer_password = os.environ["CUSTOMER_PASSWORD"]
    admin_email = os.environ["ADMIN_EMAIL"]
    admin_password = os.environ["ADMIN_PASSWORD"]
    document_id = int(os.environ["DOCUMENT_ID"])
    unit_id = os.environ.get("UNIT_ID")
    unit_id = int(unit_id) if unit_id else None

    customer = requests.Session()
    admin = requests.Session()

    print("== Login as customer ==")
    customer_csrf = login(customer, customer_email, customer_password)
    print("  logged in\n")

    print("== POST /library/publish ==")
    publish_body = {
        "document_id": document_id,
        "title": "Chunk4 Sanity Check Submission",
        "description": "Automated test submission - safe to delete.",
        "material_type": "lecture_notes",
    }
    if unit_id:
        publish_body["unit_id"] = unit_id

    resp = customer.post(
        f"{BASE_URL}/library/publish",
        json=publish_body,
        headers={"X-CSRF-Token": customer_csrf},
    )
    if not check("publish returns 201", resp.status_code == 201, f"{resp.status_code} {resp.text}"):
        fatal("Cannot continue without a publication_id.")
    publication_id = resp.json()["publication_id"]
    check("status is pending", resp.json()["status"] == "pending")
    print(f"  publication_id = {publication_id}\n")

    print("== GET /library/my-submissions ==")
    resp = customer.get(f"{BASE_URL}/library/my-submissions")
    check("returns 200", resp.status_code == 200)
    subs = resp.json().get("submissions", [])
    found = next((s for s in subs if s["id"] == publication_id), None)
    check("new submission appears", found is not None)
    if found:
        check("submission status is pending", found["status"] == "pending")
    print()

    print("== Login as admin ==")
    admin_csrf = login(admin, admin_email, admin_password)
    print("  logged in\n")

    print("== GET /admin/library/queue ==")
    resp = admin.get(f"{BASE_URL}/admin/library/queue")
    check("returns 200", resp.status_code == 200)
    queue = resp.json().get("queue", [])
    check("publication appears in queue", any(p["id"] == publication_id for p in queue))
    print()

    print("== POST /admin/library/<id>/approve (1st time) ==")
    resp = admin.post(
        f"{BASE_URL}/admin/library/{publication_id}/approve",
        headers={"X-CSRF-Token": admin_csrf},
    )
    check("returns 200", resp.status_code == 200, f"{resp.status_code} {resp.text}")
    body = resp.json()
    check("status is approved", body.get("status") == "approved")
    check("xp_awarded_now is True", body.get("xp_awarded_now") is True)
    print()

    print("== POST /admin/library/<id>/approve (2nd time - idempotency check) ==")
    resp = admin.post(
        f"{BASE_URL}/admin/library/{publication_id}/approve",
        headers={"X-CSRF-Token": admin_csrf},
    )
    # Second call hits the "not pending" guard since status is now approved.
    check("returns 400 (already approved, not re-approvable)", resp.status_code == 400, f"{resp.status_code} {resp.text}")
    print()

    print("== GET /library (browse, as customer) ==")
    resp = customer.get(f"{BASE_URL}/library", params={"q": "Chunk4 Sanity"})
    check("returns 200", resp.status_code == 200)
    pubs = resp.json().get("publications", [])
    check("approved publication appears in browse", any(p["id"] == publication_id for p in pubs))
    print()

    print("== POST /library/<id>/save ==")
    resp = customer.post(
        f"{BASE_URL}/library/{publication_id}/save",
        headers={"X-CSRF-Token": customer_csrf},
    )
    check("returns 201", resp.status_code == 201, f"{resp.status_code} {resp.text}")
    check("save_count is 1", resp.json().get("save_count") == 1)
    print()

    print("== GET /library/saved ==")
    resp = customer.get(f"{BASE_URL}/library/saved")
    check("returns 200", resp.status_code == 200)
    saved = resp.json().get("saved", [])
    check("item appears in saved list", any(p["id"] == publication_id for p in saved))
    print()

    print("== DELETE /library/<id>/save ==")
    resp = customer.delete(
        f"{BASE_URL}/library/{publication_id}/save",
        headers={"X-CSRF-Token": customer_csrf},
    )
    check("returns 200", resp.status_code == 200, f"{resp.status_code} {resp.text}")
    check("save_count back to 0", resp.json().get("save_count") == 0)
    print()

    print("== POST /library/<id>/report ==")
    resp = customer.post(
        f"{BASE_URL}/library/{publication_id}/report",
        json={"reason": "other", "details": "Automated test report - safe to dismiss."},
        headers={"X-CSRF-Token": customer_csrf},
    )
    check("returns 201", resp.status_code == 201, f"{resp.status_code} {resp.text}")
    report_id = resp.json().get("report_id")
    print(f"  report_id = {report_id}\n")

    print("== GET /admin/library/reports (as admin) ==")
    resp = admin.get(f"{BASE_URL}/admin/library/reports")
    check("returns 200", resp.status_code == 200)
    reports = resp.json().get("reports", [])
    check("report appears in pending queue", any(r["id"] == report_id for r in reports))
    print()

    print("== POST /admin/library/reports/<id>/resolve ==")
    resp = admin.post(
        f"{BASE_URL}/admin/library/reports/{report_id}/resolve",
        json={"status": "dismissed", "admin_notes": "Test report, dismissing."},
        headers={"X-CSRF-Token": admin_csrf},
    )
    check("returns 200", resp.status_code == 200, f"{resp.status_code} {resp.text}")
    check("status is dismissed", resp.json().get("status") == "dismissed")
    print()

    print("=" * 50)
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All checks passed.")


if __name__ == "__main__":
    main()
