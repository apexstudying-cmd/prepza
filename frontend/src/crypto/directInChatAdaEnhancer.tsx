import { useEffect, useMemo, useState } from 'react'
import { createAdaStudyContext } from './studyAdaContext'
import { askAdaAboutSelectedStudyContext, type AdaStudyResponse } from './studyAdaApi'

type ActiveChat = { conversationId: number; keyEpoch: number }
type StudyDocument = { id: number; title: string; status: string; page_count?: number | null }

let installed = false
let activeChat: ActiveChat | null = null
let lastTrafficAt = 0
const listeners = new Set<(chat: ActiveChat | null) => void>()

function emit(chat: ActiveChat | null) { activeChat = chat; listeners.forEach(listener => listener(chat)) }
function pathOf(input: RequestInfo | URL): string {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.pathname + input.search : input.url
  try { return new URL(raw, window.location.origin).pathname } catch { return raw.split('?')[0] }
}

export function installDirectInChatAdaObserver(): void {
  if (installed || typeof window === 'undefined' || !window.fetch) return
  installed = true
  const original = window.fetch.bind(window)
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const response = await original(input, init)
    const path = pathOf(input)
    const detailMatch = path.match(/^\/chats\/(\d+)$/)
    const messagesMatch = path.match(/^\/chats\/(\d+)\/messages$/)
    if (detailMatch || messagesMatch) {
      const conversationId = Number((detailMatch || messagesMatch)![1])
      lastTrafficAt = Date.now()
      response.clone().json().then((body: any) => {
        if (detailMatch && body && typeof body === 'object') {
          if (body.is_group === true) return
          emit({ conversationId, keyEpoch: 0 })
        } else if (messagesMatch && (!activeChat || activeChat.conversationId !== conversationId)) {
          emit({ conversationId, keyEpoch: 0 })
        }
      }).catch(() => {})
    }
    return response
  }
}

function useActiveDirectChat(): ActiveChat | null {
  const [chat, setChat] = useState<ActiveChat | null>(activeChat)
  useEffect(() => {
    const listener = (next: ActiveChat | null) => setChat(next)
    listeners.add(listener)
    const timer = window.setInterval(() => { if (activeChat && Date.now() - lastTrafficAt > 9000) emit(null) }, 3000)
    return () => { listeners.delete(listener); window.clearInterval(timer) }
  }, [])
  return chat
}

