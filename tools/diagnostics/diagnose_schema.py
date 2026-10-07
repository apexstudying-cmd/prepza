"""
Schema drift diagnostic - compares what app.py's models expect against
what actually exists in the live database, and prints exactly what's
missing. Does NOT change anything - read-only.

Usage:
    cd ~/desktop/prepza
    python diagnose_schema.py
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not found - make sure .env is present in this folder.")

# Import the actual app + db so we get the REAL current models, not a
# hand-copied list that could drift from app.py itself.
import app as prepza_app  # noqa: E402

def main():
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    live_tables = set(inspector.get_table_names())

    print(f"Live tables in DB: {len(live_tables)}")
    print()

    problems = []

    for table_name, table in prepza_app.db.metadata.tables.items():
        if table_name not in live_tables:
            problems.append(f"MISSING TABLE: {table_name}")
            continue

        live_columns = {col["name"] for col in inspector.get_columns(table_name)}
        model_columns = {col.name for col in table.columns}

        missing_cols = model_columns - live_columns
        extra_cols = live_columns - model_columns

        for col_name in sorted(missing_cols):
            col = table.columns[col_name]
            problems.append(
                f"MISSING COLUMN: {table_name}.{col_name}  "
                f"(type={col.type}, nullable={col.nullable})"
            )

        for col_name in sorted(extra_cols):
            problems.append(
                f"EXTRA COLUMN (in DB, not in model - informational only): "
                f"{table_name}.{col_name}"
            )

    if not problems:
        print("No drift detected - live schema matches app.py's models exactly.")
        return

    print(f"Found {len(problems)} item(s):")
    print()
    for p in problems:
        print(" -", p)


if __name__ == "__main__":
    main()
