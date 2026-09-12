from pathlib import Path

APP = Path('frontend/src/App.tsx')


def replace_once(text, old, new, label):
    if old not in text:
        if new in text:
            return text
        raise SystemExit(f'Expected {label} block not found')
    return text.replace(old, new, 1)


def main():
    text = APP.read_text()

    text = replace_once(
        text,
        "  | 'publish-library' | 'xp-progress' | 'study-streak' | 'achievements'\n",
        "  | 'publish-library' | 'xp-progress' | 'study-streak' | 'achievements' | 'study-materials'\n",
        'Screen union',
    )

    old_actions = """            {\n              { icon: '📤', label: 'Upload', action: () => setScreen('upload') },\n              { icon: '✦', label: 'Ada', action: () => setScreen('ai-tutor') },\n              { icon: '🃏', label: 'Flashcards', action: () => setScreen('flashcards') },\n              { icon: '📝', label: 'Practice', action: () => setScreen('quiz') },\n              { icon: '🎙️', label: 'Podcasts', action: () => setScreen('podcast-player') },\n            ].map((t, i) => ("""
    new_actions = """            {\n              { icon: '📤', label: 'Upload', action: () => setScreen('upload') },\n              { icon: '▣', label: 'My Study', action: () => setScreen('study-materials') },\n              { icon: '✦', label: 'Ada', action: () => setScreen('ai-tutor') },\n              { icon: '🎙️', label: 'Podcasts', action: () => setScreen('podcast-library') },\n            ].map((t, i) => ("""
    text = replace_once(text, old_actions, new_actions, 'Home quick actions')

    old_doc_stat = "{ label: 'Docs', value: summary ? String(summary.documents_count) : '—', color: '#4C7BC9', dest: 'library' as Screen },"
    new_doc_stat = "{ label: 'Docs', value: summary ? String(summary.documents_count) : '—', color: '#4C7BC9', dest: 'study-materials' as Screen },"
    text = replace_once(text, old_doc_stat, new_doc_stat, 'Profile Docs shortcut')

    marker = "function BottomNav({ active, setScreen }: { active: Screen; setScreen: (s: Screen) => void }) {"
    component = r'''// ─── MY STUDY / STUDY MATERIALS ───────────────────────────────────────────────
// One place for a student's private study sources and the AI materials created
// from them. Materials always retain the source document in the UI, so replay
// never feels detached from the notes that produced it.
function StudyMaterialsScreen({ setScreen, setActiveDocumentId }: { setScreen: (s: Screen) => void; setActiveDocumentId: (id: number | null) => void }) {
  const { tokens: T } = useTheme()
  const [tab, setTab] = useState<'documents' | 'materials'>('documents')
  const [documents, setDocuments] = useState<HomeDocument[]>([])
  const [materialRows, setMaterialRows] = useState<{ documentId: number; documentTitle: string; type: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    api<{ documents: HomeDocument[] }>('/documents')
      .then(async res => {
        if (cancelled) return
        const readyDocs = res.documents.filter(d => d.status === 'ready')
        setDocuments(readyDocs)
        const details = await Promise.all(readyDocs.slice(0, 20).map(async d => {
          try {
            const detail = await api<DocumentDetail>(`/documents/${d.id}`)
            return (detail.materials || []).filter(m => m.status === 'ready').map(m => ({
              documentId: d.id,
              documentTitle: d.title,
              type: m.type,
            }))
          } catch { return [] }
        }))
        if (!cancelled) setMaterialRows(details.flat())
      })
      .catch(e => { if (!cancelled) setError(e instanceof ApiError ? e.message : 'Could not load your study library.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const openDocument = (id: number) => {
    setActiveDocumentId(id)
    setScreen('document-study')
  }

  const openMaterial = (row: { documentId: number; type: string }) => {
    setActiveDocumentId(row.documentId)
    const type = row.type.toLowerCase().replace('-', '_')
    const destination: Screen = type === 'summary' ? 'summary'
      : type === 'flashcards' ? 'flashcards'
      : type === 'quiz' || type === 'practice_questions' ? 'quiz'
      : type === 'mind_map' || type === 'mindmap' ? 'mind-map'
      : type === 'podcast' ? 'podcast-player'
      : 'document-study'
    setScreen(destination)
  }

  const typeLabel = (type: string) => ({ summary: 'Summary', flashcards: 'Flashcards', quiz: 'Practice Questions', practice_questions: 'Practice Questions', mind_map: 'Mind Map', mindmap: 'Mind Map', podcast: 'Podcast' } as Record<string, string>)[type.toLowerCase()] || type.replace(/_/g, ' ')
  const typeIcon = (type: string) => ({ summary: '▤', flashcards: '▦', quiz: '?', practice_questions: '?', mind_map: '⌘', mindmap: '⌘', podcast: '◉' } as Record<string, string>)[type.toLowerCase()] || '•'

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 20px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>My Study</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', marginTop: 2 }}>Your documents and everything you create from them</div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {([['documents', 'Documents'], ['materials', 'Study Materials']] as const).map(([key, label]) => (
            <button key={key} onClick={() => setTab(key)} style={{ flex: 1, padding: '8px 10px', borderRadius: 11, background: tab === key ? N.gold : 'rgba(255,255,255,0.08)', color: tab === key ? N.navy : 'rgba(255,255,255,0.7)', border: 'none', fontWeight: 800, fontSize: 11, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{label}</button>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: 16 }} className="scrollbar-hide">
        {loading ? (
          <GenerationLoading label="Loading your study library…" />
        ) : error ? (
          <GenerationError error={error} />
        ) : tab === 'documents' ? (
          <>
            <div style={{ fontSize: 12, color: T.textMuted, marginBottom: 12 }}>Open a document to study it, ask Ada about it, or create new study materials.</div>
            {documents.length === 0 ? (
              <EmptyState icon="▣" title="No documents yet" sub="Upload your notes, slides, or past papers to start studying." action="Upload document" onAction={() => setScreen('upload')} />
            ) : documents.map(d => (
              <button key={d.id} onClick={() => openDocument(d.id)} style={{ width: '100%', textAlign: 'left', background: T.card, border: `1px solid ${T.border}`, borderRadius: 16, padding: 15, marginBottom: 10, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ width: 44, height: 44, borderRadius: 12, background: `${N.gold}18`, color: N.gold, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900, fontSize: 18, flexShrink: 0 }}>▣</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 800, fontSize: 13, color: T.text }} className="line-clamp-1">{d.title}</div>
                    <div style={{ fontSize: 11, color: T.textMuted, marginTop: 4 }}>{d.page_count ? `${d.page_count} pages` : 'Document'}{d.created_at ? ` · ${new Date(d.created_at).toLocaleDateString()}` : ''}</div>
                  </div>
                  <div style={{ color: T.textMuted }}>{Ic.chevR()}</div>
                </div>
              </button>
            ))}
          </>
        ) : (
          <>
            <div style={{ fontSize: 12, color: T.textMuted, marginBottom: 12 }}>Everything here was created from one of your documents. Tap a material to replay it.</div>
            {materialRows.length === 0 ? (
              <EmptyState icon="✦" title="No study materials yet" sub="Open a document and create a summary, flashcards, practice questions, mind map, or podcast." action="Open My Documents" onAction={() => setTab('documents')} />
            ) : materialRows.map((row, i) => (
              <button key={`${row.documentId}-${row.type}-${i}`} onClick={() => openMaterial(row)} style={{ width: '100%', textAlign: 'left', background: T.card, border: `1px solid ${T.border}`, borderRadius: 16, padding: 15, marginBottom: 10, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ width: 44, height: 44, borderRadius: 12, background: `${N.navy}0D`, color: N.navy, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900, fontSize: 18, flexShrink: 0 }}>{typeIcon(row.type)}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 800, fontSize: 13, color: T.text }}>{typeLabel(row.type)}</div>
                    <div style={{ fontSize: 11, color: T.textMuted, marginTop: 4 }} className="line-clamp-1">From: {row.documentTitle}</div>
                  </div>
                  <div style={{ color: T.textMuted }}>{Ic.chevR()}</div>
                </div>
              </button>
            ))}
          </>
        )}
        <div style={{ height: 'calc(90px + env(safe-area-inset-bottom, 0px))' }} />
      </div>
    </div>
  )
}

'''
    if 'function StudyMaterialsScreen(' not in text:
        if marker not in text:
            raise SystemExit('BottomNav marker not found')
        text = text.replace(marker, component + marker, 1)

    old_home_nav = "  const isHome  = ['home','ai-tutor','opportunities','opportunity-detail','podcast-player','podcast-library','flashcards','quiz','summary','upload','processing','doc-ready','document-study','share-sheet','share-opp-form','edu-upload-form','notifications','library','mind-map'].includes(active)"
    new_home_nav = "  const isHome  = ['home','ai-tutor','opportunities','opportunity-detail','podcast-player','podcast-library','flashcards','quiz','summary','upload','processing','doc-ready','document-study','study-materials','share-sheet','share-opp-form','edu-upload-form','notifications','library','mind-map'].includes(active)"
    text = replace_once(text, old_home_nav, new_home_nav, 'Bottom navigation home grouping')

    old_case = "      case 'library':           return <LibraryScreen setScreen={setScreen} />\n"
    new_case = "      case 'library':           return <LibraryScreen setScreen={setScreen} />\n      case 'study-materials':   return <StudyMaterialsScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} />\n"
    text = replace_once(text, old_case, new_case, 'screen renderer')

    APP.write_text(text)
    print('Applied student navigation/study flow patch.')


if __name__ == '__main__':
    main()
