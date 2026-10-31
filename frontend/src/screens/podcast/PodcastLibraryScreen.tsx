import { useEffect, useState, type ComponentType, type ReactNode } from 'react'

import { api } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import type { PodcastItem } from '../../types/podcast'
import { podcastColor, podcastDuration } from '../../types/podcast'
import { Ic } from '../../ui/icons'

type PodcastLibraryScreenProps = {
  setScreen: (screen: 'home' | 'podcast-player') => void
  setActiveDocumentId: (id: number | null) => void
  DelayedScreenSkeleton: ComponentType<{ children: ReactNode }>
  SkeletonPodcastLibrary: ComponentType
  EmptyState: ComponentType<{ icon: string; title: string; sub: string }>
  ErrorState: ComponentType
}

// Keep this cache beside the screen that owns it. It intentionally survives
// navigation away from and back to the Podcast Library during this app session.
const PODCAST_LIBRARY_CACHE: { podcastList?: PodcastItem[] } = {}

export default function PodcastLibraryScreen({
  setScreen,
  setActiveDocumentId,
  DelayedScreenSkeleton,
  SkeletonPodcastLibrary,
  EmptyState,
  ErrorState,
}: PodcastLibraryScreenProps) {
  const { tokens: T } = useTheme()
  const [podcastList, setPodcastList] = useState<PodcastItem[]>(PODCAST_LIBRARY_CACHE.podcastList ?? [])
  const [loading, setLoading] = useState(PODCAST_LIBRARY_CACHE.podcastList === undefined)
  const [error, setError] = useState('')

  useEffect(() => {
    api<{ podcasts: PodcastItem[] }>('/podcasts')
      .then(res => { setPodcastList(res.podcasts); PODCAST_LIBRARY_CACHE.podcastList = res.podcasts })
      .catch(() => setError('Could not load your podcasts.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <DelayedScreenSkeleton><SkeletonPodcastLibrary /></DelayedScreenSkeleton>

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 18, color: '#fff' }}>Study Podcasts 🎙️</span>
        </div>
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>AI-generated from your notes</div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 16 }} className="scrollbar-hide">
        {error ? (
          <ErrorState />
        ) : podcastList.length === 0 ? (
          <EmptyState icon="🎙️" title="No podcasts yet" sub="Open a document and generate a study podcast from your notes to see it here." />
        ) : (
          <>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 12 }}>Your Episodes</div>
            {podcastList.map((p) => {
              const color = podcastColor(p.document_id)
              return (
                <div key={p.document_id} onClick={() => { setActiveDocumentId(p.document_id); setScreen('podcast-player') }} style={{ display: 'flex', gap: 14, alignItems: 'center', background: T.card, borderRadius: 14, padding: '13px 14px', marginBottom: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', cursor: 'pointer' }}>
                  <div style={{ width: 52, height: 52, background: `linear-gradient(135deg,${color},${color}99)`, borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, color: '#fff', fontWeight: 800, flexShrink: 0 }}>🎙️</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 13, color: T.text }} className="line-clamp-1">{p.title}</div>
                    <div style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>{p.audio_status === 'ready' ? podcastDuration(p.duration_seconds) : 'Processing…'}</div>
                  </div>
                  <div style={{ color: N.gold }}>{Ic.play()}</div>
                </div>
              )
            })}
          </>
        )}
      </div>
    </div>
  )
}
