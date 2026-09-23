import { useEffect, useRef, useState } from 'react'
import { emitCall, installCallRealtime, onCallSignal, type CallSignal } from './callRealtime'

type Props = { userId: number | null; displayName?: string }
type ActiveCall = { callId: string; conversationId: number; peerId: number; peerName: string; kind: 'voice' | 'video'; incoming: boolean; connected: boolean }

const ICE_SERVERS: RTCIceServer[] = (() => {
  const raw = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env?.VITE_WEBRTC_ICE_SERVERS
  if (raw) {
    try { const parsed = JSON.parse(raw); if (Array.isArray(parsed) && parsed.length) return parsed } catch { /* use safe default */ }
  }
  return [{ urls: 'stun:stun.l.google.com:19302' }]
})()

function randomCallId() { return `${Date.now().toString(36)}-${crypto.randomUUID()}` }

export default function CallExperience({ userId }: Props) {
  const [incoming, setIncoming] = useState<CallSignal | null>(null)
  const [call, setCall] = useState<ActiveCall | null>(null)
  const [muted, setMuted] = useState(false)
  const [cameraOff, setCameraOff] = useState(false)
  const [screenSharing, setScreenSharing] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const screenStream = useRef<MediaStream | null>(null)
  const callStartedAt = useRef<number | null>(null)
  const localVideo = useRef<HTMLVideoElement>(null)
  const remoteVideo = useRef<HTMLVideoElement>(null)
  const remoteAudio = useRef<HTMLAudioElement>(null)
  const peer = useRef<RTCPeerConnection | null>(null)
  const localStream = useRef<MediaStream | null>(null)
  const pendingIce = useRef<RTCIceCandidateInit[]>([])
  const callRef = useRef<ActiveCall | null>(null)
  const incomingRef = useRef<CallSignal | null>(null)

  useEffect(() => { callRef.current = call; if (!call) { setSeconds(0); callStartedAt.current = null } else if (!callStartedAt.current) callStartedAt.current = Date.now() }, [call])
  useEffect(() => { if (!call) return; const timer = window.setInterval(() => { if (callStartedAt.current) setSeconds(Math.floor((Date.now() - callStartedAt.current) / 1000)) }, 1000); return () => window.clearInterval(timer) }, [call])
  useEffect(() => { incomingRef.current = incoming }, [incoming])

  useEffect(() => {
    if (!userId) return
    installCallRealtime()
    const unsubscribe = onCallSignal(event => {
      if (event.to_user_id !== userId) return
      if (event.type === 'call:incoming') { setIncoming(event); return }
      if (event.type === 'call:rejected' || event.type === 'call:ended') { cleanup(false); return }
      if (event.type === 'call:accepted') { void createAndSendOffer(event); return }
      if (event.type === 'call:offer' && event.payload) { void acceptOffer(event); return }
      if (event.type === 'call:answer' && event.payload && peer.current) { void (async () => { await peer.current!.setRemoteDescription(event.payload as RTCSessionDescriptionInit); for (const candidate of pendingIce.current.splice(0)) await peer.current!.addIceCandidate(candidate) })(); return }
      if (event.type === 'call:ice' && event.payload) { void addIce(event.payload as RTCIceCandidateInit) }
    })
    return () => { unsubscribe() }
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
    pc.onicecandidate = event => {
      if (event.candidate) emitCall('call:ice', { call_id: callInfo.callId, to_user_id: callInfo.peerId, payload: event.candidate.toJSON() })
    }
    pc.ontrack = event => {
      if (remoteVideo.current && event.streams[0]) remoteVideo.current.srcObject = event.streams[0]
      if (remoteAudio.current && event.streams[0]) { remoteAudio.current.srcObject = event.streams[0]; void remoteAudio.current.play().catch(() => {}) }
    }
    pc.onconnectionstatechange = () => {
      if (['failed', 'closed', 'disconnected'].includes(pc.connectionState)) cleanup(true)
      else if (pc.connectionState === 'connected') setCall(current => current ? { ...current, connected: true } : current)
    }
    peer.current = pc
    return pc
  }

  async function startCall(conversationId: number, peerId: number, peerName: string, kind: 'voice' | 'video') {
    if (callRef.current || !userId) return
    if (!navigator.onLine) { window.dispatchEvent(new CustomEvent('prepza-call-error', { detail: 'Calls require an internet connection.' })); return }
    const callId = randomCallId()
    const active = { callId, conversationId, peerId, peerName, kind, incoming: false, connected: false } as ActiveCall
    try {
      const stream = await ensureMedia(kind)
      const pc = createPeer(active)
      stream.getTracks().forEach(track => pc.addTrack(track, stream))
      callRef.current = active
      setCall(active)
      emitCall('call:invite', { call_id: callId, conversation_id: conversationId, to_user_id: peerId, kind })
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
    if (!event || !userId || callRef.current) return
    if (!navigator.onLine) { window.dispatchEvent(new CustomEvent('prepza-call-error', { detail: 'Calls require an internet connection.' })); return }
    const active = { callId: event.call_id, conversationId: event.conversation_id, peerId: event.from_user_id, peerName: event.from_name || 'Student', kind: event.kind, incoming: true, connected: false } as ActiveCall
    try {
      const stream = await ensureMedia(event.kind)
      const pc = createPeer(active)
      stream.getTracks().forEach(track => pc.addTrack(track, stream))
      callRef.current = active
      setCall(active)
      setIncoming(null)
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

  async function toggleScreenShare() {
    if (!call || call.kind !== 'video' || !peer.current) return
    try {
      if (screenSharing && screenStream.current) {
        const cameraTrack = localStream.current?.getVideoTracks()[0]
        const sender = peer.current.getSenders().find(item => item.track?.kind === 'video')
        if (sender && cameraTrack) await sender.replaceTrack(cameraTrack)
        screenStream.current.getTracks().forEach(track => track.stop())
        screenStream.current = null
        setScreenSharing(false)
        return
      }
      if (!navigator.mediaDevices?.getDisplayMedia) throw new Error('Screen sharing is not supported in this browser.')
      const display = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true })
      const track = display.getVideoTracks()[0]
      const sender = peer.current.getSenders().find(item => item.track?.kind === 'video')
      if (!sender) { display.getTracks().forEach(t => t.stop()); throw new Error('Video track is unavailable.') }
      await sender.replaceTrack(track)
      screenStream.current = display
      setScreenSharing(true)
      track.onended = () => { void toggleScreenShare() }
    } catch (error) {
      window.dispatchEvent(new CustomEvent('prepza-call-error', { detail: error instanceof Error ? error.message : 'Screen sharing could not start.' }))
    }
  }

  async function switchCamera() {
    if (!call || call.kind !== 'video' || !navigator.mediaDevices?.getUserMedia || !peer.current) return
    try {
      const current = localStream.current?.getVideoTracks()[0]
      const nextFacing = current?.getSettings().facingMode === 'environment' ? 'user' : 'environment'
      const replacement = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: nextFacing } }, audio: false })
      const track = replacement.getVideoTracks()[0]
      const sender = peer.current.getSenders().find(item => item.track?.kind === 'video')
      if (!sender) { replacement.getTracks().forEach(t => t.stop()); return }
      await sender.replaceTrack(track)
      if (current) current.stop()
      if (localStream.current) { localStream.current.removeTrack(current!); localStream.current.addTrack(track) }
    } catch { /* keep the current camera */ }
  }

  async function enterPictureInPicture() {
    const video = remoteVideo.current as (HTMLVideoElement & { requestPictureInPicture?: () => Promise<void> }) | null
    if (!video?.requestPictureInPicture) return
    try { await video.requestPictureInPicture() } catch { /* browser denied PiP */ }
  }

  function cleanup(notify: boolean) {
    const current = callRef.current
    if (notify && current) emitCall('call:end', { call_id: current.callId, conversation_id: current.conversationId, to_user_id: current.peerId })
    peer.current?.close(); peer.current = null
    screenStream.current?.getTracks().forEach(track => track.stop()); screenStream.current = null
    localStream.current?.getTracks().forEach(track => track.stop()); localStream.current = null
    if (localVideo.current) localVideo.current.srcObject = null
    if (remoteVideo.current) remoteVideo.current.srcObject = null
    if (remoteAudio.current) remoteAudio.current.srcObject = null
    callRef.current = null
    setCall(null); setIncoming(null); setMuted(false); setCameraOff(false); setScreenSharing(false); setSeconds(0); callStartedAt.current = null; pendingIce.current = []
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
    <audio ref={remoteAudio} autoPlay playsInline style={{ display: 'none' }} />
    {incoming && !call && <div style={{ position:'fixed', inset:0, zIndex:3000, background:'rgba(4,8,20,.86)', display:'flex', alignItems:'center', justifyContent:'center', padding:20, color:'#fff' }}>
      <div style={{ width:'min(360px,100%)', textAlign:'center' }}>
        <div style={{ width:92,height:92,borderRadius:'50%',margin:'0 auto 18px',background:'#c9a84c',color:'#0b1437',display:'grid',placeItems:'center',fontSize:34,fontWeight:900 }}>{(incoming.from_name || 'S').slice(0,1).toUpperCase()}</div>
        <div style={{ fontSize:24,fontWeight:850 }}>{incoming.from_name || 'Student'}</div><div style={{ marginTop:7,opacity:.7 }}>{incoming.kind === 'video' ? 'Incoming video call' : 'Incoming voice call'}</div>
        <div style={{ display:'flex',justifyContent:'center',gap:34,marginTop:42 }}><button type="button" onClick={() => { emitCall('call:reject',{ call_id:incoming.call_id,to_user_id:incoming.from_user_id });setIncoming(null) }} aria-label="Decline call" style={{ width:62,height:62,border:0,borderRadius:'50%',background:'#d84b4b',color:'#fff',fontSize:25 }}>×</button><button type="button" onClick={() => void acceptIncoming()} aria-label="Accept call" style={{ width:62,height:62,border:0,borderRadius:'50%',background:'#2fa866',color:'#fff',fontSize:25 }}>✓</button></div>
      </div>
    </div>}
    {call && <div style={{ position:'fixed', inset:0, zIndex:2900, background:'#090c14', color:'#fff', display:'flex', flexDirection:'column' }}>
      {call.kind === 'video' && <><video ref={remoteVideo} autoPlay playsInline style={{ position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'cover',background:'#111' }} /><video ref={localVideo} autoPlay playsInline muted style={{ position:'absolute',right:18,top:18,width:'28%',maxWidth:220,aspectRatio:'3/4',objectFit:'cover',borderRadius:18,background:'#222',boxShadow:'0 8px 30px rgba(0,0,0,.35)' }} /></>}
      {call.kind === 'voice' && <div style={{ flex:1,display:'grid',placeItems:'center' }}><div style={{ textAlign:'center' }}><div style={{ width:110,height:110,borderRadius:'50%',background:'#c9a84c',color:'#0b1437',display:'grid',placeItems:'center',fontSize:42,fontWeight:900,margin:'0 auto 18px' }}>{call.peerName.slice(0,1).toUpperCase()}</div><div style={{fontSize:25,fontWeight:850}}>{call.peerName}</div><div style={{marginTop:8,opacity:.65}}>{call.connected ? `${String(Math.floor(seconds / 60)).padStart(2,'0')}:${String(seconds % 60).padStart(2,'0')}` : 'Calling…'}</div></div></div>}
      <div style={{ position:'absolute',left:0,right:0,bottom:0,padding:'20px 18px 32px',display:'flex',justifyContent:'center',gap:12,background:'linear-gradient(transparent,rgba(0,0,0,.72))',flexWrap:'wrap' }}>
        <button type="button" onClick={() => { const tracks = localStream.current?.getAudioTracks() || []; tracks.forEach(track => { track.enabled = !track.enabled }); setMuted(tracks[0] ? !tracks[0].enabled : false) }} aria-label={muted ? 'Unmute microphone' : 'Mute microphone'} style={{width:52,height:52,border:0,borderRadius:'50%',background:muted?'#fff':'rgba(255,255,255,.18)',color:muted?'#111':'#fff',display:'grid',placeItems:'center'}}>
          <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/></svg>
        </button>
        {call.kind === 'video' && <button type="button" onClick={() => { const tracks = localStream.current?.getVideoTracks() || []; tracks.forEach(track => { track.enabled = !track.enabled }); setCameraOff(tracks[0] ? !tracks[0].enabled : false) }} aria-label={cameraOff ? 'Turn camera on' : 'Turn camera off'} style={{width:52,height:52,border:0,borderRadius:'50%',background:cameraOff?'#fff':'rgba(255,255,255,.18)',color:cameraOff?'#111':'#fff',display:'grid',placeItems:'center'}}>
          <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m16 13 5 3V8l-5 3Z"/><rect x="3" y="6" width="13" height="12" rx="2"/></svg>
        </button>}
        {call.kind === 'video' && <button type="button" onClick={() => void switchCamera()} aria-label="Switch camera" style={{width:52,height:52,border:0,borderRadius:'50%',background:'rgba(255,255,255,.18)',color:'#fff',display:'grid',placeItems:'center'}}>
          <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h12l-2-2M20 17H8l2 2"/><path d="M16 5l2 2-2 2M8 15l-2 2 2 2"/></svg>
        </button>}
        {call.kind === 'video' && <button type="button" onClick={() => void toggleScreenShare()} aria-label={screenSharing ? 'Stop screen sharing' : 'Share screen'} style={{width:52,height:52,border:0,borderRadius:'50%',background:screenSharing?'#fff':'rgba(255,255,255,.18)',color:screenSharing?'#111':'#fff',display:'grid',placeItems:'center'}}>
          <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/></svg>
        </button>}
        {call.kind === 'video' && <button type="button" onClick={() => void enterPictureInPicture()} aria-label="Picture in picture" style={{width:52,height:52,border:0,borderRadius:'50%',background:'rgba(255,255,255,.18)',color:'#fff',display:'grid',placeItems:'center'}}>
          <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M13 14h6v4h-6z"/></svg>
        </button>}
        <button type="button" onClick={() => cleanup(true)} aria-label="End call" style={{width:58,height:58,border:0,borderRadius:'50%',background:'#d84b4b',color:'#fff',display:'grid',placeItems:'center'}}>
          <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 5c3 4 9 4 12 0l2 3c-1 2-3 4-5 5v3a2 2 0 0 1-2 2h-2a2 2 0 0 1-2-2v-3c-2-1-4-3-5-5l2-3Z"/></svg>
        </button>
      </div>
    </div>}
  </>
}

export { type Props as CallExperienceProps }
