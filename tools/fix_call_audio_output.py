from pathlib import Path

p = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'crypto' / 'CallExperience.tsx'
s = p.read_text(encoding='utf-8')

if 'const remoteAudio = useRef<HTMLAudioElement>(null)' not in s:
    s = s.replace("  const remoteVideo = useRef<HTMLVideoElement>(null)\n", "  const remoteVideo = useRef<HTMLVideoElement>(null)\n  const remoteAudio = useRef<HTMLAudioElement>(null)\n", 1)

old = """    pc.ontrack = event => {\n      if (remoteVideo.current && event.streams[0]) remoteVideo.current.srcObject = event.streams[0]\n    }"""
new = """    pc.ontrack = event => {\n      if (!event.streams[0]) return\n      if (remoteVideo.current) remoteVideo.current.srcObject = event.streams[0]\n      if (remoteAudio.current) remoteAudio.current.srcObject = event.streams[0]\n    }"""
if old in s:
    s = s.replace(old, new, 1)

if 'ref={remoteAudio}' not in s:
    marker = "{call.kind === 'voice' && <div style={{ flex:1,display:'grid',placeItems:'center' }}><div style={{ textAlign:'center' }}>"
    if marker not in s:
        raise SystemExit('CALL_AUDIO_PATCH_FAILED: voice-call render anchor missing')
    s = s.replace(marker, "<audio ref={remoteAudio} autoPlay playsInline style={{ display:'none' }} />" + marker, 1)

if 'remoteAudio.current.srcObject = null' not in s:
    s = s.replace("    if (remoteVideo.current) remoteVideo.current.srcObject = null\n", "    if (remoteVideo.current) remoteVideo.current.srcObject = null\n    if (remoteAudio.current) remoteAudio.current.srcObject = null\n", 1)

p.write_text(s, encoding='utf-8')
print('CALL_AUDIO_OUTPUT_FIXED')
