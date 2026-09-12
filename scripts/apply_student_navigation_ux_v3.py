from pathlib import Path
import re

APP = Path('frontend/src/App.tsx')


def must_replace(text, pattern, replacement, label, flags=0):
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f'Could not patch {label}: expected exactly one match, got {count}')
    return updated


def main():
    text = APP.read_text()

    # Add the new global study surface without changing existing screen names.
    if "'study-materials'" not in text:
        text = must_replace(text, r"(type Screen = .*?)(\n)", lambda m: m.group(1) + " | 'study-materials'" + m.group(2), 'Screen union', re.S)

    # Home quick actions: tools that require a source document should begin from My Study.
    text = must_replace(
        text,
        r"\{ icon: '📤', label: 'Upload'.*?\n\s*\].map\(\(t, i\) => \(",
        "{ icon: '📤', label: 'Upload', action: () => setScreen('upload') },\n              { icon: '▣', label: 'My Study', action: () => setScreen('study-materials') },\n              { icon: '✦', label: 'Ada', action: () => setScreen('ai-tutor') },\n              { icon: '🎙️', label: 'Podcasts', action: () => setScreen('podcast-library') },\n            ].map((t, i) => (",
        'Home quick actions',
        re.S,
    )

    # Profile's document count becomes the entry point to the unified study area.
    text = must_replace(
        text,
        r"\{ label: 'Docs', value: summary \? String\(summary\.documents_count\) : '—', color: '#4C7BC9', dest: 'library' as Screen \},",
        "{ label: 'Docs', value: summary ? String(summary.documents_count) : '—', color: '#4C7BC9', dest: 'study-materials' as Screen },",
        'Profile Docs shortcut',
    )

    # Add a unified My Study screen immediately before BottomNav.
    if 'function StudyMaterialsScreen(' not in text:
        marker = "function BottomNav({ active, setScreen }: { active: Screen; setScreen: (s: Screen) => void }) {"
        component = r'''
// ─── MY STUDY ────────────────────────────────────────────────────────────────
// Student-facing hub for sources and reusable AI study materials. Backend
// terminology such as GeneratedMaterial is deliberately kept out of the UI.
function StudyMaterialsScreen({ setScreen, setActiveDocumentId }: { setScreen: (s: Screen) => void; setActiveDocumentId: (id: number | null) => void }) {
  const { tokens: T } = useTheme()
  const [tab, setTab] = useState<'documents' | 'materials'>('documents')
  const [documents, setDocuments] = useState<HomeDocument[]>([])
  const [materials, setMaterials] = useState<{ documentId: number; documentTitle: string; type: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        setLoading(true)
        const response = await api<{ documents: HomeDocument[] }>('/documents')
        if (cancelled) return
        const readyDocs = response.documents.filter(d => d.status === 'ready')
        setDocuments(readyDocs)
        const rows = await Promise.all(readyDocs.slice(0, 30).map(async d => {
          try {
            const detail = await api<DocumentDetail>(`/documents/${d.id}`)
            return (detail.materials || []).filter(m => m.status === 'ready').map(m => ({ documentId: d.id, documentTitle: d.title, type: m.type }))
          } catch { return [] }
        }))
        if (!cancelled) setMaterials(rows.flat())
      } catch (e) {
        if (!cancelled) setError(e instanceof ApiError ? e.message : 'Could not load your study library.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  const openDocument = (id: number) => {
    setActiveDocumentId(id)
    setScreen('document-study')
  }

  const openMaterial = (row: { documentId: number; type: string }) => {
    setActiveDocumentId(row.documentId)
    const type = row.type.toLowerCase().replace(/-/g, '_')
    const destination: Screen = type === 'summary' ? 'summary'
      : type === 'flashcards' ? 'flashcards'
      : type === 'quiz' || type === 'practice_questions' ? 'quiz'
      : type === 'mind_map' || type === 'mindmap' ? 'mind-map'
      : type === 'podcast' ? 'podcast-player'
      : 'document-study'
    setScreen(destination)
  }

  const materialLabel = (type: string) => ({
    summary: 'Summary', flashcards: 'Flashcards', quiz: 'Practice Questions',
    practice_questions: 'Practice Questions', mind_map: 'Mind Map', mindmap: 'Mind Map', podcast: 'Podcast'
  } as Record<string, string>)[type.toLowerCase()] || type.replace(/_/g, ' ')

  const materialIcon = (type: string) => ({ summary: '▤', flashcards: '▦', quiz: '?', practice_questions: '?', mind_map: '⌘', mindmap: '⌘', podcast: '◉' } as Record<string, string>)[type.toLowerCase()] || '•'

  return <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
    <div style={{ background: N.navy, padding: '0 18px 20px', flexShrink: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
        <div><div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>My Study</div><div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', marginTop: 2 }}>Your documents and the materials created from them</div></div>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        {([['documents', 'Documents'], ['materials', 'Study Materials']] as const).map(([key, label]) => <button key={key} onClick={() => setTab(key)} style={{ flex: 1, padding: '8px 10px', borderRadius: 11, background: tab === key ? N.gold : 'rgba(255,255,255,0.08)', color: tab === key ? N.navy : 'rgba(255,255,255,0.7)', border: 'none', fontWeight: 800, fontSize: 11, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{label}</button>)}
      </div>
    </div>
    <div style={{ flex: 1, overflowY: 'auto', padding: 16 }} className="scrollbar-hide">
      {loading ? <GenerationLoading label="Loading your study library…" /> : error ? <GenerationError error={error} /> : tab === 'documents' ? <>
        <div style={{ fontSize: 12, color: T.textMuted, marginBottom: 12 }}>Open a document to study it, ask Ada about it, or create study materials.</div>
        {documents.length === 0 ? <EmptyState icon="▣" title="No documents yet" sub="Upload your notes, slides, or past papers to start studying." action="Upload document" onAction={() => setScreen('upload')} /> : documents.map(d => <button key={d.id} onClick={() => openDocument(d.id)} style={{ width: '100%', textAlign: 'left', background: T.card, border: `1px solid ${T.border}`, borderRadius: 16, padding: 15, marginBottom: 10, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}><div style={{ display: 'flex', alignItems: 'center', gap: 12 }}><div style={{ width: 44, height: 44, borderRadius: 12, background: `${N.gold}18`, color: N.gold, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900 }}>▣</div><div style={{ flex: 1, minWidth: 0 }}><div style={{ fontWeight: 800, fontSize: 13, color: T.text }} className="line-clamp-1">{d.title}</div><div style={{ fontSize: 11, color: T.textMuted, marginTop: 4 }}>{d.page_count ? `${d.page_count} pages` : 'Document'}{d.created_at ? ` · ${new Date(d.created_at).toLocaleDateString()}` : ''}</div></div><div style={{ color: T.textMuted }}>{Ic.chevR()}</div></div></button>)}
      </> : <>
        <div style={{ fontSize: 12, color: T.textMuted, marginBottom: 12 }}>Everything here was created from one of your documents. Tap a material to replay it.</div>
        {materials.length === 0 ? <EmptyState icon="✦" title="No study materials yet" sub="Open a document and create a summary, flashcards, practice questions, mind map, or podcast." action="Open My Documents" onAction={() => setTab('documents')} /> : materials.map((m, i) => <button key={`${m.documentId}-${m.type}-${i}`} onClick={() => openMaterial(m)} style={{ width: '100%', textAlign: 'left', background: T.card, border: `1px solid ${T.border}`, borderRadius: 16, padding: 15, marginBottom: 10, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}><div style={{ display: 'flex', alignItems: 'center', gap: 12 }}><div style={{ width: 44, height: 44, borderRadius: 12, background: `${N.navy}0D`, color: N.navy, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900, fontSize: 18 }}>{materialIcon(m.type)}</div><div style={{ flex: 1, minWidth: 0 }}><div style={{ fontWeight: 800, fontSize: 13, color: T.text }}>{materialLabel(m.type)}</div><div style={{ fontSize: 11, color: T.textMuted, marginTop: 4 }} className="line-clamp-1">From: {m.documentTitle}</div></div><div style={{ color: T.textMuted }}>{Ic.chevR()}</div></div></button>)}
      </>}
      <div style={{ height: 'calc(90px + env(safe-area-inset-bottom, 0px))' }} />
    </div>
  </div>
}

'''
        if marker not in text:
            raise SystemExit('BottomNav marker not found')
        text = text.replace(marker, component + marker, 1)

    # Ensure the new screen is treated as part of the authenticated app shell.
    text = text.replace("'document-study','share-sheet'", "'document-study','study-materials','share-sheet'", 1)

    # Add the renderer case next to the existing library route.
    if "case 'study-materials':" not in text:
        text = must_replace(text, r"(case 'library':\s+return <LibraryScreen setScreen=\{setScreen\} />\n)", r"\1      case 'study-materials':   return <StudyMaterialsScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} />\n", 'study materials renderer')

    APP.write_text(text)


if __name__ == '__main__':
    main()
