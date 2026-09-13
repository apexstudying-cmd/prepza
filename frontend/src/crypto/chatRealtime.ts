import { io, type Socket } from 'socket.io-client'

export type RealtimeMessageEvent = { id: number; conversation_id: number; sender_id: number; body?: string | null; nonce?: string | null; created_at?: string | null; [key: string]: unknown }
let socket: Socket | null = null
let connected = false
const joined = new Set<number>()

function getSocket() {
  if (typeof window === 'undefined') return null
  if (socket) return socket
  socket = io(window.location.origin, { path: '/socket.io', transports: ['websocket', 'polling'], withCredentials: true, reconnection: true, reconnectionAttempts: Infinity, reconnectionDelay: 500, reconnectionDelayMax: 5000 })
  socket.on('connect', () => { connected = true; for (const id of joined) socket?.emit('join_chat', { conversation_id: id }); window.dispatchEvent(new CustomEvent('prepza-realtime-status', { detail: { connected: true } })) })
  socket.on('disconnect', () => { connected = false; window.dispatchEvent(new CustomEvent('prepza-realtime-status', { detail: { connected: false } })) })
  socket.on('chat:message', (message: RealtimeMessageEvent) => { if (message && typeof message.conversation_id === 'number' && typeof message.id === 'number') window.dispatchEvent(new CustomEvent('prepza-realtime-message', { detail: message })) })
  socket.on('chat:typing', detail => window.dispatchEvent(new CustomEvent('prepza-realtime-typing', { detail })))
  socket.on('chat:read', detail => window.dispatchEvent(new CustomEvent('prepza-realtime-read', { detail })))
  socket.on('chat:presence', detail => window.dispatchEvent(new CustomEvent('prepza-realtime-presence', { detail })))
  return socket
}

export function installChatRealtime() { getSocket() }
export function joinRealtimeChat(conversationId: number) { if (Number.isInteger(conversationId) && conversationId > 0) { joined.add(conversationId); getSocket()?.emit('join_chat', { conversation_id: conversationId }) } }
export function leaveRealtimeChat(conversationId: number) { if (Number.isInteger(conversationId) && conversationId > 0) { joined.delete(conversationId); getSocket()?.emit('leave_chat', { conversation_id: conversationId }) } }
export function sendTypingRealtime(conversationId: number, typing: boolean) { if (connected) getSocket()?.emit('chat:typing', { conversation_id: conversationId, typing }) }
export function sendReadRealtime(conversationId: number, readAt?: string) { if (connected) getSocket()?.emit('chat:read', { conversation_id: conversationId, read_at: readAt }) }
export function isRealtimeConnected() { return connected }
