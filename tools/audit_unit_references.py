from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"
text = APP.read_text(encoding="utf-8")

patterns = (
    "UnitProgram",
    "class Unit",
    "unit_id",
    'ForeignKey("unit.id")',
    "ContentItem",
    "content_item_id",
)

print("=== UNIT/LEGACY CONTENT REFERENCE AUDIT ===")
lines = text.splitlines()
found = []
for number, line in enumerate(lines, 1):
    if any(pattern in line for pattern in patterns):
        found.append((number, line.strip()))
for number, line in found:
    print(f"{number}: {line}")
print(f"UNIT_AUDIT_MATCH_COUNT={len(found)}")
print("=== END UNIT/LEGACY CONTENT REFERENCE AUDIT ===")
