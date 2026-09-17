from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "App.tsx"
text = APP.read_text(encoding="utf-8")

HELPER_MARKER = "// ─── HOME ─────────────────────────────────────────────────────────────────────"
HELPER = '''const LAST_STUDY_DOCUMENT_KEY = 'prepza-last-study-document-id'

function lastStudyStorageKey(): string {
  try {
    const userId = window.localStorage.getItem('prepza-offline-user-id')
    return userId ? `${LAST_STUDY_DOCUMENT_KEY}:${userId}` : LAST_STUDY_DOCUMENT_KEY
  } catch { return LAST_STUDY_DOCUMENT_KEY }
}

function rememberLastStudyDocument(documentId: number | null) {
  if (documentId == null) return
  try { window.localStorage.setItem(lastStudyStorageKey(), String(documentId)) } catch { /* storage is optional */ }
}

function readLastStudyDocumentId(): number | null {
  try {
    const raw = window.localStorage.getItem(lastStudyStorageKey())
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
else:
    # Upgrade an older unscoped helper in-place so the generated App cannot
    # retain a cross-account last-study pointer.
    old_key = "const LAST_STUDY_DOCUMENT_KEY = 'prepza-last-study-document-id'\n\nfunction rememberLastStudyDocument(documentId: number | null) {\n  if (documentId == null) return\n  try { window.localStorage.setItem(LAST_STUDY_DOCUMENT_KEY, String(documentId)) } catch { /* storage is optional */ }\n}\n\nfunction readLastStudyDocumentId(): number | null {\n  try {\n    const raw = window.localStorage.getItem(LAST_STUDY_DOCUMENT_KEY)"
    if old_key in text:
        text = text.replace(old_key, HELPER.rstrip().split('\n\n', 1)[0] + "\n\n" + HELPER.split('\n\n', 2)[1] + "\n\nfunction readLastStudyDocumentId(): number | null {\n  try {\n    const raw = window.localStorage.getItem(lastStudyStorageKey())", 1)

old_featured = "  const featuredDoc = activeDocs[0]\n  const restDocs = activeDocs.slice(1)"
new_featured = '''  const lastStudyId = readLastStudyDocumentId()
  const lastStudyDoc = lastStudyId == null ? null : activeDocs.find(d => d.id === lastStudyId) || null
  const featuredDoc = lastStudyDoc || activeDocs[0]
  const restDocs = featuredDoc ? activeDocs.filter(d => d.id !== featuredDoc.id) : []'''
if old_featured in text:
    text = text.replace(old_featured, new_featured, 1)
elif new_featured not in text:
    raise SystemExit("Home featured document anchor not found")

text = text.replace(
    "setActiveDocumentId(featuredDoc.id); setScreen('document-study')",
    "rememberLastStudyDocument(featuredDoc.id); setActiveDocumentId(featuredDoc.id); setScreen('document-study')",
)

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

required = ['lastStudyStorageKey()', "localStorage.setItem(lastStudyStorageKey(), String(documentId))", 'localStorage.getItem(lastStudyStorageKey())']
missing = [x for x in required if x not in text]
if missing:
    raise SystemExit('Last-study resume verification failed: ' + ', '.join(missing))
APP.write_text(text, encoding="utf-8")
print("Last-study resume transformation applied and account-scoped.")
