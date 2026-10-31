import { useEffect, useState, type ComponentType } from 'react'
import { api } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Pill from '../../ui/Pill'
import type { FollowListUser, FollowRequestItem } from '../../types/social'

function FollowListScreen({ mode, setScreen, targetUserId, setActiveProfileUserId, setActiveProfileName, EmptyState }: {
  mode: 'followers' | 'following'
  setScreen: (s: 'student-profile' | 'explore') => void
  targetUserId: number | null
  setActiveProfileUserId?: (id: number) => void
  setActiveProfileName?: (name: string) => void
  EmptyState: ComponentType<{ icon: string; title: string; sub: string; action?: string; onAction?: () => void }>
}) {
  const { tokens: T } = useTheme()
  const [search, setSearch] = useState('')
  const [people, setPeople] = useState<FollowListUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<Record<number, boolean>>({})
  const [csrfToken, setCsrfToken] = useState('')

  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  useEffect(() => {
    if (targetUserId == null) { setLoading(false); setError('No student selected.'); return }
    setLoading(true)
    setError('')
    const key = mode // 'followers' | 'following'
    api<{ page: number; followers?: FollowListUser[]; following?: FollowListUser[] }>(`/users/${targetUserId}/${key}?page=1`)
      .then(res => setPeople((mode === 'followers' ? res.followers : res.following) || []))
      .catch(() => setError(`Could not load ${mode}.`))
      .finally(() => setLoading(false))
  }, [mode, targetUserId])

  const filtered = people.filter(p => !search || p.display_name.toLowerCase().includes(search.toLowerCase()))

  const toggle = async (person: FollowListUser) => {
    if (busy[person.user_id]) return
    setBusy(b => ({ ...b, [person.user_id]: true }))
    const wasFollowing = person.is_following
    try {
      if (wasFollowing) {
        await api(`/users/${person.user_id}/follow`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
        setPeople(list => list.map(p => p.user_id === person.user_id ? { ...p, is_following: false, is_pending: false } : p))
      } else {
        const res = await api<{ status?: string }>(`/users/${person.user_id}/follow`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
        const nowPending = res.status === 'pending'
        setPeople(list => list.map(p => p.user_id === person.user_id ? { ...p, is_following: !nowPending, is_pending: nowPending } : p))
      }
    } catch { /* leave state as-is on failure */ }
    setBusy(b => ({ ...b, [person.user_id]: false }))
  }

  const openProfile = (person: FollowListUser) => {
    setActiveProfileUserId?.(person.user_id)
    setActiveProfileName?.(person.display_name)
    setScreen('student-profile')
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <button onClick={() => window.history.back()} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>{mode === 'followers' ? 'Followers' : 'Following'}</div>
          <div style={{ marginLeft: 'auto' }}><Pill text={filtered.length.toString()} color={N.gold} /></div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, padding: '10px 14px' }}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="6" cy="6" r="5" stroke="rgba(255,255,255,0.4)" strokeWidth="1.5"/><path d="M10 10l2.5 2.5" stroke="rgba(255,255,255,0.4)" strokeWidth="1.5" strokeLinecap="round"/></svg>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search…" style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans' }} />
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 18px' }} className="scrollbar-hide">
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '30px 0' }}>
            <div style={{ width: 26, height: 26, border: '2.5px solid #E5E7EB', borderTopColor: N.gold, borderRadius: '50%', animation: 'spin-slow 0.7s linear infinite' }} />
          </div>
        ) : error ? (
          <div style={{ textAlign: 'center', padding: '30px 0', color: T.textMuted, fontSize: 13 }}>{error}</div>
        ) : filtered.length === 0 ? (
          <EmptyState icon="👥" title={mode === 'followers' ? 'No followers yet' : 'Not following anyone'} sub={mode === 'followers' ? "When students follow you, they'll appear here." : 'Discover students and follow them from their profiles.'} action="Explore Students" onAction={() => setScreen('explore')} />
        ) : filtered.map(p => {
          const isLoading = !!busy[p.user_id]
          return (
            <div key={p.user_id} style={{ background: T.card, borderRadius: 14, padding: '14px 16px', marginBottom: 10, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
              <div onClick={() => openProfile(p)} style={{ width: 44, height: 44, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 16, color: N.navy, flexShrink: 0, cursor: 'pointer' }}>
                {p.display_name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
              </div>
              <div style={{ flex: 1, minWidth: 0, cursor: 'pointer' }} onClick={() => openProfile(p)}>
                <div style={{ fontWeight: 700, fontSize: 14, color: T.text }}>{p.display_name}</div>
              </div>
              <button onClick={() => toggle(p)} disabled={isLoading || p.is_pending} style={{ background: (p.is_following || p.is_pending) ? '#F3F4F6' : `linear-gradient(135deg,${N.gold},${N.goldL})`, color: (p.is_following || p.is_pending) ? T.text : N.navy, fontWeight: 700, fontSize: 12, border: 'none', borderRadius: 10, padding: '8px 14px', cursor: p.is_pending ? 'default' : isLoading ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans', flexShrink: 0, opacity: isLoading ? 0.7 : 1, display: 'flex', alignItems: 'center', gap: 5, transition: 'all 0.2s' }}>
                {isLoading ? <div style={{ width: 10, height: 10, border: '1.5px solid currentColor', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin-slow 0.6s linear infinite' }} /> : null}
                {p.is_pending ? 'Requested' : p.is_following ? 'Following' : 'Follow'}
              </button>
            </div>
          )
        })}
        <div style={{ height: 16 }} />
      </div>
    </div>
  )
}

function FollowRequestsScreen({ setScreen, setActiveProfileUserId, setActiveProfileName, EmptyState }: {
  setScreen: (s: 'student-profile' | 'explore') => void
  setActiveProfileUserId?: (id: number) => void
  setActiveProfileName?: (name: string) => void
  EmptyState: ComponentType<{ icon: string; title: string; sub: string; action?: string; onAction?: () => void }>
}) {
  const { tokens: T } = useTheme()
  const [requests, setRequests] = useState<FollowRequestItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<Record<number, boolean>>({})
  const [csrfToken, setCsrfToken] = useState('')

  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  useEffect(() => {
    setLoading(true)
    setError('')
    api<{ requests: FollowRequestItem[] }>('/follow-requests')
      .then(res => setRequests(res.requests))
      .catch(() => setError('Could not load follow requests.'))
      .finally(() => setLoading(false))
  }, [])

  const respond = async (req: FollowRequestItem, action: 'accept' | 'decline') => {
    if (busy[req.id]) return
    setBusy(b => ({ ...b, [req.id]: true }))
    try {
      await api(`/follow-requests/${req.id}/${action}`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      setRequests(list => list.filter(r => r.id !== req.id))
    } catch {
      setBusy(b => ({ ...b, [req.id]: false }))
    }
  }

  const openProfile = (req: FollowRequestItem) => {
    setActiveProfileUserId?.(req.requester_id)
    setActiveProfileName?.(req.requester_display_name)
    setScreen('student-profile')
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => window.history.back()} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Follow Requests</div>
          <div style={{ marginLeft: 'auto' }}><Pill text={requests.length.toString()} color={N.gold} /></div>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 18px' }} className="scrollbar-hide">
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '30px 0' }}>
            <div style={{ width: 26, height: 26, border: '2.5px solid #E5E7EB', borderTopColor: N.gold, borderRadius: '50%', animation: 'spin-slow 0.7s linear infinite' }} />
          </div>
        ) : error ? (
          <div style={{ textAlign: 'center', padding: '30px 0', color: T.textMuted, fontSize: 13 }}>{error}</div>
        ) : requests.length === 0 ? (
          <EmptyState icon="👥" title="No pending requests" sub="When someone asks to follow you, they'll show up here." action="Explore Students" onAction={() => setScreen('explore')} />
        ) : requests.map(r => {
          const isLoading = !!busy[r.id]
          return (
            <div key={r.id} style={{ background: T.card, borderRadius: 14, padding: '14px 16px', marginBottom: 10, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
              <div onClick={() => openProfile(r)} style={{ width: 44, height: 44, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 16, color: N.navy, flexShrink: 0, cursor: 'pointer' }}>
                {r.requester_display_name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
              </div>
              <div style={{ flex: 1, minWidth: 0, cursor: 'pointer' }} onClick={() => openProfile(r)}>
                <div style={{ fontWeight: 700, fontSize: 14, color: T.text }}>{r.requester_display_name}</div>
                <div style={{ fontSize: 11, color: T.textMuted }}>wants to follow you</div>
              </div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                <button onClick={() => respond(r, 'decline')} disabled={isLoading} style={{ background: '#F3F4F6', color: T.text, fontWeight: 700, fontSize: 12, border: 'none', borderRadius: 10, padding: '8px 12px', cursor: isLoading ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: isLoading ? 0.6 : 1 }}>Decline</button>
                <button onClick={() => respond(r, 'accept')} disabled={isLoading} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 700, fontSize: 12, border: 'none', borderRadius: 10, padding: '8px 12px', cursor: isLoading ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: isLoading ? 0.6 : 1 }}>Accept</button>
              </div>
            </div>
          )
        })}
        <div style={{ height: 16 }} />
      </div>
    </div>
  )
}
