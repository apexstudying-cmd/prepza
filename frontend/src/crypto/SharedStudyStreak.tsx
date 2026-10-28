import { useEffect, useState } from 'react'

type Streak = {
  id: number
  invited_by: number
  status: 'pending' | 'active'
  peer_name: string
  current_streak: number
  longest_streak: number
  minimum_minutes: number
  today: { you_studied: boolean; friend_studied: boolean; both_studied: boolean }
}
type Payload = { supported: boolean; streak: Streak | null }
type Props = { conversationId: number; isGroup: boolean; csrfToken: string; userId: number | null }

async function request<T>(path: string, csrfToken: string, method = 'GET'): Promise<T> {
  const response = await fetch(path, {
    method,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(method === 'GET' ? {} : { 'X-CSRF-Token': csrfToken }) },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body?.error || 'Could not update study streak.')
  return body as T
}

export default function SharedStudyStreak({ conversationId, isGroup, csrfToken, userId }: Props) {
  const [open, setOpen] = useState(false)
  const [payload, setPayload] = useState<Payload | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const refresh = async () => {
    if (isGroup) return
    try {
      const next = await request<Payload>(`/chats/${conversationId}/study-streak`, csrfToken)
      setPayload(next)
      setError('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load study streak.')
    }
  }

  useEffect(() => {
    setPayload(null)
    setError('')
    setNotice('')
    void refresh()
  }, [conversationId, isGroup])

  if (isGroup) return null
  const streak = payload?.streak
  const act = async (action: 'invite' | 'accept' | 'decline') => {
    setBusy(true); setError(''); setNotice('')
    try {
      const path = `/chats/${conversationId}/study-streak${action === 'accept' ? '/accept' : action === 'decline' ? '/decline' : ''}`
      await request(path, csrfToken, action === 'invite' ? 'POST' : 'POST')
      setNotice(action === 'invite' ? 'Invitation sent.' : action === 'accept' ? 'Shared streak started.' : 'Invitation declined.')
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not update study streak.')
    } finally { setBusy(false) }
  }

  return <div style={{ position: 'relative', marginLeft: 'auto', flexShrink: 0 }}>
    <button type="button" onClick={() => { setOpen(value => !value); if (!open) void refresh() }} aria-expanded={open} aria-label="Shared study streak" title="Shared study streak" style={{ border: '1px solid rgba(255,255,255,.22)', borderRadius: 10, padding: '8px 10px', background: 'rgba(255,255,255,.09)', color: '#fff', fontSize: 11, fontWeight: 800, cursor: 'pointer', whiteSpace: 'nowrap' }}>
      {streak?.status === 'active' ? `🔥 ${streak.current_streak} day${streak.current_streak === 1 ? '' : 's'}` : 'Study streak'}
    </button>
    {open && <div role="dialog" aria-label="Shared study streak details" style={{ position: 'absolute', top: 46, right: 0, zIndex: 1200, width: 'min(310px, calc(100vw - 28px))', boxSizing: 'border-box', background: '#fff', color: '#101b35', border: '1px solid #e2e5eb', borderRadius: 16, padding: 15, boxShadow: '0 18px 50px rgba(0,0,0,.22)' }}>
      <div style={{ fontSize: 14, fontWeight: 900 }}>Study together</div>
      <div style={{ marginTop: 5, fontSize: 11, lineHeight: 1.5, color: '#606b7d' }}>Both of you need at least 10 minutes of recorded study on the same Nairobi calendar day.</div>
      {streak?.status === 'active' && <>
        <div style={{ marginTop: 13, padding: 12, borderRadius: 12, background: '#fff7df' }}>
          <div style={{ fontSize: 22, fontWeight: 900 }}>🔥 {streak.current_streak} day{streak.current_streak === 1 ? '' : 's'}</div>
          <div style={{ marginTop: 3, fontSize: 11, color: '#6d5a27' }}>Longest shared streak: {streak.longest_streak} days</div>
        </div>
        <div style={{ marginTop: 10, fontSize: 11, color: '#4b5563' }}>Today: You {streak.today.you_studied ? '✓' : 'not yet'} · {streak.peer_name} {streak.today.friend_studied ? '✓' : 'not yet'}</div>
      </>}
      {streak?.status === 'pending' && <div style={{ marginTop: 12, padding: 10, borderRadius: 10, background: '#f4f6fa', fontSize: 12 }}>{streak.invited_by === userId ? 'Waiting for ' + streak.peer_name + ' to accept your invitation.' : streak.peer_name + ' invited you to start a shared streak.'}
        {streak.invited_by !== userId && <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <button type="button" disabled={busy} onClick={() => void act('accept')} style={{ flex: 1, border: 0, borderRadius: 9, padding: 9, background: '#c9a84c', color: '#101b35', fontWeight: 800 }}>Accept</button>
          <button type="button" disabled={busy} onClick={() => void act('decline')} style={{ flex: 1, border: '1px solid #d9dee7', borderRadius: 9, padding: 9, background: '#fff', color: '#101b35', fontWeight: 800 }}>Decline</button>
        </div>}
      </div>}
      {!streak && payload?.supported && <button type="button" disabled={busy} onClick={() => void act('invite')} style={{ width: '100%', marginTop: 13, border: 0, borderRadius: 10, padding: 11, background: '#c9a84c', color: '#101b35', fontWeight: 900, cursor: busy ? 'wait' : 'pointer' }}>{busy ? 'Sending…' : 'Invite to shared streak'}</button>}
      {payload && !payload.supported && <div style={{ marginTop: 12, fontSize: 11, color: '#606b7d' }}>Shared streaks are available in one-to-one chats only.</div>}
      {notice && <div role="status" style={{ marginTop: 9, fontSize: 11, color: '#17613b' }}>{notice}</div>}
      {error && <div role="alert" style={{ marginTop: 9, fontSize: 11, color: '#a33131' }}>{error}</div>}
      <button type="button" onClick={() => setOpen(false)} style={{ marginTop: 12, border: 0, background: 'transparent', color: '#687386', fontSize: 11, cursor: 'pointer' }}>Close</button>
    </div>}
  </div>
}
