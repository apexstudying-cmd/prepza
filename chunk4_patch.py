"""
Chunk 4 patch: wires DocumentStudyScreen, SummaryScreen, QuizScreen,
FlashcardsScreen, MindMapScreen, and PodcastPlayerScreen in
frontend/src/App.tsx to the real backend AI-generation pipeline:
  POST /documents/:id/summarize | /quiz | /flashcards | /mindmap
  POST /documents/:id/podcast-script -> POST + GET /documents/:id/podcast-audio
  POST /documents/:id/quiz/:material_id/complete
  POST /documents/:id/flashcards/:material_id/complete

Extends the activeDocumentId pattern from Chunk 3 so HomeScreen can set
which document is "open" when a student taps an existing doc, not just
right after a fresh upload.

FLAGGED BACKEND GAPS (deliberately NOT wired, per the chunk's own
instructions not to fabricate AI output client-side):
  - AITutorScreen's free-form "ask anything" chat has no backend route
    tied to it (no /ai-tutor or general-chat endpoint in app.py). Left
    as pre-existing mock chat, untouched by this patch.
  - DocumentStudyScreen's "AI Chat" tab (Explain / Simplify buttons +
    freeform ask input) has no dedicated "explain this paragraph"
    endpoint either. Left as pre-existing mock chat, untouched. Only
    the "Document" tab (real file viewer) and header (real title/page
    count) are wired to the backend in this patch.
  - PodcastLibraryScreen lists podcasts across MULTIPLE documents, but
    the backend only exposes podcast script/audio for ONE document at
    a time (GET /documents/:id/podcast-audio) - there is no "list all
    my podcasts" endpoint. Left as pre-existing mock list, untouched.

Every replacement is assert-guarded: if the expected original text
isn't found exactly once, the script stops and changes nothing.

Run from the project root:
    cd ~/Desktop/prepza
    python chunk4_patch.py

Then review with:
    git diff frontend/src/App.tsx
"""
import io

PATH = "frontend/src/App.tsx"

with io.open(PATH, encoding="utf-8", newline="") as f:
    src = f.read()

original_src = src


def apply(label, old, new):
    global src
    count = src.count(old)
    assert count == 1, (
        f"[{label}] expected exactly 1 occurrence, found {count}. "
        f"File may have drifted - aborting without changes."
    )
    src = src.replace(old, new, 1)
    print(f"  ok: {label}")


print("Applying Chunk 4 patches...")

# ─────────────────────────────────────────────────────────────────────────
# 1. Shared types for generation responses, placed after DocumentDetail
# ─────────────────────────────────────────────────────────────────────────

apply(
    "Add generation response types after DocumentDetail",
    """type DocumentDetail = {
  id: number; title: string; original_filename: string; status: string
  file_type: string | null; file_size_bytes: number | null; page_count: number | null
  error_message: string | null; view_url: string | null
  materials: { type: string; status: string }[]; created_at: string | null
}""",
    """type DocumentDetail = {
  id: number; title: string; original_filename: string; status: string
  file_type: string | null; file_size_bytes: number | null; page_count: number | null
  error_message: string | null; view_url: string | null
  materials: { type: string; status: string }[]; created_at: string | null
}

// Payload shape inside `summary`/`quiz`/`flashcards`/`mindmap` below is
// whatever ai_service.py produces - not pinned down here, so every
// consumer renders defensively (checks a few likely field names, falls
// back to raw JSON) rather than assuming one exact shape.
type CompletionResponse = { xp_awarded: number; newly_unlocked_achievements: string[] }

function AchievementToast({ codes }: { codes: string[] }) {
  if (codes.length === 0) return null
  return (
    <div style={{ background: 'rgba(201,168,76,0.15)', border: `1px solid ${N.gold}55`, borderRadius: 12, padding: '10px 14px', margin: '0 0 14px', fontSize: 12, fontWeight: 700, color: N.gold }}>
      🏆 Achievement unlocked: {codes.join(', ')}
    </div>
  )
}

function GenerationError({ error }: { error: string }) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 32, textAlign: 'center' }}>
      <div style={{ fontSize: 40, marginBottom: 14 }}>⚠️</div>
      <div style={{ color: '#6B7280', fontSize: 13, maxWidth: 280 }}>{error}</div>
    </div>
  )
}

function GenerationLoading({ label }: { label: string }) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 32 }}>
      <div style={{ width: 40, height: 40, border: `3px solid rgba(201,168,76,0.2)`, borderTopColor: N.gold, borderRadius: '50%', animation: 'spin-slow 0.8s linear infinite', marginBottom: 16 }} />
      <div style={{ color: '#6B7280', fontSize: 13 }}>{label}</div>
    </div>
  )
}""",
)

# ─────────────────────────────────────────────────────────────────────────
# 2. App(): thread activeDocumentId/setActiveDocumentId to home + all
#    document-study/generation screens
# ─────────────────────────────────────────────────────────────────────────

apply(
    "App() thread props into home/document-study/generation cases",
    """      case 'home':              return <HomeScreen setScreen={setScreen} />""",
    """      case 'home':              return <HomeScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} />""",
)

apply(
    "App() thread props into document-study/summary/quiz/flashcards/mindmap/podcast-player cases",
    """      case 'document-study':    return <DocumentStudyScreen setScreen={setScreen} />
      case 'ai-tutor':          return <AITutorScreen setScreen={setScreen} />
      case 'flashcards':        return <FlashcardsScreen setScreen={setScreen} />
      case 'quiz':              return <QuizScreen setScreen={setScreen} />
      case 'podcast-player':    return <PodcastPlayerScreen setScreen={setScreen} />
      case 'podcast-library':   return <PodcastLibraryScreen setScreen={setScreen} />
      case 'summary':           return <SummaryScreen setScreen={setScreen} />""",
    """      case 'document-study':    return <DocumentStudyScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'ai-tutor':          return <AITutorScreen setScreen={setScreen} />
      case 'flashcards':        return <FlashcardsScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'quiz':              return <QuizScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'podcast-player':    return <PodcastPlayerScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'podcast-library':   return <PodcastLibraryScreen setScreen={setScreen} />
      case 'summary':           return <SummaryScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />""",
)

apply(
    "App() thread props into mind-map case",
    """      case 'mind-map':          return <MindMapScreen setScreen={setScreen} />""",
    """      case 'mind-map':          return <MindMapScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />""",
)

apply(
    "App() thread props into default: fallback case (also renders HomeScreen)",
    """      default:                  return <HomeScreen setScreen={setScreen} />""",
    """      default:                  return <HomeScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} />""",
)

# ─────────────────────────────────────────────────────────────────────────
# 3. HomeScreen: set activeDocumentId when a document card is tapped
# ─────────────────────────────────────────────────────────────────────────

apply(
    "HomeScreen accept setActiveDocumentId prop",
    """function HomeScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [notifCount] = useState(3)
  const loading = useLoading(1200)

  const [displayName, setDisplayName] = useState<string | null>(null)""",
    """function HomeScreen({ setScreen, setActiveDocumentId }: { setScreen: (s: Screen) => void; setActiveDocumentId: (id: number | null) => void }) {
  const [notifCount] = useState(3)
  const loading = useLoading(1200)

  const [displayName, setDisplayName] = useState<string | null>(null)""",
)

