import { useEffect, useState } from 'react'
import { saveUploadedFileOffline } from './offline/studyHubOffline'

const ALLOWED_EXTENSIONS = new Set(['pdf','doc','docx','ppt','pptx','jpg','jpeg','png'])
const MAX_BYTES = 50 * 1024 * 1024

type ImportDetail = { file: File }
type DocumentCreate = {
  document_id: number
  status: string
  duplicate: boolean
  already_in_studyhub?: boolean
  upload_url?: string
}

function extension(name: string) {
  const value = name.split('.').pop()?.toLowerCase() || ''
  return value
}
function titleFromFilename(name: string) {
  const dot = name.lastIndexOf('.')
  return (dot > 0 ? name.slice(0, dot) : name).trim() || 'Imported document'
}
async function sha256(file: File) {
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
  return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('')
}
async function api<T>(path: string, options: RequestInit = {}) {
  const response = await fetch(path, { credentials: 'include', ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } })
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new Error(body?.error || `Request failed (${response.status})`)
  return body as T
}

export default function ExternalDocumentImport() {
  const [file, setFile] = useState<File | null>(null)
  const [documentId, setDocumentId] = useState<number | null>(null)
  const [title, setTitle] = useState('')
  const [stage, setStage] = useState<'idle'|'uploading'|'choice'|'publishing'|'done'>('idle')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [csrf, setCsrf] = useState('')
  const [duplicate, setDuplicate] = useState(false)

  useEffect(() => {
    const onImport = (event: Event) => {
      const incoming = (event as CustomEvent<ImportDetail>).detail?.file
      if (!(incoming instanceof File)) return
      setFile(incoming)
      setTitle(titleFromFilename(incoming.name))
      setDocumentId(null)
      setDuplicate(false)
      setMessage('')
      setError('')
      setStage('idle')
    }
    window.addEventListener('prepza:external-document', onImport)
    return () => window.removeEventListener('prepza:external-document', onImport)
  }, [])

  const close = () => {
    setFile(null); setDocumentId(null); setStage('idle'); setError(''); setMessage(''); setDuplicate(false)
  }

  const prepare = async () => {
    if (!file) return
    const ext = extension(file.name)
    if (!ALLOWED_EXTENSIONS.has(ext)) { setError('Prepza cannot open this file type yet.'); return }
    if (file.size <= 0 || file.size > MAX_BYTES) { setError('The file must be between 1 byte and 50 MB.'); return }

    setError('')
    setStage('uploading')
    try {
      const hash = await sha256(file)
      const me = await api<{ id: number; csrf_token: string }>('/me')
      setCsrf(me.csrf_token)
      const created = await api<DocumentCreate>('/documents', {
        method: 'POST',
        headers: { 'X-CSRF-Token': me.csrf_token },
        body: JSON.stringify({
          title: title.trim() || titleFromFilename(file.name),
          original_filename: file.name,
          file_size_bytes: file.size,
          content_hash: hash,
        }),
      })

      if (!created.duplicate && created.upload_url) {
        const upload = await fetch(created.upload_url, { method: 'PUT', body: file })
        if (!upload.ok) throw new Error('Prepza could not finish the document upload.')
        try {
          await api(`/documents/${created.document_id}/uploaded`, { method: 'POST', headers: { 'X-CSRF-Token': me.csrf_token } })
        } catch (e) {
          if (!(e instanceof Error && /409/.test(e.message))) throw e
          await new Promise(resolve => setTimeout(resolve, 1200))
          await api(`/documents/${created.document_id}/uploaded`, { method: 'POST', headers: { 'X-CSRF-Token': me.csrf_token } })
        }
      }

      await saveUploadedFileOffline(created.document_id, file, {
        userId: me.id,
        title: title.trim() || titleFromFilename(file.name),
        fileType: ext,
        contentHash: hash,
      })

      setDocumentId(created.document_id)
      setDuplicate(Boolean(created.duplicate))
      setMessage(created.duplicate
        ? 'Thank you. Prepza already has this exact document, so no second copy was uploaded.'
        : 'The document is now in your private Study Hub and saved for offline study.')
      setStage('choice')
    } catch (e) {
      setStage('idle')
      setError(e instanceof Error ? e.message : 'Could not import this document.')
    }
  }

  const studyPrivately = () => {
    if (documentId == null) return
    window.dispatchEvent(new CustomEvent('prepza:open-document', { detail: { documentId } }))
    close()
  }

  const publish = async () => {
    if (documentId == null || !csrf) return
    setStage('publishing'); setError('')
    try {
      const result = await api<{ duplicate?: boolean; message?: string; status?: string }>('/library/publish', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrf },
        body: JSON.stringify({
          document_id: documentId,
          title: title.trim() || titleFromFilename(file?.name || ''),
          material_type: 'lecture_notes',
        }),
      })
      if (result.duplicate) {
        setMessage(result.message || 'Thank you. This document is already in the Library.')
      } else {
        setMessage('Submitted to the Prepza Library for review. Your private Study Hub copy remains available offline.')
      }
      setStage('done')
    } catch (e) {
      setStage('choice')
      setError(e instanceof Error ? e.message : 'Could not publish this document.')
    }
  }

  if (!file) return null

  const busy = stage === 'uploading' || stage === 'publishing'
  const ready = stage === 'choice'
  return (
    <div style={{ position:'fixed', inset:0, zIndex:3000, background:'rgba(5,10,25,.72)', display:'flex', alignItems:'flex-end', justifyContent:'center' }}>
      <div style={{ width:'100%', maxWidth:520, maxHeight:'92dvh', overflowY:'auto', background:'#fff', borderRadius:'26px 26px 0 0', padding:'20px 18px 30px', boxSizing:'border-box', fontFamily:'Plus Jakarta Sans' }}>
        <div style={{ width:42, height:4, borderRadius:99, background:'#D1D5DB', margin:'0 auto 18px' }}/>
        <div style={{ fontSize:20, fontWeight:850, color:'#0B1437' }}>Open in Prepza</div>
        <div style={{ fontSize:12, color:'#6B7280', marginTop:5, marginBottom:18 }}>{file.name}</div>

        {stage === 'idle' && <>
          <div style={{ background:'#F7F8FC', border:'1px solid #E5E7EB', borderRadius:16, padding:14, marginBottom:14 }}>
            <div style={{ fontSize:13, fontWeight:800, color:'#0B1437' }}>Ready to study</div>
            <div style={{ fontSize:12, lineHeight:1.55, color:'#6B7280', marginTop:4 }}>Prepza will add this document to your private Study Hub and download it for offline study.</div>
          </div>
          <input value={title} onChange={e=>setTitle(e.target.value)} aria-label="Document title" style={{ width:'100%', boxSizing:'border-box', border:'1px solid #E5E7EB', borderRadius:12, padding:'12px 13px', fontSize:13, color:'#0B1437', outline:'none' }}/>
          <button onClick={prepare} style={{ width:'100%', marginTop:12, border:0, borderRadius:14, padding:14, background:'#C9A84C', color:'#0B1437', fontWeight:850, cursor:'pointer' }}>Import to Prepza</button>
        </>}

        {busy && <div style={{ padding:'30px 0', textAlign:'center', color:'#6B7280', fontSize:13 }}>Uploading and saving your document…</div>}

        {ready && <>
          <div style={{ background:'#F7F8FC', border:'1px solid #E5E7EB', borderRadius:16, padding:14, marginBottom:14 }}>
            <div style={{ fontSize:13, fontWeight:800, color:'#0B1437' }}>{duplicate ? 'Exact document already found' : 'Document added to Study Hub'}</div>
            <div style={{ fontSize:12, lineHeight:1.55, color:'#6B7280', marginTop:5 }}>{message}</div>
          </div>
          <div style={{ fontSize:12, color:'#6B7280', marginBottom:8 }}>What would you like to do?</div>
          <button onClick={studyPrivately} style={{ width:'100%', border:'1px solid #E5E7EB', borderRadius:14, padding:14, background:'#fff', color:'#0B1437', fontWeight:800, cursor:'pointer' }}>Study privately offline</button>
          <button onClick={publish} style={{ width:'100%', marginTop:9, border:0, borderRadius:14, padding:14, background:'#0B1437', color:'#E8C97E', fontWeight:800, cursor:'pointer' }}>Publish to Prepza Library</button>
        </>}

        {stage === 'done' && <div style={{ textAlign:'center', padding:'18px 0 4px' }}>
          <div style={{ fontSize:14, fontWeight:800, color:'#0B1437' }}>{message}</div>
          <button onClick={close} style={{ width:'100%', marginTop:16, border:0, borderRadius:14, padding:13, background:'#C9A84C', color:'#0B1437', fontWeight:800, cursor:'pointer' }}>Done</button>
        </div>}

        {error && <div style={{ marginTop:12, background:'#FFF3F3', border:'1px solid #F0CACA', borderRadius:12, padding:11, color:'#A33A3A', fontSize:12 }}>{error}</div>}
      </div>
    </div>
  )
}
