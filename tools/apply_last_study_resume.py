from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "App.tsx"
HOME = ROOT / "frontend" / "src" / "screens" / "home" / "HomeScreen.tsx"
STUDY = ROOT / "frontend" / "src" / "screens" / "study" / "StudyMaterialsScreen.tsx"
HELPER = ROOT / "frontend" / "src" / "lib" / "lastStudyDocument.ts"

HELPER_SOURCE = """const LAST_STUDY_DOCUMENT_KEY = 'prepza-last-study-document-id'

function storageKey(): string {
  try {
    const userId = typeof window === 'undefined' ? null : window.localStorage.getItem('prepza-offline-user-id')
    return userId ? LAST_STUDY_DOCUMENT_KEY + ':' + userId : LAST_STUDY_DOCUMENT_KEY
  } catch {
    return LAST_STUDY_DOCUMENT_KEY
  }
}

export function rememberLastStudyDocument(documentId: number | null): void {
  if (documentId == null || !Number.isSafeInteger(documentId) || documentId <= 0) return
  try {
    if (typeof window !== 'undefined') window.localStorage.setItem(storageKey(), String(documentId))
  } catch {
    // Browser storage is optional; navigation must continue when it is unavailable.
  }
}

export function readLastStudyDocumentId(): number | null {
  try {
    if (typeof window === 'undefined') return null
    const raw = window.localStorage.getItem(storageKey())
    const documentId = raw ? Number(raw) : NaN
    return Number.isSafeInteger(documentId) && documentId > 0 ? documentId : null
  } catch {
    return null
  }
}
"""


def ensure_import(source: str, anchor: str, import_line: str, label: str) -> str:
    if import_line in source:
        return source
    if anchor not in source:
        raise SystemExit(f"Last-study resume import anchor missing: {label}")
    return source.replace(anchor, anchor + import_line, 1)


def main() -> None:
    newline = chr(10)
    HELPER.parent.mkdir(parents=True, exist_ok=True)
    if not HELPER.exists():
        HELPER.write_text(HELPER_SOURCE, encoding="utf-8")
    else:
        helper = HELPER.read_text(encoding="utf-8")
        if "export function readLastStudyDocumentId()" not in helper or "export function rememberLastStudyDocument(" not in helper:
            raise SystemExit("Last-study resume helper exists but does not expose the expected storage contract")

    app = APP.read_text(encoding="utf-8")
    home = HOME.read_text(encoding="utf-8")
    study = STUDY.read_text(encoding="utf-8")

    app = ensure_import(
        app,
        "import HomeScreen from './screens/home/HomeScreen'" + newline,
        "import { rememberLastStudyDocument } from './lib/lastStudyDocument'" + newline,
        "App",
    )
    marker = "function DocumentStudyScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {"
    if "rememberLastStudyDocument(activeDocumentId)" not in app:
        start = app.find(marker)
        if start < 0:
            raise SystemExit("DocumentStudyScreen owner missing")
        effect = app.find("  useEffect(() => {", start)
        if effect < 0:
            raise SystemExit("DocumentStudyScreen effect anchor missing")
        effect_source = (
            "  useEffect(() => {" + newline
            + "    rememberLastStudyDocument(activeDocumentId)" + newline
            + "  }, [activeDocumentId])" + newline + newline
        )
        app = app[:effect] + effect_source + app[effect:]

    home = ensure_import(
        home,
        "import { api } from '../../lib/appApi'" + newline,
        "import { readLastStudyDocumentId, rememberLastStudyDocument } from '../../lib/lastStudyDocument'" + newline,
        "HomeScreen",
    )
    old_featured = "  const featuredDoc = activeDocs[0]" + newline + "  const restDocs = activeDocs.slice(1)"
    new_featured = (
        "  const lastStudyId = readLastStudyDocumentId()" + newline
        + "  const featuredDoc = activeDocs.find(document => document.id === lastStudyId) || activeDocs[0]" + newline
        + "  const restDocs = featuredDoc ? activeDocs.filter(document => document.id !== featuredDoc.id) : []"
    )
    if old_featured in home:
        home = home.replace(old_featured, new_featured, 1)
    elif "const lastStudyId = readLastStudyDocumentId()" not in home:
        raise SystemExit("Home featured document owner anchor missing")
    if "rememberLastStudyDocument(featuredDoc.id)" not in home:
        home = home.replace(
            "setActiveDocumentId(featuredDoc.id); setScreen('document-study')",
            "rememberLastStudyDocument(featuredDoc.id); setActiveDocumentId(featuredDoc.id); setScreen('document-study')",
        )
    if "rememberLastStudyDocument(d.id)" not in home:
        home = home.replace(
            "setActiveDocumentId(d.id); setScreen('document-study')",
            "rememberLastStudyDocument(d.id); setActiveDocumentId(d.id); setScreen('document-study')",
        )
    if "rememberLastStudyDocument(featuredDoc.id)" not in home or "rememberLastStudyDocument(d.id)" not in home:
        raise SystemExit("Home document-open handlers are not wired to last-study storage")

    study = ensure_import(
        study,
        "import { api, ApiError } from '../../lib/appApi'" + newline,
        "import { rememberLastStudyDocument } from '../../lib/lastStudyDocument'" + newline,
        "My Study",
    )
    old_open = "const openDocument = (id: number) => { onRememberLastStudyDocument?.(id); setActiveDocumentId(id); setScreen('document-study') }"
    new_open = "const openDocument = (id: number) => { onRememberLastStudyDocument?.(id); rememberLastStudyDocument(id); setActiveDocumentId(id); setScreen('document-study') }"
    if old_open in study:
        study = study.replace(old_open, new_open, 1)
    elif "rememberLastStudyDocument(id)" not in study:
        raise SystemExit("My Study openDocument callback anchor missing")

    APP.write_text(app, encoding="utf-8")
    HOME.write_text(home, encoding="utf-8")
    STUDY.write_text(study, encoding="utf-8")
    print("Last-study resume is wired to the extracted Home and My Study owners with account-scoped storage.")


if __name__ == "__main__":
    main()