export default function DirectInChatAdaEnhancer() {
  const chat = useActiveDirectChat()
  const [open, setOpen] = useState(false)
  const [docs, setDocs] = useState<StudyDocument[]>([])
  const [documentId, setDocumentId] = useState<number | null>(null)
  const [pageStart, setPageStart] = useState(1)
  const [pageEnd, setPageEnd] = useState(1)
  const [selectedText, setSelectedText] = useState('')
  const [prompt, setPrompt] = useState('')
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState('')
  const [answer, setAnswer] = useState<AdaStudyResponse | null>(null)
  const selectedDoc = useMemo(() => docs.find(doc => doc.id === documentId) || null, [docs, documentId])

  useEffect(() => {
    const openListener = (event: Event) => {
      const detail = (event as CustomEvent<{ conversationId?: number }>).detail
      const requestedConversationId = Number(detail?.conversationId)
      if (!chat || !requestedConversationId || chat.conversationId === requestedConversationId) setOpen(true)
    }
    window.addEventListener('prepza-open-ada', openListener)
    return () => window.removeEventListener('prepza-open-ada', openListener)
  }, [chat])

  useEffect(() => {
    if (!open || !chat) return
    let cancelled = false
    setLoadingDocs(true); setError('')
    fetch('/documents', { credentials: 'include' })
      .then(response => response.ok ? response.json() : Promise.reject(new Error('Could not load study documents')))
      .then(body => {
        if (cancelled) return
        const ready = Array.isArray(body?.documents) ? body.documents.filter((doc: StudyDocument) => doc.status === 'ready') : []
        setDocs(ready)
        if (!documentId && ready[0]) setDocumentId(ready[0].id)
      })
      .catch(errorValue => { if (!cancelled) setError(errorValue instanceof Error ? errorValue.message : 'Could not load study documents') })
      .finally(() => { if (!cancelled) setLoadingDocs(false) })
    const selection = window.getSelection()?.toString().trim()
    if (selection) setSelectedText(selection)
    return () => { cancelled = true }
  }, [open, chat?.conversationId])

  if (!chat) return null

  const askAda = async () => {
    if (!documentId || !selectedText.trim() || !prompt.trim()) return
    setAsking(true); setError('')
    try {
      const context = createAdaStudyContext({ conversationId: chat.conversationId, keyEpoch: chat.keyEpoch, documentId, pageStart, pageEnd, selectedText, userPrompt: prompt })
      setAnswer(await askAdaAboutSelectedStudyContext(context))
    } catch (errorValue) {
      setError(errorValue instanceof Error ? errorValue.message : 'Ada could not answer right now')
    } finally { setAsking(false) }
  }

  const pageCount = selectedDoc?.page_count || 1
  const updatePageStart = (value: number) => { const next = Math.max(1, Math.min(value, pageCount)); setPageStart(next); setPageEnd(Math.max(next, Math.min(pageEnd, next + 49, pageCount))) }
  const updatePageEnd = (value: number) => setPageEnd(Math.max(pageStart, Math.min(value, Math.min(pageStart + 49, pageCount))))

  return <>
    {open && <section aria-label="Ada study panel" style={{ position: 'fixed', right: 20, bottom: 20, zIndex: 1200, width: 'min(380px, calc(100vw - 32px))', maxHeight: '72vh', overflowY: 'auto', border: '1px solid rgba(255,255,255,.12)', borderRadius: 18, background: '#0d1420', color: '#f7f2e8', padding: 16, boxShadow: '0 24px 60px rgba(0,0,0,.34)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}><div><div style={{ fontWeight: 800, fontSize: 17 }}>Study with Ada</div><div style={{ opacity: .65, fontSize: 12, marginTop: 3 }}>Choose the study context Ada should use.</div></div><button type="button" onClick={() => setOpen(false)} style={{ background: 'transparent', border: 0, color: 'inherit', cursor: 'pointer' }}>Close</button></div>
      <label style={{ display: 'block', fontSize: 12, opacity: .72, marginBottom: 6 }}>Document</label>
      <select value={documentId ?? ''} onChange={event => setDocumentId(Number(event.target.value) || null)} disabled={loadingDocs} style={{ width: '100%', padding: 10, borderRadius: 10, marginBottom: 10 }}><option value="">Select a ready document</option>{docs.map(doc => <option key={doc.id} value={doc.id}>{doc.title}</option>)}</select>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 10 }}><label style={{ fontSize: 12 }}>From page<input type="number" min={1} max={pageCount} value={pageStart} onChange={event => updatePageStart(Number(event.target.value) || 1)} style={{ width: '100%', marginTop: 5, padding: 9, borderRadius: 9 }} /></label><label style={{ fontSize: 12 }}>To page<input type="number" min={pageStart} max={Math.min(pageStart + 49, pageCount)} value={pageEnd} onChange={event => updatePageEnd(Number(event.target.value) || pageStart)} style={{ width: '100%', marginTop: 5, padding: 9, borderRadius: 9 }} /></label></div>
      <label style={{ display: 'block', fontSize: 12, opacity: .72, marginBottom: 6 }}>Study excerpt</label><textarea value={selectedText} onChange={event => setSelectedText(event.target.value)} placeholder="Paste or select the passage you are studying…" rows={6} style={{ width: '100%', resize: 'vertical', padding: 10, borderRadius: 10, marginBottom: 10 }} />
      <label style={{ display: 'block', fontSize: 12, opacity: .72, marginBottom: 6 }}>Ask Ada</label><textarea value={prompt} onChange={event => setPrompt(event.target.value)} placeholder="Explain this, quiz me, or help me solve it…" rows={3} style={{ width: '100%', resize: 'vertical', padding: 10, borderRadius: 10, marginBottom: 10 }} />
      {error && <div style={{ color: '#ffb4ab', fontSize: 12, marginBottom: 10 }}>{error}</div>}
      <button type="button" onClick={askAda} disabled={asking || !documentId || !selectedText.trim() || !prompt.trim()} style={{ width: '100%', padding: 11, borderRadius: 10, border: 0, background: '#e8c36a', color: '#111', fontWeight: 800, cursor: asking ? 'wait' : 'pointer' }}>{asking ? 'Ada is thinking…' : 'Ask Ada'}</button>
      {answer && <div style={{ marginTop: 14, borderTop: '1px solid rgba(255,255,255,.1)', paddingTop: 14, lineHeight: 1.55, fontSize: 14, whiteSpace: 'pre-wrap' }}>{answer.answer}</div>}
    </section>}
  </>
