import { useEffect, useRef, useState } from 'react'

type Attachment = { id: number; file_type: string; original_filename: string; file_size_bytes: number; view_url: string | null }
type Message = { id: number; conversation_id: number; sender_id: number; body: string | null; is_deleted: boolean; created_at: string | null; edited_at: string | null; attachment: Attachment | null }
type Participant = { user_id: number; display_name: string; role: string }
type Detail = { id: number; is_group: boolean; name: string; created_by: number; member_count: number; participants: Participant[] }

let observedConversationId: number | null = null
let observedAt = 0
let observerInstalled = false
let dismissedConversationId: number | null = null
let dismissedAt = 0

function pathOf(input: RequestInfo | URL): string {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.pathname + input.search : input.url
  try { return new URL(raw, window.location.origin).pathname } catch { return raw.split('?')[0] }
}

function installConversationObserver() {
  if (observerInstalled || typeof window === 'undefined') return
  observerInstalled = true
  const original = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const path = pathOf(input)
    const match = path.match(/^\/chats\/(\d+)\/(?:messages|read)$/)
    const detail = path.match(/^\/chats\/(\d+)$/)
    if (match || detail) {
      const id = Number((match || detail)![1])
      const recentlyDismissed = dismissedConversationId === id && Date.now() - dismissedAt < 1500
      if (!recentlyDismissed) {
        observedConversationId = id
        observedAt = Date.now()
      }
    }
    return original(input, init)
  }
}

function friendlyError(value: unknown, fallback: string) {
  const message = value instanceof Error ? value.message : ''
  if (!message) return fallback
  if (/peer encryption key|secure conversation|public key|nonce|e2ee|encrypted/i.test(message)) return 'Secure messaging is temporarily unavailable. Please try again.'
  if (/authentication|required|unauthorized|forbidden|401|403/i.test(message)) return 'Your session has expired. Please sign in again.'
  if (/network|failed to fetch|request failed/i.test(message)) return 'Connection problem. Please try again.'
  return message.length > 140 ? fallback : message
}

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { credentials: 'include', ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } })
  let body: any = null
  try { body = await response.json() } catch { /* empty */ }
  if (!response.ok) throw new Error(body?.error || `Request failed (${response.status})`)
  return body as T
}

function timeLabel(value: string | null) {
  return value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''
}

function initials(name: string) { return (name || '??').slice(0, 2).toUpperCase() }

