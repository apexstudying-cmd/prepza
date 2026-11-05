import { useEffect, useState, type ComponentType } from 'react'
import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import type { DocumentDetail } from '../../types/documents'

type DocReadyRoute = 'document-study' | 'ai-tutor' | 'summary' | 'quiz' | 'flashcards' | 'podcast-player' | 'library'

export default function DocReadyScreen({ setScreen, activeDocumentId, TopBar }: { setScreen: (s: DocReadyRoute) => void; activeDocumentId: number | null; TopBar: ComponentType<any> }) {
  const { tokens: T } = useTheme()
  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) return
    api<DocumentDetail>(`/documents/${activeDocumentId}`)
      .then(setDoc)
      .catch(e => setLoadError(e instanceof ApiError ? e.message : 'Could not load document details.'))
  }, [activeDocumentId])

  const actions: { icon: string; label: string; sub: string; dest: DocReadyRoute }[] = [
    { icon: '🤖', label: 'Study with AI', sub: 'Ask questions about this doc', dest: 'document-study' },
    { icon: '❓', label: 'Ask Questions', sub: 'AI answers from your notes', dest: 'ai-tutor' },
    { icon: '📝', label: 'Summarize', sub: 'Condensed AI notes', dest: 'summary' },
    { icon: '🧠', label: 'Generate Quiz', sub: 'AI-generated practice quiz', dest: 'quiz' },
    { icon: '🃏', label: 'Flashcards', sub: 'AI-generated flashcard set', dest: 'flashcards' },
    { icon: '🎙️', label: 'Create Podcast', sub: 'AI-generated audio episode', dest: 'podcast-player' },
    { icon: '📚', label: 'Save to Library', sub: 'Access offline anytime', dest: 'library' },
  ]

  const fileTypeLabel = doc?.file_type ? doc.file_type.toUpperCase() : null
  const pageLabel = doc?.page_count != null ? `${doc.page_count} pages` : null
  const sizeLabel = doc?.file_size_bytes != null ? `${(doc.file_size_bytes / (1024 * 1024)).toFixed(1)} MB` : null
  const metaParts = [fileTypeLabel, pageLabel, sizeLabel].filter(Boolean)

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <TopBar title="Document Ready ✓" onBack={() => window.history.back()} />
        <div style={{ background: 'rgba(76,201,123,0.12)', border: '1px solid rgba(76,201,123,0.3)', borderRadius: 14, padding: '12px 14px', display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ fontSize: 24 }}>✅</span>
          <div>
            <div style={{ color: '#4CC97B', fontWeight: 700, fontSize: 13 }}>Processing Complete!</div>
            <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11 }}>Your document is ready to study</div>
          </div>
        </div>
      </div>
      <div style={{ padding: 18 }}>
        {loadError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 14 }}>{loadError}</div>}
        {/* Doc info */}
        <div style={{ background: T.card, borderRadius: 16, padding: 16, marginBottom: 20, boxShadow: '0 2px 10px rgba(0,0,0,0.06)', display: 'flex', gap: 14, alignItems: 'center' }}>
          <div style={{ width: 52, height: 52, background: 'rgba(201,68,68,0.1)', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26 }}>📕</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: 14, color: T.text }} className="line-clamp-1">{doc?.title || 'Loading…'}</div>
            <div style={{ fontSize: 12, color: T.textMuted, marginTop: 2 }}>{metaParts.length > 0 ? metaParts.join(' · ') : '—'}</div>
          </div>
        </div>
        <div style={{ fontWeight: 800, fontSize: 15, color: T.text, marginBottom: 12 }}>What would you like to do?</div>
        {actions.map((a, i) => (
          <button key={i} onClick={() => setScreen(a.dest)} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 14, background: T.card, border: '1px solid rgba(0,0,0,0.05)', borderRadius: 14, padding: '14px 16px', marginBottom: 8, cursor: 'pointer', textAlign: 'left', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
            <div style={{ width: 44, height: 44, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0 }}>{a.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: T.text }}>{a.label}</div>
              <div style={{ fontSize: 11, color: T.textMuted }}>{a.sub}</div>
            </div>
            <div style={{ color: T.textMuted }}>{Ic.chevR()}</div>
          </button>
        ))}
      </div>
    </div>
  )
}
