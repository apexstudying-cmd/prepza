from pathlib import Path

root = Path(__file__).resolve().parents[1]
server = root / 'realtime_server.py'
s = server.read_text()
if 'def _clear_calls_for_user' not in s:
    helper = '''\n\ndef _clear_calls_for_user(user_id):\n    ended = []\n    with _active_calls_lock:\n        for call_id, call in list(_active_calls.items()):\n            if user_id in {call["caller_id"], call["callee_id"]}:\n                ended.append((call_id, call))\n                _active_calls.pop(call_id, None)\n    for call_id, call in ended:\n        other_id = call["callee_id"] if user_id == call["caller_id"] else call["caller_id"]\n        emit_to_user(other_id, "call:ended", {"call_id": call_id, "conversation_id": call["conversation_id"], "from_user_id": user_id, "to_user_id": other_id, "kind": call["kind"]})\n'''
    s = s.replace('\ndef emit_to_user(user_id, event, payload):', helper + '\n\ndef emit_to_user(user_id, event, payload):', 1)
    s = s.replace('    rooms, user_id = socket_rooms_for_disconnect()\n    if user_id is None:\n        return', '    rooms, user_id = socket_rooms_for_disconnect()\n    if user_id is None:\n        return\n    _clear_calls_for_user(user_id)', 1)
server.write_text(s)

client = root / 'frontend' / 'src' / 'crypto' / 'CallExperience.tsx'
s = client.read_text()
old = "if (event.type === 'call:answer' && event.payload && peer.current) void peer.current.setRemoteDescription(event.payload as RTCSessionDescriptionInit)"
new = "if (event.type === 'call:answer' && event.payload && peer.current) void (async () => { await peer.current!.setRemoteDescription(event.payload as RTCSessionDescriptionInit); for (const candidate of pendingIce.current.splice(0)) await peer.current!.addIceCandidate(candidate) })()"
if old in s:
    s = s.replace(old, new, 1)

if 'const remoteAudio = useRef<HTMLAudioElement>(null)' not in s:
    s = s.replace("  const remoteVideo = useRef<HTMLVideoElement>(null)\n", "  const remoteVideo = useRef<HTMLVideoElement>(null)\n  const remoteAudio = useRef<HTMLAudioElement>(null)\n", 1)
if 'remoteAudio.current.srcObject = event.streams[0]' not in s:
    s = s.replace("      if (remoteVideo.current && event.streams[0]) remoteVideo.current.srcObject = event.streams[0]\n", "      if (remoteVideo.current && event.streams[0]) remoteVideo.current.srcObject = event.streams[0]\n      if (remoteAudio.current && event.streams[0]) { remoteAudio.current.srcObject = event.streams[0]; void remoteAudio.current.play().catch(() => {}) }\n", 1)
if '<audio ref={remoteAudio} autoPlay playsInline' not in s:
    s = s.replace("  return <>\n", "  return <>\n    <audio ref={remoteAudio} autoPlay playsInline style={{ display: 'none' }} />\n", 1)
if 'remoteAudio.current.srcObject = null' not in s:
    s = s.replace("    if (remoteVideo.current) remoteVideo.current.srcObject = null\n", "    if (remoteVideo.current) remoteVideo.current.srcObject = null\n    if (remoteAudio.current) remoteAudio.current.srcObject = null\n", 1)
client.write_text(s)
print('CALLING_HARDENED')
