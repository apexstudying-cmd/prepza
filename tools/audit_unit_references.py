from pathlib import Path
import re

APP = Path(__file__).resolve().parents[1] / "app.py"
text = APP.read_text(encoding="utf-8")

# The current production schema still uses Unit/UnitProgram for curriculum
# metadata. Do not let a stale frontend prebuild migration delete live ORM
# models or rewrite the backend during a static frontend build.
if "class Unit(db.Model)" in text:
    print("Skipped Unit-reference retirement audit: current backend still owns the Unit curriculum model.")
    raise SystemExit(0)

# The Unit tables are already removed from production. This final prebuild
# cleanup makes the application source match that schema before the process
# starts. It is deliberately fail-closed around the model block so we never
# silently leave a half-removed Unit mapper behind.
unit_block = re.compile(r"\nclass Unit\(db\.Model\):.*?(?=\nclass ContentItem\(db\.Model\):)", re.S)
text, unit_count = unit_block.subn("\n", text, count=1)
if unit_count != 1:
    raise SystemExit(f"FAIL CLOSED: expected exactly one Unit model block, found {unit_count}")

unit_program_block = re.compile(r"\nclass UnitProgram\(db\.Model\):.*?(?=\nclass ContentItem\(db\.Model\):)", re.S)
text, unit_program_count = unit_program_block.subn("\n", text, count=1)
# The UnitProgram block is normally consumed together with Unit; this second
# pass is kept for source versions where the classes are separated.
if unit_program_count not in (0, 1):
    raise SystemExit(f"FAIL CLOSED: unexpected UnitProgram block count {unit_program_count}")

# Remove SQLAlchemy Unit foreign-key fields from the remaining legacy models.
text, fk_count = re.subn(
    r'^\s*unit_id\s*=\s*db\.Column\(db\.Integer,\s*db\.ForeignKey\("unit\.id"\),\s*nullable=(?:True|False)\)\s*\n',
    '', text, flags=re.M,
)
if fk_count < 1:
    raise SystemExit("FAIL CLOSED: no Unit foreign-key model fields were found")

# No runtime endpoint may dereference the retired Unit mapper.
text = re.sub(r'db\.session\.get\(Unit, [^\n]+\)', 'None', text)
text = re.sub(r'UnitProgram\.query\.[^\n]+', 'None', text)

# Legacy filters are ignored rather than allowed to reference a removed
# column. Current Library filtering is academic-context based instead.
text = text.replace('LibraryPublication.unit_id == unit_id', 'False')
text = re.sub(r'query\.filter_by\(unit_id=unit_id\)', 'query', text)
text = re.sub(r'query\.filter\(Group\.unit_id == unit_id\)', 'query', text)

# Constructors and response payloads may still carry the legacy compatibility
# key. Keep the JSON key as null where useful, but never access a DB column.
text = re.sub(r'^\s*unit_id=unit_id,\n', '', text, flags=re.M)
text = re.sub(r'"unit_id":\s*[^,\n]+,', '"unit_id": None,', text)
text = re.sub(r'"unit_code":\s*[^,\n]+,', '"unit_code": None,', text)

APP.write_text(text, encoding="utf-8")

# Audit the transformed runtime source. These are allowed compatibility
# references only; no SQLAlchemy Unit mapper or Unit FK should remain.
patterns = (
    "class Unit",
    "class UnitProgram",
    'ForeignKey("unit.id")',
    "LibraryPublication.unit_id",
    "Group.unit_id",
)
lines = text.splitlines()
found = []
for number, line in enumerate(lines, 1):
    if any(pattern in line for pattern in patterns):
        found.append((number, line.strip()))

print("=== UNIT/LEGACY CONTENT REFERENCE AUDIT ===")
for number, line in found:
    print(f"{number}: {line}")
print(f"UNIT_AUDIT_MATCH_COUNT={len(found)}")
print("=== END UNIT/LEGACY CONTENT REFERENCE AUDIT ===")
if found:
    raise SystemExit("FAIL CLOSED: retired Unit runtime references remain")