apply(
    "HomeScreen featured doc + rest docs set activeDocumentId on click",
    """              {/* Featured doc */}
              <div onClick={() => setScreen('document-study')} style={{ background: `linear-gradient(135deg,${N.navy},${N.navy3})`, borderRadius: 18, padding: 18, cursor: 'pointer', position: 'relative', overflow: 'hidden', marginBottom: 10 }}>
                <div style={{ position: 'absolute', right: -20, top: -20, width: 120, height: 120, background: 'rgba(201,168,76,0.07)', borderRadius: '50%' }} />
                <div style={{ display: 'flex', gap: 14, alignItems: 'center', marginBottom: 14 }}>
                  <div style={{ width: 48, height: 48, background: 'rgba(201,168,76,0.15)', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, color: N.gold, fontWeight: 800 }}>📄</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 800, fontSize: 14, color: '#fff' }} className="line-clamp-1">{featuredDoc.title}</div>
                    <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', marginTop: 2, textTransform: 'capitalize' }}>{featuredDoc.status}</div>
                  </div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <button onClick={e => { e.stopPropagation(); setScreen('document-study') }} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 11, border: 'none', borderRadius: 10, padding: '6px 14px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Continue →</button>
                </div>
              </div>
              {/* Other docs */}
              {restDocs.map(d => (
                <div key={d.id} onClick={() => setScreen('document-study')} style={{ background: '#fff', borderRadius: 14, padding: '12px 14px', marginBottom: 8, boxShadow: '0 2px 10px rgba(0,0,0,0.05)', display: 'flex', gap: 12, alignItems: 'center', cursor: 'pointer', border: '1px solid rgba(0,0,0,0.04)' }}>
                  <div style={{ width: 40, height: 40, background: N.gold + '18', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, color: N.gold, fontWeight: 800 }}>📄</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 12, color: N.navy }} className="line-clamp-1">{d.title}</div>
                    <div style={{ fontSize: 11, color: '#6B7280', textTransform: 'capitalize' }}>{d.status}</div>
                  </div>
                </div>
              ))}""",
    """              {/* Featured doc */}
              <div onClick={() => { setActiveDocumentId(featuredDoc.id); setScreen('document-study') }} style={{ background: `linear-gradient(135deg,${N.navy},${N.navy3})`, borderRadius: 18, padding: 18, cursor: 'pointer', position: 'relative', overflow: 'hidden', marginBottom: 10 }}>
                <div style={{ position: 'absolute', right: -20, top: -20, width: 120, height: 120, background: 'rgba(201,168,76,0.07)', borderRadius: '50%' }} />
                <div style={{ display: 'flex', gap: 14, alignItems: 'center', marginBottom: 14 }}>
                  <div style={{ width: 48, height: 48, background: 'rgba(201,168,76,0.15)', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, color: N.gold, fontWeight: 800 }}>📄</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 800, fontSize: 14, color: '#fff' }} className="line-clamp-1">{featuredDoc.title}</div>
                    <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', marginTop: 2, textTransform: 'capitalize' }}>{featuredDoc.status}</div>
                  </div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <button onClick={e => { e.stopPropagation(); setActiveDocumentId(featuredDoc.id); setScreen('document-study') }} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 11, border: 'none', borderRadius: 10, padding: '6px 14px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Continue →</button>
                </div>
              </div>
              {/* Other docs */}
              {restDocs.map(d => (
                <div key={d.id} onClick={() => { setActiveDocumentId(d.id); setScreen('document-study') }} style={{ background: '#fff', borderRadius: 14, padding: '12px 14px', marginBottom: 8, boxShadow: '0 2px 10px rgba(0,0,0,0.05)', display: 'flex', gap: 12, alignItems: 'center', cursor: 'pointer', border: '1px solid rgba(0,0,0,0.04)' }}>
                  <div style={{ width: 40, height: 40, background: N.gold + '18', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, color: N.gold, fontWeight: 800 }}>📄</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 12, color: N.navy }} className="line-clamp-1">{d.title}</div>
                    <div style={{ fontSize: 11, color: '#6B7280', textTransform: 'capitalize' }}>{d.status}</div>
                  </div>
                </div>
              ))}""",
)

# ─────────────────────────────────────────────────────────────────────────
# 4. DocumentStudyScreen: real header + real document viewer (doc tab only)
# ─────────────────────────────────────────────────────────────────────────

apply(
    "DocumentStudyScreen accept activeDocumentId + load real doc",
    """function DocumentStudyScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [tab, setTab] = useState<'doc'|'ai'|'tools'>('doc')
  const [askInput, setAskInput] = useState('')
  const [showMenu, setShowMenu] = useState(false)
  const [showDots, setShowDots] = useState(false)
  const [showRename, setShowRename] = useState(false)
  const [showDelete, setShowDelete] = useState(false)
  const [showReport, setShowReport] = useState(false)
  const [renameVal, setRenameVal] = useState('ACT 101 – Interest Theory')
  const [savedToLib, setSavedToLib] = useState(false)
  const loading = useLoading(700)
  const [messages, setMessages] = useState([
    { role: 'ai', text: "I've read your ACT 101 notes. I can explain concepts, quiz you, create flashcards, or summarise any section. What would you like to do?\\n\\n📎 Using: ACT 101 – Interest Theory" },
  ])

  if (loading) return <SkeletonDocument />""",
    """function DocumentStudyScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const [tab, setTab] = useState<'doc'|'ai'|'tools'>('doc')
  const [askInput, setAskInput] = useState('')
  const [showMenu, setShowMenu] = useState(false)
  const [showDots, setShowDots] = useState(false)
  const [showRename, setShowRename] = useState(false)
  const [showDelete, setShowDelete] = useState(false)
  const [showReport, setShowReport] = useState(false)
  const [renameVal, setRenameVal] = useState('')
  const [savedToLib, setSavedToLib] = useState(false)
  const loading = useLoading(700)
  const [messages, setMessages] = useState([
    { role: 'ai', text: "I've read your document. I can explain concepts, quiz you, create flashcards, or summarise any section. What would you like to do?" },
  ])

  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [docLoadError, setDocLoadError] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) return
    api<DocumentDetail>(`/documents/${activeDocumentId}`)
      .then(d => { setDoc(d); setRenameVal(d.title) })
      .catch(e => setDocLoadError(e instanceof ApiError ? e.message : 'Could not load this document.'))
  }, [activeDocumentId])

  if (loading) return <SkeletonDocument />

  if (activeDocumentId == null) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.bg, padding: 32, textAlign: 'center' }}>
        <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 8 }}>No document selected</div>
        <div style={{ color: '#6B7280', fontSize: 13, marginBottom: 24 }}>Open a document from Home to study it here.</div>
        <button onClick={() => setScreen('home')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '12px 28px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Go Home</button>
      </div>
    )
  }""",
)

apply(
    "DocumentStudyScreen header title/subtitle real values",
    """          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: 14, color: '#fff' }} className="line-clamp-1">ACT 101 – Interest Theory</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>38 pages · Processed</div>
          </div>""",
    """          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: 14, color: '#fff' }} className="line-clamp-1">{doc?.title || 'Loading…'}</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>{doc?.page_count != null ? `${doc.page_count} pages · ` : ''}{doc?.status ? doc.status.charAt(0).toUpperCase() + doc.status.slice(1) : ''}</div>
          </div>""",
)

