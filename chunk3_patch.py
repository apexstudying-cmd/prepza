"""
Chunk 3 patch: wires UploadScreen, ProcessingScreen, DocReadyScreen in
frontend/src/App.tsx to the real backend document-upload flow:
  POST /documents -> PUT file bytes to Supabase (direct, no CSRF) ->
  POST /documents/:id/uploaded -> poll GET /documents/:id -> doc-ready.

Since the existing `Screen` union has no per-screen params, this patch
adds one small piece of shared state to the top-level App() component
(activeDocumentId) and threads it down as props - same lightweight
pattern as everything else in this file (no new global store, no
Context).

Every replacement is assert-guarded: if the expected original text
isn't found exactly once, the script stops and changes nothing.

Run from the project root:
    cd ~/Desktop/prepza
    python chunk3_patch.py

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


print("Applying Chunk 3 patches...")

# ─────────────────────────────────────────────────────────────────────────
# 1. Shared helpers: SHA-256 hashing + upload constants, after api()
# ─────────────────────────────────────────────────────────────────────────

apply(
    "Add upload helpers after api() function",
    """async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const { headers: extraHeaders, ...restOptions } = options
  const res = await fetch(path, {
    credentials: 'include',
    ...restOptions,
    headers: { 'Content-Type': 'application/json', ...(extraHeaders || {}) },
  })
  let body: any = null
  try { body = await res.json() } catch { /* no JSON body */ }
  if (!res.ok) {
    throw new ApiError((body && body.error) || `Request failed (${res.status})`, res.status)
  }
  return body as T
}""",
    """async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const { headers: extraHeaders, ...restOptions } = options
  const res = await fetch(path, {
    credentials: 'include',
    ...restOptions,
    headers: { 'Content-Type': 'application/json', ...(extraHeaders || {}) },
  })
  let body: any = null
  try { body = await res.json() } catch { /* no JSON body */ }
  if (!res.ok) {
    throw new ApiError((body && body.error) || `Request failed (${res.status})`, res.status)
  }
  return body as T
}

// ─── Document upload helpers ───────────────────────────────────────────────
const ALLOWED_UPLOAD_EXTENSIONS = ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'jpg', 'jpeg', 'png']
const MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024 // 50 MB - matches backend MAX_DOCUMENT_SIZE_BYTES

function getFileExtension(filename: string): string | null {
  const parts = filename.split('.')
  if (parts.length < 2) return null
  return parts[parts.length - 1].toLowerCase()
}

async function sha256Hex(file: File): Promise<string> {
  const buffer = await file.arrayBuffer()
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer)
  return Array.from(new Uint8Array(hashBuffer)).map(b => b.toString(16).padStart(2, '0')).join('')
}

