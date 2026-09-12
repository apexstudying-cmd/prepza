from pathlib import Path

p = Path('frontend/src/App.tsx')
s = p.read_text()

def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise SystemExit(f'{label} anchor not found')

s = replace_once(
    s,
    "function LibraryScreen({ setScreen }: { setScreen: (s: Screen) => void }) {",
    "function LibraryScreen({ setScreen, setActiveDocumentId }: { setScreen: (s: Screen) => void; setActiveDocumentId: (id: number | null) => void }) {",
    'LibraryScreen props',
)

old_card = """              <div key={p.id} style={{ background: T.card, borderRadius: 16, padding: '14px 16px', marginBottom: 10, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', border: `1.5px solid ${p.status === 'approved' ? 'rgba(76,201,123,0.2)' : 'rgba(0,0,0,0.06)'}` }}>"""
new_card = """              <div key={p.id} onClick={p.status === 'approved' && p.document_id ? () => { setActiveDocumentId(p.document_id); setScreen('document-study') } : undefined} style={{ background: T.card, borderRadius: 16, padding: '14px 16px', marginBottom: 10, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', border: `1.5px solid ${p.status === 'approved' ? 'rgba(76,201,123,0.2)' : 'rgba(0,0,0,0.06)'}`, cursor: p.status === 'approved' && p.document_id ? 'pointer' : 'default' }}>"""
s = replace_once(s, old_card, new_card, 'published material card')

s = replace_once(
    s,
    "case 'library':           return <LibraryScreen setScreen={setScreen} />",
    "case 'library':           return <LibraryScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} />",
    'library route props',
)

p.write_text(s)
print('published material entry patch applied')