apply(
    "DocumentStudyScreen doc tab: one clean block replacement (real viewer + fallback)",
    """        {tab === 'doc' && (
          <div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 14, overflowX: 'auto' }} className="scrollbar-hide">
              <button onClick={doExplain} style={{ flexShrink: 0, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, border: `1px solid ${N.gold}33`, color: N.gold, fontSize: 11, fontWeight: 700, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Explain</button>
              <button onClick={doSimplify} style={{ flexShrink: 0, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, border: `1px solid ${N.gold}33`, color: N.gold, fontSize: 11, fontWeight: 700, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Simplify</button>
              <button onClick={() => setScreen('quiz')} style={{ flexShrink: 0, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, border: `1px solid ${N.gold}33`, color: N.gold, fontSize: 11, fontWeight: 700, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Quiz Me</button>
              <button onClick={() => setScreen('flashcards')} style={{ flexShrink: 0, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, border: `1px solid ${N.gold}33`, color: N.gold, fontSize: 11, fontWeight: 700, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Flashcards</button>
            </div>
            <div style={{ background: '#fff', borderRadius: 16, padding: 18, boxShadow: '0 2px 10px rgba(0,0,0,0.06)' }}>
              <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 4 }}>Chapter 3: Interest Theory</div>
              <div style={{ fontSize: 11, color: '#9CA3AF', marginBottom: 16 }}>Section 3.1 – Simple and Compound Interest</div>
              <p style={{ fontSize: 13, color: '#374151', lineHeight: 1.8, margin: '0 0 14px' }}>
                Interest theory forms the mathematical foundation of actuarial science. The <strong>accumulation function</strong> A(t) describes how a principal amount grows over time under a given interest rate structure.
              </p>
              <div onClick={() => setShowMenu(v => !v)} style={{ background: showMenu ? 'rgba(201,168,76,0.2)' : 'transparent', borderRadius: 6, cursor: 'pointer', padding: '2px 0', transition: 'background 0.2s', marginBottom: 14 }}>
                <p style={{ fontSize: 13, color: '#374151', lineHeight: 1.8, margin: 0 }}>
                  Under <strong>compound interest</strong>, the accumulation function is A(t) = A(0)(1+i)ᵗ, where i is the effective annual interest rate. For a principal of KES 10,000 at 8% p.a. for 3 years, A(3) = 10,000 × (1.08)³ = KES 12,597.12. The key property is that interest earned in one period itself earns interest in subsequent periods.
                </p>
              </div>
              {showMenu && (
                <div style={{ background: N.navy, borderRadius: 12, padding: '8px 6px', display: 'flex', gap: 6, marginBottom: 14 }}>
                  <button onClick={doExplain} style={{ flex: 1, background: `rgba(201,168,76,0.15)`, border: `1px solid ${N.gold}30`, color: N.gold, fontSize: 10, fontWeight: 700, padding: '7px 2px', borderRadius: 8, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Explain</button>
                  <button onClick={doSimplify} style={{ flex: 1, background: `rgba(201,168,76,0.15)`, border: `1px solid ${N.gold}30`, color: N.gold, fontSize: 10, fontWeight: 700, padding: '7px 2px', borderRadius: 8, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Simplify</button>
                  <button onClick={() => { setShowMenu(false); setScreen('quiz') }} style={{ flex: 1, background: `rgba(201,168,76,0.15)`, border: `1px solid ${N.gold}30`, color: N.gold, fontSize: 10, fontWeight: 700, padding: '7px 2px', borderRadius: 8, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Quiz Me</button>
                  <button onClick={() => { setShowMenu(false); setScreen('flashcards') }} style={{ flex: 1, background: `rgba(201,168,76,0.15)`, border: `1px solid ${N.gold}30`, color: N.gold, fontSize: 10, fontWeight: 700, padding: '7px 2px', borderRadius: 8, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Cards</button>
                  <button onClick={() => setShowMenu(false)} style={{ background: 'rgba(255,255,255,0.1)', border: 'none', color: '#fff', fontSize: 10, fontWeight: 700, padding: '7px 8px', borderRadius: 8, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>✕</button>
                </div>
              )}
              <div style={{ background: `rgba(201,168,76,0.08)`, borderRadius: 12, padding: '12px 14px', border: `1px solid ${N.gold}25` }}>
                <div style={{ fontSize: 11, color: N.gold, fontWeight: 700, marginBottom: 4 }}>✦ Tip: Highlight any text</div>
                <div style={{ fontSize: 12, color: '#374151', lineHeight: 1.6 }}>Tap any paragraph to get AI explanations, simplifications, or generate quiz questions from that specific text.</div>
              </div>
            </div>
          </div>
        )}""",
    """        {tab === 'doc' && (
          <div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 14, overflowX: 'auto' }} className="scrollbar-hide">
              <button onClick={() => setScreen('summary')} style={{ flexShrink: 0, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, border: `1px solid ${N.gold}33`, color: N.gold, fontSize: 11, fontWeight: 700, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Summarize</button>
              <button onClick={() => setScreen('quiz')} style={{ flexShrink: 0, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, border: `1px solid ${N.gold}33`, color: N.gold, fontSize: 11, fontWeight: 700, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Quiz Me</button>
              <button onClick={() => setScreen('flashcards')} style={{ flexShrink: 0, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, border: `1px solid ${N.gold}33`, color: N.gold, fontSize: 11, fontWeight: 700, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Flashcards</button>
              <button onClick={() => setScreen('mind-map')} style={{ flexShrink: 0, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, border: `1px solid ${N.gold}33`, color: N.gold, fontSize: 11, fontWeight: 700, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Mind Map</button>
            </div>
            {docLoadError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 12 }}>{docLoadError}</div>}
            {doc?.view_url ? (
              <div style={{ background: '#fff', borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 10px rgba(0,0,0,0.06)', height: '60vh' }}>
                {doc.file_type && ['jpg', 'jpeg', 'png'].includes(doc.file_type) ? (
                  <img src={doc.view_url} alt={doc.title} style={{ width: '100%', height: '100%', objectFit: 'contain', background: '#000' }} />
                ) : (
                  <iframe src={doc.view_url} title={doc.title} style={{ width: '100%', height: '100%', border: 'none' }} />
                )}
              </div>
            ) : (
              <div style={{ background: '#fff', borderRadius: 16, padding: 18, boxShadow: '0 2px 10px rgba(0,0,0,0.06)', textAlign: 'center' }}>
                <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 6 }}>{doc?.title || 'Loading document…'}</div>
                <div style={{ fontSize: 12, color: '#9CA3AF' }}>{doc ? 'Preview not available for this file type - use the tools above to study it.' : 'Fetching your document…'}</div>
              </div>
            )}
          </div>
        )}""",
)

# NOTE: DocumentStudyScreen's "AI Chat" tab (Explain/Simplify buttons +
# freeform ask input, referenced by doExplain/doSimplify/sendMsg further
# up in this component) is INTENTIONALLY left wired to its pre-existing
# canned/mock responses. There is no backend endpoint for "explain this
# paragraph" - see this script's module docstring for why that's a
# flagged gap rather than something to fabricate.

# ─────────────────────────────────────────────────────────────────────────
# 5. SummaryScreen: real POST /documents/:id/summarize
# ─────────────────────────────────────────────────────────────────────────

