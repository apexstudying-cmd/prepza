"""Apply or baseline Prepza SQL migrations safely.

Historical migrations are intentionally not auto-baselined: an existing database
must be explicitly marked as current by an operator after schema verification.
Future migrations are recorded in schema_migration with a SHA-256 checksum.
"""
from __future__ import annotations
import argparse, hashlib, os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
LEDGER_MIGRATION = "20261001_migration_history.sql"
def migration_files(): return sorted(MIGRATIONS.glob("*.sql"))
def checksum(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def connect():
    load_dotenv(ROOT / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url: raise SystemExit("DATABASE_URL is required")
    return create_engine(url)
def ensure_ledger(conn): conn.execute(text((MIGRATIONS / LEDGER_MIGRATION).read_text(encoding="utf-8")))
def baseline(conn):
    for path in migration_files():
        if path.name == LEDGER_MIGRATION:
            continue
        conn.execute(text("""INSERT INTO schema_migration (migration_name, checksum)
VALUES (:name, :checksum) ON CONFLICT (migration_name) DO NOTHING"""), {"name":path.name,"checksum":checksum(path)})
    print(f"Baselined {len(migration_files())} migration file(s).")
def verify(conn):
    rows=conn.execute(text("SELECT migration_name, checksum FROM schema_migration ORDER BY migration_name")).all()
    expected={p.name:checksum(p) for p in migration_files()}; applied=dict(rows)
    changed=[n for n,d in applied.items() if expected.get(n) not in (None,d)]
    missing=sorted(set(expected)-set(applied)); unknown=sorted(set(applied)-set(expected))
    if changed or missing or unknown: raise SystemExit(f"Migration ledger mismatch: changed={changed}, missing={missing}, unknown={unknown}")
    print(f"Migration ledger verified: {len(applied)} file(s).")
def apply(conn):
    applied=dict(conn.execute(text("SELECT migration_name, checksum FROM schema_migration")).all())
    for path in migration_files():
        if path.name in applied:
            if applied[path.name] != checksum(path): raise SystemExit(f"Migration checksum changed after application: {path.name}")
            continue
        if path.name == LEDGER_MIGRATION:
            continue
        print(f"Applying {path.name}...")
        conn.execute(text(path.read_text(encoding="utf-8")))
        conn.execute(text("INSERT INTO schema_migration (migration_name, checksum) VALUES (:name, :checksum)"), {"name":path.name,"checksum":checksum(path)})
    print("Migration apply complete.")
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--baseline",action="store_true"); parser.add_argument("--apply",action="store_true"); parser.add_argument("--verify",action="store_true"); args=parser.parse_args()
    if sum(bool(x) for x in (args.baseline,args.apply,args.verify)) != 1: parser.error("choose exactly one of --baseline, --apply, or --verify")
    with connect().begin() as conn:
        ensure_ledger(conn)
        if args.baseline: baseline(conn)
        elif args.apply: apply(conn)
        else: verify(conn)
if __name__ == "__main__": main()
