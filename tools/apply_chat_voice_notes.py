from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

app = ROOT / 'app.py'
text = app.read_text(encoding='utf-8')
if 'CHAT_AUDIO_EXTENSIONS' not in text:
    text = text.replace('CHAT_ATTACHMENT_MAX_SIZE_BYTES = 20 * 1024 * 1024\n', 'CHAT_ATTACHMENT_MAX_SIZE_BYTES = 20 * 1024 * 1024\nCHAT_AUDIO_EXTENSIONS = {"webm", "ogg", "mp3", "m4a", "wav", "aac", "mp4"}\n', 1)
text = text.replace('    ext = get_document_extension(original_filename)\n    if not ext:\n        return jsonify({"error": "Unsupported file type"}), 400\n', '    ext = get_document_extension(original_filename)\n    if not ext:\n        candidate_ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""\n        ext = candidate_ext if candidate_ext in CHAT_AUDIO_EXTENSIONS else None\n    if not ext:\n        return jsonify({"error": "Unsupported file type"}), 400\n', 1)
app.write_text(text, encoding='utf-8')

for rel in ('frontend/src/crypto/e2eeFetchBridge.ts', 'frontend/src/crypto/directChatE2EE.ts'):
    path = ROOT / rel
    text = path.read_text(encoding='utf-8')
    if 'webm:' not in text:
        text = text.replace("    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',\n  }", "    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',\n    webm: 'audio/webm', ogg: 'audio/ogg', mp3: 'audio/mpeg', m4a: 'audio/mp4', wav: 'audio/wav', aac: 'audio/aac', mp4: 'audio/mp4',\n  }", 1)
    path.write_text(text, encoding='utf-8')

chat = ROOT / 'frontend/src/crypto/WhatsAppChatExperience.tsx'
s = chat.read_text(encoding='utf-8')

if 'function isAudio(' not in s:
    s = s.replace("function isImage(fileType: string) { return /^(jpg|jpeg|png|gif|webp)$/i.test(fileType) || fileType.startsWith('image/') }", "function isImage(fileType: string) { return /^(jpg|jpeg|png|gif|webp)$/i.test(fileType) || fileType.startsWith('image/') }\nfunction isAudio(fileType: string) { return /^(webm|ogg|mp3|m4a|wav|aac|mp4)$/i.test(fileType) || fileType.startsWith('audio/') }")
if 'recordingVoice' not in s:
    s = s.replace("  const [groupError, setGroupError] = useState('')", "  const [groupError, setGroupError] = useState('')\n  const [recordingVoice, setRecordingVoice] = useState(false)\n  const [recordingSeconds, setRecordingSeconds] = useState(0)")
if 'voiceRecorderRef' not in s:
    s = s.replace("  const csrfTokenRef = useRef('')", "  const csrfTokenRef = useRef('')\n  const voiceRecorderRef = useRef<MediaRecorder | null>(null)\n  const voiceChunksRef = useRef<Blob[]>([])\n  const voiceTimerRef = useRef<number | null>(null)\n")

if 'startVoiceRecording' not in s:
    fn = """  const startVoiceRecording = async () => {
    if (selectedId == null || recordingVoice || uploading || sending) return
    if (!navigator.onLine) { setError('Voice notes require an internet connection.'); return }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { setError('Voice recording is not supported in this browser.'); return }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'].find(type => MediaRecorder.isTypeSupported(type)) || ''
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
      voiceChunksRef.current = []
      recorder.ondataavailable = event => { if (event.data.size > 0) voiceChunksRef.current.push(event.data) }
      recorder.onstop = () => {
        stream.getTracks().forEach(track => track.stop())
        const blob = new Blob(voiceChunksRef.current, { type: recorder.mimeType || 'audio/webm' })
        voiceChunksRef.current = []
        setRecordingVoice(false)
        if (voiceTimerRef.current) { window.clearInterval(voiceTimerRef.current); voiceTimerRef.current = null }
        setRecordingSeconds(0)
        if (blob.size > 0) {
          const extension = recorder.mimeType.includes('mp4') ? 'm4a' : recorder.mimeType.includes('ogg') ? 'ogg' : 'webm'
          void sendAttachment(new File([blob], `voice-note-${Date.now()}.${extension}`, { type: blob.type }))
        }
      }
      voiceRecorderRef.current = recorder
      recorder.start(250)
      setRecordingVoice(true)
      setRecordingSeconds(0)
      voiceTimerRef.current = window.setInterval(() => setRecordingSeconds(value => value + 1), 1000)
    } catch { setError('Microphone access was not granted.'); setRecordingVoice(false) }
  }
  const stopVoiceRecording = () => { const recorder = voiceRecorderRef.current; voiceRecorderRef.current = null; if (recorder && recorder.state !== 'inactive') recorder.stop() }
"""
    marker = next((candidate for candidate in ('  const loadEarlier = async () => {', '  const runMessageSearch = async () => {', '  const openAda = () =>') if candidate in s), None)
    if marker:
        s = s.replace(marker, fn + marker, 1)

