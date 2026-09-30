"""Static admin frontend/backend route contract audit.

This intentionally checks the routes the current Admin UI depends on.
It reads the backend route decorators from app.py and the reconciled admin
runtime modules, then fails if any required endpoint is absent.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

BACKEND_FILES = [
    ROOT / "app.py",
    ROOT / "admin_reconciled_core_a.py",
    ROOT / "admin_reconciled_core_b.py",
    ROOT / "admin_reconciled_opportunities.py",
    ROOT / "admin_reconciled_organisation.py",
    ROOT / "admin_reconciled_ambassadors.py",
    ROOT / "opportunity_expiry_runtime.py",
    ROOT / "auth_otp.py",
]

REQUIRED = {
    "/admin/announcements",
    "/admin/ai-usage",
    "/admin/ai-jobs",
    "/admin/ai-jobs/<int:job_id>/retry",
    "/admin/content-reports",
    "/admin/content-reports/summary",
    "/admin/content-reports/<int:report_id>/dismiss",
    "/admin/content-reports/<int:report_id>/remove",
    "/admin/content-reports/<int:report_id>/warn",
    "/admin/payments",
    "/admin/payments/<int:payment_id>/refund",
    "/admin/analytics",
    "/admin/analytics/universities",
    "/admin/system/capacity",
    "/admin/system/capacity/tier",
    "/admin/users",
    "/admin/users/<int:user_id>",
    "/admin/universities",
    "/admin/universities/<int:university_id>",
    "/admin/programs",
    "/admin/programs/<int:program_id>",
    "/admin/groups",
    "/admin/groups/<int:group_id>",
    "/admin/settings",
    "/admin/opportunities",
    "/admin/opportunities/<int:opportunity_id>/approve",
    "/admin/opportunities/<int:opportunity_id>/reject",
    "/admin/opportunities/<int:opportunity_id>/publish",
    "/admin/opportunities/<int:opportunity_id>/archive",
    "/admin/opportunities/<int:opportunity_id>/remove",
    "/admin/opportunities/sweep-expired",
    "/admin/organisations",
    "/admin/organisations/<int:organisation_id>/verify",
    "/admin/organisations/<int:organisation_id>/reject",
    "/admin/organisations/<int:organisation_id>",
    "/admin/ambassadors",
    "/admin/ambassadors/<int:ambassador_id>",
    "/admin/ambassadors/<int:ambassador_id>/approve",
    "/admin/ambassadors/<int:ambassador_id>/reject",
    "/admin/ambassadors/<int:ambassador_id>/suspend",
    "/admin/ambassadors/<int:ambassador_id>/reinstate",
    "/admin/payouts",
    "/admin/payouts/<int:payout_id>/approve",
    "/admin/payouts/<int:payout_id>/reject",
    "/admin/payouts/<int:payout_id>/sync-status",
    "/admin/auth/otp",
}

ROUTE_RE = re.compile(r"@app\.(?:route|get|post|put|patch|delete|options|head)\(\s*[\"']([^\"']+)[\"']")

def main():
    routes = set()
    for path in BACKEND_FILES:
        if not path.exists():
            print(f"ERROR missing backend runtime file: {path}")
            return 1
        routes.update(ROUTE_RE.findall(path.read_text(encoding="utf-8")))

    missing = sorted(REQUIRED - routes)
    if missing:
        print("ADMIN ROUTE CONTRACT FAILED")
        for route in missing:
            print(f"  MISSING {route}")
        return 1

    print(f"ADMIN ROUTE CONTRACT OK: {len(REQUIRED)} required routes present")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
