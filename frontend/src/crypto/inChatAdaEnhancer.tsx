import { useEffect, useMemo, useState } from 'react'
import { createAdaStudyContext } from './studyAdaContext'
import { askAdaAboutSelectedStudyContext, type AdaStudyResponse } from './studyAdaApi'

type ChatState = { conversationId: number; keyEpoch: number }
type SharedDocument = { attachmentId: number; filename: string; mimeType: string; conversationId: number }

let installed = false
let activeChat: ChatState | null = null
let lastTrafficAt = 0
const listeners = new Set<(state: ChatState | null) => void>()
const ADA_MENTION_RE = /(^|\s)@ada\b/i

function emit(state: ChatState | null) { activeChat = state; listeners.forEach(listener => listener(state)) }
function pathOf(input: RequestInfo | URL): string {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.pathname : input.url
  try { return new URL(raw, window.location.origin).pathname } catch { return raw.split('?')[0] }
}
function attachmentFromMessage(conversationId: number, message: any): SharedDocument | null {
  const attachment = message?.attachment
  const id = Number(attachment?.id ?? attachment?.attachment_id)
  const filename = String(attachment?.original_filename || attachment?.filename || '').trim()
  if (!Number.isInteger(id) || id < 1 || !filename) return null
  return { attachmentId: id, filename, mimeType: String(attachment?.mime_type || attachment?.file_type || 'application/octet-stream'), conversationId }
}

export function installInChatAdaObserver(): void {
  if (installed || typeof window === 'undefined' || !window.fetch) return
  installed = true
  const original = window.fetch.bind(window)
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const response = await original(input, init)
    const path = pathOf(input)
    const match = path.match(/^\/chats\/(\d+)(?:\/messages)?$/)
    if (match) {
      const conversationId = Number(match[1])
      lastTrafficAt = Date.now()
      response.clone().json().then((body: any) => {
        if (path.endsWith('/messages')) {
          if (!activeChat || activeChat.conversationId !== conversationId) emit({ conversationId, keyEpoch: 0 })
          return
        }
        if (body?.is_group !== true) { emit(null); return }
        original(`/chats/${conversationId}/key-envelopes`, { credentials: 'include' })
          .then(r => r.json().catch(() => null).then(state => ({ r, state })))
          .then(({ r, state }) => {
            if (!r.ok || state?.e2ee_mode !== 'group_v1') return emit(null)
            const keyEpoch = Number(state.key_epoch) || 0
            if (keyEpoch > 0) emit({ conversationId, keyEpoch })
          }).catch(() => {})
      }).catch(() => {})
    }
    return response
  }
}

function useActiveGroupChat(): ChatState | null {
  const [chat, setChat] = useState<ChatState | null>(activeChat)
  useEffect(() => {
    const listener = (next: ChatState | null) => setChat(next)
    listeners.add(listener)
    const timer = window.setInterval(() => { if (activeChat && Date.now() - lastTrafficAt > 9000) emit(null) }, 3000)
    return () => { listeners.delete(listener); window.clearInterval(timer) }
  }, [])
  return chat
}

