import { enqueueOfflineChatMessage } from '../offline/chatOfflineQueue'
import { getCachedChatMessages, cacheChatMessages } from '../offline/chatMessageCache'

import { useEffect, useMemo, useRef, useState } from 'react'
import { joinRealtimeChat, leaveRealtimeChat, sendReadRealtime, sendTypingRealtime } from './chatRealtime'
import { ensureE2EEIdentityReady, fetchUserPublicKey, uploadGroupKeyEnvelopes } from './e2eeChatApi'
import { provisionInitialGroupKey } from './groupProvisioning'
import CallExperience from './CallExperience'

type ChatSummary = { id: number; is_group: boolean; name: string; last_message: string | null; last_message_at: string | null; unread_count: number; status?: string }
type Attachment = { id: number; file_type: string; original_filename: string; file_size_bytes: number; view_url: string | null }
type Message = { id: number; conversation_id: number; sender_id: number; body: string | null; nonce?: string | null; is_deleted: boolean; created_at: string | null; edited_at: string | null; attachment: Attachment | null; kind?: 'text' | 'reaction'; read_by_count?: number; read_by_all?: boolean }
type Participant = { user_id: number; display_name: string; role: string }
type Detail = { id: number; is_group: boolean; name: string; created_by: number; member_count: number; participants: Participant[]; viewer_muted?: boolean }
type ChatEnvelope = { v: 1; type: 'text'; text: string; reply_to?: number } | { v: 1; type: 'reaction'; target_id: number; emoji: string; action: 'add' | 'remove' }
type ReactionState = Record<number, Record<string, Set<number>>>
type GroupPickerUser = { id: number; display_name: string }

let observerInstalled = false
let observedMode: 'list' | 'detail' | null = null
let observedConversationId: number | null = null
let observedAt = 0
let suppressObserverUntil = 0
const internalFetches = new Map<string, number>()

function pathOf(input: RequestInfo | URL): string { const raw = typeof input === 'string' ? input : input instanceof URL ? input.pathname + input.search : input.url; try { return new URL(raw, window.location.origin).pathname } catch { return raw.split('?')[0] } }
function markInternal(path: string, delta: number) { const count = internalFetches.get(path) || 0; if (delta > 0) internalFetches.set(path, count + delta); else if (count <= 1) internalFetches.delete(path); else internalFetches.set(path, count - 1) }
function installConversationObserver() {
  if (observerInstalled || typeof window === 'undefined' || !window.fetch) return
  observerInstalled = true
  const original = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const path = pathOf(input)
    if ((internalFetches.get(path) || 0) > 0) return original(input, init)
    if (Date.now() >= suppressObserverUntil) {
      const detail = path.match(/^\/chats\/(\d+)(?:\/(?:messages|read))?$/)
      if (path === '/chats') { observedMode = 'list'; observedConversationId = null; observedAt = Date.now() }
      else if (detail) { observedMode = 'detail'; observedConversationId = Number(detail[1]); observedAt = Date.now() }
    }
    return original(input, init)
  }
}
installConversationObserver()

function friendlyError(value: unknown, fallback: string) { const message = value instanceof Error ? value.message : ''; if (/peer encryption key|secure conversation|public key|nonce|e2ee|encrypted/i.test(message)) return 'Secure messaging is temporarily unavailable. Please try again.'; if (/authentication|required|unauthorized|forbidden|401|403/i.test(message)) return 'Your session has expired. Please sign in again.'; if (/network|failed to fetch|request failed/i.test(message)) return 'Connection problem. Please try again.'; return message && message.length <= 140 ? message : fallback }
async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  markInternal(pathOf(path), 1)
  try { const response = await fetch(path, { credentials: 'include', ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } }); let body: any = null; try { body = await response.json() } catch { /* empty */ }; if (!response.ok) throw new Error(body?.error || `Request failed (${response.status})`); return body as T }
  finally { markInternal(pathOf(path), -1) }
}
function initials(name: string) { return (name || '??').trim().split(/\s+/).map(part => part[0]).join('').slice(0, 2).toUpperCase() || '??' }
function timeLabel(value: string | null) { return value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '' }
function listTime(value: string | null) { if (!value) return ''; const date = new Date(value); const now = new Date(); return date.toDateString() === now.toDateString() ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : date.toLocaleDateString([], { day: 'numeric', month: 'short' }) }
function parseEnvelope(body: string | null): ChatEnvelope | null { if (!body) return null; try { const value = JSON.parse(body); if (value?.v === 1 && value?.type === 'text' && typeof value.text === 'string') return value; if (value?.v === 1 && value?.type === 'reaction' && Number.isInteger(value.target_id) && typeof value.emoji === 'string' && (value.action === 'add' || value.action === 'remove')) return value } catch { /* legacy plain-text message */ } return null }
function displayText(message: Message) { const envelope = parseEnvelope(message.body); return envelope?.type === 'text' ? envelope.text : (message.body || '') }
function replyId(message: Message) { const envelope = parseEnvelope(message.body); return envelope?.type === 'text' ? envelope.reply_to || null : null }
function buildReactionState(messages: Message[]) { const state: ReactionState = {}; for (const message of messages) { if (message.kind !== 'reaction') continue; const event = parseEnvelope(message.body); if (!event || event.type !== 'reaction') continue; const byEmoji = state[event.target_id] || (state[event.target_id] = {}); const users = byEmoji[event.emoji] || (byEmoji[event.emoji] = new Set<number>()); if (event.action === 'add') users.add(message.sender_id); else users.delete(message.sender_id) } return state }
function isImage(fileType: string) { return /^(jpg|jpeg|png|gif|webp)$/i.test(fileType) || fileType.startsWith('image/') }
function isAudio(fileType: string) { return /^(webm|ogg|mp3|m4a|wav|aac|mp4)$/i.test(fileType) || fileType.startsWith('audio/') }

