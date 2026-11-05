import { useEffect, useRef, useState, type ComponentType, type ReactNode } from 'react'

import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'

type TutorMsg = { id: number | string; role: 'user' | 'assistant'; content: string }

type PickableDoc = { id: number; title: string; status: string }

// Stale-while-revalidate cache keyed by document ID: reopening the AI tutor
// for a document already visited this session renders instantly while a
// fresh fetch runs quietly in the background.
const AI_TUTOR_CACHE: Record<number, TutorMsg[]> = {}

type AITutorScreenProps = {
  setScreen: (screen: 'home' | 'upload') => void
  activeDocumentId: number | null
  setActiveDocumentId: (id: number | null) => void
  GenerationError: ComponentType<{ error: string }>
  DelayedScreenSkeleton: ComponentType<{ children: ReactNode }>
  SkeletonAITutor: ComponentType
}

export default function AITutorScreen({ setScreen, activeDocumentId, setActiveDocumentId, GenerationError, DelayedScreenSkeleton, SkeletonAITutor }: AITutorScreenProps) {
  const { tokens: T } = useTheme()
  const [messages, setMessages] = useState<TutorMsg[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState('')
  const [voiceMode, setVoiceMode] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const [pickerDocs, setPickerDocs] = useState<PickableDoc[]>([])
  const [pickerLoading, setPickerLoading] = useState(false)
  const [pickerError, setPickerError] = useState('')

  useEffect(() => {
    if (activeDocumentId != null) return
    setPickerLoading(true)
    api<{ documents: PickableDoc[] }>('/documents')
      .then(res => setPickerDocs(res.documents.filter(d => d.status === 'ready')))
      .catch(e => setPickerError(e instanceof ApiError ? e.message : 'Could not load your documents.'))
      .finally(() => setPickerLoading(false))
  }, [activeDocumentId])

  useEffect(() => {
    if (activeDocumentId == null) { setLoading(false); return }
    const cached = AI_TUTOR_CACHE[activeDocumentId]
    if (cached) { setMessages(cached); setLoading(false) } else { setLoading(true) }
    api<{ csrf_token: string }>('/me')
      .then(me => {
        setCsrfToken(me.csrf_token)
        return api<{ conversation_id: number | null; messages: TutorMsg[] }>(`/documents/${activeDocumentId}/tutor`)
      })
      .then(res => { setMessages(res.messages); AI_TUTOR_CACHE[activeDocumentId] = res.messages })
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load this conversation.'))
      .finally(() => setLoading(false))
  }, [activeDocumentId])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages, sending])

  useEffect(() => {
    if (activeDocumentId == null || loading || error || !csrfToken) return
    const ping = () => {
      if (document.visibilityState !== 'visible') return
      api('/study-time/heartbeat', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ feature: 'tutor_chat' }),
      }).catch(() => {})
    }
    const interval = setInterval(ping, 20000)
    return () => clearInterval(interval)
  }, [activeDocumentId, loading, error, csrfToken])

  const send = async () => {
    if (!input.trim() || sending || activeDocumentId == null) return
    const body = input; setInput(''); setSendError('')
    setMessages(m => [...m, { id: `local-${Date.now()}`, role: 'user', content: body }])
    setSending(true)
    try {
      const res = await api<{ reply: TutorMsg }>(`/documents/${activeDocumentId}/tutor/messages`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ body }),
      })
      setMessages(m => [...m, res.reply])
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) setSendError("You've hit the hourly message limit - try again later.")
      else if (e instanceof ApiError && e.status === 503) setSendError('AI budget exceeded for now - try again later.')
      else setSendError(e instanceof ApiError ? e.message : 'Could not send that message. Please try again.')
    } finally {
      setSending(false)
    }
  }

  if (activeDocumentId == null) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
        <div style={{ background: N.navy, padding: '0 18px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <div style={{ width: 38, height: 38, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>✦</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>Morio</div>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', fontWeight: 600 }}>Pick a document to start</div>
            </div>
          </div>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
          {pickerLoading && <div style={{ textAlign: 'center', color: T.textMuted, fontSize: 13, marginTop: 24 }}>Loading your documents…</div>}
          {pickerError && <GenerationError error={pickerError} />}
          {!pickerLoading && !pickerError && pickerDocs.length === 0 && (
            <div style={{ textAlign: 'center', padding: '32px 20px' }}>
              <div style={{ fontSize: 13, color: T.textMuted, marginBottom: 14 }}>You don't have any documents ready yet. Upload one to start asking Morio questions.</div>
              <button onClick={() => setScreen('upload')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 13, border: 'none', borderRadius: 14, padding: '12px 20px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Upload a Document</button>
            </div>
          )}
          {!pickerLoading && !pickerError && pickerDocs.map(d => (
            <div key={d.id} onClick={() => setActiveDocumentId(d.id)} style={{ background: T.card, borderRadius: 14, padding: '12px 14px', marginBottom: 8, boxShadow: '0 2px 10px rgba(0,0,0,0.05)', display: 'flex', gap: 12, alignItems: 'center', cursor: 'pointer', border: '1px solid rgba(0,0,0,0.04)' }}>
              <div style={{ width: 38, height: 38, background: 'rgba(201,168,76,0.12)', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, flexShrink: 0 }}>📄</div>
              <div style={{ fontWeight: 700, fontSize: 13, color: T.text }} className="line-clamp-1">{d.title}</div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (loading) return <DelayedScreenSkeleton><SkeletonAITutor /></DelayedScreenSkeleton>
  if (error) return <GenerationError error={error} />

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ width: 38, height: 38, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>✦</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>Morio</div>
            <div style={{ fontSize: 11, color: '#4CC97B', fontWeight: 600 }}>● Online · Ready to help</div>
          </div>
        </div>
        {/* Quick actions */}
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto' }} className="scrollbar-hide">
          {['Explain','Quiz Me','Summarize','Flashcards','Podcast'].map(a => (
            <button key={a} onClick={() => { setInput(a + ' '); }} style={{ flexShrink: 0, padding: '6px 12px', borderRadius: 20, background: `rgba(201,168,76,0.12)`, border: `1px solid ${N.gold}30`, color: N.gold, fontWeight: 700, fontSize: 11, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{a}</button>
          ))}
        </div>
      </div>

      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: 14 }} className="scrollbar-hide">
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', color: T.textMuted, fontSize: 13, marginTop: 40 }}>Ask me anything about this document to get started.</div>
        )}
        {messages.map((m) => (
          <div key={m.id} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', gap: 10, alignItems: 'flex-start' }}>
            {m.role === 'assistant' && <div style={{ width: 32, height: 32, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, flexShrink: 0 }}>✦</div>}
            <div style={{ maxWidth: '80%', background: m.role === 'user' ? `linear-gradient(135deg,${N.navy},${N.navy3})` : '#fff', borderRadius: m.role === 'user' ? '14px 0 14px 14px' : '0 14px 14px 14px', padding: '12px 14px', boxShadow: '0 2px 8px rgba(0,0,0,0.07)' }}>
              <div style={{ fontSize: 13, color: m.role === 'user' ? '#fff' : T.text, lineHeight: 1.75, whiteSpace: 'pre-line' }}>{m.content}</div>
            </div>
          </div>
        ))}
        {sending && (
          <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <div style={{ width: 32, height: 32, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, flexShrink: 0 }}>✦</div>
            <div style={{ background: T.card, borderRadius: '0 14px 14px 14px', padding: '12px 14px', boxShadow: '0 2px 8px rgba(0,0,0,0.07)' }}>
              <div style={{ fontSize: 13, color: T.textMuted }}>Thinking…</div>
            </div>
          </div>
        )}
      </div>

      {sendError && (
        <div style={{ margin: '0 16px 8px', fontSize: 12, color: '#C94C4C', fontWeight: 600 }}>{sendError}</div>
      )}

      {voiceMode && (
        <div style={{ margin: '0 16px 8px', background: `linear-gradient(135deg,${N.navy},${N.navy3})`, borderRadius: 16, padding: 16, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 56, height: 56, background: `rgba(201,168,76,0.2)`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', border: `2px solid ${N.gold}`, animation: 'pulse-gold 1.5s infinite' }}>
            <div style={{ color: N.gold }}>{Ic.mic()}</div>
          </div>
          <div style={{ color: '#fff', fontSize: 13, fontWeight: 600 }}>Listening…</div>
          <button onClick={() => setVoiceMode(false)} style={{ background: 'rgba(255,255,255,0.1)', border: 'none', color: '#fff', fontSize: 12, fontWeight: 600, borderRadius: 10, padding: '7px 20px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Cancel</button>
        </div>
      )}

      <div style={{ padding: '10px 14px 14px', background: T.card, borderTop: '1px solid rgba(0,0,0,0.06)' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', background: T.pageBg, borderRadius: 14, padding: '8px 12px', border: '1px solid rgba(11,20,55,0.08)' }}>
          <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} disabled={sending} placeholder="Ask your AI tutor anything…" style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 13, color: T.text, fontFamily: 'Plus Jakarta Sans' }} />
          <button onClick={() => setVoiceMode(v => !v)} style={{ width: 32, height: 32, background: voiceMode ? `rgba(201,168,76,0.2)` : '#F3F4F6', border: 'none', borderRadius: 9, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: voiceMode ? N.gold : T.textMuted }}>{Ic.mic('w-4 h-4')}</div>
          </button>
          <button onClick={send} disabled={sending || !input.trim()} style={{ width: 32, height: 32, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 9, cursor: sending ? 'default' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: sending || !input.trim() ? 0.5 : 1 }}>
            <div style={{ color: T.text }}>{Ic.send('w-4 h-4')}</div>
          </button>
        </div>
      </div>
    </div>
  )
}
