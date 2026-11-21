import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from 'react'

import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Avi from '../../ui/Avi'
import type { ChatDetail, ChatMessageData } from '../../types/chat'
import { joinRealtimeChat, leaveRealtimeChat, sendReadRealtime, sendTypingRealtime } from '../../crypto/chatRealtime'

type ChatDetailRoute = 'chats' | 'chat-options' | 'student-profile'
type ChatDetailScreenProps = {
  setScreen: (screen: ChatDetailRoute) => void
  conversationId: number | null
  setActiveProfileUserId?: (id: number) => void
  setActiveProfileName?: (name: string) => void
  getFileExtension: (filename: string) => string | null
  allowedUploadExtensions: readonly string[]
  maxChatAttachmentSizeBytes: number
  loadingView: ReactNode
}

const CHAT_DRAFTS: Record<number, string> = {}
function getChatDraft(conversationId: number | null): string {
  if (conversationId == null) return ''
  if (Object.prototype.hasOwnProperty.call(CHAT_DRAFTS, conversationId)) return CHAT_DRAFTS[conversationId]
  try {
    const value = window.localStorage.getItem('prepza-chat-draft-' + conversationId) || ''
    CHAT_DRAFTS[conversationId] = value
    return value
  } catch {
    return ''
  }
}
function setChatDraft(conversationId: number, value: string) {
  CHAT_DRAFTS[conversationId] = value
  try {
    if (value) window.localStorage.setItem('prepza-chat-draft-' + conversationId, value)
    else window.localStorage.removeItem('prepza-chat-draft-' + conversationId)
  } catch {}
  window.dispatchEvent(new CustomEvent('prepza-chat-draft-changed', { detail: { conversationId } }))
}

// ─── CHAT DETAIL ──────────────────────────────────────────────────────────────

type ChatEnvelope =
  | { v: 1; type: 'text'; text: string; reply_to?: number }
  | { v: 1; type: 'reaction'; target_id: number; emoji: string; action: 'add' | 'remove' }
type ReactionState = Record<number, Record<string, Set<number>>>

const CHAT_DETAIL_CACHE: Record<number, { msgs: ChatMessageData[]; headerName: string; headerIsGroup: boolean; senderNames: Record<number, string> }> = {}

function parseChatEnvelope(body: string | null): ChatEnvelope | null {
  if (!body) return null
  try {
    const value = JSON.parse(body)
    if (value?.v === 1 && value?.type === 'text' && typeof value.text === 'string') return value
    if (value?.v === 1 && value?.type === 'reaction' && Number.isInteger(value.target_id) && typeof value.emoji === 'string' && (value.action === 'add' || value.action === 'remove')) return value
  } catch { /* legacy plain text */ }
  return null
}

function chatDisplayText(message: ChatMessageData) {
  const envelope = parseChatEnvelope(message.body)
  return envelope?.type === 'text' ? envelope.text : (message.body || '')
}

function chatReplyId(message: ChatMessageData) {
  const envelope = parseChatEnvelope(message.body)
  return envelope?.type === 'text' ? envelope.reply_to || null : null
}

function buildChatReactionState(messages: ChatMessageData[]): ReactionState {
  const state: ReactionState = {}
  for (const message of messages) {
    if (message.kind !== 'reaction') continue
    const event = parseChatEnvelope(message.body)
    if (!event || event.type !== 'reaction') continue
    const byEmoji = state[event.target_id] || (state[event.target_id] = {})
    const users = byEmoji[event.emoji] || (byEmoji[event.emoji] = new Set<number>())
    if (event.action === 'add') users.add(message.sender_id)
    else users.delete(message.sender_id)
  }
  return state
}

function chatIsImage(fileType: string) {
  return /^(jpg|jpeg|png|gif|webp)$/i.test(fileType) || fileType.startsWith('image/')
}

function chatIsAudio(fileType: string) {
  return /^(webm|ogg|mp3|m4a|wav|aac|mp4|mpeg)$/i.test(fileType) || fileType.startsWith('audio/')
}

