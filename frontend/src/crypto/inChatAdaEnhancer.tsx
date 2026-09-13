import { useEffect, useMemo, useState } from 'react'
import { createAdaStudyContext } from './studyAdaContext'
import { askAdaAboutSelectedStudyContext, type AdaStudyResponse } from './studyAdaApi'

type ChatState = {
  conversationId: number
  isGroup: boolean
  e2eeMode: string
  keyEpoch: number
}

type StudyDocument = {
  id: number
  title: string
  status: string
  page_count?: number | null
  file_type?: string | null
}

let installed = false
let activeChat: ChatState | null = null
let lastChatTrafficAt = 0
const listeners = new Set<(state: ChatState | null) => void>()

function emit(state: ChatState | null) {
  activeChat = state
  listeners.forEach(listener => listener(state))
}

function pathOf(input: RequestInfo | URL): string {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.pathname + input.search : input.url
  try { return new URL(raw, window.location.origin).pathname } catch { return raw.split('?')[0] }
}

export function installInChatAdaObserver(): void {
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
      lastChatTrafficAt = Date.now()
      response.clone().json().then((body: any) => {
        if (detailMatch && body && typeof body === 'object') {
          const isGroup = body.is_group === true
          if (!isGroup) {
            emit({ conversationId, isGroup: false, e2eeMode: 'legacy', keyEpoch: 0 })
            return
          }

          original(`/chats/${conversationId}/key-envelopes`, { credentials: 'include' })
            .then(stateResponse => stateResponse.json().catch(() => null).then(state => ({ stateResponse, state })))
            .then(({ stateResponse, state }) => {
              if (!stateResponse.ok || !state) return
              emit({
                conversationId,
                isGroup: true,
                e2eeMode: typeof state.e2ee_mode === 'string' ? state.e2ee_mode : 'unknown',
                keyEpoch: Number(state.key_epoch) || 0,
              })
            })
            .catch(() => {})
        } else if (messagesMatch && (!activeChat || activeChat.conversationId !== conversationId)) {
          emit({ conversationId, isGroup: false, e2eeMode: 'unknown', keyEpoch: 0 })
        }
      }).catch(() => {})
    }

    return response
  }
}

function useActiveChat(): ChatState | null {
  const [state, setState] = useState<ChatState | null>(activeChat)
  useEffect(() => {
    const listener = (next: ChatState | null) => setState(next)
    listeners.add(listener)
    const timer = window.setInterval(() => {
      if (activeChat && Date.now() - lastChatTrafficAt > 9000) emit(null)
    }, 3000)
    return () => {
      listeners.delete(listener)
      window.clearInterval(timer)
    }
  }, [])
  return state
}

