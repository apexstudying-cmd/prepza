import { useEffect, useRef, useState, type ComponentType, type ReactNode } from 'react'

import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import type { SponsoredCampaign } from '../../types/opportunities'
import { Ic } from '../../ui/icons'
import Pill from '../../ui/Pill'

type PodcastAudioStatus = {
  audio_status: string
  audio_url: string | null
  duration_seconds: number | null
  progress_percent?: number
  progress_stage?: string
}

type GenerationProgress = { progress_percent: number; progress_stage: string; status: string }
type PodcastPlayerScreenProps = {
  setScreen: (screen: 'document-study') => void
  activeDocumentId: number | null
  setActiveOpportunityId: (id: number | null) => void
  generationRequest: <T = any>(
    path: string,
    options?: RequestInit,
    onProgress?: (progress: GenerationProgress) => void,
    currentUserId?: number,
  ) => Promise<T>
  cacheReadyPodcastOffline: (
    documentId: number | null,
    materialId: number | null,
    path: string,
    status: PodcastAudioStatus,
  ) => void
  getCachedPodcastAudio: (path: string) => Promise<{ audioUrl: string | null; duration: number }>
  TopBar: ComponentType<{ title?: string; onBack?: () => void }>
  GenerationError: ComponentType<{ error: string }>
  renderSponsoredOpportunities: (campaigns: SponsoredCampaign[]) => ReactNode
}

