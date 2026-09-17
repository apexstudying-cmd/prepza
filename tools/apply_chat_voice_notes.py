from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return False
    if old not in text:
        raise SystemExit(f"Chat voice patch anchor missing: {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True

# Backend: chat attachments may use audio formats without widening the
# document-upload allowlist used elsewhere in the app.
app = ROOT / "app.py"
replace_once(app, 'CHAT_ATTACHMENT_MAX_SIZE_BYTES = 20 * 1024 * 1024\n', 'CHAT_ATTACHMENT_MAX_SIZE_BYTES = 20 * 1024 * 1024\nCHAT_AUDIO_EXTENSIONS = {"webm", "ogg", "mp3", "m4a", "wav", "aac", "mp4"}\n')
replace_once(app, '    ext = get_document_extension(original_filename)\n    if not ext:\n        return jsonify({"error": "Unsupported file type"}), 400\n    if not isinstance(file_size_bytes, int) or isinstance(file_size_bytes, bool) or file_size_bytes <= 0:\n', '    ext = get_document_extension(original_filename)\n    if not ext:\n        candidate_ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""\n        ext = candidate_ext if candidate_ext in CHAT_AUDIO_EXTENSIONS else None\n    if not ext:\n        return jsonify({"error": "Unsupported file type"}), 400\n    if not isinstance(file_size_bytes, int) or isinstance(file_size_bytes, bool) or file_size_bytes <= 0:\n')

# E2EE attachment bridges: preserve the real audio MIME type when an
# encrypted voice note becomes a local Blob URL.
for rel in ("frontend/src/crypto/e2eeFetchBridge.ts", "frontend/src/crypto/directChatE2EE.ts"):
    path = ROOT / rel
    replace_once(path, "    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',\n  }", "    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',\n    webm: 'audio/webm', ogg: 'audio/ogg', mp3: 'audio/mpeg',\n    m4a: 'audio/mp4', wav: 'audio/wav', aac: 'audio/aac', mp4: 'audio/mp4',\n  }")

chat = ROOT / "frontend/src/crypto/WhatsAppChatExperience.tsx"
replace_once(chat, "function isImage(fileType: string) { return /^(jpg|jpeg|png|gif|webp)$/i.test(fileType) || fileType.startsWith('image/') }\n", "function isImage(fileType: string) { return /^(jpg|jpeg|png|gif|webp)$/i.test(fileType) || fileType.startsWith('image/') }\nfunction isAudio(fileType: string) { return /^(webm|ogg|mp3|m4a|wav|aac|mp4)$/i.test(fileType) || fileType.startsWith('audio/') }\n")
replace_once(chat, "  const [groupError, setGroupError] = useState('')\n", "  const [groupError, setGroupError] = useState('')\n  const [recordingVoice, setRecordingVoice] = useState(false)\n  const [recordingSeconds, setRecordingSeconds] = useState(0)\n")
replace_once(chat, "  const csrfTokenRef = useRef('')\n", "  const csrfTokenRef = useRef('')\n  const voiceRecorderRef = useRef<MediaRecorder | null>(null)\n  const voiceChunksRef = useRef<Blob[]>([])\n  const voiceTimerRef = useRef<number | null>(null)\n")
replace_once(chat, "  useEffect(() => { csrfTokenRef.current = csrfToken }, [csrfToken])\n", "  useEffect(() => { csrfTokenRef.current = csrfToken }, [csrfToken])\n  useEffect(() => () => { if (voiceTimerRef.current) window.clearInterval(voiceTimerRef.current); voiceRecorderRef.current?.stop() }, [])\n")
replace_once(chat, "    if (!/\\.(pdf|doc|docx|ppt|pptx|jpg|jpeg|png)$/i.test(file.name)) { setError('Unsupported file type.'); return }\n", "    if (!/\\.(pdf|doc|docx|ppt|pptx|jpg|jpeg|png|webm|ogg|mp3|m4a|wav|aac|mp4)$/i.test(file.name)) { setError('Unsupported file type.'); return }\n")
replace_once(chat, "  const loadEarlier = async () => {", """  const startVoiceRecording = async () => {
    if (selectedId == null || recordingVoice || uploading || sending) return
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { setError('Voice recording is not supported in this browser.'); return }
    if (!navigator.onLine) { setError('Voice notes require an internet connection.'); return }
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
  const loadEarlier = async () => {""")
replace_once(chat, "{message.attachment.view_url && isImage(message.attachment.file_type) ? <img src={message.attachment.view_url} alt={message.attachment.original_filename} style={{ maxWidth:'100%',maxHeight:260,borderRadius:10,display:'block' }} /> : <div style={{ background:mine?'rgba(255,255,255,.09)':'#f3f4f6',borderRadius:10,padding:10,color:mine?'#fff':'#202534' }}>", "{message.attachment.view_url && isImage(message.attachment.file_type) ? <img src={message.attachment.view_url} alt={message.attachment.original_filename} style={{ maxWidth:'100%',maxHeight:260,borderRadius:10,display:'block' }} /> : message.attachment.view_url && isAudio(message.attachment.file_type) ? <audio controls preload=\"metadata\" src={message.attachment.view_url} style={{ width:'min(320px,100%)',display:'block' }} /> : <div style={{ background:mine?'rgba(255,255,255,.09)':'#f3f4f6',borderRadius:10,padding:10,color:mine?'#fff':'#202534' }}>")
replace_once(chat, "<div style={{ maxWidth:900,margin:'0 auto',display:'flex',gap:7,alignItems:'flex-end' }}><button type=\"button\" className=\"prepza-wa-attach\" onClick={() => setAttachOpen(v => !v)} disabled={uploading}>", "<div style={{ maxWidth:900,margin:'0 auto',display:'flex',gap:7,alignItems:'flex-end' }}><button type=\"button\" className=\"prepza-wa-attach\" onClick={() => setAttachOpen(v => !v)} disabled={uploading || recordingVoice}>+")
# The source currently has the + button text outside the anchor above; add a permanent mic control after it.
replace_once(chat, "disabled={uploading}>+</button><button type=\"button\" onClick={openAda}", "disabled={uploading || recordingVoice}>+</button><button type=\"button\" onClick={() => void startVoiceRecording()} disabled={recordingVoice || uploading || sending} aria-label=\"Record voice note\" title=\"Record voice note\" style={{ width:40,height:40,border:0,borderRadius:12,background:recordingVoice?'#d84b4b':'#f1f2f4',color:recordingVoice?'#fff':'#5e6470',fontWeight:900,cursor:'pointer' }}>{recordingVoice ? '■' : '◉'}</button><button type=\"button\" onClick={openAda}")
replace_once(chat, "accept=\".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png\"", "accept=\".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png,.webm,.ogg,.mp3,.m4a,.wav,.aac,.mp4\"")
replace_once(chat, "{replyingTo && <div style={{ maxWidth:900,margin:'0 auto 7px',background:'#f6f1df'", "{recordingVoice && <div style={{ maxWidth:900,margin:'0 auto 7px',background:'#0b1437',color:'#fff',borderRadius:10,padding:'8px 10px',display:'flex',alignItems:'center',gap:9 }}><span style={{ width:9,height:9,borderRadius:'50%',background:'#e05252' }} /><span style={{ flex:1,fontSize:11,fontWeight:800 }}>Recording voice note · {Math.floor(recordingSeconds / 60)}:{String(recordingSeconds % 60).padStart(2,'0')}</span><button type=\"button\" onClick={stopVoiceRecording} style={{ border:0,borderRadius:9,background:'#e4c96a',color:'#0b1437',padding:'6px 10px',fontWeight:900,cursor:'pointer' }}>Stop</button></div>}{replyingTo && <div style={{ maxWidth:900,margin:'0 auto 7px',background:'#f6f1df'")

# Chat-list preview: the existing E2EE fetch bridge decrypts /messages locally.
replace_once(chat, "  const loadList = async () => { setListError(''); try { const result = await api<{ chats: ChatSummary[] }>('/chats'); setChats(Array.isArray(result.chats) ? result.chats : []) } catch (value) { setListError(friendlyError(value, 'Could not load your conversations.')) } }", "  const loadList = async () => { setListError(''); try { const result = await api<{ chats: ChatSummary[] }>('/chats'); const baseChats = Array.isArray(result.chats) ? result.chats : []; const enriched = await Promise.all(baseChats.map(async chat => { if (!chat.last_message_at) return chat; try { const latest = await api<{ messages: Message[] }>(`/chats/${chat.id}/messages`); const candidates = (latest.messages || []).filter(message => message.kind !== 'reaction'); const message = candidates[candidates.length - 1]; if (!message) return chat; if (message.attachment && isAudio(message.attachment.file_type)) return { ...chat, last_message: 'Voice message' }; const preview = displayText(message).trim(); return { ...chat, last_message: preview || (message.attachment ? 'Attachment' : chat.last_message) }; } catch { return chat } })); setChats(enriched) } catch (value) { setListError(friendlyError(value, 'Could not load your conversations.')) } }")

print('CHAT_VOICE_PATCH_APPLIED')
