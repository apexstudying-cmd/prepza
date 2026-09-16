from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'

s = APP.read_text(encoding='utf-8')
original = s

# The /documents list is typed independently from DocumentDetail and its id can
# arrive as a string. Offline StudyHub APIs intentionally require numeric ids.
s = s.replace("const openDocument = (id: number) => { setActiveDocumentId(id); setScreen('document-study') }", "const openDocument = (id: number | string) => { const documentId = Number(id); if (!Number.isInteger(documentId) || documentId <= 0) return; setActiveDocumentId(documentId); setScreen('document-study') }")
s = s.replace("setActiveDocumentId(row.documentId)\n    const type =", "setActiveDocumentId(Number(row.documentId))\n    const type =")
s = s.replace("openDocument(d.id)", "openDocument(Number(d.id))")

if s == original:
    raise SystemExit('offline build fixes: no changes made')
APP.write_text(s, encoding='utf-8')
print('Offline build fixes applied and verified.')
