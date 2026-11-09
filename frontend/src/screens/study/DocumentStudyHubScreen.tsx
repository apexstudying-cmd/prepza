import { useEffect, useState, type ComponentType } from 'react'

import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import type { DocumentDetail } from '../../types/documents'
import {
  getSavedStudyHubOffline,
  listSavedStudyHubOffline,
  saveStudyHubDocumentOffline,
} from '../../offline/studyHubOffline'
import { listOfflineGeneratedMaterials } from '../../offline/generatedMaterials'

type DocumentStudyHubScreenTarget =
  | 'study-materials'
  | 'document-reader'
  | 'ai-tutor'
  | 'summary'
  | 'flashcards'
  | 'quiz'
  | 'mind-map'
  | 'podcast-player'

export default function DocumentStudyHubScreen({
  setScreen,
  activeDocumentId,
  LoadingView,
  ErrorView,
  DOC_CACHE,
}: {
  setScreen: (s: DocumentStudyHubScreenTarget) => void
  activeDocumentId: number | null
  LoadingView: ComponentType<{ label: string }>
  ErrorView: ComponentType<{ error: string }>
  DOC_CACHE: Record<number, DocumentDetail>
}) {
  const { tokens: T } = useTheme()
  const [document, setDocument] = useState<DocumentDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [readingPage, setReadingPage] = useState(0)
  const [saveOfflineBusy, setSaveOfflineBusy] = useState(false)
  const [savedToLib, setSavedToLib] = useState(false)

  useEffect(() => {
    let cancelled = false
    if (activeDocumentId == null) {
      setLoading(false)
      setError('No document selected.')
      return
    }
    setLoading(true)
    setError('')
    const load = async () => {
      try {
        // My Study source files are persisted as complete IndexedDB Blobs during
        // upload. Prefer that local package before asking Flask for document
        // detail/reading state; this avoids re-serving the same study item.
        const localUserId = Number(localStorage.getItem('prepza-offline-user-id') || 0)
        if (Number.isInteger(localUserId) && localUserId > 0) {
          const localRows = await listSavedStudyHubOffline(localUserId)
          const saved = localRows.find(row => row.documentId === activeDocumentId)
          if (saved) {
            const cached = await listOfflineGeneratedMaterials()
            const offlineMaterials = cached.flatMap(row => {
              const match = row.path.match(/^\/documents\/(\d+)\/materials\/(\d+)$/)
              if (!match || Number(match[1]) !== activeDocumentId) return []
              const payload = row.payload as any
              if (!payload?.type || payload?.status !== 'ready') return []
              return [{
                id: Number(match[2]),
                type: payload.type,
                status: 'ready',
                parameters: payload.parameters || {},
              }]
            })
            if (cancelled) return
            setDocument({
              id: activeDocumentId,
              title: saved.title || 'Saved study document',
              original_filename: saved.title || 'Study document',
              status: 'ready',
              file_type: saved.fileType || 'pdf',
              file_size_bytes: null,
              page_count: saved.pageCount || null,
              error_message: null,
              view_url: null,
              materials: offlineMaterials,
              created_at: new Date(saved.savedAt).toISOString(),
            })
            let offlinePage = 0
            try {
              const storedPage = Number(localStorage.getItem(`prepza-offline-reading:${localUserId}:${activeDocumentId}`) || 0)
              if (Number.isInteger(storedPage) && storedPage >= 0) offlinePage = storedPage
            } catch (_) {}
            setReadingPage(offlinePage)
            return
          }
        }

        // Documents sourced from Library or older non-local records retain the
        // existing online path. Their behavior is deliberately unchanged.
        if (!navigator.onLine) throw new Error('offline')
        const [data, progress] = await Promise.all([
          api<DocumentDetail>(`/documents/${activeDocumentId}`),
          api<{ page_num: number }>(`/documents/${activeDocumentId}/reading`),
        ])
        if (cancelled) return
        // Study Hub is local-first: do not present the item as ready until its
        // complete source has been persisted locally. This also repairs older
        // Study Hub items created before the automatic-ingestion contract.
        setSaveOfflineBusy(true)
        try {
          await saveStudyHubDocumentOffline(activeDocumentId)
          if (cancelled) return
          setSavedToLib(true)
        } finally {
          if (!cancelled) setSaveOfflineBusy(false)
        }
        setDocument(data)
        setReadingPage(Math.max(0, progress.page_num || 0))
      } catch (err) {
        try {
          const userId = Number(localStorage.getItem('prepza-offline-user-id') || 0)
          if (!Number.isInteger(userId) || userId <= 0) throw new Error('No offline account')
          const saved = await getSavedStudyHubOffline(activeDocumentId, userId)
          if (!saved) throw new Error('Not saved offline')
          if (cancelled) return
          const cached = await listOfflineGeneratedMaterials()
          const offlineMaterials = cached.flatMap(row => {
            const match = row.path.match(/^\/documents\/(\d+)\/materials\/(\d+)$/)
            if (!match || Number(match[1]) !== activeDocumentId) return []
            const payload = row.payload as any
            if (!payload?.type || payload?.status !== 'ready') return []
            return [{
              id: Number(match[2]),
              type: payload.type,
              status: 'ready',
              parameters: payload.parameters || {},
            }]
          })
setDocument({
            id: activeDocumentId,
            title: saved.title || 'Saved study document',
            original_filename: saved.title || 'Study document',
            status: 'ready',
            file_type: saved.fileType || 'pdf',
            file_size_bytes: null,
            page_count: saved.pageCount || null,
            error_message: null,
            view_url: null,
            materials: offlineMaterials,
            created_at: new Date(saved.savedAt).toISOString(),
          })
          let offlinePage = 0
          try {
            const storedPage = Number(localStorage.getItem(`prepza-offline-reading:${userId}:${activeDocumentId}`) || 0)
            if (Number.isInteger(storedPage) && storedPage >= 0) offlinePage = storedPage
          } catch (_) {}
          setReadingPage(offlinePage)
          return
        } catch (_) {
          if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not open this document.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [activeDocumentId])

  if (loading) return <LoadingView label="Opening your document…" />
  if (error || !document) return <ErrorView error={error || 'Document unavailable.'} />

  const readyMaterials = (document.materials || []).filter(m => m.status === 'ready')
  const materialMeta: Record<string, { label: string; icon: string; screen: DocumentStudyHubScreenTarget }> = {
    summary: { label: 'Summary', icon: '▤', screen: 'summary' },
    flashcards: { label: 'Flashcards', icon: '▦', screen: 'flashcards' },
    quiz: { label: 'Practice Questions', icon: '?', screen: 'quiz' },
    practice_questions: { label: 'Practice Questions', icon: '?', screen: 'quiz' },
    mind_map: { label: 'Mind Map', icon: '⌘', screen: 'mind-map' },
    mindmap: { label: 'Mind Map', icon: '⌘', screen: 'mind-map' },
    podcast: { label: 'Podcast', icon: '◉', screen: 'podcast-player' },
  }

  const openMaterial = (material: { id: number; type: string }) => {
    const key = material.type.toLowerCase().replace(/-/g, '_')
    try {
      sessionStorage.setItem('prepza-open-material', JSON.stringify({
        documentId: activeDocumentId,
        materialId: material.id,
        type: key,
      }))
    } catch {}
    setScreen(materialMeta[key]?.screen || 'document-reader')
  }

  const createOptions: Array<{ type: string; label: string; description: string; icon: string; screen: DocumentStudyHubScreenTarget }> = [
    { type: 'summary', label: 'Summary', description: 'Condense the key ideas and explanations.', icon: '▤', screen: 'summary' },
    { type: 'flashcards', label: 'Flashcards', description: 'Turn important concepts into active recall cards.', icon: '▦', screen: 'flashcards' },
    { type: 'practice_questions', label: 'Practice Questions', description: 'Generate questions to test your understanding.', icon: '?', screen: 'quiz' },
    { type: 'mind_map', label: 'Mind Map', description: 'See the concepts and how they connect.', icon: '⌘', screen: 'mind-map' },
    { type: 'podcast', label: 'Podcast', description: 'Listen to an explanation based on this document.', icon: '◉', screen: 'podcast-player' },
  ]

  return <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
    <div style={{ background: N.navy, padding: '12px 18px 22px', flexShrink: 0 }}>
      <button onClick={() => setScreen('study-materials')} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.75)', padding: 0, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'Plus Jakarta Sans', fontSize: 11, fontWeight: 700 }}>
        {Ic.back()} My Study
      </button>
      <div style={{ marginTop: 18 }}>
        <div style={{ color: '#fff', fontSize: 20, fontWeight: 850, lineHeight: 1.25 }} className="line-clamp-2">{document.title}</div>
        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11, marginTop: 6 }}>
          {document.page_count ? `${document.page_count} pages` : 'Document'}{document.file_type ? ` · ${document.file_type.toUpperCase()}` : ''}
        </div>
        {document.page_count ? (() => {
          const studiedPercent = Math.min(100, Math.round((Math.min(readingPage + 1, document.page_count) / document.page_count) * 100))
          return <div style={{ marginTop: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: 'rgba(255,255,255,0.62)', fontSize: 10, marginBottom: 5 }}>
              <span>Study progress</span><span>{studiedPercent}%</span>
            </div>
            <div style={{ height: 5, borderRadius: 999, background: 'rgba(255,255,255,0.12)', overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${studiedPercent}%`, background: N.gold, borderRadius: 999 }} />
            </div>
          </div>
        })() : null}
      </div>
    </div>

    <div style={{ flex: 1, overflowY: 'auto', padding: 16 }} className="scrollbar-hide">
      <button onClick={() => setScreen('document-reader')} style={{ width: '100%', background: `linear-gradient(135deg, ${N.navy}, ${N.navy3})`, border: 'none', borderRadius: 17, padding: '17px 16px', color: '#fff', textAlign: 'left', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 44, height: 44, borderRadius: 13, background: 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>▤</div>
          <div style={{ flex: 1 }}><div style={{ fontWeight: 850, fontSize: 14 }}>Continue Reading</div><div style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)', marginTop: 3 }}>Read this document in Prepza</div></div>
          <span style={{ fontSize: 20 }}>›</span>
        </div>
      </button>

      <section style={{ marginBottom: 22 }}>
        <div style={{ fontWeight: 850, fontSize: 14, color: T.text, marginBottom: 10 }}>Study with Morio</div>
        <button onClick={() => setScreen('ai-tutor')} style={{ width: '100%', background: T.card, border: `1px solid ${T.border}`, borderRadius: 15, padding: 14, display: 'flex', alignItems: 'center', gap: 12, textAlign: 'left', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
          <div style={{ width: 42, height: 42, borderRadius: 12, background: `${N.gold}18`, color: N.gold, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 19, fontWeight: 900 }}>✦</div>
          <div style={{ flex: 1 }}><div style={{ color: T.text, fontWeight: 800, fontSize: 13 }}>Ask anything about these notes</div><div style={{ color: T.textMuted, fontSize: 11, marginTop: 3 }}>Use Morio while this document is your study context.</div></div>
          <span style={{ color: T.textMuted }}>›</span>
        </button>
      </section>

      <section>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <div style={{ fontWeight: 850, fontSize: 14, color: T.text }}>Your Study Materials</div>
          <button onClick={() => setShowCreate(true)} style={{ background: 'none', border: 'none', color: N.gold, fontWeight: 800, fontSize: 11, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>+ Create</button>
        </div>
        {readyMaterials.length === 0 ? (
          <div style={{ background: T.card, border: `1px dashed ${T.border}`, borderRadius: 15, padding: 18, textAlign: 'center' }}>
            <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.5 }}>Nothing has been created from this document yet.</div>
            <button onClick={() => setShowCreate(true)} style={{ marginTop: 11, background: N.gold, color: N.navy, border: 'none', borderRadius: 10, padding: '8px 13px', fontWeight: 850, fontSize: 11, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Create Study Material</button>
          </div>
        ) : readyMaterials.map((m, i) => {
          const meta = materialMeta[m.type.toLowerCase().replace(/-/g, '_')] || { label: m.type.replace(/_/g, ' '), icon: '•', screen: 'document-reader' as Screen }
          const variantLabel = meta.label
          return <button key={m.id} onClick={() => openMaterial(m)} style={{ width: '100%', background: T.card, border: `1px solid ${T.border}`, borderRadius: 15, padding: 14, marginBottom: 9, display: 'flex', alignItems: 'center', gap: 12, textAlign: 'left', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
            <div style={{ width: 42, height: 42, borderRadius: 12, background: `${N.navy}0D`, color: N.navy, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, fontWeight: 900 }}>{meta.icon}</div>
            <div style={{ flex: 1, minWidth: 0 }}><div style={{ color: T.text, fontWeight: 800, fontSize: 13, textTransform: 'capitalize' }}>{variantLabel}</div><div style={{ color: T.textMuted, fontSize: 10, marginTop: 3 }}>Ready to replay</div></div>
            <span style={{ color: T.textMuted }}>›</span>
          </button>
        })}
      </section>
      <div style={{ height: 'calc(90px + env(safe-area-inset-bottom, 0px))' }} />
    </div>

    {showCreate && <div onClick={() => setShowCreate(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.48)', zIndex: 100, display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
      <div onClick={e => e.stopPropagation()} style={{ width: '100%', maxWidth: 520, maxHeight: '82vh', overflowY: 'auto', background: T.card, borderRadius: '22px 22px 0 0', padding: '18px 16px calc(22px + env(safe-area-inset-bottom, 0px))' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}><div><div style={{ color: T.text, fontWeight: 850, fontSize: 16 }}>Create Study Material</div><div style={{ color: T.textMuted, fontSize: 11, marginTop: 3 }}>Choose what you want to make from this document.</div></div><button onClick={() => setShowCreate(false)} style={{ background: T.pageBg, border: 'none', borderRadius: 10, width: 34, height: 34, cursor: 'pointer', color: T.text }}>{Ic.close()}</button></div>
        {createOptions.map(option => <button key={option.type} onClick={() => { setShowCreate(false); setScreen(option.screen) }} style={{ width: '100%', background: T.pageBg, border: `1px solid ${T.border}`, borderRadius: 14, padding: 13, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 12, textAlign: 'left', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}><div style={{ width: 40, height: 40, borderRadius: 11, background: `${N.gold}18`, color: N.gold, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900 }}>{option.icon}</div><div><div style={{ color: T.text, fontWeight: 800, fontSize: 12 }}>{option.label}</div><div style={{ color: T.textMuted, fontSize: 10, marginTop: 3 }}>{option.description}</div></div></button>)}
      </div>
    </div>}
  </div>
}
