import { useEffect, useRef, useState } from 'react'
import { emitCall, installCallRealtime, onCallSignal, type CallSignal } from './callRealtime'

type Props = { userId: number | null; displayName?: string }
type ActiveCall = { callId: string; conversationId: number; peerId: number; peerName: string; kind: 'voice' | 'video'; incoming: boolean; connected: boolean }
type CallOutcome = 'unavailable' | 'no-answer' | 'ended' | null

const ICE_SERVERS: RTCIceServer[] = (() => {
  const raw = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env?.VITE_WEBRTC_ICE_SERVERS
  if (raw) {
    try { const parsed = JSON.parse(raw); if (Array.isArray(parsed) && parsed.length) return parsed } catch { /* use safe default */ }
  }
  return [{ urls: 'stun:stun.l.google.com:19302' }]
})()

function randomCallId() { return `${Date.now().toString(36)}-${crypto.randomUUID()}` }

export default function CallExperience({ userId }: Props) {
  const [resolvedUserId, setResolvedUserId] = useState<number | null>(userId)
  const [incoming, setIncoming] = useState<CallSignal | null>(null)
  const [call, setCall] = useState<ActiveCall | null>(null)
  const [outcome, setOutcome] = useState<CallOutcome>(null)
  const [muted, setMuted] = useState(false)
  const [cameraOff, setCameraOff] = useState(false)
  const [connectedAt, setConnectedAt] = useState<number | null>(null)
  const [callSeconds, setCallSeconds] = useState(0)
  const localVideo = useRef<HTMLVideoElement>(null)
  const remoteVideo = useRef<HTMLVideoElement>(null)
  const remoteAudio = useRef<HTMLAudioElement>(null)
  const peer = useRef<RTCPeerConnection | null>(null)
  const localStream = useRef<MediaStream | null>(null)
  const pendingIce = useRef<RTCIceCandidateInit[]>([])
  const callRef = useRef<ActiveCall | null>(null)
  const incomingRef = useRef<CallSignal | null>(null)
  const callTimeoutRef = useRef<number | null>(null)
  const incomingTimeoutRef = useRef<number | null>(null)

  useEffect(() => { callRef.current = call }, [call])
  useEffect(() => {
    if (userId != null) { setResolvedUserId(userId); return }
    let cancelled = false
    fetch('/me', { credentials: 'include' })
      .then(response => response.ok ? response.json() : null)
      .then(payload => {
        const id = payload?.id ?? payload?.user?.id
        if (!cancelled && Number.isInteger(id)) setResolvedUserId(Number(id))
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [userId])
  useEffect(() => {
    if (!connectedAt) { setCallSeconds(0); return }
    const tick = () => setCallSeconds(Math.max(0, Math.floor((Date.now() - connectedAt) / 1000)))
    tick()
    const timer = window.setInterval(tick, 1000)
    return () => window.clearInterval(timer)
  }, [connectedAt])

  useEffect(() => { incomingRef.current = incoming }, [incoming])

  useEffect(() => {
    if (!resolvedUserId) return
    installCallRealtime()
    const unsubscribe = onCallSignal(event => {
      if (event.to_user_id !== resolvedUserId) return
      if (event.type === 'call:incoming') {
        if (callRef.current) return
        setOutcome(null)
        setIncoming(event)
        if (incomingTimeoutRef.current) window.clearTimeout(incomingTimeoutRef.current)
        incomingTimeoutRef.current = window.setTimeout(() => {
          const current = incomingRef.current
          if (current) emitCall('call:reject', { call_id: current.call_id, to_user_id: current.from_user_id })
          setIncoming(null)
        }, 30000)
        return
      }
      if (event.type === 'call:rejected' || event.type === 'call:ended') { cleanup(false); return }
      if (event.type === 'call:accepted') { void createAndSendOffer(event); return }
      if (event.type === 'call:offer' && event.payload) { void acceptOffer(event); return }
      if (event.type === 'call:answer' && event.payload && peer.current) { void (async () => { await peer.current!.setRemoteDescription(event.payload as RTCSessionDescriptionInit); for (const candidate of pendingIce.current.splice(0)) await peer.current!.addIceCandidate(candidate) })(); return }
      if (event.type === 'call:ice' && event.payload) { void addIce(event.payload as RTCIceCandidateInit) }
    })
    return () => { unsubscribe() }
  }, [resolvedUserId])

  useEffect(() => () => cleanup(false), [])
  useEffect(() => () => {
    if (callTimeoutRef.current) window.clearTimeout(callTimeoutRef.current)
    if (incomingTimeoutRef.current) window.clearTimeout(incomingTimeoutRef.current)
  }, [])

  async function ensureMedia(kind: 'voice' | 'video') {
    if (localStream.current) return localStream.current
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: kind === 'video' })
    localStream.current = stream
    if (localVideo.current) { localVideo.current.srcObject = stream; localVideo.current.muted = true }
    return stream
  }

  function createPeer(callInfo: ActiveCall) {
    const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS })
    pc.onicecandidate = event => {
      if (event.candidate) emitCall('call:ice', { call_id: callInfo.callId, to_user_id: callInfo.peerId, payload: event.candidate.toJSON() })
    }
    pc.ontrack = event => {
      if (remoteVideo.current && event.streams[0]) remoteVideo.current.srcObject = event.streams[0]
      if (remoteAudio.current && event.streams[0]) { remoteAudio.current.srcObject = event.streams[0]; void remoteAudio.current.play().catch(() => {}) }
    }
    pc.onconnectionstatechange = () => {
      if (['failed', 'closed', 'disconnected'].includes(pc.connectionState)) cleanup(true)
      else if (pc.connectionState === 'connected') { setCall(current => current ? { ...current, connected: true } : current); setConnectedAt(value => value || Date.now()) }
    }
    peer.current = pc
    return pc
  }

  async function startCall(conversationId: number, peerId: number, peerName: string, kind: 'voice' | 'video') {
    if (callRef.current || !resolvedUserId) return
    if (!navigator.onLine) { window.dispatchEvent(new CustomEvent('prepza-call-error', { detail: 'Calls require an internet connection.' })); return }
    const callId = randomCallId()
    const active = { callId, conversationId, peerId, peerName, kind, incoming: false, connected: false } as ActiveCall
    try {
      const stream = await ensureMedia(kind)
      const pc = createPeer(active)
      stream.getTracks().forEach(track => pc.addTrack(track, stream))
      callRef.current = active
      setCall(active)
      const result = await emitCall('call:invite', { call_id: callId, conversation_id: conversationId, to_user_id: peerId, kind })
      if (result.ok !== true) {
        setOutcome(result.error === 'User unavailable' ? 'unavailable' : 'no-answer')
        cleanup(false)
        window.setTimeout(() => setOutcome(null), 2200)
        return
      }
      if (callTimeoutRef.current) window.clearTimeout(callTimeoutRef.current)
      callTimeoutRef.current = window.setTimeout(() => {
        if (callRef.current?.callId !== callId || callRef.current?.connected) return
        emitCall('call:end', { call_id: callId, conversation_id: conversationId, to_user_id: peerId })
        cleanup(false)
        setOutcome('no-answer')
        window.setTimeout(() => setOutcome(null), 2200)
      }, 30000)
    } catch {
      cleanup(false)
      window.dispatchEvent(new CustomEvent('prepza-call-error', { detail: 'Microphone or camera permission is required for calls.' }))
    }
  }

  async function createAndSendOffer(event: CallSignal) {
    const current = callRef.current
    if (!current || current.callId !== event.call_id || !peer.current) return
    try {
      const offer = await peer.current.createOffer()
      await peer.current.setLocalDescription(offer)
      emitCall('call:offer', { call_id: current.callId, conversation_id: current.conversationId, to_user_id: current.peerId, payload: offer })
    } catch { cleanup(true) }
  }

  async function acceptIncoming() {
    const event = incomingRef.current
    if (!event || !resolvedUserId || callRef.current) return
    if (!navigator.onLine) { window.dispatchEvent(new CustomEvent('prepza-call-error', { detail: 'Calls require an internet connection.' })); return }
    const active = { callId: event.call_id, conversationId: event.conversation_id, peerId: event.from_user_id, peerName: event.from_name || 'Student', kind: event.kind, incoming: true, connected: false } as ActiveCall
    try {
      const stream = await ensureMedia(event.kind)
      const pc = createPeer(active)
      stream.getTracks().forEach(track => pc.addTrack(track, stream))
      callRef.current = active
      setCall(active)
      setIncoming(null)
      if (incomingTimeoutRef.current) { window.clearTimeout(incomingTimeoutRef.current); incomingTimeoutRef.current = null }
      emitCall('call:accept', { call_id: event.call_id, conversation_id: event.conversation_id, to_user_id: event.from_user_id })
    } catch {
      emitCall('call:reject', { call_id: event.call_id, to_user_id: event.from_user_id })
      setIncoming(null)
    }
  }

  async function acceptOffer(event: CallSignal) {
    const current = callRef.current
    if (!peer.current || !current || current.callId !== event.call_id) return
    try {
      await peer.current.setRemoteDescription(event.payload as RTCSessionDescriptionInit)
      for (const candidate of pendingIce.current.splice(0)) await peer.current.addIceCandidate(candidate)
      const answer = await peer.current.createAnswer()
      await peer.current.setLocalDescription(answer)
      emitCall('call:answer', { call_id: event.call_id, conversation_id: event.conversation_id, to_user_id: event.from_user_id, payload: answer })
    } catch { cleanup(true) }
  }

  async function addIce(candidate: RTCIceCandidateInit) {
    if (!peer.current || !peer.current.remoteDescription) { pendingIce.current.push(candidate); return }
    try { await peer.current.addIceCandidate(candidate) } catch { /* stale ICE candidate */ }
  }

  function cleanup(notify: boolean) {
    const current = callRef.current
    if (notify && current) emitCall('call:end', { call_id: current.callId, conversation_id: current.conversationId, to_user_id: current.peerId })
    if (callTimeoutRef.current) { window.clearTimeout(callTimeoutRef.current); callTimeoutRef.current = null }
    if (incomingTimeoutRef.current) { window.clearTimeout(incomingTimeoutRef.current); incomingTimeoutRef.current = null }
    peer.current?.close(); peer.current = null
    localStream.current?.getTracks().forEach(track => track.stop()); localStream.current = null
    if (localVideo.current) localVideo.current.srcObject = null
    if (remoteVideo.current) remoteVideo.current.srcObject = null
    if (remoteAudio.current) remoteAudio.current.srcObject = null
    callRef.current = null
    setConnectedAt(null); setCallSeconds(0)
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

  if (!incoming && !call && !outcome) return null
  return <>
    <audio ref={remoteAudio} autoPlay playsInline style={{ display: 'none' }} />
    {outcome && !incoming && !call && <div style={{ position:'fixed',left:'50%',bottom:28,transform:'translateX(-50%)',zIndex:3100,background:'#fff',color:'#111827',borderRadius:14,padding:'12px 18px',boxShadow:'0 12px 40px rgba(0,0,0,.24)',fontSize:13,fontWeight:750 }}>{outcome === 'unavailable' ? 'Student is unavailable.' : outcome === 'no-answer' ? 'No answer.' : 'Call ended.'}</div>}
    {incoming && !call && <div style={{ position:'fixed', inset:0, zIndex:3000, background:'rgba(4,8,20,.86)', display:'flex', alignItems:'center', justifyContent:'center', padding:20, color:'#fff' }}>
      <div style={{ width:'min(360px,100%)', textAlign:'center' }}>
        <div style={{ width:92,height:92,borderRadius:'50%',margin:'0 auto 18px',background:'#c9a84c',color:'#0b1437',display:'grid',placeItems:'center',fontSize:34,fontWeight:900 }}>{(incoming.from_name || 'S').slice(0,1).toUpperCase()}</div>
        <div style={{ fontSize:24,fontWeight:850 }}>{incoming.from_name || 'Student'}</div><div style={{ marginTop:7,opacity:.7 }}>{incoming.kind === 'video' ? 'Incoming video call' : 'Incoming voice call'}</div>
        <div style={{ display:'flex',justifyContent:'center',gap:34,marginTop:42 }}>
          <button type="button" onClick={() => { emitCall('call:reject',{ call_id:incoming.call_id,to_user_id:incoming.from_user_id });setIncoming(null) }} aria-label="Decline call" title="Decline call" style={{ width:64,height:64,border:0,borderRadius:'50%',background:'#d84b4b',color:'#fff',cursor:'pointer',display:'grid',placeItems:'center' }}><svg width="25" height="25" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg></button>
          <button type="button" onClick={() => void acceptIncoming()} aria-label="Accept call" title="Accept call" style={{ width:64,height:64,border:0,borderRadius:'50%',background:'#2fa866',color:'#fff',cursor:'pointer',display:'grid',placeItems:'center' }}><svg width="25" height="25" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 12.5 10 16l8-8"/></svg></button>
        </div>
      </div>
    </div>}
    {call && <div style={{ position:'fixed', inset:0, zIndex:2900, background:'#090c14', color:'#fff', display:'flex', flexDirection:'column' }}>
      {call.kind === 'video' && <><video ref={remoteVideo} autoPlay playsInline style={{ position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'cover',background:'#111' }} /><video ref={localVideo} autoPlay playsInline muted style={{ position:'absolute',right:18,top:18,width:'28%',maxWidth:220,aspectRatio:'3/4',objectFit:'cover',borderRadius:18,background:'#222',boxShadow:'0 8px 30px rgba(0,0,0,.35)' }} /></>}
      {call.kind === 'voice' && <div style={{ flex:1,display:'grid',placeItems:'center' }}><div style={{ textAlign:'center' }}><div style={{ width:110,height:110,borderRadius:'50%',background:'#c9a84c',color:'#0b1437',display:'grid',placeItems:'center',fontSize:42,fontWeight:900,margin:'0 auto 18px' }}>{call.peerName.slice(0,1).toUpperCase()}</div><div style={{fontSize:25,fontWeight:850}}>{call.peerName}</div><div style={{marginTop:8,opacity:.65}}>{call.connected ? `Connected · ${Math.floor(callSeconds / 60)}:${String(callSeconds % 60).padStart(2,'0')}` : 'Calling…'}</div></div></div>}
      <div style={{ position:'absolute',left:0,right:0,bottom:0,padding:'28px 22px 34px',display:'flex',justifyContent:'center',gap:14,background:'linear-gradient(transparent,rgba(0,0,0,.65))' }}>
        <button type="button" onClick={() => { const tracks = localStream.current?.getAudioTracks() || []; tracks.forEach(track => { track.enabled = !track.enabled }); setMuted(tracks[0] ? !tracks[0].enabled : false) }} aria-label={muted ? "Unmute microphone" : "Mute microphone"} title={muted ? "Unmute microphone" : "Mute microphone"} style={{width:52,height:52,border:0,borderRadius:'50%',background:muted?'#fff':'rgba(255,255,255,.18)',color:muted?'#111':'#fff',cursor:'pointer',display:'grid',placeItems:'center'}}>
          <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/>{muted && <path d="M4 4l16 16"/>}</svg>
        </button>
        {call.kind === 'video' && <button type="button" onClick={() => { const tracks = localStream.current?.getVideoTracks() || []; tracks.forEach(track => { track.enabled = !track.enabled }); setCameraOff(tracks[0] ? !tracks[0].enabled : false) }} aria-label={cameraOff ? "Turn camera on" : "Turn camera off"} title={cameraOff ? "Turn camera on" : "Turn camera off"} style={{width:52,height:52,border:0,borderRadius:'50%',background:cameraOff?'#fff':'rgba(255,255,255,.18)',color:cameraOff?'#111':'#fff',cursor:'pointer',display:'grid',placeItems:'center'}}>
          <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 11 5-3v8l-5-3Z"/>{cameraOff && <path d="M4 4l16 16"/>}</svg>
        </button>}
        <button type="button" onClick={() => { cleanup(true); setOutcome('ended'); window.setTimeout(() => setOutcome(null), 1800) }} aria-label="End call" title="End call" style={{width:58,height:58,border:0,borderRadius:'50%',background:'#d84b4b',color:'#fff',cursor:'pointer',display:'grid',placeItems:'center'}}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M5 5l14 14M19 5 5 19"/></svg>
        </button>
      </div>
    </div>}
  </>
}

export { type Props as CallExperienceProps }
