from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'

s = APP.read_text(encoding='utf-8')
original = s

# The /documents list and upload responses are not consistently typed as
# numeric ids. Normalize every non-null/non-already-normalized active-document
# setter argument at the final build transformation boundary.
s = s.replace("const openDocument = (id: number) => { setActiveDocumentId(id); setScreen('document-study') }", "const openDocument = (id: number | string) => { const documentId = Number(id); if (!Number.isInteger(documentId) || documentId <= 0) return; setActiveDocumentId(documentId); setScreen('document-study') }")
s = s.replace("setActiveDocumentId(row.documentId)\n    const type =", "setActiveDocumentId(Number(row.documentId))\n    const type =")
s = s.replace("openDocument(d.id)", "openDocument(Number(d.id))")
s = re.sub(r"setActiveDocumentId\(((?!null\b|Number\().*?)\)", r"setActiveDocumentId(Number(\1))", s)

if s == original:
    raise SystemExit('offline build fixes: no changes made')
APP.write_text(s, encoding='utf-8')
print('Offline build fixes applied and verified.')
