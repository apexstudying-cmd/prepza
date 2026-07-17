"""
Patch script: fix reset-password email link.

Problem:
    The reset-password email links to /reset-password?token=...
    but that path is a POST-only API route (used by the page's JS),
    not the actual page. Clicking the email link does a GET request
    to a POST-only route, so Flask returns "405 Method Not Allowed".

Fix:
    Point the emailed link at the actual static page instead:
    /static/reset-password.html?token=...
    The page's own JS will still POST to /reset-password when the
    student submits their new password, so that route is untouched.

Usage:
    cd ~/Desktop/prepza
    python fix_reset_link.py
"""

import pathlib

APP_FILE = pathlib.Path("app.py")

OLD = 'reset_link = f"{BASE_URL}/reset-password?token={token}"'
NEW = 'reset_link = f"{BASE_URL}/static/reset-password.html?token={token}"'


def main():
    if not APP_FILE.exists():
        raise SystemExit(
            "ERROR: app.py not found in the current directory.\n"
            "Make sure you're in ~/Desktop/prepza before running this "
            "(run 'cd ~/Desktop/prepza' first)."
        )

    text = APP_FILE.read_text(encoding="utf-8")

    count = text.count(OLD)
    assert count != 0, (
        "Could not find the expected line in app.py:\n"
        f"    {OLD}\n"
        "Nothing was changed. This likely means the line has already "
        "been changed, or the file differs from what we expect — "
        "let's check together before editing further."
    )
    assert count == 1, (
        f"Expected exactly ONE match for the line, but found {count}. "
        "Refusing to guess which one to change — let's look at this together."
    )

    text = text.replace(OLD, NEW)
    APP_FILE.write_text(text, encoding="utf-8")

    print("✅ Patched app.py successfully.")
    print(f"   Old: {OLD}")
    print(f"   New: {NEW}")
    print()
    print("Next steps:")
    print("  1. Review the change:  git diff app.py")
    print("  2. Restart your local Flask server if it's running")
    print("  3. Test: trigger a password reset and check the emailed link")
    print("  4. Commit: git add app.py && git commit -m 'Fix reset-password email link'")
    print("  5. Push and let Render redeploy: git push")


if __name__ == "__main__":
    main()
