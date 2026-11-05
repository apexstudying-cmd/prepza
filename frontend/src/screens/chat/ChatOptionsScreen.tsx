import { useEffect, useRef, useState } from 'react'

import { api } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Pill from '../../ui/Pill'
import type { ChatDetail, ChatMessageData } from '../../types/chat'

type SharedMediaItem = { id: number; message_id: number; file_type: string; original_filename: string; file_size_bytes: number; view_url: string | null; uploaded_by_user_id: number; uploaded_by_name: string; created_at: string | null }

type SharedMediaTab = 'all' | 'images' | 'videos' | 'audio' | 'files'
const SHARED_MEDIA_VIDEO_TYPES = new Set(['mp4', 'webm', 'mov', 'm4v', 'avi'])
const SHARED_MEDIA_AUDIO_TYPES = new Set(['webm', 'ogg', 'mp3', 'm4a', 'wav', 'aac'])
function sharedMediaCategory(item: SharedMediaItem, getFileExtension: (filename: string) => string | null, imageFileTypes: string[]): Exclude<SharedMediaTab, 'all'> {
  const ext = getFileExtension(item.original_filename || '') || String(item.file_type || '').toLowerCase().replace(/^\./, '')
  if (imageFileTypes.includes(ext)) return 'images'
  if (SHARED_MEDIA_AUDIO_TYPES.has(ext) && (ext !== 'webm' || item.original_filename.toLowerCase().startsWith('voice-note-'))) return 'audio'
  if (SHARED_MEDIA_VIDEO_TYPES.has(ext)) return 'videos'
  return 'files'
}


type ChatOptionsScreenProps = {
  setScreen: (screen: 'chat-detail' | 'chats' | 'student-profile') => void
  conversationId: number | null
  setActiveProfileUserId?: (id: number) => void
  setActiveProfileName?: (name: string) => void
  backScreen?: 'chat-detail' | 'chats'
  setActiveProfileBackScreen?: (screen: 'chat-detail' | 'chats') => void
  getFileExtension: (filename: string) => string | null
  imageFileTypes: string[]
}

