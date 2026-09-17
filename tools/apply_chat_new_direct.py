from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'crypto' / 'WhatsAppChatExperience.tsx'

def once(text, old, new, label):
    if new in text: return text
    if text.count(old) != 1: raise RuntimeError(f'New chat patch anchor missing: {label}')
    return text.replace(old, new, 1)

def main():
    text = TARGET.read_text(encoding='utf-8')
    text = once(text, "  const [groupError, setGroupError] = useState('')\n", "  const [groupError, setGroupError] = useState('')\n  const [showNewChat, setShowNewChat] = useState(false)\n  const [newChatSearch, setNewChatSearch] = useState('')\n  const [newChatUsers, setNewChatUsers] = useState<GroupPickerUser[]>([])\n  const [newChatCreating, setNewChatCreating] = useState(false)\n  const [newChatError, setNewChatError] = useState('')\n", 'state')
    logic = """  useEffect(() => {
    if (!showNewChat) return
    const needle = newChatSearch.trim()
    if (needle.length < 2) { setNewChatUsers([]); return }
    let cancelled = false
    const timer = window.setTimeout(() => {
      fetch(`/users/search?q=${encodeURIComponent(needle)}`, { credentials:'include' })
        .then(async response => { const body = await response.json().catch(() => ({})); if (!response.ok) throw new Error(body?.error || 'Could not search students'); return body })
        .then(body => { if (!cancelled) setNewChatUsers(Array.isArray(body?.users) ? body.users : Array.isArray(body?.results) ? body.results : []) })
        .catch(() => { if (!cancelled) setNewChatUsers([]) })
    }, 220)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [showNewChat, newChatSearch])

  const openNewChat = () => { setNewChatSearch(''); setNewChatUsers([]); setNewChatError(''); setShowNewChat(true) }
  const createDirectChat = async (user: GroupPickerUser) => {
    if (newChatCreating) return
    setNewChatCreating(true); setNewChatError('')
    try {
      const token = await getCsrfToken()
      await ensureE2EEIdentityReady()
      const created = await api<{ id:number }>(`/chats`, { method:'POST', headers:{'X-CSRF-Token':token}, body:JSON.stringify({ is_group:false, participant_ids:[user.id] }) })
      if (!created?.id) throw new Error('The chat could not be created')
      setShowNewChat(false); await loadList(); chooseChat(created.id)
    } catch (value) { setNewChatError(friendlyError(value, 'Could not start this secure chat.')) }
    finally { setNewChatCreating(false) }
  }

"""
    text = once(text, "  const createChatGroup = async () => {\n", logic + "  const createChatGroup = async () => {\n", 'logic')
    modal = """    {showNewChat && <div role=\"dialog\" aria-modal=\"true\" aria-label=\"Start secure chat\" style={{position:'fixed',inset:0,zIndex:1150,background:'rgba(3,7,18,.72)',display:'flex',alignItems:'center',justifyContent:'center',padding:16}}><div style={{width:'min(480px,100%)',maxHeight:'90vh',display:'flex',flexDirection:'column',background:'#fff',borderRadius:22,overflow:'hidden',boxShadow:'0 24px 70px rgba(0,0,0,.35)'}}><div style={{background:'#0b1437',color:'#fff',padding:18,display:'flex',alignItems:'center',gap:12}}><button type=\"button\" onClick={() => setShowNewChat(false)} disabled={newChatCreating} aria-label=\"Close new chat\" style={{width:36,height:36,border:0,borderRadius:11,background:'rgba(255,255,255,.1)',color:'#fff',fontSize:22}}>‹</button><div><div style={{fontSize:17,fontWeight:850}}>New secure chat</div><div style={{fontSize:11,opacity:.62,marginTop:3}}>Search a student to start a private conversation.</div></div></div><div style={{padding:18,overflowY:'auto',flex:1}}><input value={newChatSearch} onChange={event => setNewChatSearch(event.target.value)} autoFocus placeholder=\"Search students by name\" style={{width:'100%',boxSizing:'border-box',height:46,border:'1px solid #dfe3e8',borderRadius:12,padding:'0 13px',outline:0,font:'inherit',fontSize:13}} /><div style={{marginTop:12}}>{newChatSearch.trim().length < 2 && <div style={{padding:28,textAlign:'center',color:'#8b919b',fontSize:12}}>Type at least 2 characters to find students.</div>}{newChatSearch.trim().length >= 2 && !newChatUsers.length && <div style={{padding:28,textAlign:'center',color:'#8b919b',fontSize:12}}>No students found.</div>}{newChatUsers.map(user => <button key={user.id} type=\"button\" onClick={() => void createDirectChat(user)} disabled={newChatCreating} style={{width:'100%',display:'flex',alignItems:'center',gap:11,border:0,borderBottom:'1px solid #f0f1f3',background:'#fff',padding:'11px 4px',textAlign:'left'}}><span style={{width:40,height:40,borderRadius:13,background:'linear-gradient(135deg,#c9a84c,#e4c96a)',color:'#0b1437',display:'grid',placeItems:'center',fontWeight:900}}>{initials(user.display_name)}</span><span style={{flex:1,fontSize:13,fontWeight:750}}>{user.display_name}</span><span style={{fontSize:10,color:'#737985'}}>{newChatCreating ? 'Opening…' : 'Chat'}</span></button>)}</div>{newChatError && <div style={{marginTop:14,padding:11,borderRadius:12,background:'#fff1ef',color:'#a33a35',fontSize:11}}>{newChatError}</div>}</div></div></div>}
"""
    anchor = "    {showGroupCreator && <div role=\"dialog\" aria-modal=\"true\" aria-label=\"Create group chat\""
    text = once(text, anchor, modal + anchor[4:], 'modal')
    button = "<button type=\"button\" onClick={openGroupCreator} aria-label=\"New group\" title=\"Create a group chat\""
    replacement = "<button type=\"button\" onClick={openNewChat} aria-label=\"New chat\" title=\"Start a secure chat\" style={{width:34,height:34,border:0,borderRadius:10,background:'rgba(201,168,76,.16)',color:'#e4c96a',cursor:'pointer',fontSize:18}}>＋</button><button type=\"button\" onClick={openGroupCreator} aria-label=\"New group\" title=\"Create a group chat\""
    text = once(text, button, replacement, 'header button')
    TARGET.write_text(text, encoding='utf-8')
    print('Applied new secure chat picker.')

if __name__ == '__main__': main()
