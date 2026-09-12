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

    text = replace_once(
        text,
        "  | 'publish-library' | 'xp-progress' | 'study-streak' | 'achievements' | 'study-materials'\n",
        "  | 'publish-library' | 'xp-progress' | 'study-streak' | 'achievements' | 'study-materials' | 'document-reader'\n",
        'document-reader screen union',
    )

    if 'function DocumentStudyHubScreen(' not in text:
        marker = "function BottomNav({ active, setScreen }: { active: Screen; setScreen: (s: Screen) => void }) {"
        component = r'''
// ─── DOCUMENT STUDY HUB ─────────────────────────────────────────────────────
// A document is the student's study home: read it, ask Ada about it, replay
// existing materials, or create a new material. Generation remains owned by
// the existing material screens/reusable-generation backend.
function DocumentStudyHubScreen({
  setScreen,
  activeDocumentId,
}: {
  setScreen: (s: Screen) => void
  activeDocumentId: number | null
}) {
  const { tokens: T } = useTheme()
  const [document, setDocument] = useState<DocumentDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)

  useEffect(() => {
    let cancelled = false
    if (activeDocumentId == null) {
      setLoading(false)
      setError('No document selected.')
      return
    }
    setLoading(true)
    setError('')
    api<DocumentDetail>(`/documents/${activeDocumentId}`)
      .then(data => { if (!cancelled) setDocument(data) })
      .catch(err => { if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not open this document.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [activeDocumentId])

  if (loading) return <GenerationLoading label="Opening your document…" />
  if (error || !document) return <GenerationError error={error || 'Document unavailable.'} />

  const readyMaterials = (document.materials || []).filter(m => m.status === 'ready')
  const materialMeta: Record<string, { label: string; icon: string; screen: Screen }> = {
    summary: { label: 'Summary', icon: '▤', screen: 'summary' },
    flashcards: { label: 'Flashcards', icon: '▦', screen: 'flashcards' },
    quiz: { label: 'Practice Questions', icon: '?', screen: 'quiz' },
    practice_questions: { label: 'Practice Questions', icon: '?', screen: 'quiz' },
    mind_map: { label: 'Mind Map', icon: '⌘', screen: 'mind-map' },
    mindmap: { label: 'Mind Map', icon: '⌘', screen: 'mind-map' },
    podcast: { label: 'Podcast', icon: '◉', screen: 'podcast-player' },
  }

  const openMaterial = (type: string) => {
    const key = type.toLowerCase().replace(/-/g, '_')
    setScreen(materialMeta[key]?.screen || 'document-reader')
  }

  const createOptions: Array<{ type: string; label: string; description: string; icon: string; screen: Screen }> = [
    { type: 'summary', label: 'Summary', description: 'Condense the key ideas and explanations.', icon: '▤', screen: 'summary' },
    { type: 'flashcards', label: 'Flashcards', description: 'Turn important concepts into active recall cards.', icon: '▦', screen: 'flashcards' },
    { type: 'practice_questions', label: 'Practice Questions', description: 'Generate questions to test your understanding.', icon: '?', screen: 'quiz' },
    { type: 'mind_map', label: 'Mind Map', description: 'See the concepts and how they connect.', icon: '⌘', screen: 'mind-map' },
    { type: 'podcast', label: 'Podcast', description: 'Listen to an explanation based on this document.', icon: '◉', screen: 'podcast-player' },
  ]

  return <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
    <div style={{ background: N.navy, padding: '12px 18px 22px', flexShrink: 0 }}>
      <button onClick={() => setScreen('study-materials')} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.75)', padding: 0, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'Plus Jakarta Sans', fontSize: 11, fontWeight: 700 }}>
        {Ic.back()} My Study
      </button>
      <div style={{ marginTop: 18 }}>
        <div style={{ color: '#fff', fontSize: 20, fontWeight: 850, lineHeight: 1.25 }} className="line-clamp-2">{document.title}</div>
        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11, marginTop: 6 }}>
          {document.page_count ? `${document.page_count} pages` : 'Document'}{document.file_type ? ` · ${document.file_type.toUpperCase()}` : ''}
        </div>
      </div>
    </div>

    <div style={{ flex: 1, overflowY: 'auto', padding: 16 }} className="scrollbar-hide">
      <button onClick={() => setScreen('document-reader')} style={{ width: '100%', background: `linear-gradient(135deg, ${N.navy}, ${N.navy3})`, border: 'none', borderRadius: 17, padding: '17px 16px', color: '#fff', textAlign: 'left', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 44, height: 44, borderRadius: 13, background: 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>▤</div>
          <div style={{ flex: 1 }}><div style={{ fontWeight: 850, fontSize: 14 }}>Continue Reading</div><div style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)', marginTop: 3 }}>Read this document in Prepza</div></div>
          <span style={{ fontSize: 20 }}>›</span>
        </div>
      </button>

      <section style={{ marginBottom: 22 }}>
        <div style={{ fontWeight: 850, fontSize: 14, color: T.text, marginBottom: 10 }}>Study with Ada</div>
        <button onClick={() => setScreen('ai-tutor')} style={{ width: '100%', background: T.card, border: `1px solid ${T.border}`, borderRadius: 15, padding: 14, display: 'flex', alignItems: 'center', gap: 12, textAlign: 'left', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
          <div style={{ width: 42, height: 42, borderRadius: 12, background: `${N.gold}18`, color: N.gold, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 19, fontWeight: 900 }}>✦</div>
          <div style={{ flex: 1 }}><div style={{ color: T.text, fontWeight: 800, fontSize: 13 }}>Ask anything about these notes</div><div style={{ color: T.textMuted, fontSize: 11, marginTop: 3 }}>Use Ada while this document is your study context.</div></div>
          <span style={{ color: T.textMuted }}>›</span>
        </button>
      </section>

      <section>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <div style={{ fontWeight: 850, fontSize: 14, color: T.text }}>Your Study Materials</div>
          <button onClick={() => setShowCreate(true)} style={{ background: 'none', border: 'none', color: N.gold, fontWeight: 800, fontSize: 11, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>+ Create</button>
        </div>
        {readyMaterials.length === 0 ? (
          <div style={{ background: T.card, border: `1px dashed ${T.border}`, borderRadius: 15, padding: 18, textAlign: 'center' }}>
            <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.5 }}>Nothing has been created from this document yet.</div>
            <button onClick={() => setShowCreate(true)} style={{ marginTop: 11, background: N.gold, color: N.navy, border: 'none', borderRadius: 10, padding: '8px 13px', fontWeight: 850, fontSize: 11, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Create Study Material</button>
          </div>
        ) : readyMaterials.map((m, i) => {
          const meta = materialMeta[m.type.toLowerCase().replace(/-/g, '_')] || { label: m.type.replace(/_/g, ' '), icon: '•', screen: 'document-reader' as Screen }
          return <button key={`${m.type}-${i}`} onClick={() => openMaterial(m.type)} style={{ width: '100%', background: T.card, border: `1px solid ${T.border}`, borderRadius: 15, padding: 14, marginBottom: 9, display: 'flex', alignItems: 'center', gap: 12, textAlign: 'left', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
            <div style={{ width: 42, height: 42, borderRadius: 12, background: `${N.navy}0D`, color: N.navy, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, fontWeight: 900 }}>{meta.icon}</div>
            <div style={{ flex: 1, minWidth: 0 }}><div style={{ color: T.text, fontWeight: 800, fontSize: 13, textTransform: 'capitalize' }}>{meta.label}</div><div style={{ color: T.textMuted, fontSize: 10, marginTop: 3 }}>Ready to replay</div></div>
            <span style={{ color: T.textMuted }}>›</span>
          </button>
        })}
      </section>
      <div style={{ height: 'calc(90px + env(safe-area-inset-bottom, 0px))' }} />
    </div>

    {showCreate && <div onClick={() => setShowCreate(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.48)', zIndex: 100, display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
      <div onClick={e => e.stopPropagation()} style={{ width: '100%', maxWidth: 520, maxHeight: '82vh', overflowY: 'auto', background: T.card, borderRadius: '22px 22px 0 0', padding: '18px 16px calc(22px + env(safe-area-inset-bottom, 0px))' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}><div><div style={{ color: T.text, fontWeight: 850, fontSize: 16 }}>Create Study Material</div><div style={{ color: T.textMuted, fontSize: 11, marginTop: 3 }}>Choose what you want to make from this document.</div></div><button onClick={() => setShowCreate(false)} style={{ background: T.pageBg, border: 'none', borderRadius: 10, width: 34, height: 34, cursor: 'pointer', color: T.text }}>{Ic.close()}</button></div>
        {createOptions.map(option => <button key={option.type} onClick={() => { setShowCreate(false); setScreen(option.screen) }} style={{ width: '100%', background: T.pageBg, border: `1px solid ${T.border}`, borderRadius: 14, padding: 13, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 12, textAlign: 'left', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}><div style={{ width: 40, height: 40, borderRadius: 11, background: `${N.gold}18`, color: N.gold, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900 }}>{option.icon}</div><div><div style={{ color: T.text, fontWeight: 800, fontSize: 12 }}>{option.label}</div><div style={{ color: T.textMuted, fontSize: 10, marginTop: 3 }}>{option.description}</div></div></button>)}
      </div>
    </div>}
  </div>
}

'''
        if marker not in text:
            raise SystemExit('BottomNav marker not found')
        text = text.replace(marker, component + marker, 1)

    route_pattern = r"case 'document-study':\s*return <DocumentStudyScreen[^\n]*\n"
    replacement = "case 'document-study': return <DocumentStudyHubScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />\n      case 'document-reader': return <DocumentStudyScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />\n"
    text2, count = re.subn(route_pattern, replacement, text, count=1)
    if count == 0:
        if "case 'document-study': return <DocumentStudyHubScreen" not in text:
            raise SystemExit('document-study route case not found')
    else:
        text = text2

    APP.write_text(text)


if __name__ == '__main__':
    main()
