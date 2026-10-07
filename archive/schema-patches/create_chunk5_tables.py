"""
Chunk 5 patch script (2/2): creates the new tables in the actual
database. Run this AFTER chunk5_models_patch.py has been applied.

db.create_all() only creates tables that don't exist yet - it will
NOT touch or alter your existing tables, so this is safe to re-run.

Usage:
    cd ~/Desktop/prepza
    python create_chunk5_tables.py
"""
from app import app, db

NEW_TABLES = [
    "group", "group_member", "group_post", "group_post_comment",
    "group_post_like", "group_question_vote", "group_file",
    "follow", "notification",
]

with app.app_context():
    before = set(db.inspect(db.engine).get_table_names())
    db.create_all()
    after = set(db.inspect(db.engine).get_table_names())

created = sorted(after - before)
missing = [t for t in NEW_TABLES if t not in after]

if created:
    print("Created tables:", ", ".join(created))
else:
    print("No new tables created (already up to date).")

if missing:
    print("WARNING - expected but still missing:", ", ".join(missing))
