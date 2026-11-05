import { useEffect, useState } from 'react'

import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Pill from '../../ui/Pill'
import type { XpHistoryItem, XpProgressResponse } from '../../types/gamification'

function formatXpDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const startOfDay = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate())
  const diffDays = Math.round((startOfDay(now).getTime() - startOfDay(d).getTime()) / 86400000)
  if (diffDays <= 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  return `${diffDays} days ago`
}

export function XPProgressScreen({ setScreen }: { setScreen: (screen: 'profile') => void }) {
  const { tokens: T } = useTheme()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<XpProgressResponse | null>(null)
  const [history, setHistory] = useState<XpHistoryItem[]>([])
  const [page, setPage] = useState(1)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    api<XpProgressResponse>('/xp/progress?page=1')
      .then(res => {
        if (cancelled) return
        setData(res)
        setHistory(res.history)
        setPage(1)
        setHasMore(res.history.length >= 20)
      })
      .catch(err => { if (!cancelled) setError(err instanceof ApiError ? err.message : 'Failed to load XP progress') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const loadMore = () => {
    if (loadingMore || !hasMore) return
    const nextPage = page + 1
    setLoadingMore(true)
    api<XpProgressResponse>(`/xp/progress?page=${nextPage}`)
      .then(res => {
        setHistory(prev => [...prev, ...res.history])
        setPage(nextPage)
        setHasMore(res.history.length >= 20)
      })
      .catch(() => { /* keep existing history on failure */ })
      .finally(() => setLoadingMore(false))
  }

  const xpTotal = data?.xp_total ?? 0
  const level = data?.level ?? 1
  const levelTitle = data?.level_title ?? 'Scholar'
  const xpIntoLevel = data?.xp_into_level ?? 0
  const xpForLevelGap = data?.xp_for_level_gap ?? 1
  const nextLevelXp = data?.next_level_xp ?? 0
  const pct = xpForLevelGap > 0 ? (xpIntoLevel / xpForLevelGap) * 100 : 0
  const howToEarn = data?.how_to_earn ?? []

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
        <div style={{ background: N.navy, padding: '0 18px 24px', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>XP & Progress</div>
          </div>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: T.textMuted }}>Loading…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
        <div style={{ background: N.navy, padding: '0 18px 24px', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>XP & Progress</div>
          </div>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: '#EF4444', padding: '0 24px', textAlign: 'center' }}>{error}</div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 24px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>XP & Progress</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <div style={{ position: 'relative', width: 80, height: 80, flexShrink: 0 }}>
            <svg width="80" height="80" viewBox="0 0 80 80">
              <circle cx="40" cy="40" r="34" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="8" />
              <circle cx="40" cy="40" r="34" fill="none" stroke={N.gold} strokeWidth="8" strokeLinecap="round"
                strokeDasharray={`${2 * Math.PI * 34 * pct / 100} ${2 * Math.PI * 34}`} strokeDashoffset={2 * Math.PI * 34 * 0.25} />
            </svg>
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ fontWeight: 800, fontSize: 18, color: '#fff', lineHeight: 1 }}>{level}</div>
              <div style={{ fontSize: 9, color: N.gold, fontWeight: 700, letterSpacing: 0.5 }}>LEVEL</div>
            </div>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 20, color: '#fff', marginBottom: 2 }}>{levelTitle}</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)', marginBottom: 10 }}>{xpTotal.toLocaleString()} XP · {xpForLevelGap - xpIntoLevel} XP to Level {level + 1}</div>
            <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 99, height: 6, overflow: 'hidden' }}>
              <div style={{ background: `linear-gradient(90deg,${N.gold},${N.goldL})`, height: 6, width: `${pct}%`, borderRadius: 99, transition: 'width 1s ease' }} />
            </div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginTop: 4 }}>{xpForLevelGap - xpIntoLevel} XP to next level (Level {level + 1} at {nextLevelXp.toLocaleString()} XP total)</div>
          </div>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 18px' }} className="scrollbar-hide">
        <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 12 }}>Recent XP activity</div>
        {history.length === 0 && (
          <div style={{ fontSize: 13, color: T.textMuted, padding: '12px 0 20px' }}>No XP activity yet — study a document or complete a quiz to start earning.</div>
        )}
        {history.map((h, i) => (
          <div key={i} style={{ background: T.card, borderRadius: 14, padding: '12px 16px', marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
            <div style={{ width: 38, height: 38, background: `${N.gold}15`, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, flexShrink: 0 }}>{h.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{h.label}</div>
              <div style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>{formatXpDate(h.created_at)}</div>
            </div>
            <div style={{ fontWeight: 800, fontSize: 14, color: '#16A34A' }}>+{h.xp}</div>
          </div>
        ))}
        {hasMore && history.length > 0 && (
          <button onClick={loadMore} disabled={loadingMore} style={{ width: '100%', background: 'none', border: 'none', color: N.gold, fontWeight: 700, fontSize: 12, padding: '10px 0 4px', cursor: loadingMore ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
            {loadingMore ? 'Loading…' : 'Load more'}
          </button>
        )}
        <div style={{ fontWeight: 700, fontSize: 13, color: T.text, margin: '20px 0 12px' }}>How to earn XP</div>
        <div style={{ background: T.card, borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
          {howToEarn.map((h, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: i < howToEarn.length - 1 ? '1px solid #F3F4F6' : 'none' }}>
              <span style={{ fontSize: 13, color: T.text }}>{h.label}</span>
              <Pill text={h.xp} color={N.gold} />
            </div>
          ))}
        </div>
        <div style={{ height: 20 }} />
      </div>
    </div>
  )
}