export default function InChatAdaEnhancer() {
  const chat = useActiveGroupChat()
  const [open, setOpen] = useState(false)
  const [documents, setDocuments] = useState<SharedDocument[]>([])
  const [attachmentId, setAttachmentId] = useState<number | null>(null)
  const [pageStart, setPageStart] = useState(1)
  const [pageEnd, setPageEnd] = useState(1)
  const [selectedText, setSelectedText] = useState('')
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState('')
  const [answer, setAnswer] = useState<AdaStudyResponse | null>(null)
  const selected = useMemo(() => documents.find(doc => doc.attachmentId === attachmentId) || null, [documents, attachmentId])

  // Group Ada is mention-driven only. There is intentionally no standalone
  // open event/button path here: a group student must type @Ada in the message.
  useEffect(() => {
    if (!chat) return
    const input = document.querySelector('input[placeholder="Message…"]') as HTMLInputElement | null
    if (!input) return
    const onInput = () => {
      if (ADA_MENTION_RE.test(input.value)) setOpen(true)
    }
    onInput()
    input.addEventListener('input', onInput)
    return () => input.removeEventListener('input', onInput)
  }, [chat?.conversationId])

  useEffect(() => {
    if (!open || !chat) return
    let cancelled = false
    setLoading(true); setError(''); setAnswer(null)
    fetch(`/chats/${chat.conversationId}/messages`, { credentials: 'include' })
      .then(r => r.ok ? r.json() : Promise.reject(new Error('Could not load shared study documents.')))
      .then(body => {
        if (cancelled) return
        const seen = new Set<number>()
        const docs = (Array.isArray(body?.messages) ? body.messages : [])
          .map((message: any) => attachmentFromMessage(chat.conversationId, message))
          .filter((doc: SharedDocument | null): doc is SharedDocument => Boolean(doc))
          .filter((doc: SharedDocument) => { if (seen.has(doc.attachmentId)) return false; seen.add(doc.attachmentId); return true })
        setDocuments(docs)
        if (attachmentId == null && docs[0]) setAttachmentId(docs[0].attachmentId)
        else if (attachmentId != null && !docs.some((doc: SharedDocument) => doc.attachmentId === attachmentId)) setAttachmentId(docs[0]?.attachmentId ?? null)
      })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load shared study documents.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [open, chat?.conversationId])

  useEffect(() => { setPageStart(1); setPageEnd(1); setSelectedText(''); setPrompt(''); setAnswer(null); setError('') }, [attachmentId])

  const ask = async () => {
    if (!chat || !selected || !selectedText.trim() || !prompt.trim()) return
    setAsking(true); setError(''); setAnswer(null)
    try {
      const stateResponse = await fetch(`/chats/${chat.conversationId}/key-envelopes`, { credentials: 'include' })
      const state = await stateResponse.json().catch(() => null)
      if (!stateResponse.ok || state?.e2ee_mode !== 'group_v1') throw new Error('Secure study mode is temporarily unavailable.')
      const currentEpoch = Number(state.key_epoch) || 0
      if (currentEpoch < 1 || currentEpoch !== chat.keyEpoch) { if (currentEpoch > 0) emit({ ...chat, keyEpoch: currentEpoch }); throw new Error('The group encryption key changed. Reopen Ada and try again.') }
      const context = createAdaStudyContext({ conversationId: chat.conversationId, keyEpoch: currentEpoch, attachmentId: selected.attachmentId, pageStart, pageEnd, selectedText, userPrompt: prompt, contextScope: 'selected_chat_document' })
      setAnswer(await askAdaAboutSelectedStudyContext(context))
    } catch (e) { setError(e instanceof Error ? e.message : 'Ada could not answer right now.') }
    finally { setAsking(false) }
  }

  if (!chat) return null
  return open ? (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1200, background: 'rgba(5,10,25,.58)', display: 'flex', alignItems: 'flex-end', justifyContent: 'center', padding: 14 }}>
      <section aria-label="Ada shared study panel" style={{ width: 'min(620px,100%)', maxHeight: '90vh', overflowY: 'auto', background: '#fff', color: '#111827', borderRadius: 22, padding: 18, boxShadow: '0 24px 70px rgba(0,0,0,.3)', fontFamily: 'Plus Jakarta Sans' }}>
        <header style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}><div style={{ width: 38, height: 38, borderRadius: 12, background: 'linear-gradient(135deg,#C9A84C,#E4C96A)', display: 'grid', placeItems: 'center', color: '#0B1437', fontWeight: 900 }}>A</div><div style={{ flex: 1 }}><div style={{ fontWeight: 850 }}>Ada · Shared study</div><div style={{ fontSize: 11, color: '#6B7280' }}>Only the shared document context you explicitly select is sent.</div></div><button type="button" onClick={() => setOpen(false)} style={{ border: 0, borderRadius: 10, padding: '8px 11px', cursor: 'pointer' }}>Close</button></header>
        {loading ? <div style={{ padding: 18, color: '#6B7280', fontSize: 13 }}>Loading shared documents…</div> : documents.length === 0 ? <div style={{ padding: 18, color: '#6B7280', fontSize: 13 }}>Share a study document in this group first, then use @Ada.</div> : <>
          <label style={{ display: 'block', fontSize: 11, fontWeight: 800, marginBottom: 6 }}>Shared document</label>
          <select value={attachmentId ?? ''} onChange={e => setAttachmentId(Number(e.target.value) || null)} style={{ width: '100%', boxSizing: 'border-box', border: '1px solid #E5E7EB', borderRadius: 12, padding: 11, marginBottom: 12 }}>
            <option value="">Select a shared document</option>{documents.map(doc => <option key={doc.attachmentId} value={doc.attachmentId}>{doc.filename}</option>)}
          </select>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}><label style={{ fontSize: 11, fontWeight: 800 }}>From page<input type="number" min={1} value={pageStart} onChange={e => setPageStart(Math.max(1, Number(e.target.value) || 1))} style={{ display: 'block', width: '100%', boxSizing: 'border-box', marginTop: 6, padding: 10, border: '1px solid #E5E7EB', borderRadius: 10 }} /></label><label style={{ fontSize: 11, fontWeight: 800 }}>To page<input type="number" min={pageStart} value={pageEnd} onChange={e => setPageEnd(Math.max(pageStart, Number(e.target.value) || pageStart))} style={{ display: 'block', width: '100%', boxSizing: 'border-box', marginTop: 6, padding: 10, border: '1px solid #E5E7EB', borderRadius: 10 }} /></label></div>
          <label style={{ display: 'block', fontSize: 11, fontWeight: 800, marginBottom: 6 }}>Selected text <span style={{ color: '#9CA3AF', fontWeight: 600 }}>(explicitly disclosed to Ada)</span></label>
          <textarea value={selectedText} onChange={e => setSelectedText(e.target.value)} maxLength={20000} rows={6} placeholder="Paste or select the exact passage you want Ada to use…" style={{ width: '100%', boxSizing: 'border-box', resize: 'vertical', border: '1px solid #E5E7EB', borderRadius: 12, padding: 11, lineHeight: 1.55 }} />
          <label style={{ display: 'block', fontSize: 11, fontWeight: 800, margin: '12px 0 6px' }}>Ask Ada</label><textarea value={prompt} onChange={e => setPrompt(e.target.value)} maxLength={4000} rows={3} placeholder="Explain this, quiz us, compare these ideas…" style={{ width: '100%', boxSizing: 'border-box', resize: 'vertical', border: '1px solid #E5E7EB', borderRadius: 12, padding: 11, lineHeight: 1.55 }} />
          {error && <div style={{ marginTop: 10, padding: 10, borderRadius: 10, background: '#FEF2F2', color: '#B91C1C', fontSize: 12, fontWeight: 700 }}>{error}</div>}
          <button type="button" onClick={ask} disabled={asking || !selected || !selectedText.trim() || !prompt.trim()} style={{ width: '100%', marginTop: 12, border: 0, borderRadius: 13, padding: '12px 14px', fontWeight: 850, color: '#0B1437', background: asking || !selected || !selectedText.trim() || !prompt.trim() ? '#E5E7EB' : 'linear-gradient(135deg,#C9A84C,#E4C96A)', cursor: asking ? 'wait' : 'pointer' }}>{asking ? 'Ada is thinking…' : 'Ask Ada about this document'}</button>
          {answer && <div style={{ marginTop: 14, padding: 13, borderRadius: 14, background: '#F8F9FC', border: '1px solid #E5E7EB', whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.65 }}><strong>ADA</strong><div style={{ marginTop: 6 }}>{answer.answer}</div><div style={{ marginTop: 8, color: '#6B7280', fontSize: 10 }}>Shared document · pages {pageStart}–{pageEnd}</div></div>}
        </>}
      </section>
    </div>
  ) : null
}
