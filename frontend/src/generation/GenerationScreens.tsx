import { useEffect, useRef, useState } from 'react'
import { canGenerate, fetchPrepzaUsage, type PrepzaUsage, usageLabel } from './usagePlan'

type SetScreen = (screen: any) => void

type ApiErrorShape = { message?: string; error?: string; status?: number; code?: string; remaining_units?: number; unit_limit?: number; feature?: string }

class GenerationApiError extends Error {
  status: number
  code?: string
  remainingUnits?: number
  constructor(message: string, status: number, code?: string, remainingUnits?: number) {
    super(message)
    this.status = status
    this.code = code
    this.remainingUnits = remainingUnits
  }
}

async function generationApi<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const { headers: extraHeaders, ...rest } = options
  const res = await fetch(path, {
    credentials: 'include',
    ...rest,
    headers: { 'Content-Type': 'application/json', ...(extraHeaders || {}) },
  })
  let body: ApiErrorShape & T = {} as ApiErrorShape & T
  try { body = await res.json() } catch { /* empty response */ }
  if (!res.ok) throw new GenerationApiError(body?.error || body?.message || `Request failed (${res.status})`, res.status, body?.code, body?.remaining_units)
  return body as T
}
async function pollGenerationJob<T = any>(jobId: number, onProgress?: (percent: number, stage: string) => void): Promise<{ payload: T; materialId: number | null }> {
  for (;;) {
    const job = await generationApi<{ status: string; progress_percent: number; progress_stage: string; error?: string; payload?: T }>(`/ai-jobs/${jobId}`)
    onProgress?.(Math.max(0, Math.min(100, Number(job.progress_percent || 0))), job.progress_stage || 'working')
    if (job.status === 'completed') return { payload: (job.payload ?? {}) as T, materialId: job.material_id ?? null }
    if (job.status === 'failed') throw new Error(job.error || 'Generation failed. Please try again.')
    await new Promise(resolve => window.setTimeout(resolve, 1800))
  }
}

function QuotaNotice({ usage, feature, unit }: { usage: PrepzaUsage | null; feature: 'summary' | 'podcast' | 'flashcards' | 'quiz' | 'mind_map'; unit: string }) {
  const remaining = Number(usage?.usage?.[feature]?.remaining_units ?? 0)
  if (!usage || remaining > 0) return null
  return <div style={{ margin: '10px 0 14px', padding: 12, borderRadius: 14, background: 'rgba(201,76,76,0.08)', border: '1px solid rgba(201,76,76,0.22)', color: C.text, fontSize: 11, lineHeight: 1.5 }}>
    <strong>Allowance used</strong><br />
    You have no {unit} remaining on your {usage.plan === 'free' ? 'Free' : usage.plan === 'plus' ? 'Plus' : 'Pro'} plan for this period. Upgrade your plan to continue generating.
  </div>
}

function friendlyGenerationError(error: unknown): string {
  if (!(error instanceof GenerationApiError)) return error instanceof Error ? error.message : 'Generation could not be completed. Please try again.'
  if (error.code === 'generation_quota_exhausted' || /used up this plan.?s generation allowance|generation quota exhausted/i.test(error.message)) {
    return 'You have used all of this feature’s allowance for your current plan. Upgrade your plan to continue generating.'
  }
  if (error.code === 'generation_size_limit') {
    return error.message
  }
  if (error.status === 429) return 'Prepza has temporarily limited this request. Please wait a moment and try again.'
  if (error.status === 402) return 'Fresh AI generation is temporarily unavailable. Existing study material is still available.'
  return error.message
}

function GenerationProgressCard({ title, subtitle, percent, stage }: { title: string; subtitle?: string; percent: number; stage: string }) {
  const safe = Math.max(0, Math.min(100, Math.round(percent)))
  return <div style={{ background: C.card, borderRadius: 22, padding: 22, boxShadow: '0 8px 30px rgba(0,0,0,0.07)' }}>
    <div style={{ color: C.gold, fontSize: 10, fontWeight: 900, letterSpacing: 1, textTransform: 'uppercase' }}>Prepza · Generating</div>
    <div style={{ color: C.text, fontSize: 19, fontWeight: 850, marginTop: 7 }}>{title}</div>
    {subtitle && <div style={{ color: C.muted, fontSize: 12, marginTop: 4 }}>{subtitle}</div>}
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 22, marginBottom: 8 }}>
      <span style={{ color: C.muted, fontSize: 11 }}>{stage}</span>
      <strong style={{ color: C.text, fontSize: 15 }}>{safe}%</strong>
    </div>
    <div style={{ height: 9, background: C.border, borderRadius: 99, overflow: 'hidden' }}>
      <div style={{ width: `${safe}%`, height: '100%', background: `linear-gradient(90deg,${C.gold},${C.goldLight})`, borderRadius: 99, transition: 'width .45s ease' }} />
    </div>
    <div style={{ color: C.muted, fontSize: 11, lineHeight: 1.5, marginTop: 13 }}>You can leave this screen. Prepza keeps the generation running and will notify you when it is ready.</div>
  </div>
}

const C = {
  navy: '#0B1437',
  navy2: '#162342',
  navy3: '#24345B',
  gold: '#C9A84C',
  goldLight: '#E3C873',
  text: '#172033',
  muted: '#7A8498',
  page: '#F7F8FB',
  card: '#FFFFFF',
  border: '#E7E9EF',
  green: '#4CC97B',
  red: '#C94C4C',
}

