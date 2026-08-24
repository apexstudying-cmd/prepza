"""
Prepza - Chunk 2 migration: creates the document_content, document, and
generated_material tables.

Run from the repo root, after patch_document_system.py has already been
applied and your local virtualenv has the project's dependencies installed:

    python migrate_document_system.py

This imports app.py directly, so it reuses the exact same DATABASE_URL your
app already reads from .env - no Supabase SQL editor needed. Safe to re-run:
create_all() only creates tables that don't already exist yet; it never
touches or drops existing tables/rows, including the three new ones if this
is run twice.
"""

from app import app, db, DocumentContent, Document, GeneratedMaterial

with app.app_context():
    tables = [
        DocumentContent.__table__,
        Document.__table__,
        GeneratedMaterial.__table__,
    ]
    db.metadata.create_all(bind=db.engine, tables=tables)
    print("Migration complete. Created (or already present):")
    for t in tables:
        print(f"  - {t.name}")
