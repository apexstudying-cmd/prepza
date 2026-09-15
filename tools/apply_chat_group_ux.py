"""Build-time patch for first-class WhatsApp-style study chat groups.

This intentionally extends the existing WhatsAppChatExperience instead of
creating a second group/community chat surface. Groups use the existing
/chats conversation API, the same message timeline, realtime layer and E2EE
key machinery; the only structural difference is multiple participant IDs.
"""
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "frontend" / "src" / "crypto" / "WhatsAppChatExperience.tsx"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Chat group UX patch anchor missing: {label}")
    if text.count(old) != 1:
        raise RuntimeError(f"Chat group UX patch anchor is not unique: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "import { joinRealtimeChat, leaveRealtimeChat, sendReadRealtime, sendTypingRealtime } from './chatRealtime'\n",
        "import { joinRealtimeChat, leaveRealtimeChat, sendReadRealtime, sendTypingRealtime } from './chatRealtime'\nimport { ensureE2EEIdentityReady, fetchUserPublicKey, uploadGroupKeyEnvelopes } from './e2eeChatApi'\nimport { provisionInitialGroupKey } from './groupProvisioning'\n",
        "imports",
    )

    text = replace_once(
        text,
        "type ReactionState = Record<number, Record<string, Set<number>>>\n",
        "type ReactionState = Record<number, Record<string, Set<number>>>\ntype GroupPickerUser = { id: number; display_name: string }\n",
        "group picker type",
    )

    text = replace_once(
        text,
        "  const [showListSearch, setShowListSearch] = useState(false)\n",
        "  const [showListSearch, setShowListSearch] = useState(false)\n  const [showGroupCreator, setShowGroupCreator] = useState(false)\n  const [groupName, setGroupName] = useState('')\n  const [groupSearch, setGroupSearch] = useState('')\n  const [groupUsers, setGroupUsers] = useState<GroupPickerUser[]>([])\n  const [groupSelected, setGroupSelected] = useState<GroupPickerUser[]>([])\n  const [groupCreating, setGroupCreating] = useState(false)\n  const [groupError, setGroupError] = useState('')\n",
        "group creator state",
    )

    text = replace_once(
        text,
        "  const send = async () => {\n",
        """  useEffect(() => {
    if (!showGroupCreator) return
    const needle = groupSearch.trim()
    if (needle.length < 2) { setGroupUsers([]); return }
    let cancelled = false
    const timer = window.setTimeout(() => {
      fetch(`/users/search?q=${encodeURIComponent(needle)}`, { credentials: 'include' })
        .then(async response => {
          const body = await response.json().catch(() => ({}))
          if (!response.ok) throw new Error(body?.error || 'Could not search students')
          return body
        })
        .then(body => { if (!cancelled) setGroupUsers(Array.isArray(body?.users) ? body.users : Array.isArray(body?.results) ? body.results : []) })
        .catch(() => { if (!cancelled) setGroupUsers([]) })
    }, 220)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [showGroupCreator, groupSearch])

  const openGroupCreator = () => {
    setGroupName('')
    setGroupSearch('')
    setGroupUsers([])
    setGroupSelected([])
    setGroupError('')
    setShowGroupCreator(true)
  }

  const toggleGroupUser = (user: GroupPickerUser) => {
    setGroupSelected(current => current.some(item => item.id === user.id)
      ? current.filter(item => item.id !== user.id)
      : current.length >= 99 ? current : [...current, user])
  }

  const createChatGroup = async () => {
    const name = groupName.trim()
    if (!name) { setGroupError('Give the group a name.'); return }
    if (groupSelected.length < 2) { setGroupError('Select at least 2 other students for a group chat.'); return }
    if (groupCreating) return

    setGroupCreating(true)
    setGroupError('')
    try {
      const token = await getCsrfToken()
      await ensureE2EEIdentityReady()
      if (!meIdRef.current) throw new Error('Your secure chat identity is unavailable')

      const creatorId = meIdRef.current
      const memberIds = [creatorId, ...groupSelected.map(user => user.id)]
      const memberKeys = await Promise.all(memberIds.map(async id => ({ userId: id, publicKey: await fetchUserPublicKey(id) })))

      const created = await api<{ id: number }>(`/chats`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': token },
        body: JSON.stringify({ is_group: true, participant_ids: groupSelected.map(user => user.id), name }),
      })
      if (!created?.id) throw new Error('The group could not be created')

      await provisionInitialGroupKey(
        created.id,
        1,
        creatorId,
        memberKeys,
        (conversationId, envelopes) => uploadGroupKeyEnvelopes(conversationId, token, envelopes),
      )

      setShowGroupCreator(false)
      await loadList()
      chooseChat(created.id)
    } catch (value) {
      setGroupError(friendlyError(value, 'Could not create this group. Make sure everyone has secure chat enabled and try again.'))
    } finally {
      setGroupCreating(false)
    }
  }

  const send = async () => {
""",
        "group creation logic",
    )

    text = replace_once(
        text,
        "<button type=\"button\" onClick={closeExperience} aria-label=\"New chat\" title=\"Close this view to start a new chat\" style={{ width:34,height:34,border:0,borderRadius:10,background:'rgba(201,168,76,.16)',color:'#e4c96a',cursor:'pointer',fontSize:20 }}>+</button>",
        "<button type=\"button\" onClick={openGroupCreator} aria-label=\"New group\" title=\"Create a group chat\" style={{ width:34,height:34,border:0,borderRadius:10,background:'rgba(201,168,76,.16)',color:'#e4c96a',cursor:'pointer',fontSize:20 }}>+</button>",
        "new group button",
    )

    marker = "</style>\n    <div className={`prepza-wa-window ${view === 'detail' ? 'detail-mode' : 'list-mode'}`}>"
    modal = """</style>
    {showGroupCreator && <div role=\"dialog\" aria-modal=\"true\" aria-label=\"Create group chat\" style={{ position:'fixed',inset:0,zIndex:1100,background:'rgba(3,7,18,.72)',backdropFilter:'blur(8px)',display:'flex',alignItems:'center',justifyContent:'center',padding:16 }}>
      <div style={{ width:'min(520px,100%)',maxHeight:'min(760px,92vh)',display:'flex',flexDirection:'column',background:'#fff',borderRadius:22,overflow:'hidden',boxShadow:'0 24px 70px rgba(0,0,0,.35)' }}>
        <div style={{ background:'#0b1437',color:'#fff',padding:'18px 18px 16px',display:'flex',alignItems:'center',gap:12 }}>
          <button type=\"button\" onClick={() => setShowGroupCreator(false)} disabled={groupCreating} aria-label=\"Close group creator\" style={{ width:36,height:36,border:0,borderRadius:11,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer',fontSize:22 }}>‹</button>
          <div style={{ flex:1 }}><div style={{ fontSize:17,fontWeight:850 }}>New study group</div><div style={{ marginTop:3,fontSize:11,opacity:.62 }}>The same Prepza chat, with multiple students.</div></div>
        </div>
        <div style={{ padding:18,overflowY:'auto',flex:1 }}>
          <label style={{ display:'block',fontSize:11,fontWeight:800,color:'#606672',marginBottom:7 }}>GROUP NAME</label>
          <input value={groupName} onChange={event => setGroupName(event.target.value)} maxLength={100} placeholder=\"e.g. Actuarial CAT revision\" autoFocus style={{ width:'100%',boxSizing:'border-box',height:46,border:'1px solid #dfe3e8',borderRadius:12,padding:'0 13px',outline:'none',font:'inherit',fontSize:13 }} />
          <div style={{ marginTop:18,display:'flex',gap:8,alignItems:'center' }}>
            <input value={groupSearch} onChange={event => setGroupSearch(event.target.value)} placeholder=\"Search students by name\" style={{ flex:1,height:42,border:'1px solid #dfe3e8',borderRadius:12,padding:'0 12px',outline:'none',font:'inherit',fontSize:12 }} />
          </div>
          {groupSelected.length > 0 && <div style={{ display:'flex',gap:7,flexWrap:'wrap',marginTop:12 }}>{groupSelected.map(user => <button key={user.id} type=\"button\" onClick={() => toggleGroupUser(user)} style={{ border:0,borderRadius:99,background:'#0b1437',color:'#fff',padding:'7px 10px',fontSize:11,cursor:'pointer' }}>{user.display_name} ×</button>)}</div>}
          <div style={{ marginTop:12 }}>
            {groupSearch.trim().length < 2 && <div style={{ padding:'24px 10px',textAlign:'center',color:'#8b919b',fontSize:12 }}>Search for classmates to add.</div>}
            {groupSearch.trim().length >= 2 && !groupUsers.length && <div style={{ padding:'24px 10px',textAlign:'center',color:'#8b919b',fontSize:12 }}>No students found.</div>}
            {groupUsers.map(user => { const selected = groupSelected.some(item => item.id === user.id); return <button key={user.id} type=\"button\" onClick={() => toggleGroupUser(user)} style={{ width:'100%',display:'flex',alignItems:'center',gap:11,border:0,borderBottom:'1px solid #f0f1f3',background:selected ? '#f5f2e8' : '#fff',padding:'11px 4px',textAlign:'left',cursor:'pointer' }}><span style={{ width:40,height:40,borderRadius:13,background:'linear-gradient(135deg,#c9a84c,#e4c96a)',color:'#0b1437',display:'flex',alignItems:'center',justifyContent:'center',fontWeight:900 }}>{initials(user.display_name)}</span><span style={{ flex:1,fontSize:13,fontWeight:750,color:'#20242b' }}>{user.display_name}</span><span style={{ width:22,height:22,borderRadius:'50%',border:selected ? '0' : '1px solid #cfd4da',background:selected ? '#0b1437' : '#fff',color:'#e4c96a',display:'flex',alignItems:'center',justifyContent:'center',fontSize:13 }}>{selected ? '✓' : ''}</span></button> })}
          </div>
          {groupError && <div style={{ marginTop:14,padding:11,borderRadius:12,background:'#fff1ef',color:'#a33a35',fontSize:11 }}>{groupError}</div>}
        </div>
        <div style={{ padding:'12px 18px 16px',borderTop:'1px solid #eceef1',display:'flex',gap:9 }}>
          <button type=\"button\" onClick={() => setShowGroupCreator(false)} disabled={groupCreating} style={{ flex:1,height:44,border:'1px solid #dfe3e8',background:'#fff',borderRadius:12,fontWeight:800,cursor:'pointer' }}>Cancel</button>
          <button type=\"button\" onClick={() => void createChatGroup()} disabled={groupCreating || groupSelected.length < 2 || !groupName.trim()} style={{ flex:1,height:44,border:0,background:'#0b1437',color:'#e4c96a',borderRadius:12,fontWeight:850,cursor:'pointer',opacity:(groupCreating || groupSelected.length < 2 || !groupName.trim()) ? .5 : 1 }}>{groupCreating ? 'Creating…' : `Create group${groupSelected.length ? ` · ${groupSelected.length + 1}` : ''}`}</button>
        </div>
      </div>
    </div>}
    <div className={`prepza-wa-window ${view === 'detail' ? 'detail-mode' : 'list-mode'}`}>"""
    text = replace_once(text, marker, modal, "group creator modal insertion")

    TARGET.write_text(text, encoding="utf-8")
    print("Applied WhatsApp-style multi-user group creation UX patch.")


if __name__ == "__main__":
    main()
