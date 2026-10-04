"""Build a first-pass behavior-coverage matrix for every registered Flask route.

This tool is deliberately conservative:
- it reads the runtime Flask URL map;
- it scans tests/ for literal route strings;
- it does NOT claim a route is behaviorally covered merely because its path
  appears in a test;
- it reports routes that have no obvious test reference so they can be mapped
  to real scenarios next.

Run inside the normal local QA container:
    python tools/route_coverage_matrix.py

The output is an audit aid, not a substitute for behavior tests.
"""

from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app


ROUTE_LITERAL_RE = re.compile(
    r"""["'](/[^"']*)["']"""
)


def _test_route_literals() -> dict[str, set[str]]:
    """Return route-looking string literals grouped by test file."""
    found: dict[str, set[str]] = defaultdict(set)
    tests_root = ROOT / "tests"
    if not tests_root.exists():
        return found

    for path in sorted(tests_root.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError):
            continue

        # Keep both ordinary string constants and f-string source literals.
        # Real route calls commonly look like f"/groups/{group_id}".
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value
                if value.startswith("/") and not value.startswith("//"):
                    found[str(path.relative_to(ROOT))].add(value)

        for match in re.finditer(r'''(?i)(?:f|r|fr|rf)?["'](/[^"']*)["']''', source):
            value = match.group(1)
            if value.startswith("/") and not value.startswith("//"):
                found[str(path.relative_to(ROOT))].add(value)
    return found


def _normalize_for_matching(value: str) -> str:
    """Turn a concrete test URL into a comparable Flask rule shape."""
    value = value.split("?", 1)[0]
    value = re.sub(r"/[0-9]+(?=/|$)", "/<int>", value)
    return value


def _best_route_matches(route: str, literals: set[str]) -> set[str]:
    matches = set()
    for literal in literals:
        normalized = _normalize_for_matching(literal)
        if normalized == route:
            matches.add(literal)
            continue

        # Test strings may contain f-string fragments such as
        # /groups/{group_id}; normalize those to the corresponding converter.
        candidate = re.sub(r"\{[^}]+\}", "<int>", normalized)
        route_shape = re.sub(r"<int:[^>]+>", "<int>", route)
        route_shape = re.sub(r"<string:[^>]+>", "<string>", route_shape)
        if candidate == route_shape:
            matches.add(literal)
    return matches


