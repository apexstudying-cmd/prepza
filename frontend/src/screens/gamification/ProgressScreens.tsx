import { useEffect, useState } from 'react'

import { api, ApiError } from '../../lib/appApi'
import { formatStudyTime } from '../../lib/studyTime'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Pill from '../../ui/Pill'
import type {
  HowToEarnItem,
  StreakCalendarDay,
  StreakResponse,
  StudyTimeResponse,
  XpHistoryItem,
  XpProgressResponse,
} from '../../types/gamification'

type ProgressScreenNavigation = (screen: 'profile' | 'share-sheet') => void

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

export function XPProgressScreen({ setScreen }: { setScreen: ProgressScreenNavigation }) {
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

export function StudyStreakScreen({ setScreen }: { setScreen: ProgressScreenNavigation }) {
  const { tokens: T } = useTheme()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<StreakResponse | null>(null)
  const [viewMonth, setViewMonth] = useState<string | null>(null)
  // Selected day for the tap-to-reveal detail line below the calendar -
  // the `title` attribute on each tile only fires on desktop mouse hover
  // and does nothing on touch devices, so this is the actual mechanism
  // mobile users have for seeing a day's study duration.
  const [selectedDay, setSelectedDay] = useState<StreakCalendarDay | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    api<StreakResponse>('/streak' + (viewMonth ? `?month=${viewMonth}` : ''))
      .then(res => {
        if (cancelled) return
        setData(res)
        if (!viewMonth) setViewMonth(res.calendar_month)
      })
      .catch(err => { if (!cancelled) setError(err instanceof ApiError ? err.message : 'Failed to load streak') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [viewMonth])

  const current = data?.current_streak ?? 0
  const longest = data?.longest_streak ?? 0
  const days = data?.calendar ?? []
  const milestones = data?.milestones ?? []
  const unlockedMilestones = milestones.filter(m => m.done)
  const calendarMonth = data?.calendar_month ?? viewMonth ?? ''
  const startWeekday = data?.calendar_start_weekday ?? 0
  const earliestMonth = data?.earliest_month ?? null

  const realCurrentMonth = (() => { const n = new Date(); return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}` })()
  const atEarliest = !!earliestMonth && calendarMonth === earliestMonth
  const atCurrent = calendarMonth === realCurrentMonth
  const monthLabel = (() => {
    if (!calendarMonth) return ''
    const [y, m] = calendarMonth.split('-').map(Number)
    return new Date(y, m - 1, 1).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
  })()
  const shiftMonth = (dir: 1 | -1) => {
    if (!calendarMonth) return
    const [y, m] = calendarMonth.split('-').map(Number)
    const d = new Date(y, m - 1 + dir, 1)
    setSelectedDay(null)
    setViewMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`)
  }

  // GitHub-contributions-style shading: darker gold the longer the
  // student studied that day, rather than a flat studied/not color.
  const SHADE_LEVELS = [
    { color: '#F3F4F6', border: '1px solid #E5E7EB' }, // no activity
    { color: `${N.gold}35`, border: 'none' },           // < 15 min
    { color: `${N.gold}70`, border: 'none' },           // 15-45 min
    { color: `${N.gold}A8`, border: 'none' },           // 45-90 min
    { color: N.gold, border: 'none' },                  // 90+ min
  ]
  const shadeForSeconds = (seconds: number) => {
    if (!seconds || seconds <= 0) return SHADE_LEVELS[0]
    if (seconds < 900) return SHADE_LEVELS[1]
    if (seconds < 2700) return SHADE_LEVELS[2]
    if (seconds < 5400) return SHADE_LEVELS[3]
    return SHADE_LEVELS[4]
  }
  const formatStudyDuration = (seconds: number) => {
    if (!seconds || seconds <= 0) return 'No study time logged'
    const mins = Math.round(seconds / 60)
    if (mins < 60) return `Studied ${mins} min`
    const hrs = Math.floor(mins / 60)
    const remMins = mins % 60
    return remMins > 0 ? `Studied ${hrs}h ${remMins}m` : `Studied ${hrs}h`
  }

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
        <div style={{ background: N.navy, padding: '0 18px 24px', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Study Streak</div>
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
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Study Streak</div>
          </div>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: '#EF4444', padding: '0 24px', textAlign: 'center' }}>{error}</div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 24px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Study Streak</div>
        </div>
        <div style={{ display: 'flex', gap: 14 }}>
          <div style={{ flex: 1, background: 'rgba(255,255,255,0.08)', borderRadius: 14, padding: '14px 16px' }}>
            <div style={{ fontSize: 38, fontWeight: 800, color: N.gold, lineHeight: 1 }}>{current}</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)', marginTop: 4 }}>day streak 🔥</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginTop: 2 }}>Current</div>
          </div>
          <div style={{ flex: 1, background: 'rgba(255,255,255,0.08)', borderRadius: 14, padding: '14px 16px' }}>
            <div style={{ fontSize: 38, fontWeight: 800, color: 'rgba(255,255,255,0.9)', lineHeight: 1 }}>{longest}</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)', marginTop: 4 }}>days</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginTop: 2 }}>Personal best</div>
          </div>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
        <div style={{ background: T.card, borderRadius: 16, padding: '16px 16px', marginBottom: 16, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <button onClick={() => shiftMonth(-1)} disabled={atEarliest} style={{ width: 28, height: 28, border: 'none', borderRadius: 8, background: '#F3F4F6', cursor: atEarliest ? 'default' : 'pointer', opacity: atEarliest ? 0.35 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, color: T.text }}>‹</button>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text }}>{monthLabel}</div>
            <button onClick={() => shiftMonth(1)} disabled={atCurrent} style={{ width: 28, height: 28, border: 'none', borderRadius: 8, background: '#F3F4F6', cursor: atCurrent ? 'default' : 'pointer', opacity: atCurrent ? 0.35 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, color: T.text }}>›</button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 5 }}>
            {['S','M','T','W','T','F','S'].map((d, i) => <div key={i} style={{ textAlign: 'center', fontSize: 10, color: T.textMuted, fontWeight: 600, marginBottom: 4 }}>{d}</div>)}
            {Array.from({ length: startWeekday }).map((_, i) => <div key={`pad-${i}`} />)}
            {days.map((d, i) => {
              const shade = shadeForSeconds(d.study_seconds)
              const dateLabel = new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
              const tooltip = `${dateLabel} — ${d.is_future ? 'Upcoming' : formatStudyDuration(d.study_seconds)}`
              const isSelected = selectedDay?.date === d.date
              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => setSelectedDay(isSelected ? null : d)}
                  title={tooltip}
                  style={{ aspectRatio: '1', borderRadius: 6, background: shade.color, border: isSelected ? `2px solid ${N.navy}` : shade.border, opacity: d.is_future ? 0.35 : 1, transition: 'background 0.2s, border 0.15s', padding: 0, margin: 0, appearance: 'none', font: 'inherit', cursor: 'pointer' }}
                />
              )
            })}
          </div>
          {selectedDay && (
            <div style={{ marginTop: 10, padding: '8px 12px', background: `${N.gold}15`, borderRadius: 10, fontSize: 12, fontWeight: 600, color: T.text, textAlign: 'center' }}>
              {new Date(selectedDay.date).toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })} — {selectedDay.is_future ? 'Upcoming' : formatStudyDuration(selectedDay.study_seconds)}
            </div>
          )}
          <div style={{ display: 'flex', gap: 6, marginTop: 14, alignItems: 'center', justifyContent: 'flex-end' }}>
            <span style={{ fontSize: 10, color: T.textMuted }}>Less</span>
            {SHADE_LEVELS.map((lvl, i) => (
              <div key={i} style={{ width: 12, height: 12, borderRadius: 3, background: lvl.color, border: lvl.border }} />
            ))}
            <span style={{ fontSize: 10, color: T.textMuted }}>More</span>
          </div>
        </div>
        <div style={{ background: T.card, borderRadius: 16, padding: '14px 16px', marginBottom: 16, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 12 }}>Streak milestones{unlockedMilestones.length > 0 ? ` (${unlockedMilestones.length})` : ''}</div>
          {unlockedMilestones.length === 0 ? (
            <div style={{ fontSize: 12, color: T.textMuted, padding: '4px 0 2px' }}>No milestones reached yet — keep your streak going to unlock your first one.</div>
          ) : (
            <div style={{ maxHeight: 220, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }} className="scrollbar-hide">
              {unlockedMilestones.map((m, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
                  <div style={{ width: 36, height: 36, borderRadius: 10, background: `${N.gold}20`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <span style={{ fontSize: 16 }}>🏆</span>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 13, color: T.text }}>{m.days}-Day Streak</div>
                    <div style={{ fontSize: 11, color: T.textMuted }}>{m.label}</div>
                  </div>
                  <Pill text={m.xp} color={N.gold} />
                </div>
              ))}
            </div>
          )}
        </div>
        <button onClick={() => setScreen('share-sheet')} style={{ width: '100%', background: 'transparent', border: `1.5px solid ${N.gold}`, color: N.gold, fontWeight: 700, fontSize: 14, borderRadius: 16, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
          Share {current}-Day Streak
        </button>
        <div style={{ height: 'calc(96px + env(safe-area-inset-bottom, 0px))' }} />
      </div>
    </div>
  )
}