apply(
    "SummaryScreen full rewrite",
    """function SummaryScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [saved, setSaved] = useState(false)
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('document-study')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>AI Summary</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>ACT 101 – Interest Theory</div>
          </div>
          <button onClick={() => setScreen('share-sheet')} style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, padding: '7px 12px', color: '#fff', fontWeight: 600, fontSize: 12, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', marginRight: 6 }}>Share</button>
          <button onClick={() => setSaved(true)} style={{ background: saved ? `linear-gradient(135deg,${N.gold},${N.goldL})` : 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, padding: '7px 12px', color: saved ? N.navy : '#fff', fontWeight: 700, fontSize: 12, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{saved ? '✓ Saved' : 'Save'}</button>
        </div>
        {saved && <div style={{ background: 'rgba(76,201,123,0.15)', border: '1px solid rgba(76,201,123,0.3)', borderRadius: 10, padding: '7px 12px', marginTop: 8, fontSize: 12, color: '#4CC97B', fontWeight: 600 }}>✓ Saved to your Library</div>}
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 18 }} className="scrollbar-hide">
        <div style={{ background: '#fff', borderRadius: 16, padding: 20, boxShadow: '0 2px 10px rgba(0,0,0,0.06)' }}>
          <Pill text="AI Generated · 2 min read" />
          <div style={{ fontWeight: 800, fontSize: 18, color: N.navy, margin: '14px 0 6px' }}>ACT 101: Interest Theory – Key Concepts</div>
          <div style={{ fontSize: 11, color: '#9CA3AF', marginBottom: 20 }}>Generated from your 38-page lecture notes</div>
          {[
            { title: '1. Simple vs Compound Interest', body: 'Simple interest: A(t) = A(0)(1 + it). Interest earned does not itself earn interest.\\n\\nCompound interest: A(t) = A(0)(1+i)ᵗ. Interest is reinvested each period. Always use compound for exam questions unless stated.' },
            { title: '2. Present & Future Value', body: 'Future Value: FV = PV(1+i)ⁿ\\nPresent Value: PV = FV/(1+i)ⁿ = FV·vⁿ where v = 1/(1+i)\\n\\nKES 100,000 in 5 years at 10%: PV = 100,000/(1.1)⁵ = KES 62,092' },
            { title: '3. Annuities', body: 'Annuity-immediate: payments at END of period. a(n,i) = (1-vⁿ)/i\\n\\nAnnuity-due: payments at START of period. ä(n,i) = (1+i)·a(n,i)\\n\\nPerpetuity: a(∞,i) = 1/i' },
            { title: '4. Force of Interest', body: 'δ = ln(1+i) — continuously compounded rate.\\n\\nFor i = 10%: δ = ln(1.1) = 9.53%\\n\\nRelation: e^δ = 1+i' },
          ].map((s, i) => (
            <div key={i} style={{ marginBottom: 20 }}>
              <div style={{ fontWeight: 800, fontSize: 14, color: N.navy, marginBottom: 8 }}>{s.title}</div>
              <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.8, whiteSpace: 'pre-line' }}>{s.body}</div>
              {i < 3 && <div style={{ height: 1, background: 'rgba(0,0,0,0.06)', marginTop: 20 }} />}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}""",
    """function SummaryScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const [saved, setSaved] = useState(false)
  const [summary, setSummary] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) { setLoading(false); setError('No document selected.'); return }
    api<{ csrf_token: string }>('/me')
      .then(me => api<{ material_id: number; reused: boolean; summary: any }>(`/documents/${activeDocumentId}/summarize`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': me.csrf_token },
      }))
      .then(res => setSummary(res.summary))
      .catch(e => {
        if (e instanceof ApiError && e.status === 429) setError("You've hit the hourly generation limit - try again later.")
        else if (e instanceof ApiError && e.status === 503) setError('AI budget exceeded for now - try again later.')
        else setError(e instanceof ApiError ? e.message : 'Could not generate a summary. Please try again.')
      })
      .finally(() => setLoading(false))
  }, [activeDocumentId])

  // Renders whatever ai_service.py returned, without assuming one fixed
  // shape: a plain string, an array of {title, body}-like sections, or
  // (as a last resort) raw JSON so nothing is silently hidden.
  const renderSummaryBody = () => {
    if (typeof summary === 'string') {
      return <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.8, whiteSpace: 'pre-line' }}>{summary}</div>
    }
    if (Array.isArray(summary)) {
      return summary.map((s: any, i: number) => (
        <div key={i} style={{ marginBottom: 20 }}>
          {(s.title || s.heading) && <div style={{ fontWeight: 800, fontSize: 14, color: N.navy, marginBottom: 8 }}>{s.title || s.heading}</div>}
          <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.8, whiteSpace: 'pre-line' }}>{s.body || s.content || s.text || JSON.stringify(s)}</div>
          {i < summary.length - 1 && <div style={{ height: 1, background: 'rgba(0,0,0,0.06)', marginTop: 20 }} />}
        </div>
      ))
    }
    if (summary && typeof summary === 'object') {
      const text = summary.text || summary.content || summary.body
      if (text) return <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.8, whiteSpace: 'pre-line' }}>{text}</div>
      return <pre style={{ fontSize: 11, color: '#374151', whiteSpace: 'pre-wrap', background: '#F8F9FC', borderRadius: 10, padding: 12 }}>{JSON.stringify(summary, null, 2)}</pre>
    }
    return null
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('document-study')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>AI Summary</div>
          </div>
          <button onClick={() => setScreen('share-sheet')} style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, padding: '7px 12px', color: '#fff', fontWeight: 600, fontSize: 12, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', marginRight: 6 }}>Share</button>
          <button onClick={() => setSaved(true)} style={{ background: saved ? `linear-gradient(135deg,${N.gold},${N.goldL})` : 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, padding: '7px 12px', color: saved ? N.navy : '#fff', fontWeight: 700, fontSize: 12, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{saved ? '✓ Saved' : 'Save'}</button>
        </div>
        {saved && <div style={{ background: 'rgba(76,201,123,0.15)', border: '1px solid rgba(76,201,123,0.3)', borderRadius: 10, padding: '7px 12px', marginTop: 8, fontSize: 12, color: '#4CC97B', fontWeight: 600 }}>✓ Saved to your Library</div>}
      </div>
      {loading ? <GenerationLoading label="Generating your summary…" /> : error ? <GenerationError error={error} /> : (
        <div style={{ flex: 1, overflowY: 'auto', padding: 18 }} className="scrollbar-hide">
          <div style={{ background: '#fff', borderRadius: 16, padding: 20, boxShadow: '0 2px 10px rgba(0,0,0,0.06)' }}>
            <Pill text="AI Generated" />
            {renderSummaryBody()}
          </div>
        </div>
      )}
    </div>
  )
}""",
)

# ─────────────────────────────────────────────────────────────────────────
# 6. QuizScreen: real POST /documents/:id/quiz + completion
# ─────────────────────────────────────────────────────────────────────────

