import { useEffect, useState } from 'react'
import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Pill from '../../ui/Pill'
import type { Achievement } from '../../types/gamification'

type AchievementsResponse = { unlocked_count: number; total_count: number; achievements: Achievement[] }

function formatAchievementDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function AchievementsScreen({ setScreen }: { setScreen: (s: 'profile' | 'share-sheet') => void }) {
  const { tokens: T } = useTheme()
  const [sharing, setSharing] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [achievementsList, setAchievementsList] = useState<Achievement[]>([])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    api<AchievementsResponse>('/achievements')
      .then(res => { if (!cancelled) setAchievementsList(res.achievements) })
      .catch(err => { if (!cancelled) setError(err instanceof ApiError ? err.message : 'Failed to load achievements') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const unlocked = achievementsList.filter(a => a.done)
  const locked = achievementsList.filter(a => !a.done)

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
        <div style={{ background: N.navy, padding: '0 18px 16px', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Achievements</div>
          </div>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: T.textMuted }}>Loading…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
        <div style={{ background: N.navy, padding: '0 18px 16px', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Achievements</div>
          </div>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: '#EF4444', padding: '0 24px', textAlign: 'center' }}>{error}</div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, background: T.pageBg }}>
      {sharing && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 200, display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
          <div style={{ width: 390, background: T.card, borderRadius: '24px 24px 0 0', padding: '24px 20px 32px' }}>
            <div style={{ width: 40, height: 4, background: '#E5E7EB', borderRadius: 99, margin: '0 auto 20px' }} />
            {(() => { const a = achievementsList.find(x => x.code === sharing)!; return (
              <div>
                <div style={{ background: N.navy, borderRadius: 16, padding: '20px', marginBottom: 16, textAlign: 'center' }}>
                  <div style={{ fontSize: 40, marginBottom: 10 }}>{a.icon}</div>
                  <div style={{ fontWeight: 800, fontSize: 16, color: '#fff', marginBottom: 4 }}>Achievement Unlocked</div>
                  <div style={{ fontWeight: 700, fontSize: 20, color: N.gold, marginBottom: 8 }}>{a.name}</div>
                  <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>{a.desc}</div>
                  <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid rgba(255,255,255,0.1)', fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>Join me on Prepza · prepza.app</div>
                </div>
                <div style={{ display: 'flex', gap: 10 }}>
                  <button onClick={() => setScreen('share-sheet')} style={{ flex: 1, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Share</button>
                  <button onClick={() => setSharing(null)} style={{ flex: 1, background: '#F3F4F6', color: T.text, fontWeight: 700, fontSize: 14, border: 'none', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Close</button>
                </div>
              </div>
            ) })()}
          </div>
        </div>
      )}
      <div style={{ background: N.navy, padding: '0 18px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Achievements</div>
          <div style={{ marginLeft: 'auto' }}><Pill text={`${unlocked.length} of ${achievementsList.length}`} color={N.gold} /></div>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 18px' }} className="scrollbar-hide">
        <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 12 }}>Unlocked ({unlocked.length})</div>
        {unlocked.map(a => (
          <div key={a.code} style={{ background: T.card, borderRadius: 16, padding: '14px 16px', marginBottom: 10, border: `1.5px solid ${N.gold}30`, boxShadow: `0 4px 16px ${N.gold}10`, display: 'flex', gap: 12, alignItems: 'center' }}>
            <div style={{ width: 48, height: 48, background: `${N.gold}15`, borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, flexShrink: 0 }}>{a.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 14, color: T.text }}>{a.name}</div>
              <div style={{ fontSize: 12, color: T.textMuted, marginTop: 2 }}>{a.desc}</div>
              <div style={{ fontSize: 11, color: T.textMuted, marginTop: 4 }}>Achieved {formatAchievementDate(a.unlocked_at)}</div>
            </div>
            <button onClick={() => setSharing(a.code)} style={{ background: '#F3F4F6', border: 'none', borderRadius: 8, padding: '6px 12px', cursor: 'pointer', fontSize: 12, fontWeight: 600, color: T.text, fontFamily: 'Plus Jakarta Sans', flexShrink: 0 }}>Share</button>
          </div>
        ))}
        <div style={{ fontWeight: 700, fontSize: 13, color: T.text, margin: '20px 0 12px' }}>In progress ({locked.length})</div>
        {locked.map(a => (
          <div key={a.code} style={{ background: T.card, borderRadius: 16, padding: '14px 16px', marginBottom: 10, opacity: 0.7, boxShadow: '0 2px 6px rgba(0,0,0,0.04)', display: 'flex', gap: 12, alignItems: 'center' }}>
            <div style={{ width: 48, height: 48, background: '#F3F4F6', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, flexShrink: 0, filter: 'grayscale(1)', opacity: 0.5 }}>{a.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 14, color: T.textMuted }}>{a.name}</div>
              <div style={{ fontSize: 12, color: T.textMuted, marginTop: 2 }}>{a.desc}</div>
              <div style={{ background: '#F3F4F6', borderRadius: 99, height: 5, marginTop: 8, overflow: 'hidden' }}>
                <div style={{ background: '#D1D5DB', height: 5, width: `${a.total > 0 ? (a.progress / a.total) * 100 : 0}%`, borderRadius: 99 }} />
              </div>
              <div style={{ fontSize: 11, color: T.textMuted, marginTop: 4 }}>{a.progress} / {a.total}</div>
            </div>
          </div>
        ))}
        <div style={{ height: 'calc(96px + env(safe-area-inset-bottom, 0px))' }} />
      </div>
    </div>
  )
}