const headerStyle = { background: C.navy, padding: '0 18px 16px', color: '#fff' }
const buttonBase = { fontFamily: 'Plus Jakarta Sans', fontWeight: 800, cursor: 'pointer' }


async function subscribeForGenerationNotifications(csrfToken: string): Promise<void> {
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) throw new Error('Push notifications are not supported on this device.')
  if (Notification.permission !== 'granted') {
    const permission = await Notification.requestPermission()
    if (permission !== 'granted') throw new Error('Notification permission was not granted.')
  }
  const registration = await navigator.serviceWorker.ready
  const response = await generationApi<{ public_key: string }>('/push/vapid-public-key')
  const padding = '='.repeat((4 - (response.public_key.length % 4)) % 4)
  const raw = window.atob((response.public_key + padding).replace(/-/g, '+').replace(/_/g, '/'))
  const key = Uint8Array.from([...raw].map(c => c.charCodeAt(0)))
  const subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key as BufferSource })
  const json = subscription.toJSON()
  await generationApi('/push/subscribe', { method: 'POST', headers: { 'X-CSRF-Token': csrfToken }, body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }) })
}
function GenerationHeader({ title, subtitle, onBack }: { title: string; subtitle?: string; onBack: () => void }) {
  return (
    <div style={headerStyle}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button onClick={onBack} style={{ width: 34, height: 34, border: 'none', borderRadius: 10, background: 'rgba(255,255,255,0.1)', color: '#fff', fontSize: 20, cursor: 'pointer' }}>‹</button>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 800, fontSize: 16 }}>{title}</div>
          {subtitle && <div style={{ marginTop: 2, fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>{subtitle}</div>}
        </div>
      </div>
    </div>
  )
}