type DocumentDetail = {
  id: number; title: string; original_filename: string; status: string
  file_type: string | null; file_size_bytes: number | null; page_count: number | null
  error_message: string | null; view_url: string | null
  materials: { type: string; status: string }[]; created_at: string | null
}""",
)

# ─────────────────────────────────────────────────────────────────────────
# 2. App(): add shared activeDocumentId state + thread through props
# ─────────────────────────────────────────────────────────────────────────

apply(
    "App() add activeDocumentId state",
    """export default function App() {
  const [screen, setScreen] = useState<Screen>('splash')
  const [adminMode, setAdminMode] = useState(false)
  const [oauthError, setOauthError] = useState('')
  const [isAdmin, setIsAdmin] = useState(false)""",
    """export default function App() {
  const [screen, setScreen] = useState<Screen>('splash')
  const [adminMode, setAdminMode] = useState(false)
  const [oauthError, setOauthError] = useState('')
  const [isAdmin, setIsAdmin] = useState(false)
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null)""",
)

apply(
    "App() thread props into upload/processing/doc-ready cases",
    """      case 'upload':            return <UploadScreen setScreen={setScreen} />
      case 'processing':        return <ProcessingScreen setScreen={setScreen} />
      case 'doc-ready':         return <DocReadyScreen setScreen={setScreen} />""",
    """      case 'upload':            return <UploadScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} />
      case 'processing':        return <ProcessingScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'doc-ready':         return <DocReadyScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />""",
)

# ─────────────────────────────────────────────────────────────────────────
# 3. UploadScreen: real hash -> POST /documents -> PUT -> confirm
# ─────────────────────────────────────────────────────────────────────────

apply(
    "UploadScreen full rewrite",
    """function UploadScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <TopBar title="Upload Document" onBack={() => setScreen('home')} />
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', marginTop: -8 }}>Prepza AI processes your document instantly</div>
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 18 }}>
        <div onDragOver={e => { e.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); setScreen('processing') }} onClick={() => fileRef.current?.click()} style={{ border: `2px dashed ${dragging ? N.gold : 'rgba(11,20,55,0.18)'}`, borderRadius: 20, padding: '40px 20px', textAlign: 'center', background: dragging ? 'rgba(201,168,76,0.04)' : '#fff', cursor: 'pointer', transition: 'all 0.2s' }}>
          <input ref={fileRef} type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.jpg,.png" style={{ display: 'none' }} onChange={() => setScreen('processing')} />
          <div style={{ fontSize: 48, marginBottom: 12 }}>📤</div>
          <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 6 }}>Drop your file here</div>
          <div style={{ fontSize: 13, color: '#6B7280', marginBottom: 16 }}>or tap to browse from your device</div>
          <div style={{ display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap' }}>
            {['PDF','Word','PowerPoint','JPG','PNG','EPUB'].map(t => <span key={t} style={{ background: '#F3F4F6', color: '#374151', fontSize: 10, fontWeight: 600, padding: '4px 10px', borderRadius: 20 }}>{t}</span>)}
          </div>
        </div>

        <div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>Or import from</div>
        {[
          { icon: '📷', label: 'Camera / Scan', sub: 'Photograph handwritten notes', color: N.gold },
          { icon: '☁️', label: 'Google Drive', sub: 'Import directly from Drive', color: '#4C7BC9' },
          { icon: '📱', label: 'Phone Storage', sub: 'Browse local files', color: '#4CC97B' },
        ].map((s, i) => (
          <button key={i} onClick={() => setScreen('processing')} style={{ display: 'flex', alignItems: 'center', gap: 12, background: '#fff', border: '1px solid rgba(0,0,0,0.05)', borderRadius: 16, padding: '14px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <div style={{ width: 42, height: 42, background: s.color + '18', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>{s.icon}</div>
            <div style={{ flex: 1, textAlign: 'left' }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>{s.label}</div>
              <div style={{ fontSize: 11, color: '#6B7280' }}>{s.sub}</div>
            </div>
            <div style={{ color: '#9CA3AF' }}>{Ic.chevR()}</div>
          </button>
        ))}

        <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginTop: 4 }}>Recent Uploads</div>
        {[
          { name: 'ACT_101_Lecture_Notes_Week1-6.pdf', size: '4.1 MB', date: 'Today' },
          { name: 'MAT_101_Calculus_PastPapers.pdf', size: '2.3 MB', date: 'Yesterday' },
        ].map((f, i) => (
          <div key={i} onClick={() => setScreen('document-study')} style={{ display: 'flex', gap: 12, alignItems: 'center', background: '#fff', borderRadius: 14, padding: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)', cursor: 'pointer' }}>
            <div style={{ width: 38, height: 38, background: 'rgba(201,68,68,0.1)', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16 }}>📕</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 12, color: N.navy }} className="line-clamp-1">{f.name}</div>
              <div style={{ fontSize: 11, color: '#9CA3AF' }}>{f.size} · {f.date}</div>
            </div>
            <Pill text="✓ Ready" color="#4CC97B" />
          </div>
        ))}
      </div>
    </div>
  )
}""",
    """function UploadScreen({ setScreen, setActiveDocumentId }: { setScreen: (s: Screen) => void; setActiveDocumentId: (id: number | null) => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadStage, setUploadStage] = useState('')
  const [error, setError] = useState('')

  const startUpload = async (file: File) => {
    setError('')

    const ext = getFileExtension(file.name)
    if (!ext || !ALLOWED_UPLOAD_EXTENSIONS.includes(ext)) {
      setError(`Unsupported file type. Allowed: ${ALLOWED_UPLOAD_EXTENSIONS.join(', ').toUpperCase()}`)
      return
    }
    if (file.size > MAX_UPLOAD_SIZE_BYTES) {
      setError(`File exceeds the ${MAX_UPLOAD_SIZE_BYTES / (1024 * 1024)} MB limit`)
      return
    }

    setUploading(true)
    try {
      setUploadStage('Hashing file...')
      const contentHash = await sha256Hex(file)

      setUploadStage('Registering upload...')
      const me = await api<{ csrf_token: string }>('/me')
      const title = file.name.includes('.') ? file.name.slice(0, file.name.lastIndexOf('.')) : file.name

      const created = await api<{
        document_id: number; status: string; duplicate: boolean
        upload_url?: string; storage_path?: string
      }>('/documents', {
        method: 'POST',
        headers: { 'X-CSRF-Token': me.csrf_token },
        body: JSON.stringify({
          title,
          original_filename: file.name,
          file_size_bytes: file.size,
          content_hash: contentHash,
        }),
      })

      if (!created.duplicate && created.upload_url) {
        setUploadStage('Uploading file...')
        const putRes = await fetch(created.upload_url, { method: 'PUT', body: file })
        if (!putRes.ok) throw new Error('Upload to storage failed - please try again')

        setUploadStage('Confirming upload...')
        try {
          await api(`/documents/${created.document_id}/uploaded`, {
            method: 'POST',
            headers: { 'X-CSRF-Token': me.csrf_token },
          })
        } catch (e) {
          if (e instanceof ApiError && e.status === 409) {
            await new Promise(r => setTimeout(r, 1500))
            await api(`/documents/${created.document_id}/uploaded`, {
              method: 'POST',
              headers: { 'X-CSRF-Token': me.csrf_token },
            })
          } else {
            throw e
          }
        }
      }

      setActiveDocumentId(created.document_id)
      setScreen('processing')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'Upload failed - please check your connection and try again.')
    } finally {
      setUploading(false)
      setUploadStage('')
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) startUpload(file)
    e.target.value = ''
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <TopBar title="Upload Document" onBack={() => setScreen('home')} />
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', marginTop: -8 }}>Prepza AI processes your document instantly</div>
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 18 }}>
        {error && (
          <div style={{ background: 'rgba(201,68,68,0.08)', border: '1px solid rgba(201,68,68,0.25)', borderRadius: 12, padding: '12px 14px', color: '#C94C4C', fontSize: 12, fontWeight: 600 }}>{error}</div>
        )}
        <div
          onDragOver={e => { e.preventDefault(); if (!uploading) setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={e => { e.preventDefault(); setDragging(false); const file = e.dataTransfer.files?.[0]; if (file && !uploading) startUpload(file) }}
          onClick={() => !uploading && fileRef.current?.click()}
          style={{ border: `2px dashed ${dragging ? N.gold : 'rgba(11,20,55,0.18)'}`, borderRadius: 20, padding: '40px 20px', textAlign: 'center', background: dragging ? 'rgba(201,168,76,0.04)' : '#fff', cursor: uploading ? 'wait' : 'pointer', opacity: uploading ? 0.7 : 1, transition: 'all 0.2s' }}
        >
          <input ref={fileRef} type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png" style={{ display: 'none' }} onChange={handleFileChange} disabled={uploading} />
          <div style={{ fontSize: 48, marginBottom: 12 }}>{uploading ? '⏳' : '📤'}</div>
          <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 6 }}>{uploading ? (uploadStage || 'Uploading...') : 'Drop your file here'}</div>
          {!uploading && <div style={{ fontSize: 13, color: '#6B7280', marginBottom: 16 }}>or tap to browse from your device</div>}
          {!uploading && (
            <div style={{ display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap' }}>
              {['PDF','Word','PowerPoint','JPG','PNG'].map(t => <span key={t} style={{ background: '#F3F4F6', color: '#374151', fontSize: 10, fontWeight: 600, padding: '4px 10px', borderRadius: 20 }}>{t}</span>)}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}""",
)

# ─────────────────────────────────────────────────────────────────────────
# 4. ProcessingScreen: poll GET /documents/:id until ready/failed
# ─────────────────────────────────────────────────────────────────────────

apply(
    "ProcessingScreen full rewrite",
    """function ProcessingScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [step, setStep] = useState(0)
  useEffect(() => {
    let i = 0
    const t = setInterval(() => { i++; setStep(i); if (i >= 4) clearInterval(t) }, 900)
    return () => clearInterval(t)
  }, [])
  const steps = ['Uploading document…','Extracting content…','AI analysing structure…','Generating study materials…','Ready to study!']
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.navy, padding: 32 }}>
      <div style={{ position: 'relative', width: 120, height: 120, marginBottom: 36 }}>
        <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: '3px solid rgba(201,168,76,0.18)' }} />
        <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: '3px solid transparent', borderTopColor: N.gold, animation: 'spin-slow 1.1s linear infinite' }} />
        <div style={{ position: 'absolute', inset: 14, borderRadius: '50%', background: 'rgba(201,168,76,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <img src={logoImg} alt="Prepza" style={{ width: 52, height: 52, borderRadius: 14 }} />
        </div>
      </div>
      <div style={{ color: '#fff', fontWeight: 800, fontSize: 20, marginBottom: 6, textAlign: 'center' }}>Prepza AI is working…</div>
      <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 13, textAlign: 'center', marginBottom: 40 }}>ACT 101 Lecture Notes – Week 1-6.pdf</div>
      <div style={{ width: '100%', maxWidth: 280, display: 'flex', flexDirection: 'column', gap: 14 }}>
        {steps.map((s, i) => (
          <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <div style={{ width: 24, height: 24, borderRadius: '50%', background: i <= step ? N.gold : 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, transition: 'background 0.3s' }}>
              {i <= step ? <div style={{ color: N.navy }}>{Ic.check('w-3 h-3')}</div> : <div style={{ width: 6, height: 6, background: 'rgba(255,255,255,0.25)', borderRadius: '50%' }} />}
            </div>
            <span style={{ fontSize: 13, color: i <= step ? '#fff' : 'rgba(255,255,255,0.35)', fontWeight: i <= step ? 600 : 400, transition: 'color 0.3s' }}>{s}</span>
          </div>
        ))}
      </div>
      {step >= 4 && (
        <button onClick={() => setScreen('doc-ready')} style={{ marginTop: 44, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 44px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 4px 20px rgba(201,168,76,0.4)' }}>
          View Document →
        </button>
      )}
    </div>
  )
}""",
    """function ProcessingScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [pollError, setPollError] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>

    const poll = async () => {
      try {
        const result = await api<DocumentDetail>(`/documents/${activeDocumentId}`)
        if (cancelled) return
        setDoc(result)
        if (result.status === 'ready' || result.status === 'failed') return
        timer = setTimeout(poll, 2500)
      } catch (e) {
        if (cancelled) return
        setPollError(e instanceof ApiError ? e.message : 'Lost connection while checking status - retrying...')
        timer = setTimeout(poll, 2500)
      }
    }
    poll()

    return () => { cancelled = true; clearTimeout(timer) }
  }, [activeDocumentId])

  const status = doc?.status
  const stageLabel = status === 'uploading' ? 'Uploading document…'
    : status === 'processing' ? 'Extracting content & analysing…'
    : status === 'ready' ? 'Ready to study!'
    : status === 'failed' ? 'Something went wrong'
    : 'Getting started…'

  if (activeDocumentId == null) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.navy, padding: 32, textAlign: 'center' }}>
        <div style={{ color: '#fff', fontWeight: 800, fontSize: 18, marginBottom: 10 }}>No upload in progress</div>
        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginBottom: 28 }}>Head back to upload a document to see its processing status here.</div>
        <button onClick={() => setScreen('upload')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '12px 28px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Go to Upload</button>
      </div>
    )
  }

  if (status === 'failed') {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.navy, padding: 32, textAlign: 'center' }}>
        <div style={{ fontSize: 44, marginBottom: 16 }}>⚠️</div>
        <div style={{ color: '#fff', fontWeight: 800, fontSize: 18, marginBottom: 10 }}>Processing failed</div>
        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginBottom: 28, maxWidth: 280 }}>{doc?.error_message || 'This document could not be processed. Please try uploading again.'}</div>
        <button onClick={() => setScreen('upload')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '12px 28px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Try Again</button>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.navy, padding: 32 }}>
      <div style={{ position: 'relative', width: 120, height: 120, marginBottom: 36 }}>
        <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: '3px solid rgba(201,168,76,0.18)' }} />
        <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: '3px solid transparent', borderTopColor: N.gold, animation: 'spin-slow 1.1s linear infinite' }} />
        <div style={{ position: 'absolute', inset: 14, borderRadius: '50%', background: 'rgba(201,168,76,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <img src={logoImg} alt="Prepza" style={{ width: 52, height: 52, borderRadius: 14 }} />
        </div>
      </div>
      <div style={{ color: '#fff', fontWeight: 800, fontSize: 20, marginBottom: 6, textAlign: 'center' }}>{stageLabel}</div>
      <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 13, textAlign: 'center', marginBottom: 20 }}>{doc?.title || 'Your document'}</div>
      {pollError && <div style={{ color: '#E8A54C', fontSize: 12, marginBottom: 20, textAlign: 'center' }}>{pollError}</div>}
      {status === 'ready' && (
        <button onClick={() => setScreen('doc-ready')} style={{ marginTop: 12, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 44px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 4px 20px rgba(201,168,76,0.4)' }}>
          View Document →
        </button>
      )}
    </div>
  )
}""",
)

# ─────────────────────────────────────────────────────────────────────────
# 5. DocReadyScreen: real title/file_type/page_count, plain navigation
# ─────────────────────────────────────────────────────────────────────────

apply(
    "DocReadyScreen full rewrite",
    """function DocReadyScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const trigger = (label: string, dest: Screen, isAI = false) => {
    if (busyAction) return
    if (isAI) { setBusyAction(label); setTimeout(() => { setBusyAction(null); setScreen(dest) }, 1500) }
    else setScreen(dest)
  }
  const actions = [
    { icon: '🤖', label: 'Study with AI', sub: 'Ask questions about this doc', dest: 'document-study' as Screen, ai: false },
    { icon: '❓', label: 'Ask Questions', sub: 'AI answers from your notes', dest: 'ai-tutor' as Screen, ai: false },
    { icon: '📝', label: 'Summarize', sub: '2-page condensed notes', dest: 'summary' as Screen, ai: true },
    { icon: '🧠', label: 'Generate Quiz', sub: '15 MCQ questions', dest: 'quiz' as Screen, ai: true },
    { icon: '🃏', label: 'Flashcards', sub: '35 cards auto-generated', dest: 'flashcards' as Screen, ai: true },
    { icon: '🎙️', label: 'Create Podcast', sub: '9-min audio episode', dest: 'podcast-player' as Screen, ai: true },
    { icon: '📚', label: 'Save to Library', sub: 'Access offline anytime', dest: 'library' as Screen, ai: false },
  ]
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <TopBar title="Document Ready ✓" onBack={() => setScreen('home')} />
        <div style={{ background: 'rgba(76,201,123,0.12)', border: '1px solid rgba(76,201,123,0.3)', borderRadius: 14, padding: '12px 14px', display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ fontSize: 24 }}>✅</span>
          <div>
            <div style={{ color: '#4CC97B', fontWeight: 700, fontSize: 13 }}>Processing Complete!</div>
            <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11 }}>Your document is ready to study</div>
          </div>
        </div>
      </div>
      <div style={{ padding: 18 }}>
        {/* Doc info */}
        <div style={{ background: '#fff', borderRadius: 16, padding: 16, marginBottom: 20, boxShadow: '0 2px 10px rgba(0,0,0,0.06)', display: 'flex', gap: 14, alignItems: 'center' }}>
          <div style={{ width: 52, height: 52, background: 'rgba(201,68,68,0.1)', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26 }}>📕</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 14, color: N.navy }}>ACT 101 Lecture Notes – Week 1-6</div>
            <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>PDF · 38 pages · 4.1 MB</div>
            <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
              <Pill text="35 Flashcards" color="#4C7BC9" />
              <Pill text="15 Quiz Questions" color="#4CC97B" />
              <Pill text="9 min Podcast" color="#C94C4C" />
            </div>
          </div>
        </div>
        <div style={{ fontWeight: 800, fontSize: 15, color: N.navy, marginBottom: 12 }}>What would you like to do?</div>
        {actions.map((a, i) => {
          const isBusy = busyAction === a.label
          return (
            <button key={i} onClick={() => trigger(a.label, a.dest, a.ai)} disabled={!!busyAction} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 14, background: '#fff', border: `1px solid ${isBusy ? N.gold + '55' : 'rgba(0,0,0,0.05)'}`, borderRadius: 14, padding: '14px 16px', marginBottom: 8, cursor: busyAction ? 'wait' : 'pointer', textAlign: 'left', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 2px 6px rgba(0,0,0,0.04)', opacity: busyAction && !isBusy ? 0.55 : 1, transition: 'opacity 0.2s, border-color 0.2s' }}>
              <div style={{ width: 44, height: 44, background: isBusy ? `linear-gradient(135deg,${N.gold},${N.goldL})` : `linear-gradient(135deg,${N.navy2},${N.navy3})`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: isBusy ? 0 : 20, flexShrink: 0, transition: 'background 0.2s' }}>
                {isBusy
                  ? <div style={{ width: 18, height: 18, border: `2.5px solid ${N.navy}`, borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin-slow 0.65s linear infinite' }} />
                  : a.icon}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: isBusy ? N.gold : N.navy }}>{isBusy ? 'Generating…' : a.label}</div>
                <div style={{ fontSize: 11, color: '#6B7280' }}>{a.sub}</div>
              </div>
              {!isBusy && <div style={{ color: '#9CA3AF' }}>{Ic.chevR()}</div>}
            </button>
          )
        })}
      </div>
    </div>
  )
}""",
    """function DocReadyScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) return
    api<DocumentDetail>(`/documents/${activeDocumentId}`)
      .then(setDoc)
      .catch(e => setLoadError(e instanceof ApiError ? e.message : 'Could not load document details.'))
  }, [activeDocumentId])

  const actions: { icon: string; label: string; sub: string; dest: Screen }[] = [
    { icon: '🤖', label: 'Study with AI', sub: 'Ask questions about this doc', dest: 'document-study' },
    { icon: '❓', label: 'Ask Questions', sub: 'AI answers from your notes', dest: 'ai-tutor' },
    { icon: '📝', label: 'Summarize', sub: 'Condensed AI notes', dest: 'summary' },
    { icon: '🧠', label: 'Generate Quiz', sub: 'AI-generated practice quiz', dest: 'quiz' },
    { icon: '🃏', label: 'Flashcards', sub: 'AI-generated flashcard set', dest: 'flashcards' },
    { icon: '🎙️', label: 'Create Podcast', sub: 'AI-generated audio episode', dest: 'podcast-player' },
    { icon: '📚', label: 'Save to Library', sub: 'Access offline anytime', dest: 'library' },
  ]

  const fileTypeLabel = doc?.file_type ? doc.file_type.toUpperCase() : null
  const pageLabel = doc?.page_count != null ? `${doc.page_count} pages` : null
  const sizeLabel = doc?.file_size_bytes != null ? `${(doc.file_size_bytes / (1024 * 1024)).toFixed(1)} MB` : null
  const metaParts = [fileTypeLabel, pageLabel, sizeLabel].filter(Boolean)

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <TopBar title="Document Ready ✓" onBack={() => setScreen('home')} />
        <div style={{ background: 'rgba(76,201,123,0.12)', border: '1px solid rgba(76,201,123,0.3)', borderRadius: 14, padding: '12px 14px', display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ fontSize: 24 }}>✅</span>
          <div>
            <div style={{ color: '#4CC97B', fontWeight: 700, fontSize: 13 }}>Processing Complete!</div>
            <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11 }}>Your document is ready to study</div>
          </div>
        </div>
      </div>
      <div style={{ padding: 18 }}>
        {loadError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 14 }}>{loadError}</div>}
        {/* Doc info */}
        <div style={{ background: '#fff', borderRadius: 16, padding: 16, marginBottom: 20, boxShadow: '0 2px 10px rgba(0,0,0,0.06)', display: 'flex', gap: 14, alignItems: 'center' }}>
          <div style={{ width: 52, height: 52, background: 'rgba(201,68,68,0.1)', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26 }}>📕</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: 14, color: N.navy }} className="line-clamp-1">{doc?.title || 'Loading…'}</div>
            <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>{metaParts.length > 0 ? metaParts.join(' · ') : '—'}</div>
          </div>
        </div>
        <div style={{ fontWeight: 800, fontSize: 15, color: N.navy, marginBottom: 12 }}>What would you like to do?</div>
        {actions.map((a, i) => (
          <button key={i} onClick={() => setScreen(a.dest)} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 14, background: '#fff', border: '1px solid rgba(0,0,0,0.05)', borderRadius: 14, padding: '14px 16px', marginBottom: 8, cursor: 'pointer', textAlign: 'left', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
            <div style={{ width: 44, height: 44, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0 }}>{a.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>{a.label}</div>
              <div style={{ fontSize: 11, color: '#6B7280' }}>{a.sub}</div>
            </div>
            <div style={{ color: '#9CA3AF' }}>{Ic.chevR()}</div>
          </button>
        ))}
      </div>
    </div>
  )
}""",
)

assert src != original_src, "No changes were made - something is wrong."

with io.open(PATH, "w", encoding="utf-8", newline="") as f:
    f.write(src)

print("\nAll Chunk 3 patches applied successfully.")
print("\nNext steps:")
print("  cd ~/Desktop/prepza")
print("  git diff frontend/src/App.tsx")
print("  cd frontend && npx tsc --noEmit")
print("\nManual test: pick a real small PDF in Upload, watch it go through")
print("uploading -> processing -> ready, confirm doc-ready shows real title/")
print("file type/page count. Re-upload the exact same file to confirm the")
print("duplicate flag skips the PUT step.")
