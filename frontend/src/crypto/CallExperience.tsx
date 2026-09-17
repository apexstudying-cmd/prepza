import { useEffect, useRef, useState } from 'react'
import { emitCall, installCallRealtime, onCallSignal, type CallSignal } from './callRealtime'

type Props = { userId: number | null; displayName?: string }
type ActiveCall = { callId: string; conversationId: number; peerId: number; peerName: string; kind: 'voice' | 'video'; incoming: boolean; connected: boolean }

const ICE_SERVERS: RTCIceServer[] = (() => {
  const raw = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env?.VITE_WEBRTC_ICE_SERVERS
  if (!raw) return []
  try { const parsed = JSON.parse(raw); return Array.isArray(parsed) ? parsed : [] } catch { return [] }
})()

function randomCallId() { return `${Date.now().toString(36)}-${crypto.randomUUID()}` }

export default function CallExperience({ userId }: Props) {
  const [incoming, setIncoming] = useState<CallSignal | null>(null)
  const [call, setCall] = useState<ActiveCall | null>(null)
  const [muted, setMuted] = useState(false)
  const [cameraOff, setCameraOff] = useState(false)
  const localVideo = useRef<HTMLVideoElement>(null)
  const remoteVideo = useRef<HTMLVideoElement>(null)
  const peer = useRef<RTCPeerConnection | null>(null)
  const localStream = useRef<MediaStream | null>(null)
  const pendingIce = useRef<RTCIceCandidateInit[]>([])

  useEffect(() => {
    if (!userId) return
    installCallRealtime()
    return onCallSignal(event => {
      if (event.to_user_id !== userId) return
      if (event.type === 'call:incoming') { setIncoming(event); return }
      if (event.type === 'call:rejected' || event.type === 'call:ended') cleanup(false)
      if (event.type === 'call:offer' && event.payload) void acceptOffer(event)
      if (event.type === 'call:answer' && event.payload && peer.current) void peer.current.setRemoteDescription(event.payload as RTCSessionDescriptionInit)
      if (event.type === 'call:ice' && event.payload) void addIce(event.payload as RTCIceCandidateInit)
      if (event.type === 'call:accepted' && call) setCall({ ...call, connected: true })
    })
  }, [userId])

  useEffect(() => () => cleanup(false), [])

  async function ensureMedia(kind: 'voice' | 'video') {
    if (localStream.current) return localStream.current
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: kind === 'video' })
    localStream.current = stream
    if (localVideo.current) { localVideo.current.srcObject = stream; localVideo.current.muted = true }
    return stream
  }

  function createPeer(callInfo: ActiveCall) {
    const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS })
    pc.onicecandidate = event => { if (event.candidate) emitCall('call:ice', { call_id: callInfo.callId, to_user_id: callInfo.peerId, payload: event.candidate.toJSON() }) }
    pc.ontrack = event => { if (remoteVideo.current && event.streams[0]) remoteVideo.current.srcObject = event.streams[0] }
    pc.onconnectionstatechange = () => { if (['failed', 'closed', 'disconnected'].includes(pc.connectionState)) cleanup(true); else if (pc.connectionState === 'connected') setCall(current => current ? { ...current, connected: true } : current) }
    peer.current = pc
    return pc
  }

  async function startCall(conversationId: number, peerId: number, peerName: string, kind: 'voice' | 'video') {
    if (call || !userId) return
    const callId = randomCallId()
    const active = { callId, conversationId, peerId, peerName, kind, incoming: false, connected: false } as ActiveCall
    try {
      const stream = await ensureMedia(kind)
      const pc = createPeer(active)
      stream.getTracks().forEach(track => pc.addTrack(track, stream))
      setCall(active)
      emitCall('call:invite', { call_id: callId, conversation_id: conversationId, to_user_id: peerId, kind })
    } catch { cleanup(false); window.dispatchEvent(new CustomEvent('prepza-call-error', { detail: 'Microphone or camera permission is required for calls.' })) }
  }

  async function acceptIncoming() {
    if (!incoming || !userId) return
    const event = incoming
    const active = { callId: event.call_id, conversationId: event.conversation_id, peerId: event.from_user_id, peerName: event.from_name || 'Student', kind: event.kind, incoming: true, connected: false } as ActiveCall
    try {
      await ensureMedia(event.kind)
      createPeer(active)
      setCall(active); setIncoming(null)
      emitCall('call:accept', { call_id: event.call_id, conversation_id: event.conversation_id, to_user_id: event.from_user_id })
    } catch { emitCall('call:reject', { call_id: event.call_id, to_user_id: event.from_user_id }); setIncoming(null) }
  }

  async function acceptOffer(event: CallSignal) {
    if (!peer.current || !call) return
    await peer.current.setRemoteDescription(event.payload as RTCSessionDescriptionInit)
    for (const candidate of pendingIce.current.splice(0)) await peer.current.addIceCandidate(candidate)
    const answer = await peer.current.createAnswer(); await peer.current.setLocalDescription(answer)
    emitCall('call:answer', { call_id: event.call_id, conversation_id: event.conversation_id, to_user_id: event.from_user_id, payload: answer })
  }

  async function addIce(candidate: RTCIceCandidateInit) {
    if (!peer.current || !peer.current.remoteDescription) { pendingIce.current.push(candidate); return }
    try { await peer.current.addIceCandidate(candidate) } catch { /* stale ICE candidate */ }
  }

  function cleanup(notify: boolean) {
    const current = call
    if (notify && current) emitCall('call:end', { call_id: current.callId, conversation_id: current.conversationId, to_user_id: current.peerId })
    peer.current?.close(); peer.current = null
    localStream.current?.getTracks().forEach(track => track.stop()); localStream.current = null
    if (localVideo.current) localVideo.current.srcObject = null
    if (remoteVideo.current) remoteVideo.current.srcObject = null
    setCall(null); setIncoming(null); setMuted(false); setCameraOff(false); pendingIce.current = []
  }

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ conversationId: number; peerId: number; peerName: string; kind: 'voice' | 'video' }>).detail
      if (detail) void startCall(detail.conversationId, detail.peerId, detail.peerName, detail.kind)
    }
    window.addEventListener('prepza-start-call', handler)
    return () => window.removeEventListener('prepza-start-call', handler)
  })

  if (!incoming && !call) return null
  return <>
    {incoming && !call && <div style={{ position:'fixed', inset:0, zIndex:3000, background:'rgba(4,8,20,.86)', display:'flex', alignItems:'center', justifyContent:'center', padding:20, color:'#fff' }}>
      <div style={{ width:'min(360px,100%)', textAlign:'center' }}>
        <div style={{ width:92,height:92,borderRadius:'50%',margin:'0 auto 18px',background:'#c9a84c',color:'#0b1437',display:'grid',placeItems:'center',fontSize:34,fontWeight:900 }}>{(incoming.from_name || 'S').slice(0,1).toUpperCase()}</div>
        <div style={{ fontSize:24,fontWeight:850 }}>{incoming.from_name || 'Student'}</div><div style={{ marginTop:7,opacity:.7 }}>{incoming.kind === 'video' ? 'Incoming video call' : 'Incoming voice call'}</div>
        <div style={{ display:'flex',justifyContent:'center',gap:34,marginTop:42 }}><button onClick={() => { emitCall('call:reject',{ call_id:incoming.call_id,to_user_id:incoming.from_user_id });setIncoming(null) }} aria-label="Decline call" style={{ width:62,height:62,border:0,borderRadius:'50%',background:'#d84b4b',color:'#fff',fontSize:25 }}>×</button><button onClick={() => void acceptIncoming()} aria-label="Accept call" style={{ width:62,height:62,border:0,borderRadius:'50%',background:'#2fa866',color:'#fff',fontSize:25 }}>✓</button></div>
      </div>
    </div>}
    {call && <div style={{ position:'fixed', inset:0, zIndex:2900, background:'#090c14', color:'#fff', display:'flex', flexDirection:'column' }}>
      {call.kind === 'video' && <><video ref={remoteVideo} autoPlay playsInline style={{ position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'cover',background:'#111' }} /><video ref={localVideo} autoPlay playsInline muted style={{ position:'absolute',right:18,top:18,width:'28%',maxWidth:220,aspectRatio:'3/4',objectFit:'cover',borderRadius:18,background:'#222',boxShadow:'0 8px 30px rgba(0,0,0,.35)' }} /></>}
      {call.kind === 'voice' && <div style={{ flex:1,display:'grid',placeItems:'center' }}><div style={{ textAlign:'center' }}><div style={{ width:110,height:110,borderRadius:'50%',background:'#c9a84c',color:'#0b1437',display:'grid',placeItems:'center',fontSize:42,fontWeight:900,margin:'0 auto 18px' }}>{call.peerName.slice(0,1).toUpperCase()}</div><div style={{fontSize:25,fontWeight:850}}>{call.peerName}</div><div style={{marginTop:8,opacity:.65}}>{call.connected ? 'Connected' : 'Calling…'}</div></div></div>}
      <div style={{ position:'absolute',left:0,right:0,bottom:0,padding:'28px 22px 34px',display:'flex',justifyContent:'center',gap:14,background:'linear-gradient(transparent,rgba(0,0,0,.65))' }}>
        <button onClick={() => { const tracks = localStream.current?.getAudioTracks() || []; tracks.forEach(track => { track.enabled = !track.enabled }); setMuted(tracks[0] ? !tracks[0].enabled : false) }} aria-label="Mute microphone" style={{width:52,height:52,border:0,borderRadius:'50%',background:muted?'#fff':'rgba(255,255,255,.18)',color:muted?'#111':'#fff',fontSize:20}}>⌁</button>
        {call.kind === 'video' && <button onClick={() => { const tracks = localStream.current?.getVideoTracks() || []; tracks.forEach(track => { track.enabled = !track.enabled }); setCameraOff(tracks[0] ? !tracks[0].enabled : false) }} aria-label="Turn camera off" style={{width:52,height:52,border:0,borderRadius:'50%',background:cameraOff?'#fff':'rgba(255,255,255,.18)',color:cameraOff?'#111':'#fff',fontSize:20}}>◉</button>}
        <button onClick={() => cleanup(true)} aria-label="End call" style={{width:58,height:58,border:0,borderRadius:'50%',background:'#d84b4b',color:'#fff',fontSize:23}}>×</button>
      </div>
    </div>}
  </>
}

export { type Props as CallExperienceProps }