export default function ChatOptionsScreen({ setScreen, conversationId, setActiveProfileUserId, setActiveProfileName, backScreen = 'chat-detail', setActiveProfileBackScreen, getFileExtension, imageFileTypes }: ChatOptionsScreenProps) {
  const { tokens: T } = useTheme()
  const [detail, setDetail] = useState<ChatDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [csrfToken, setCsrfToken] = useState('')
  const [viewerId, setViewerId] = useState<number | null>(null)
  const [showRename, setShowRename] = useState(false)
  const [renameVal, setRenameVal] = useState('')
  const [renaming, setRenaming] = useState(false)
  const [renameError, setRenameError] = useState<string | null>(null)
  const [leaving, setLeaving] = useState(false)
  const [leaveError, setLeaveError] = useState<string | null>(null)
  const [mutingBusy, setMutingBusy] = useState(false)
  const [muteError, setMuteError] = useState<string | null>(null)
  const [showSearch, setShowSearch] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<ChatMessageData[]>([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [showMedia, setShowMedia] = useState(false)
  const [mediaItems, setMediaItems] = useState<SharedMediaItem[]>([])
  const [mediaLoading, setMediaLoading] = useState(false)
  const [mediaError, setMediaError] = useState<string | null>(null)
  const [mediaTab, setMediaTab] = useState<SharedMediaTab>('all')

  useEffect(() => {
    api<{ id: number; csrf_token: string }>('/me').then(me => { setCsrfToken(me.csrf_token); setViewerId(me.id) }).catch(() => {})
  }, [])

  useEffect(() => {
    if (conversationId == null) { setLoading(false); return }
    let cancelled = false
    setLoading(true)
    setError(null)
    api<ChatDetail>(`/chats/${conversationId}`)
      .then(d => { if (!cancelled) { setDetail(d); setRenameVal(d.name) } })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load chat info') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [conversationId])

  const chatOptionsOverlayRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!showRename && !showSearch && !showMedia) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setShowRename(false); setShowSearch(false); setShowMedia(false) }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [showRename, showSearch, showMedia])

  useEffect(() => {
    if (!showSearch || conversationId == null) return
    const q = searchQuery.trim()
    if (!q) { setSearchResults([]); setSearchError(null); setSearching(false); return }
    let cancelled = false
    setSearching(true)
    const t = setTimeout(() => {
      api<{ messages: ChatMessageData[] }>(`/chats/${conversationId}/messages/search?q=${encodeURIComponent(q)}`)
        .then(res => { if (!cancelled) { setSearchResults(res.messages); setSearchError(null) } })
        .catch(e => { if (!cancelled) setSearchError(e instanceof Error ? e.message : 'Search failed') })
        .finally(() => { if (!cancelled) setSearching(false) })
    }, 300)
    return () => { cancelled = true; clearTimeout(t) }
  }, [searchQuery, showSearch, conversationId])

  useEffect(() => {
    if (!showMedia || conversationId == null) return
    let cancelled = false
    setMediaLoading(true)
    setMediaError(null)
    api<{ attachments: SharedMediaItem[] }>(`/chats/${conversationId}/attachments`)
      .then(res => { if (!cancelled) setMediaItems(res.attachments) })
      .catch(e => { if (!cancelled) setMediaError(e instanceof Error ? e.message : 'Could not load shared media') })
      .finally(() => { if (!cancelled) setMediaLoading(false) })
    return () => { cancelled = true }
  }, [showMedia, conversationId])

  const saveRename = async () => {
    if (!renameVal.trim() || conversationId == null || renaming) return
    setRenaming(true)
    setRenameError(null)
    try {
      const res = await api<{ id: number; name: string }>(`/chats/${conversationId}`, {
        method: 'PATCH',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ name: renameVal.trim() }),
      })
      setDetail(d => d ? { ...d, name: res.name } : d)
      setShowRename(false)
    } catch (e) {
      setRenameError(e instanceof Error ? e.message : 'Could not rename group')
    } finally {
      setRenaming(false)
    }
  }

  const leaveGroup = async () => {
    if (conversationId == null || leaving) return
    setLeaving(true)
    setLeaveError(null)
    try {
      await api(`/chats/${conversationId}/leave`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      setScreen('chats')
    } catch (e) {
      setLeaveError(e instanceof Error ? e.message : 'Could not leave group')
    } finally {
      setLeaving(false)
    }
  }

  const toggleMute = async () => {
    if (conversationId == null || detail == null || mutingBusy) return
    setMutingBusy(true)
    setMuteError(null)
    const next = !detail.viewer_muted
    try {
      const res = await api<{ muted: boolean }>(`/chats/${conversationId}/mute`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ muted: next }),
      })
      setDetail(d => d ? { ...d, viewer_muted: res.muted } : d)
    } catch (e) {
      setMuteError(e instanceof Error ? e.message : 'Could not update notifications')
    } finally {
      setMutingBusy(false)
    }
  }

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
        <div style={{ background: N.navy, padding: '0 18px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button type="button" onClick={() => setScreen(backScreen)} aria-label="Back to chat" style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Chat Info</span>
          </div>
        </div>
        <div style={{ padding: '40px 20px', textAlign: 'center', color: T.textMuted, fontSize: 13, fontFamily: 'Plus Jakarta Sans' }}>Loading…</div>
      </div>
    )
  }

  const initials = (detail?.name || '??').slice(0, 2).toUpperCase()
  const directPeer = detail && !detail.is_group && viewerId != null ? detail.participants.find(p => p.user_id !== viewerId) : null

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg, position: 'relative' }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <button type="button" onClick={() => setScreen(backScreen)} aria-label="Back to chat" style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>{detail?.is_group ? 'Group Info' : 'Chat Info'}</span>
        </div>
        {error ? (
          <div style={{ color: '#ffb4bd', fontSize: 13, textAlign: 'center' }}>{error}</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <Avi name={initials} size={64} />
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff', marginTop: 12 }}>{detail?.name}</div>
            {detail?.is_group && <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.5)', marginTop: 4 }}>{detail.member_count} member{detail.member_count === 1 ? '' : 's'} · Created by {detail.created_by_name}</div>}
          </div>
        )}
      </div>
      <div style={{ padding: 16 }}>
        {detail?.is_group && (
          <div onClick={() => { setRenameError(null); setShowRename(true) }} style={{ background: T.card, borderRadius: 14, padding: '13px 16px', marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', cursor: 'pointer' }}>
            <div style={{ color: T.textMuted }}>{Ic.edit('w-5 h-5')}</div>
            <div style={{ flex: 1 }}><div style={{ fontWeight: 700, fontSize: 13, color: T.text }}>Rename Group</div><div style={{ fontSize: 11, color: T.textMuted }}>{detail.name}</div></div>
            {Ic.chevR()}
          </div>
        )}
        {directPeer && <div onClick={() => { setActiveProfileBackScreen?.(backScreen); setActiveProfileUserId?.(directPeer.user_id); setActiveProfileName?.(directPeer.display_name || detail?.name || 'Student'); setScreen('student-profile') }} style={{ background: T.card, borderRadius: 14, padding: '13px 16px', marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', cursor: 'pointer' }}>
          <Avi name={(directPeer.display_name || detail?.name || '??').slice(0, 2).toUpperCase()} size={34} />
          <div style={{ flex: 1 }}><div style={{ fontWeight: 700, fontSize: 13, color: T.text }}>View profile</div><div style={{ fontSize: 11, color: T.textMuted }}>{directPeer.display_name || detail?.name}</div></div>
          {Ic.chevR()}
        </div>}
        <div onClick={() => { setMediaError(null); setShowMedia(true) }} style={{ background: T.card, borderRadius: 14, padding: '13px 16px', marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', cursor: 'pointer' }}>
          <div style={{ color: T.textMuted }}>{Ic.image('w-5 h-5')}</div>
          <div style={{ flex: 1 }}><div style={{ fontWeight: 700, fontSize: 13, color: T.text }}>Shared Media</div><div style={{ fontSize: 11, color: T.textMuted }}>Files and images shared here</div></div>
          {Ic.chevR()}
        </div>
        <div onClick={() => { setSearchError(null); setShowSearch(true) }} style={{ background: T.card, borderRadius: 14, padding: '13px 16px', marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', cursor: 'pointer' }}>
          <div style={{ color: T.textMuted }}>{Ic.search('w-5 h-5')}</div>
          <div style={{ flex: 1 }}><div style={{ fontWeight: 700, fontSize: 13, color: T.text }}>Search Messages</div><div style={{ fontSize: 11, color: T.textMuted }}>Find something in this chat</div></div>
          {Ic.chevR()}
        </div>
        <div style={{ background: T.card, borderRadius: 14, padding: '13px 16px', marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', opacity: mutingBusy ? 0.6 : 1 }}>
          <div style={{ color: T.textMuted }}>{Ic.bell('w-5 h-5')}</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text }}>Notifications</div>
            <div style={{ fontSize: 11, color: T.textMuted }}>{detail && !detail.viewer_muted ? 'On' : 'Muted'}</div>
            {muteError && <div style={{ fontSize: 11, color: '#C94C4C', marginTop: 2 }}>{muteError}</div>}
          </div>
          <div onClick={toggleMute}>{Ic.toggle(!!detail && !detail.viewer_muted)}</div>
        </div>
        {detail?.is_group && detail.participants.length > 0 && (
          <div style={{ background: T.card, borderRadius: 14, marginBottom: 8, overflow: 'hidden', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
            <div style={{ padding: '12px 16px 8px', fontWeight: 700, fontSize: 12, color: T.textMuted, textTransform: 'uppercase', letterSpacing: 0.4 }}>Members ({detail.participants.length})</div>
            {detail.participants.map(p => (
              <button key={p.user_id} type="button" onClick={() => { if (p.user_id === viewerId) return; setActiveProfileBackScreen?.(backScreen); setActiveProfileUserId?.(p.user_id); setActiveProfileName?.(p.display_name || 'Student'); setScreen('student-profile') }} style={{ display: 'flex', gap: 12, alignItems: 'center', width: '100%', padding: '10px 16px', border: 0, borderTop: '1px solid rgba(0,0,0,0.04)', background: 'transparent', textAlign: 'left', cursor: p.user_id === viewerId ? 'default' : 'pointer' }} aria-label="View member profile">
                <Avi name={(p.display_name || '??').slice(0, 2).toUpperCase()} size={34} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, color: T.text }} className="line-clamp-1">{p.display_name}{p.user_id === detail.created_by ? ' (Creator)' : ''}</div>
                </div>
                {p.role === 'admin' && <Pill text="Admin" />}
              </button>
            ))}
          </div>
        )}
        {detail?.is_group && (
          <div style={{ background: T.card, borderRadius: 14, marginTop: 12, overflow: 'hidden' }}>
            {leaveError && <div style={{ padding: '10px 16px', color: '#C94C4C', fontSize: 12, fontFamily: 'Plus Jakarta Sans' }}>{leaveError}</div>}
            <button onClick={leaveGroup} disabled={leaving} style={{ display: 'flex', gap: 12, alignItems: 'center', width: '100%', padding: '14px 16px', background: 'none', border: 'none', cursor: leaving ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: leaving ? 0.6 : 1 }}>
              <span aria-hidden="true" style={{ width:20,height:20,display:'inline-flex',alignItems:'center',justifyContent:'center' }}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M10 17l5-5-5-5M15 12H3"/><path d="M21 19V5a2 2 0 0 0-2-2h-7"/></svg></span>
              <span style={{ fontWeight: 700, fontSize: 13, color: '#C94C4C' }}>{leaving ? 'Leaving…' : 'Leave Group'}</span>
            </button>
          </div>
        )}
      </div>

      {showRename && (
        <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 50 }}>
          <div style={{ background: T.card, borderRadius: 20, padding: 24, width: '100%' }}>
            <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 16 }}>Rename Group</div>
            <input value={renameVal} onChange={e => setRenameVal(e.target.value)} maxLength={100} style={{ width: '100%', border: `1px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, boxSizing: 'border-box' }} />
            {renameError && <div style={{ color: '#C94C4C', fontSize: 12, marginTop: 8 }}>{renameError}</div>}
            <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
              <button onClick={() => setShowRename(false)} style={{ flex: 1, background: '#F3F4F6', border: 'none', borderRadius: 12, padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, color: T.text }}>Cancel</button>
              <button onClick={saveRename} disabled={renaming} style={{ flex: 1, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 12, padding: '12px 0', cursor: renaming ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 13, color: N.navy, opacity: renaming ? 0.7 : 1 }}>{renaming ? 'Saving…' : 'Save'}</button>
            </div>
          </div>
        </div>
      )}
      {showSearch && (
        <div onPointerDown={(event) => { if (event.target === event.currentTarget) { setShowSearch(false); setSearchQuery(''); setSearchResults([]) } }} style={{ position: 'absolute', inset: 0, background: T.pageBg, display: 'flex', flexDirection: 'column', zIndex: 50 }}>
          <div style={{ background: N.navy, padding: '0 18px 14px', flexShrink: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <button onClick={() => { setShowSearch(false); setSearchQuery(''); setSearchResults([]) }} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
              <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Search Messages</span>
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', background: 'rgba(255,255,255,0.09)', borderRadius: 12, padding: '9px 12px' }}>
              <div style={{ color: 'rgba(255,255,255,0.4)' }}>{Ic.search('w-4 h-4')}</div>
              <input autoFocus value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Search this conversation…" style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: 13, fontFamily: 'Plus Jakarta Sans' }} />
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }} className="scrollbar-hide">
            {searchError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 10 }}>{searchError}</div>}
            {!searchQuery.trim() ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 20px', textAlign: 'center' }}>
                <div style={{ fontSize: 44, marginBottom: 12 }}>🔍</div>
                <div style={{ fontWeight: 700, fontSize: 16, color: T.text }}>Search this chat</div>
                <div style={{ fontSize: 13, color: T.textMuted, marginTop: 4 }}>Start typing to find a message</div>
              </div>
            ) : searching ? (
              <div style={{ padding: '20px 0', textAlign: 'center', color: T.textMuted, fontSize: 13, fontFamily: 'Plus Jakarta Sans' }}>Searching…</div>
            ) : searchResults.length === 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 20px', textAlign: 'center' }}>
                <div style={{ fontSize: 44, marginBottom: 12 }}>🙁</div>
                <div style={{ fontWeight: 700, fontSize: 16, color: T.text }}>No messages found</div>
              </div>
            ) : searchResults.map(m => {
              const sender = detail?.participants.find(p => p.user_id === m.sender_id)
              const senderName = sender?.display_name || 'Deleted user'
              return (
                <div key={m.id} style={{ background: T.card, borderRadius: 14, padding: '12px 14px', marginBottom: 8, boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ fontWeight: 700, fontSize: 12, color: N.gold }}>{senderName}</span>
                    <span style={{ fontSize: 11, color: T.textMuted }}>{m.created_at ? new Date(m.created_at).toLocaleString() : ''}</span>
                  </div>
                  <div style={{ fontSize: 13, color: T.text, lineHeight: 1.55 }}>{m.body}</div>
                </div>
              )
            })}
          </div>
        </div>
      )}
      {showMedia && (
        <div onPointerDown={(event) => { if (event.target === event.currentTarget) setShowMedia(false) }} style={{ position: 'absolute', inset: 0, background: T.pageBg, display: 'flex', flexDirection: 'column', zIndex: 50 }}>
          <div style={{ background: N.navy, padding: '0 18px 14px', flexShrink: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button onClick={() => setShowMedia(false)} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
              <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Shared Media</span>
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }} className="scrollbar-hide">
            <div style={{ display: 'flex', gap: 6, overflowX: 'auto', paddingBottom: 10 }} role="tablist" aria-label="Shared media types">
              {([['all','All'],['images','Images'],['videos','Videos'],['audio','Audio'],['files','Files']] as const).map(([key,label]) => (
                <button key={key} type="button" role="tab" aria-selected={mediaTab === key} onClick={() => setMediaTab(key)} style={{ flexShrink: 0, border: mediaTab === key ? '1px solid '+N.gold : '1px solid '+T.border, borderRadius: 999, padding: '7px 11px', background: mediaTab === key ? N.gold+'18' : T.card, color: mediaTab === key ? N.gold : T.textMuted, fontSize: 11, fontWeight: 750, cursor: 'pointer' }}>{label}</button>
              ))}
            </div>
            {mediaError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 10 }}>{mediaError}</div>}
            {mediaLoading ? (
              <div style={{ padding: '20px 0', textAlign: 'center', color: T.textMuted, fontSize: 13, fontFamily: 'Plus Jakarta Sans' }}>Loading…</div>
            ) : mediaItems.length === 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 20px', textAlign: 'center' }}>
                <div style={{ color: T.textMuted, marginBottom: 12 }}>{Ic.image("w-10 h-10")}</div>
                <div style={{ fontWeight: 700, fontSize: 16, color: T.text }}>Nothing shared yet</div>
                <div style={{ fontSize: 13, color: T.textMuted, marginTop: 4 }}>Files and images sent in this chat will show up here</div>
              </div>
            ) : mediaItems.filter(item => mediaTab === 'all' || sharedMediaCategory(item, getFileExtension, imageFileTypes) === mediaTab).length === 0 ? (
              <div style={{ padding: '50px 20px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Nothing in this category yet</div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8 }}>
                {mediaItems.filter(item => mediaTab === 'all' || sharedMediaCategory(item, getFileExtension, imageFileTypes) === mediaTab).map(item => (
                  <a key={item.id} href={item.view_url || undefined} target="_blank" rel="noreferrer" style={{ textDecoration: 'none' }}>
                    {imageFileTypes.includes(item.file_type) ? (
                      <div style={{ aspectRatio: '1', borderRadius: 10, overflow: 'hidden', background: '#F3F4F6' }}>
                        <img src={item.view_url || undefined} alt={item.original_filename} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
                      </div>
                    ) : (
                      <div style={{ aspectRatio: '1', borderRadius: 10, background: '#F3F4F6', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4, padding: 8 }}>
                        <div style={{ color: T.textMuted }}>{Ic.paperclip("w-6 h-6")}</div>
                        <div style={{ fontSize: 9, color: T.textMuted, textAlign: 'center', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', width: '100%' }}>{item.original_filename}</div>
                      </div>
                    )}
                  </a>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── EDIT PROFILE ─────────────────────────────────────────────────────────────
type EditProfileMe = { id?: number; display_name: string | null; bio: string | null; year: number | null; semester: number | null; university_id: number | null; program_id: number | null; avatar_url?: string | null; csrf_token: string }
