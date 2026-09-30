"""Day 5 ORM/schema drift audit."""
from pathlib import Path
import re
APP = Path(__file__).resolve().parents[1] / "app.py"
text = APP.read_text(encoding="utf-8")
patterns = (
    r"^class Unit\(db\.Model\):", r"^class UnitProgram\(db\.Model\):",
    r'ForeignKey\("unit\.id"\)', r"db\.session\.get\(Unit\b",
    r"LibraryPublication\.unit_id", r"Group\.unit_id", r"join\(Unit\b",
)
found=[(n,l.strip()) for n,l in enumerate(text.splitlines(),1) if any(re.search(p,l) for p in patterns)]
print("DAY5_ORM_SCHEMA_DRIFT_AUDIT")
for n,l in found: print(f"{n}: {l}")
if found: raise SystemExit("Retired Unit ORM/schema references remain")
print("PASS: retired Unit ORM/schema references are absent.")
