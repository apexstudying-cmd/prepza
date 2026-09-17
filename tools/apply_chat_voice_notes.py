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
replace_once(
    app,
    'CHAT_ATTACHMENT_MAX_SIZE_BYTES = 20 * 1024 * 1024\n',
    'CHAT_ATTACHMENT_MAX_SIZE_BYTES = 20 * 1024 * 1024\nCHAT_AUDIO_EXTENSIONS = {"webm", "ogg", "mp3", "m4a", "wav", "aac", "mp4"}\n',
)
replace_once(
    app,
    '    ext = get_document_extension(original_filename)\n    if not ext:\n        return jsonify({"error": "Unsupported file type"}), 400\n    if not isinstance(file_size_bytes, int) or isinstance(file_size_bytes, bool) or file_size_bytes <= 0:\n',
    '    ext = get_document_extension(original_filename)\n    if not ext:\n        candidate_ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""\n        ext = candidate_ext if candidate_ext in CHAT_AUDIO_EXTENSIONS else None\n    if not ext:\n        return jsonify({"error": "Unsupported file type"}), 400\n    if not isinstance(file_size_bytes, int) or isinstance(file_size_bytes, bool) or file_size_bytes <= 0:\n',
)

# E2EE attachment bridges: preserve the real audio MIME type when the
# encrypted voice note is turned back into a local Blob URL.
for rel in (
    "frontend/src/crypto/e2eeFetchBridge.ts",
    "frontend/src/crypto/directChatE2EE.ts",
):
    path = ROOT / rel
    replace_once(
        path,
        "    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',\n  }",
        "    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',\n    webm: 'audio/webm', ogg: 'audio/ogg', mp3: 'audio/mpeg',\n    m4a: 'audio/mp4', wav: 'audio/wav', aac: 'audio/aac', mp4: 'audio/mp4',\n  }",
    )

