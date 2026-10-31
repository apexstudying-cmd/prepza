import { useEffect, useState, type ComponentType } from 'react'

import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Pill from '../../ui/Pill'
import type { GroupSummary, GroupPostData, GroupPostDetail, GroupMemberData, GroupFileData } from '../../types/groups'

// ─── GROUP DETAIL ─────────────────────────────────────────────────────────────
type GroupDetailScreenProps = {
  setScreen: (s: 'explore') => void
  groupId: number | null
  EmptyState: ComponentType<{ icon: string; title: string; sub: string; action?: string; onAction?: () => void }>
  ErrorState: ComponentType<{ onRetry?: () => void }>
}

type MyDocumentSummary = { id: number; title: string; status: string; file_type: string | null; page_count: number | null; created_at: string | null }

export default function GroupDetailScreen({ setScreen, groupId, EmptyState, ErrorState }: GroupDetailScreenProps) {
  const { tokens: T } = useTheme()
  const [tab, setTab] = useState<'Posts' | 'Questions' | 'Files' | 'Members'>('Posts')
  const [group, setGroup] = useState<GroupSummary | null>(null)
  const [loadingGroup, setLoadingGroup] = useState(true)
  const [groupError, setGroupError] = useState('')
  const [joining, setJoining] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const [actionError, setActionError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')

  const [posts, setPosts] = useState<GroupPostData[]>([])
  const [loadingPosts, setLoadingPosts] = useState(false)
  const [postsError, setPostsError] = useState('')
  const [composeText, setComposeText] = useState('')
  const [composing, setComposing] = useState(false)

  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [expandedDetail, setExpandedDetail] = useState<GroupPostDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [commentInput, setCommentInput] = useState('')
  const [sendingComment, setSendingComment] = useState(false)

  const [members, setMembers] = useState<GroupMemberData[]>([])
  const [loadingMembers, setLoadingMembers] = useState(false)
  const [membersError, setMembersError] = useState('')

  const [files, setFiles] = useState<GroupFileData[]>([])
  const [loadingFiles, setLoadingFiles] = useState(false)
  const [filesError, setFilesError] = useState('')
  const [shareableDocs, setShareableDocs] = useState<MyDocumentSummary[]>([])
  const [showFilePicker, setShowFilePicker] = useState(false)
  const [sharing, setSharing] = useState(false)

  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  const loadGroup = () => {
    if (groupId == null) return
    setLoadingGroup(true); setGroupError('')
    api<GroupSummary>(`/groups/${groupId}`)
      .then(setGroup)
      .catch(() => setGroupError('Could not load this group.'))
      .finally(() => setLoadingGroup(false))
  }
  useEffect(loadGroup, [groupId])

  const postType = tab === 'Questions' ? 'question' : 'post'
  const loadPosts = () => {
    if (groupId == null || (tab !== 'Posts' && tab !== 'Questions')) return
    setLoadingPosts(true); setPostsError('')
    api<{ page: number; posts: GroupPostData[] }>(`/groups/${groupId}/posts?type=${postType}`)
      .then(res => setPosts(res.posts))
      .catch(() => setPostsError('Could not load this tab.'))
      .finally(() => setLoadingPosts(false))
  }
  useEffect(loadPosts, [groupId, tab])

  useEffect(() => {
    if (groupId == null || tab !== 'Members') return
    setLoadingMembers(true); setMembersError('')
    api<{ members: GroupMemberData[] }>(`/groups/${groupId}/members`)
      .then(res => setMembers(res.members))
      .catch(() => setMembersError('Could not load members.'))
      .finally(() => setLoadingMembers(false))
  }, [groupId, tab])

  const loadFiles = () => {
    if (groupId == null || tab !== 'Files') return
    setLoadingFiles(true); setFilesError('')
    api<{ files: GroupFileData[] }>(`/groups/${groupId}/files`)
      .then(res => setFiles(res.files))
      .catch(() => setFilesError('Could not load files.'))
      .finally(() => setLoadingFiles(false))
  }
  useEffect(loadFiles, [groupId, tab])

  const doJoin = async () => {
    if (groupId == null || joining) return
    setJoining(true); setActionError('')
    try {
      await api(`/groups/${groupId}/join`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      loadGroup()
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Could not join this group.')
    } finally { setJoining(false) }
  }

  const doLeave = async () => {
    if (groupId == null || leaving) return
    setLeaving(true); setActionError('')
    try {
      await api(`/groups/${groupId}/leave`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      loadGroup()
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Could not leave this group.')
    } finally { setLeaving(false) }
  }

  const submitPost = async () => {
    if (groupId == null || !composeText.trim() || composing) return
    setComposing(true); setPostsError('')
    try {
      await api(`/groups/${groupId}/posts`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ post_type: postType, body: composeText.trim() }),
      })
      setComposeText('')
      loadPosts()
    } catch (e) {
      setPostsError(e instanceof ApiError ? e.message : 'Could not post. Please try again.')
    } finally { setComposing(false) }
  }

  const toggleLike = async (p: GroupPostData) => {
    if (groupId == null) return
    const method = p.viewer_liked ? 'DELETE' : 'POST'
    try {
      const res = await api<{ like_count: number }>(`/groups/${groupId}/posts/${p.id}/like`, { method, headers: { 'X-CSRF-Token': csrfToken } })
      setPosts(ps => ps.map(x => x.id === p.id ? { ...x, viewer_liked: !p.viewer_liked, like_count: res.like_count } : x))
    } catch { /* transient failure - the button just won't visually update, safe to ignore */ }
  }

  const toggleVote = async (p: GroupPostData) => {
    if (groupId == null) return
    const method = p.viewer_voted ? 'DELETE' : 'POST'
    try {
      const res = await api<{ vote_count: number }>(`/groups/${groupId}/posts/${p.id}/vote`, { method, headers: { 'X-CSRF-Token': csrfToken } })
      setPosts(ps => ps.map(x => x.id === p.id ? { ...x, viewer_voted: !p.viewer_voted, vote_count: res.vote_count } : x))
    } catch { /* transient failure - safe to ignore, same reasoning as toggleLike */ }
  }

  const openPost = (p: GroupPostData) => {
    if (expandedId === p.id) { setExpandedId(null); setExpandedDetail(null); return }
    if (groupId == null) return
    setExpandedId(p.id); setLoadingDetail(true); setExpandedDetail(null)
    api<GroupPostDetail>(`/groups/${groupId}/posts/${p.id}`)
      .then(setExpandedDetail)
      .catch(() => setPostsError('Could not load that thread.'))
      .finally(() => setLoadingDetail(false))
  }

  const submitComment = async () => {
    if (groupId == null || expandedId == null || !commentInput.trim() || sendingComment) return
    setSendingComment(true)
    try {
      await api(`/groups/${groupId}/posts/${expandedId}/comments`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ body: commentInput.trim() }),
      })
      setCommentInput('')
      const detail = await api<GroupPostDetail>(`/groups/${groupId}/posts/${expandedId}`)
      setExpandedDetail(detail)
      setPosts(ps => ps.map(x => x.id === expandedId ? { ...x, comment_count: detail.comments.length } : x))
    } catch { /* best-effort; the comment box just stays populated so the user can retry */ }
    finally { setSendingComment(false) }
  }

  const markHelpful = async (commentId: number) => {
    if (groupId == null || expandedId == null) return
    try {
      await api(`/groups/${groupId}/posts/${expandedId}/comments/${commentId}/helpful`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      const detail = await api<GroupPostDetail>(`/groups/${groupId}/posts/${expandedId}`)
      setExpandedDetail(detail)
    } catch { /* best-effort */ }
  }

  const changeRole = async (userId: number, role: 'admin' | 'member') => {
    if (groupId == null) return
    try {
      await api(`/groups/${groupId}/members/${userId}`, { method: 'PATCH', headers: { 'X-CSRF-Token': csrfToken }, body: JSON.stringify({ role }) })
      setMembers(ms => ms.map(m => m.user_id === userId ? { ...m, role } : m))
    } catch (e) { setMembersError(e instanceof ApiError ? e.message : 'Could not update that member.') }
  }

  const removeMember = async (userId: number) => {
    if (groupId == null) return
    try {
      await api(`/groups/${groupId}/members/${userId}`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
      setMembers(ms => ms.filter(m => m.user_id !== userId))
      setGroup(g => g ? { ...g, member_count: Math.max(0, g.member_count - 1) } : g)
    } catch (e) { setMembersError(e instanceof ApiError ? e.message : 'Could not remove that member.') }
  }

  const openFilePicker = () => {
    setShowFilePicker(true)
    api<{ documents: MyDocumentSummary[] }>('/documents')
      .then(res => setShareableDocs(res.documents.filter(d => d.status === 'ready')))
      .catch(() => setShareableDocs([]))
  }

  const shareDoc = async (documentId: number) => {
    if (groupId == null || sharing) return
    setSharing(true)
    try {
      await api(`/groups/${groupId}/files`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken }, body: JSON.stringify({ document_id: documentId }) })
      setShowFilePicker(false)
      loadFiles()
    } catch (e) {
      setFilesError(e instanceof ApiError ? e.message : 'Could not share that file.')
    } finally { setSharing(false) }
  }

  const removeFile = async (fileId: number) => {
    if (groupId == null) return
    try {
      await api(`/groups/${groupId}/files/${fileId}`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
      setFiles(fs => fs.filter(f => f.id !== fileId))
    } catch (e) { setFilesError(e instanceof ApiError ? e.message : 'Could not remove that file.') }
  }

  if (groupId == null) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
        <div style={{ background: N.navy, padding: '0 18px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => window.history.back()} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Group</span>
          </div>
        </div>
        <EmptyState icon="👥" title="No group selected" sub="Go back and pick a group first." action="Find Groups" onAction={() => setScreen('explore')} />
      </div>
    )
  }

  if (loadingGroup) {
    return <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: T.pageBg, fontSize: 12, color: T.textMuted }}>Loading group…</div>
  }

  if (!group) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
        <div style={{ background: N.navy, padding: '0 18px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => window.history.back()} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Group</span>
          </div>
        </div>
        <ErrorState onRetry={loadGroup} />
      </div>
    )
  }

  const joined = group.is_member
  const isAdmin = group.role === 'admin'

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      {/* Header */}
      <div style={{ background: N.navy, padding: '0 18px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <button onClick={() => window.history.back()} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: 16, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{group.name}</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginTop: 1 }}>{group.member_count} member{group.member_count === 1 ? '' : 's'}{group.unit_code ? ` · ${group.unit_code}` : ''}</div>
          </div>
          {joined ? (
            <button onClick={doLeave} disabled={leaving} style={{ background: 'rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.8)', fontWeight: 700, fontSize: 12, border: 'none', borderRadius: 10, padding: '8px 14px', cursor: leaving ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{leaving ? '…' : 'Joined'}</button>
          ) : (
            <button onClick={doJoin} disabled={joining} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 700, fontSize: 12, border: 'none', borderRadius: 10, padding: '8px 14px', cursor: joining ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{joining ? '…' : 'Join'}</button>
          )}
        </div>
        {actionError && <div style={{ color: '#FFB4B4', fontSize: 11, fontWeight: 600, marginBottom: 10 }}>{actionError}</div>}
        <div style={{ display: 'flex', gap: 0 }}>
          {(['Posts', 'Questions', 'Files', 'Members'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{ flex: 1, background: 'none', border: 'none', borderBottom: `2px solid ${tab === t ? N.gold : 'transparent'}`, color: tab === t ? N.gold : 'rgba(255,255,255,0.5)', fontWeight: tab === t ? 700 : 500, fontSize: 13, padding: '10px 0 10px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', transition: 'all 0.2s' }}>
              {t}
            </button>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }} className="scrollbar-hide">
        {(tab === 'Posts' || tab === 'Questions') && (
          <div style={{ padding: '14px 18px' }}>
            {!joined && (
              <div style={{ background: 'rgba(201,168,76,0.08)', border: `1px solid ${N.gold}30`, borderRadius: 12, padding: '10px 14px', marginBottom: 14, fontSize: 12, color: T.textMuted }}>Join this group to post, comment, like, and vote.</div>
            )}
            {joined && (
              <div style={{ background: T.card, border: '1.5px solid rgba(0,0,0,0.08)', borderRadius: 14, padding: 12, marginBottom: 14, boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
                <textarea value={composeText} onChange={e => setComposeText(e.target.value)} placeholder={tab === 'Questions' ? 'Ask the group a question…' : 'Write something…'} rows={2} style={{ width: '100%', border: 'none', outline: 'none', fontSize: 13, color: T.text, fontFamily: 'Plus Jakarta Sans', resize: 'none', boxSizing: 'border-box' }} />
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 6 }}>
                  <button onClick={submitPost} disabled={!composeText.trim() || composing} style={{ background: composeText.trim() ? `linear-gradient(135deg,${N.gold},${N.goldL})` : '#E5E7EB', color: composeText.trim() ? N.navy : T.textMuted, fontWeight: 700, fontSize: 12, border: 'none', borderRadius: 10, padding: '7px 16px', cursor: composeText.trim() ? 'pointer' : 'not-allowed', fontFamily: 'Plus Jakarta Sans' }}>{composing ? 'Posting…' : tab === 'Questions' ? 'Ask' : 'Post'}</button>
                </div>
              </div>
            )}
            {postsError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 10 }}>{postsError}</div>}
            {loadingPosts ? (
              <div style={{ fontSize: 12, color: T.textMuted, padding: '20px 0' }}>Loading…</div>
            ) : posts.length === 0 ? (
              <EmptyState icon={tab === 'Questions' ? '❓' : '💬'} title={tab === 'Questions' ? 'No questions yet' : 'No posts yet'} sub={joined ? 'Be the first to share something.' : 'Join the group to get things started.'} />
            ) : posts.map(p => (
              <div key={p.id} style={{ background: T.card, borderRadius: 16, padding: '14px 16px', marginBottom: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
                <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
                  <div style={{ width: 36, height: 36, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, color: N.navy, flexShrink: 0 }}>{p.author.slice(0, 2).toUpperCase()}</div>
                  <div><div style={{ fontWeight: 700, fontSize: 13, color: T.text }}>{p.author}</div><div style={{ fontSize: 11, color: T.textMuted }}>{p.created_at ? new Date(p.created_at).toLocaleString() : ''}</div></div>
                </div>
                <div style={{ fontSize: 13, color: T.text, lineHeight: 1.65, marginBottom: 12 }}>{p.is_removed ? '[removed]' : p.body}</div>
                <div style={{ display: 'flex', gap: 16, borderTop: '1px solid #F3F4F6', paddingTop: 10 }}>
                  {tab === 'Posts' ? (
                    <button onClick={() => toggleLike(p)} disabled={!joined} style={{ background: 'none', border: 'none', display: 'flex', alignItems: 'center', gap: 5, color: p.viewer_liked ? N.gold : T.textMuted, cursor: joined ? 'pointer' : 'default', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>
                      <svg width="14" height="14" viewBox="0 0 14 14" fill={p.viewer_liked ? N.gold : 'none'} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M7 12.5S1.5 9 1.5 5a2.5 2.5 0 015-0 2.5 2.5 0 015 0c0 4-5.5 7.5-5.5 7.5z"/></svg>
                      {p.like_count ?? 0}
                    </button>
                  ) : (
                    <button onClick={() => toggleVote(p)} disabled={!joined} style={{ background: 'none', border: 'none', display: 'flex', alignItems: 'center', gap: 5, color: p.viewer_voted ? N.gold : T.textMuted, cursor: joined ? 'pointer' : 'default', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M7 2v10M3 6l4-4 4 4" /></svg>
                      {p.vote_count ?? 0} vote{(p.vote_count ?? 0) === 1 ? '' : 's'}
                    </button>
                  )}
                  <button onClick={() => openPost(p)} style={{ background: 'none', border: 'none', display: 'flex', alignItems: 'center', gap: 5, color: T.textMuted, cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M2 2h10a1 1 0 011 1v6a1 1 0 01-1 1H5l-3 3V3a1 1 0 011-1z"/></svg>
                    {p.comment_count} {expandedId === p.id ? '· hide' : ''}
                  </button>
                </div>
                {expandedId === p.id && (
                  <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #F3F4F6' }}>
                    {loadingDetail ? (
                      <div style={{ fontSize: 12, color: T.textMuted }}>Loading replies…</div>
                    ) : !expandedDetail ? (
                      <div style={{ fontSize: 12, color: '#C94C4C' }}>Could not load replies.</div>
                    ) : (
                      <>
                        {expandedDetail.comments.length === 0 && <div style={{ fontSize: 12, color: T.textMuted, marginBottom: 10 }}>No replies yet.</div>}
                        {expandedDetail.comments.map(c => (
                          <div key={c.id} style={{ background: T.pageBg, borderRadius: 12, padding: '10px 12px', marginBottom: 8 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                              <span style={{ fontWeight: 700, fontSize: 12, color: T.text }}>{c.author}{c.marked_helpful && <span style={{ marginLeft: 6, color: '#4CC97B', fontWeight: 700 }}>✓ Helpful</span>}</span>
                              {tab === 'Questions' && p.author_id !== c.author_id && !c.marked_helpful && !c.is_removed && (
                                <button onClick={() => markHelpful(c.id)} style={{ background: 'none', border: 'none', color: N.gold, fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Mark helpful</button>
                              )}
                            </div>
                            <div style={{ fontSize: 12, color: T.text }}>{c.is_removed ? '[removed]' : c.body}</div>
                          </div>
                        ))}
                        {joined && (
                          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                            <input value={commentInput} onChange={e => setCommentInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && submitComment()} placeholder="Reply…" style={{ flex: 1, border: '1px solid rgba(0,0,0,0.1)', borderRadius: 10, padding: '8px 12px', fontSize: 12, outline: 'none', fontFamily: 'Plus Jakarta Sans' }} />
                            <button onClick={submitComment} disabled={!commentInput.trim() || sendingComment} style={{ background: N.gold, color: N.navy, border: 'none', borderRadius: 10, padding: '8px 14px', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{sendingComment ? '…' : 'Send'}</button>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        {tab === 'Files' && (
          <div style={{ padding: '14px 18px' }}>
            {joined && (
              <button onClick={openFilePicker} style={{ width: '100%', background: T.card, border: `1.5px dashed ${T.border}`, borderRadius: 14, padding: '12px 16px', marginBottom: 14, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontSize: 13, color: N.gold, fontWeight: 700, textAlign: 'center' }}>+ Share a document</button>
            )}
            {filesError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 10 }}>{filesError}</div>}
            {loadingFiles ? (
              <div style={{ fontSize: 12, color: T.textMuted, padding: '20px 0' }}>Loading…</div>
            ) : files.length === 0 ? (
              <EmptyState icon="📁" title="No files shared yet" sub="Members can share their own ready documents here." />
            ) : files.map(f => (
              <div key={f.id} style={{ background: T.card, borderRadius: 14, padding: '14px 16px', marginBottom: 10, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
                <div style={{ width: 40, height: 44, background: '#F3F4F6', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, cursor: f.view_url ? 'pointer' : 'default' }} onClick={() => f.view_url && window.open(f.view_url, '_blank')}>
                  <svg width="18" height="22" viewBox="0 0 20 24" fill="none"><path d="M4 0h8l8 8v16H4V0z" fill="#E5E7EB"/><path d="M12 0l8 8h-8V0z" fill="#D1D5DB"/></svg>
                </div>
                <div style={{ flex: 1, minWidth: 0, cursor: f.view_url ? 'pointer' : 'default' }} onClick={() => f.view_url && window.open(f.view_url, '_blank')}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.title || 'Untitled document'}</div>
                  <div style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>{f.shared_by}{f.page_count ? ` · ${f.page_count} pages` : ''}</div>
                </div>
                {(isAdmin || f.shared_by_user_id !== undefined) && (
                  <button onClick={() => removeFile(f.id)} style={{ background: 'none', border: 'none', color: '#C94C4C', fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Remove</button>
                )}
              </div>
            ))}
            {showFilePicker && (
              <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'flex-end', zIndex: 100 }} onClick={() => setShowFilePicker(false)}>
                <div style={{ background: T.card, width: '100%', borderRadius: '18px 18px 0 0', padding: 18, maxHeight: '60vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
                  <div style={{ fontWeight: 800, fontSize: 14, color: T.text, marginBottom: 12 }}>Share a document</div>
                  {shareableDocs.length === 0 ? (
                    <div style={{ fontSize: 12, color: T.textMuted }}>You have no ready documents to share yet.</div>
                  ) : shareableDocs.map(d => (
                    <button key={d.id} onClick={() => shareDoc(d.id)} disabled={sharing} style={{ width: '100%', textAlign: 'left', background: T.pageBg, border: 'none', borderRadius: 12, padding: '10px 14px', marginBottom: 8, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontSize: 13, color: T.text }}>{d.title}</button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
        {tab === 'Members' && (
          <div style={{ padding: '14px 18px' }}>
            <div style={{ fontSize: 12, color: T.textMuted, fontWeight: 600, marginBottom: 12 }}>{group.member_count} MEMBER{group.member_count === 1 ? '' : 'S'}</div>
            {membersError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 10 }}>{membersError}</div>}
            {loadingMembers ? (
              <div style={{ fontSize: 12, color: T.textMuted, padding: '20px 0' }}>Loading…</div>
            ) : members.map(m => (
              <div key={m.user_id} style={{ background: T.card, borderRadius: 14, padding: '12px 16px', marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
                <div style={{ width: 38, height: 38, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, color: N.navy, flexShrink: 0 }}>{m.display_name.slice(0, 2).toUpperCase()}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, color: T.text }}>{m.display_name}</div>
                </div>
                {m.role === 'admin' && <Pill text="Admin" color={N.gold} />}
                {isAdmin && (
                  <div style={{ display: 'flex', gap: 6, marginLeft: 8 }}>
                    <button onClick={() => changeRole(m.user_id, m.role === 'admin' ? 'member' : 'admin')} style={{ background: 'none', border: 'none', color: N.gold, fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{m.role === 'admin' ? 'Demote' : 'Promote'}</button>
                    {m.role !== 'admin' && <button onClick={() => removeMember(m.user_id)} style={{ background: 'none', border: 'none', color: '#C94C4C', fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Remove</button>}
                  </div>
                )}
              </div>
            ))}
            <div style={{ height: 16 }} />
          </div>
        )}
      </div>
    </div>
  )
}