apply(
    "QuizScreen full rewrite",
    """function QuizScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [qi, setQi] = useState(0)
  const [selected, setSelected] = useState<number|null>(null)
  const [score, setScore] = useState(0)
  const [done, setDone] = useState(false)
  const loading = useLoading(500)
  if (loading) return <SkeletonQuiz />
  const q = quizData[qi]
  const choose = (i: number) => {
    if (selected !== null) return
    setSelected(i)
    if (i === q.ans) setScore(s => s + 1)
    setTimeout(() => {
      if (qi + 1 >= quizData.length) setDone(true)
      else { setQi(qi + 1); setSelected(null) }
    }, 1100)
  }
  if (done) return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.bg, padding: 32 }}>
      <div style={{ fontSize: 56, marginBottom: 16 }}>🎉</div>
      <div style={{ fontWeight: 800, fontSize: 24, color: N.navy, marginBottom: 6 }}>Quiz Complete!</div>
      <div style={{ fontSize: 15, color: '#6B7280', marginBottom: 24 }}>You scored {score}/{quizData.length}</div>
      <div style={{ width: 100, height: 100, borderRadius: '50%', background: score >= 3 ? '#D1FAE5' : '#FEE2E2', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 32 }}>
        <div style={{ fontWeight: 800, fontSize: 26, color: score >= 3 ? '#065F46' : '#C94C4C' }}>{Math.round((score/quizData.length)*100)}%</div>
      </div>
      <div style={{ display: 'flex', gap: 10 }}>
        <button onClick={() => { setQi(0); setScore(0); setDone(false); setSelected(null) }} style={{ background: N.navy, color: N.gold, fontWeight: 800, fontSize: 13, border: 'none', borderRadius: 14, padding: '12px 20px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Try Again</button>
        <button onClick={() => setScreen('document-study')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 13, border: 'none', borderRadius: 14, padding: '12px 20px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Back to Notes</button>
      </div>
    </div>
  )
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => setScreen('document-study')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>Practice Quiz</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>ACT 101 – Interest Theory</div>
          </div>
          <Pill text={`${score} correct`} color="#4CC97B" />
        </div>
        <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 99, height: 5, overflow: 'hidden' }}>
          <div style={{ width: `${((qi) / quizData.length) * 100}%`, height: '100%', background: N.gold, borderRadius: 99, transition: 'width 0.3s' }} />
        </div>
        <div style={{ textAlign: 'right', marginTop: 4, fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>Q{qi+1} of {quizData.length}</div>
      </div>
      <div style={{ flex: 1, padding: 20 }}>
        <div style={{ background: '#fff', borderRadius: 18, padding: 20, marginBottom: 20, boxShadow: '0 2px 12px rgba(0,0,0,0.07)' }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: N.gold, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 }}>Question {qi+1}</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: N.navy, lineHeight: 1.7 }}>{q.q}</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {q.opts.map((opt, i) => {
            const isSelected = selected === i
            const isCorrect = i === q.ans
            const bg = selected !== null
              ? isCorrect ? '#D1FAE5' : isSelected ? '#FEE2E2' : '#fff'
              : '#fff'
            const color = selected !== null
              ? isCorrect ? '#065F46' : isSelected ? '#C94C4C' : N.navy
              : N.navy
            return (
              <button key={i} onClick={() => choose(i)} style={{ background: bg, border: `2px solid ${selected !== null && isCorrect ? '#4CC97B' : selected !== null && isSelected ? '#C94C4C' : 'rgba(0,0,0,0.06)'}`, borderRadius: 14, padding: '14px 16px', cursor: selected !== null ? 'default' : 'pointer', textAlign: 'left', fontFamily: 'Plus Jakarta Sans', fontSize: 13, fontWeight: 600, color, transition: 'all 0.2s', display: 'flex', gap: 10, alignItems: 'center' }}>
                <div style={{ width: 26, height: 26, borderRadius: '50%', background: selected !== null && isCorrect ? '#4CC97B' : selected !== null && isSelected ? '#C94C4C' : 'rgba(0,0,0,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 800, color: selected !== null && (isCorrect || isSelected) ? '#fff' : N.navy, flexShrink: 0 }}>{String.fromCharCode(65+i)}</div>
                {opt}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}""",
    """function QuizScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const [qi, setQi] = useState(0)
  const [selected, setSelected] = useState<number|null>(null)
  const [score, setScore] = useState(0)
  const [done, setDone] = useState(false)

  const [questions, setQuestions] = useState<{ q: string; opts: string[]; ans: number }[]>([])
  const [materialId, setMaterialId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')
  const [completion, setCompletion] = useState<CompletionResponse | null>(null)

  // Normalizes ai_service.py's quiz payload defensively: tries a few
  // likely field names for the question text, options list, and
  // correct-answer index rather than assuming one exact shape.
  const normalizeQuiz = (raw: any): { q: string; opts: string[]; ans: number }[] => {
    const list = Array.isArray(raw) ? raw : Array.isArray(raw?.questions) ? raw.questions : []
    return list.map((item: any) => ({
      q: item.question || item.q || item.prompt || 'Question',
      opts: item.options || item.opts || item.choices || [],
      ans: typeof item.answer_index === 'number' ? item.answer_index
        : typeof item.correct_index === 'number' ? item.correct_index
        : typeof item.ans === 'number' ? item.ans : 0,
    }))
  }

  useEffect(() => {
    if (activeDocumentId == null) { setLoading(false); setError('No document selected.'); return }
    api<{ csrf_token: string }>('/me')
      .then(me => {
        setCsrfToken(me.csrf_token)
        return api<{ material_id: number; reused: boolean; quiz: any }>(`/documents/${activeDocumentId}/quiz`, {
          method: 'POST',
          headers: { 'X-CSRF-Token': me.csrf_token },
        })
      })
      .then(res => { setMaterialId(res.material_id); setQuestions(normalizeQuiz(res.quiz)) })
      .catch(e => {
        if (e instanceof ApiError && e.status === 429) setError("You've hit the hourly generation limit - try again later.")
        else if (e instanceof ApiError && e.status === 503) setError('AI budget exceeded for now - try again later.')
        else setError(e instanceof ApiError ? e.message : 'Could not generate a quiz. Please try again.')
      })
      .finally(() => setLoading(false))
  }, [activeDocumentId])

  const finish = async (finalScore: number) => {
    setDone(true)
    if (activeDocumentId == null || materialId == null) return
    try {
      const scorePercent = Math.round((finalScore / questions.length) * 100)
      const res = await api<CompletionResponse>(`/documents/${activeDocumentId}/quiz/${materialId}/complete`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ score_percent: scorePercent }),
      })
      setCompletion(res)
    } catch {
      // Non-fatal - the quiz itself already completed for the student.
    }
  }

  const q = questions[qi]
  const choose = (i: number) => {
    if (selected !== null || !q) return
    setSelected(i)
    const newScore = i === q.ans ? score + 1 : score
    if (i === q.ans) setScore(newScore)
    setTimeout(() => {
      if (qi + 1 >= questions.length) finish(newScore)
      else { setQi(qi + 1); setSelected(null) }
    }, 1100)
  }

  if (loading) return <GenerationLoading label="Generating your quiz…" />
  if (error) return <GenerationError error={error} />
  if (questions.length === 0) return <GenerationError error="No quiz questions were returned." />

  if (done) return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.bg, padding: 32 }}>
      <div style={{ fontSize: 56, marginBottom: 16 }}>🎉</div>
      <div style={{ fontWeight: 800, fontSize: 24, color: N.navy, marginBottom: 6 }}>Quiz Complete!</div>
      <div style={{ fontSize: 15, color: '#6B7280', marginBottom: 16 }}>You scored {score}/{questions.length}</div>
      {completion && completion.xp_awarded > 0 && (
        <div style={{ fontSize: 13, color: N.gold, fontWeight: 700, marginBottom: 8 }}>+{completion.xp_awarded} XP</div>
      )}
      {completion && <AchievementToast codes={completion.newly_unlocked_achievements} />}
      <div style={{ width: 100, height: 100, borderRadius: '50%', background: score / questions.length >= 0.6 ? '#D1FAE5' : '#FEE2E2', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 32 }}>
        <div style={{ fontWeight: 800, fontSize: 26, color: score / questions.length >= 0.6 ? '#065F46' : '#C94C4C' }}>{Math.round((score/questions.length)*100)}%</div>
      </div>
      <div style={{ display: 'flex', gap: 10 }}>
        <button onClick={() => setScreen('document-study')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 13, border: 'none', borderRadius: 14, padding: '12px 20px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Back to Notes</button>
      </div>
    </div>
  )
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => setScreen('document-study')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>Practice Quiz</div>
          </div>
          <Pill text={`${score} correct`} color="#4CC97B" />
        </div>
        <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 99, height: 5, overflow: 'hidden' }}>
          <div style={{ width: `${((qi) / questions.length) * 100}%`, height: '100%', background: N.gold, borderRadius: 99, transition: 'width 0.3s' }} />
        </div>
        <div style={{ textAlign: 'right', marginTop: 4, fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>Q{qi+1} of {questions.length}</div>
      </div>
      <div style={{ flex: 1, padding: 20 }}>
        <div style={{ background: '#fff', borderRadius: 18, padding: 20, marginBottom: 20, boxShadow: '0 2px 12px rgba(0,0,0,0.07)' }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: N.gold, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 }}>Question {qi+1}</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: N.navy, lineHeight: 1.7 }}>{q.q}</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {q.opts.map((opt, i) => {
            const isSelected = selected === i
            const isCorrect = i === q.ans
            const bg = selected !== null
              ? isCorrect ? '#D1FAE5' : isSelected ? '#FEE2E2' : '#fff'
              : '#fff'
            const color = selected !== null
              ? isCorrect ? '#065F46' : isSelected ? '#C94C4C' : N.navy
              : N.navy
            return (
              <button key={i} onClick={() => choose(i)} style={{ background: bg, border: `2px solid ${selected !== null && isCorrect ? '#4CC97B' : selected !== null && isSelected ? '#C94C4C' : 'rgba(0,0,0,0.06)'}`, borderRadius: 14, padding: '14px 16px', cursor: selected !== null ? 'default' : 'pointer', textAlign: 'left', fontFamily: 'Plus Jakarta Sans', fontSize: 13, fontWeight: 600, color, transition: 'all 0.2s', display: 'flex', gap: 10, alignItems: 'center' }}>
                <div style={{ width: 26, height: 26, borderRadius: '50%', background: selected !== null && isCorrect ? '#4CC97B' : selected !== null && isSelected ? '#C94C4C' : 'rgba(0,0,0,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 800, color: selected !== null && (isCorrect || isSelected) ? '#fff' : N.navy, flexShrink: 0 }}>{String.fromCharCode(65+i)}</div>
                {opt}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}""",
)

# ─────────────────────────────────────────────────────────────────────────
# 7. FlashcardsScreen: real POST /documents/:id/flashcards + completion
# ─────────────────────────────────────────────────────────────────────────

