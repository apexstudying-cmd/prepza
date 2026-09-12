from pathlib import Path
import re

APP = Path('frontend/src/App.tsx')


def replace_once(text, old, new, label):
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise SystemExit(f'Expected {label} block not found')


def main():
    text = APP.read_text()

    screen_before = "  | 'publish-library' | 'xp-progress' | 'study-streak' | 'achievements' | 'study-materials'\n"
    screen_after = "  | 'publish-library' | 'xp-progress' | 'study-streak' | 'achievements' | 'study-materials' | 'document-reader'\n"
    if screen_after not in text:
        text = replace_once(text, screen_before, screen_after, 'document-reader screen union')

    if 'function DocumentStudyHubScreen(' not in text:
        marker = "function BottomNav({ active, setScreen }: { active: Screen; setScreen: (s: Screen) => void }) {"
        component = r'''
// ─── DOCUMENT STUDY HUB ─────────────────────────────────────────────────────
// A document is the student's study home: read it, ask Ada about it, replay
// existing materials, or create a new material. Generation remains owned by
// the existing backend generation routes.
function DocumentStudyHubScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const { tokens: T } = useTheme()
  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)

  useEffect(() => {
    if (activeDocumentId == null) { setLoading(false); setError('No document selected.'); return }
    setLoading(true)
    api<DocumentDetail>(`/documents/${activeDocumentId}`)
      .then(setDoc)
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load this document.'))
      .finally(() => setLoading(false))
  }, [activeDocumentId])

  if (loading) return <GenerationLoading label="Opening your study hub…" />
  if (error) return <GenerationError error={error} />
  if (!doc || activeDocumentId == null) return <GenerationError error="Document unavailable." />

  const readyMaterials = (doc.materials || []).filter((m: any) => m.status === 'ready')
  const openMaterial = (type: string) => {
    if (type === 'summary') setScreen('summary')
    else if (type === 'flashcards') setScreen('flashcards')
    else if (type === 'quiz' || type === 'practice_questions') setScreen('quiz')
    else if (type === 'mind_map' || type === 'mindmap') setScreen('mind-map')
    else if (type === 'podcast') setScreen('podcast-library')
  }

  return <div style={{ flex:1, overflowY:'auto', background:T.bg }}>
    <div style={{ padding:'18px 16px 24px', maxWidth:760, margin:'0 auto' }}>
      <button onClick={() => setScreen('study-materials')} style={{ border:'none', background:'none', padding:0, color:T.muted, fontSize:12, fontWeight:700, cursor:'pointer' }}>← My Study</button>
      <div style={{ marginTop:16, display:'flex', alignItems:'flex-start', gap:12 }}>
        <div style={{ flex:1, minWidth:0 }}><div style={{ fontSize:22, fontWeight:900, color:T.text }}>{doc.title}</div><div style={{ marginTop:5, color:T.muted, fontSize:12 }}>{doc.page_count || 1} pages · {doc.file_type?.toUpperCase() || 'DOCUMENT'}</div></div>
      </div>
      <button onClick={() => setScreen('document-reader')} style={{ width:'100%', marginTop:18, padding:'14px 16px', border:'none', borderRadius:14, background:N.navy, color:'#fff', fontWeight:800, cursor:'pointer' }}>Continue Reading</button>
      <div style={{ marginTop:22, fontSize:14, fontWeight:900, color:T.text }}>Study with Ada</div>
      <button onClick={() => setScreen('ai-tutor')} style={{ width:'100%', marginTop:10, padding:'14px 16px', border:`1px solid ${T.border}`, borderRadius:14, background:T.card, color:T.text, fontWeight:800, textAlign:'left', cursor:'pointer' }}>Ask anything about this document</button>
      <div style={{ marginTop:24, fontSize:14, fontWeight:900, color:T.text }}>Your Study Materials</div>
      <div style={{ marginTop:10, display:'grid', gap:8 }}>
        {readyMaterials.map((m: any) => <button key={`${m.material_type}-${m.id || m.created_at}`} onClick={() => openMaterial(m.material_type)} style={{ border:`1px solid ${T.border}`, background:T.card, borderRadius:14, padding:'13px 14px', textAlign:'left', cursor:'pointer' }}><div style={{ fontWeight:800, color:T.text }}>{m.material_type === 'practice_questions' ? 'Practice Questions' : m.material_type.replace(/_/g,' ').replace(/\b\w/g, (c:string)=>c.toUpperCase())}</div><div style={{ marginTop:3, fontSize:11, color:T.muted }}>From {doc.title}</div></button>)}
        {!readyMaterials.length && <div style={{ padding:16, border:`1px dashed ${T.border}`, borderRadius:14, color:T.muted, fontSize:12 }}>No study materials yet.</div>}
      </div>
      <button onClick={() => setShowCreate(true)} style={{ width:'100%', marginTop:14, padding:'14px 16px', border:`1px solid ${N.gold}`, borderRadius:14, background:'transparent', color:N.gold, fontWeight:900, cursor:'pointer' }}>+ Create Study Material</button>
    </div>
    {showCreate && <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,.45)', display:'flex', alignItems:'flex-end', zIndex:50 }} onClick={() => setShowCreate(false)}><div style={{ width:'100%', maxWidth:760, margin:'0 auto', background:T.card, borderRadius:'22px 22px 0 0', padding:20 }} onClick={e=>e.stopPropagation()}><div style={{ fontSize:18, fontWeight:900, color:T.text }}>Create Study Material</div>{['summary','flashcards','quiz','mind_map','podcast'].map(type => <button key={type} onClick={() => { setShowCreate(false); openMaterial(type) }} style={{ width:'100%', marginTop:8, padding:13, border:`1px solid ${T.border}`, borderRadius:12, background:T.bg, color:T.text, textAlign:'left', fontWeight:700, cursor:'pointer' }}>{type === 'quiz' ? 'Practice Questions' : type === 'mind_map' ? 'Mind Map' : type.charAt(0).toUpperCase()+type.slice(1)}</button>)}</div></div>}
  </div>
}

'''
        text = replace_once(text, marker, component + marker, 'document study hub')

    text = replace_once(text, "      case 'document-study': return <DocumentStudyScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />", "      case 'document-study': return <DocumentStudyHubScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />", 'document study route')
    text = replace_once(text, "      case 'document-reader': return <DocumentStudyScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />", "      case 'document-reader': return <DocumentReaderScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />", 'document reader route')
    APP.write_text(text)


if __name__ == '__main__':
    main()
