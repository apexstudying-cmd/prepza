from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "frontend/src/crypto/WhatsAppChatExperience.tsx"
ADA_TARGET = ROOT / "frontend/src/crypto/inChatAdaEnhancer.tsx"

def req(text, pattern, replacement, label, regex=False):
    if regex:
        text, n = re.subn(pattern, replacement, text, count=1, flags=re.S)
        if n != 1:
            raise SystemExit("CHAT_NAV_FAILED: missing " + label)
        return text
    if pattern not in text:
        raise SystemExit("CHAT_NAV_FAILED: missing " + label)
    return text.replace(pattern, replacement, 1)

def main():
    text = TARGET.read_text(encoding="utf-8")
    text = req(text,
        "type GroupPickerUser = { id: number; display_name: string }",
        """type GroupPickerUser = { id: number; display_name: string }
type ChatSection = 'chats' | 'calls' | 'settings'
type CallHistoryEntry = { id: string; peerId: number; peerName: string; kind: 'voice' | 'video'; direction: 'incoming' | 'outgoing' | 'missed'; at: string; conversationId: number }""",
        "types")

    text = req(text,
        "const [view, setView] = useState<'list' | 'detail'>('list')",
        """const [view, setView] = useState<'list' | 'detail'>('list')
  const [section, setSection] = useState<ChatSection>('chats')
  const [infoView, setInfoView] = useState<'none' | 'media' | 'group'>('none')
  const [callHistory, setCallHistory] = useState<CallHistoryEntry[]>([])
  const [readReceipts, setReadReceipts] = useState(() => localStorage.getItem('prepza-chat-read-receipts') !== 'off')
  const [mediaVisibility, setMediaVisibility] = useState(() => localStorage.getItem('prepza-chat-media-visibility') !== 'off')""",
        "state")

    text = req(text,
        "useEffect(() => { meIdRef.current = meId }, [meId])",
        """useEffect(() => { meIdRef.current = meId }, [meId])
  useEffect(() => {
    try { const raw = localStorage.getItem('prepza-call-history'); setCallHistory(raw ? JSON.parse(raw) : []) } catch { setCallHistory([]) }
    const onHistory = (event: Event) => {
      const item = (event as CustomEvent<CallHistoryEntry>).detail
      if (!item) return
      setCallHistory(current => { const next = [item, ...current.filter(entry => entry.id !== item.id)].slice(0, 100); localStorage.setItem('prepza-call-history', JSON.stringify(next)); return next })
    }
    window.addEventListener('prepza-call-history', onHistory)
    return () => window.removeEventListener('prepza-call-history', onHistory)
  }, [])
  useEffect(() => { localStorage.setItem('prepza-chat-read-receipts', readReceipts ? 'on' : 'off') }, [readReceipts])
  useEffect(() => { localStorage.setItem('prepza-chat-media-visibility', mediaVisibility ? 'on' : 'off') }, [mediaVisibility])""",
        "effects")

    text = req(text,
        "if (!visible || view !== 'detail' || selectedId == null || !csrfToken) return",
        "if (!visible || view !== 'detail' || selectedId == null || !csrfToken || !readReceipts) return",
        "read receipt guard")

    text = req(text,
        "  const closeExperience = () => {",
        """  const closeExperience = () => {""",
        "navigation anchor")
    text = req(text,
        "  const backToList = () => { if (selectedId != null) leaveRealtimeChat(selectedId); setView('list'); setSelectedId(null); setDetail(null); setMessages([]); setReactionPicker(null); void loadList() }",
        """  const backToList = () => { if (selectedId != null) leaveRealtimeChat(selectedId); setView('list'); setInfoView('none'); setSelectedId(null); setDetail(null); setMessages([]); setReactionPicker(null); void loadList() }
  const openCalls = () => { setSection('calls'); setView('list'); setInfoView('none'); setSelectedId(null); setDetail(null); setMessages([]) }
  const openSettings = () => { setSection('settings'); setView('list'); setInfoView('none'); setSelectedId(null); setDetail(null); setMessages([]) }
  const openChatList = () => { setSection('chats'); setView('list'); setInfoView('none'); void loadList() }
  const openInfo = () => setInfoView(isGroup ? 'group' : 'media')
  const startCall = (kind: 'voice' | 'video') => {
    if (!detail || isGroup) return
    const peer = detail.participants.find(item => item.user_id !== meId)
    if (!peer) return
    const entry: CallHistoryEntry = { id: String(Date.now()), peerId: peer.user_id, peerName: peer.display_name, kind, direction: 'outgoing', at: new Date().toISOString(), conversationId: detail.id }
    window.dispatchEvent(new CustomEvent('prepza-call-history', { detail: entry }))
    window.dispatchEvent(new CustomEvent('prepza-start-call', { detail: { conversationId: detail.id, peerId: peer.user_id, peerName: peer.display_name, kind } }))
  }
  const sharedAttachments = messages.map(message => message.attachment).filter((item): item is Attachment => Boolean(item))""",
        "navigation helpers")

    # Add navigation tabs to the sidebar.
    text = req(text,
        "{showListSearch && <div className=\"prepza-wa-search\">",
        """<div style={{ display:'flex',gap:5,padding:'8px 10px',borderBottom:'1px solid #eceef1' }}>
          <button type="button" onClick={openChatList} style={{ flex:1,border:0,borderRadius:10,padding:9,fontWeight:850,background:section==='chats'?'#e9edf2':'transparent' }}>Chats</button>
          <button type="button" onClick={openCalls} style={{ flex:1,border:0,borderRadius:10,padding:9,fontWeight:850,background:section==='calls'?'#e9edf2':'transparent' }}>Calls</button>
          <button type="button" onClick={openSettings} style={{ flex:1,border:0,borderRadius:10,padding:9,fontWeight:850,background:section==='settings'?'#e9edf2':'transparent' }}>Settings</button>
        </div>
        {section === 'calls' && <div style={{ flex:1,overflowY:'auto' }}>{callHistory.length === 0 ? <div style={{ padding:45,textAlign:'center',color:'#858b96',fontSize:12 }}>No calls yet.</div> : callHistory.map(call => <div key={call.id} className="prepza-wa-row"><div style={{ width:46,height:46,borderRadius:14,background:'#0b1437',color:'#e4c96a',display:'grid',placeItems:'center',fontWeight:900 }}>{call.kind === 'video' ? 'V' : '☎'}</div><div style={{ flex:1,minWidth:0 }}><div style={{ fontWeight:800,fontSize:13 }}>{call.peerName}</div><div style={{ fontSize:10,color:'#7b8190',marginTop:3 }}>{call.direction} · {call.kind} · {listTime(call.at)}</div></div><button type="button" onClick={() => { setSection('chats'); chooseChat(call.conversationId) }} style={{ border:0,borderRadius:10,background:'#f1f2f4',padding:'8px 10px',fontWeight:800 }}>Chat</button></div>)}</div>}
        {section === 'settings' && <div style={{ flex:1,overflowY:'auto',padding:16 }}><div style={{ fontSize:11,fontWeight:900,color:'#8a909b',margin:'4px 4px 8px' }}>PRIVACY</div><div style={{ background:'#fff',border:'1px solid #e5e7eb',borderRadius:15,overflow:'hidden' }}><label style={{ display:'flex',alignItems:'center',gap:12,padding:15,borderBottom:'1px solid #eef0f2',cursor:'pointer' }}><span style={{ flex:1 }}><strong style={{ display:'block',fontSize:13 }}>Read receipts</strong><small style={{ color:'#7b8190' }}>Mark messages as read when you open a chat.</small></span><input type="checkbox" checked={readReceipts} onChange={e => setReadReceipts(e.target.checked)} /></label><label style={{ display:'flex',alignItems:'center',gap:12,padding:15,cursor:'pointer' }}><span style={{ flex:1 }}><strong style={{ display:'block',fontSize:13 }}>Media visibility</strong><small style={{ color:'#7b8190' }}>Show image previews in chats and media.</small></span><input type="checkbox" checked={mediaVisibility} onChange={e => setMediaVisibility(e.target.checked)} /></label></div></div>}
        {section === 'chats' && {showListSearch && <div className=\"prepza-wa-search\">""",
        "sidebar navigation")

    # Make header title reflect section and remove Ada control if the earlier redesign missed it.
    text = req(text,
        "<div style={{ flex:1,fontWeight:850,fontSize:18 }}>Chats</div>",
        "<div style={{ flex:1,fontWeight:850,fontSize:18 }}>{section === 'calls' ? 'Calls' : section === 'settings' ? 'Chat settings' : 'Chats'}</div>",
        "sidebar title")
    text = req(text,
        """<button type="button" onClick={openAda} aria-label="Study with Ada" style={{ border:'1px solid rgba(201,168,76,.45)',background:'rgba(201,168,76,.12)',color:'#e4c96a',borderRadius:11,padding:'8px 10px',fontWeight:900,fontSize:11,cursor:'pointer' }}>@Ada</button>""",
        "",
        "Ada header button")
    text = req(text,
        """<button type="button" onClick={openAda} style={{ height:40,border:'1px solid #dcc67d',borderRadius:12,background:'#fff9e9',color:'#72570e',padding:'0 11px',fontWeight:900,fontSize:11,cursor:'pointer' }}>@Ada</button>""",
        "",
        "Ada composer button")
    text = req(text,
        """<div className="prepza-wa-row" onClick={() => window.dispatchEvent(new CustomEvent('prepza-open-ada'))} style={{ background:'#0b1437',color:'#fff',margin:'10px 10px 6px',borderRadius:13,border:0 }}><div style={{ width:44,height:44,borderRadius:13,background:'rgba(201,168,76,.18)',display:'flex',alignItems:'center',justifyContent:'center',color:'#e4c96a',fontWeight:900 }}>A</div><div style={{ flex:1,minWidth:0 }}><div style={{ fontWeight:850,fontSize:13 }}>Ada</div><div style={{ fontSize:11,opacity:.55 }}>Your study assistant</div></div><span style={{ fontSize:10,color:'#e4c96a' }}>AI</span></div>
""",
        "",
        "Ada list row")
    # Insert header call/info controls before message search.
    text = req(text,
        """<button type="button" onClick={() => setMessageSearchOpen(v => !v)} aria-label="Search messages" """,
        """{!isGroup && <><button type="button" onClick={() => startCall('voice')} aria-label="Start voice call" style={{ width:34,height:34,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer' }}>☎</button><button type="button" onClick={() => startCall('video')} aria-label="Start video call" style={{ width:34,height:34,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer' }}>▣</button></>}
          <button type="button" onClick={openInfo} aria-label="Chat info" style={{ width:34,height:34,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer' }}>⋮</button><button type="button" onClick={() => setMessageSearchOpen(v => !v)} aria-label="Search messages" """,
        "chat header controls")

    # Media/group information is a real full-pane navigation surface.
    text = req(text,
        "{messageSearchOpen && <div style={{ background:'#fff',borderBottom:'1px solid #e1e4e8'",
        """{infoView !== 'none' && <div style={{ position:'absolute',inset:0,zIndex:20,background:'#fff',display:'flex',flexDirection:'column' }}><div style={{ minHeight:60,display:'flex',alignItems:'center',gap:10,padding:'0 12px',background:'#0b1437',color:'#fff' }}><button type="button" onClick={() => setInfoView('none')} style={{ width:34,height:34,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff' }}>‹</button><strong>{infoView === 'group' ? 'Group info' : 'Media, documents & links'}</strong></div>{infoView === 'group' ? <div style={{ padding:18,overflowY:'auto' }}><div style={{ fontSize:20,fontWeight:900 }}>{headerName}</div><div style={{ color:'#7b8190',fontSize:12,marginTop:4 }}>{detail?.member_count || 0} members</div><div style={{ marginTop:18,fontWeight:850,fontSize:12 }}>Members</div>{detail?.participants.map(member => <div key={member.user_id} style={{ display:'flex',alignItems:'center',gap:10,padding:'11px 0',borderBottom:'1px solid #eef0f2' }}><div style={{ width:38,height:38,borderRadius:12,background:'#c9a84c',display:'grid',placeItems:'center',fontWeight:900 }}>{initials(member.display_name)}</div><div style={{ flex:1,fontSize:12,fontWeight:750 }}>{member.display_name}</div><span style={{ fontSize:10,color:'#7b8190' }}>{member.role}</span></div>)}</div> : <div style={{ padding:14,overflowY:'auto',display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(150px,1fr))',gap:10 }}>{sharedAttachments.length === 0 ? <div style={{ gridColumn:'1/-1',padding:40,textAlign:'center',color:'#858b96',fontSize:12 }}>No shared media or documents.</div> : sharedAttachments.map(file => <a key={file.id} href={file.view_url || undefined} target="_blank" rel="noreferrer" style={{ textDecoration:'none',color:'#202534',border:'1px solid #e5e7eb',borderRadius:12,padding:10 }}>{mediaVisibility && isImage(file.file_type) && file.view_url ? <img src={file.view_url} alt={file.original_filename} style={{ width:'100%',height:110,objectFit:'cover',borderRadius:8 }} /> : <div style={{ height:110,display:'grid',placeItems:'center',background:'#f3f4f6',borderRadius:8,fontWeight:900 }}>FILE</div>}<div style={{ marginTop:7,fontSize:11,fontWeight:800,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap' }}>{file.original_filename}</div></a>)}</div>}</div>}
          {messageSearchOpen && <div style={{ background:'#fff',borderBottom:'1px solid #e1e4e8'""",
        "info surface")

    text = req(text,
        "{message.attachment.view_url && isImage(message.attachment.file_type) ? <img",
        "{mediaVisibility && message.attachment.view_url && isImage(message.attachment.file_type) ? <img",
        "media preview guard")
    text = req(text,
        'placeholder="Message…" disabled={sending || uploading} rows={1}',
        'placeholder="Message…" data-prepza-chat-composer="true" disabled={sending || uploading} rows={1}',
        "Ada textarea marker")
    TARGET.write_text(text, encoding="utf-8")

    ada = ADA_TARGET.read_text(encoding="utf-8")
    ada = req(ada, 'document.querySelector(\\'input[placeholder="Message…"]\\') as HTMLInputElement | null',
              'document.querySelector(\\'[data-prepza-chat-composer="true"]\\') as HTMLTextAreaElement | null',
              "Ada textarea selector")
    ADA_TARGET.write_text(ada, encoding="utf-8")
    print("CHAT_NAVIGATION_APPLIED")
    print("CALLS_SECTION_READY")
    print("CHAT_SETTINGS_READY")
    print("MEDIA_AND_GROUP_INFO_READY")
    print("ADA_MENTION_ONLY_READY")

if __name__ == "__main__":
    main()
