from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "App.tsx"
text = APP.read_text(encoding="utf-8")

HELPER_MARKER = "// ─── HOME ─────────────────────────────────────────────────────────────────────"
HELPER = '''const LAST_STUDY_DOCUMENT_KEY = 'prepza-last-study-document-id'

function rememberLastStudyDocument(documentId: number | null) {
  if (documentId == null) return
  try { window.localStorage.setItem(LAST_STUDY_DOCUMENT_KEY, String(documentId)) } catch { /* storage is optional */ }
}

function readLastStudyDocumentId(): number | null {
  try {
    const raw = window.localStorage.getItem(LAST_STUDY_DOCUMENT_KEY)
    const id = raw ? Number(raw) : NaN
    return Number.isInteger(id) && id > 0 ? id : null
  } catch {
    return null
  }
}

'''
if HELPER not in text:
    marker = text.find(HELPER_MARKER)
    if marker < 0:
        raise SystemExit("Home marker not found")
    text = text[:marker] + HELPER + text[marker:]

old_featured = "  const featuredDoc = activeDocs[0]\n  const restDocs = activeDocs.slice(1)"
new_featured = '''  const lastStudyId = readLastStudyDocumentId()
  const lastStudyDoc = lastStudyId == null ? null : activeDocs.find(d => d.id === lastStudyId) || null
  const featuredDoc = lastStudyDoc || activeDocs[0]
  const restDocs = featuredDoc ? activeDocs.filter(d => d.id !== featuredDoc.id) : []'''
if old_featured in text:
    text = text.replace(old_featured, new_featured, 1)
elif new_featured not in text:
    raise SystemExit("Home featured document anchor not found")

# Record the target at the moment the student chooses Continue Studying.
# This is more reliable than waiting for the destination component to mount.
text = text.replace(
    "setActiveDocumentId(featuredDoc.id); setScreen('document-study')",
    "rememberLastStudyDocument(featuredDoc.id); setActiveDocumentId(featuredDoc.id); setScreen('document-study')",
)

# My Study has its own document-opening helper. Keep it as another explicit
# entry point so switching documents there immediately changes Continue Studying.
study_hub_marker = "function StudyMaterialsScreen"
start = text.find(study_hub_marker)
if start >= 0:
    end = text.find("\nfunction ", start + len(study_hub_marker))
    section_end = end if end >= 0 else len(text)
    study_hub = text[start:section_end]
    old_open = "const openDocument = (id: number) => { setActiveDocumentId(id); setScreen('document-study') }"
    new_open = "const openDocument = (id: number) => { rememberLastStudyDocument(id); setActiveDocumentId(id); setScreen('document-study') }"
    if old_open in study_hub:
        study_hub = study_hub.replace(old_open, new_open, 1)
        text = text[:start] + study_hub + text[section_end:]

# The destination component remains a fallback for entry points not covered
# above (Library/Explore/etc.), so direct navigation into it still records the
# document as the last meaningful study target.
study_marker = "function DocumentStudyScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {"
if "rememberLastStudyDocument(activeDocumentId)" not in text:
    start = text.find(study_marker)
    if start < 0:
        raise SystemExit("DocumentStudyScreen marker not found")
    effect_anchor = text.find("  useEffect(() => {", start)
    if effect_anchor < 0:
        raise SystemExit("DocumentStudyScreen effect anchor not found")
    remember_effect = """  useEffect(() => {\n    rememberLastStudyDocument(activeDocumentId)\n  }, [activeDocumentId])\n\n"""
    text = text[:effect_anchor] + remember_effect + text[effect_anchor:]

APP.write_text(text, encoding="utf-8")
print("Last-study resume transformation applied.")
