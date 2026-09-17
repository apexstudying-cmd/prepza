import { io, type Socket } from 'socket.io-client'

export type CallSignal = {
  call_id: string
  conversation_id: number
  from_user_id: number
  from_name?: string
  to_user_id: number
  kind: 'voice' | 'video'
  payload?: unknown
}

let socket: Socket | null = null
let connected = false
const listeners = new Set<(event: CallSignal & { type: string }) => void>()

function getSocket() {
  if (typeof window === 'undefined') return null
  if (socket) return socket
  socket = io(window.location.origin, { path: '/socket.io', transports: ['websocket', 'polling'], withCredentials: true, reconnection: true, reconnectionAttempts: Infinity, reconnectionDelay: 500, reconnectionDelayMax: 5000 })
  socket.on('connect', () => { connected = true })
  socket.on('disconnect', () => { connected = false })
  for (const type of ['call:incoming', 'call:accepted', 'call:rejected', 'call:ended', 'call:offer', 'call:answer', 'call:ice']) {
    socket.on(type, (payload: CallSignal) => { if (payload && typeof payload.call_id === 'string') listeners.forEach(listener => listener({ ...payload, type })) })
  }
  return socket
}

export function installCallRealtime() { getSocket() }
export function onCallSignal(listener: (event: CallSignal & { type: string }) => void) { listeners.add(listener); getSocket(); return () => listeners.delete(listener) }
export function emitCall(type: string, payload: Record<string, unknown>) { if (!getSocket()) return; socket?.emit(type, payload) }
export function isCallRealtimeConnected() { return connected }