export default function PodcastPlayerScreen({ setScreen, activeDocumentId, setActiveOpportunityId, generationRequest, cacheReadyPodcastOffline, getCachedPodcastAudio, TopBar, GenerationError, renderSponsoredOpportunities }: PodcastPlayerScreenProps) {
  const { tokens: T } = useTheme()
  const audioRef = useRef<HTMLAudioElement>(null)
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState(0)
  const [speed, setSpeed] = useState(1)
  const [stage, setStage] = useState<'loading' | 'audio' | 'ready'>('loading')
  const [title, setTitle] = useState('Study Podcast')
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [generationPercent, setGenerationPercent] = useState(0)
  const [generationStage, setGenerationStage] = useState('Preparing your podcast…')
  const [heartbeatCsrf, setHeartbeatCsrf] = useState('')
  const [playerOpportunities, setPlayerOpportunities] = useState<SponsoredCampaign[]>([])
  const [playerOppIndex, setPlayerOppIndex] = useState(0)

  useEffect(() => {
    if (stage !== 'ready') return
    let cancelled = false
    api<{ campaigns: SponsoredCampaign[] }>('/api/discovery/feed?placement=podcast')
      .then(res => {
        if (!cancelled) {
          setPlayerOpportunities(res.campaigns || [])
          setPlayerOppIndex(0)
        }
      })
      .catch(() => { if (!cancelled) setPlayerOpportunities([]) })
    return () => { cancelled = true }
  }, [stage])

  const positionKey = activeDocumentId == null ? '' : `prepza-podcast-position:${activeDocumentId}`
  const selectedPodcastMaterialId = (() => {
    try {
      const raw = sessionStorage.getItem('prepza-open-material')
      const selected = raw ? JSON.parse(raw) : null
      return selected && String(selected.documentId) === String(activeDocumentId) && selected.type === 'podcast' && Number(selected.materialId) > 0
        ? Number(selected.materialId)
        : null
    } catch { return null }
  })()
  const podcastAudioPath = selectedPodcastMaterialId
    ? `/documents/${activeDocumentId}/podcast-audio?material_id=${selectedPodcastMaterialId}`
    : `/documents/${activeDocumentId}/podcast-audio`

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setHeartbeatCsrf(me.csrf_token)).catch(() => {})
  }, [])

  useEffect(() => {
    if (!playing || !heartbeatCsrf) return
    const ping = () => {
      if (document.visibilityState !== 'visible') return
      api('/study-time/heartbeat', {
        method: 'POST',
        headers: { 'X-CSRF-Token': heartbeatCsrf },
        body: JSON.stringify({ feature: 'podcast', document_id: activeDocumentId }),
      }).catch(() => {})
    }
    ping()
    const interval = setInterval(ping, 20000)
    return () => clearInterval(interval)
  }, [playing, heartbeatCsrf, activeDocumentId])

  useEffect(() => {
    if (activeDocumentId == null) { setError('No document selected.'); return }
    let cancelled = false
    const run = async () => {
      try {
        const existing = await api<{ audio_status: string; audio_url: string | null; duration_seconds: number | null; progress_percent?: number; progress_stage?: string }>(podcastAudioPath)
        if (cancelled) return
        if (existing.audio_status === 'ready' && existing.audio_url) {
          cacheReadyPodcastOffline(activeDocumentId, selectedPodcastMaterialId, podcastAudioPath, existing)
          setAudioUrl(existing.audio_url)
          setDuration(existing.duration_seconds || 0)
          setGenerationPercent(100)
          setGenerationStage('ready')
          setStage('ready')
          try { if (selectedPodcastMaterialId) sessionStorage.removeItem('prepza-open-material') } catch {}
          return
        }
        if (existing.audio_status === 'processing') {
          setGenerationPercent(Number(existing.progress_percent || 0))
          setGenerationStage(existing.progress_stage || 'Generating audio…')
          setStage('audio')
          const pollExisting = async () => {
            if (cancelled) return
            const status = await api<{ audio_status: string; audio_url: string | null; duration_seconds: number | null; progress_percent?: number; progress_stage?: string }>(podcastAudioPath)
            if (cancelled) return
            setGenerationPercent(Math.max(0, Math.min(100, Number(status.progress_percent || 0))))
            setGenerationStage(status.progress_stage || 'Generating audio…')
            if (status.audio_status === 'ready' && status.audio_url) {
              cacheReadyPodcastOffline(activeDocumentId, selectedPodcastMaterialId, podcastAudioPath, status)
              setAudioUrl(status.audio_url)
              setDuration(status.duration_seconds || 0)
              setGenerationPercent(100)
              setGenerationStage('ready')
              setStage('ready')
            } else if (status.audio_status === 'failed') {
              setError('Audio generation failed. Try again from the document study hub.')
            } else {
              setTimeout(pollExisting, 2500)
            }
          }
          await pollExisting()
          return
        }

        const me = await api<{ id: number; csrf_token: string }>('/me')
        if (cancelled) return
        setGenerationPercent(2)
        setGenerationStage('Generating podcast script…')
        const scriptRes = await generationRequest<{ material_id: number; reused: boolean; podcast: any }>(`/documents/${activeDocumentId}/podcast-script`, {
          method: 'POST', headers: { 'X-CSRF-Token': me.csrf_token },
        }, (p) => { setGenerationPercent(p.progress_percent); setGenerationStage(p.progress_stage) }, me.id)
        if (scriptRes.podcast?.title) setTitle(scriptRes.podcast.title)
        if (cancelled) return
        setGenerationPercent(5)
        setGenerationStage('Generating audio…')
        setStage('audio')

        await api(podcastAudioPath, {
          method: 'POST', headers: { 'X-CSRF-Token': me.csrf_token },
        })

        const poll = async () => {
          if (cancelled) return
          const status = await api<{ audio_status: string; audio_url: string | null; duration_seconds: number | null; progress_percent?: number; progress_stage?: string }>(podcastAudioPath)
          if (cancelled) return
          setGenerationPercent(Math.max(0, Math.min(100, Number(status.progress_percent || 0))))
          setGenerationStage(status.progress_stage || 'Generating audio…')
          if (status.audio_status === 'ready' && status.audio_url) {
            cacheReadyPodcastOffline(activeDocumentId, selectedPodcastMaterialId, podcastAudioPath, status)
            setAudioUrl(status.audio_url)
            setDuration(status.duration_seconds || 0)
            setGenerationPercent(100)
            setGenerationStage('ready')
            setStage('ready')
            try { if (selectedPodcastMaterialId) sessionStorage.removeItem('prepza-open-material') } catch {}
          } else if (status.audio_status === 'failed') {
            setError('Audio generation failed. Try again from the document study hub.')
          } else {
            setTimeout(poll, 2500)
          }
        }
        await poll()
      } catch (e) {
        if (cancelled) return
        const cachedAudio = await getCachedPodcastAudio(podcastAudioPath)
        const localAudioUrl = cachedAudio.audioUrl
        if (localAudioUrl) {
          setAudioUrl(localAudioUrl)
          setDuration(cachedAudio.duration)
          setStage('ready')
          return
        }
        setError(e instanceof ApiError ? e.message : 'Could not open this podcast.')
      }
    }
    void run()
    return () => { cancelled = true }
  }, [activeDocumentId])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !audioUrl) return
    const saved = positionKey ? Number(localStorage.getItem(positionKey) || 0) : 0
    const restore = () => {
      if (Number.isFinite(saved) && saved > 0 && saved < (audio.duration || Infinity)) audio.currentTime = saved
    }
    const onTime = () => {
      setProgress(audio.currentTime)
      if (positionKey) localStorage.setItem(positionKey, String(Math.floor(audio.currentTime)))
    }
    const onPlay = () => setPlaying(true)
    const onPause = () => setPlaying(false)
    const onEnded = () => {
      setPlaying(false)
      if (positionKey) localStorage.removeItem(positionKey)
    }
    audio.addEventListener('loadedmetadata', restore)
    audio.addEventListener('timeupdate', onTime)
    audio.addEventListener('play', onPlay)
    audio.addEventListener('pause', onPause)
    audio.addEventListener('ended', onEnded)
    return () => {
      audio.removeEventListener('loadedmetadata', restore)
      audio.removeEventListener('timeupdate', onTime)
      audio.removeEventListener('play', onPlay)
      audio.removeEventListener('pause', onPause)
      audio.removeEventListener('ended', onEnded)
    }
  }, [audioUrl, positionKey])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    audio.playbackRate = speed
  }, [speed, audioUrl])

  useEffect(() => {
    const media = navigator.mediaSession
    if (!media || !audioUrl) return
    media.metadata = new MediaMetadata({ title, artist: 'Prepza', album: 'Prepza Study Podcast' })
    media.setActionHandler('play', () => { void audioRef.current?.play() })
    media.setActionHandler('pause', () => audioRef.current?.pause())
    media.setActionHandler('seekbackward', () => seek(-15))
    media.setActionHandler('seekforward', () => seek(15))
    media.setActionHandler('stop', () => {
      const audio = audioRef.current
      if (audio) { audio.pause(); audio.currentTime = 0 }
      setPlaying(false)
    })
    return () => {
      for (const action of ['play','pause','seekbackward','seekforward','stop'] as MediaSessionAction[]) {
        try { media.setActionHandler(action, null) } catch {}
      }
    }
  }, [audioUrl, title])

  const togglePlay = async () => {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) await audio.play()
    else audio.pause()
  }

  function seek(delta: number) {
    const audio = audioRef.current
    if (!audio) return
    audio.currentTime = Math.max(0, Math.min(audio.duration || duration, audio.currentTime + delta))
    setProgress(audio.currentTime)
  }

  const cycleSpeed = () => {
    const values = [0.5, 0.75, 1, 1.25, 1.5, 2]
    setSpeed(values[(values.indexOf(speed) + 1) % values.length])
  }

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 20px' }}><TopBar title="Study Podcast" onBack={() => setScreen('document-study')} /></div>
      {error ? <GenerationError error={error} /> : stage !== 'ready' ? (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 28 }}>
          <div style={{ width: '100%', maxWidth: 380, background: T.card, borderRadius: 22, padding: 24, boxShadow: '0 8px 30px rgba(0,0,0,0.07)' }}>
            <div style={{ color: N.gold, fontSize: 10, fontWeight: 900, letterSpacing: 1, textTransform: 'uppercase' }}>Prepza Podcast</div>
            <div style={{ color: T.text, fontSize: 19, fontWeight: 800, marginTop: 8 }}>{stage === 'loading' ? 'Opening your podcast' : 'Generating your podcast'}</div>
            <div style={{ color: T.textMuted, fontSize: 12, lineHeight: 1.55, marginTop: 5 }}>{generationStage}</div>
            <div style={{ height: 9, background: T.border, borderRadius: 99, overflow: 'hidden', marginTop: 22 }}>
              <div style={{ width: `${generationPercent}%`, height: '100%', background: `linear-gradient(90deg,${N.gold},${N.goldL})`, transition: 'width .5s ease' }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, color: T.textMuted, fontSize: 11 }}>
              <span>{generationPercent}%</span>
              <span>{stage === 'loading' ? 'Checking saved material' : 'Please keep this screen open or enable notifications'}</span>
            </div>
          </div>
        </div>
      ) : (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '32px 28px', gap: 24 }}>
          {audioUrl && <audio ref={audioRef} src={audioUrl} preload="metadata" />}
          {playerOpportunities.length > 0 && (
            <section style={{ width: '100%', maxWidth: 520 }}>
              <div style={{ fontSize: 9, fontWeight: 900, letterSpacing: 0.8, color: T.textMuted, marginBottom: 8 }}>OPPORTUNITIES</div>
              <div style={{ display: 'flex', gap: 10, overflowX: 'auto', paddingBottom: 3 }} className="scrollbar-hide">
                {renderSponsoredOpportunities(playerOpportunities.slice(0, 2))}
              </div>
            </section>
          )}
          <div style={{ width: 200, height: 200, borderRadius: 28, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: `0 16px 48px rgba(201,168,76,0.35)`, fontSize: 28, fontWeight: 900, color: N.navy, fontFamily: 'Plus Jakarta Sans' }}>PREPZA</div>
          <div style={{ textAlign: 'center' }}><div style={{ fontWeight: 800, fontSize: 20, color: T.text, marginBottom: 4 }}>{title}</div><Pill text="AI Generated" color={N.gold} /></div>
          <div style={{ width: '100%' }}>
            <input aria-label="Podcast progress" type="range" min={0} max={duration || 1} step={0.5} value={progress} onChange={e => { const v = +e.target.value; setProgress(v); if (audioRef.current) audioRef.current.currentTime = v }} style={{ width: '100%', accentColor: N.gold, cursor: 'pointer' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: T.textMuted, marginTop: 4 }}><span>{fmt(progress)}</span><span>{fmt(duration)}</span></div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 26 }}>
            <button aria-label="Rewind 15 seconds" onClick={() => seek(-15)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.text }}>{Ic.rewind()}</button>
            <button aria-label={playing ? 'Pause' : 'Play'} onClick={togglePlay} style={{ width: 64, height: 64, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: '50%', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: `0 6px 20px rgba(201,168,76,0.4)` }}><div style={{ color: T.text }}>{playing ? Ic.pause() : Ic.play()}</div></button>
            <button aria-label="Forward 15 seconds" onClick={() => seek(15)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.text }}>{Ic.skip()}</button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button onClick={cycleSpeed} style={{ border: `1px solid ${T.border}`, background: T.card, color: T.text, borderRadius: 10, padding: '7px 12px', fontSize: 12, fontWeight: 800, cursor: 'pointer' }}>{speed}×</button>
            <span style={{ fontSize: 11, color: T.textMuted }}>Speed</span>
          </div>
        </div>
      )}
    </div>
  )
}