apply(
    "FlashcardsScreen full rewrite",
    """function FlashcardsScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [idx, setIdx] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [known, setKnown] = useState<number[]>([])
  const loading = useLoading(500)
  if (loading) return <SkeletonFlashcards />
  const card = flashcardData[idx]
  const next = (k: boolean) => {
    if (k) setKnown(n => [...n, idx])
    setFlipped(false)
    setTimeout(() => setIdx(i => (i + 1) % flashcardData.length), 150)
  }
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => setScreen('document-study')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>Flashcards</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>ACT 101 – Interest Theory · 35 cards</div>
          </div>
          <Pill text={`${known.length}/${flashcardData.length} Known`} color="#4CC97B" />
        </div>
        <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 99, height: 5, overflow: 'hidden' }}>
          <div style={{ width: `${((idx + 1) / flashcardData.length) * 100}%`, height: '100%', background: N.gold, borderRadius: 99, transition: 'width 0.3s' }} />
        </div>
        <div style={{ textAlign: 'right', marginTop: 4, fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>{idx + 1} / {flashcardData.length}</div>
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '24px 20px', gap: 24 }}>
        <div onClick={() => setFlipped(v => !v)} style={{ width: '100%', minHeight: 220, background: '#fff', borderRadius: 24, padding: 28, boxShadow: '0 8px 32px rgba(0,0,0,0.1)', cursor: 'pointer', display: 'flex', flexDirection: 'column', justifyContent: 'center', border: `2px solid ${flipped ? N.gold + '44' : 'transparent'}`, transition: 'border-color 0.2s' }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: flipped ? N.gold : '#9CA3AF', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 14 }}>{flipped ? 'Answer' : 'Question — tap to reveal'}</div>
          <div style={{ fontSize: 14, color: N.navy, fontWeight: flipped ? 600 : 700, lineHeight: 1.7, whiteSpace: 'pre-line' }}>{flipped ? card.a : card.q}</div>
        </div>
        {flipped && (
          <div style={{ display: 'flex', gap: 14, width: '100%' }}>
            <button onClick={() => next(false)} style={{ flex: 1, background: '#FEE2E2', color: '#C94C4C', fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>✗ Still Learning</button>
            <button onClick={() => next(true)} style={{ flex: 1, background: '#D1FAE5', color: '#065F46', fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>✓ Got It</button>
          </div>
        )}
        {!flipped && (
          <div style={{ color: '#9CA3AF', fontSize: 12, textAlign: 'center' }}>Tap the card to see the answer</div>
        )}
      </div>
    </div>
  )
}""",
    """function FlashcardsScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const [idx, setIdx] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [known, setKnown] = useState<number[]>([])

  const [cards, setCards] = useState<{ q: string; a: string }[]>([])
  const [materialId, setMaterialId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')
  const [finished, setFinished] = useState(false)
  const [completion, setCompletion] = useState<CompletionResponse | null>(null)

  // Normalizes ai_service.py's flashcards payload defensively - tries a
  // few likely field names for the front/back of each card.
  const normalizeCards = (raw: any): { q: string; a: string }[] => {
    const list = Array.isArray(raw) ? raw : Array.isArray(raw?.cards) ? raw.cards : Array.isArray(raw?.flashcards) ? raw.flashcards : []
    return list.map((item: any) => ({
      q: item.q || item.question || item.front || 'Question',
      a: item.a || item.answer || item.back || 'Answer',
    }))
  }

  useEffect(() => {
    if (activeDocumentId == null) { setLoading(false); setError('No document selected.'); return }
    api<{ csrf_token: string }>('/me')
      .then(me => {
        setCsrfToken(me.csrf_token)
        return api<{ material_id: number; reused: boolean; flashcards: any }>(`/documents/${activeDocumentId}/flashcards`, {
          method: 'POST',
          headers: { 'X-CSRF-Token': me.csrf_token },
        })
      })
      .then(res => { setMaterialId(res.material_id); setCards(normalizeCards(res.flashcards)) })
      .catch(e => {
        if (e instanceof ApiError && e.status === 429) setError("You've hit the hourly generation limit - try again later.")
        else if (e instanceof ApiError && e.status === 503) setError('AI budget exceeded for now - try again later.')
        else setError(e instanceof ApiError ? e.message : 'Could not generate flashcards. Please try again.')
      })
      .finally(() => setLoading(false))
  }, [activeDocumentId])

  const complete = async (reviewedCount: number) => {
    setFinished(true)
    if (activeDocumentId == null || materialId == null) return
    try {
      const res = await api<CompletionResponse>(`/documents/${activeDocumentId}/flashcards/${materialId}/complete`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ cards_reviewed: reviewedCount }),
      })
      setCompletion(res)
    } catch {
      // Non-fatal - the review session itself already completed.
    }
  }

  const card = cards[idx]
  const next = (k: boolean) => {
    const newKnown = k ? [...known, idx] : known
    if (k) setKnown(newKnown)
    setFlipped(false)
    setTimeout(() => {
      if (idx + 1 >= cards.length) complete(idx + 1)
      else setIdx(i => i + 1)
    }, 150)
  }

  if (loading) return <GenerationLoading label="Generating your flashcards…" />
  if (error) return <GenerationError error={error} />
  if (cards.length === 0) return <GenerationError error="No flashcards were returned." />

  if (finished) return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.bg, padding: 32 }}>
      <div style={{ fontSize: 56, marginBottom: 16 }}>🎉</div>
      <div style={{ fontWeight: 800, fontSize: 24, color: N.navy, marginBottom: 6 }}>Review Complete!</div>
      <div style={{ fontSize: 15, color: '#6B7280', marginBottom: 16 }}>{known.length}/{cards.length} marked as known</div>
      {completion && completion.xp_awarded > 0 && (
        <div style={{ fontSize: 13, color: N.gold, fontWeight: 700, marginBottom: 8 }}>+{completion.xp_awarded} XP</div>
      )}
      {completion && <AchievementToast codes={completion.newly_unlocked_achievements} />}
      <button onClick={() => setScreen('document-study')} style={{ marginTop: 16, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 13, border: 'none', borderRadius: 14, padding: '12px 20px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Back to Notes</button>
    </div>
  )

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => setScreen('document-study')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>Flashcards</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>{cards.length} cards</div>
          </div>
          <Pill text={`${known.length}/${cards.length} Known`} color="#4CC97B" />
        </div>
        <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 99, height: 5, overflow: 'hidden' }}>
          <div style={{ width: `${((idx + 1) / cards.length) * 100}%`, height: '100%', background: N.gold, borderRadius: 99, transition: 'width 0.3s' }} />
        </div>
        <div style={{ textAlign: 'right', marginTop: 4, fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>{idx + 1} / {cards.length}</div>
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '24px 20px', gap: 24 }}>
        <div onClick={() => setFlipped(v => !v)} style={{ width: '100%', minHeight: 220, background: '#fff', borderRadius: 24, padding: 28, boxShadow: '0 8px 32px rgba(0,0,0,0.1)', cursor: 'pointer', display: 'flex', flexDirection: 'column', justifyContent: 'center', border: `2px solid ${flipped ? N.gold + '44' : 'transparent'}`, transition: 'border-color 0.2s' }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: flipped ? N.gold : '#9CA3AF', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 14 }}>{flipped ? 'Answer' : 'Question — tap to reveal'}</div>
          <div style={{ fontSize: 14, color: N.navy, fontWeight: flipped ? 600 : 700, lineHeight: 1.7, whiteSpace: 'pre-line' }}>{flipped ? card.a : card.q}</div>
        </div>
        {flipped && (
          <div style={{ display: 'flex', gap: 14, width: '100%' }}>
            <button onClick={() => next(false)} style={{ flex: 1, background: '#FEE2E2', color: '#C94C4C', fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>✗ Still Learning</button>
            <button onClick={() => next(true)} style={{ flex: 1, background: '#D1FAE5', color: '#065F46', fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>✓ Got It</button>
          </div>
        )}
        {!flipped && (
          <div style={{ color: '#9CA3AF', fontSize: 12, textAlign: 'center' }}>Tap the card to see the answer</div>
        )}
      </div>
    </div>
  )
}""",
)

# ─────────────────────────────────────────────────────────────────────────
# 8. MindMapScreen: real POST /documents/:id/mindmap, defensive render
# ─────────────────────────────────────────────────────────────────────────

