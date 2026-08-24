"""
Prepza - Audit Logging companion script.

Creates the new `audit_log` table added by audit_logging_patch.py.
Safe to re-run - db.create_all() only creates tables that don't
already exist, it never touches or drops existing ones.

Usage (after running audit_logging_patch.py):
    cd ~/Desktop/prepza
    python create_audit_log_table.py
"""

from sqlalchemy import inspect

import app as appmod

with appmod.app.app_context():
    before = set(inspect(appmod.db.engine).get_table_names())
    appmod.db.create_all()
    after = set(inspect(appmod.db.engine).get_table_names())

    created = after - before
    if created:
        print(f"Created table(s): {', '.join(sorted(created))}")
    else:
        print("No new tables created (already existed).")

    print("audit_log present:", "audit_log" in after)
