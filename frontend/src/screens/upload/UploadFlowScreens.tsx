import { useEffect, useRef, useState, type ChangeEvent, type ComponentType } from 'react'

import { api, ApiError } from '../../lib/appApi'
import { getFileExtension, sha256Hex } from '../../lib/fileUtils'
import { saveUploadedFileOffline } from '../../offline/studyHubOffline'
import { N, useTheme } from '../../theme/theme'
import type { DocumentDetail } from '../../types/documents'
import type { Screen } from '../../types/navigation'
import { ALLOWED_UPLOAD_EXTENSIONS, MAX_UPLOAD_SIZE_BYTES } from './uploadConfig'

type UploadTopBar = ComponentType<{ title?: string; onBack?: () => void }>

// ─── UPLOAD ───────────────────────────────────────────────────────────────────
function UploadScreen({ setScreen, setActiveDocumentId, TopBar }: { setScreen: (s: Screen) => void; setActiveDocumentId: (id: number | null) => void; TopBar: UploadTopBar }) {
  const { mode, tokens: T } = useTheme()
  const fileRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadStage, setUploadStage] = useState('')
  const [error, setError] = useState('')

  const startUpload = async (file: File) => {
    setError('')

    const ext = getFileExtension(file.name)
    if (!ext || !ALLOWED_UPLOAD_EXTENSIONS.includes(ext)) {
      setError(`Unsupported file type. Allowed: ${ALLOWED_UPLOAD_EXTENSIONS.join(', ').toUpperCase()}`)
      return
    }
    if (file.size > MAX_UPLOAD_SIZE_BYTES) {
      setError(`File exceeds the ${MAX_UPLOAD_SIZE_BYTES / (1024 * 1024)} MB limit`)
      return
    }

    setUploading(true)
    try {
      setUploadStage('Hashing file...')
      const contentHash = await sha256Hex(file)

      setUploadStage('Registering upload...')
      const me = await api<{ id: number; csrf_token: string }>('/me')
      const title = file.name.includes('.') ? file.name.slice(0, file.name.lastIndexOf('.')) : file.name

      const created = await api<{
        document_id: number; status: string; duplicate: boolean
        upload_url?: string; storage_path?: string
      }>('/documents', {
        method: 'POST',
        headers: { 'X-CSRF-Token': me.csrf_token },
        body: JSON.stringify({
          title,
          original_filename: file.name,
          file_size_bytes: file.size,
          content_hash: contentHash,
        }),
      })

      if (!created.duplicate && created.upload_url) {
        setUploadStage('Uploading file...')
        const putRes = await fetch(created.upload_url, { method: 'PUT', body: file })
        if (!putRes.ok) throw new Error('Upload to storage failed - please try again')

        setUploadStage('Confirming upload...')
        try {
          await api(`/documents/${created.document_id}/uploaded`, {
            method: 'POST',
            headers: { 'X-CSRF-Token': me.csrf_token },
          })
        } catch (e) {
          if (e instanceof ApiError && e.status === 409) {
            await new Promise(r => setTimeout(r, 1500))
            await api(`/documents/${created.document_id}/uploaded`, {
              method: 'POST',
              headers: { 'X-CSRF-Token': me.csrf_token },
            })
          } else {
            throw e
          }
        }
      }

      // Study Hub ingestion is local-first. The original File is already the
      // canonical bytes, so persist it before declaring the new Study Hub item
      // ready. This avoids an extra download and guarantees the item is usable
      // offline immediately after ingestion.
      setUploadStage('Preparing offline copy...')
      await saveUploadedFileOffline(created.document_id, file, {
        userId: me.id,
        title,
        fileType: ext,
        contentHash,
      })

      setActiveDocumentId(created.document_id)
      setScreen('upload-share-choice')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'Upload failed - please check your connection and try again.')
    } finally {
      setUploading(false)
      setUploadStage('')
    }
  }

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) startUpload(file)
    e.target.value = ''
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <TopBar title="Upload Document" onBack={() => window.history.back()} />
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', marginTop: -8 }}>Prepza AI processes your document instantly</div>
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 18 }}>
        {error && (
          <div style={{ background: 'rgba(201,68,68,0.08)', border: '1px solid rgba(201,68,68,0.25)', borderRadius: 12, padding: '12px 14px', color: '#C94C4C', fontSize: 12, fontWeight: 600 }}>{error}</div>
        )}
        <div
          onDragOver={e => { e.preventDefault(); if (!uploading) setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={e => { e.preventDefault(); setDragging(false); const file = e.dataTransfer.files?.[0]; if (file && !uploading) startUpload(file) }}
          onClick={() => !uploading && fileRef.current?.click()}
          style={{ border: `2px dashed ${dragging ? N.gold : T.border}`, borderRadius: 20, padding: '40px 20px', textAlign: 'center', background: dragging ? 'rgba(201,168,76,0.04)' : T.card, cursor: uploading ? 'wait' : 'pointer', opacity: uploading ? 0.7 : 1, transition: 'all 0.2s' }}
        >
          <input ref={fileRef} type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png" style={{ display: 'none' }} onChange={handleFileChange} disabled={uploading} />
          <div style={{ fontSize: 48, marginBottom: 12 }}>{uploading ? '⏳' : '📤'}</div>
          <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 6 }}>{uploading ? (uploadStage || 'Uploading...') : 'Drop your file here'}</div>
          {!uploading && <div style={{ fontSize: 13, color: T.textMuted, marginBottom: 16 }}>or tap to browse from your device</div>}
          {!uploading && (
            <div style={{ display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap' }}>
              {['PDF','Word','PowerPoint','JPG','PNG'].map(t => <span key={t} style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: T.text, fontSize: 10, fontWeight: 600, padding: '4px 10px', borderRadius: 20 }}>{t}</span>)}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── POST-UPLOAD STUDYHUB / LIBRARY CHOICE ────────────────────────────────────
function UploadShareChoiceScreen({ setScreen, activeDocumentId, TopBar }: { setScreen: (s: Screen) => void; activeDocumentId: number | null; TopBar: UploadTopBar }) {
  const { tokens: T } = useTheme()
  const [doc, setDoc] = useState<DocumentDetail | null>(null)

  useEffect(() => {
    if (activeDocumentId == null) return
    api<DocumentDetail>(`/documents/${activeDocumentId}`)
      .then(setDoc)
      .catch(() => {})
  }, [activeDocumentId])

  const openStudyHub = () => setScreen('processing')
  const publish = () => setScreen('publish-library')

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 24px' }}>
        <TopBar title="Document added to StudyHub" onBack={openStudyHub} />
      </div>
      <div style={{ padding: '24px 18px 40px', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
        <div style={{ width: 72, height: 72, borderRadius: 22, background: `${N.gold}18`, border: `1px solid ${N.gold}40`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 18, fontSize: 34 }}>✓</div>
        <div style={{ fontWeight: 850, fontSize: 21, color: T.text, marginBottom: 8 }}>Your document is in StudyHub</div>
        <div style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.65, maxWidth: 360, marginBottom: 8 }}>
          {doc?.title ? <><strong style={{ color: T.text }}>{doc.title}</strong> is safely in your personal StudyHub.</> : 'Your document is safely in your personal StudyHub.'}
        </div>
        <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.6, maxWidth: 360, marginBottom: 26 }}>
          It is private by default. Sharing to Library is optional and requires your explicit choice.
        </div>

        <div style={{ width: '100%', maxWidth: 420, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <button onClick={publish} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, border: 'none', borderRadius: 16, padding: '15px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 850, fontSize: 14, boxShadow: `0 6px 22px ${N.gold}35` }}>
            Share to Prepza Library
            <span style={{ display: 'block', fontSize: 11, fontWeight: 600, opacity: 0.7, marginTop: 3 }}>Help other students · Earn XP on approval</span>
          </button>
          <button onClick={openStudyHub} style={{ width: '100%', background: T.card, color: T.text, border: `1px solid ${T.border}`, borderRadius: 16, padding: '14px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 750, fontSize: 14 }}>
            Study my document
          </button>
          <button onClick={openStudyHub} style={{ background: 'none', border: 'none', color: T.textMuted, padding: '10px 8px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 650, fontSize: 12 }}>
            Maybe later
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── PROCESSING ───────────────────────────────────────────────────────────────
function ProcessingScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const { tokens: T } = useTheme()
  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [pollError, setPollError] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>

    const poll = async () => {
      try {
        const result = await api<DocumentDetail>(`/documents/${activeDocumentId}`)
        if (cancelled) return
        setDoc(result)
        if (result.status === 'ready' || result.status === 'failed') return
        timer = setTimeout(poll, 2500)
      } catch (e) {
        if (cancelled) return
        setPollError(e instanceof ApiError ? e.message : 'Lost connection while checking status - retrying...')
        timer = setTimeout(poll, 2500)
      }
    }
    poll()

    return () => { cancelled = true; clearTimeout(timer) }
  }, [activeDocumentId])

  const status = doc?.status
  const stageLabel = status === 'uploading' ? 'Uploading document…'
    : status === 'processing' ? 'Extracting content & analysing…'
    : status === 'ready' ? 'Ready to study!'
    : status === 'failed' ? 'Something went wrong'
    : 'Getting started…'

  if (activeDocumentId == null) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.navy, padding: 32, textAlign: 'center' }}>
        <div style={{ color: '#fff', fontWeight: 800, fontSize: 18, marginBottom: 10 }}>No upload in progress</div>
        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginBottom: 28 }}>Head back to upload a document to see its processing status here.</div>
        <button onClick={() => setScreen('upload')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '12px 28px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Go to Upload</button>
      </div>
    )
  }

  if (status === 'failed') {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.navy, padding: 32, textAlign: 'center' }}>
        <div style={{ fontSize: 44, marginBottom: 16 }}>⚠️</div>
        <div style={{ color: '#fff', fontWeight: 800, fontSize: 18, marginBottom: 10 }}>Processing failed</div>
        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginBottom: 28, maxWidth: 280 }}>{doc?.error_message || 'This document could not be processed. Please try uploading again.'}</div>
        <button onClick={() => setScreen('upload')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '12px 28px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Try Again</button>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.navy, padding: 32 }}>
      <div style={{ position: 'relative', width: 120, height: 120, marginBottom: 36 }}>
        <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: '3px solid rgba(201,168,76,0.18)' }} />
        <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: '3px solid transparent', borderTopColor: N.gold, animation: 'spin-slow 1.1s linear infinite' }} />
        <div style={{ position: 'absolute', inset: 14, borderRadius: '50%', background: 'rgba(201,168,76,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <img src="/icon-192.png" alt="Prepza" style={{ width: 52, height: 52, borderRadius: 14 }} />
        </div>
      </div>
      <div style={{ color: '#fff', fontWeight: 800, fontSize: 20, marginBottom: 6, textAlign: 'center' }}>{stageLabel}</div>
      <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 13, textAlign: 'center', marginBottom: 20 }}>{doc?.title || 'Your document'}</div>
      {pollError && <div style={{ color: '#E8A54C', fontSize: 12, marginBottom: 20, textAlign: 'center' }}>{pollError}</div>}
      {status === 'ready' && (
        <button onClick={() => setScreen('doc-ready')} style={{ marginTop: 12, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 44px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 4px 20px rgba(201,168,76,0.4)' }}>
          View Document →
        </button>
      )}
    </div>
  )
}
