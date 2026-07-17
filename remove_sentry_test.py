"""
Removes the temporary /sentry-test route now that Sentry is confirmed working.
Run this once from inside your prepza folder: python remove_sentry_test.py
"""

path = "app.py"
content = open(path, encoding="utf-8").read()

old = (
    '@app.route("/sentry-test")\n'
    'def sentry_test():\n'
    '    1 / 0  # Deliberately crashes to confirm Sentry catches it\n'
    '    return "unreachable"\n'
    '\n'
    '\n'
    '@app.route("/")'
)
new = '@app.route("/")'

assert old in content, "Anchor not found - the test route may already be removed, or was edited"
assert content.count(old) == 1, "Anchor not unique - aborting to be safe"

content = content.replace(old, new, 1)
open(path, "w", encoding="utf-8").write(content)
print("Removed /sentry-test route successfully")