export default function WhatsAppChatExperience() {
  const [active, setActive] = useState(false)
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [meId, setMeId] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [attachOpen, setAttachOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    installConversationObserver()
    let cancelled = false
    const sync = () => {
      const composer = document.querySelector('input[placeholder="Message…"]')
      const id = observedConversationId
      const isFresh = Date.now() - observedAt < 10000
      const suppressed = dismissedConversationId === id && Date.now() - dismissedAt < 1500
      const nextActive = Boolean(composer && id && isFresh && !suppressed)
      if (!nextActive) {
        if (!cancelled) setActive(false)
        return
      }
      if (!cancelled) {
        setActive(true)
        if (conversationId !== id) setConversationId(id)
      }
    }
    const timer = window.setInterval(sync, 350)
    sync()
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [conversationId])

  useEffect(() => {
    if (!active || conversationId == null) return
    let cancelled = false
    setLoading(true); setError('')
    Promise.all([
      api<Detail>(`/chats/${conversationId}`),
      api<{ messages: Message[] }>(`/chats/${conversationId}/messages`),
      api<{ id: number }>('/me'),
    ]).then(([nextDetail, nextMessages, me]) => {
      if (cancelled) return
      setDetail(nextDetail); setMessages(nextMessages.messages || []); setMeId(me.id)
    }).catch(errorValue => { if (!cancelled) setError(friendlyError(errorValue, 'Could not load this chat.')) })
      .finally(() => { if (!cancelled) setLoading(false) })

    const interval = window.setInterval(async () => {
      try {
        const data = await api<{ messages: Message[] }>(`/chats/${conversationId}/messages`)
        if (!cancelled) setMessages(data.messages || [])
      } catch { /* keep current messages */ }
    }, 3000)
    return () => { cancelled = true; window.clearInterval(interval) }
  }, [active, conversationId])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages.length])

  const send = async () => {
    const body = input.trim()
    if (!body || sending || conversationId == null) return
    setSending(true); setError('')
    try {
      const message = await api<Message>(`/chats/${conversationId}/messages`, { method: 'POST', body: JSON.stringify({ body }) })
      setMessages(current => [...current.filter(m => m.id !== message.id), message])
      setInput('')
    } catch (errorValue) { setError(friendlyError(errorValue, 'Could not send this message.')) }
    finally { setSending(false) }
  }

  const sendAttachment = async (file: File) => {
    if (conversationId == null || uploading) return
    if (file.size > 20 * 1024 * 1024) { setError('That file is too large. The limit is 20 MB.'); return }
    setUploading(true); setError(''); setAttachOpen(false)
    try {
      const init = await api<{ attachment_id: number; upload_url: string }>(`/chats/${conversationId}/attachments`, { method: 'POST', body: JSON.stringify({ original_filename: file.name, file_size_bytes: file.size }) })
      const upload = await fetch(init.upload_url, { method: 'PUT', body: file })
      if (!upload.ok) throw new Error('Upload failed')
      await api(`/chats/${conversationId}/attachments/${init.attachment_id}/uploaded`, { method: 'POST' })
      const message = await api<Message>(`/chats/${conversationId}/messages`, { method: 'POST', body: JSON.stringify({ attachment_id: init.attachment_id }) })
      setMessages(current => [...current.filter(m => m.id !== message.id), message])
    } catch (errorValue) { setError(friendlyError(errorValue, 'Could not send this attachment.')) }
    finally { setUploading(false) }
  }

  const openAda = () => window.dispatchEvent(new CustomEvent('prepza-open-ada', { detail: { conversationId } }))
  const closeChat = () => {
    if (conversationId != null) {
      dismissedConversationId = conversationId
      dismissedAt = Date.now()
    }
    setActive(false)
    document.querySelector('input[placeholder="Message…"]')?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  }

  if (!active) return null

  const name = detail?.name || 'Conversation'
  const group = Boolean(detail?.is_group)
  const other = detail?.participants?.find(p => p.user_id !== meId)
  const header = group ? name : (other?.display_name || name)

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', flexDirection: 'column', background: '#F4F5F7', fontFamily: 'Plus Jakarta Sans, sans-serif' }}>
      <header style={{ height: 66, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 11, padding: '0 14px', background: '#0B1437', color: '#fff', boxShadow: '0 1px 8px rgba(0,0,0,.12)' }}>
        <button type="button" aria-label="Back" onClick={closeChat} style={{ width: 38, height: 38, border: 0, borderRadius: 12, background: 'rgba(255,255,255,.09)', color: '#fff', cursor: 'pointer', fontSize: 22 }}>‹</button>
        <div style={{ width: 40, height: 40, borderRadius: 14, background: 'linear-gradient(135deg,#C9A84C,#E4C96A)', color: '#0B1437', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900 }}>{initials(header)}</div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 850, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{header}</div>
          <div style={{ fontSize: 10, opacity: .65 }}>{group ? `${detail?.member_count || 0} members` : 'online'}</div>
        </div>
        <div title="Messages are encrypted on your device" style={{ fontSize: 11, opacity: .7 }}>●</div>
        <button type="button" aria-label="Study with Ada" onClick={openAda} style={{ border: '1px solid rgba(201,168,76,.45)', background: 'rgba(201,168,76,.12)', color: '#E4C96A', borderRadius: 12, padding: '8px 10px', fontWeight: 850, fontSize: 11, cursor: 'pointer' }}>@Ada</button>
      </header>

      <main style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '18px max(14px, calc((100vw - 760px)/2)) 14px', background: 'linear-gradient(180deg,#EEF0F3 0%,#F7F7F5 100%)' }}>
        {loading && messages.length === 0 && <div style={{ textAlign: 'center', padding: 30, color: '#7B8190', fontSize: 12 }}>Loading…</div>}
        {error && <div style={{ margin: '0 auto 10px', maxWidth: 620, padding: '9px 12px', borderRadius: 12, background: '#fff', color: '#A33A35', fontSize: 11, boxShadow: '0 2px 10px rgba(0,0,0,.05)' }}>{error}</div>}
        {messages.map(message => {
          const mine = message.sender_id === meId
          const sender = detail?.participants?.find(p => p.user_id === message.sender_id)?.display_name || 'Student'
          return <div key={message.id} style={{ display: 'flex', flexDirection: 'column', alignItems: mine ? 'flex-end' : 'flex-start', marginBottom: 8 }}>
            {group && !mine && <div style={{ fontSize: 10, color: '#8A6B20', fontWeight: 800, margin: '0 10px 3px' }}>{sender}</div>}
            <div style={{ maxWidth: 'min(76%, 560px)', padding: '9px 11px 7px', borderRadius: mine ? '15px 4px 15px 15px' : '4px 15px 15px 15px', background: mine ? '#0B1437' : '#fff', color: mine ? '#fff' : '#202534', boxShadow: '0 2px 7px rgba(0,0,0,.07)' }}>
              {message.attachment && <div style={{ borderRadius: 11, background: mine ? 'rgba(255,255,255,.09)' : '#F4F5F7', padding: 9, marginBottom: message.body ? 7 : 0 }}>
                <div style={{ fontSize: 12, fontWeight: 800, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{message.attachment.original_filename}</div>
                <div style={{ fontSize: 10, opacity: .58, marginTop: 3 }}>{(message.attachment.file_size_bytes / 1048576).toFixed(1)} MB · tap to study</div>
                {message.attachment.view_url && <a href={message.attachment.view_url} target="_blank" rel="noreferrer" style={{ display: 'inline-block', marginTop: 7, color: mine ? '#E4C96A' : '#8A6B20', fontSize: 10, fontWeight: 800 }}>Open document</a>}
              </div>}
              {message.is_deleted ? <i style={{ opacity: .55, fontSize: 12 }}>This message was deleted</i> : message.body && <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.5 }}>{message.body}</div>}
              <div style={{ marginTop: 3, textAlign: 'right', fontSize: 9, opacity: .45 }}>{timeLabel(message.created_at)}</div>
            </div>
          </div>
        })}
        <div ref={bottomRef} />
      </main>

      <footer style={{ flexShrink: 0, padding: '9px max(10px, calc((100vw - 760px)/2)) 12px', background: '#fff', borderTop: '1px solid #E4E6EA' }}>
        {attachOpen && <div style={{ display: 'flex', gap: 8, padding: '0 0 9px' }}>
          <button type="button" onClick={() => fileRef.current?.click()} style={{ border: 0, borderRadius: 12, background: '#F1F2F4', padding: '9px 12px', fontWeight: 800, fontSize: 11, cursor: 'pointer' }}>Document</button>
          <button type="button" onClick={() => { fileRef.current?.click() }} style={{ border: 0, borderRadius: 12, background: '#F1F2F4', padding: '9px 12px', fontWeight: 800, fontSize: 11, cursor: 'pointer' }}>Image</button>
        </div>}
        <input ref={fileRef} type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png" style={{ display: 'none' }} onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void sendAttachment(file) }} />
        <div style={{ maxWidth: 760, margin: '0 auto', display: 'flex', alignItems: 'flex-end', gap: 7 }}>
          <button type="button" onClick={() => setAttachOpen(v => !v)} disabled={uploading} aria-label="Attach" style={{ width: 40, height: 40, flexShrink: 0, border: 0, borderRadius: 13, background: '#F0F1F3', color: '#5E6470', fontSize: 20, cursor: 'pointer' }}>+</button>
          <button type="button" onClick={openAda} aria-label="Ask Ada" style={{ height: 40, flexShrink: 0, border: '1px solid #DCC67D', borderRadius: 13, background: '#FFF9E9', color: '#72570E', padding: '0 11px', fontWeight: 900, fontSize: 11, cursor: 'pointer' }}>@Ada</button>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', background: '#F3F4F6', border: '1px solid #E5E7EB', borderRadius: 15, padding: '0 12px' }}>
            <input value={input} onChange={event => setInput(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void send() } }} placeholder="Message…" disabled={sending || uploading} style={{ width: '100%', height: 42, border: 0, outline: 0, background: 'transparent', fontFamily: 'inherit', fontSize: 13 }} />
          </div>
          <button type="button" onClick={() => void send()} disabled={sending || uploading || !input.trim()} aria-label="Send" style={{ width: 40, height: 40, flexShrink: 0, border: 0, borderRadius: 13, background: input.trim() ? '#C9A84C' : '#E7E8EA', color: '#0B1437', fontWeight: 900, cursor: input.trim() ? 'pointer' : 'default' }}>➤</button>
        </div>
      </footer>
    </div>
  )
}