apply(
    "MindMapScreen full rewrite",
    """function MindMapScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const loading = useLoading(900)
  if (loading) return <SkeletonMindMap />
  const nodes = [
    { id: 'center', label: 'Interest Theory', x: 150, y: 150, r: 44, color: N.gold, textColor: N.navy, fontSize: 11 },
    { id: 'compound', label: 'Compound\\nInterest', x: 60, y: 60, r: 36, color: N.navy2, textColor: N.gold, fontSize: 10 },
    { id: 'simple', label: 'Simple\\nInterest', x: 240, y: 60, r: 36, color: N.navy2, textColor: N.gold, fontSize: 10 },
    { id: 'annuity', label: 'Annuities', x: 60, y: 240, r: 36, color: N.navy3, textColor: '#fff', fontSize: 10 },
    { id: 'pv', label: 'Present\\nValue', x: 240, y: 240, r: 36, color: N.navy3, textColor: '#fff', fontSize: 10 },
    { id: 'force', label: 'Force of\\nInterest', x: 280, y: 150, r: 30, color: '#4C7BC9', textColor: '#fff', fontSize: 9 },
    { id: 'perpetuity', label: 'Perpetuity', x: 20, y: 150, r: 30, color: '#4CC97B', textColor: N.navy, fontSize: 9 },
  ]
  const lines = [['center','compound'],['center','simple'],['center','annuity'],['center','pv'],['center','force'],['center','perpetuity']]
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('document-study')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>Mind Map</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>ACT 101 – Interest Theory</div>
          </div>
        </div>
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
        <div style={{ background: '#fff', borderRadius: 20, padding: 16, boxShadow: '0 4px 20px rgba(0,0,0,0.08)', width: '100%', marginBottom: 16 }}>
          <svg viewBox="-10 -10 320 320" style={{ width: '100%', height: 300 }}>
            {lines.map(([from, to]) => {
              const f = nodes.find(n => n.id === from)!
              const t = nodes.find(n => n.id === to)!
              return <line key={from+to} x1={f.x} y1={f.y} x2={t.x} y2={t.y} stroke="rgba(11,20,55,0.15)" strokeWidth="2" />
            })}
            {nodes.map(node => (
              <g key={node.id} style={{ cursor: 'pointer' }}>
                <circle cx={node.x} cy={node.y} r={node.r} fill={node.color} />
                {node.label.split('\\n').map((line, i, arr) => (
                  <text key={i} x={node.x} y={node.y + (i - (arr.length - 1) / 2) * (node.fontSize + 2)} textAnchor="middle" dominantBaseline="middle" fontSize={node.fontSize} fontWeight="700" fill={node.textColor} fontFamily="Plus Jakarta Sans">{line}</text>
                ))}
              </g>
            ))}
          </svg>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%' }}>
          {nodes.slice(1).map(node => (
            <div key={node.id} style={{ display: 'flex', gap: 10, alignItems: 'center', background: '#fff', borderRadius: 12, padding: '10px 14px', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: node.color, flexShrink: 0 }} />
              <div style={{ fontWeight: 600, fontSize: 13, color: N.navy }}>{node.label.replace('\\n',' ')}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}""",
    """type MindMapNode = { id: string; label: string; x: number; y: number; r: number; color: string; textColor: string; fontSize: number }

function MindMapScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const [raw, setRaw] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) { setLoading(false); setError('No document selected.'); return }
    api<{ csrf_token: string }>('/me')
      .then(me => api<{ material_id: number; reused: boolean; mindmap: any }>(`/documents/${activeDocumentId}/mindmap`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': me.csrf_token },
      }))
      .then(res => setRaw(res.mindmap))
      .catch(e => {
        if (e instanceof ApiError && e.status === 429) setError("You've hit the hourly generation limit - try again later.")
        else if (e instanceof ApiError && e.status === 503) setError('AI budget exceeded for now - try again later.')
        else setError(e instanceof ApiError ? e.message : 'Could not generate a mind map. Please try again.')
      })
      .finally(() => setLoading(false))
  }, [activeDocumentId])

  // Builds a simple radial layout from whatever ai_service.py returned:
  // tries {center, branches:[...]} or {nodes:[...], edges:[...]} shapes.
  // Falls back to raw JSON if neither is recognizable.
  const palette = [N.navy2, N.navy3, '#4C7BC9', '#4CC97B', '#9B59B6', '#C94C4C']
  const buildLayout = (): { nodes: MindMapNode[]; lines: [string, string][] } | null => {
    if (!raw) return null
    const centerLabel: string = raw.center || raw.root || raw.title || 'Overview'
    const branches: string[] = Array.isArray(raw.branches) ? raw.branches
      : Array.isArray(raw.nodes) ? raw.nodes.map((n: any) => n.label || n.name || String(n))
      : []
    if (branches.length === 0) return null

    const nodes: MindMapNode[] = [{ id: 'center', label: centerLabel, x: 150, y: 150, r: 44, color: N.gold, textColor: N.navy, fontSize: 11 }]
    const lines: [string, string][] = []
    const angleStep = (2 * Math.PI) / branches.length
    const radius = 110
    branches.forEach((label, i) => {
      const id = `n${i}`
      const angle = i * angleStep
      nodes.push({
        id, label: String(label),
        x: 150 + radius * Math.cos(angle), y: 150 + radius * Math.sin(angle),
        r: 34, color: palette[i % palette.length], textColor: '#fff', fontSize: 10,
      })
      lines.push(['center', id])
    })
    return { nodes, lines }
  }

  const layout = buildLayout()

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('document-study')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>Mind Map</div>
          </div>
        </div>
      </div>
      {loading ? <GenerationLoading label="Generating your mind map…" /> : error ? <GenerationError error={error} /> : !layout ? (
        <div style={{ flex: 1, overflowY: 'auto', padding: 20 }} className="scrollbar-hide">
          <pre style={{ fontSize: 11, color: '#374151', whiteSpace: 'pre-wrap', background: '#fff', borderRadius: 12, padding: 14, boxShadow: '0 2px 10px rgba(0,0,0,0.06)' }}>{JSON.stringify(raw, null, 2)}</pre>
        </div>
      ) : (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
          <div style={{ background: '#fff', borderRadius: 20, padding: 16, boxShadow: '0 4px 20px rgba(0,0,0,0.08)', width: '100%', marginBottom: 16 }}>
            <svg viewBox="-10 -10 320 320" style={{ width: '100%', height: 300 }}>
              {layout.lines.map(([from, to]) => {
                const f = layout.nodes.find(n => n.id === from)!
                const t = layout.nodes.find(n => n.id === to)!
                return <line key={from+to} x1={f.x} y1={f.y} x2={t.x} y2={t.y} stroke="rgba(11,20,55,0.15)" strokeWidth="2" />
              })}
              {layout.nodes.map(node => (
                <g key={node.id} style={{ cursor: 'pointer' }}>
                  <circle cx={node.x} cy={node.y} r={node.r} fill={node.color} />
                  {node.label.split('\\n').map((line, i, arr) => (
                    <text key={i} x={node.x} y={node.y + (i - (arr.length - 1) / 2) * (node.fontSize + 2)} textAnchor="middle" dominantBaseline="middle" fontSize={node.fontSize} fontWeight="700" fill={node.textColor} fontFamily="Plus Jakarta Sans">{line}</text>
                  ))}
                </g>
              ))}
            </svg>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%' }}>
            {layout.nodes.slice(1).map(node => (
              <div key={node.id} style={{ display: 'flex', gap: 10, alignItems: 'center', background: '#fff', borderRadius: 12, padding: '10px 14px', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
                <div style={{ width: 10, height: 10, borderRadius: '50%', background: node.color, flexShrink: 0 }} />
                <div style={{ fontWeight: 600, fontSize: 13, color: N.navy }}>{node.label.replace('\\n',' ')}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}""",
)

# ─────────────────────────────────────────────────────────────────────────
# 9. PodcastPlayerScreen: real script + audio generation, real <audio>
# ─────────────────────────────────────────────────────────────────────────

