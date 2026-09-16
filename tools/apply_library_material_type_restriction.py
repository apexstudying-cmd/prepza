import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.tsx"
text = APP.read_text(encoding="utf-8")

pattern = r"const LIBRARY_MATERIAL_TYPES\s*=\s*\[[\s\S]*?\]\n"
replacement = "const LIBRARY_MATERIAL_TYPES = [\n  { value: 'lecture_notes', label: 'Lecture Notes' },\n  { value: 'past_paper', label: 'Past Paper' },\n]\n"
text, count = re.subn(pattern, replacement, text, count=1)
if count != 1:
    raise SystemExit("FAIL CLOSED: LIBRARY_MATERIAL_TYPES definition was not found exactly once")

APP.write_text(text, encoding="utf-8")
print("Restricted Library publication types to student notes and past papers.")
