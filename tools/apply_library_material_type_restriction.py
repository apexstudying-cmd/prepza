import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "App.tsx"
HELPERS = ROOT / "frontend" / "src" / "lib" / "library.ts"

if HELPERS.exists() and "export const LIBRARY_MATERIAL_TYPES" in HELPERS.read_text(encoding="utf-8"):
    TARGET = HELPERS
    pattern = r"export const LIBRARY_MATERIAL_TYPES(?:\s*:\s*\{[^\n]+\}\[\])?\s*=\s*\[[\s\S]*?\]\n"
    replacement = "export const LIBRARY_MATERIAL_TYPES: { value: string; label: string }[] = [\n  { value: 'lecture_notes', label: 'Lecture Notes' },\n  { value: 'past_paper', label: 'Past Paper' },\n]\n"
else:
    # Retain the inline-source fallback for older branches where the helper
    # has not yet been extracted from App.tsx.
    TARGET = APP
    pattern = r"const LIBRARY_MATERIAL_TYPES(?:\s*:\s*\{[^\n]+\}\[\])?\s*=\s*\[[\s\S]*?\]\n"
    replacement = "const LIBRARY_MATERIAL_TYPES: { value: string; label: string }[] = [\n  { value: 'lecture_notes', label: 'Lecture Notes' },\n  { value: 'past_paper', label: 'Past Paper' },\n]\n"

text = TARGET.read_text(encoding="utf-8")
text, count = re.subn(pattern, replacement, text, count=1)
if count != 1:
    raise SystemExit(f"FAIL CLOSED: LIBRARY_MATERIAL_TYPES definition was not found exactly once in {TARGET.relative_to(ROOT)}")

TARGET.write_text(text, encoding="utf-8")
print("Restricted Library publication types to student notes and past papers.")
