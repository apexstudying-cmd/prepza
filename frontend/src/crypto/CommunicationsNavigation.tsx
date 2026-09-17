import { useEffect, useState } from 'react'

type Attachment = { id: number; file_type: string; original_filename: string; file_size_bytes: number; view_url: string | null }
type Participant = { user_id: number; display_name: string; role: string }
type Detail = { id: number; is_group: boolean; name: string; created_by: number; member_count: number; participants: Participant[] }

type Props = { conversationId: number | null; detail: Detail | null; messages: Array<{ attachment: Attachment | null }>; onOpenChat: (id: number) => void }

type CallItem = { id: string; peerId: number; peerName: string; kind: 'voice' | 'video'; direction: 'incoming' | 'outgoing' | 'missed'; at: string; conversationId: number }

export default function CommunicationsNavigation({ conversationId, detail, messages, onOpenChat }: Props) {
  const [screen, setScreen] = useState<'none' | 'calls' | 'settings' | 'info'>('none')
  const [readReceipts, setReadReceipts] = useState(() => localStorage.getItem('prepza-chat-read-receipts') !== 'off')
  const [mediaVisibility, setMediaVisibility] = useState(() => localStorage.getItem('prepza-chat-media-visibility') !== 'off')
  const [calls, setCalls] = useState<CallItem[]>([])

  useEffect(() => {
    try { const raw = localStorage.getItem('prepza-call-history'); if (raw) setCalls(JSON.parse(raw)) } catch { setCalls([]) }
    const history = (event: Event) => {
      const item = (event as CustomEvent<CallItem>).detail
      if (!item) return
      setCalls(current => { const next = [item, ...current.filter(value => value.id !== item.id)].slice(0, 100); localStorage.setItem('prepza-call-history', JSON.stringify(next)); return next })
    }
    const openCalls = () => setScreen('calls')
    const openSettings = () => setScreen('settings')
    const openInfo = () => setScreen('info')
    window.addEventListener('prepza-call-history', history)
    window.addEventListener('prepza-open-calls', openCalls)
    window.addEventListener('prepza-open-chat-settings', openSettings)
    window.addEventListener('prepza-open-chat-info', openInfo)
    return () => {
      window.removeEventListener('prepza-call-history', history)
      window.removeEventListener('prepza-open-calls', openCalls)
      window.removeEventListener('prepza-open-chat-settings', openSettings)
      window.removeEventListener('prepza-open-chat-info', openInfo)
    }
  }, [])

  useEffect(() => { localStorage.setItem('prepza-chat-read-receipts', readReceipts ? 'on' : 'off') }, [readReceipts])
  useEffect(() => { localStorage.setItem('prepza-chat-media-visibility', mediaVisibility ? 'on' : 'off') }, [mediaVisibility])

  if (screen === 'none') return null

  const attachments = messages.map(value => value.attachment).filter((value): value is Attachment => Boolean(value))

  return <div style={{ position: 'absolute', inset: 0, zIndex: 40, background: '#fff', display: 'flex', flexDirection: 'column' }}>
    <div style={{ minHeight: 62, display: 'flex', alignItems: 'center', gap: 10, padding: '0 12px', background: '#0b1437', color: '#fff' }}>
      <button type="button" onClick={() => setScreen('none')} aria-label="Back" style={{ width: 36, height: 36, border: 0, borderRadius: 10, background: 'rgba(255,255,255,.1)', color: '#fff', fontSize: 20 }}>Back</button>
      <strong>{screen === 'calls' ? 'Calls' : screen === 'settings' ? 'Chat settings' : detail?.is_group ? 'Group info' : 'Media, documents and links'}</strong>
    </div>

    {screen === 'calls' && <div style={{ flex: 1, overflowY: 'auto' }}>
      {calls.length === 0 ? <div style={{ padding: 50, textAlign: 'center', color: '#858b96', fontSize: 12 }}>No calls yet.</div> : calls.map(call => <div key={call.id} style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '12px 14px', borderBottom: '1px solid #eef0f2' }}>
        <div style={{ width: 44, height: 44, borderRadius: 13, background: '#0b1437', color: '#e4c96a', display: 'grid', placeItems: 'center', fontWeight: 900 }}>{call.kind === 'video' ? 'V' : 'C'}</div>
        <div style={{ flex: 1, minWidth: 0 }}><div style={{ fontSize: 13, fontWeight: 800 }}>{call.peerName}</div><div style={{ marginTop: 3, fontSize: 10, color: '#7b8190' }}>{call.direction} - {call.kind} - {new Date(call.at).toLocaleString()}</div></div>
        <button type="button" onClick={() => { setScreen('none'); onOpenChat(call.conversationId) }} style={{ border: 0, borderRadius: 10, background: '#f1f2f4', padding: '8px 10px', fontWeight: 800 }}>Chat</button>
      </div>)}
    </div>}

    {screen === 'settings' && <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 900, color: '#8a909b', marginBottom: 8 }}>PRIVACY</div>
      <div style={{ border: '1px solid #e5e7eb', borderRadius: 15, overflow: 'hidden' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 15, borderBottom: '1px solid #eef0f2' }}><span style={{ flex: 1 }}><strong style={{ display: 'block', fontSize: 13 }}>Read receipts</strong><small style={{ color: '#7b8190' }}>Send read confirmations when chats are opened.</small></span><input type="checkbox" checked={readReceipts} onChange={event => setReadReceipts(event.target.checked)} /></label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 15 }}><span style={{ flex: 1 }}><strong style={{ display: 'block', fontSize: 13 }}>Media visibility</strong><small style={{ color: '#7b8190' }}>Show image previews in conversations.</small></span><input type="checkbox" checked={mediaVisibility} onChange={event => setMediaVisibility(event.target.checked)} /></label>
      </div>
    </div>}

    {screen === 'info' && <div style={{ flex: 1, overflowY: 'auto' }}>
      {detail?.is_group ? <div style={{ padding: 18 }}><div style={{ fontSize: 20, fontWeight: 900 }}>{detail.name}</div><div style={{ marginTop: 4, color: '#7b8190', fontSize: 12 }}>{detail.member_count} members</div><div style={{ marginTop: 18, fontSize: 12, fontWeight: 850 }}>Members</div>{detail.participants.map(member => <div key={member.user_id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '11px 0', borderBottom: '1px solid #eef0f2' }}><div style={{ width: 38, height: 38, borderRadius: 12, background: '#c9a84c', color: '#0b1437', display: 'grid', placeItems: 'center', fontWeight: 900 }}>{member.display_name.slice(0, 1).toUpperCase()}</div><div style={{ flex: 1, fontSize: 12, fontWeight: 750 }}>{member.display_name}</div><span style={{ fontSize: 10, color: '#7b8190' }}>{member.role}</span></div>)}</div> : <div style={{ padding: 14, display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(150px,1fr))', gap: 10 }}>{attachments.length === 0 ? <div style={{ padding: 40, textAlign: 'center', color: '#858b96', fontSize: 12 }}>No shared media or documents.</div> : attachments.map(file => <a key={file.id} href={file.view_url || undefined} target="_blank" rel="noreferrer" style={{ textDecoration: 'none', color: '#202534', border: '1px solid #e5e7eb', borderRadius: 12, padding: 10 }}>{mediaVisibility && /^image\//i.test(file.file_type) && file.view_url ? <img src={file.view_url} alt={file.original_filename} style={{ width: '100%', height: 110, objectFit: 'cover', borderRadius: 8 }} /> : <div style={{ height: 110, display: 'grid', placeItems: 'center', background: '#f3f4f6', borderRadius: 8, fontWeight: 900 }}>FILE</div>}<div style={{ marginTop: 7, fontSize: 11, fontWeight: 800 }}>{file.original_filename}</div></a>)}</div>}
    </div>}
  </div>
}