def main() -> None:
    tests = _test_route_literals()

    routes = []
    for rule in app.url_map.iter_rules():
        methods = sorted(rule.methods - {"HEAD", "OPTIONS"})
        if rule.endpoint == "static":
            continue
        routes.append(
            {
                "path": rule.rule,
                "methods": methods,
                "endpoint": rule.endpoint,
            }
        )

    routes.sort(key=lambda row: (row["path"], tuple(row["methods"]), row["endpoint"]))

    all_literals = set().union(*tests.values()) if tests else set()
    covered = []
    uncovered = []
    route_test_files: dict[tuple[str, str], set[str]] = defaultdict(set)

    for route in routes:
        matches = _best_route_matches(route["path"], all_literals)
        key = (route["path"], ",".join(route["methods"]))
        for test_file, literals in tests.items():
            if _best_route_matches(route["path"], literals):
                route_test_files[key].add(test_file)

        row = dict(route)
        row["test_files"] = sorted(route_test_files[key])
        row["literal_matches"] = sorted(matches)
        if matches:
            covered.append(row)
        else:
            uncovered.append(row)

    domain_counts = Counter()
    for route in routes:
        path = route["path"]
        if path.startswith("/admin") or path.startswith("/api/admin"):
            domain = "admin"
        elif path.startswith("/api/organisations") or path.startswith("/organisations"):
            domain = "b2b_organisation"
        elif path.startswith("/api/discovery"):
            domain = "b2b_discovery"
        elif path.startswith("/api/opportunities") or path.startswith("/opportunities"):
            domain = "opportunities"
        elif path.startswith("/chats") or path.startswith("/message-requests"):
            domain = "chat"
        elif path.startswith("/documents") or path.startswith("/ai-jobs"):
            domain = "documents_ai"
        elif path.startswith("/groups"):
            domain = "groups"
        elif path.startswith("/library") or path.startswith("/content"):
            domain = "library_content"
        elif path.startswith("/subscription") or path.startswith("/payment") or path.startswith("/orders"):
            domain = "payments_subscriptions"
        elif path.startswith("/ambassador"):
            domain = "ambassador"
        elif path.startswith("/study-time") or path.startswith("/streak") or path.startswith("/xp") or path.startswith("/gamification") or path.startswith("/achievements"):
            domain = "study_gamification"
        elif path.startswith("/profile") or path.startswith("/users") or path.startswith("/students"):
            domain = "social_profile"
        elif path.startswith("/internal"):
            domain = "internal_control"
        elif path.startswith("/auth") or path in {"/login", "/logout", "/signup", "/me", "/forgot-password", "/reset-password", "/verify-email", "/verify-email/confirm", "/verify-otp", "/resend-verification", "/change-email", "/change-password", "/delete-account"}:
            domain = "auth_account"
        elif path.startswith("/notifications") or path.startswith("/notification-preferences") or path.startswith("/push"):
            domain = "notifications_push"
        elif path in {"/universities"} or path.startswith("/universities/"):
            domain = "academic_lookup"
        elif path.startswith("/analytics"):
            domain = "analytics"
        elif path in {"/", "/health", "/sw.js"}:
            domain = "platform"
        else:
            domain = "other"
        domain_counts[domain] += 1

    print(f"TOTAL_APPLICATION_ROUTES={len(routes)}")
    print(f"ROUTES_WITH_OBVIOUS_TEST_REFERENCE={len(covered)}")
    print(f"ROUTES_WITHOUT_OBVIOUS_TEST_REFERENCE={len(uncovered)}")
    print()
    print("DOMAIN COUNTS")
    for domain, count in sorted(domain_counts.items()):
        print(f"{domain}={count}")

    print()
    print("COVERAGE MATRIX")
    print("STATUS | DOMAIN | METHODS | PATH | ENDPOINT | TEST FILES")

    for row in routes:
        path = row["path"]
        if path.startswith("/admin") or path.startswith("/api/admin"):
            domain = "admin"
        elif path.startswith("/api/organisations") or path.startswith("/organisations"):
            domain = "b2b_organisation"
        elif path.startswith("/api/discovery"):
            domain = "b2b_discovery"
        elif path.startswith("/api/opportunities") or path.startswith("/opportunities"):
            domain = "opportunities"
        elif path.startswith("/chats") or path.startswith("/message-requests"):
            domain = "chat"
        elif path.startswith("/documents") or path.startswith("/ai-jobs"):
            domain = "documents_ai"
        elif path.startswith("/groups"):
            domain = "groups"
        elif path.startswith("/library") or path.startswith("/content"):
            domain = "library_content"
        elif path.startswith("/subscription") or path.startswith("/payment") or path.startswith("/orders"):
            domain = "payments_subscriptions"
        elif path.startswith("/ambassador"):
            domain = "ambassador"
        elif path.startswith("/study-time") or path.startswith("/streak") or path.startswith("/xp") or path.startswith("/gamification") or path.startswith("/achievements"):
            domain = "study_gamification"
        elif path.startswith("/profile") or path.startswith("/users") or path.startswith("/students"):
            domain = "social_profile"
        elif path.startswith("/internal"):
            domain = "internal_control"
        elif path.startswith("/auth") or path in {"/login", "/logout", "/signup", "/me", "/forgot-password", "/reset-password", "/verify-email", "/verify-email/confirm", "/verify-otp", "/resend-verification", "/change-email", "/change-password", "/delete-account"}:
            domain = "auth_account"
        elif path.startswith("/notifications") or path.startswith("/notification-preferences") or path.startswith("/push"):
            domain = "notifications_push"
        elif path in {"/universities"} or path.startswith("/universities/"):
            domain = "academic_lookup"
        elif path.startswith("/analytics"):
            domain = "analytics"
        elif path in {"/", "/health", "/sw.js"}:
            domain = "platform"
        else:
            domain = "other"

        key = (row["path"], ",".join(row["methods"]))
        files = sorted(route_test_files.get(key, set()))
        status = "REFERENCED" if files else "UNMAPPED"
        print(
            f"{status} | {domain} | {','.join(row['methods'])} | "
            f"{row['path']} | {row['endpoint']} | {', '.join(files) or '-'}"
        )


if __name__ == "__main__":
    main()