apply(
    "PodcastPlayerScreen full rewrite",
    """function PodcastPlayerScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0.28)
  const loading = useLoading(800)
  if (loading) return <SkeletonPodcast />
  const pod = podcasts[0]
  const total = 9 * 60
  const current = Math.floor(progress * total)
  const fmt = (s: number) => `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <TopBar title="Study Podcast" onBack={() => setScreen('podcast-library')} />
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '32px 28px', gap: 28 }}>
        {/* Album art */}
        <div style={{ width: 200, height: 200, borderRadius: 28, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: `0 16px 48px rgba(201,168,76,0.35)`, fontSize: 80, fontWeight: 800, color: N.navy, fontFamily: 'Plus Jakarta Sans' }}>∑</div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontWeight: 800, fontSize: 20, color: N.navy, marginBottom: 4 }}>{pod.title}</div>
          <div style={{ fontSize: 13, color: '#6B7280' }}>ACT 101 · Kenyatta University · {pod.duration}</div>
          <Pill text="AI Generated" color={N.gold} />
        </div>
        {/* Progress */}
        <div style={{ width: '100%' }}>
          <input type="range" min={0} max={1} step={0.01} value={progress} onChange={e => setProgress(+e.target.value)} style={{ width: '100%', accentColor: N.gold, cursor: 'pointer' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#9CA3AF', marginTop: 4 }}>
            <span>{fmt(current)}</span><span>{fmt(total)}</span>
          </div>
        </div>
        {/* Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 28 }}>
          <button onClick={() => setProgress(p => Math.max(0, p - 0.15))} style={{ background: 'none', border: 'none', cursor: 'pointer', color: N.navy }}>{Ic.rewind()}</button>
          <button onClick={() => setPlaying(v => !v)} style={{ width: 64, height: 64, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: '50%', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: `0 6px 20px rgba(201,168,76,0.4)` }}>
            <div style={{ color: N.navy }}>{playing ? Ic.pause() : Ic.play()}</div>
          </button>
          <button onClick={() => setProgress(p => Math.min(1, p + 0.15))} style={{ background: 'none', border: 'none', cursor: 'pointer', color: N.navy }}>{Ic.skip()}</button>
        </div>
        {/* More episodes */}
        <div style={{ width: '100%' }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 12 }}>More Episodes</div>
          {podcasts.slice(1).map((p, i) => (
            <div key={i} onClick={() => setScreen('podcast-player')} style={{ display: 'flex', gap: 12, alignItems: 'center', background: '#fff', borderRadius: 14, padding: 12, marginBottom: 8, boxShadow: '0 2px 6px rgba(0,0,0,0.05)', cursor: 'pointer' }}>
              <div style={{ width: 42, height: 42, background: `linear-gradient(135deg,${p.color},${p.color}99)`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, color: '#fff', fontWeight: 800 }}>{p.icon}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700, fontSize: 12, color: N.navy }}>{p.title}</div>
                <div style={{ fontSize: 11, color: '#6B7280' }}>{p.subject} · {p.duration}</div>
              </div>
              <div style={{ color: N.gold }}>{Ic.play('w-4 h-4')}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}""",
    """function PodcastPlayerScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState(0)

  const [stage, setStage] = useState<'script' | 'audio' | 'ready'>('script')
  const [title, setTitle] = useState('Study Podcast')
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) { setError('No document selected.'); return }
    let cancelled = false

    const run = async () => {
      try {
        const me = await api<{ csrf_token: string }>('/me')
        if (cancelled) return
        setCsrfToken(me.csrf_token)

        const scriptRes = await api<{ material_id: number; reused: boolean; podcast: any }>(`/documents/${activeDocumentId}/podcast-script`, {
          method: 'POST',
          headers: { 'X-CSRF-Token': me.csrf_token },
        })
        if (cancelled) return
        if (scriptRes.podcast?.title) setTitle(scriptRes.podcast.title)

        setStage('audio')
        const audioKickoff = await api<{ audio_status: string; material_id: number }>(`/documents/${activeDocumentId}/podcast-audio`, {
          method: 'POST',
          headers: { 'X-CSRF-Token': me.csrf_token },
        })
        if (cancelled) return

        if (audioKickoff.audio_status === 'ready') {
          await pollAudio()
          return
        }

        const poll = async () => {
          if (cancelled) return
          const status = await api<{ audio_status: string; audio_url: string | null; duration_seconds: number | null }>(`/documents/${activeDocumentId}/podcast-audio`)
          if (cancelled) return
          if (status.audio_status === 'ready' && status.audio_url) {
            setAudioUrl(status.audio_url)
            setDuration(status.duration_seconds || 0)
            setStage('ready')
          } else {
            setTimeout(poll, 3000)
          }
        }
        await poll()
      } catch (e) {
        if (cancelled) return
        if (e instanceof ApiError && e.status === 429) setError("You've hit the hourly generation limit - try again later.")
        else if (e instanceof ApiError && e.status === 503) setError('AI budget exceeded for now - try again later.')
        else setError(e instanceof ApiError ? e.message : 'Could not generate this podcast. Please try again.')
      }
    }

    const pollAudio = async () => {
      const status = await api<{ audio_status: string; audio_url: string | null; duration_seconds: number | null }>(`/documents/${activeDocumentId}/podcast-audio`)
      if (status.audio_status === 'ready' && status.audio_url) {
        setAudioUrl(status.audio_url)
        setDuration(status.duration_seconds || 0)
        setStage('ready')
      }
    }

    run()
    return () => { cancelled = true }
  }, [activeDocumentId])

  const togglePlay = () => {
    const el = audioRef.current
    if (!el) return
    if (playing) { el.pause() } else { el.play() }
    setPlaying(!playing)
  }

  const seek = (delta: number) => {
    const el = audioRef.current
    if (!el) return
    el.currentTime = Math.max(0, Math.min(el.duration || duration, el.currentTime + delta))
  }

  const fmt = (s: number) => `${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <TopBar title="Study Podcast" onBack={() => setScreen('document-study')} />
      </div>
      {error ? <GenerationError error={error} /> : stage !== 'ready' ? (
        <GenerationLoading label={stage === 'script' ? 'Writing your podcast script…' : 'Generating audio — this can take a minute…'} />
      ) : (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '32px 28px', gap: 28 }}>
          {audioUrl && (
            <audio
              ref={audioRef}
              src={audioUrl}
              onTimeUpdate={e => setProgress(e.currentTarget.currentTime)}
              onLoadedMetadata={e => setDuration(e.currentTarget.duration)}
              onEnded={() => setPlaying(false)}
            />
          )}
          {/* Album art */}
          <div style={{ width: 200, height: 200, borderRadius: 28, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: `0 16px 48px rgba(201,168,76,0.35)`, fontSize: 80, fontWeight: 800, color: N.navy, fontFamily: 'Plus Jakarta Sans' }}>🎙️</div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontWeight: 800, fontSize: 20, color: N.navy, marginBottom: 4 }}>{title}</div>
            <Pill text="AI Generated" color={N.gold} />
          </div>
          {/* Progress */}
          <div style={{ width: '100%' }}>
            <input type="range" min={0} max={duration || 1} step={0.5} value={progress} onChange={e => { const v = +e.target.value; setProgress(v); if (audioRef.current) audioRef.current.currentTime = v }} style={{ width: '100%', accentColor: N.gold, cursor: 'pointer' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#9CA3AF', marginTop: 4 }}>
              <span>{fmt(progress)}</span><span>{fmt(duration)}</span>
            </div>
          </div>
          {/* Controls */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 28 }}>
            <button onClick={() => seek(-15)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: N.navy }}>{Ic.rewind()}</button>
            <button onClick={togglePlay} style={{ width: 64, height: 64, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: '50%', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: `0 6px 20px rgba(201,168,76,0.4)` }}>
              <div style={{ color: N.navy }}>{playing ? Ic.pause() : Ic.play()}</div>
            </button>
            <button onClick={() => seek(15)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: N.navy }}>{Ic.skip()}</button>
          </div>
        </div>
      )}
    </div>
  )
}""",
)

assert src != original_src, "No changes were made - something is wrong."

with io.open(PATH, "w", encoding="utf-8", newline="") as f:
    f.write(src)

print("\nAll Chunk 4 patches applied successfully.")
print("\nNext steps:")
print("  cd ~/Desktop/prepza")
print("  git diff frontend/src/App.tsx")
print("  cd frontend && npx tsc --noEmit")
print("\nIMPORTANT: quiz/flashcards/mindmap rendering makes reasonable")
print("guesses about ai_service.py's exact field names (question/options/")
print("answer_index etc). Generate one of each for real and tell me the")
print("actual field names if the UI shows blanks or the JSON fallback -")
print("it's a one-line fix in normalizeQuiz/normalizeCards/buildLayout.")