export function TimeStudiedScreen({ setScreen }: { setScreen: ProgressScreenNavigation }) {
  const { tokens: T } = useTheme()
  const [period, setPeriod] = useState<'day' | 'week' | 'month'>('week')
  const [data, setData] = useState<StudyTimeResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    api<StudyTimeResponse>(`/study-time?period=${period}`)
      .then(res => { if (!cancelled) setData(res) })
      .catch(err => { if (!cancelled) setError(err instanceof ApiError ? err.message : 'Failed to load study time') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [period])

  const totalLabel = data ? formatStudyTime(data.total_seconds) : '—'
  const periodLabel = period === 'day' ? 'today' : period === 'week' ? 'this week' : 'this month'

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 24px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Time Studied</div>
        </div>
        <div style={{ background: 'rgba(255,255,255,0.08)', borderRadius: 14, padding: '18px 16px', textAlign: 'center' }}>
          <div style={{ fontSize: 42, fontWeight: 800, color: N.gold, lineHeight: 1 }}>{loading ? '…' : totalLabel}</div>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)', marginTop: 6 }}>studied {periodLabel}</div>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
        {error && <div style={{ background: '#FEF2F2', color: '#B91C1C', borderRadius: 12, padding: '10px 14px', marginBottom: 14, fontSize: 12 }}>{error}</div>}
        <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
          {(['day', 'week', 'month'] as const).map(p => (
            <button key={p} onClick={() => setPeriod(p)} style={{ flex: 1, padding: '10px 0', borderRadius: 12, border: 'none', background: period === p ? N.gold : '#fff', color: period === p ? N.navy : T.textMuted, fontWeight: 700, fontSize: 13, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
            {p.charAt(0).toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>
        <button onClick={() => setScreen('share-sheet')} style={{ width: '100%', background: 'transparent', border: `1.5px solid ${N.gold}`, color: N.gold, fontWeight: 700, fontSize: 14, borderRadius: 16, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
          Share {totalLabel} Studied 🔥
        </button>
        <div style={{ height: 100 }} />
      </div>
    </div>
  )
}

// ─── FOLLOWERS / FOLLOWING ────────────────────────────────────────────────────
// ─── EMPTY & ERROR STATES ─────────────────────────────────────────────────────
