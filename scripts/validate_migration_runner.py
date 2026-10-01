"""Static regression checks for the migration ledger runner."""
from pathlib import Path

SOURCE = Path("scripts/apply_migrations.py").read_text(encoding="utf-8")

if 'expected = {p.name: checksum(p) for p in migration_files() if p.name != LEDGER_MIGRATION}' not in SOURCE:
    raise SystemExit("Migration runner regression: verify must exclude the ledger definition itself")

if 'if path.name == LEDGER_MIGRATION:' not in SOURCE:
    raise SystemExit("Migration runner regression: apply must skip the ledger definition")

if 'files = [p for p in migration_files() if p.name != LEDGER_MIGRATION]' not in SOURCE:
    raise SystemExit("Migration runner regression: baseline must skip the ledger definition")

print("Migration runner invariants passed.")
