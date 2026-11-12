import { useEffect, useRef, useState, type ComponentType } from 'react'

import { api, ApiError } from '../../lib/appApi'
import { N } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import type { DocumentDetail } from '../../types/documents'
import PdfStudyCanvas from '../../crypto/PdfStudyCanvas'
import {
  getOfflineStudyDocumentUrl,
  getSavedStudyHubOffline,
  saveStudyHubDocumentOffline,
} from '../../offline/studyHubOffline'

type DocumentReaderScreenTarget = 'document-study'
type DocumentReaderScreenProps = {
  setScreen: (screen: DocumentReaderScreenTarget) => void
  activeDocumentId: number | null
  DOC_CACHE: Record<number, DocumentDetail>
  GenerationLoading: ComponentType<{ label: string }>
  GenerationError: ComponentType<{ error: string }>
}

export default function DocumentReaderScreen({ activeDocumentId, DOC_CACHE, GenerationLoading, GenerationError }: DocumentReaderScreenProps) {
  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [page, setPage] = useState(0)
  const [savedPage, setSavedPage] = useState(0)
  const [zoom, setZoom] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')
  const [offlineSrc, setOfflineSrc] = useState<string | null>(null)
  const readerRef = useRef<HTMLDivElement>(null)
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (activeDocumentId == null) { setLoading(false); setError('No document selected.'); return }
    let cancelled = false
    let objectUrl: string | null = null
    setLoading(true); setError(''); setOfflineSrc(null); setDoc(null)
    const loadLocal = async () => {
      const userId = Number(localStorage.getItem('prepza-offline-user-id') || 0)
      if (!Number.isInteger(userId) || userId <= 0) throw new Error('No offline study account is available.')
      const meta = await getSavedStudyHubOffline(activeDocumentId, userId)
      if (!meta) throw new Error('This document has not been saved for offline study.')
      const url = await getOfflineStudyDocumentUrl(activeDocumentId, userId)
      if (!url) throw new Error('The saved offline study copy is unavailable.')
      objectUrl = url
      try {
        const storedPage = Number(localStorage.getItem(`prepza-offline-reading:${userId}:${activeDocumentId}`) || 0)
        if (Number.isInteger(storedPage) && storedPage >= 0) {
          setPage(storedPage)
          setSavedPage(storedPage)
        }
      } catch (_) {}
      return {
        id: activeDocumentId,
        title: meta.title || 'Saved study document',
        original_filename: meta.title || 'Study document',
        status: 'ready',
        file_type: meta.fileType || 'pdf',
        file_size_bytes: null,
        page_count: meta.pageCount || null,
        error_message: null,
        view_url: null,
        materials: [],
        created_at: new Date(meta.savedAt).toISOString(),
      } as DocumentDetail
    }
    const load = async () => {
      try {
        // The reader should consume the upload-time local Blob first, even
        // while online. Only records without a complete local copy need the
        // server-rendered page route or a document-detail lookup.
        try {
          const localDoc = await loadLocal()
          if (!cancelled) {
            setDoc(localDoc)
            setOfflineSrc(objectUrl)
          }
          // Keep online-only reader actions and the Study Hub heartbeat working
          // without waiting for /me before the locally stored document opens.
          if (navigator.onLine) {
            void api<{csrf_token:string}>('/me')
              .then(me => { if (!cancelled) setCsrfToken(me.csrf_token) })
              .catch(() => {})
          }
          return
        } catch (localError) {
          if (!navigator.onLine) throw localError
          if (objectUrl) {
            URL.revokeObjectURL(objectUrl)
            objectUrl = null
          }
        }

        const [detail, progress, me] = await Promise.all([
          api<DocumentDetail>(`/documents/${activeDocumentId}`),
          api<{page_num:number}>(`/documents/${activeDocumentId}/reading`),
          api<{csrf_token:string}>('/me'),
        ])
        if (cancelled) return
        setDoc(detail)
        setPage(progress.page_num || 0)
        setSavedPage(progress.page_num || 0)
        setCsrfToken(me.csrf_token)
        // The native reader is also an entry point for records that did not
        // already have a local copy. Persist their bytes for the next open.
        void saveStudyHubDocumentOffline(activeDocumentId).catch(() => {})
      } catch (e) {
        if (!cancelled) setError(e instanceof ApiError ? e.message : 'Could not open this document.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [activeDocumentId])

  useEffect(() => {
    if (activeDocumentId == null || !csrfToken) return
    const ping = () => {
      if (!navigator.onLine || document.visibilityState !== 'visible') return
      api('/study-time/heartbeat', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ feature: 'reading', document_id: activeDocumentId }),
      }).catch(() => {})
    }
    ping()
    const interval = setInterval(ping, 20000)
    return () => clearInterval(interval)
  }, [activeDocumentId, csrfToken])

  useEffect(() => {
    if (activeDocumentId == null || !csrfToken || offlineSrc || page === savedPage) return
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(() => {
      if (!navigator.onLine) return
      api(`/documents/${activeDocumentId}/reading`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ page_num: page }),
      }).then(() => setSavedPage(page)).catch(() => {})
    }, 350)
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    }
  }, [activeDocumentId, csrfToken, page, savedPage, offlineSrc])

  useEffect(() => {
    const root = readerRef.current
    if (!root || !doc?.page_count || offlineSrc) return
    const nodes = Array.from(root.querySelectorAll<HTMLElement>('[data-reader-page]'))
    if (!nodes.length) return
    const observer = new IntersectionObserver(entries => {
      const visible = entries
        .filter(entry => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
      if (!visible) return
      const nextPage = Number((visible.target as HTMLElement).dataset.readerPage)
      if (Number.isInteger(nextPage)) setPage(nextPage)
    }, { root, threshold: [0.25, 0.5, 0.75] })
    nodes.forEach(node => observer.observe(node))
    return () => observer.disconnect()
  }, [doc?.page_count, loading, offlineSrc])

  if (loading) return <GenerationLoading label="Opening your document…" />
  if (error) return <GenerationError error={error} />
  if (!doc || activeDocumentId == null) return <GenerationError error="Document unavailable." />
  if (doc.file_type !== 'pdf') return <GenerationError error="Native reading currently supports PDF documents only." />

  if (offlineSrc) {
    return <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', background: '#111827' }}>
      <div style={{ background: N.navy, padding: '10px 14px 12px', flexShrink: 0, zIndex: 5 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => window.history.back()} aria-label="Back" style={{ width: 36, height: 36, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ color: '#fff', fontWeight: 800, fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.title}</div>
            <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 10, marginTop: 2 }}>Offline study copy</div>
          </div>
          <div style={{ color: N.gold, fontSize: 10, fontWeight: 800 }}>OFFLINE</div>
        </div>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <PdfStudyCanvas
          src={offlineSrc}
          title={doc.title}
          storageKey={`offline:${Number(localStorage.getItem('prepza-offline-user-id') || 0)}:${activeDocumentId ?? 0}`}
          onPageChange={p => {
            const nextPage = Math.max(0, p - 1)
            setPage(nextPage)
            try {
              const userId = Number(localStorage.getItem('prepza-offline-user-id') || 0)
              if (Number.isInteger(userId) && userId > 0 && activeDocumentId != null) {
                localStorage.setItem(`prepza-offline-reading:${userId}:${activeDocumentId}`, String(nextPage))
              }
            } catch (_) {}
          }}
        />
      </div>
    </div>
  }

  const count = Math.max(1, doc.page_count || 1)
  const current = Math.min(Math.max(page, 0), count - 1)
  const progress = ((current + 1) / count) * 100

  return <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', background: '#111827' }}>
    <div style={{ background: N.navy, padding: '10px 14px 12px', flexShrink: 0, zIndex: 5 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button onClick={() => window.history.back()} aria-label="Back" style={{ width: 36, height: 36, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ color: '#fff', fontWeight: 800, fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.title}</div>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 10, marginTop: 2 }}>Page {current + 1} of {count}</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
          <button onClick={() => setZoom(z => Math.max(0.75, Math.round((z - 0.1) * 10) / 10))} aria-label="Zoom out" style={{ width: 30, height: 30, border: 'none', borderRadius: 8, background: 'rgba(255,255,255,0.08)', color: '#fff', fontSize: 17, cursor: 'pointer' }}>−</button>
          <button onClick={() => setZoom(1)} aria-label="Fit width" style={{ minWidth: 42, height: 30, border: 'none', borderRadius: 8, background: 'rgba(255,255,255,0.08)', color: 'rgba(255,255,255,0.8)', fontSize: 10, fontWeight: 800, cursor: 'pointer' }}>{Math.round(zoom * 100)}%</button>
          <button onClick={() => setZoom(z => Math.min(2, Math.round((z + 0.1) * 10) / 10))} aria-label="Zoom in" style={{ width: 30, height: 30, border: 'none', borderRadius: 8, background: 'rgba(255,255,255,0.08)', color: '#fff', fontSize: 17, cursor: 'pointer' }}>+</button>
        </div>
        <div style={{ color: 'rgba(255,255,255,0.65)', fontSize: 10, fontWeight: 800, flexShrink: 0 }}>{Math.round(progress)}%</div>
      </div>
      <div style={{ marginTop: 10, height: 3, background: 'rgba(255,255,255,0.12)', borderRadius: 99, overflow: 'hidden' }}><div style={{ width: `${progress}%`, height: '100%', background: N.gold, transition: 'width 0.15s ease-out' }} /></div>
    </div>
    <div ref={readerRef} style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden', padding: '12px 8px 28px', WebkitOverflowScrolling: 'touch', overscrollBehaviorY: 'contain' }} className="scrollbar-hide">
      <div style={{ width: 'min(100%, 980px)', margin: '0 auto' }}>
        {Array.from({ length: count }, (_, index) => {
          const pageUrl = `/documents/${activeDocumentId}/reading/page/${index}`
          const isCurrent = index === current
          return <div key={pageUrl} data-reader-page={index} style={{ margin: '0 auto 12px', width: '100%', display: 'flex', justifyContent: 'center', scrollMarginTop: 12, position: 'relative' }}>
            <div style={{ width: '100%', overflowX: zoom > 1 ? 'auto' : 'hidden' }}>
              <img src={pageUrl} alt={`Page ${index + 1} of ${doc.title}`} loading={index < 2 ? 'eager' : 'lazy'} decoding="async" style={{ display: 'block', width: '100%', height: 'auto', background: '#fff', boxShadow: '0 3px 18px rgba(0,0,0,0.28)', outline: isCurrent ? `1px solid ${N.gold}55` : 'none' }} />
            </div>
          </div>
        })}
      </div>
    </div>
  </div>
}
