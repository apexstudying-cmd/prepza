"""Build-time patch for completing the chat test surface.

Adds a first-class new direct-chat picker and lightweight group member
management to the existing WhatsApp-style chat experience. It intentionally
uses the existing /chats and /chats/<id>/members APIs and existing E2EE setup.
"""
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "frontend" / "src" / "crypto" / "WhatsAppChatExperience.tsx"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Chat completion patch anchor missing: {label}")
    if text.count(old) != 1:
        raise RuntimeError(f"Chat completion patch anchor is not unique: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "  const [groupError, setGroupError] = useState('')\n",
        """  const [groupError, setGroupError] = useState('')
  const [showNewChat, setShowNewChat] = useState(false)
  const [newChatSearch, setNewChatSearch] = useState('')
  const [newChatUsers, setNewChatUsers] = useState<GroupPickerUser[]>([])
  const [newChatCreating, setNewChatCreating] = useState(false)
  const [newChatError, setNewChatError] = useState('')
  const [showGroupMembers, setShowGroupMembers] = useState(false)
  const [memberSearch, setMemberSearch] = useState('')
  const [memberUsers, setMemberUsers] = useState<GroupPickerUser[]>([])
  const [memberBusy, setMemberBusy] = useState<number | null>(null)
  const [memberError, setMemberError] = useState('')
""",
        "chat completion state",
    )

    text = replace_once(
        text,
        "  const createChatGroup = async () => {\n",
        """  useEffect(() => {
    if (!showNewChat) return
    const needle = newChatSearch.trim()
    if (needle.length < 2) { setNewChatUsers([]); return }
    let cancelled = false
    const timer = window.setTimeout(() => {
      fetch(`/users/search?q=${encodeURIComponent(needle)}`, { credentials: 'include' })
        .then(async response => { const body = await response.json().catch(() => ({})); if (!response.ok) throw new Error(body?.error || 'Could not search students'); return body })
        .then(body => { if (!cancelled) setNewChatUsers(Array.isArray(body?.users) ? body.users : Array.isArray(body?.results) ? body.results : []) })
        .catch(() => { if (!cancelled) setNewChatUsers([]) })
    }, 220)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [showNewChat, newChatSearch])

  useEffect(() => {
    if (!showGroupMembers) return
    const needle = memberSearch.trim()
    if (needle.length < 2) { setMemberUsers([]); return }
    let cancelled = false
    const timer = window.setTimeout(() => {
      fetch(`/users/search?q=${encodeURIComponent(needle)}`, { credentials: 'include' })
        .then(async response => { const body = await response.json().catch(() => ({})); if (!response.ok) throw new Error(body?.error || 'Could not search students'); return body })
        .then(body => { if (!cancelled) setMemberUsers(Array.isArray(body?.users) ? body.users : Array.isArray(body?.results) ? body.results : []) })
        .catch(() => { if (!cancelled) setMemberUsers([]) })
    }, 220)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [showGroupMembers, memberSearch])

  const openNewChat = () => { setNewChatSearch(''); setNewChatUsers([]); setNewChatError(''); setShowNewChat(true) }
  const createDirectChat = async (user: GroupPickerUser) => {
    if (newChatCreating) return
    setNewChatCreating(true); setNewChatError('')
    try {
      const token = await getCsrfToken()
      await ensureE2EEIdentityReady()
      const created = await api<{ id: number }>(`/chats`, { method:'POST', headers:{'X-CSRF-Token':token}, body:JSON.stringify({ is_group:false, participant_ids:[user.id] }) })
      if (!created?.id) throw new Error('The chat could not be created')
      setShowNewChat(false); await loadList(); chooseChat(created.id)
    } catch (value) { setNewChatError(friendlyError(value, 'Could not start this secure chat.')) }
    finally { setNewChatCreating(false) }
  }

  const openGroupMembers = () => { setMemberSearch(''); setMemberUsers([]); setMemberError(''); setShowGroupMembers(true) }
  const addGroupMember = async (user: GroupPickerUser) => {
    if (selectedId == null || memberBusy != null) return
    if (detail?.participants.some(member => member.user_id === user.id && !member.role)) return
    setMemberBusy(user.id); setMemberError('')
    try {
      const token = await getCsrfToken()
      await api(`/chats/${selectedId}/members`, { method:'POST', headers:{'X-CSRF-Token':token}, body:JSON.stringify({ user_ids:[user.id] }) })
      const nextDetail = await api<Detail>(`/chats/${selectedId}`); setDetail(nextDetail); setMemberSearch(''); setMemberUsers([])
    } catch (value) { setMemberError(friendlyError(value, 'Could not add this student. They may need secure chat enabled first.')) }
    finally { setMemberBusy(null) }
  }

  const removeGroupMember = async (userId: number) => {
    if (selectedId == null || memberBusy != null) return
    setMemberBusy(userId); setMemberError('')
    try {
      const token = await getCsrfToken()
      await api(`/chats/${selectedId}/members/${userId}`, { method:'DELETE', headers:{'X-CSRF-Token':token} })
      const nextDetail = await api<Detail>(`/chats/${selectedId}`); setDetail(nextDetail)
    } catch (value) { setMemberError(friendlyError(value, 'Could not remove this member.')) }
    finally { setMemberBusy(null) }
  }

  const createChatGroup = async () => {
""",
        "direct/group management logic",
    )

    text = replace_once(
        text,
        "    {showGroupCreator && <div role=\"dialog\" aria-modal=\"true\" aria-label=\"Create group chat\"",
        """    {showNewChat && <div role=\"dialog\" aria-modal=\"true\" aria-label=\"Start secure chat\" style={{ position:'fixed',inset:0,zIndex:1150,background:'rgba(3,7,18,.72)',backdropFilter:'blur(8px)',display:'flex',alignItems:'center',justifyContent:'center',padding:16 }}>
      <div style={{ width:'min(480px,100%)',maxHeight:'min(700px,92vh)',display:'flex',flexDirection:'column',background:'#fff',borderRadius:22,overflow:'hidden',boxShadow:'0 24px 70px rgba(0,0,0,.35)' }}>
        <div style={{ background:'#0b1437',color:'#fff',padding:'18px',display:'flex',alignItems:'center',gap:12 }}><button type=\"button\" onClick={() => setShowNewChat(false)} disabled={newChatCreating} aria-label=\"Close new chat\" style={{ width:36,height:36,border:0,borderRadius:11,background:'rgba(255,255,255,.1)',color:'#fff',fontSize:22 }}>‹</button><div><div style={{fontSize:17,fontWeight:850}}>New secure chat</div><div style={{marginTop:3,fontSize:11,opacity:.62}}>Search a student to start a private conversation.</div></div></div>
        <div style={{padding:18,overflowY:'auto',flex:1}}><input value={newChatSearch} onChange={event => setNewChatSearch(event.target.value)} autoFocus placeholder=\"Search students by name\" style={{width:'100%',boxSizing:'border-box',height:46,border:'1px solid #dfe3e8',borderRadius:12,padding:'0 13px',outline:'none',font:'inherit',fontSize:13}} />
          <div style={{marginTop:12}}>{newChatSearch.trim().length < 2 && <div style={{padding:'28px 10px',textAlign:'center',color:'#8b919b',fontSize:12}}>Type at least 2 characters to find students.</div>}{newChatSearch.trim().length >= 2 && !newChatUsers.length && <div style={{padding:'28px 10px',textAlign:'center',color:'#8b919b',fontSize:12}}>No students found.</div>}{newChatUsers.map(user => <button key={user.id} type=\"button\" onClick={() => void createDirectChat(user)} disabled={newChatCreating} style={{width:'100%',display:'flex',alignItems:'center',gap:11,border:0,borderBottom:'1px solid #f0f1f3',background:'#fff',padding:'11px 4px',textAlign:'left',cursor:'pointer'}}><span style={{width:40,height:40,borderRadius:13,background:'linear-gradient(135deg,#c9a84c,#e4c96a)',color:'#0b1437',display:'flex',alignItems:'center',justifyContent:'center',fontWeight:900}}>{initials(user.display_name)}</span><span style={{flex:1,fontSize:13,fontWeight:750}}>{user.display_name}</span><span style={{fontSize:10,color:'#737985'}}>{newChatCreating ? 'Opening…' : 'Chat'}</span></button>)}</div>
          {newChatError && <div style={{marginTop:14,padding:11,borderRadius:12,background:'#fff1ef',color:'#a33a35',fontSize:11}}>{newChatError}</div>}
        </div>
      </div>
    </div>}
    {showGroupMembers && isGroup && <div role=\"dialog\" aria-modal=\"true\" aria-label=\"Manage group members\" style={{ position:'fixed',inset:0,zIndex:1150,background:'rgba(3,7,18,.72)',backdropFilter:'blur(8px)',display:'flex',alignItems:'center',justifyContent:'center',padding:16 }}>
      <div style={{ width:'min(520px,100%)',maxHeight:'min(760px,92vh)',display:'flex',flexDirection:'column',background:'#fff',borderRadius:22,overflow:'hidden',boxShadow:'0 24px 70px rgba(0,0,0,.35)' }}>
        <div style={{background:'#0b1437',color:'#fff',padding:'18px',display:'flex',alignItems:'center',gap:12}}><button type=\"button\" onClick={() => setShowGroupMembers(false)} disabled={memberBusy != null} aria-label=\"Close group members\" style={{width:36,height:36,border:0,borderRadius:11,background:'rgba(255,255,255,.1)',color:'#fff',fontSize:22}}>‹</button><div><div style={{fontSize:17,fontWeight:850}}>Group members</div><div style={{marginTop:3,fontSize:11,opacity:.62}}>{detail?.member_count || 0} active members</div></div></div>
        <div style={{padding:18,overflowY:'auto',flex:1}}><div style={{fontSize:11,fontWeight:850,color:'#626874',marginBottom:8}}>CURRENT MEMBERS</div>{detail?.participants.map(member => <div key={member.user_id} style={{display:'flex',alignItems:'center',gap:10,padding:'9px 0',borderBottom:'1px solid #f0f1f3'}}><span style={{width:38,height:38,borderRadius:12,background:'#f1f2f4',display:'grid',placeItems:'center',fontWeight:850,color:'#0b1437'}}>{initials(member.display_name)}</span><span style={{flex:1,fontSize:12,fontWeight:750}}>{member.display_name}{member.user_id === meId ? ' · You' : ''}</span><span style={{fontSize:10,color:'#8a909b'}}>{member.role === 'admin' ? 'Admin' : 'Member'}</span>{member.user_id !== meId && member.role !== 'admin' && <button type=\"button\" onClick={() => void removeGroupMember(member.user_id)} disabled={memberBusy != null} style={{border:0,background:'#fff0ef',color:'#a33a35',borderRadius:9,padding:'6px 8px',fontSize:10,fontWeight:800}}>Remove</button>}</div>)}
          <div style={{fontSize:11,fontWeight:850,color:'#626874',margin:'20px 0 8px'}}>ADD MEMBER</div><input value={memberSearch} onChange={event => setMemberSearch(event.target.value)} placeholder=\"Search students\" style={{width:'100%',boxSizing:'border-box',height:42,border:'1px solid #dfe3e8',borderRadius:12,padding:'0 12px',outline:0,font:'inherit',fontSize:12}} />
          <div style={{marginTop:8}}>{memberSearch.trim().length >= 2 && memberUsers.filter(user => !detail?.participants.some(member => member.user_id === user.id)).map(user => <button key={user.id} type=\"button\" onClick={() => void addGroupMember(user)} disabled={memberBusy != null} style={{width:'100%',display:'flex',alignItems:'center',gap:10,border:0,borderBottom:'1px solid #f0f1f3',background:'#fff',padding:'10px 3px',textAlign:'left'}}><span style={{width:36,height:36,borderRadius:11,background:'#f5f2e8',display:'grid',placeItems:'center',fontWeight:850,color:'#0b1437'}}>{initials(user.display_name)}</span><span style={{flex:1,fontSize:12,fontWeight:750}}>{user.display_name}</span><span style={{fontSize:10,color:'#8a6b20'}}>{memberBusy === user.id ? 'Adding…' : 'Add'}</span></button>)}</div>
          {memberError && <div style={{marginTop:12,padding:11,borderRadius:12,background:'#fff1ef',color:'#a33a35',fontSize:11}}>{memberError}</div>}
        </div>
      </div>
    </div>}
    {showGroupCreator && <div role=\"dialog\" aria-modal=\"true\" aria-label=\"Create group chat\""" + """""",
        "new chat and group members modals",
    )

    text = replace_once(
        text,
        "<button type=\"button\" onClick={openGroupCreator} aria-label=\"New group\" title=\"Create a group chat\"",
        "<button type=\"button\" onClick={openNewChat} aria-label=\"New chat\" title=\"Start a secure chat\" style={{ width:34,height:34,border:0,borderRadius:10,background:'rgba(201,168,76,.16)',color:'#e4c96a',cursor:'pointer',fontSize:18 }}>＋</button><button type=\"button\" onClick={openGroupCreator} aria-label=\"New group\" title=\"Create a group chat\"",
        "new chat header button",
    )

    text = replace_once(
        text,
        "<div title=\"End-to-end encrypted\" style={{ fontSize:10,opacity:.65 }}>E2EE</div>",
        "<div title=\"End-to-end encrypted\" style={{ fontSize:10,opacity:.65 }}>E2EE</div>{isGroup && <button type=\"button\" onClick={openGroupMembers} aria-label=\"Manage group members\" title=\"Manage group members\" style={{ border:'1px solid rgba(201,168,76,.35)',background:'rgba(201,168,76,.1)',color:'#e4c96a',borderRadius:11,padding:'8px 9px',fontWeight:900,fontSize:10,cursor:'pointer' }}>Members</button>}",
        "group members header button",
    )

    TARGET.write_text(text, encoding="utf-8")
    print("Applied direct-chat and group member management patch.")


if __name__ == "__main__":
    main()
