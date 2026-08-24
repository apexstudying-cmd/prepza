"""
Prepza - Chunk 7, Step 6 companion script.

Creates the new `saved_opportunity` table added by
chunk7_opportunity_browse_patch.py. Safe to re-run - db.create_all()
only creates tables that don't already exist, it never touches or
drops existing ones.

Usage (after running chunk7_opportunity_browse_patch.py):
    cd ~/Desktop/prepza
    python create_saved_opportunity_table.py
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

    print("saved_opportunity present:", "saved_opportunity" in after)
