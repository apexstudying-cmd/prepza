import { useEffect, useState } from 'react'
import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import { formatStudyTime } from '../../lib/studyTime'
import type { StudyTimeResponse } from '../../types/gamification'

export default function TimeStudiedScreen({ setScreen }: { setScreen: (s: 'profile' | 'share-sheet') => void }) {
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