export default function WhatsAppChatExperience() {
  const [visible, setVisible] = useState(false)
  const [view, setView] = useState<'list' | 'detail'>('list')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [chats, setChats] = useState<ChatSummary[]>([])
  const [detail, setDetail] = useState<Detail | null>(null)
  const [meId, setMeId] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [search, setSearch] = useState('')
  const [messageSearch, setMessageSearch] = useState('')
  const [messageSearchOpen, setMessageSearchOpen] = useState(false)
  const [messageSearchResults, setMessageSearchResults] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [replyingTo, setReplyingTo] = useState<Message | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingEarlier, setLoadingEarlier] = useState(false)
  const [sending, setSending] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [listError, setListError] = useState('')
  const [realtimeConnected, setRealtimeConnected] = useState(false)
  const [typingUsers, setTypingUsers] = useState<Record<number, number>>({})
  const [onlineUsers, setOnlineUsers] = useState<Set<number>>(new Set())
  const [attachOpen, setAttachOpen] = useState(false)
  const [reactionPicker, setReactionPicker] = useState<number | null>(null)
  const [csrfToken, setCsrfToken] = useState('')
  const [showListSearch, setShowListSearch] = useState(false)
  const [showGroupCreator, setShowGroupCreator] = useState(false)
  const [groupName, setGroupName] = useState('')
  const [groupSearch, setGroupSearch] = useState('')
  const [groupUsers, setGroupUsers] = useState<GroupPickerUser[]>([])
  const [groupSelected, setGroupSelected] = useState<GroupPickerUser[]>([])
  const [groupCreating, setGroupCreating] = useState(false)
  const [groupError, setGroupError] = useState('')
  const [showNewChat, setShowNewChat] = useState(false)
  const [newChatSearch, setNewChatSearch] = useState('')
  const [newChatUsers, setNewChatUsers] = useState<GroupPickerUser[]>([])
  const [newChatCreating, setNewChatCreating] = useState(false)
  const [newChatError, setNewChatError] = useState('')
  const [recordingVoice, setRecordingVoice] = useState(false)
  const [recordingSeconds, setRecordingSeconds] = useState(0)
  const fileRef = useRef<HTMLInputElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const typingTimer = useRef<number | null>(null)
  const typingTimeouts = useRef<Map<number, number>>(new Map())
  const meIdRef = useRef<number | null>(null)
  const csrfTokenRef = useRef('')
  const voiceRecorderRef = useRef<MediaRecorder | null>(null)
  const voiceChunksRef = useRef<Blob[]>([])
  const voiceTimerRef = useRef<number | null>(null)
  useEffect(() => { meIdRef.current = meId }, [meId])
  useEffect(() => { csrfTokenRef.current = csrfToken }, [csrfToken])

  const getCsrfToken = async (): Promise<string> => {
    if (csrfTokenRef.current) return csrfTokenRef.current
    const me = await api<{ id: number; csrf_token: string }>('/me')
    if (!me?.csrf_token) throw new Error('CSRF token is unavailable; please refresh the session')
    csrfTokenRef.current = me.csrf_token
    setMeId(me.id)
    setCsrfToken(me.csrf_token)
    return me.csrf_token
  }
  useEffect(() => { const onStatus = (event: Event) => setRealtimeConnected(Boolean((event as CustomEvent<{ connected?: boolean }>).detail?.connected)); window.addEventListener('prepza-realtime-status', onStatus); return () => window.removeEventListener('prepza-realtime-status', onStatus) }, [])
  useEffect(() => { const timer = window.setInterval(() => { if (Date.now() - observedAt > 10000 || Date.now() < suppressObserverUntil) return; if (observedMode === 'detail' && observedConversationId && selectedId !== observedConversationId) { setSelectedId(observedConversationId); setView('detail'); setVisible(true) } else if (observedMode === 'list' && !visible) { setView('list'); setSelectedId(null); setVisible(true) } }, 150); return () => window.clearInterval(timer) }, [selectedId, visible])

  const loadList = async () => { setListError(''); try { const result = await api<{ chats: ChatSummary[] }>('/chats'); setChats(Array.isArray(result.chats) ? result.chats : []) } catch (value) { setListError(friendlyError(value, 'Could not load your conversations.')) } }
  useEffect(() => { if (!visible) return; void loadList(); void getCsrfToken().catch(() => {}) }, [visible])

  useEffect(() => {
    if (!visible || view !== 'detail' || selectedId == null) return
    let cancelled = false
    setLoading(true); setError(''); setMessageSearchResults([])
    let cacheLoaded = false
    void getCachedChatMessages(selectedId).then(cached => {
      if (cancelled || !cached) return
      cacheLoaded = true
      setMessages(cached as Message[])
      setLoading(false)
    })
    Promise.all([
      api<Detail>(`/chats/${selectedId}`),
      api<{ messages: Message[] }>(`/chats/${selectedId}/messages`),
    ]).then(([nextDetail, nextMessages]) => {
      if (cancelled) return
      setDetail(nextDetail)
      setMessages(nextMessages.messages || [])
      void cacheChatMessages(selectedId, nextMessages.messages || [])
      setOnlineUsers(new Set())
      joinRealtimeChat(selectedId)
      sendReadRealtime(selectedId)
    }).catch(value => {
      if (!cancelled && !cacheLoaded) setError(friendlyError(value, 'Could not load this conversation.'))
    }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true; leaveRealtimeChat(selectedId) }
  }, [visible, view, selectedId])

  useEffect(() => {
    if (!visible || view !== 'detail' || selectedId == null || !csrfToken) return
    void api(`/chats/${selectedId}/read`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } }).catch(() => {})
  }, [visible, view, selectedId, csrfToken])

  useEffect(() => {
    if (!visible || view !== 'detail' || selectedId == null) return
    const refresh = () => api<{ messages: Message[] }>(`/chats/${selectedId}/messages`).then(result => { setMessages(result.messages || []); void cacheChatMessages(selectedId, result.messages || []) }).catch(() => {})
    const onMessage = (event: Event) => { const message = (event as CustomEvent<Message>).detail; if (message?.conversation_id === selectedId) void refresh() }
    const onRead = (event: Event) => { const data = (event as CustomEvent<{ conversation_id?: number; user_id?: number }>).detail; if (data?.conversation_id === selectedId && data.user_id) setMessages(current => current.map(m => m.sender_id === meIdRef.current ? { ...m, read_by_count: Math.max(m.read_by_count || 0, 1) } : m)) }
    const onTyping = (event: Event) => { const data = (event as CustomEvent<{ conversation_id?: number; user_id?: number; typing?: boolean }>).detail; if (data?.conversation_id !== selectedId || !data.user_id || data.user_id === meIdRef.current) return; const id = data.user_id; if (data.typing) { setTypingUsers(current => ({ ...current, [id]: Date.now() })); const old = typingTimeouts.current.get(id); if (old) window.clearTimeout(old); typingTimeouts.current.set(id, window.setTimeout(() => setTypingUsers(current => { const next = { ...current }; delete next[id]; return next }), 2500)) } else { const old = typingTimeouts.current.get(id); if (old) window.clearTimeout(old); setTypingUsers(current => { const next = { ...current }; delete next[id]; return next }) } }
    const onPresence = (event: Event) => { const data = (event as CustomEvent<{ conversation_id?: number; user_id?: number; online?: boolean }>).detail; if (data?.conversation_id !== selectedId || !data.user_id || data.user_id === meIdRef.current) return; setOnlineUsers(current => { const next = new Set(current); data.online ? next.add(data.user_id!) : next.delete(data.user_id!); return next }) }
    const onOfflineSync = () => {
      void refresh()
      void loadList()
    }
    window.addEventListener('prepza-realtime-message', onMessage); window.addEventListener('prepza-realtime-read', onRead); window.addEventListener('prepza-realtime-typing', onTyping); window.addEventListener('prepza-realtime-presence', onPresence); window.addEventListener('prepza:offline-chat-synced', onOfflineSync)
    return () => { window.removeEventListener('prepza-realtime-message', onMessage); window.removeEventListener('prepza-realtime-read', onRead); window.removeEventListener('prepza-realtime-typing', onTyping); window.removeEventListener('prepza-realtime-presence', onPresence); window.removeEventListener('prepza:offline-chat-synced', onOfflineSync); typingTimeouts.current.forEach(timer => window.clearTimeout(timer)); typingTimeouts.current.clear() }
  }, [visible, view, selectedId])

  useEffect(() => { if (view === 'detail' && messages.length) bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages.length, view])
  const filteredChats = useMemo(() => { const needle = search.trim().toLowerCase(); return chats.filter(chat => !needle || chat.name.toLowerCase().includes(needle)) }, [chats, search])
  const reactionState = useMemo(() => buildReactionState(messages), [messages])
  const typingNames = Object.keys(typingUsers).map(id => detail?.participants.find(p => p.user_id === Number(id))?.display_name || 'Someone')
  const headerName = detail?.name || 'Conversation'
  const isGroup = Boolean(detail?.is_group)
  const closeExperience = () => { suppressObserverUntil = Date.now() + 2500; if (selectedId != null) leaveRealtimeChat(selectedId); setVisible(false); setView('list'); setSelectedId(null); setDetail(null); setMessages([]); setTypingUsers({}); setReactionPicker(null) }
  const chooseChat = (id: number) => { setSelectedId(id); setView('detail'); setVisible(true); setMessageSearchOpen(false); setMessageSearch('') }
  const backToList = () => { if (selectedId != null) leaveRealtimeChat(selectedId); setView('list'); setSelectedId(null); setDetail(null); setMessages([]); setReactionPicker(null); void loadList() }

  useEffect(() => {
    if (!showGroupCreator) return
    const needle = groupSearch.trim()
    if (needle.length < 2) { setGroupUsers([]); return }
    let cancelled = false
    const timer = window.setTimeout(() => {
      fetch(`/users/search?q=${encodeURIComponent(needle)}`, { credentials: 'include' })
        .then(async response => {
          const body = await response.json().catch(() => ({}))
          if (!response.ok) throw new Error(body?.error || 'Could not search students')
          return body
        })
        .then(body => { if (!cancelled) setGroupUsers(Array.isArray(body?.users) ? body.users : Array.isArray(body?.results) ? body.results : []) })
        .catch(() => { if (!cancelled) setGroupUsers([]) })
    }, 220)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [showGroupCreator, groupSearch])

  const openGroupCreator = () => {
    setGroupName('')
    setGroupSearch('')
    setGroupUsers([])
    setGroupSelected([])
    setGroupError('')
    setShowGroupCreator(true)
  }

  const toggleGroupUser = (user: GroupPickerUser) => {
    setGroupSelected(current => current.some(item => item.id === user.id)
      ? current.filter(item => item.id !== user.id)
      : current.length >= 99 ? current : [...current, user])
  }

  useEffect(() => {
    if (!showNewChat) return
    const needle = newChatSearch.trim()
    if (needle.length < 2) { setNewChatUsers([]); return }
    let cancelled = false
    const timer = window.setTimeout(() => {
      fetch(`/users/search?q=${encodeURIComponent(needle)}`, { credentials:'include' })
        .then(async response => { const body = await response.json().catch(() => ({})); if (!response.ok) throw new Error(body?.error || 'Could not search students'); return body })
        .then(body => { if (!cancelled) setNewChatUsers(Array.isArray(body?.users) ? body.users : Array.isArray(body?.results) ? body.results : []) })
        .catch(() => { if (!cancelled) setNewChatUsers([]) })
    }, 220)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [showNewChat, newChatSearch])

  const openNewChat = () => { setNewChatSearch(''); setNewChatUsers([]); setNewChatError(''); setShowNewChat(true) }
  const createDirectChat = async (user: GroupPickerUser) => {
    if (newChatCreating) return
    setNewChatCreating(true); setNewChatError('')
    try {
      const token = await getCsrfToken()
      await ensureE2EEIdentityReady()
      const created = await api<{ id:number }>(`/chats`, { method:'POST', headers:{'X-CSRF-Token':token}, body:JSON.stringify({ is_group:false, participant_ids:[user.id] }) })
      if (!created?.id) throw new Error('The chat could not be created')
      setShowNewChat(false); await loadList(); chooseChat(created.id)
    } catch (value) { setNewChatError(friendlyError(value, 'Could not start this secure chat.')) }
    finally { setNewChatCreating(false) }
  }

  const createChatGroup = async () => {
    const name = groupName.trim()
    if (!name) { setGroupError('Give the group a name.'); return }
    if (groupSelected.length < 2) { setGroupError('Select at least 2 other students for a group chat.'); return }
    if (groupCreating) return

    setGroupCreating(true)
    setGroupError('')
    try {
      const token = await getCsrfToken()
      await ensureE2EEIdentityReady()
      if (!meIdRef.current) throw new Error('Your secure chat identity is unavailable')

      const creatorId = meIdRef.current
      const memberIds = [creatorId, ...groupSelected.map(user => user.id)]
      const memberKeys = await Promise.all(memberIds.map(async id => ({ userId: id, publicKey: await fetchUserPublicKey(id) })))

      const created = await api<{ id: number }>(`/chats`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': token },
        body: JSON.stringify({ is_group: true, participant_ids: groupSelected.map(user => user.id), name }),
      })
      if (!created?.id) throw new Error('The group could not be created')

      await provisionInitialGroupKey(
        created.id,
        1,
        creatorId,
        memberKeys,
        (conversationId, envelopes) => uploadGroupKeyEnvelopes(conversationId, token, envelopes),
      )

      setShowGroupCreator(false)
      await loadList()
      chooseChat(created.id)
    } catch (value) {
      setGroupError(friendlyError(value, 'Could not create this group. Make sure everyone has secure chat enabled and try again.'))
    } finally {
      setGroupCreating(false)
    }
  }

  const startVoiceRecording = async () => {
    if (selectedId == null || recordingVoice || uploading || sending) return
    if (!navigator.onLine) { setError('Voice notes require an internet connection.'); return }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { setError('Voice recording is not supported in this browser.'); return }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = ['audio/webm;codecs=opus','audio/webm','audio/mp4','audio/ogg'].find(type => MediaRecorder.isTypeSupported(type)) || ''
      const recorder = mimeType ? new MediaRecorder(stream,{mimeType}) : new MediaRecorder(stream)
      voiceChunksRef.current=[]
      recorder.ondataavailable=e=>{if(e.data.size>0)voiceChunksRef.current.push(e.data)}
      recorder.onstop=()=>{
        stream.getTracks().forEach(t=>t.stop())
        const blob=new Blob(voiceChunksRef.current,{type:recorder.mimeType||'audio/webm'})
        voiceChunksRef.current=[]
        setRecordingVoice(false)
        if(voiceTimerRef.current){window.clearInterval(voiceTimerRef.current);voiceTimerRef.current=null}
        setRecordingSeconds(0)
        if(blob.size>0){const ext=recorder.mimeType.includes('mp4')?'m4a':recorder.mimeType.includes('ogg')?'ogg':'webm';void sendAttachment(new File([blob],`voice-note-${Date.now()}.${ext}`,{type:blob.type}))}
      }
      voiceRecorderRef.current=recorder
      recorder.start(250);setRecordingVoice(true);setRecordingSeconds(0)
      voiceTimerRef.current=window.setInterval(()=>setRecordingSeconds(v=>v+1),1000)
    }catch{setError('Microphone access was not granted.');setRecordingVoice(false)}
  }
  const stopVoiceRecording=()=>{const r=voiceRecorderRef.current;voiceRecorderRef.current=null;if(r&&r.state!=='inactive')r.stop()}
  const send = async () => {
    const text = input.trim(); if (!text || sending || selectedId == null) return
    setSending(true); setError(''); sendTypingRealtime(selectedId, false)
    const envelope: ChatEnvelope = { v: 1, type: 'text', text, ...(replyingTo ? { reply_to: replyingTo.id } : {}) }
    const clientMessageId = crypto.randomUUID()
    const requestBody = JSON.stringify({ body: JSON.stringify(envelope), kind: 'text', client_message_id: clientMessageId })
    try { const token = await getCsrfToken(); await api(`/chats/${selectedId}/messages`, { method: 'POST', headers: { 'X-CSRF-Token': token }, body: requestBody }); setInput(''); setReplyingTo(null); const result = await api<{ messages: Message[] }>(`/chats/${selectedId}/messages`); setMessages(result.messages || []); void loadList() } catch (value) {
      if (!navigator.onLine) {
        const queued = await enqueueOfflineChatMessage(`/chats/${selectedId}/messages`, requestBody, csrfToken)
        if (queued) { setInput(''); setReplyingTo(null); setError('Message saved. It will send when you reconnect.') }
        else setError('Could not save this message for offline sending. Your offline message queue may be full.')
      } else setError(friendlyError(value, 'Could not send this message.'))
    } finally { setSending(false) }
  }
  const react = async (message: Message, emoji: string) => {
    if (selectedId == null || sending) return
    const current = reactionState[message.id]?.[emoji]?.has(meId || -1) || false
    setReactionPicker(null); setSending(true); setError('')
    const envelope: ChatEnvelope = { v: 1, type: 'reaction', target_id: message.id, emoji, action: current ? 'remove' : 'add' }
    try { const token = await getCsrfToken(); await api(`/chats/${selectedId}/messages`, { method: 'POST', headers: { 'X-CSRF-Token': token }, body: JSON.stringify({ body: JSON.stringify(envelope), kind: 'reaction' }) }); const result = await api<{ messages: Message[] }>(`/chats/${selectedId}/messages`); setMessages(result.messages || []); void loadList() } catch (value) { setError(friendlyError(value, 'Could not update reaction.')) } finally { setSending(false) }
  }
  const sendAttachment = async (file: File) => {
    if (selectedId == null || uploading) return
    if (!/\.(pdf|doc|docx|ppt|pptx|jpg|jpeg|png|webm|ogg|mp3|m4a|wav|aac)$/i.test(file.name)) { setError('Unsupported file type.'); return }
    if (file.size > 20 * 1024 * 1024) { setError('That file is too large. The limit is 20 MB.'); return }
    setUploading(true); setError(''); setAttachOpen(false)
    try { const token = await getCsrfToken(); const init = await api<{ attachment_id: number; upload_url: string }>(`/chats/${selectedId}/attachments`, { method: 'POST', headers: { 'X-CSRF-Token': token }, body: JSON.stringify({ original_filename: file.name, file_size_bytes: file.size }) }); const upload = await fetch(init.upload_url, { method: 'PUT', body: file }); if (!upload.ok) throw new Error('Upload failed'); await api(`/chats/${selectedId}/attachments/${init.attachment_id}/uploaded`, { method: 'POST', headers: { 'X-CSRF-Token': token } }); await api(`/chats/${selectedId}/messages`, { method: 'POST', headers: { 'X-CSRF-Token': token }, body: JSON.stringify({ attachment_id: init.attachment_id, kind: 'text' }) }); const result = await api<{ messages: Message[] }>(`/chats/${selectedId}/messages`); setMessages(result.messages || []); void loadList() } catch (value) { setError(friendlyError(value, 'Could not send this attachment.')) } finally { setUploading(false) }
  }
  const loadEarlier = async () => { if (selectedId == null || loadingEarlier || messages.length === 0) return; const firstId = messages[0].id; setLoadingEarlier(true); try { const result = await api<{ messages: Message[] }>(`/chats/${selectedId}/messages?before_id=${firstId}`); const earlier = result.messages || []; setMessages(current => { const merged = [...earlier, ...current.filter(message => !earlier.some(old => old.id === message.id))]; void cacheChatMessages(selectedId, merged); return merged }) } catch (value) { setError(friendlyError(value, 'Could not load earlier messages.')) } finally { setLoadingEarlier(false) } }
  const runMessageSearch = async () => { if (selectedId == null) return; const q = messageSearch.trim(); if (!q) { setMessageSearchResults([]); return }; try { const result = await api<{ messages: Message[] }>(`/chats/${selectedId}/messages/search?q=${encodeURIComponent(q)}`); setMessageSearchResults(result.messages || []) } catch (value) { setError(friendlyError(value, 'Could not search this chat.')) } }
  const openAda = () => window.dispatchEvent(new CustomEvent('prepza-open-ada', { detail: { conversationId: selectedId } }))
  if (!visible) return null

  return <div className="prepza-wa-shell"><style>{`.prepza-wa-shell{position:fixed;inset:0;z-index:1000;background:#eef0f3;font-family:Plus Jakarta Sans,sans-serif;display:flex;align-items:stretch;justify-content:center}.prepza-wa-window{width:100%;height:100%;display:grid;grid-template-columns:340px minmax(0,1fr);background:#fff;overflow:hidden}.prepza-wa-list{border-right:1px solid #e2e5ea;background:#fff;display:flex;flex-direction:column;min-width:0}.prepza-wa-list-head{background:#0b1437;color:#fff;padding:14px;display:flex;align-items:center;gap:9px}.prepza-wa-search{margin:10px 12px;background:#f3f4f6;border:1px solid #e5e7eb;border-radius:12px;padding:9px 11px;display:flex;gap:8px;align-items:center}.prepza-wa-search input{border:0;outline:0;background:transparent;width:100%;font:inherit;font-size:12px}.prepza-wa-row{display:flex;gap:10px;align-items:center;padding:11px 13px;border-bottom:1px solid #f0f1f3;cursor:pointer}.prepza-wa-row:hover{background:#fafafa}.prepza-wa-main{min-width:0;flex:1;display:flex;flex-direction:column;background:#f5f6f7}.prepza-wa-head{height:66px;flex-shrink:0;background:#0b1437;color:#fff;display:flex;align-items:center;gap:10px;padding:0 14px}.prepza-wa-messages{flex:1;min-height:0;overflow-y:auto;padding:18px max(12px,calc((100vw - 1120px)/2)) 14px;background:linear-gradient(180deg,#eef0f3,#f8f8f7)}.prepza-wa-composer{flex-shrink:0;background:#fff;border-top:1px solid #e1e4e8;padding:9px max(10px,calc((100vw - 1120px)/2)) 12px}.prepza-wa-bubble{position:relative;max-width:min(72%,620px);padding:9px 11px 7px;border-radius:15px;margin-bottom:8px;box-shadow:0 2px 7px rgba(0,0,0,.07)}.prepza-wa-actions{position:absolute;top:-28px;right:0;display:flex;gap:4px;opacity:0;pointer-events:none;transition:opacity .15s}.prepza-wa-wrap:hover .prepza-wa-actions{opacity:1;pointer-events:auto}.prepza-wa-action{border:1px solid #ddd;background:#fff;border-radius:9px;padding:5px 7px;font-size:11px;cursor:pointer;box-shadow:0 2px 7px rgba(0,0,0,.08)}.prepza-wa-reactions{display:flex;gap:4px;flex-wrap:wrap;margin-top:5px}.prepza-wa-reaction{border:1px solid #ddd;background:#fff7db;border-radius:12px;padding:2px 7px;font-size:11px;cursor:pointer}.prepza-wa-attach{border:0;background:#f1f2f4;border-radius:12px;padding:0 11px;height:40px;cursor:pointer;font-weight:800;color:#5e6470}@media(max-width:760px){.prepza-wa-shell{display:block}.prepza-wa-window{display:block}.prepza-wa-list{height:100%;border-right:0}.prepza-wa-main{height:100%}.prepza-wa-window.detail-mode .prepza-wa-list{display:none}.prepza-wa-window.list-mode .prepza-wa-main{display:none}.prepza-wa-bubble{max-width:84%}.prepza-wa-actions{opacity:1;pointer-events:auto;position:static;margin-bottom:3px;justify-content:flex-end}.prepza-wa-head{height:62px}.prepza-wa-messages{padding-left:9px;padding-right:9px}}`}</style>
    {showNewChat && <div role="dialog" aria-modal="true" aria-label="Start secure chat" style={{position:'fixed',inset:0,zIndex:1150,background:'rgba(3,7,18,.72)',display:'flex',alignItems:'center',justifyContent:'center',padding:16}}><div style={{width:'min(480px,100%)',maxHeight:'90vh',display:'flex',flexDirection:'column',background:'#fff',borderRadius:22,overflow:'hidden',boxShadow:'0 24px 70px rgba(0,0,0,.35)'}}><div style={{background:'#0b1437',color:'#fff',padding:18,display:'flex',alignItems:'center',gap:12}}><button type="button" onClick={() => setShowNewChat(false)} disabled={newChatCreating} aria-label="Close new chat" style={{width:36,height:36,border:0,borderRadius:11,background:'rgba(255,255,255,.1)',color:'#fff',fontSize:22}}>‹</button><div><div style={{fontSize:17,fontWeight:850}}>New secure chat</div><div style={{fontSize:11,opacity:.62,marginTop:3}}>Search a student to start a private conversation.</div></div></div><div style={{padding:18,overflowY:'auto',flex:1}}><input value={newChatSearch} onChange={event => setNewChatSearch(event.target.value)} autoFocus placeholder="Search students by name" style={{width:'100%',boxSizing:'border-box',height:46,border:'1px solid #dfe3e8',borderRadius:12,padding:'0 13px',outline:0,font:'inherit',fontSize:13}} /><div style={{marginTop:12}}>{newChatSearch.trim().length < 2 && <div style={{padding:28,textAlign:'center',color:'#8b919b',fontSize:12}}>Type at least 2 characters to find students.</div>}{newChatSearch.trim().length >= 2 && !newChatUsers.length && <div style={{padding:28,textAlign:'center',color:'#8b919b',fontSize:12}}>No students found.</div>}{newChatUsers.map(user => <button key={user.id} type="button" onClick={() => void createDirectChat(user)} disabled={newChatCreating} style={{width:'100%',display:'flex',alignItems:'center',gap:11,border:0,borderBottom:'1px solid #f0f1f3',background:'#fff',padding:'11px 4px',textAlign:'left'}}><span style={{width:40,height:40,borderRadius:13,background:'linear-gradient(135deg,#c9a84c,#e4c96a)',color:'#0b1437',display:'grid',placeItems:'center',fontWeight:900}}>{initials(user.display_name)}</span><span style={{flex:1,fontSize:13,fontWeight:750}}>{user.display_name}</span><span style={{fontSize:10,color:'#737985'}}>{newChatCreating ? 'Opening…' : 'Chat'}</span></button>)}</div>{newChatError && <div style={{marginTop:14,padding:11,borderRadius:12,background:'#fff1ef',color:'#a33a35',fontSize:11}}>{newChatError}</div>}</div></div></div>}
    {showGroupCreator && <div role="dialog" aria-modal="true" aria-label="Create group chat" style={{ position:'fixed',inset:0,zIndex:1100,background:'rgba(3,7,18,.72)',backdropFilter:'blur(8px)',display:'flex',alignItems:'center',justifyContent:'center',padding:16 }}>
      <div style={{ width:'min(520px,100%)',maxHeight:'min(760px,92vh)',display:'flex',flexDirection:'column',background:'#fff',borderRadius:22,overflow:'hidden',boxShadow:'0 24px 70px rgba(0,0,0,.35)' }}>
        <div style={{ background:'#0b1437',color:'#fff',padding:'18px 18px 16px',display:'flex',alignItems:'center',gap:12 }}>
          <button type="button" onClick={() => setShowGroupCreator(false)} disabled={groupCreating} aria-label="Close group creator" style={{ width:36,height:36,border:0,borderRadius:11,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer',fontSize:22 }}>‹</button>
          <div style={{ flex:1 }}><div style={{ fontSize:17,fontWeight:850 }}>New study group</div><div style={{ marginTop:3,fontSize:11,opacity:.62 }}>The same Prepza chat, with multiple students.</div></div>
        </div>
        <div style={{ padding:18,overflowY:'auto',flex:1 }}>
          <label style={{ display:'block',fontSize:11,fontWeight:800,color:'#606672',marginBottom:7 }}>GROUP NAME</label>
          <input value={groupName} onChange={event => setGroupName(event.target.value)} maxLength={100} placeholder="e.g. Actuarial CAT revision" autoFocus style={{ width:'100%',boxSizing:'border-box',height:46,border:'1px solid #dfe3e8',borderRadius:12,padding:'0 13px',outline:'none',font:'inherit',fontSize:13 }} />
          <div style={{ marginTop:18,display:'flex',gap:8,alignItems:'center' }}>
            <input value={groupSearch} onChange={event => setGroupSearch(event.target.value)} placeholder="Search students by name" style={{ flex:1,height:42,border:'1px solid #dfe3e8',borderRadius:12,padding:'0 12px',outline:'none',font:'inherit',fontSize:12 }} />
          </div>
          {groupSelected.length > 0 && <div style={{ display:'flex',gap:7,flexWrap:'wrap',marginTop:12 }}>{groupSelected.map(user => <button key={user.id} type="button" onClick={() => toggleGroupUser(user)} style={{ border:0,borderRadius:99,background:'#0b1437',color:'#fff',padding:'7px 10px',fontSize:11,cursor:'pointer' }}>{user.display_name} ×</button>)}</div>}
          <div style={{ marginTop:12 }}>
            {groupSearch.trim().length < 2 && <div style={{ padding:'24px 10px',textAlign:'center',color:'#8b919b',fontSize:12 }}>Search for classmates to add.</div>}
            {groupSearch.trim().length >= 2 && !groupUsers.length && <div style={{ padding:'24px 10px',textAlign:'center',color:'#8b919b',fontSize:12 }}>No students found.</div>}
            {groupUsers.map(user => { const selected = groupSelected.some(item => item.id === user.id); return <button key={user.id} type="button" onClick={() => toggleGroupUser(user)} style={{ width:'100%',display:'flex',alignItems:'center',gap:11,border:0,borderBottom:'1px solid #f0f1f3',background:selected ? '#f5f2e8' : '#fff',padding:'11px 4px',textAlign:'left',cursor:'pointer' }}><span style={{ width:40,height:40,borderRadius:13,background:'linear-gradient(135deg,#c9a84c,#e4c96a)',color:'#0b1437',display:'flex',alignItems:'center',justifyContent:'center',fontWeight:900 }}>{initials(user.display_name)}</span><span style={{ flex:1,fontSize:13,fontWeight:750,color:'#20242b' }}>{user.display_name}</span><span style={{ width:22,height:22,borderRadius:'50%',border:selected ? '0' : '1px solid #cfd4da',background:selected ? '#0b1437' : '#fff',color:'#e4c96a',display:'flex',alignItems:'center',justifyContent:'center',fontSize:13 }}>{selected ? '✓' : ''}</span></button> })}
          </div>
          {groupError && <div style={{ marginTop:14,padding:11,borderRadius:12,background:'#fff1ef',color:'#a33a35',fontSize:11 }}>{groupError}</div>}
        </div>
        <div style={{ padding:'12px 18px 16px',borderTop:'1px solid #eceef1',display:'flex',gap:9 }}>
          <button type="button" onClick={() => setShowGroupCreator(false)} disabled={groupCreating} style={{ flex:1,height:44,border:'1px solid #dfe3e8',background:'#fff',borderRadius:12,fontWeight:800,cursor:'pointer' }}>Cancel</button>
          <button type="button" onClick={() => void createChatGroup()} disabled={groupCreating || groupSelected.length < 2 || !groupName.trim()} style={{ flex:1,height:44,border:0,background:'#0b1437',color:'#e4c96a',borderRadius:12,fontWeight:850,cursor:'pointer',opacity:(groupCreating || groupSelected.length < 2 || !groupName.trim()) ? .5 : 1 }}>{groupCreating ? 'Creating…' : `Create group${groupSelected.length ? ` · ${groupSelected.length + 1}` : ''}`}</button>
        </div>
      </div>
    </div>}
    <div className={`prepza-wa-window ${view === 'detail' ? 'detail-mode' : 'list-mode'}`}>
      <aside className="prepza-wa-list">
        <div className="prepza-wa-list-head"><button type="button" onClick={closeExperience} aria-label="Close chats" style={{ width:34,height:34,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer',fontSize:20 }}>‹</button><div style={{ flex:1,fontWeight:850,fontSize:18 }}>Chats</div><button type="button" onClick={() => setShowListSearch(v => !v)} aria-label="Search chats" style={{ width:34,height:34,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer' }}>⌕</button><button type="button" onClick={openNewChat} aria-label="New chat" title="Start a secure chat" style={{width:34,height:34,border:0,borderRadius:10,background:'rgba(201,168,76,.16)',color:'#e4c96a',cursor:'pointer',fontSize:18}}>＋</button><button type="button" onClick={openGroupCreator} aria-label="New group" title="Create a group chat" style={{ width:34,height:34,border:0,borderRadius:10,background:'rgba(201,168,76,.16)',color:'#e4c96a',cursor:'pointer',fontSize:20 }}>+</button></div>
        {showListSearch && <div className="prepza-wa-search"><span style={{ color:'#8a909b' }}>⌕</span><input value={search} onChange={event => setSearch(event.target.value)} autoFocus placeholder="Search conversations" /></div>}
        {listError && <div style={{ margin:10,padding:10,borderRadius:10,background:'#fff3f1',color:'#a33a35',fontSize:11 }}>{listError}</div>}
        <div style={{ flex:1,overflowY:'auto' }}>
          <div className="prepza-wa-row" onClick={() => window.dispatchEvent(new CustomEvent('prepza-open-ada'))} style={{ background:'#0b1437',color:'#fff',margin:'10px 10px 6px',borderRadius:13,border:0 }}><div style={{ width:44,height:44,borderRadius:13,background:'rgba(201,168,76,.18)',display:'flex',alignItems:'center',justifyContent:'center',color:'#e4c96a',fontWeight:900 }}>A</div><div style={{ flex:1,minWidth:0 }}><div style={{ fontWeight:850,fontSize:13 }}>Ada</div><div style={{ fontSize:11,opacity:.55 }}>Your study assistant</div></div><span style={{ fontSize:10,color:'#e4c96a' }}>AI</span></div>
          {filteredChats.map(chat => <div key={chat.id} className="prepza-wa-row" onClick={() => chooseChat(chat.id)}><div style={{ position:'relative' }}><div style={{ width:46,height:46,borderRadius:14,background:'linear-gradient(135deg,#c9a84c,#e4c96a)',color:'#0b1437',display:'flex',alignItems:'center',justifyContent:'center',fontWeight:900 }}>{initials(chat.name)}</div>{chat.is_group && <span style={{ position:'absolute',right:-2,bottom:-2,width:15,height:15,borderRadius:'50%',background:'#0b1437',color:'#e4c96a',fontSize:8,display:'flex',alignItems:'center',justifyContent:'center',border:'2px solid #fff' }}>G</span>}</div><div style={{ flex:1,minWidth:0 }}><div style={{ display:'flex',justifyContent:'space-between',gap:8 }}><span style={{ fontWeight:750,fontSize:13,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap' }}>{chat.name}</span><span style={{ fontSize:10,color:'#9096a0',flexShrink:0 }}>{listTime(chat.last_message_at)}</span></div><div style={{ fontSize:11,color:'#737985',marginTop:3,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap' }}>{chat.last_message || 'No messages yet'}</div></div>{chat.unread_count > 0 && <span style={{ minWidth:21,height:21,padding:'0 5px',borderRadius:99,background:'#c9a84c',color:'#0b1437',display:'flex',alignItems:'center',justifyContent:'center',fontSize:9,fontWeight:900 }}>{chat.unread_count > 99 ? '99+' : chat.unread_count}</span>}</div>)}
          {!filteredChats.length && <div style={{ padding:50, textAlign:'center',color:'#858b96',fontSize:12 }}>No conversations found.</div>}
        </div>
      </aside>
      <section className="prepza-wa-main">
        {view === 'detail' && <><header className="prepza-wa-head"><button type="button" onClick={backToList} aria-label="Back to conversations" style={{ width:36,height:36,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer',fontSize:21 }}>‹</button><div style={{ width:42,height:42,borderRadius:14,background:'linear-gradient(135deg,#c9a84c,#e4c96a)',color:'#0b1437',display:'flex',alignItems:'center',justifyContent:'center',fontWeight:900 }}>{initials(headerName)}</div><div style={{ flex:1,minWidth:0 }}><div style={{ fontWeight:850,fontSize:14,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap' }}>{headerName}</div><div style={{ fontSize:10,opacity:.6 }}>{isGroup ? `${detail?.member_count || 0} members` : typingNames.length ? `${typingNames.join(', ')} ${typingNames.length === 1 ? 'is' : 'are'} typing…` : (onlineUsers.size ? 'online' : (realtimeConnected ? 'connected' : 'offline'))}</div></div><div title="End-to-end encrypted" style={{ fontSize:10,opacity:.65 }}>E2EE</div><button type="button" onClick={openAda} aria-label="Study with Ada" style={{ border:'1px solid rgba(201,168,76,.45)',background:'rgba(201,168,76,.12)',color:'#e4c96a',borderRadius:11,padding:'8px 10px',fontWeight:900,fontSize:11,cursor:'pointer' }}>@Ada</button><button type="button" onClick={() => setMessageSearchOpen(v => !v)} aria-label="Search messages" style={{ width:34,height:34,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer' }}>⌕</button>{view === 'detail' && detail && !detail.is_group && (() => { const peer = detail.participants.find(item => item.user_id !== meId); return peer ? <div className="prepza-call-actions" style={{ marginLeft:7,display:'flex',gap:7,flexShrink:0 }}><button type="button" aria-label="Start voice call" title="Voice call" onClick={() => window.dispatchEvent(new CustomEvent('prepza-start-call',{detail:{conversationId:detail.id,peerId:peer.user_id,peerName:peer.display_name,kind:'voice'}}))} style={{width:34,height:34,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer',fontSize:16}}>☎</button><button type="button" aria-label="Start video call" title="Video call" onClick={() => window.dispatchEvent(new CustomEvent('prepza-start-call',{detail:{conversationId:detail.id,peerId:peer.user_id,peerName:peer.display_name,kind:'video'}}))} style={{width:34,height:34,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer',fontSize:16}}>▣</button></div> : null })()}</header>
          {messageSearchOpen && <div style={{ background:'#fff',borderBottom:'1px solid #e1e4e8',padding:'8px 12px',display:'flex',gap:8 }}><input value={messageSearch} onChange={event => setMessageSearch(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') void runMessageSearch() }} autoFocus placeholder="Search this chat" style={{ flex:1,border:'1px solid #e2e5ea',borderRadius:10,padding:'9px 11px',outline:0 }} /><button type="button" onClick={() => void runMessageSearch()} style={{ border:0,borderRadius:10,background:'#0b1437',color:'#e4c96a',padding:'0 12px',fontWeight:800 }}>Search</button></div>}
          {messageSearchResults.length > 0 && <div style={{ maxHeight:160,overflowY:'auto',background:'#fff',borderBottom:'1px solid #e1e4e8',padding:8 }}>{messageSearchResults.map(result => <button key={result.id} type="button" onClick={() => { setMessageSearchResults([]); setMessageSearchOpen(false); document.getElementById(`prepza-msg-${result.id}`)?.scrollIntoView({ behavior:'smooth',block:'center' }) }} style={{ display:'block',width:'100%',textAlign:'left',border:0,background:'transparent',padding:'7px',cursor:'pointer',fontSize:11,color:'#303541' }}>{displayText(result)}</button>)}</div>}
          <main className="prepza-wa-messages">
            {loading && <div style={{ textAlign:'center',padding:28,color:'#7b8190',fontSize:12 }}>Loading secure chat…</div>}
            {!loading && messages.length > 0 && <button type="button" onClick={() => void loadEarlier()} disabled={loadingEarlier} style={{ display:'block',margin:'0 auto 14px',border:'1px solid #dfe2e7',background:'#fff',borderRadius:10,padding:'7px 11px',fontSize:10,fontWeight:800,color:'#626874',cursor:'pointer' }}>{loadingEarlier ? 'Loading…' : 'Load earlier messages'}</button>}
            {!loading && messages.length === 0 && <div style={{ textAlign:'center',padding:'60px 20px',color:'#858b96',fontSize:12 }}>No messages yet. Start studying together.</div>}
            {messages.filter(message => message.kind !== 'reaction').map(message => { const mine = message.sender_id === meId; const text = displayText(message); const reply = replyId(message); const quoted = reply ? messages.find(item => item.id === reply) : null; const reactions = reactionState[message.id] || {}; return <div key={message.id} id={`prepza-msg-${message.id}`} className="prepza-wa-wrap" style={{ display:'flex',flexDirection:'column',alignItems:mine?'flex-end':'flex-start',position:'relative' }}><div className="prepza-wa-actions"><button type="button" className="prepza-wa-action" onClick={() => setReplyingTo(message)}>Reply</button><button type="button" className="prepza-wa-action" onClick={() => setReactionPicker(reactionPicker === message.id ? null : message.id)}>React</button></div>{isGroup && !mine && <div style={{ fontSize:10,color:'#8a6b20',fontWeight:850,margin:'0 10px 3px' }}>{detail?.participants.find(p => p.user_id === message.sender_id)?.display_name || 'Student'}</div>}{reactionPicker === message.id && <div style={{ display:'flex',gap:3,padding:4,borderRadius:10,background:'#fff',boxShadow:'0 5px 18px rgba(0,0,0,.12)',marginBottom:4 }}>{['👍','❤️','😂','😮','😢','🙏'].map(emoji => <button type="button" key={emoji} onClick={() => void react(message,emoji)} style={{ border:0,background:'transparent',fontSize:18,cursor:'pointer',padding:3 }}>{emoji}</button>)}</div>}<div className="prepza-wa-bubble" style={{ background:mine?'#0b1437':'#fff',color:mine?'#fff':'#202534',borderRadius:mine?'15px 4px 15px 15px':'4px 15px 15px 15px' }}>{quoted && <div onClick={() => document.getElementById(`prepza-msg-${quoted.id}`)?.scrollIntoView({ behavior:'smooth',block:'center' })} style={{ borderLeft:'3px solid #c9a84c',background:mine?'rgba(255,255,255,.08)':'#f4f5f7',padding:'6px 8px',borderRadius:7,marginBottom:7,cursor:'pointer',fontSize:10,opacity:.82,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap' }}>{displayText(quoted)}</div>}{message.attachment && <a href={message.attachment.view_url || undefined} target="_blank" rel="noreferrer" style={{ display:'block',textDecoration:'none',marginBottom:text?7:0 }}>{localStorage.getItem('prepza-chat-media-visibility') !== 'off' && message.attachment.view_url && isImage(message.attachment.file_type) ? <img src={message.attachment.view_url} alt={message.attachment.original_filename} style={{ maxWidth:'100%',maxHeight:260,borderRadius:10,display:'block' }} /> : message.attachment.view_url && isAudio(message.attachment.file_type) ? <audio controls preload="metadata" src={message.attachment.view_url} style={{width:'min(320px,100%)',display:'block'}} /> : <div style={{ background:mine?'rgba(255,255,255,.09)':'#f3f4f6',borderRadius:10,padding:10,color:mine?'#fff':'#202534' }}><div style={{ fontSize:12,fontWeight:850,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap' }}>{message.attachment.original_filename}</div><div style={{ fontSize:10,opacity:.55,marginTop:3 }}>{(message.attachment.file_size_bytes / 1048576).toFixed(1)} MB · tap to study</div></div>}</a>}{message.is_deleted ? <i style={{ opacity:.55,fontSize:12 }}>This message was deleted</i> : text && <div style={{ whiteSpace:'pre-wrap',fontSize:13,lineHeight:1.5 }}>{text}</div>}<div style={{ marginTop:4,textAlign:'right',fontSize:9,opacity:.48 }}>{timeLabel(message.created_at)} {mine && <span title={message.read_by_all ? 'Read by everyone' : message.read_by_count ? `Read by ${message.read_by_count}` : 'Sent'}>{message.read_by_count ? '✓✓' : '✓'}</span>}</div>{Object.keys(reactions).filter(emoji => reactions[emoji].size > 0).length > 0 && <div className="prepza-wa-reactions">{Object.entries(reactions).filter(([,users]) => users.size > 0).map(([emoji,users]) => <button key={emoji} type="button" className="prepza-wa-reaction" onClick={() => void react(message,emoji)}>{emoji} {users.size}</button>)}</div>}</div></div> })}
            <div ref={bottomRef} />
          </main>
          <footer className="prepza-wa-composer">
            {replyingTo && <div style={{ maxWidth:900,margin:'0 auto 7px',background:'#f6f1df',borderLeft:'3px solid #c9a84c',borderRadius:9,padding:'7px 9px',display:'flex',gap:8,alignItems:'center' }}><div style={{ flex:1,minWidth:0,fontSize:10,color:'#555b66',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap' }}>Replying to: {displayText(replyingTo)}</div><button type="button" onClick={() => setReplyingTo(null)} style={{ border:0,background:'transparent',cursor:'pointer',fontWeight:900 }}>×</button></div>}
            {error && <div style={{ maxWidth:900,margin:'0 auto 7px',background:'#fff3f1',color:'#a33a35',borderRadius:9,padding:'7px 10px',fontSize:10 }}>{error}</div>}
            {attachOpen && <div style={{ maxWidth:900,margin:'0 auto 8px',display:'flex',gap:7 }}><button type="button" onClick={() => fileRef.current?.click()} style={{ border:0,borderRadius:11,background:'#f1f2f4',padding:'9px 12px',fontSize:11,fontWeight:800,cursor:'pointer' }}>Document / image</button><button type="button" onClick={() => setAttachOpen(false)} style={{ border:0,borderRadius:11,background:'#f1f2f4',padding:'9px 12px',fontSize:11,fontWeight:800,cursor:'pointer' }}>Cancel</button></div>}
            <input ref={fileRef} type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png" style={{ display:'none' }} onChange={event => { const file = event.target.files?.[0]; event.target.value=''; if (file) void sendAttachment(file) }} />
            <div style={{ maxWidth:900,margin:'0 auto',display:'flex',gap:7,alignItems:'flex-end' }}><button type="button" className="prepza-wa-attach" onClick={() => setAttachOpen(v => !v)} disabled={uploading || recordingVoice}>+</button><button type="button" onClick={() => recordingVoice ? stopVoiceRecording() : void startVoiceRecording()} disabled={uploading || sending} aria-label={recordingVoice ? 'Stop recording voice note' : 'Record voice note'} title={recordingVoice ? 'Stop recording' : 'Record voice note'} style={{height:40,minWidth:40,border:'1px solid #e4e6ea',borderRadius:12,background:recordingVoice?'#fff0f0':'#fff',color:recordingVoice?'#b42318':'#202534',cursor:'pointer',display:'flex',alignItems:'center',justifyContent:'center'}}>{recordingVoice ? <span style={{fontSize:11,fontWeight:800}}>{recordingSeconds}s</span> : <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/></svg>}</button><button type="button" onClick={openAda} style={{ height:40,border:'1px solid #dcc67d',borderRadius:12,background:'#fff9e9',color:'#72570e',padding:'0 11px',fontWeight:900,fontSize:11,cursor:'pointer' }}>@Ada</button><div style={{ flex:1,background:'#f3f4f6',border:'1px solid #e4e6ea',borderRadius:14,padding:'0 11px' }}><textarea value={input} onChange={event => { setInput(event.target.value); if (selectedId != null) { sendTypingRealtime(selectedId,event.target.value.trim().length>0); if (typingTimer.current) window.clearTimeout(typingTimer.current); typingTimer.current=window.setTimeout(() => sendTypingRealtime(selectedId,false),1800) } }} onKeyDown={event => { if (event.key==='Enter' && !event.shiftKey) { event.preventDefault(); void send() } }} placeholder="Message…" data-prepza-chat-composer="true" disabled={sending || uploading} rows={1} style={{ width:'100%',minHeight:40,maxHeight:100,resize:'none',border:0,outline:0,background:'transparent',padding:'11px 0',font:'13px Plus Jakarta Sans',boxSizing:'border-box' }} /></div><button type="button" onClick={() => void send()} disabled={sending || uploading || !input.trim()} aria-label="Send" style={{ width:40,height:40,border:0,borderRadius:12,background:input.trim()?'#c9a84c':'#e6e7e9',color:'#0b1437',fontWeight:900,cursor:input.trim()?'pointer':'default' }}>➤</button></div>
          </footer>
        </>}
      </section>
    </div>
    <CallExperience userId={meId} />
  </div>
}
