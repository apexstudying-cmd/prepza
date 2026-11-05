import { useEffect, useState } from 'react'
import { api } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Avi from '../../ui/Avi'
import type { UserSearchResult } from '../../types/users'

export default function NewChatScreen({ setScreen, setActiveConversationId }: { setScreen: (s: 'chat-detail') => void; setActiveConversationId: (id: number) => void }) {
  const { tokens: T } = useTheme()
  const [mode, setMode] = useState<'select'|'new-chat'|'new-group'>('select')
  const [search, setSearch] = useState('')
  const [results, setResults] = useState<UserSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [csrfToken, setCsrfToken] = useState('')
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [groupName, setGroupName] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
  }, [])

  useEffect(() => {
    if (mode === 'select') return
    const q = search.trim()
    if (!q) { setResults([]); setSearchError(null); return }
    let cancelled = false
    setSearching(true)
    const t = setTimeout(() => {
      api<{ users: UserSearchResult[] }>(`/users/search?q=${encodeURIComponent(q)}`)
        .then(data => { if (!cancelled) { setResults(data.users); setSearchError(null) } })
        .catch(e => { if (!cancelled) setSearchError(e instanceof Error ? e.message : 'Search failed') })
        .finally(() => { if (!cancelled) setSearching(false) })
    }, 300)
    return () => { cancelled = true; clearTimeout(t) }
  }, [search, mode])

  const startDirectChat = async (userId: number) => {
    if (creating) return
    setCreating(true)
    setCreateError(null)
    try {
      const res = await api<{ id: number; reused: boolean }>('/chats', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ is_group: false, participant_ids: [userId] }),
      })
      setActiveConversationId(res.id)
      setScreen('chat-detail')
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : 'Could not start chat')
    } finally {
      setCreating(false)
    }
  }

  const toggleSelected = (userId: number) => {
    setSelectedIds(ids => ids.includes(userId) ? ids.filter(id => id !== userId) : [...ids, userId])
  }

  const createGroup = async () => {
    if (creating) return
    if (!groupName.trim()) { setCreateError('Group name is required'); return }
    if (selectedIds.length === 0) { setCreateError('Select at least one member'); return }
    setCreating(true)
    setCreateError(null)
    try {
      const res = await api<{ id: number; reused: boolean }>('/chats', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ is_group: true, name: groupName.trim(), participant_ids: selectedIds }),
      })
      setActiveConversationId(res.id)
      setScreen('chat-detail')
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : 'Could not create group')
    } finally {
      setCreating(false)
    }
  }

  if (mode === 'select') return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => window.history.back()} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 18, color: '#fff' }}>New Conversation</span>
        </div>
      </div>
      <div style={{ flex: 1, padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <button onClick={() => setMode('new-chat')} style={{ display: 'flex', alignItems: 'center', gap: 14, background: T.card, border: 'none', borderRadius: 16, padding: 16, cursor: 'pointer', boxShadow: '0 2px 10px rgba(0,0,0,0.05)', fontFamily: 'Plus Jakarta Sans' }}>
          <div style={{ width: 48, height: 48, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22 }}>💬</div>
          <div style={{ textAlign: 'left' }}><div style={{ fontWeight: 800, fontSize: 14, color: T.text }}>New Chat</div><div style={{ fontSize: 12, color: T.textMuted }}>Message a classmate directly</div></div>
        </button>
        <button onClick={() => setMode('new-group')} style={{ display: 'flex', alignItems: 'center', gap: 14, background: T.card, border: 'none', borderRadius: 16, padding: 16, cursor: 'pointer', boxShadow: '0 2px 10px rgba(0,0,0,0.05)', fontFamily: 'Plus Jakarta Sans' }}>
          <div style={{ width: 48, height: 48, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22 }}>👥</div>
          <div style={{ textAlign: 'left' }}><div style={{ fontWeight: 800, fontSize: 14, color: T.text }}>New Group</div><div style={{ fontSize: 12, color: T.textMuted }}>Create a study group chat</div></div>
        </button>
      </div>
    </div>
  )
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.card }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => setMode('select')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>{mode === 'new-chat' ? 'Select Contact' : 'New Group'}</span>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', background: 'rgba(255,255,255,0.09)', borderRadius: 12, padding: '9px 12px' }}>
          <div style={{ color: 'rgba(255,255,255,0.4)' }}>{Ic.search('w-4 h-4')}</div>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search students…" style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: 13, fontFamily: 'Plus Jakarta Sans' }} />
        </div>
        {mode === 'new-group' && (
          <input value={groupName} onChange={e => setGroupName(e.target.value)} placeholder="Group name…" style={{ marginTop: 10, width: '100%', boxSizing: 'border-box', background: 'rgba(255,255,255,0.09)', border: 'none', borderRadius: 12, padding: '10px 12px', color: '#fff', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none' }} />
        )}
      </div>
      <div style={{ flex: 1, overflowY: 'auto' }} className="scrollbar-hide">
        {createError && <div style={{ padding: '10px 16px', color: '#C94C4C', fontSize: 12, fontFamily: 'Plus Jakarta Sans' }}>{createError}</div>}
        {searchError && <div style={{ padding: '10px 16px', color: '#C94C4C', fontSize: 12, fontFamily: 'Plus Jakarta Sans' }}>{searchError}</div>}
        {!search.trim() ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 20px', textAlign: 'center' }}>
            <div style={{ fontSize: 44, marginBottom: 12 }}>🔍</div>
            <div style={{ fontWeight: 700, fontSize: 16, color: T.text }}>Search for students</div>
            <div style={{ fontSize: 13, color: T.textMuted, marginTop: 4 }}>Start typing a name to find classmates</div>
          </div>
        ) : searching ? (
          <div style={{ padding: '20px 16px', textAlign: 'center', color: T.textMuted, fontSize: 13, fontFamily: 'Plus Jakarta Sans' }}>Searching…</div>
        ) : results.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 20px', textAlign: 'center' }}>
            <div style={{ fontSize: 44, marginBottom: 12 }}>🙁</div>
            <div style={{ fontWeight: 700, fontSize: 16, color: T.text }}>No students found</div>
          </div>
        ) : results.map(c => {
          const initials = (c.display_name || '??').slice(0, 2).toUpperCase()
          const course = c.year != null && c.semester != null ? `Year ${c.year} · Semester ${c.semester}` : 'Prepza student'
          const selected = selectedIds.includes(c.id)
          return (
            <div key={c.id} onClick={() => mode === 'new-chat' ? startDirectChat(c.id) : toggleSelected(c.id)} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '13px 16px', cursor: 'pointer', borderBottom: '1px solid rgba(0,0,0,0.04)', opacity: creating ? 0.6 : 1 }}>
              <Avi name={initials} size={44} />
              <div style={{ flex: 1 }}><div style={{ fontWeight: 700, fontSize: 14, color: T.text }}>{c.display_name}</div><div style={{ fontSize: 12, color: T.textMuted }}>{course}</div></div>
              {mode === 'new-chat' && <div style={{ color: N.gold }}>{Ic.chevR()}</div>}
              {mode === 'new-group' && (
                <div style={{ width: 22, height: 22, borderRadius: '50%', border: `2px solid ${selected ? N.gold : T.textMuted}`, background: selected ? N.gold : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, color: N.navy, fontWeight: 800, flexShrink: 0 }}>{selected ? '✓' : ''}</div>
              )}
            </div>
          )
        })}
        {mode === 'new-group' && (
          <div style={{ padding: '20px 16px' }}>
            <button onClick={createGroup} disabled={creating} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '14px 0', cursor: creating ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: creating ? 0.7 : 1 }}>{creating ? 'Creating…' : `Create Group${selectedIds.length ? ` (${selectedIds.length})` : ''} →`}</button>
          </div>
        )}
      </div>
    </div>
  )
}
