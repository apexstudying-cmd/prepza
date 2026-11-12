import { useEffect, useState } from 'react'
import { api } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Avi from '../../ui/Avi'
import { formatStudyTime } from '../../lib/studyTime'

type FollowSummary = { user_id: number; followers_count: number; following_count: number; is_following: boolean; is_followed_by: boolean; is_pending?: boolean }
type PublicProfile = {
  user_id: number; display_name: string; bio: string | null; year: number | null
  university_name: string | null; program_name: string | null
  documents_count: number; xp_total: number; weekly_study_seconds: number
  is_private?: boolean
}

export default function StudentProfileScreen({ setScreen, targetUserId, fallbackName, setActiveConversationId, activeConversationId, backScreen = 'chats' }: {
  setScreen: (s: 'chat-detail' | 'chats' | 'chat-options') => void
  targetUserId: number | null
  fallbackName?: string | null
  setActiveConversationId?: (id: number) => void
  activeConversationId?: number | null
  backScreen?: 'chat-detail' | 'chats'
}) {
  const { tokens: T } = useTheme()
  const [profile, setProfile] = useState<PublicProfile | null>(null)
  const [summary, setSummary] = useState<FollowSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')
  const [followBusy, setFollowBusy] = useState(false)
  const [messageBusy, setMessageBusy] = useState(false)

  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  useEffect(() => {
    if (targetUserId == null) { setLoading(false); setError('No student selected.'); return }
    setLoading(true)
    setError('')
    Promise.all([
      api<PublicProfile>(`/users/${targetUserId}/public-profile`),
      api<FollowSummary>(`/users/${targetUserId}/follow-summary`),
    ])
      .then(([profileRes, summaryRes]) => { setProfile(profileRes); setSummary(summaryRes) })
      .catch(() => setError('Could not load this profile.'))
      .finally(() => setLoading(false))
  }, [targetUserId])

  const toggleFollow = async () => {
    if (targetUserId == null || !summary || followBusy) return
    setFollowBusy(true)
    const wasFollowing = summary.is_following
    try {
      if (wasFollowing) {
        const res = await api<{ followers_count: number }>(`/users/${targetUserId}/follow`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
        setSummary(s => s ? { ...s, is_following: false, is_pending: false, followers_count: res.followers_count } : s)
      } else {
        const res = await api<{ followers_count?: number; status?: string }>(`/users/${targetUserId}/follow`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
        const nowPending = res.status === 'pending'
        setSummary(s => s ? { ...s, is_following: !nowPending, is_pending: nowPending, followers_count: res.followers_count ?? s.followers_count } : s)
      }
    } catch { /* leave state as-is on failure */ }
    setFollowBusy(false)
  }

  // Reuses the Chunk 8 chat infra: starts (or reuses) a 1:1 conversation
  // with this user, then hands off to ChatDetailScreen the same way
  // NewChatScreen does.
  const startMessage = async () => {
    if (targetUserId == null || messageBusy) return
    setMessageBusy(true)
    try {
      const res = await api<{ id: number; reused: boolean }>('/chats', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ is_group: false, participant_ids: [targetUserId] }),
      })
      setActiveConversationId?.(res.id)
      setScreen('chat-detail')
    } catch { /* stay put on failure */ }
    setMessageBusy(false)
  }

  const displayName = profile?.display_name || fallbackName || 'Student'
  const initials = displayName.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() || 'ST'
  const courseLine = profile && (profile.program_name || profile.year != null)
    ? [profile.program_name, profile.year != null ? `Year ${profile.year}` : null].filter(Boolean).join(' · ')
    : null

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: `linear-gradient(180deg,${N.navy} 0%,${N.navy3} 100%)`, padding: '0 18px 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <button type="button" onClick={() => setScreen(backScreen)} aria-label="Back" style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ fontWeight: 700, fontSize: 13, color: 'rgba(255,255,255,0.72)' }}>Contact info</span>
        </div>
        {loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '20px 0' }}>
            <div style={{ width: 30, height: 30, border: '2.5px solid rgba(255,255,255,0.2)', borderTopColor: N.gold, borderRadius: '50%', animation: 'spin-slow 0.7s linear infinite' }} />
          </div>
        ) : error ? (
          <div style={{ textAlign: 'center', padding: '20px 0' }}>
            <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 13 }}>{error}</div>
          </div>
        ) : profile?.is_private ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
            <div style={{ marginBottom: 14 }}><Avi name={initials} size={72} /></div>
            <div style={{ fontWeight: 800, fontSize: 20, color: '#fff', marginBottom: 4 }}>{displayName}</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)' }}>This profile is private.</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
            <div style={{ marginBottom: 14 }}><Avi name={initials} size={72} /></div>
            <div style={{ fontWeight: 800, fontSize: 20, color: '#fff', marginBottom: 2 }}>{displayName}</div>
            {courseLine && <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.55)' }}>{courseLine}</div>}
            {profile?.university_name && <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', marginTop: 2 }}>{profile.university_name}</div>}
            {profile?.bio && <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.65)', marginTop: 8, maxWidth: 260, lineHeight: 1.5 }}>{profile.bio}</div>}
            <div style={{ marginBottom: 14 }} />
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={toggleFollow} disabled={followBusy || summary?.is_pending} style={{ background: (summary?.is_following || summary?.is_pending) ? 'rgba(201,168,76,0.2)' : `linear-gradient(135deg,${N.gold},${N.goldL})`, color: (summary?.is_following || summary?.is_pending) ? N.gold : N.navy, fontWeight: 800, fontSize: 13, border: (summary?.is_following || summary?.is_pending) ? `1px solid ${N.gold}44` : 'none', borderRadius: 12, padding: '10px 24px', cursor: summary?.is_pending ? 'default' : followBusy ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: followBusy ? 0.7 : 1 }}>{summary?.is_pending ? 'Requested' : summary?.is_following ? 'Following ✓' : 'Follow'}</button>
              {activeConversationId == null && <button onClick={startMessage} disabled={messageBusy} style={{ background: 'rgba(255,255,255,0.1)', color: '#fff', fontWeight: 700, fontSize: 13, border: '1px solid rgba(255,255,255,0.15)', borderRadius: 12, padding: '10px 20px', cursor: messageBusy ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: messageBusy ? 0.7 : 1 }}>{messageBusy ? 'Opening…' : 'Message'}</button>}
            </div>
          </div>
        )}
      </div>
      {!loading && !error && summary && profile && !profile.is_private && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10, padding: '16px 16px 0' }}>
          <div style={{ background: T.card, borderRadius: 14, padding: '14px 8px', textAlign: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
            <div style={{ fontWeight: 800, fontSize: 18, color: N.gold }}>{profile.xp_total.toLocaleString()}</div>
            <div style={{ fontSize: 11, color: T.textMuted }}>XP</div>
          </div>
          <div style={{ background: T.card, borderRadius: 14, padding: '14px 8px', textAlign: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
            <div style={{ fontWeight: 800, fontSize: 18, color: N.gold }}>{summary.followers_count}</div>
            <div style={{ fontSize: 11, color: T.textMuted }}>Followers</div>
          </div>
          <div style={{ background: T.card, borderRadius: 14, padding: '14px 8px', textAlign: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
            <div style={{ fontWeight: 800, fontSize: 18, color: N.gold }}>{summary.following_count}</div>
            <div style={{ fontSize: 11, color: T.textMuted }}>Following</div>
          </div>
          <div style={{ background: T.card, borderRadius: 14, padding: '14px 8px', textAlign: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
            <div style={{ fontWeight: 800, fontSize: 18, color: N.gold }}>{profile.documents_count}</div>
            <div style={{ fontSize: 11, color: T.textMuted }}>Documents</div>
          </div>
          <div style={{ background: T.card, borderRadius: 14, padding: '14px 8px', textAlign: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
            <div style={{ fontWeight: 800, fontSize: 18, color: N.gold }}>{formatStudyTime(profile.weekly_study_seconds)}</div>
            <div style={{ fontSize: 11, color: T.textMuted }}>Time</div>
          </div>
        </div>
      )}
      {activeConversationId != null && !loading && !error && profile && !profile.is_private && (
        <div style={{ padding: '16px' }}>
          <div style={{ background: T.card, borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 8px rgba(0,0,0,.05)' }}>
            <div style={{ padding: '14px 16px 8px', fontSize: 11, fontWeight: 800, color: T.textMuted, textTransform: 'uppercase', letterSpacing: .5 }}>Chat</div>
            <button type="button" onClick={() => setScreen('chat-options')} style={{ width:'100%',display:'flex',alignItems:'center',gap:12,padding:'13px 16px',border:0,borderTop:'1px solid rgba(0,0,0,.05)',background:'transparent',cursor:'pointer',textAlign:'left' }}>
              <div style={{ color:T.textMuted }}>{Ic.message('w-5 h-5')}</div><div style={{flex:1}}><div style={{fontWeight:750,fontSize:13,color:T.text}}>Chat info & settings</div><div style={{fontSize:11,color:T.textMuted,marginTop:2}}>Shared media, notifications and conversation settings</div></div>{Ic.chevR()}
            </button>
          </div>
        </div>
      )}
      {/* Recent posts for another user still aren't exposed by any current
          endpoint - not shown, rather than faked. */}
    </div>
  )
}
