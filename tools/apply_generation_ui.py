from pathlib import Path

path = Path('frontend/src/App.tsx')
text = path.read_text()
start = text.index('// ─── PODCAST PLAYER ───────────────────────────────────────────────────────────')
end = text.index('// ─── FLASHCARDS ───────────────────────────────────────────────────────────────', start)
replacement = r'''// ─── PODCAST PLAYER / GENERATION ───────────────────────────────────────────────
const PODCAST_OPTIONS = [
  { minutes: 5, label: 'Quick Revision', description: 'Key points and the essentials.', style: 'quick_revision' },
  { minutes: 10, label: 'Focused Revision', description: 'Core concepts with useful context.', style: 'focused_revision' },
  { minutes: 20, label: 'Deeper Explanation', description: 'More teaching, examples, and connections.', style: 'deep_explanation' },
  { minutes: 30, label: 'Deep Study', description: 'A proper guided study session.', style: 'deep_study' },
  { minutes: 40, label: 'Comprehensive Study', description: 'Broad coverage with deeper explanations.', style: 'comprehensive_study' },
  { minutes: 50, label: 'Deep Explanation + Exam Focus', description: 'The fullest Prepza study session, with exam-focused teaching and review.', style: 'deep_exam' },
] as const

type PodcastStatus = 'config' | 'script' | 'audio' | 'ready' | 'error'

function PodcastPlayerScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const { tokens: T } = useTheme()
  const audioRef = useRef<HTMLAudioElement>(null)
  const [status, setStatus] = useState<PodcastStatus>('config')
  const [minutes, setMinutes] = useState(20)
  const [style, setStyle] = useState('deep_explanation')
  const [csrfToken, setCsrfToken] = useState('')
  const [documentTitle, setDocumentTitle] = useState('Your document')
  const [pageCount, setPageCount] = useState<number | null>(null)
  const [materialId, setMaterialId] = useState<number | null>(null)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [duration, setDuration] = useState(0)
  const [progress, setProgress] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [error, setError] = useState('')
  const [polling, setPolling] = useState(false)

  const selected = PODCAST_OPTIONS.find(o => o.minutes === minutes) || PODCAST_OPTIONS[2]

  useEffect(() => {
    if (activeDocumentId == null) { setError('No document selected.'); return }
    let cancelled = false
    Promise.all([api<{ csrf_token: string }>('/me'), api<DocumentDetail>(`/documents/${activeDocumentId}`)])
      .then(([me, doc]) => { if (!cancelled) { setCsrfToken(me.csrf_token); setDocumentTitle(doc.title); setPageCount(doc.page_count) } })
      .catch(e => { if (!cancelled) setError(e instanceof ApiError ? e.message : 'Could not load this document.') })
    return () => { cancelled = true }
  }, [activeDocumentId])

  useEffect(() => {
    const found = PODCAST_OPTIONS.find(o => o.minutes === minutes)
    if (found) setStyle(found.style)
  }, [minutes])

  useEffect(() => {
    if (status !== 'audio' || activeDocumentId == null) return
    let cancelled = false
    setPolling(true)
    const poll = async () => {
      try {
        const res = await api<{ audio_status: string; audio_url: string | null; duration_seconds: number | null }>(`/documents/${activeDocumentId}/podcast-audio`)
        if (cancelled) return
        if (res.audio_status === 'ready' && res.audio_url) { setAudioUrl(res.audio_url); setDuration(res.duration_seconds || 0); setStatus('ready'); setPolling(false); return }
        if (res.audio_status === 'failed') { setError('Audio generation failed. Your script is still available; you can try generating the audio again.'); setStatus('error'); setPolling(false); return }
        window.setTimeout(poll, 2500)
      } catch (e) {
        if (!cancelled) { setError(e instanceof ApiError ? e.message : 'Could not check podcast progress.'); setStatus('error'); setPolling(false) }
      }
    }
    poll()
    return () => { cancelled = true }
  }, [status, activeDocumentId])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    const update = () => { setProgress(audio.currentTime); if (Number.isFinite(audio.duration)) setDuration(audio.duration) }
    const ended = () => setPlaying(false)
    audio.addEventListener('timeupdate', update); audio.addEventListener('loadedmetadata', update); audio.addEventListener('ended', ended)
    return () => { audio.removeEventListener('timeupdate', update); audio.removeEventListener('loadedmetadata', update); audio.removeEventListener('ended', ended) }
  }, [audioUrl])

  const generate = async () => {
    if (activeDocumentId == null || !csrfToken) return
    setError(''); setStatus('script')
    try {
      const script = await api<{ material_id: number }>(`/documents/${activeDocumentId}/podcast-script`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken }, body: JSON.stringify({ duration_minutes: minutes, style, language: 'en' }) })
      setMaterialId(script.material_id)
      setStatus('audio')
      await api(`/documents/${activeDocumentId}/podcast-audio`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Could not generate this podcast.'); setStatus('error') }
  }

  const retryAudio = async () => {
    if (activeDocumentId == null || !csrfToken || materialId == null) return
    setError(''); setStatus('audio')
    try { await api(`/documents/${activeDocumentId}/podcast-audio`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } }) }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Could not restart audio generation.'); setStatus('error') }
  }

  const togglePlay = async () => {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) { await audio.play(); setPlaying(true) } else { audio.pause(); setPlaying(false) }
  }

  const progressPct = duration > 0 ? Math.min(100, (progress / duration) * 100) : 0
  const formatTime = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`

  if (activeDocumentId == null) return <GenerationError error="No document selected." />

  if (status === 'script' || status === 'audio') {
    const scriptStage = status === 'script'
    return <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px', color: '#fff' }}><div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><button onClick={() => setStatus('config')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, color: '#fff', cursor: 'pointer' }}>{Ic.back()}</button><div><div style={{ fontWeight: 800, fontSize: 15 }}>Creating your podcast</div><div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>{minutes} minutes · {selected.label}</div></div></div></div>
      <div style={{ flex: 1, padding: 22, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}><div style={{ background: T.card, borderRadius: 22, padding: 22, boxShadow: '0 8px 30px rgba(0,0,0,0.07)' }}><div style={{ fontSize: 11, color: N.gold, fontWeight: 800, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>Prepza Podcast</div><div style={{ fontSize: 18, color: T.text, fontWeight: 800, lineHeight: 1.35 }}>{documentTitle}</div><div style={{ fontSize: 12, color: T.textMuted, margin: '6px 0 18px' }}>{minutes} minutes · {selected.label}</div>{[['Document ready', true], ['Creating podcast script', !scriptStage], ['Creating audio', status === 'audio' ? 'active' : false], ['Finalising', false]].map(([label, done]) => <div key={String(label)} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: `1px solid ${T.border}` }}><div style={{ width: 22, height: 22, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: done === true ? 'rgba(76,201,123,0.14)' : done === 'active' ? `rgba(201,168,76,0.16)` : T.pageBg, color: done === true ? '#4CC97B' : done === 'active' ? N.gold : T.textMuted, fontSize: 11, fontWeight: 900 }}>{done === true ? '✓' : done === 'active' ? '•' : ''}</div><div style={{ flex: 1, color: T.text, fontSize: 13, fontWeight: done === 'active' ? 800 : 600 }}>{label}</div>{done === 'active' && <div style={{ width: 16, height: 16, border: `2px solid ${N.gold}35`, borderTopColor: N.gold, borderRadius: '50%', animation: 'spin-slow 0.8s linear infinite' }} />}</div>)}</div><div style={{ textAlign: 'center', color: T.textMuted, fontSize: 11, marginTop: 12 }}>{polling ? 'Audio is being assembled from the speaker turns.' : 'Preparing your study session…'}</div></div>
    </div>
  }

  if (status === 'ready' && audioUrl) return <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}><div style={{ background: N.navy, padding: '0 18px 16px' }}><div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><button onClick={() => setStatus('config')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, color: '#fff', cursor: 'pointer' }}>{Ic.back()}</button><div style={{ flex: 1, color: '#fff' }}><div style={{ fontWeight: 800, fontSize: 15 }}>Study Podcast</div><div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>{documentTitle}</div></div></div></div><div style={{ flex: 1, padding: 22, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}><div style={{ background: `linear-gradient(145deg,${N.navy},${N.navy3})`, borderRadius: 24, padding: 24, color: '#fff', boxShadow: '0 12px 35px rgba(11,20,55,0.18)' }}><div style={{ fontSize: 11, color: N.gold, fontWeight: 800, textTransform: 'uppercase', letterSpacing: 1 }}>Ready to study</div><div style={{ fontSize: 20, fontWeight: 800, lineHeight: 1.35, margin: '8px 0' }}>{selected.label}</div><div style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)', marginBottom: 22 }}>{minutes} minutes · 3 voices · AI-generated from your document</div><audio ref={audioRef} src={audioUrl} preload="metadata" /><div style={{ height: 5, background: 'rgba(255,255,255,0.12)', borderRadius: 99, overflow: 'hidden' }}><div style={{ width: `${progressPct}%`, height: '100%', background: N.gold }} /></div><div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 10, color: 'rgba(255,255,255,0.45)' }}><span>{formatTime(progress)}</span><span>{formatTime(duration)}</span></div><button onClick={togglePlay} style={{ width: 58, height: 58, margin: '18px auto 0', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '50%', border: 'none', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, cursor: 'pointer', fontSize: 22 }}>{playing ? 'Ⅱ' : '▶'}</button></div><button onClick={() => setStatus('config')} style={{ marginTop: 14, background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: '12px 0', color: T.text, fontWeight: 800, fontSize: 12, fontFamily: 'Plus Jakarta Sans', cursor: 'pointer' }}>Create another version</button></div></div>

  if (status === 'error') return <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}><div style={{ background: N.navy, padding: '0 18px 16px', color: '#fff', display: 'flex', alignItems: 'center', gap: 10 }}><button onClick={() => setStatus('config')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, color: '#fff', cursor: 'pointer' }}>{Ic.back()}</button><div style={{ fontWeight: 800 }}>Podcast</div></div><div style={{ flex: 1, padding: 22, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center' }}><div style={{ width: 52, height: 52, borderRadius: 16, background: 'rgba(201,76,76,0.1)', color: '#C94C4C', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 14, fontWeight: 900 }}>!</div><div style={{ fontWeight: 800, color: T.text, fontSize: 16, marginBottom: 8 }}>We couldn't finish the podcast</div><div style={{ color: T.textMuted, fontSize: 12, lineHeight: 1.6, maxWidth: 320, marginBottom: 18 }}>{error}</div><div style={{ display: 'flex', gap: 8, width: '100%', maxWidth: 340 }}><button onClick={() => setStatus('config')} style={{ flex: 1, background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: 12, color: T.text, fontWeight: 800, fontFamily: 'Plus Jakarta Sans' }}>Change settings</button>{materialId && <button onClick={retryAudio} style={{ flex: 1, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 12, padding: 12, color: N.navy, fontWeight: 800, fontFamily: 'Plus Jakarta Sans' }}>Retry audio</button>}</div></div></div>

  return <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}><div style={{ background: N.navy, padding: '0 18px 16px', color: '#fff' }}><div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><button onClick={() => setScreen('document-study')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, color: '#fff', cursor: 'pointer' }}>{Ic.back()}</button><div style={{ flex: 1 }}><div style={{ fontWeight: 800, fontSize: 15 }}>Create your podcast</div><div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>{documentTitle}{pageCount != null ? ` · ${pageCount} pages` : ''}</div></div></div></div><div style={{ flex: 1, overflowY: 'auto', padding: 18 }} className="scrollbar-hide"><div style={{ background: T.card, borderRadius: 18, padding: 18, marginBottom: 14, border: `1px solid ${T.border}` }}><div style={{ fontSize: 11, color: T.textMuted, fontWeight: 800, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8 }}>Choose your study depth</div><div style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.6 }}>Longer sessions give Ada more room to explain, connect ideas, and prepare you for exams.</div></div><div style={{ display: 'grid', gap: 9 }}>{PODCAST_OPTIONS.map(option => { const active = minutes === option.minutes; const premium = option.minutes === 50; return <button key={option.minutes} onClick={() => { setMinutes(option.minutes); setStyle(option.style) }} style={{ width: '100%', textAlign: 'left', border: active ? `1.5px solid ${N.gold}` : `1px solid ${T.border}`, background: active ? 'rgba(201,168,76,0.08)' : T.card, borderRadius: 16, padding: '13px 14px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: active ? '0 5px 18px rgba(201,168,76,0.10)' : 'none' }}><div style={{ display: 'flex', alignItems: 'center', gap: 12 }}><div style={{ width: 48, height: 48, borderRadius: 14, background: active ? `linear-gradient(135deg,${N.gold},${N.goldL})` : T.pageBg, color: active ? N.navy : T.text, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><div style={{ fontWeight: 900, fontSize: 15 }}>{option.minutes}</div><div style={{ fontSize: 8, fontWeight: 700 }}>MIN</div></div><div style={{ flex: 1 }}><div style={{ display: 'flex', gap: 7, alignItems: 'center' }}><div style={{ color: T.text, fontWeight: 800, fontSize: 13 }}>{option.label}</div>{premium && <span style={{ fontSize: 8, fontWeight: 900, color: N.gold, border: `1px solid ${N.gold}55`, borderRadius: 99, padding: '3px 6px', textTransform: 'uppercase' }}>Deepest</span>}</div><div style={{ color: T.textMuted, fontSize: 11, lineHeight: 1.45, marginTop: 3 }}>{option.description}</div></div><div style={{ width: 18, height: 18, borderRadius: '50%', border: active ? `5px solid ${N.gold}` : `2px solid ${T.border}`, flexShrink: 0 }} /></div></button> })}</div><div style={{ background: `linear-gradient(135deg,${N.navy},${N.navy3})`, borderRadius: 16, padding: 16, marginTop: 14, color: '#fff' }}><div style={{ color: N.gold, fontSize: 10, fontWeight: 900, textTransform: 'uppercase', letterSpacing: 0.9, marginBottom: 5 }}>Selected session</div><div style={{ fontWeight: 800, fontSize: 15 }}>{selected.minutes} minutes · {selected.label}</div><div style={{ color: 'rgba(255,255,255,0.58)', fontSize: 11, lineHeight: 1.5, marginTop: 4 }}>{selected.description}</div></div></div><div style={{ padding: '10px 14px calc(12px + env(safe-area-inset-bottom))', background: T.card, borderTop: `1px solid ${T.border}` }}><button onClick={generate} disabled={!csrfToken} style={{ width: '100%', background: csrfToken ? `linear-gradient(135deg,${N.gold},${N.goldL})` : T.pageBg, color: csrfToken ? N.navy : T.textMuted, border: 'none', borderRadius: 14, padding: 13, fontWeight: 900, fontSize: 13, fontFamily: 'Plus Jakarta Sans', cursor: csrfToken ? 'pointer' : 'wait' }}>Generate {selected.minutes}-minute podcast</button></div></div>
}

'''
path.write_text(text[:start] + replacement + text[end:])
