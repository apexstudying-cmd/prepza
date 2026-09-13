import { useEffect, useState } from 'react'
import { createAdaStudyContext } from './studyAdaContext'
import { askAdaAboutSelectedStudyContext, type AdaStudyResponse } from './studyAdaApi'

type Doc = { id: number; title: string; status: string; page_count?: number | null }

export default function WhatsAppAdaPanel() {
  const [open, setOpen] = useState(false)
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [docs, setDocs] = useState<Doc[]>([])
  const [documentId, setDocumentId] = useState<number | null>(null)
  const [pageStart, setPageStart] = useState(1)
  const [pageEnd, setPageEnd] = useState(1)
  const [selectedText, setSelectedText] = useState('')
  const [prompt, setPrompt] = useState('')
  const [answer, setAnswer] = useState<AdaStudyResponse | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const onOpen = (event: Event) => {
      const id = Number((event as CustomEvent<{ conversationId?: number }>).detail?.conversationId)
      if (Number.isInteger(id) && id > 0) setConversationId(id)
      setOpen(true)
    }
    window.addEventListener('prepza-open-ada', onOpen)
    return () => window.removeEventListener('prepza-open-ada', onOpen)
  }, [])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true); setError('')
    fetch('/documents', { credentials: 'include' })
      .then(response => response.ok ? response.json() : Promise.reject(new Error('Could not load documents')))
      .then(body => {
        if (cancelled) return
        const ready = Array.isArray(body?.documents) ? body.documents.filter((doc: Doc) => doc.status === 'ready') : []
        setDocs(ready)
        if (documentId == null && ready[0]) setDocumentId(ready[0].id)
      })
      .catch(errorValue => { if (!cancelled) setError(errorValue instanceof Error ? errorValue.message : 'Could not load documents') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [open, documentId])

  useEffect(() => {
    if (!open) return
    const hideLegacyAda = () => {
      document.querySelectorAll('button').forEach(button => {
        if (button.textContent?.trim() === 'Study with Ada') button.style.display = 'none'
      })
    }
    hideLegacyAda()
    const observer = new MutationObserver(hideLegacyAda)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [open])

  const ask = async () => {
    if (!conversationId || !documentId || !selectedText.trim() || !prompt.trim()) return
    setError(''); setAnswer(null); setLoading(true)
    try {
      const stateResponse = await fetch(`/chats/${conversationId}/key-envelopes`, { credentials: 'include' })
      const state = await stateResponse.json().catch(() => null)
      const isGroup = state?.e2ee_mode === 'group_v1'
      const keyEpoch = isGroup ? Number(state?.key_epoch) || 0 : 0
      const context = createAdaStudyContext({ conversationId, keyEpoch, documentId, pageStart, pageEnd, selectedText, userPrompt: prompt })
      setAnswer(await askAdaAboutSelectedStudyContext(context))
    } catch (errorValue) { setError(errorValue instanceof Error ? errorValue.message : 'Ada could not answer right now') }
    finally { setLoading(false) }
  }

  if (!open) return null
  const selectedDoc = docs.find(doc => doc.id === documentId)
  const maxPage = Math.max(1, selectedDoc?.page_count || 1)

  return <div style={{ position: 'fixed', inset: 0, zIndex: 1300, background: 'rgba(5,10,25,.55)', display: 'flex', alignItems: 'flex-end', justifyContent: 'center', padding: 14 }}>
    <section style={{ width: 'min(620px,100%)', maxHeight: '90vh', overflowY: 'auto', background: '#fff', borderRadius: 22, padding: 18, boxShadow: '0 24px 70px rgba(0,0,0,.3)', fontFamily: 'Plus Jakarta Sans,sans-serif' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
        <div style={{ width: 38, height: 38, borderRadius: 12, background: 'linear-gradient(135deg,#C9A84C,#E4C96A)', display: 'grid', placeItems: 'center', fontWeight: 900, color: '#0B1437' }}>A</div>
        <div style={{ flex: 1 }}><div style={{ fontWeight: 900, fontSize: 15 }}>Ada · Study together</div><div style={{ fontSize: 11, color: '#6B7280' }}>Choose the study context Ada should use.</div></div>
        <button onClick={() => setOpen(false)} style={{ border: 0, background: '#F3F4F6', borderRadius: 10, padding: '8px 11px', fontWeight: 800, cursor: 'pointer' }}>Close</button>
      </div>
      {loading && docs.length === 0 ? <div style={{ padding: 20, color: '#6B7280', fontSize: 13 }}>Loading…</div> : <>
        <select value={documentId ?? ''} onChange={e => setDocumentId(Number(e.target.value) || null)} style={{ width: '100%', padding: 11, borderRadius: 12, border: '1px solid #E5E7EB', marginBottom: 10 }}><option value="">Select a document</option>{docs.map(doc => <option key={doc.id} value={doc.id}>{doc.title}</option>)}</select>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}><input type="number" min={1} max={maxPage} value={pageStart} onChange={e => setPageStart(Math.max(1, Math.min(Number(e.target.value) || 1, maxPage)))} placeholder="From page" style={{ padding: 10, borderRadius: 10, border: '1px solid #E5E7EB' }} /><input type="number" min={pageStart} max={maxPage} value={pageEnd} onChange={e => setPageEnd(Math.max(pageStart, Math.min(Number(e.target.value) || pageStart, maxPage)))} placeholder="To page" style={{ padding: 10, borderRadius: 10, border: '1px solid #E5E7EB' }} /></div>
        <textarea value={selectedText} onChange={e => setSelectedText(e.target.value)} rows={6} placeholder="Select or paste the passage you want Ada to study…" style={{ width: '100%', boxSizing: 'border-box', marginTop: 10, padding: 11, borderRadius: 12, border: '1px solid #E5E7EB', resize: 'vertical' }} />
        <textarea value={prompt} onChange={e => setPrompt(e.target.value)} rows={3} placeholder="@Ada explain this, quiz us, or help us solve it…" style={{ width: '100%', boxSizing: 'border-box', marginTop: 10, padding: 11, borderRadius: 12, border: '1px solid #E5E7EB', resize: 'vertical' }} />
        {error && <div style={{ marginTop: 10, padding: 10, borderRadius: 10, background: '#FEF2F2', color: '#A33A35', fontSize: 12 }}>{error}</div>}
        {answer && <div style={{ marginTop: 10, padding: 13, borderRadius: 14, background: '#F8F9FC', fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{answer.answer}</div>}
        <button disabled={loading || !conversationId || !documentId || !selectedText.trim() || !prompt.trim()} onClick={() => void ask()} style={{ width: '100%', marginTop: 12, padding: 12, border: 0, borderRadius: 13, background: '#C9A84C', color: '#0B1437', fontWeight: 900, cursor: 'pointer' }}>{loading ? 'Ada is thinking…' : 'Ask Ada'}</button>
      </>}
    </section>
  </div>
}
