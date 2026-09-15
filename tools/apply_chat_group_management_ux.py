"""Build-time patch for WhatsApp-style group info and membership controls.

Keeps groups on the existing WhatsAppChatExperience surface. The group header
opens a compact Group Info sheet; admins can add/remove members through the
existing multi-user Conversation APIs and rotate the existing E2EE epoch.
"""
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "frontend" / "src" / "crypto" / "WhatsAppChatExperience.tsx"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Group management UX patch anchor missing: {label}")
    if text.count(old) != 1:
        raise RuntimeError(f"Group management UX patch anchor is not unique: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "import { provisionInitialGroupKey } from './groupProvisioning'\n",
        "import { provisionInitialGroupKey, provisionRotatedGroupKey } from './groupProvisioning'\n",
        "rotated group key import",
    )

    text = replace_once(
        text,
        "  const [groupError, setGroupError] = useState('')\n",
        "  const [groupError, setGroupError] = useState('')\n  const [showGroupInfo, setShowGroupInfo] = useState(false)\n  const [groupMemberSearch, setGroupMemberSearch] = useState('')\n  const [groupMemberResults, setGroupMemberResults] = useState<GroupPickerUser[]>([])\n  const [groupMemberBusy, setGroupMemberBusy] = useState(false)\n  const [groupInfoError, setGroupInfoError] = useState('')\n",
        "group info state",
    )

    text = replace_once(
        text,
        "  const send = async () => {\n",
        """  useEffect(() => {
    if (!showGroupInfo || !isGroup) return
    const needle = groupMemberSearch.trim()
    if (needle.length < 2) { setGroupMemberResults([]); return }
    let cancelled = false
    const timer = window.setTimeout(() => {
      fetch(`/users/search?q=${encodeURIComponent(needle)}`, { credentials: 'include' })
        .then(async response => { const body = await response.json().catch(() => ({})); if (!response.ok) throw new Error(body?.error || 'Search failed'); return body })
        .then(body => { if (!cancelled) setGroupMemberResults(Array.isArray(body?.users) ? body.users : Array.isArray(body?.results) ? body.results : []) })
        .catch(() => { if (!cancelled) setGroupMemberResults([]) })
    }, 220)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [showGroupInfo, isGroup, groupMemberSearch])

  const refreshGroupDetail = async () => {
    if (selectedId == null) return
    const next = await api<Detail>(`/chats/${selectedId}`)
    setDetail(next)
    return next
  }

  const rotateGroupKeyAfterMembershipChange = async (nextDetail: Detail, epoch: number) => {
    if (!meIdRef.current) throw new Error('Your secure chat identity is unavailable')
    await ensureE2EEIdentityReady()
    const members = await Promise.all(nextDetail.participants.map(async participant => ({ userId: participant.user_id, publicKey: await fetchUserPublicKey(participant.user_id) })))
    const token = await getCsrfToken()
    await provisionRotatedGroupKey(nextDetail.id, epoch, meIdRef.current, members, (conversationId, envelopes) => uploadGroupKeyEnvelopes(conversationId, token, envelopes))
  }

  const addGroupMembers = async () => {
    if (selectedId == null || !detail || !isGroup || detail.participants.find(p => p.user_id === meIdRef.current)?.role !== 'admin') return
    const selected = groupMemberResults.filter(user => groupMemberSearch.trim().toLowerCase() === user.display_name.trim().toLowerCase())
    if (!selected.length) { setGroupInfoError('Search for a student, then tap their name to add them.'); return }
    setGroupMemberBusy(true); setGroupInfoError('')
    try {
      const token = await getCsrfToken()
      const result = await api<{ conversation: Detail; key_epoch: number }>(`/chats/${selectedId}/members`, { method:'POST', headers:{'X-CSRF-Token':token}, body:JSON.stringify({ user_ids:[selected[0].id] }) })
      await rotateGroupKeyAfterMembershipChange(result.conversation, result.key_epoch)
      setGroupMemberSearch(''); setGroupMemberResults([]); await refreshGroupDetail(); await loadList()
    } catch (value) { setGroupInfoError(friendlyError(value, 'Could not add that student to the group.')) }
    finally { setGroupMemberBusy(false) }
  }

  const removeGroupMember = async (member: Participant) => {
    if (selectedId == null || !detail || member.user_id === meIdRef.current || member.role === 'admin') return
    if (!window.confirm(`Remove ${member.display_name} from this group?`)) return
    setGroupMemberBusy(true); setGroupInfoError('')
    try {
      const token = await getCsrfToken()
      const result = await api<{ conversation: Detail; key_epoch: number }>(`/chats/${selectedId}/members/${member.user_id}`, { method:'DELETE', headers:{'X-CSRF-Token':token} })
      await rotateGroupKeyAfterMembershipChange(result.conversation, result.key_epoch)
      await refreshGroupDetail(); await loadList()
    } catch (value) { setGroupInfoError(friendlyError(value, 'Could not remove that member.')) }
    finally { setGroupMemberBusy(false) }
  }

  const send = async () => {
""",
        "group membership logic",
    )

    text = replace_once(
        text,
        "<div style={{ flex:1,minWidth:0 }}><div style={{ fontWeight:850,fontSize:14,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap' }}>{headerName}</div><div style={{ fontSize:10,opacity:.6 }}>{isGroup ? `${detail?.member_count || 0} members` : typingNames.length ? `${typingNames.join(', ')} ${typingNames.length === 1 ? 'is' : 'are'} typing…` : (onlineUsers.size ? 'online' : (realtimeConnected ? 'connected' : 'offline'))}</div></div>",
        "<button type=\"button\" onClick={() => isGroup ? (setGroupInfoError(''), setShowGroupInfo(true)) : undefined} disabled={!isGroup} aria-label={isGroup ? 'Open group info' : headerName} style={{ flex:1,minWidth:0,textAlign:'left',border:0,background:'transparent',padding:0,color:'#fff',cursor:isGroup ? 'pointer' : 'default' }}><div style={{ fontWeight:850,fontSize:14,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap' }}>{headerName}</div><div style={{ fontSize:10,opacity:.6 }}>{isGroup ? `${detail?.member_count || 0} members` : typingNames.length ? `${typingNames.join(', ')} ${typingNames.length === 1 ? 'is' : 'are'} typing…` : (onlineUsers.size ? 'online' : (realtimeConnected ? 'connected' : 'offline'))}</div></button>",
        "group header info trigger",
    )

    marker = "</style>\n    {showGroupCreator &&"
    modal = """</style>
    {showGroupInfo && isGroup && detail && <div role=\"dialog\" aria-modal=\"true\" aria-label=\"Group info\" style={{ position:'fixed',inset:0,zIndex:1150,background:'rgba(3,7,18,.72)',backdropFilter:'blur(8px)',display:'flex',alignItems:'stretch',justifyContent:'flex-end' }}>
      <div style={{ width:'min(420px,100%)',height:'100%',background:'#fff',display:'flex',flexDirection:'column',boxShadow:'-18px 0 60px rgba(0,0,0,.28)' }}>
        <div style={{ background:'#0b1437',color:'#fff',padding:'18px 18px 22px' }}>
          <div style={{ display:'flex',alignItems:'center',gap:10 }}><button type=\"button\" onClick={() => setShowGroupInfo(false)} aria-label=\"Close group info\" style={{ width:36,height:36,border:0,borderRadius:11,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer',fontSize:22 }}>‹</button><div style={{fontSize:16,fontWeight:850}}>Group info</div></div>
          <div style={{ marginTop:20,display:'flex',alignItems:'center',gap:13 }}><div style={{ width:58,height:58,borderRadius:18,background:'linear-gradient(135deg,#c9a84c,#e4c96a)',color:'#0b1437',display:'flex',alignItems:'center',justifyContent:'center',fontWeight:950,fontSize:20 }}>{initials(detail.name)}</div><div style={{minWidth:0}}><div style={{fontSize:17,fontWeight:900,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{detail.name}</div><div style={{fontSize:11,opacity:.65,marginTop:3}}>{detail.member_count} participants · E2EE</div></div></div>
        </div>
        <div style={{flex:1,overflowY:'auto',padding:'14px 0'}}>
          {detail.participants.find(p => p.user_id === meIdRef.current)?.role === 'admin' && <div style={{padding:'0 16px 15px'}}><div style={{fontSize:10,fontWeight:850,color:'#747b87',marginBottom:7}}>ADD MEMBERS</div><div style={{display:'flex',gap:8}}><input value={groupMemberSearch} onChange={event => setGroupMemberSearch(event.target.value)} placeholder=\"Search students\" style={{flex:1,height:42,border:'1px solid #dfe3e8',borderRadius:12,padding:'0 11px',outline:0,font:'inherit',fontSize:12}} /><button type=\"button\" onClick={() => void addGroupMembers()} disabled={groupMemberBusy || !groupMemberResults.length} style={{border:0,borderRadius:12;background:'#0b1437',color:'#e4c96a',padding:'0 13px',fontWeight:850,fontSize:11,cursor:'pointer'}}>Add</button></div>{groupMemberResults.length > 0 && <div style={{marginTop:6,border:'1px solid #eceef1',borderRadius:12,overflow:'hidden'}}>{groupMemberResults.slice(0,6).map(user => <button key={user.id} type=\"button\" onClick={() => { setGroupMemberSearch(user.display_name); setGroupMemberResults([user]) }} style={{width:'100%',display:'flex',alignItems:'center',gap:9,border:0,borderBottom:'1px solid #f0f1f3',background:'#fff',padding:'10px',textAlign:'left',cursor:'pointer'}}><span style={{width:32,height:32,borderRadius:10,background:'#f2ead1',color:'#0b1437',display:'flex',alignItems:'center',justifyContent:'center',fontWeight:900}}>{initials(user.display_name)}</span><span style={{fontSize:12,fontWeight:750}}>{user.display_name}</span></button>)}</div>}</div>}
          <div style={{padding:'8px 16px 6px',fontSize:10,fontWeight:850,color:'#747b87'}}>PARTICIPANTS · {detail.member_count}</div>
          {detail.participants.map(member => <div key={member.user_id} style={{display:'flex',alignItems:'center',gap:11,padding:'10px 16px'}}><div style={{width:42,height:42,borderRadius:13,background:'linear-gradient(135deg,#c9a84c,#e4c96a)',color:'#0b1437',display:'flex',alignItems:'center',justifyContent:'center',fontWeight:900}}>{initials(member.display_name)}</div><div style={{flex:1,minWidth:0}}><div style={{fontSize:12,fontWeight:800}}>{member.display_name}{member.user_id === meIdRef.current ? ' (You)' : ''}</div><div style={{fontSize:10,color:'#8a909a',marginTop:2}}>{member.role === 'admin' ? 'Group admin' : 'Participant'}</div></div>{detail.participants.find(p => p.user_id === meIdRef.current)?.role === 'admin' && member.user_id !== meIdRef.current && member.role !== 'admin' && <button type=\"button\" onClick={() => void removeGroupMember(member)} disabled={groupMemberBusy} style={{border:0;background:'transparent;color:#a33a35;fontSize:10;fontWeight:800,cursor:'pointer',padding:'7px'}}>Remove</button>}</div>)}
          {groupInfoError && <div style={{margin:'10px 16px',padding:11,borderRadius:12,background:'#fff1ef',color:'#a33a35',fontSize:11}}>{groupInfoError}</div>}
        </div>
        <div style={{padding:'13px 16px',borderTop:'1px solid #eceef1'}}><button type=\"button\" onClick={() => setShowGroupInfo(false)} style={{width:'100%',height:44,border:'1px solid #dfe3e8',background:'#fff',borderRadius:12,fontWeight:800,cursor:'pointer'}}>Done</button></div>
      </div>
    </div>}
    {showGroupCreator &&"""
    text = replace_once(text, marker, modal, "group info modal insertion")

    TARGET.write_text(text, encoding="utf-8")
    print("Applied WhatsApp-style group info and membership UX patch.")


if __name__ == "__main__":
    main()
