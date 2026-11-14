from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
LIBRARY_ROUTES = ROOT / "library_routes.py"
GROUP_ROUTES = ROOT / "group_routes.py"
MODEL_SOURCES = [
    APP,
    ROOT / "library_models.py",
    ROOT / "social_models.py",
    ROOT / "academic_models.py",
]
RUNTIME_SOURCES = [APP, LIBRARY_ROUTES, GROUP_ROUTES]


def clean_model_source(source: str) -> str:
    unit_block = re.compile(r"\nclass Unit\(db\.Model\):.*?(?=\nclass ContentItem\(db\.Model\):)", re.S)
    source, _ = unit_block.subn("\n", source, count=1)
    unit_program_block = re.compile(r"\nclass UnitProgram\(db\.Model\):.*?(?=\nclass ContentItem\(db\.Model\):)", re.S)
    source, _ = unit_program_block.subn("\n", source, count=1)
    source = re.sub(
        r'^\s*unit_id\s*=\s*db\.Column\(db\.Integer,\s*db\.ForeignKey\("unit\.id"\),\s*nullable=(?:True|False)\)\s*\n',
        '', source, flags=re.M,
    )
    return source


def clean_runtime_source(source: str) -> str:
    source = re.sub(r'db\.session\.get\(Unit, [^\n]+\)', 'None', source)
    source = re.sub(r'UnitProgram\.query\.[^\n]+', 'None', source)
    source = source.replace('LibraryPublication.unit_id == unit_id', 'False')
    source = re.sub(r'query\.filter_by\(unit_id=unit_id\)', 'query', source)
    source = re.sub(r'query\.filter\(Group\.unit_id == unit_id\)', 'query', source)
    source = re.sub(r'^\s*unit_id=unit_id,\n', '', source, flags=re.M)
    source = re.sub(r'"unit_id":\s*[^,\n]+,', '"unit_id": None,', source)
    source = re.sub(r'"unit_code":\s*[^,\n]+,', '"unit_code": None,', source)
    return source


for path in MODEL_SOURCES:
    original = path.read_text(encoding="utf-8")
    updated = clean_model_source(original)
    if updated != original:
        path.write_text(updated, encoding="utf-8")

for path in RUNTIME_SOURCES:
    original = path.read_text(encoding="utf-8")
    updated = clean_runtime_source(original)
    if updated != original:
        path.write_text(updated, encoding="utf-8")

patterns = (
    "class Unit",
    "class UnitProgram",
    'ForeignKey("unit.id")',
    "LibraryPublication.unit_id",
    "Group.unit_id",
)
found = []
for path in [*MODEL_SOURCES, *RUNTIME_SOURCES]:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if any(pattern in line for pattern in patterns):
            found.append((str(path.relative_to(ROOT)), number, line.strip()))

print("=== UNIT/LEGACY CONTENT REFERENCE AUDIT ===")
for path, number, line in found:
    print(f"{path}:{number}: {line}")
print(f"UNIT_AUDIT_MATCH_COUNT={len(found)}")
print("=== END UNIT/LEGACY CONTENT REFERENCE AUDIT ===")
if found:
    raise SystemExit("FAIL CLOSED: retired Unit runtime references remain")
