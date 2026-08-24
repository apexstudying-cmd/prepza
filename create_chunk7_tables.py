"""
Chunk 7 patch 2/N: create the 4 new tables for Opportunities +
Organisation portal.

Deliberately creates ONLY these 4 tables, one at a time, with
checkfirst=True - not a blanket db.create_all() - so it can't
accidentally create some other unrelated table that happens to be
missing for a different reason, and so you get clear per-table
feedback about what actually happened.

Tables:
  organisation
  organisation_member
  opportunity
  opportunity_promotion

Safe to re-run: each table is skipped if it already exists.

Usage:
    cd ~/Desktop/prepza
    python create_chunk7_tables.py
"""

import app as appmod
from sqlalchemy import inspect

MODELS = [
    appmod.Organisation,
    appmod.OrganisationMember,
    appmod.Opportunity,
    appmod.OpportunityPromotion,
]


def main():
    with appmod.app.app_context():
        engine = appmod.db.engine
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())

        for model in MODELS:
            table_name = model.__tablename__
            if table_name in existing_tables:
                print(f"SKIP  {table_name} (already exists)")
                continue
            model.__table__.create(bind=engine, checkfirst=True)
            print(f"CREATE {table_name}")

        # Re-inspect to confirm what actually landed.
        inspector = inspect(engine)
        final_tables = set(inspector.get_table_names())
        missing = [m.__tablename__ for m in MODELS if m.__tablename__ not in final_tables]
        if missing:
            print(f"WARNING: these tables still don't exist after running: {missing}")
        else:
            print("All 4 tables confirmed present.")


if __name__ == "__main__":
    main()
