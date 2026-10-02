"""Verified Prepza schema baseline."""
from __future__ import annotations
from pathlib import Path
from alembic import op
revision = "20261002_baseline"
down_revision = None
branch_labels = None
depends_on = None
ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "schema" / "local_baseline.sql"
def upgrade() -> None:
    op.get_bind().exec_driver_sql(BASELINE.read_text(encoding="utf-8"))
def downgrade() -> None:
    raise RuntimeError("The verified baseline is not reversible; recreate a disposable database instead.")