function chatAudioMime(fileType: string) {
  const type = fileType.toLowerCase().replace(/^audio\//, '')
  return ({ webm: 'audio/webm', ogg: 'audio/ogg', mp3: 'audio/mpeg', m4a: 'audio/mp4', wav: 'audio/wav', aac: 'audio/aac', mp4: 'audio/mp4', mpeg: 'audio/mpeg' } as Record<string, string>)[type] || 'audio/*'
}

function chatTime(value: string | null) {
  return value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''
}

function ChatVoiceBubble({ src, mine, filename }: { src: string; mine: boolean; filename: string }) {
  const { tokens: T } = useTheme()
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [playing, setPlaying] = useState(false)
  const [current, setCurrent] = useState(0)
  const [duration, setDuration] = useState(0)

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    const onTime = () => setCurrent(audio.currentTime || 0)
    const onMeta = () => setDuration(Number.isFinite(audio.duration) ? audio.duration : 0)
    const onEnded = () => { setPlaying(false); setCurrent(0) }
    audio.addEventListener('timeupdate', onTime)
    audio.addEventListener('loadedmetadata', onMeta)
    audio.addEventListener('durationchange', onMeta)
    audio.addEventListener('ended', onEnded)
    return () => {
      audio.removeEventListener('timeupdate', onTime)
      audio.removeEventListener('loadedmetadata', onMeta)
      audio.removeEventListener('durationchange', onMeta)
      audio.removeEventListener('ended', onEnded)
    }
  }, [])

  const toggle = async () => {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) {
      try { await audio.play(); setPlaying(true) } catch { setPlaying(false) }
    } else {
      audio.pause()
      setPlaying(false)
    }
  }

  const seek = (event: ChangeEvent<HTMLInputElement>) => {
    const audio = audioRef.current
    if (!audio) return
    const next = Number(event.target.value)
    audio.currentTime = next
    setCurrent(next)
  }

  const formatTime = (value: number) => {
    if (!Number.isFinite(value) || value <= 0) return '0:00'
    const total = Math.floor(value)
    return Math.floor(total / 60) + ':' + String(total % 60).padStart(2, '0')
  }

  return (
    <div style={{ display:'flex', alignItems:'center', gap:9, minWidth:'min(250px,100%)', maxWidth:320, padding:'2px 1px' }}>
      <audio ref={audioRef} preload="metadata" src={src} aria-label={filename} />
      <button type="button" onClick={() => void toggle()} aria-label={playing ? 'Pause voice message' : 'Play voice message'} title={playing ? 'Pause' : 'Play'} style={{ width:40,height:40,border:0,borderRadius:'50%',background:mine?'rgba(255,255,255,.16)':N.gold,color:mine?'#fff':N.navy,cursor:'pointer',display:'flex',alignItems:'center',justifyContent:'center',flexShrink:0 }}>
        {playing ? Ic.pause('w-4 h-4') : Ic.play('w-4 h-4')}
      </button>
      <div style={{ flex:1,minWidth:0 }}>
        <div style={{ display:'flex',alignItems:'center',gap:7 }}>
          <div style={{ position:'relative',flex:1,height:28,display:'flex',alignItems:'center',gap:2,overflow:'hidden' }}>
            {Array.from({ length: 28 }, (_, index) => {
              const height = 5 + ((index * 17 + filename.length * 7) % 19)
              const progress = duration ? (current / duration) * 28 : 0
              const active = index < progress
              return <span key={index} style={{ flex:1,minWidth:2,height,background:active ? N.gold : (mine ? 'rgba(255,255,255,.32)' : T.border),borderRadius:99,transition:'background .08s' }} />
            })}
            <input type="range" min={0} max={duration || 0} step={0.1} value={Math.min(current,duration || current)} onChange={seek} disabled={!duration} aria-label="Voice message progress" style={{ position:'absolute',inset:0,width:'100%',height:'100%',opacity:0,cursor:duration?'pointer':'default' }} />
          </div>
          <span style={{ fontSize:9,opacity:.6,flexShrink:0 }}>{formatTime(playing ? current : duration)}</span>
        </div>
        <div style={{ marginTop:3,fontSize:9,opacity:.52,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap' }}>Voice message</div>
      </div>
    </div>
  )
}

export default function ChatDetailScreen({ setScreen, conversationId, setActiveProfileUserId, setActiveProfileName, getFileExtension, allowedUploadExtensions, maxChatAttachmentSizeBytes, loadingView }: ChatDetailScreenProps) {
  const { tokens: T } = useTheme()
  const [input, setInput] = useState('')
  const [msgs, setMsgs] = useState<ChatMessageData[]>(() => conversationId != null ? (CHAT_DETAIL_CACHE[conversationId]?.msgs ?? []) : [])
  const [loading, setLoading] = useState(() => conversationId == null || !CHAT_DETAIL_CACHE[conversationId])
  const [error, setError] = useState<string | null>(null)
  const [draftVersion, setDraftVersion] = useState(0)
  const [sending, setSending] = useState(false)
  const [csrfToken, setCsrfToken] = useState('')
  const [meId, setMeId] = useState<number | null>(null)
  const [callPeerId, setCallPeerId] = useState<number | null>(null)
  const [callPeerName, setCallPeerName] = useState('Student')
  const [callParticipants, setCallParticipants] = useState<ChatDetail['participants']>([])
  const [headerName, setHeaderName] = useState(() => conversationId != null ? (CHAT_DETAIL_CACHE[conversationId]?.headerName ?? 'Conversation') : 'Conversation')
  const [headerIsGroup, setHeaderIsGroup] = useState(() => conversationId != null ? (CHAT_DETAIL_CACHE[conversationId]?.headerIsGroup ?? false) : false)
  const [senderNames, setSenderNames] = useState<Record<number, string>>(() => conversationId != null ? (CHAT_DETAIL_CACHE[conversationId]?.senderNames ?? {}) : {})
  const [uploadingAttachment, setUploadingAttachment] = useState(false)
  const [attachError, setAttachError] = useState<string | null>(null)
  const [showAttach, setShowAttach] = useState(false)
  const [replyingTo, setReplyingTo] = useState<ChatMessageData | null>(null)
  const [reactionPicker, setReactionPicker] = useState<number | null>(null)
  const [messageSearchOpen, setMessageSearchOpen] = useState(false)
  const [messageSearch, setMessageSearch] = useState('')
  const [messageSearchResults, setMessageSearchResults] = useState<ChatMessageData[]>([])
  const [loadingEarlier, setLoadingEarlier] = useState(false)
  const [typingUsers, setTypingUsers] = useState<Record<number, number>>({})
  const [onlineUsers, setOnlineUsers] = useState<Set<number>>(new Set())
  const [showEmojiPicker, setShowEmojiPicker] = useState(false)
  const [recordingVoice, setRecordingVoice] = useState(false)
  const [recordingSeconds, setRecordingSeconds] = useState(0)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const cameraInputRef = useRef<HTMLInputElement>(null)
  const voiceRecorderRef = useRef<MediaRecorder | null>(null)
  const voiceChunksRef = useRef<Blob[]>([])
  const voiceTimerRef = useRef<number | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const typingTimer = useRef<number | null>(null)
  const typingTimeouts = useRef<Map<number, number>>(new Map())
  const meIdRef = useRef<number | null>(null)

  useEffect(() => () => {
    const recorder = voiceRecorderRef.current
    voiceRecorderRef.current = null
    if (recorder && recorder.state !== 'inactive') recorder.stop()
    if (voiceTimerRef.current) {
      window.clearInterval(voiceTimerRef.current)
      voiceTimerRef.current = null
    }
  }, [])

  useEffect(() => {
    meIdRef.current = meId
    if (!headerIsGroup && meId != null) {
      const peer = callParticipants.find(p => p.user_id !== meId)
      setCallPeerId(peer?.user_id ?? null)
      setCallPeerName(peer?.display_name || 'Student')
    }
  }, [meId, headerIsGroup, callParticipants])

  useEffect(() => {
    api<{ id: number; csrf_token: string }>('/me').then(me => { setCsrfToken(me.csrf_token); setMeId(me.id) }).catch(() => {})
  }, [])

  useEffect(() => {
    setInput(getChatDraft(conversationId))
    if (conversationId == null) { setLoading(false); return }
    let cancelled = false
    const cached = CHAT_DETAIL_CACHE[conversationId]
    if (cached) {
      setMsgs(cached.msgs); setHeaderName(cached.headerName); setHeaderIsGroup(cached.headerIsGroup); setSenderNames(cached.senderNames); setLoading(false)
    } else setLoading(true)
    setError(null)
    Promise.all([api<ChatDetail>(`/chats/${conversationId}`), api<{ messages: ChatMessageData[] }>(`/chats/${conversationId}/messages`)]).then(([detail, data]) => {
      if (cancelled) return
      const names: Record<number, string> = {}
      detail.participants.forEach(p => { names[p.user_id] = p.display_name })
      setHeaderName(detail.name); setHeaderIsGroup(detail.is_group); setSenderNames(names); setMsgs(data.messages || []); setOnlineUsers(new Set())
      setCallParticipants(detail.participants)
      const peer = detail.is_group ? null : detail.participants.find(p => p.user_id !== meId)
      setCallPeerId(peer?.user_id ?? null)
      setCallPeerName(peer?.display_name || 'Student')
      CHAT_DETAIL_CACHE[conversationId] = { msgs: data.messages || [], headerName: detail.name, headerIsGroup: detail.is_group, senderNames: names }
      joinRealtimeChat(conversationId); sendReadRealtime(conversationId)
    }).catch(e => { if (!cancelled) setError(e instanceof ApiError ? e.message : 'Could not load this conversation.') }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true; leaveRealtimeChat(conversationId) }
  }, [conversationId])

  useEffect(() => {
    if (conversationId == null || !csrfToken) return
    void api(`/chats/${conversationId}/read`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } }).catch(() => {})
  }, [conversationId, csrfToken])

  const getChatCsrfToken = async () => {
    if (csrfToken) return csrfToken
    const me = await api<{ id: number; csrf_token: string }>('/me')
    if (!me.csrf_token) throw new Error('Could not establish a CSRF token for this session.')
    setCsrfToken(me.csrf_token)
    setMeId(me.id)
    return me.csrf_token
  }


  useEffect(() => {
    if (conversationId == null) return
    const refresh = () => api<{ messages: ChatMessageData[] }>(`/chats/${conversationId}/messages`).then(result => {
      const next = result.messages || []
      setMsgs(next)
      const cached = CHAT_DETAIL_CACHE[conversationId]
      if (cached) cached.msgs = next
    }).catch(() => {})
    const onMessage = (event: Event) => {
      const message = (event as CustomEvent<ChatMessageData>).detail
      if (message?.conversation_id === conversationId) void refresh()
    }
    const onRead = (event: Event) => {
      const data = (event as CustomEvent<{ conversation_id?: number; user_id?: number }>).detail
      if (data?.conversation_id === conversationId && data.user_id) setMsgs(current => current.map(m => m.sender_id === meIdRef.current ? { ...m, read_by_count: Math.max(m.read_by_count || 0, 1) } : m))
    }
    const onTyping = (event: Event) => {
      const data = (event as CustomEvent<{ conversation_id?: number; user_id?: number; typing?: boolean }>).detail
      if (data?.conversation_id !== conversationId || !data.user_id || data.user_id === meIdRef.current) return
      const id = data.user_id
      if (data.typing) {
        setTypingUsers(current => ({ ...current, [id]: Date.now() }))
        const old = typingTimeouts.current.get(id); if (old) window.clearTimeout(old)
        typingTimeouts.current.set(id, window.setTimeout(() => setTypingUsers(current => { const next = { ...current }; delete next[id]; return next }), 2500))
      } else {
        const old = typingTimeouts.current.get(id); if (old) window.clearTimeout(old)
        setTypingUsers(current => { const next = { ...current }; delete next[id]; return next })
      }
    }
    const onPresence = (event: Event) => {
      const data = (event as CustomEvent<{ conversation_id?: number; user_id?: number; online?: boolean }>).detail
      if (data?.conversation_id !== conversationId || !data.user_id || data.user_id === meIdRef.current) return
      setOnlineUsers(current => { const next = new Set(current); data.online ? next.add(data.user_id!) : next.delete(data.user_id!); return next })
    }
    window.addEventListener('prepza-realtime-message', onMessage); window.addEventListener('prepza-realtime-read', onRead); window.addEventListener('prepza-realtime-typing', onTyping); window.addEventListener('prepza-realtime-presence', onPresence)
    return () => { window.removeEventListener('prepza-realtime-message', onMessage); window.removeEventListener('prepza-realtime-read', onRead); window.removeEventListener('prepza-realtime-typing', onTyping); window.removeEventListener('prepza-realtime-presence', onPresence); typingTimeouts.current.forEach(timer => window.clearTimeout(timer)); typingTimeouts.current.clear() }
  }, [conversationId])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [msgs.length])

  const reactionState = buildChatReactionState(msgs)
  const typingNames = Object.keys(typingUsers).map(id => senderNames[Number(id)] || 'Someone')
  const initials = (headerName || '??').trim().split(/\s+/).map(part => part[0]).join('').slice(0, 2).toUpperCase() || '??'

  const send = async () => {
    const text = input.trim()
    if (!text || sending || conversationId == null) return
    setSending(true); setError(null); sendTypingRealtime(conversationId, false)
    const envelope: ChatEnvelope = { v: 1, type: 'text', text, ...(replyingTo ? { reply_to: replyingTo.id } : {}) }
    try {
      const token = await getChatCsrfToken()
      await api(`/chats/${conversationId}/messages`, { method: 'POST', headers: { 'X-CSRF-Token': token }, body: JSON.stringify({ body: JSON.stringify(envelope), kind: 'text' }) })
      setInput(''); setChatDraft(conversationId, ''); setReplyingTo(null)
      const result = await api<{ messages: ChatMessageData[] }>(`/chats/${conversationId}/messages`)
      setMsgs(result.messages || []); CHAT_DETAIL_CACHE[conversationId] && (CHAT_DETAIL_CACHE[conversationId].msgs = result.messages || [])
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Could not send message.') } finally { setSending(false) }
  }

  const react = async (message: ChatMessageData, emoji: string) => {
    if (conversationId == null || sending || meId == null) return
    const current = reactionState[message.id]?.[emoji]?.has(meId) || false
    setReactionPicker(null); setSending(true); setError(null)
    const envelope: ChatEnvelope = { v: 1, type: 'reaction', target_id: message.id, emoji, action: current ? 'remove' : 'add' }
    try {
      const token = await getChatCsrfToken()
      await api(`/chats/${conversationId}/messages`, { method: 'POST', headers: { 'X-CSRF-Token': token }, body: JSON.stringify({ body: JSON.stringify(envelope), kind: 'reaction' }) })
      const result = await api<{ messages: ChatMessageData[] }>(`/chats/${conversationId}/messages`)
      setMsgs(result.messages || [])
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Could not update reaction.') } finally { setSending(false) }
  }

  const startVoiceRecording = async () => {
    if (conversationId == null || recordingVoice || sending || uploadingAttachment) return
    if (!navigator.onLine) {
      setAttachError('Voice notes require an internet connection.')
      return
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setAttachError('Voice recording is not supported in this browser.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg']
        .find(type => MediaRecorder.isTypeSupported(type)) || ''
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
      voiceChunksRef.current = []
      recorder.ondataavailable = event => {
        if (event.data.size > 0) voiceChunksRef.current.push(event.data)
      }
      recorder.onstop = () => {
        stream.getTracks().forEach(track => track.stop())
        const blob = new Blob(voiceChunksRef.current, { type: recorder.mimeType || 'audio/webm' })
        voiceChunksRef.current = []
        setRecordingVoice(false)
        if (voiceTimerRef.current) {
          window.clearInterval(voiceTimerRef.current)
          voiceTimerRef.current = null
        }
        setRecordingSeconds(0)
        if (blob.size > 0) {
          const ext = recorder.mimeType.includes('mp4') ? 'm4a' : recorder.mimeType.includes('ogg') ? 'ogg' : 'webm'
          void sendAttachment(new File([blob], `voice-note-${Date.now()}.${ext}`, { type: blob.type }))
        }
      }
      voiceRecorderRef.current = recorder
      recorder.start(250)
      setAttachError(null)
      setRecordingVoice(true)
      setRecordingSeconds(0)
      voiceTimerRef.current = window.setInterval(() => setRecordingSeconds(value => value + 1), 1000)
    } catch {
      setAttachError('Microphone access was not granted.')
      setRecordingVoice(false)
    }
  }

  const stopVoiceRecording = () => {
    const recorder = voiceRecorderRef.current
    voiceRecorderRef.current = null
    if (recorder && recorder.state !== 'inactive') recorder.stop()
  }

  const sendAttachment = async (file: File) => {
    if (conversationId == null || uploadingAttachment) return
    const ext = getFileExtension(file.name)
    const allowedChatAttachment = new Set([...allowedUploadExtensions, 'webm', 'ogg', 'mp3', 'm4a', 'wav', 'aac', 'mp4'])
    if (!ext || !allowedChatAttachment.has(ext) || file.size > maxChatAttachmentSizeBytes) { setAttachError('Unsupported file or file exceeds the 20 MB limit.'); return }
    setUploadingAttachment(true); setAttachError(null); setShowAttach(false)
    try {
      const token = await getChatCsrfToken()
      const init = await api<{ attachment_id: number; upload_url: string }>(`/chats/${conversationId}/attachments`, { method: 'POST', headers: { 'X-CSRF-Token': token }, body: JSON.stringify({ original_filename: file.name, file_size_bytes: file.size }) })
      const uploadHeaders: HeadersInit = {}
      if (file.type) uploadHeaders['Content-Type'] = file.type
      const upload = await fetch(init.upload_url, { method: 'PUT', headers: uploadHeaders, body: file })
      if (!upload.ok) throw new Error('Upload to storage failed.')
      await api(`/chats/${conversationId}/attachments/${init.attachment_id}/uploaded`, { method: 'POST', headers: { 'X-CSRF-Token': token } })
      await api(`/chats/${conversationId}/messages`, { method: 'POST', headers: { 'X-CSRF-Token': token }, body: JSON.stringify({ attachment_id: init.attachment_id, kind: 'text' }) })
      const result = await api<{ messages: ChatMessageData[] }>(`/chats/${conversationId}/messages`)
      setMsgs(result.messages || [])
    } catch (e) { setAttachError(e instanceof ApiError ? e.message : 'Could not send attachment.') } finally { setUploadingAttachment(false) }
  }

  const loadEarlier = async () => {
    if (conversationId == null || loadingEarlier || msgs.length === 0) return
    setLoadingEarlier(true)
    try {
      const result = await api<{ messages: ChatMessageData[] }>(`/chats/${conversationId}/messages?before_id=${msgs[0].id}`)
      const earlier = result.messages || []
      setMsgs(current => [...earlier, ...current.filter(message => !earlier.some(old => old.id === message.id))])
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Could not load earlier messages.') } finally { setLoadingEarlier(false) }
  }

  const runMessageSearch = async () => {
    if (conversationId == null) return
    const q = messageSearch.trim()
    if (!q) { setMessageSearchResults([]); return }
    try {
      const result = await api<{ messages: ChatMessageData[] }>(`/chats/${conversationId}/messages/search?q=${encodeURIComponent(q)}`)
      setMessageSearchResults(result.messages || [])
    } catch (e) { setError(e instanceof ApiError ? e.message : 'Could not search this chat.') }
  }

  const handleInputChange = (value: string) => {
    setInput(value)
    if (conversationId != null) setChatDraft(conversationId, value)
    if (conversationId == null) return
    sendTypingRealtime(conversationId, Boolean(value.trim()))
    if (typingTimer.current) window.clearTimeout(typingTimer.current)
    if (value.trim()) typingTimer.current = window.setTimeout(() => sendTypingRealtime(conversationId, false), 1800)
  }

  if (loading) return loadingView

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', background: T.pageBg, fontFamily: 'Plus Jakarta Sans' }}>
      <div style={{ background: N.navy, padding: '8px 10px', color: '#fff', boxShadow: '0 2px 10px rgba(0,0,0,0.12)', zIndex: 2 }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', minHeight: 52 }}>
          <button type="button" onClick={() => setScreen('chats')} aria-label="Back to chats" style={{ width: 40, height: 40, background: 'transparent', border: 0, borderRadius: 999, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', flexShrink: 0 }}>{Ic.back('w-6 h-6')}</button>
          <button type="button" onClick={() => {
            if (headerIsGroup) {
              setScreen('chat-options')
              return
            }
            // Use the participant map as the source of truth as well as callPeerId.
            // A cached conversation can render before the call-peer effect has
            // repopulated its state; the contact header must still open the
            // contact profile immediately, like a normal messaging app.
            const cachedPeerId = meId != null
              ? Object.keys(senderNames).map(Number).find(id => id !== meId)
              : null
            const peerId = callPeerId ?? cachedPeerId
            if (peerId != null) {
              setActiveProfileUserId?.(peerId)
              setActiveProfileName?.(senderNames[peerId] || callPeerName || headerName)
              setScreen('student-profile')
            } else {
              setScreen('chat-options')
            }
          }} aria-label={headerIsGroup ? 'Open chat info' : 'Open contact profile'} style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 10, background: 'transparent', border: 0, padding: 0, color: '#fff', textAlign: 'left', cursor: 'pointer' }}>
            <div style={{ position: 'relative', flexShrink: 0 }}>
              <Avi name={initials} size={42} />
              {!headerIsGroup && onlineUsers.size > 0 && <span style={{ position: 'absolute', right: -1, bottom: -1, width: 10, height: 10, borderRadius: '50%', background: '#46c46b', border: '2px solid ' + N.navy }} />}
            </div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontWeight: 800, fontSize: 15, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{headerName}</div>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.58)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {headerIsGroup ? `${Object.keys(senderNames).length || 0} members` : typingNames.length ? `${typingNames.join(', ')} ${typingNames.length === 1 ? 'is' : 'are'} typing…` : (onlineUsers.size ? 'online' : 'last seen recently')}
              </div>
            </div>
          </button>
          {!headerIsGroup && callPeerId != null && meId != null && <div style={{ display: 'flex', gap: 2, flexShrink: 0 }}>
            <button type="button" onClick={() => window.dispatchEvent(new CustomEvent('prepza-start-call', { detail: { conversationId, peerId: callPeerId, peerName: callPeerName, kind: 'voice' } }))} aria-label="Start voice call" title="Voice call" style={{ width: 42, height: 42, background: 'transparent', border: 0, borderRadius: 999, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff' }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M22 16.92v3a2 2 0 0 1-2.18 2A19.8 19.8 0 0 1 3.1 5.18 2 2 0 0 1 5.1 3h3a2 2 0 0 1 2 1.72c.12.9.33 1.77.62 2.61a2 2 0 0 1-.45 2.11L9 10.71a16 16 0 0 0 4.29 4.29l1.27-1.27a2 2 0 0 1 2.11.45c.84.29 1.71.5 2.61.62A2 2 0 0 1 22 16.92Z"/></svg>
            </button>
            <button type="button" onClick={() => window.dispatchEvent(new CustomEvent('prepza-start-call', { detail: { conversationId, peerId: callPeerId, peerName: callPeerName, kind: 'video' } }))} aria-label="Start video call" title="Video call" style={{ width: 42, height: 42, background: 'transparent', border: 0, borderRadius: 999, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff' }}>
              <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m16 13 5 3V8l-5 3Z"/><rect x="3" y="6" width="13" height="12" rx="2"/></svg>
            </button>
          </div>}
          <button type="button" onClick={() => setScreen('chat-options')} aria-label="Chat options" style={{ width: 40, height: 40, background: 'transparent', border: 0, borderRadius: 999, color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{Ic.dots('w-5 h-5')}</button>
        </div>
      </div>

      {messageSearchResults.length > 0 && <div style={{ maxHeight: 150, overflowY: 'auto', background: T.card, borderBottom: `1px solid ${T.border}`, padding: 8 }}>{messageSearchResults.map(result => <button key={result.id} onClick={() => { setMessageSearchResults([]); document.getElementById(`prepza-msg-${result.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }} style={{ display: 'block', width: '100%', textAlign: 'left', border: 'none', background: 'transparent', padding: 7, cursor: 'pointer', color: T.text, fontSize: 11 }}>{chatDisplayText(result)}</button>)}</div>}

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px 12px 12px', display: 'flex', flexDirection: 'column', gap: 4, background: `linear-gradient(180deg, ${T.pageBg}, ${T.card})` }} className="scrollbar-hide">
        {error && <div style={{ alignSelf: 'center', maxWidth: 320, textAlign: 'center', color: '#C94C4C', fontSize: 11, padding: '5px 9px' }}>{error}</div>}
        {msgs.length > 0 && <button type="button" onClick={() => void loadEarlier()} disabled={loadingEarlier} style={{ alignSelf: 'center', margin: '0 auto 8px', border: `1px solid ${T.border}`, background: T.card, borderRadius: 10, padding: '7px 11px', color: T.textMuted, fontSize: 10, fontWeight: 800, cursor: 'pointer' }}>{loadingEarlier ? 'Loading…' : 'Load earlier messages'}</button>}
        {msgs.filter(message => message.kind !== 'reaction').map(message => {
          const mine = message.sender_id === meId
          const text = chatDisplayText(message)
          const reply = chatReplyId(message)
          const quoted = reply ? msgs.find(item => item.id === reply) : null
          const reactions = reactionState[message.id] || {}
          const isLastFromSender = true
          return (
            <div key={message.id} id={`prepza-msg-${message.id}`} style={{ display: 'flex', flexDirection: 'column', alignItems: mine ? 'flex-end' : 'flex-start', position: 'relative', marginBottom: 3 }}>
              {headerIsGroup && !mine && <div style={{ fontSize: 10, color: N.gold, fontWeight: 800, margin: '0 10px 2px' }}>{senderNames[message.sender_id] || 'Student'}</div>}
              {reactionPicker === message.id && <div style={{ display: 'flex', gap: 2, padding: 4, borderRadius: 11, background: T.card, boxShadow: '0 5px 18px rgba(0,0,0,0.14)', marginBottom: 3, zIndex: 3 }}>{['👍','❤️','😂','😮','😢','🙏'].map(emoji => <button key={emoji} type="button" onClick={() => void react(message, emoji)} style={{ border: 0, background: 'transparent', fontSize: 18, cursor: 'pointer', padding: 3 }}>{emoji}</button>)}</div>}
              <div style={{ maxWidth: '82%', position: 'relative', background: mine ? N.navy : T.card, color: mine ? '#fff' : T.text, borderRadius: mine ? '15px 4px 15px 15px' : '4px 15px 15px 15px', padding: '8px 10px 6px', boxShadow: '0 1px 3px rgba(0,0,0,0.08)', border: mine ? 'none' : `1px solid ${T.border}` }}>
                <div style={{ position: 'absolute', top: 3, right: 4, display: 'flex', gap: 3 }}><button type="button" onClick={() => setReplyingTo(message)} title="Reply" aria-label="Reply to message" style={{ border: 0, background: 'transparent', color: mine ? 'rgba(255,255,255,.45)' : T.textMuted, cursor: 'pointer', width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 17 4 12l5-5"/><path d="M4 12h9a7 7 0 0 1 7 7v1"/></svg></button><button type="button" onClick={() => setReactionPicker(reactionPicker === message.id ? null : message.id)} title="React" aria-label="React to message" style={{ border: 0, background: 'transparent', color: mine ? 'rgba(255,255,255,.45)' : T.textMuted, cursor: 'pointer', width: 24, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="8"/><path d="M8.5 10h.01M15.5 10h.01"/><path d="M8.5 14c1.2 1.2 5.8 1.2 7 0"/></svg></button></div>
                {quoted && <button onClick={() => document.getElementById(`prepza-msg-${quoted.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })} style={{ width: '100%', textAlign: 'left', border: 0, borderLeft: `3px solid ${N.gold}`, background: mine ? 'rgba(255,255,255,.08)' : T.pageBg, color: mine ? 'rgba(255,255,255,.82)' : T.textMuted, padding: '5px 7px', borderRadius: 6, marginBottom: 6, cursor: 'pointer', fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{chatDisplayText(quoted)}</button>}
                {message.attachment && (message.attachment.view_url && chatIsAudio(message.attachment.file_type)
                  ? <ChatVoiceBubble src={message.attachment.view_url} mine={mine} filename={message.attachment.original_filename} />
                  : <a href={message.attachment.view_url || undefined} target="_blank" rel="noreferrer" style={{ display: 'block', textDecoration: 'none', marginBottom: text ? 6 : 0 }}>
                      {message.attachment.view_url && chatIsImage(message.attachment.file_type)
                        ? <img src={message.attachment.view_url} alt={message.attachment.original_filename} style={{ maxWidth: '100%', maxHeight: 260, borderRadius: 9, display: 'block' }} />
                        : <div style={{ background: mine ? 'rgba(255,255,255,.09)' : T.pageBg, borderRadius: 9, padding: 9, color: mine ? '#fff' : T.text }}>
                            <div style={{ fontSize: 12, fontWeight: 800, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{message.attachment.original_filename}</div>
                            <div style={{ fontSize: 10, opacity: .55, marginTop: 3 }}>{(message.attachment.file_size_bytes / 1048576).toFixed(1)} MB · tap to open</div>
                          </div>}
                    </a>)}
                {message.is_deleted ? <i style={{ opacity: .55, fontSize: 12 }}>This message was deleted</i> : text && <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.5, paddingRight: 24 }}>{text}</div>}
                <div style={{ marginTop: 4, textAlign: 'right', fontSize: 9, opacity: .48 }}>{chatTime(message.created_at)} {mine && <span title={message.read_by_all ? 'Read by everyone' : message.read_by_count ? `Read by ${message.read_by_count}` : 'Sent'}>{message.read_by_count ? '✓✓' : '✓'}</span>}</div>
                {Object.entries(reactions).filter(([, users]) => users.size > 0).length > 0 && <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>{Object.entries(reactions).filter(([, users]) => users.size > 0).map(([emoji, users]) => <button key={emoji} onClick={() => void react(message, emoji)} style={{ border: `1px solid ${T.border}`, background: T.card, color: T.text, borderRadius: 12, padding: '2px 7px', fontSize: 11, cursor: 'pointer' }}>{emoji} {users.size}</button>)}</div>}
              </div>
            </div>
          )
        })}
        {Object.keys(typingUsers).length > 0 && <div style={{ alignSelf: 'flex-start', color: T.textMuted, fontSize: 10, padding: '4px 8px', fontStyle: 'italic' }}>{typingNames.join(', ')} {typingNames.length === 1 ? 'is' : 'are'} typing…</div>}
        <div ref={bottomRef} />
      </div>

      <div style={{ padding: '7px 10px max(10px, env(safe-area-inset-bottom))', background: T.pageBg, borderTop: `1px solid ${T.border}`, position: 'relative' }}>
        {replyingTo && <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 9px', marginBottom: 7, borderLeft: `3px solid ${N.gold}`, background: T.card, borderRadius: 8 }}><div style={{ flex: 1, minWidth: 0 }}><div style={{ fontSize: 10, color: N.gold, fontWeight: 800 }}>Replying to {senderNames[replyingTo.sender_id] || (replyingTo.sender_id === meId ? 'yourself' : 'student')}</div><div style={{ fontSize: 11, color: T.textMuted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{chatDisplayText(replyingTo)}</div></div><button type="button" onClick={() => setReplyingTo(null)} style={{ border: 0, background: 'transparent', color: T.textMuted, cursor: 'pointer', fontSize: 16 }}>×</button></div>}
        {(attachError || uploadingAttachment) && <div style={{ color: attachError ? '#C94C4C' : T.textMuted, fontSize: 11, fontWeight: 600, marginBottom: 7, textAlign: 'center' }}>{attachError || 'Sending attachment…'}</div>}
        {showEmojiPicker && <div style={{ position: 'absolute', bottom: '100%', left: 10, right: 10, background: T.card, border: `1px solid ${T.border}`, borderRadius: 16, boxShadow: '0 -8px 28px rgba(0,0,0,.18)', padding: 10, zIndex: 5 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8,1fr)', gap: 4 }}>
            {['😀','😂','🤣','😊','😍','🥹','😎','😭','😅','😉','🙂','🙃','😏','😢','😮','😡','❤️','👍','🙏','🔥','🎉','💯','✨','🤝','👏','💀','🙌','🤔','😴','🥲','❤️‍🔥'].map(emoji => <button type="button" key={emoji} onClick={() => { setInput(value => value + emoji); setShowEmojiPicker(false) }} style={{ border: 0, background: 'transparent', borderRadius: 9, padding: 7, fontSize: 21, cursor: 'pointer' }}>{emoji}</button>)}
          </div>
        </div>}
        <input ref={fileInputRef} type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png,.webm,.ogg,.mp3,.m4a,.wav,.aac,.mp4" style={{ display: 'none' }} onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; if (file) void sendAttachment(file) }} />
        <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" style={{ display: 'none' }} onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; if (file) void sendAttachment(file) }} />
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 5, background: T.card, border: `1px solid ${T.border}`, borderRadius: 22, padding: '3px 6px 3px 10px', minHeight: 42 }}>
            <button type="button" onClick={() => setShowEmojiPicker(v => !v)} aria-label="Emoji" style={{ width: 34, height: 34, border: 0, background: 'transparent', color: T.textMuted, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M8.5 10h.01M15.5 10h.01"/><path d="M8.5 14.2c1.2 1.4 5.8 1.4 7 0"/></svg>
            </button>
            <input value={input} onChange={e => handleInputChange(e.target.value)} onFocus={() => setShowEmojiPicker(false)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }} placeholder={replyingTo ? 'Write a reply…' : 'Message'} style={{ flex: 1, minWidth: 0, border: 0, outline: 0, background: 'transparent', color: T.text, fontSize: 14, fontFamily: 'Plus Jakarta Sans' }} disabled={sending || uploadingAttachment || recordingVoice} />
            <button type="button" onClick={() => setShowAttach(v => !v)} disabled={uploadingAttachment || recordingVoice} aria-label="Attach file" style={{ width: 32, height: 34, border: 0, background: 'transparent', color: T.textMuted, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              {Ic.attach('w-5 h-5')}
            </button>
            <button type="button" onClick={() => cameraInputRef.current?.click()} disabled={uploadingAttachment || recordingVoice} aria-label="Camera" style={{ width: 32, height: 34, border: 0, background: 'transparent', color: T.textMuted, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 7h3l1.5-2h7L17 7h3a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Z"/><circle cx="12" cy="13" r="3.5"/></svg>
            </button>
          </div>
          <button type="button" onClick={() => input.trim() ? void send() : (recordingVoice ? stopVoiceRecording() : void startVoiceRecording())} disabled={sending || uploadingAttachment} aria-label={input.trim() ? 'Send' : (recordingVoice ? 'Stop recording voice note' : 'Record voice note')} style={{ width: 48, height: 48, border: 0, borderRadius: 999, background: recordingVoice ? '#C94C4C' : N.gold, color: N.navy, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, boxShadow: '0 3px 10px rgba(0,0,0,.18)' }}>
            {input.trim() ? Ic.send('w-5 h-5') : recordingVoice ? <span style={{ fontSize: 11, fontWeight: 900 }}>{recordingSeconds}s</span> : <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/></svg>}
          </button>
        </div>
        {showAttach && <div style={{ position: 'absolute', bottom: '100%', left: 10, right: 10, background: T.card, borderRadius: 15, boxShadow: '0 -5px 24px rgba(0,0,0,.12)', padding: 13, border: `1px solid ${T.border}`, zIndex: 4 }}>
          <div style={{ fontSize: 12, fontWeight: 800, color: T.text, marginBottom: 10 }}>Share with this chat</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 8 }}>
            <button type="button" onClick={() => fileInputRef.current?.click()} style={{ border: 0, background: T.pageBg, borderRadius: 11, padding: 11, color: T.text, fontWeight: 700, cursor: 'pointer' }}>{Ic.book('w-5 h-5')}<span style={{ marginLeft: 7 }}>Document / image</span></button>
            <button type="button" onClick={() => setShowAttach(false)} style={{ border: 0, background: T.pageBg, borderRadius: 11, padding: 11, color: T.textMuted, fontWeight: 700, cursor: 'pointer' }}>Cancel</button>
          </div>
        </div>}
      </div>

    </div>
  )
}