function ChoiceCard({ selected, title, description, onClick, badge, disabled }: { selected: boolean; title: string; description?: string; onClick: () => void; badge?: string; disabled?: boolean }) {
  return (
    <button disabled={disabled} onClick={onClick} style={{ width: '100%', textAlign: 'left', border: `1.5px solid ${selected ? C.gold : C.border}`, background: disabled ? '#F1F3F6' : selected ? 'rgba(201,168,76,0.07)' : C.card, color: disabled ? C.muted : undefined, opacity: disabled ? 0.6 : 1, borderRadius: 15, padding: '13px 14px', marginBottom: 8, ...buttonBase, cursor: disabled ? 'not-allowed' : 'pointer' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
        <div style={{ width: 19, height: 19, borderRadius: '50%', border: `2px solid ${selected ? C.gold : '#B9BFCC'}`, background: selected ? C.gold : 'transparent', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {selected && <div style={{ width: 7, height: 7, borderRadius: '50%', background: C.navy }} />}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <div style={{ color: C.text, fontSize: 13 }}>{title}</div>
            {badge && <span style={{ background: C.navy, color: C.gold, borderRadius: 99, padding: '3px 7px', fontSize: 9, fontWeight: 800 }}>{badge}</span>}
          </div>
          {description && <div style={{ color: C.muted, fontSize: 11, lineHeight: 1.45, marginTop: 2 }}>{description}</div>}
        </div>
      </div>
    </button>
  )
}

function GenerateButton({ disabled, children, onClick }: { disabled?: boolean; children: React.ReactNode; onClick: () => void }) {
  return <button disabled={disabled} onClick={onClick} style={{ width: '100%', border: 'none', borderRadius: 15, padding: '14px 16px', background: disabled ? '#D9DDE5' : `linear-gradient(135deg,${C.gold},${C.goldLight})`, color: disabled ? '#7D8492' : C.navy, fontSize: 14, ...buttonBase }}>{children}</button>
}

function GenerationFailure({ error, onBack, onRetry }: { error: string; onBack: () => void; onRetry: () => void }) {
  return (
    <div style={{ flex: 1, background: C.page }}>
      <GenerationHeader title="Generation failed" onBack={onBack} />
      <div style={{ minHeight: 360, padding: 24, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center' }}>
        <div style={{ width: 52, height: 52, borderRadius: 16, background: 'rgba(201,76,76,0.1)', color: C.red, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900, fontSize: 22, marginBottom: 14 }}>!</div>
        <div style={{ color: C.text, fontWeight: 800, fontSize: 17, marginBottom: 8 }}>We couldn't finish this yet</div>
        <div style={{ color: C.muted, fontSize: 12, lineHeight: 1.6, maxWidth: 320, marginBottom: 18 }}>{error}</div>
        <button onClick={onRetry} style={{ border: 'none', borderRadius: 12, padding: '11px 22px', background: C.navy, color: C.gold, ...buttonBase }}>Try again</button>
      </div>
    </div>
  )
}

const PODCAST_OPTIONS = [
  { minutes: 10, label: 'Focused Revision', description: 'Core concepts with useful context.', style: 'focused_revision' },
  { minutes: 20, label: 'Deeper Explanation', description: 'Teaching, examples, and connections.', style: 'deep_explanation' },
  { minutes: 30, label: 'Deep Study', description: 'A proper guided study session.', style: 'deep_study' },
  { minutes: 40, label: 'Comprehensive Study', description: 'Broad coverage with deeper explanations.', style: 'comprehensive_study' },
  { minutes: 50, label: 'Deep Explanation + Exam Focus', description: 'The fullest study session with exam-focused teaching and review.', style: 'deep_exam' },
] as const

export function PodcastGenerationScreen({ setScreen, activeDocumentId }: { setScreen: SetScreen; activeDocumentId: number | null }) {
  const [minutes, setMinutes] = useState(10)
  const [style, setStyle] = useState('quick_revision')
  const [csrf, setCsrf] = useState('')
  const [title, setTitle] = useState('Study Podcast')
  const [pages, setPages] = useState<number | null>(null)
  const [phase, setPhase] = useState<'config' | 'script' | 'audio' | 'ready' | 'error'>('config')
  const [error, setError] = useState('')
  const [generationPercent, setGenerationPercent] = useState(0)
  const [generationStage, setGenerationStage] = useState('preparing')
  const [usage, setUsage] = useState<PrepzaUsage | null>(null)
  const [materialId, setMaterialId] = useState<number | null>(null)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [audioDuration, setAudioDuration] = useState(0)
  const [progress, setProgress] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [notificationChoice, setNotificationChoice] = useState(false)
  const [notificationBusy, setNotificationBusy] = useState(false)
  const audioRef = useRef<HTMLAudioElement>(null)

  useEffect(() => {
    if (activeDocumentId == null) return
    Promise.all([generationApi<{ csrf_token: string }>('/me'), generationApi<{ title: string; page_count: number | null }>(`/documents/${activeDocumentId}`), fetchPrepzaUsage()])
      .then(([me, doc, planUsage]) => { setCsrf(me.csrf_token); setTitle(doc.title); setPages(doc.page_count); setUsage(planUsage) })
      .catch(e => setError(e instanceof Error ? e.message : 'Could not load the document.'))
  }, [activeDocumentId])

  useEffect(() => {
    const option = PODCAST_OPTIONS.find(o => o.minutes === minutes)
    if (option && phase === 'config') setStyle(option.style)
  }, [minutes, phase])

  useEffect(() => {
    if (activeDocumentId == null || !csrf || phase !== 'config') return
    let cancelled = false
    generationApi<{ audio_status: string; audio_url: string | null; duration_seconds: number | null }>('/documents/' + activeDocumentId + '/podcast-audio')
      .then(res => {
        if (cancelled) return
        if (res.audio_status === 'processing') setPhase('audio')
        else if (res.audio_status === 'ready' && res.audio_url) {
          setAudioUrl(res.audio_url)
          setAudioDuration(res.duration_seconds || 0)
          setPhase('ready')
        }
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [activeDocumentId, csrf, phase])

  // Recover a script job that is still running after the student leaves and
  // returns to this screen. Generation is server-owned; the screen must not
  // lose the job merely because its local React state was unmounted.
  useEffect(() => {
    if (activeDocumentId == null || !csrf || phase !== 'config') return
    let cancelled = false
    const recover = async () => {
      try {
        const status = await generationApi<{
          found: boolean
          status: string
          job_id?: number
          material_id?: number | null
          progress_percent?: number
          progress_stage?: string
        }>(`/documents/${activeDocumentId}/generation-progress?feature=podcast`)
        if (cancelled || !status.found) return

        if (status.status === 'processing' && status.job_id) {
          setGenerationPercent(Math.min(65, Math.round(Number(status.progress_percent || 0) * 0.65)))
          setGenerationStage(status.progress_stage || 'generating with AI')
          setPhase('script')
          const result = await pollGenerationJob<{ script?: any; audio_status?: string }>(
            status.job_id,
            (p, s) => {
              if (cancelled) return
              setGenerationPercent(Math.min(65, Math.round(p * 0.65)))
              setGenerationStage(s)
            },
          )
          if (cancelled) return
          setMaterialId(result.materialId ?? status.material_id ?? null)
          setGenerationPercent(65)
          setGenerationStage('starting audio synthesis')
          setPhase('audio')
          await generationApi(`/documents/${activeDocumentId}/podcast-audio`, {
            method: 'POST',
            headers: { 'X-CSRF-Token': csrf },
          })
          return
        }

        if (status.status === 'completed' && status.material_id) {
          setMaterialId(status.material_id)
          const audio = await generationApi<{
            audio_status: string
            audio_url: string | null
            duration_seconds: number | null
            progress_percent?: number
            progress_stage?: string
          }>(`/documents/${activeDocumentId}/podcast-audio`)
          if (cancelled) return
          if (audio.audio_status === 'ready' && audio.audio_url) {
            setAudioUrl(audio.audio_url)
            setAudioDuration(audio.duration_seconds || 0)
            setGenerationPercent(100)
            setGenerationStage('ready')
            setPhase('ready')
          } else {
            setGenerationPercent(Math.max(65, Number(audio.progress_percent || 0)))
            setGenerationStage(audio.progress_stage || 'creating audio')
            setPhase('audio')
          }
        }
      } catch {
        // A normal config screen remains usable if there is no recoverable job.
      }
    }
    recover()
    return () => { cancelled = true }
  }, [activeDocumentId, csrf, phase])

  useEffect(() => {
    if (phase !== 'audio' || activeDocumentId == null) return
    let cancelled = false
    const poll = async () => {
      try {
        const res = await generationApi<{ audio_status: string; audio_url: string | null; duration_seconds: number | null }>(`/documents/${activeDocumentId}/podcast-audio`)
        if (cancelled) return
        if (res.audio_status === 'ready' && res.audio_url) {
          setAudioUrl(res.audio_url); setAudioDuration(res.duration_seconds || 0); setPhase('ready'); return
        }
        if (res.audio_status === 'failed') { setError('Audio generation failed. You can retry it without regenerating the script.'); setPhase('error'); return }
        generationApi<{ progress_percent: number; progress_stage: string }>(`/documents/${activeDocumentId}/generation-progress?feature=podcast_audio`).then(p => { setGenerationPercent(Math.max(65, Number(p.progress_percent || 0))); setGenerationStage(p.progress_stage || 'creating audio') }).catch(() => {})
        window.setTimeout(poll, 1800)
      } catch (e) { if (!cancelled) { setError(e instanceof Error ? e.message : 'Could not check audio progress.'); setPhase('error') } }
    }
    poll()
    return () => { cancelled = true }
  }, [phase, activeDocumentId])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    const onTime = () => setProgress(audio.currentTime)
    const onMeta = () => setAudioDuration(audio.duration || 0)
    const onEnd = () => setPlaying(false)
    audio.addEventListener('timeupdate', onTime); audio.addEventListener('loadedmetadata', onMeta); audio.addEventListener('ended', onEnd)
    return () => { audio.removeEventListener('timeupdate', onTime); audio.removeEventListener('loadedmetadata', onMeta); audio.removeEventListener('ended', onEnd) }
  }, [audioUrl])

  const generate = async () => {
    if (activeDocumentId == null || !csrf) return
    setError(''); setGenerationPercent(0); setGenerationStage('preparing'); setPhase('script')
    try {
      const scriptJob = await generationApi<{ job_id: number }>(`/documents/${activeDocumentId}/podcast-script?async=1`, { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ duration_minutes: minutes, style, language: 'en' }) })
      const scriptResult = await pollGenerationJob<{ script?: any; audio_status?: string }>(scriptJob.job_id, (p, s) => { setGenerationPercent(Math.min(65, Math.round(p * 0.65))); setGenerationStage(s) })
      setMaterialId(scriptResult.materialId)
      setGenerationPercent(65); setGenerationStage('starting audio synthesis')
      setPhase('audio')
      await generationApi(`/documents/${activeDocumentId}/podcast-audio`, { method: 'POST', headers: { 'X-CSRF-Token': csrf } })
    } catch (e) { setError(friendlyGenerationError(e)); setPhase('error') }
  }

  const retryAudio = async () => {
    if (activeDocumentId == null || !csrf || !materialId) return
    setError(''); setPhase('audio')
    try { await generationApi(`/documents/${activeDocumentId}/podcast-audio`, { method: 'POST', headers: { 'X-CSRF-Token': csrf } }) }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not restart audio generation.'); setPhase('error') }
  }

  if (activeDocumentId == null) return <GenerationFailure error="No document selected." onBack={() => setScreen('document-study')} onRetry={() => setScreen('document-study')} />
  if (phase === 'error') return <GenerationFailure error={error} onBack={() => setPhase('config')} onRetry={materialId ? retryAudio : generate} />
  if (phase === 'script' || phase === 'audio') {
    return <div style={{ flex: 1, background: C.page }}><GenerationHeader title="Creating your podcast" subtitle={`${minutes} minutes · ${PODCAST_OPTIONS.find(o => o.minutes === minutes)?.label}`} onBack={() => setScreen('document-study')} /><div style={{ padding: 22, display: 'flex', flexDirection: 'column', justifyContent: 'center', minHeight: 380 }}><GenerationProgressCard title="Generating your podcast" subtitle={`${minutes} minutes · ${PODCAST_OPTIONS.find(o => o.minutes === minutes)?.label || ''}`} percent={generationPercent} stage={generationStage} /><div style={{ display: 'none' }}><div style={{ color: C.gold, fontSize: 10, fontWeight: 900, letterSpacing: 1, textTransform: 'uppercase' }}>Prepza Podcast</div><div style={{ color: C.text, fontSize: 18, fontWeight: 800, marginTop: 7 }}>{title}</div><div style={{ color: C.muted, fontSize: 12, marginTop: 4, marginBottom: 18 }}>{pages != null ? `${pages} pages · ` : ''}{minutes} minutes</div>{[['Document ready', true], ['Creating podcast script', phase === 'audio'], ['Creating audio', phase === 'audio'], ['Finalising', false]].map(([label, done]) => <div key={String(label)} style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '10px 0', borderBottom: `1px solid ${C.border}` }}><div style={{ width: 22, height: 22, borderRadius: '50%', background: done === true ? 'rgba(76,201,123,0.14)' : C.page, color: done === true ? C.green : C.muted, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 900 }}>{done === true ? '✓' : ''}</div><div style={{ flex: 1, color: C.text, fontSize: 13, fontWeight: done === true ? 700 : 600 }}>{label}</div></div>)}</div><div style={{ textAlign: 'center', color: C.muted, fontSize: 11, marginTop: 14 }}>{phase === 'audio' ? 'Audio is being assembled from the generated speaker turns.' : 'Writing a study-focused script from your document…'}</div></div></div>
  }
  if (phase === 'ready' && audioUrl) {
    const pct = audioDuration ? Math.min(100, (progress / audioDuration) * 100) : 0
    return <div style={{ flex: 1, background: C.page }}><GenerationHeader title="Study Podcast" subtitle={title} onBack={() => setScreen('document-study')} /><div style={{ padding: 22, display: 'flex', flexDirection: 'column', justifyContent: 'center', minHeight: 380 }}><div style={{ background: `linear-gradient(145deg,${C.navy},${C.navy3})`, borderRadius: 24, padding: 24, color: '#fff' }}><div style={{ color: C.gold, fontSize: 10, fontWeight: 900, letterSpacing: 1, textTransform: 'uppercase' }}>Ready to study</div><div style={{ fontSize: 20, fontWeight: 800, margin: '8px 0' }}>{PODCAST_OPTIONS.find(o => o.minutes === minutes)?.label}</div><div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 12, marginBottom: 18 }}>{minutes} minutes · 3 voices · AI-generated from your document</div><audio ref={audioRef} src={audioUrl} preload="metadata" /><div style={{ height: 5, background: 'rgba(255,255,255,0.12)', borderRadius: 99, overflow: 'hidden' }}><div style={{ width: `${pct}%`, height: '100%', background: C.gold }} /></div><div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 10, color: 'rgba(255,255,255,0.45)' }}><span>{Math.floor(progress / 60)}:{String(Math.floor(progress % 60)).padStart(2, '0')}</span><span>{Math.floor(audioDuration / 60)}:{String(Math.floor(audioDuration % 60)).padStart(2, '0')}</span></div><button onClick={async () => { const a = audioRef.current; if (!a) return; if (a.paused) { await a.play(); setPlaying(true) } else { a.pause(); setPlaying(false) } }} style={{ width: 58, height: 58, margin: '18px auto 0', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '50%', border: 'none', background: `linear-gradient(135deg,${C.gold},${C.goldLight})`, color: C.navy, fontSize: 21, cursor: 'pointer' }}>{playing ? 'Ⅱ' : '▶'}</button></div><button onClick={() => setPhase('config')} style={{ width: '100%', marginTop: 12, border: `1px solid ${C.border}`, borderRadius: 14, padding: 12, background: C.card, color: C.text, ...buttonBase }}>Create another version</button></div></div>
  }
  const selected = PODCAST_OPTIONS.find(o => o.minutes === minutes) || PODCAST_OPTIONS[2]
  const podcastLimit = usage?.limits.podcast_max_minutes ?? 0
  const podcastAvailable = (n: number) => canGenerate(usage, 'podcast', n)
  return <div style={{ flex: 1, background: C.page, overflowY: 'auto' }}><GenerationHeader title="Create your podcast" subtitle={title} onBack={() => setScreen('document-study')} /><div style={{ padding: 18 }}><div style={{ color: C.text, fontWeight: 800, fontSize: 18 }}>Choose how you want to study</div><div style={{ color: C.muted, fontSize: 12, lineHeight: 1.6, margin: '5px 0 18px' }}>{pages != null ? `${pages} pages · ` : ''}Your choices become part of the generation fingerprint, so each distinct configuration can be reused safely.</div><div style={{ color: C.text, fontWeight: 800, fontSize: 12, marginBottom: 9 }}>Duration</div><div style={{ color: C.muted, fontSize: 11, marginBottom: 9 }}>{usageLabel(usage)}{usage ? ` · ${usage.usage.podcast?.remaining_units ?? 0} podcast minutes remaining` : ''}</div><QuotaNotice usage={usage} feature="podcast" unit="podcast minutes" />{PODCAST_OPTIONS.map(o => <ChoiceCard key={o.minutes} disabled={o.minutes > podcastLimit || !podcastAvailable(o.minutes)} selected={minutes === o.minutes} title={`${o.minutes} minutes · ${o.label}`} description={o.description} badge={o.minutes === 50 ? 'DEEPEST' : undefined} onClick={() => setMinutes(o.minutes)} />)}<div style={{ color: C.text, fontWeight: 800, fontSize: 12, margin: '17px 0 9px' }}>Teaching style</div>{PODCAST_OPTIONS.map(o => <ChoiceCard key={o.style} selected={style === o.style} title={o.label} description={o.description} onClick={() => setStyle(o.style)} />)}<div style={{ background: 'rgba(201,168,76,0.08)', border: `1px solid ${C.gold}33`, borderRadius: 14, padding: 12, margin: '14px 0 16px', color: C.text, fontSize: 11, lineHeight: 1.55 }}><strong>{selected.minutes}-minute {selected.label}</strong> — {selected.minutes === 50 ? 'the deepest option, combining explanation, deep study and exam focus.' : selected.description}</div><GenerateButton disabled={!csrf || !podcastAvailable(minutes) || notificationBusy} onClick={() => {
        if (typeof Notification !== 'undefined' && Notification.permission === 'granted') { void generate(); return }
        setNotificationChoice(true)
      }}>{notificationBusy ? 'Enabling notifications…' : 'Generate ' + minutes + '-minute podcast'}</GenerateButton>
      {notificationChoice && (
        <div style={{ marginTop: 12, background: C.card, border: '1px solid ' + C.border, borderRadius: 16, padding: 15 }}>
          <div style={{ color: C.text, fontWeight: 800, fontSize: 13 }}>Want a notification when it’s ready?</div>
          <div style={{ color: C.muted, fontSize: 11, lineHeight: 1.5, marginTop: 4 }}>You can leave this screen while Prepza creates the podcast. We’ll notify you when the finished episode is ready.</div>
          <button disabled={notificationBusy} onClick={async () => {
            setNotificationBusy(true)
            try { await subscribeForGenerationNotifications(csrf); setNotificationChoice(false); await generate() }
            catch (e) { setError(e instanceof Error ? e.message : 'Could not enable notifications. The podcast will still be generated.'); setNotificationChoice(false); await generate() }
            finally { setNotificationBusy(false) }
          }} style={{ width: '100%', marginTop: 12, border: 'none', borderRadius: 12, padding: 12, background: C.navy, color: C.gold, ...buttonBase }}>Yes, notify me</button>
          <button disabled={notificationBusy} onClick={() => { setNotificationChoice(false); void generate() }} style={{ width: '100%', marginTop: 7, border: '1px solid ' + C.border, borderRadius: 12, padding: 12, background: C.card, color: C.text, ...buttonBase }}>Not now</button>
        </div>
      )}</div></div>
}