s = re.sub(r'accept="\.pdf,\.doc,\.docx,\.ppt,\.pptx,\.jpg,\.jpeg,\.png(?:,[^"]*)?"', 'accept=".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png,.webm,.ogg,.mp3,.m4a,.wav,.aac,.mp4"', s, count=1)

if 'message.attachment.view_url && isAudio' not in s:
    needle = "message.attachment.view_url && isImage(message.attachment.file_type) ? <img src={message.attachment.view_url} alt={message.attachment.original_filename} style={{ maxWidth:'100%',maxHeight:260,borderRadius:10,display:'block' }} /> :"
    if needle in s:
        s = s.replace(needle, needle + " message.attachment.view_url && isAudio(message.attachment.file_type) ? <audio controls preload=\"metadata\" src={message.attachment.view_url} style={{ width:'min(320px,100%)',display:'block' }} /> :", 1)

if 'aria-label=\"Record voice note\"' not in s:
    voice_button = "<button type=\"button\" onClick={() => void startVoiceRecording()} disabled={recordingVoice || uploading || sending} aria-label=\"Record voice note\" title=\"Record voice note\" style={{ width:40,height:40,border:0,borderRadius:12,background:recordingVoice?'#d84b4b':'#f1f2f4',color:recordingVoice?'#fff':'#5e6470',fontWeight:900,cursor:'pointer' }}>{recordingVoice ? '■' : '◉'}</button>"
    match = re.search(r'(<button type=\"button\" className=\"prepza-wa-attach\"[^>]*>\+?</button>)', s)
    if match:
        s = s[:match.end()] + voice_button + s[match.end():]
    else:
        textarea = re.search(r'<textarea\b', s)
        if not textarea:
            raise SystemExit('CHAT_VOICE_PATCH_FAILED: no stable textarea/composer anchor found for voice-note button')
        s = s[:textarea.start()] + voice_button + s[textarea.start():]

if 'Recording voice note ·' not in s:
    marker = "{replyingTo && <div style={{ maxWidth:900,margin:'0 auto 7px',background:'#f6f1df'"
    if marker in s:
        ui = "{recordingVoice && <div style={{ maxWidth:900,margin:'0 auto 7px',background:'#0b1437',color:'#fff',borderRadius:10,padding:'8px 10px',display:'flex',alignItems:'center',gap:9 }}><span style={{ width:9,height:9,borderRadius:'50%',background:'#e05252' }} /><span style={{ flex:1,fontSize:11,fontWeight:800 }}>Recording voice note · {Math.floor(recordingSeconds / 60)}:{String(recordingSeconds % 60).padStart(2,'0')}</span><button type=\"button\" onClick={stopVoiceRecording} style={{ border:0,borderRadius:9,background:'#e4c96a',color:'#0b1437',padding:'6px 10px',fontWeight:900,cursor:'pointer' }}>Stop</button></div>}"
        s = s.replace(marker, ui + marker, 1)

if 'const enriched = await Promise.all(baseChats.map' not in s:
    old = re.search(r"  const loadList = async \(\) => \{.*?\n  useEffect\(\(\) => \{ if \(!visible\) return; void loadList\(\);", s, flags=re.S)
    if old:
        replacement = """  const loadList = async () => { setListError(''); try { const result = await api<{ chats: ChatSummary[] }>('/chats'); const baseChats = Array.isArray(result.chats) ? result.chats : []; const enriched = await Promise.all(baseChats.map(async chat => { if (!chat.last_message_at) return chat; try { const latest = await api<{ messages: Message[] }>(`/chats/${chat.id}/messages`); const candidates = (latest.messages || []).filter(message => message.kind !== 'reaction'); const message = candidates[candidates.length - 1]; if (!message) return chat; if (message.attachment && isAudio(message.attachment.file_type)) return { ...chat, last_message: 'Voice message' }; const preview = displayText(message).trim(); return { ...chat, last_message: preview || (message.attachment ? 'Attachment' : chat.last_message) }; } catch { return chat } })); setChats(enriched) } catch (value) { setListError(friendlyError(value, 'Could not load your conversations.')) } }
  useEffect(() => { if (!visible) return; void loadList();"""
        s = s[:old.start()] + replacement + s[old.end():]

chat.write_text(s, encoding='utf-8')
print('CHAT_VOICE_PATCH_APPLIED')