# WhatsApp-style composer: recording, audio rendering, and chat-list previews.
chat = ROOT / "frontend/src/crypto/WhatsAppChatExperience.tsx"
replace_once(
    chat,
    "function isImage(fileType: string) { return /^(jpg|jpeg|png|gif|webp)$/i.test(fileType) || fileType.startsWith('image/') }\n",
    "function isImage(fileType: string) { return /^(jpg|jpeg|png|gif|webp)$/i.test(fileType) || fileType.startsWith('image/') }\nfunction isAudio(fileType: string) { return /^(webm|ogg|mp3|m4a|wav|aac|mp4)$/i.test(fileType) || fileType.startsWith('audio/') }\n",
)
replace_once(
    chat,
    "  const [groupError, setGroupError] = useState('')\n",
    "  const [groupError, setGroupError] = useState('')\n  const [recordingVoice, setRecordingVoice] = useState(false)\n  const [recordingSeconds, setRecordingSeconds] = useState(0)\n",
)
replace_once(
    chat,
    "  const csrfTokenRef = useRef('')\n",
    "  const csrfTokenRef = useRef('')\n  const voiceRecorderRef = useRef<MediaRecorder | null>(null)\n  const voiceChunksRef = useRef<Blob[]>([])\n  const voiceTimerRef = useRef<number | null>(null)\n",
)
replace_once(
    chat,
    "  useEffect(() => { csrfTokenRef.current = csrfToken }, [csrfToken])\n",
    "  useEffect(() => { csrfTokenRef.current = csrfToken }, [csrfToken])\n  useEffect(() => () => { if (voiceTimerRef.current) window.clearInterval(voiceTimerRef.current); voiceRecorderRef.current?.stop() }, [])\n",
)
replace_once(
    chat,
    "  const sendAttachment = async (file: File) => {\n    if (selectedId == null || uploading) return\n    if (!/\\.(pdf|doc|docx|ppt|pptx|jpg|jpeg|png)$/i.test(file.name)) { setError('Unsupported file type.'); return }\n",
    "  const sendAttachment = async (file: File) => {\n    if (selectedId == null || uploading) return\n    if (!/\\.(pdf|doc|docx|ppt|pptx|jpg|jpeg|png|webm|ogg|mp3|m4a|wav|aac|mp4)$/i.test(file.name)) { setError('Unsupported file type.'); return }\n",
)
replace_once(
    chat,
    "  const loadEarlier = async () => {",
    "  const startVoiceRecording = async () => {\n    if (selectedId == null || recordingVoice || uploading || sending) return\n    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { setError('Voice recording is not supported in this browser.'); return }\n    try {\n      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })\n      const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'].find(type => MediaRecorder.isTypeSupported(type)) || ''\n      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)\n      voiceChunksRef.current = []\n      recorder.ondataavailable = event => { if (event.data.size > 0) voiceChunksRef.current.push(event.data) }\n      recorder.onstop = () => {\n        stream.getTracks().forEach(track => track.stop())\n        const blob = new Blob(voiceChunksRef.current, { type: recorder.mimeType || 'audio/webm' })\n        voiceChunksRef.current = []\n        setRecordingVoice(false)\n        if (voiceTimerRef.current) { window.clearInterval(voiceTimerRef.current); voiceTimerRef.current = null }\n        setRecordingSeconds(0)\n        if (blob.size > 0) {\n          const extension = recorder.mimeType.includes('mp4') ? 'm4a' : recorder.mimeType.includes('ogg') ? 'ogg' : 'webm'\n          void sendAttachment(new File([blob], `voice-note-${Date.now()}.${extension}`, { type: blob.type }))\n        }\n      }\n      voiceRecorderRef.current = recorder\n      recorder.start(250)\n      setRecordingVoice(true)\n      setRecordingSeconds(0)\n      voiceTimerRef.current = window.setInterval(() => setRecordingSeconds(value => value + 1), 1000)\n    } catch { setError('Microphone access was not granted.'); setRecordingVoice(false) }\n  }\n  const stopVoiceRecording = () => {\n    if (!voiceRecorderRef.current) return\n    voiceRecorderRef.current.stop()\n    voiceRecorderRef.current = null\n  }\n  const loadEarlier = async () => {",
)
replace_once(
    chat,
    "{message.attachment.view_url && isImage(message.attachment.file_type) ? <img src={message.attachment.view_url} alt={message.attachment.original_filename} style={{ maxWidth:'100%',maxHeight:260,borderRadius:10,display:'block' }} /> : <div style={{ background:mine?'rgba(255,255,255,.09)':'#f3f4f6',borderRadius:10,padding:10,color:mine?'#fff':'#202534' }}>",
    "{message.attachment.view_url && isImage(message.attachment.file_type) ? <img src={message.attachment.view_url} alt={message.attachment.original_filename} style={{ maxWidth:'100%',maxHeight:260,borderRadius:10,display:'block' }} /> : message.attachment.view_url && isAudio(message.attachment.file_type) ? <audio controls preload=\"metadata\" src={message.attachment.view_url} style={{ width:'min(320px,100%)',display:'block' }} /> : <div style={{ background:mine?'rgba(255,255,255,.09)':'#f3f4f6',borderRadius:10,padding:10,color:mine?'#fff':'#202534' }}>",
)
replace_once(
    chat,
    "<div style={{ maxWidth:900,margin:'0 auto',display:'flex',gap:7,alignItems:'flex-end' }}><button type=\"button\" className=\"prepza-wa-attach\" onClick={() => setAttachOpen(v => !v)} disabled={uploading}>+</button>",
    "<div style={{ maxWidth:900,margin:'0 auto',display:'flex',gap:7,alignItems:'flex-end' }}><button type=\"button\" className=\"prepza-wa-attach\" onClick={() => setAttachOpen(v => !v)} disabled={uploading || recordingVoice}>+</button>",
)
replace_once(
    chat,
    "{attachOpen && <div style={{ maxWidth:900,margin:'0 auto 8px',display:'flex',gap:7 }}><button type=\"button\" onClick={() => fileRef.current?.click()} style={{ border:0,borderRadius:11,background:'#f1f2f4',padding:'9px 12px',fontSize:11,fontWeight:800,cursor:'pointer' }}>Document / image</button>",
    "{attachOpen && <div style={{ maxWidth:900,margin:'0 auto 8px',display:'flex',gap:7,flexWrap:'wrap' }}><button type=\"button\" onClick={() => fileRef.current?.click()} style={{ border:0,borderRadius:11,background:'#f1f2f4',padding:'9px 12px',fontSize:11,fontWeight:800,cursor:'pointer' }}>Document / image / audio</button><button type=\"button\" onClick={() => void startVoiceRecording()} disabled={recordingVoice || uploading} style={{ border:0,borderRadius:11,background:'#0b1437',color:'#e4c96a',padding:'9px 12px',fontSize:11,fontWeight:800,cursor:'pointer' }}>Voice note</button>",
)
replace_once(
    chat,
    "accept=\".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png\"",
    "accept=\".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png,.webm,.ogg,.mp3,.m4a,.wav,.aac,.mp4\"",
)
replace_once(
    chat,
    "{replyingTo && <div style={{ maxWidth:900,margin:'0 auto 7px',background:'#f6f1df'",
    "{recordingVoice && <div style={{ maxWidth:900,margin:'0 auto 7px',background:'#0b1437',color:'#fff',borderRadius:10,padding:'8px 10px',display:'flex',alignItems:'center',gap:9 }}><span style={{ width:9,height:9,borderRadius:'50%',background:'#e05252',boxShadow:'0 0 0 5px rgba(224,82,82,.12)' }} /><span style={{ flex:1,fontSize:11,fontWeight:800 }}>Recording voice note · {Math.floor(recordingSeconds / 60)}:{String(recordingSeconds % 60).padStart(2,'0')}</span><button type=\"button\" onClick={stopVoiceRecording} style={{ border:0,borderRadius:9,background:'#e4c96a',color:'#0b1437',padding:'6px 10px',fontWeight:900,cursor:'pointer' }}>Stop</button></div>}{replyingTo && <div style={{ maxWidth:900,margin:'0 auto 7px',background:'#f6f1df'",
)
# Preview the actual latest decrypted message instead of the server-side
# E2EE placeholder. The existing E2EE fetch bridges transparently decrypt
# /messages responses, so the server never sees plaintext.
replace_once(
    chat,
    "  const loadList = async () => { setListError(''); try { const result = await api<{ chats: ChatSummary[] }>('/chats'); setChats(Array.isArray(result.chats) ? result.chats : []) } catch (value) { setListError(friendlyError(value, 'Could not load your conversations.')) } }",
    "  const loadList = async () => { setListError(''); try { const result = await api<{ chats: ChatSummary[] }>('/chats'); const baseChats = Array.isArray(result.chats) ? result.chats : []; const enriched = await Promise.all(baseChats.map(async chat => { if (!chat.last_message_at) return chat; try { const latest = await api<{ messages: Message[] }>(`/chats/${chat.id}/messages`); const candidates = (latest.messages || []).filter(message => message.kind !== 'reaction'); const message = candidates[candidates.length - 1]; if (!message) return chat; if (message.attachment && isAudio(message.attachment.file_type)) return { ...chat, last_message: 'Voice message' }; if (message.attachment && !displayText(message)) return { ...chat, last_message: 'Attachment' }; const preview = displayText(message).trim(); return { ...chat, last_message: preview || (message.attachment ? 'Attachment' : chat.last_message) }; } catch { return chat } })); setChats(enriched) } catch (value) { setListError(friendlyError(value, 'Could not load your conversations.')) } }",
)