export default function InChatAdaEnhancer() {
  const chat = useActiveChat()
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

  const activeGroup = Boolean(chat?.isGroup && chat.e2eeMode === 'group_v1' && chat.keyEpoch > 0)
  const selectedDoc = useMemo(() => docs.find(doc => doc.id === documentId) || null, [docs, documentId])

  useEffect(() => {
    const onOpenAda = (event: Event) => {
      const detail = (event as CustomEvent<{ conversationId?: number }>).detail
      if (detail?.conversationId == null) return
      if (chat?.conversationId !== Number(detail.conversationId)) return
      setOpen(true)
    }
    window.addEventListener('prepza-open-ada', onOpenAda)
    return () => window.removeEventListener('prepza-open-ada', onOpenAda)
  }, [chat?.conversationId])

  useEffect(() => {
    if (!open || !activeGroup) return
    let cancelled = false
    setLoadingDocs(true)
    setError('')
    fetch('/documents', { credentials: 'include' })
      .then(res => res.ok ? res.json() : Promise.reject(new Error('Could not load your documents.')))
      .then(body => {
        if (cancelled) return
        const ready = Array.isArray(body?.documents)
          ? body.documents.filter((doc: StudyDocument) => doc.status === 'ready')
          : []
        setDocs(ready)
        if (documentId == null && ready[0]) {
          setDocumentId(ready[0].id)
          setPageEnd(1)
        }
      })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load your documents.') })
      .finally(() => { if (!cancelled) setLoadingDocs(false) })
    return () => { cancelled = true }
  }, [open, activeGroup])

  useEffect(() => {
    const input = document.querySelector('input[placeholder="Message…"]') as HTMLInputElement | null
    if (!input) return
    const onInput = () => {
      if (input.value.toLowerCase().includes('@ada')) setOpen(true)
    }
    input.addEventListener('input', onInput)
    return () => input.removeEventListener('input', onInput)
  })

  useEffect(() => {
    if (!selectedDoc) return
    const maxPage = Math.max(1, selectedDoc.page_count || 1)
    setPageStart(prev => Math.min(Math.max(1, prev), maxPage))
    setPageEnd(prev => Math.min(Math.max(1, prev), maxPage))
  }, [selectedDoc])

  const ask = async () => {
    if (!chat || !activeGroup || documentId == null) return
    setError('')
    setAnswer(null)
    setAsking(true)
    try {
      const stateRes = await fetch(`/chats/${chat.conversationId}/key-envelopes`, { credentials: 'include' })
      const stateBody = await stateRes.json().catch(() => null)
      if (!stateRes.ok) throw new Error('Could not verify the study chat right now.')
      const currentEpoch = Number(stateBody?.key_epoch) || 0
      if (stateBody?.e2ee_mode !== 'group_v1' || currentEpoch < 1) {
        throw new Error('Study mode is temporarily unavailable for this group.')
      }
      if (currentEpoch !== chat.keyEpoch) emit({ ...chat, keyEpoch: currentEpoch })

      const context = createAdaStudyContext({
        conversationId: chat.conversationId,
        keyEpoch: currentEpoch,
        documentId,
        pageStart,
        pageEnd,
        selectedText,
        userPrompt: prompt,
      })
      const result = await askAdaAboutSelectedStudyContext(context)
      setAnswer(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ada could not answer right now.')
    } finally {
      setAsking(false)
    }
  }

  if (!activeGroup) return null

  return (
    <>
      {open && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 80, background: 'rgba(5,10,25,0.58)', display: 'flex', alignItems: 'flex-end', justifyContent: 'center', padding: 14 }}>
          <div style={{ width: 'min(620px,100%)', maxHeight: '90vh', overflowY: 'auto', background: '#fff', borderRadius: 22, boxShadow: '0 24px 70px rgba(0,0,0,0.3)', padding: 18, fontFamily: 'Plus Jakarta Sans' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <div style={{ width: 38, height: 38, borderRadius: 12, background: 'linear-gradient(135deg,#C9A84C,#E4C96A)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#0B1437', fontWeight: 900 }}>A</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 850, color: '#111827', fontSize: 15 }}>Ada · Study context</div>
                <div style={{ fontSize: 11, color: '#6B7280' }}>Only the document pages and text you explicitly select are sent.</div>
              </div>
              <button onClick={() => setOpen(false)} style={{ border: 'none', background: '#F3F4F6', borderRadius: 10, padding: '8px 11px', cursor: 'pointer', fontWeight: 800 }}>Close</button>
            </div>

            {loadingDocs ? <div style={{ padding: 18, color: '#6B7280', fontSize: 13 }}>Loading your documents…</div> : (
              <>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 800, color: '#374151', marginBottom: 6 }}>Study document</label>
                <select value={documentId ?? ''} onChange={e => setDocumentId(Number(e.target.value) || null)} style={{ width: '100%', boxSizing: 'border-box', border: '1px solid #E5E7EB', borderRadius: 12, padding: '11px 12px', fontFamily: 'Plus Jakarta Sans', fontSize: 13, marginBottom: 12 }}>
                  <option value="">Select a document</option>
                  {docs.map(doc => <option key={doc.id} value={doc.id}>{doc.title}</option>)}
                </select>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
                  <label style={{ fontSize: 11, fontWeight: 800, color: '#374151' }}>From page
                    <input type="number" min={1} max={selectedDoc?.page_count || 1} value={pageStart} onChange={e => setPageStart(Number(e.target.value) || 1)} style={{ display: 'block', width: '100%', boxSizing: 'border-box', marginTop: 6, border: '1px solid #E5E7EB', borderRadius: 10, padding: '10px', fontFamily: 'Plus Jakarta Sans' }} />
                  </label>
                  <label style={{ fontSize: 11, fontWeight: 800, color: '#374151' }}>To page
                    <input type="number" min={pageStart} max={selectedDoc?.page_count || 1} value={pageEnd} onChange={e => setPageEnd(Number(e.target.value) || pageStart)} style={{ display: 'block', width: '100%', boxSizing: 'border-box', marginTop: 6, border: '1px solid #E5E7EB', borderRadius: 10, padding: '10px', fontFamily: 'Plus Jakarta Sans' }} />
                  </label>
                </div>

                <label style={{ display: 'block', fontSize: 11, fontWeight: 800, color: '#374151', marginBottom: 6 }}>Selected text <span style={{ color: '#9CA3AF', fontWeight: 600 }}>(explicitly disclosed to Ada)</span></label>
                <textarea value={selectedText} onChange={e => setSelectedText(e.target.value)} maxLength={20000} rows={6} placeholder="Paste or select the exact text from the chosen pages that you want Ada to study…" style={{ width: '100%', boxSizing: 'border-box', resize: 'vertical', border: '1px solid #E5E7EB', borderRadius: 12, padding: 11, fontFamily: 'Plus Jakarta Sans', fontSize: 13, lineHeight: 1.55, outline: 'none' }} />

                <label style={{ display: 'block', fontSize: 11, fontWeight: 800, color: '#374151', margin: '12px 0 6px' }}>Ask Ada</label>
                <textarea value={prompt} onChange={e => setPrompt(e.target.value)} maxLength={4000} rows={3} placeholder="Explain this concept, quiz me, compare these ideas…" style={{ width: '100%', boxSizing: 'border-box', resize: 'vertical', border: '1px solid #E5E7EB', borderRadius: 12, padding: 11, fontFamily: 'Plus Jakarta Sans', fontSize: 13, lineHeight: 1.55, outline: 'none' }} />

                {error && <div style={{ marginTop: 10, padding: 10, borderRadius: 10, background: '#FEF2F2', color: '#B91C1C', fontSize: 12, fontWeight: 700 }}>{error}</div>}
                {answer && <div style={{ marginTop: 12, padding: 13, borderRadius: 14, background: '#F8F9FC', border: '1px solid #E5E7EB' }}><div style={{ fontSize: 11, fontWeight: 900, color: '#0B1437', marginBottom: 6 }}>ADA</div><div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.65, color: '#111827' }}>{answer.answer}</div><div style={{ marginTop: 8, fontSize: 10, color: '#6B7280' }}>Context: pages {pageStart}–{pageEnd}</div></div>}

                <button type="button" disabled={asking || !documentId || !selectedText.trim() || !prompt.trim()} onClick={ask} style={{ width: '100%', marginTop: 12, border: 'none', borderRadius: 13, padding: '12px 14px', cursor: asking ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 850, fontSize: 13, color: '#0B1437', background: asking || !documentId || !selectedText.trim() || !prompt.trim() ? '#E5E7EB' : 'linear-gradient(135deg,#C9A84C,#E4C96A)' }}>{asking ? 'Ada is thinking…' : 'Ask Ada about this selection'}</button>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}
