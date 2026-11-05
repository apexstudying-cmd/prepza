import { useEffect, useState, type ComponentType, type ReactNode } from 'react'

import { api } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import type { NotificationItem } from '../../types/notifications'

type NotificationsScreenProps = {
  setScreen: (screen: 'podcast-player' | 'group-detail' | 'student-profile') => void
  setActiveProfileUserId?: (id: number) => void
  setActiveDocumentId?: (id: number) => void
  EmptyStateView: ComponentType<{ icon: string; title: string; sub: string }>
  loadingView: ReactNode
}

const NOTIFS_CACHE: { notifs?: NotificationItem[] } = {}

export default function NotificationsScreen({ setScreen, setActiveProfileUserId, setActiveDocumentId, EmptyStateView, loadingView }: NotificationsScreenProps) {
  const { tokens: T } = useTheme()
  const [notifs, setNotifs] = useState<NotificationItem[]>(NOTIFS_CACHE.notifs ?? [])
  const [loading, setLoading] = useState(NOTIFS_CACHE.notifs === undefined)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')

  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  useEffect(() => {
    if (NOTIFS_CACHE.notifs === undefined) setLoading(true)
    api<{ page: number; notifications: NotificationItem[] }>('/notifications?page=1')
      .then(res => { setNotifs(res.notifications); NOTIFS_CACHE.notifs = res.notifications })
      .catch(() => setError('Could not load notifications.'))
      .finally(() => setLoading(false))
  }, [])

  const markRead = async (n: NotificationItem) => {
    if (n.is_read) return
    setNotifs(list => { const next = list.map(x => x.id === n.id ? { ...x, is_read: true } : x); NOTIFS_CACHE.notifs = next; return next })
    try { await api(`/notifications/${n.id}/read`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } }) } catch {}
  }
  const markAllRead = async () => {
    setNotifs(list => { const next = list.map(x => ({ ...x, is_read: true })); NOTIFS_CACHE.notifs = next; return next })
    try { await api('/notifications/read-all', { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } }) } catch {}
  }
  const removeNotif = async (id: number) => {
    setNotifs(list => { const next = list.filter(x => x.id !== id); NOTIFS_CACHE.notifs = next; return next })
    try { await api(`/notifications/${id}`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } }) } catch {}
  }
  const openNotif = (n: NotificationItem) => {
    markRead(n)
    if ((n.type === 'podcast_ready' || n.type === 'podcast_failed') && n.related_id && setActiveDocumentId) {
      setActiveDocumentId(n.related_id)
      setScreen('podcast-player')
    } else if (n.related_type === 'group' || n.related_type === 'group_post') setScreen('group-detail')
    else if (n.related_type === 'user' && n.related_id && setActiveProfileUserId) { setActiveProfileUserId(n.related_id); setScreen('student-profile') }
  }
  const iconFor = (type: string) => ({
    group_post: '\ud83d\udcac', group_comment: '\ud83d\udcac', group_join_request: '\ud83d\udc65', new_follower: '\u2795',
    forum_ai_reply: '\u2726', study_reminder: '\ud83d\udcda', opportunity: '\ud83d\ude80', achievement: '\ud83c\udfc6',
    announcement: '\ud83d\udce3', group_like: '\u2764\ufe0f', group_vote: '\u2b06\ufe0f', group_promoted: '\u2b50', podcast_ready: '◉', podcast_failed: '!', moderation_warning: '\u26a0\ufe0f',
  } as Record<string,string>)[type] || '\ud83d\udd14'

  if (loading) return loadingView
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => window.history.back()} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 18, color: '#fff' }}>Notifications</span>
          {notifs.some(n => !n.is_read) && (
            <button onClick={markAllRead} style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, padding: '7px 12px', color: '#fff', fontWeight: 600, fontSize: 11, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Mark all read</button>
          )}
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 8 }} className="scrollbar-hide">
        {error && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600 }}>{error}</div>}
        {!error && notifs.length === 0 && <EmptyStateView icon="\ud83d\udd14" title="No notifications yet" sub="You'll see updates about study activity, community, and your account here." />}
        {notifs.map(n => (
          <div key={n.id} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', background: n.is_read ? '#fff' : '#FFFBEF', border: n.is_read ? 'none' : `1px solid ${N.gold}30`, borderRadius: 14, padding: '13px 14px', boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
            <button onClick={() => openNotif(n)} style={{ display: 'flex', gap: 12, flex: 1, background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', fontFamily: 'Plus Jakarta Sans', padding: 0 }}>
              <div style={{ width: 42, height: 42, background: `${N.gold}18`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0 }}>{iconFor(n.type)}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 2 }}>{n.title}</div>
                {n.body && <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.55 }} className="line-clamp-2">{n.body}</div>}
                <div style={{ fontSize: 10, color: T.textMuted, marginTop: 4 }}>{n.created_at ? new Date(n.created_at).toLocaleString() : ''}</div>
              </div>
            </button>
            <button onClick={() => removeNotif(n.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.textMuted, flexShrink: 0, padding: 4 }}>{Ic.close('w-4 h-4')}</button>
          </div>
        ))}
      </div>
    </div>
  )
}