const FLASHCARD_COUNTS = [10, 20, 30, 50]
const FLASHCARD_DIFFICULTIES = [
  { value: 'easy', label: 'Easy', description: 'Definitions, recall, and fundamentals.' },
  { value: 'balanced', label: 'Balanced', description: 'A mix of recall and application.' },
  { value: 'hard', label: 'Hard', description: 'More challenging exam-style recall.' },
]

export function FlashcardsGenerationScreen({ setScreen, activeDocumentId }: { setScreen: SetScreen; activeDocumentId: number | null }) {
  const [count, setCount] = useState(10)
  const [difficulty, setDifficulty] = useState('balanced')
  const [phase, setPhase] = useState<'config' | 'generating' | 'review' | 'done' | 'error'>('config')
  const [csrf, setCsrf] = useState('')
  const [title, setTitle] = useState('Flashcards')
  const [cards, setCards] = useState<{ q: string; a: string }[]>([])
  const [idx, setIdx] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [known, setKnown] = useState<number[]>([])
  const [materialId, setMaterialId] = useState<number | null>(null)
  const [completion, setCompletion] = useState<any>(null)
  const [error, setError] = useState('')
  const [generationPercent, setGenerationPercent] = useState(0)
  const [generationStage, setGenerationStage] = useState('preparing')
  const [usage, setUsage] = useState<PrepzaUsage | null>(null)

  useEffect(() => {
    if (activeDocumentId == null) return
    Promise.all([generationApi<{ csrf_token: string }>('/me'), generationApi<{ title: string }>(`/documents/${activeDocumentId}`), fetchPrepzaUsage()])
      .then(([me, doc, planUsage]) => { setCsrf(me.csrf_token); setTitle(doc.title); setUsage(planUsage) })
      .catch(e => setError(e instanceof Error ? e.message : 'Could not load the document.'))
  }, [activeDocumentId])

  const normalize = (raw: any) => {
    const list = Array.isArray(raw) ? raw : Array.isArray(raw?.cards) ? raw.cards : Array.isArray(raw?.flashcards) ? raw.flashcards : []
    return list.map((item: any) => ({ q: item.q || item.question || item.front || 'Question', a: item.a || item.answer || item.back || 'Answer' }))
  }

  const generate = async () => {
    if (activeDocumentId == null || !csrf || !canGenerate(usage, 'flashcards', count)) return
    setError(''); setGenerationPercent(0); setGenerationStage('preparing'); setPhase('generating')
    try {
      const started = await generationApi<{ job_id: number }>(`/documents/${activeDocumentId}/flashcards?async=1`, { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ card_count: count, difficulty, language: 'en' }) })
      const result = await pollGenerationJob<any>(started.job_id, (p, s) => { setGenerationPercent(p); setGenerationStage(s) })
      const next = normalize(result.payload.flashcards)
      if (!next.length) throw new Error('No flashcards were returned.')
      setMaterialId(result.materialId); setCards(next); setIdx(0); setFlipped(false); setKnown([]); setPhase('review')
    } catch (e) { setError(friendlyGenerationError(e)); setPhase('error') }
  }

  const finish = async (reviewed: number) => {
    setPhase('done')
    if (activeDocumentId == null || materialId == null) return
    try { setCompletion(await generationApi(`/documents/${activeDocumentId}/flashcards/${materialId}/complete`, { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ cards_reviewed: reviewed }) })) } catch { /* review is already complete */ }
  }

  const answer = (gotIt: boolean) => {
    if (gotIt) setKnown(k => [...k, idx])
    setFlipped(false)
    window.setTimeout(() => idx + 1 >= cards.length ? finish(idx + 1) : setIdx(i => i + 1), 120)
  }

  if (phase === 'error') return <GenerationFailure error={error} onBack={() => setPhase('config')} onRetry={generate} />
  if (phase === 'generating') return <div style={{ flex: 1, background: C.page }}><GenerationHeader title="Generating flashcards" subtitle={title} onBack={() => setScreen('document-study')} /><div style={{ padding: 22, minHeight: 380, display: 'flex', alignItems: 'center' }}><div style={{ width: '100%' }}><GenerationProgressCard title="Generating your flashcards" subtitle={`${count} cards · ${difficulty}`} percent={generationPercent} stage={generationStage} /></div></div></div>
  if (phase === 'done') return <div style={{ flex: 1, background: C.page }}><GenerationHeader title="Review complete" onBack={() => setScreen('document-study')} /><div style={{ minHeight: 380, padding: 30, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center' }}><div style={{ fontSize: 42, marginBottom: 12 }}>✓</div><div style={{ color: C.text, fontSize: 21, fontWeight: 800 }}>Review complete</div><div style={{ color: C.muted, fontSize: 13, marginTop: 6 }}>{known.length}/{cards.length} marked as known</div>{completion?.xp_awarded > 0 && <div style={{ color: C.gold, fontWeight: 800, fontSize: 13, marginTop: 10 }}>+{completion.xp_awarded} XP</div>}<button onClick={() => setScreen('document-study')} style={{ marginTop: 20, border: 'none', borderRadius: 14, padding: '12px 22px', background: `linear-gradient(135deg,${C.gold},${C.goldLight})`, color: C.navy, ...buttonBase }}>Back to Notes</button></div></div>
  if (phase === 'review') {
    const card = cards[idx]
    return <div style={{ flex: 1, background: C.page }}><GenerationHeader title="Flashcards" subtitle={`${idx + 1} of ${cards.length} · ${title}`} onBack={() => setScreen('document-study')} /><div style={{ padding: 18 }}><div style={{ height: 5, background: C.border, borderRadius: 99, overflow: 'hidden', marginBottom: 22 }}><div style={{ width: `${((idx + 1) / cards.length) * 100}%`, height: '100%', background: C.gold }} /></div><button onClick={() => setFlipped(v => !v)} style={{ width: '100%', minHeight: 230, border: `1.5px solid ${flipped ? C.gold : C.border}`, borderRadius: 22, background: C.card, padding: 25, textAlign: 'left', cursor: 'pointer', boxShadow: '0 8px 28px rgba(0,0,0,0.06)' }}><div style={{ color: C.gold, fontSize: 10, fontWeight: 900, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 13 }}>{flipped ? 'Answer' : 'Question · tap to reveal'}</div><div style={{ color: C.text, fontSize: 14, lineHeight: 1.75, fontWeight: 650, whiteSpace: 'pre-line' }}>{flipped ? card.a : card.q}</div></button>{flipped ? <div style={{ display: 'flex', gap: 9, marginTop: 16 }}><button onClick={() => answer(false)} style={{ flex: 1, border: 'none', borderRadius: 14, padding: 13, background: '#FDE5E5', color: C.red, ...buttonBase }}>Still learning</button><button onClick={() => answer(true)} style={{ flex: 1, border: 'none', borderRadius: 14, padding: 13, background: '#DDF6E8', color: '#17663A', ...buttonBase }}>Got it</button></div> : <div style={{ color: C.muted, fontSize: 12, textAlign: 'center', marginTop: 14 }}>Tap the card to see the answer</div>}</div></div>
  }
  return <div style={{ flex: 1, background: C.page, overflowY: 'auto' }}><GenerationHeader title="Create flashcards" subtitle={title} onBack={() => setScreen('document-study')} /><div style={{ padding: 18 }}><div style={{ color: C.text, fontWeight: 800, fontSize: 18 }}>Choose your deck</div><div style={{ color: C.muted, fontSize: 12, lineHeight: 1.6, margin: '5px 0 18px' }}>Your count and difficulty are sent to the generation backend and included in the artifact fingerprint.</div><div style={{ color: C.text, fontWeight: 800, fontSize: 12, marginBottom: 9 }}>Number of cards</div><div style={{ color: C.muted, fontSize: 11, marginBottom: 9 }}>{usageLabel(usage)}{usage ? ` · ${usage.usage.flashcards?.remaining_units ?? 0} flashcards remaining` : ''}</div><QuotaNotice usage={usage} feature="flashcards" unit="flashcards" />{FLASHCARD_COUNTS.map(n => <ChoiceCard key={n} disabled={!canGenerate(usage, 'flashcards', n)} selected={count === n} title={`${n} cards`} description={n === 50 ? 'Large exam-prep deck.' : n === 30 ? 'Thorough review.' : n === 20 ? 'Balanced study session.' : 'Quick recall session.'} onClick={() => setCount(n)} />)}<div style={{ color: C.text, fontWeight: 800, fontSize: 12, margin: '17px 0 9px' }}>Difficulty</div>{FLASHCARD_DIFFICULTIES.map(d => <ChoiceCard key={d.value} selected={difficulty === d.value} title={d.label} description={d.description} onClick={() => setDifficulty(d.value)} />)}<GenerateButton disabled={!csrf || !canGenerate(usage, 'flashcards', count)} onClick={generate}>Generate {count} flashcards</GenerateButton></div></div>
}

const SUMMARY_OPTIONS = [
  { pages: 1, label: 'One-page brief', description: 'Only the most important points.' },
  { pages: 2, label: 'Two-page study sheet', description: 'Compact but properly explained.' },
  { pages: 5, label: 'Detailed notes', description: 'More context, examples, and structure.' },
  { pages: 10, label: 'Comprehensive summary', description: 'Maximum detail within the summary format.' },
]

export function SummaryGenerationScreen({ setScreen, activeDocumentId }: { setScreen: SetScreen; activeDocumentId: number | null }) {
  const [maxPages, setMaxPages] = useState(2)
  const [style, setStyle] = useState('balanced')
  const [csrf, setCsrf] = useState('')
  const [title, setTitle] = useState('AI Summary')
  const [phase, setPhase] = useState<'config' | 'generating' | 'ready' | 'error'>('config')
  const [summary, setSummary] = useState<any>(null)
  const [error, setError] = useState('')
  const [generationPercent, setGenerationPercent] = useState(0)
  const [generationStage, setGenerationStage] = useState('preparing')
  const [usage, setUsage] = useState<PrepzaUsage | null>(null)

  useEffect(() => {
    if (activeDocumentId == null) return
    Promise.all([generationApi<{ csrf_token: string }>('/me'), generationApi<{ title: string }>(`/documents/${activeDocumentId}`), fetchPrepzaUsage()])
      .then(([me, doc, planUsage]) => { setCsrf(me.csrf_token); setTitle(doc.title); setUsage(planUsage) })
      .catch(e => setError(e instanceof Error ? e.message : 'Could not load the document.'))
  }, [activeDocumentId])

  const generate = async () => {
    if (activeDocumentId == null || !csrf || !canGenerate(usage, 'summary', maxPages)) return
    setError(''); setPhase('generating')
    try {
      const started = await generationApi<{ job_id: number }>(`/documents/${activeDocumentId}/summarize?async=1`, { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ max_pages: maxPages, style, language: 'en' }) })
      const result = await pollGenerationJob<any>(started.job_id, (p, s) => { setGenerationPercent(p); setGenerationStage(s) })
      setSummary(result.payload.summary); setPhase('ready')
    } catch (e) { setError(friendlyGenerationError(e)); setPhase('error') }
  }

  const renderSummary = () => {
    if (typeof summary === 'string') return <div style={{ whiteSpace: 'pre-line' }}>{summary}</div>
    if (Array.isArray(summary)) return summary.map((s: any, i: number) => <div key={i} style={{ marginBottom: 18 }}>{(s.title || s.heading) && <div style={{ fontWeight: 800, marginBottom: 6 }}>{s.title || s.heading}</div>}<div style={{ whiteSpace: 'pre-line' }}>{s.body || s.content || s.text || JSON.stringify(s)}</div></div>)
    if (summary && typeof summary === 'object') return <div style={{ whiteSpace: 'pre-line' }}>{summary.text || summary.content || summary.body || JSON.stringify(summary, null, 2)}</div>
    return null
  }

  if (phase === 'error') return <GenerationFailure error={error} onBack={() => setPhase('config')} onRetry={generate} />
  if (phase === 'generating') return <div style={{ flex: 1, background: C.page }}><GenerationHeader title="Generating summary" subtitle={title} onBack={() => setScreen('document-study')} /><div style={{ padding: 22, minHeight: 380, display: 'flex', alignItems: 'center' }}><div style={{ width: '100%' }}><GenerationProgressCard title="Generating your summary" subtitle={`${maxPages}-page · ${style}`} percent={generationPercent} stage={generationStage} /></div></div></div>
  if (phase === 'ready') return <div style={{ flex: 1, background: C.page, overflowY: 'auto' }}><GenerationHeader title="AI Summary" subtitle={`${title} · ${maxPages}-page format`} onBack={() => setScreen('document-study')} /><div style={{ padding: 18 }}><div style={{ background: C.card, borderRadius: 18, padding: 20, boxShadow: '0 2px 10px rgba(0,0,0,0.06)', color: C.text, fontSize: 13, lineHeight: 1.8 }}><div style={{ color: C.gold, fontSize: 10, fontWeight: 900, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 10 }}>AI Generated</div>{renderSummary()}</div><button onClick={() => setPhase('config')} style={{ width: '100%', marginTop: 12, border: `1px solid ${C.border}`, borderRadius: 14, padding: 12, background: C.card, color: C.text, ...buttonBase }}>Create another version</button></div></div>
  return <div style={{ flex: 1, background: C.page, overflowY: 'auto' }}><GenerationHeader title="Create a summary" subtitle={title} onBack={() => setScreen('document-study')} /><div style={{ padding: 18 }}><div style={{ color: C.text, fontWeight: 800, fontSize: 18 }}>Choose the depth</div><div style={{ color: C.muted, fontSize: 12, lineHeight: 1.6, margin: '5px 0 18px' }}>The selected output length and style are passed directly to the generation backend.</div><div style={{ color: C.text, fontWeight: 800, fontSize: 12, marginBottom: 9 }}>Length</div><div style={{ color: C.muted, fontSize: 11, marginBottom: 9 }}>{usageLabel(usage)}{usage ? ` · ${usage.usage.summary?.remaining_units ?? 0} summary pages remaining` : ''}</div><QuotaNotice usage={usage} feature="summary" unit="summary pages" />{SUMMARY_OPTIONS.map(o => <ChoiceCard key={o.pages} disabled={!canGenerate(usage, 'summary', o.pages)} selected={maxPages === o.pages} title={o.label} description={o.description} onClick={() => setMaxPages(o.pages)} />)}<div style={{ color: C.text, fontWeight: 800, fontSize: 12, margin: '17px 0 9px' }}>Style</div>{[['concise', 'Concise', 'High-signal revision notes.'], ['balanced', 'Balanced', 'Clear explanation without unnecessary length.'], ['exam_focus', 'Exam focus', 'Prioritises examinable concepts and recall points.']].map(([v, label, description]) => <ChoiceCard key={v} selected={style === v} title={label} description={description} onClick={() => setStyle(v)} />)}<GenerateButton disabled={!csrf || !canGenerate(usage, 'summary', maxPages)} onClick={generate}>Generate {maxPages}-page summary</GenerateButton></div></div>
}
