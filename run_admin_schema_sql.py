"""
Runs add_admin_schema_columns.sql against the database at DATABASE_URL
(read from .env), so this migration can be done from the terminal
instead of the Supabase browser SQL editor.

Usage:
    python run_admin_schema_sql.py

Requires: add_admin_schema_columns.sql to be in the same directory
(or edit SQL_FILE below to point elsewhere). Uses the same DATABASE_URL
your Flask app already connects with, via SQLAlchemy - no new
dependencies beyond what's already in requirements.txt.
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

SQL_FILE = "add_admin_schema_columns.sql"


def fail(message):
    print(f"FAILED: {message}", file=sys.stderr)
    sys.exit(1)


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        fail("DATABASE_URL not found in .env - check your .env file is present and not saved as .env.txt")

    if not os.path.exists(SQL_FILE):
        fail(f"{SQL_FILE} not found in the current directory. Run this from the same folder as the SQL file.")

    with open(SQL_FILE, "r", encoding="utf-8") as f:
        sql_text = f.read()

    # Split on semicolons at end of line to run each statement
    # separately (needed because some drivers won't run multiple
    # statements in a single execute() call). Skips comment-only
    # and blank chunks.
    statements = [s.strip() for s in sql_text.split(";")]
    statements = [s for s in statements if s and not s.replace("\n", "").strip().startswith("--")]

    engine = create_engine(database_url)

    print(f"Connecting and running {len(statements)} statement(s)...")
    with engine.begin() as conn:
        for i, stmt in enumerate(statements, 1):
            # Skip pure-comment chunks that survived the split
            meaningful = "\n".join(
                line for line in stmt.splitlines() if not line.strip().startswith("--")
            ).strip()
            if not meaningful:
                continue
            print(f"  [{i}/{len(statements)}] running...")
            conn.execute(text(stmt))

    print("Migration applied successfully.")
    print("Verify with: python -c \"" +
          "from dotenv import load_dotenv; load_dotenv(); import os; " +
          "from sqlalchemy import create_engine, text; " +
          "e = create_engine(os.environ['DATABASE_URL']); " +
          "conn = e.connect(); " +
          "r = conn.execute(text('SELECT column_name FROM information_schema.columns WHERE table_name = \\'user\\'')); " +
          "print([row[0] for row in r])\"")


if __name__ == "__main__":
    main()
