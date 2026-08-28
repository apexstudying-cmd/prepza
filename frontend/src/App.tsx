import { useState, useEffect, useRef } from 'react'
import logoImg from './imports/logo.png'
import { TERMS_TEXT, PRIVACY_TEXT } from './legalContent'

// ─── API helper ─────────────────────────────────────────────────────────────
// Dev: Vite proxies these paths straight to the Flask backend (see
// vite.config.ts), so relative paths work identically in dev and once this
// app is eventually served by Flask itself in production - no base URL
// switching needed.
class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const { headers: extraHeaders, ...restOptions } = options
  const res = await fetch(path, {
    credentials: 'include',
    ...restOptions,
    headers: { 'Content-Type': 'application/json', ...(extraHeaders || {}) },
  })
  let body: any = null
  try { body = await res.json() } catch { /* no JSON body */ }
  if (!res.ok) {
    throw new ApiError((body && body.error) || `Request failed (${res.status})`, res.status)
  }
  return body as T
}

// ─── Document upload helpers ───────────────────────────────────────────────
const ALLOWED_UPLOAD_EXTENSIONS = ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'jpg', 'jpeg', 'png']
const MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024 // 50 MB - matches backend MAX_DOCUMENT_SIZE_BYTES
const MAX_CHAT_ATTACHMENT_SIZE_BYTES = 20 * 1024 * 1024 // 20 MB - matches backend CHAT_ATTACHMENT_MAX_SIZE_BYTES
const IMAGE_FILE_TYPES = ['jpg', 'jpeg', 'png']

function getFileExtension(filename: string): string | null {
  const parts = filename.split('.')
  if (parts.length < 2) return null
  return parts[parts.length - 1].toLowerCase()
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  return Uint8Array.from([...rawData].map(c => c.charCodeAt(0)))
}

async function subscribeToPush(csrfToken: string): Promise<void> {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    throw new Error('Push notifications are not supported on this device/browser.')
  }
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') {
    throw new Error('Notification permission was not granted.')
  }
  const registration = await navigator.serviceWorker.ready
  const { public_key } = await api<{ public_key: string }>('/push/vapid-public-key')
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(public_key) as BufferSource,
  })
  const json = subscription.toJSON()
  await api('/push/subscribe', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }),
  })
}

async function unsubscribeFromPush(csrfToken: string): Promise<void> {
  if (!('serviceWorker' in navigator)) return
  const registration = await navigator.serviceWorker.ready
  const subscription = await registration.pushManager.getSubscription()
  if (!subscription) return
  const endpoint = subscription.endpoint
  await subscription.unsubscribe()
  await api('/push/subscribe', {
    method: 'DELETE',
    headers: { 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ endpoint }),
  })
}

async function sha256Hex(file: File): Promise<string> {
  const buffer = await file.arrayBuffer()
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer)
  return Array.from(new Uint8Array(hashBuffer)).map(b => b.toString(16).padStart(2, '0')).join('')
}

type DocumentDetail = {
  id: number; title: string; original_filename: string; status: string
  file_type: string | null; file_size_bytes: number | null; page_count: number | null
  error_message: string | null; view_url: string | null
  materials: { type: string; status: string }[]; created_at: string | null
}

// Payload shape inside `summary`/`quiz`/`flashcards`/`mindmap` below is
// whatever ai_service.py produces - not pinned down here, so every
// consumer renders defensively (checks a few likely field names, falls
// back to raw JSON) rather than assuming one exact shape.
type CompletionResponse = { xp_awarded: number; newly_unlocked_achievements: string[] }

function AchievementToast({ codes }: { codes: string[] }) {
  if (codes.length === 0) return null
  return (
    <div style={{ background: 'rgba(201,168,76,0.15)', border: `1px solid ${N.gold}55`, borderRadius: 12, padding: '10px 14px', margin: '0 0 14px', fontSize: 12, fontWeight: 700, color: N.gold }}>
      🏆 Achievement unlocked: {codes.join(', ')}
    </div>
  )
}

function GenerationError({ error }: { error: string }) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 32, textAlign: 'center' }}>
      <div style={{ fontSize: 40, marginBottom: 14 }}>⚠️</div>
      <div style={{ color: '#6B7280', fontSize: 13, maxWidth: 280 }}>{error}</div>
    </div>
  )
}

function GenerationLoading({ label }: { label: string }) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 32 }}>
      <div style={{ width: 40, height: 40, border: `3px solid rgba(201,168,76,0.2)`, borderTopColor: N.gold, borderRadius: '50%', animation: 'spin-slow 0.8s linear infinite', marginBottom: 16 }} />
      <div style={{ color: '#6B7280', fontSize: 13 }}>{label}</div>
    </div>
  )
}

// ─── Icon helpers ─────────────────────────────────────────────────────────────
const Ic = {
  home:     (s='w-6 h-6') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>,
  explore:  (s='w-6 h-6') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>,
  plus:     (s='w-6 h-6') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>,
  chat:     (s='w-6 h-6') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>,
  person:   (s='w-6 h-6') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>,
  back:     (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg>,
  close:    (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>,
  search:   (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>,
  send:     (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>,
  mic:      (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1-9c0-.55.45-1 1-1s1 .45 1 1v6c0 .55-.45 1-1 1s-1-.45-1-1V5zm6 6c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>,
  upload:   (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5 5 5h-3z"/></svg>,
  heart:    (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>,
  comment:  (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M21.99 4c0-1.1-.89-2-1.99-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h14l4 4-.01-18z"/></svg>,
  bookmark: (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M17 3H7c-1.1 0-1.99.9-1.99 2L5 21l7-3 7 3V5c0-1.1-.9-2-2-2z"/></svg>,
  share:    (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92 1.61 0 2.92-1.31 2.92-2.92s-1.31-2.92-2.92-2.92z"/></svg>,
  dots:     (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg>,
  bell:     (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/></svg>,
  check:    (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>,
  flash:    (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M7 2v11h3v9l7-12h-4l4-8z"/></svg>,
  podcast:  (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M12 1c-4.97 0-9 4.03-9 9v7c0 1.66 1.34 3 3 3h1v-8H5v-2c0-3.87 3.13-7 7-7s7 3.13 7 7v2h-2v8h1c1.66 0 3-1.34 3-3v-7c0-4.97-4.03-9-9-9z"/></svg>,
  book:     (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 14H8v-2h8v2zm0-4H8v-2h8v2zm0-4H8V6h8v2z"/></svg>,
  trophy:   (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M19 5h-2V3H7v2H5c-1.1 0-2 .9-2 2v1c0 2.55 1.92 4.63 4.39 4.94.63 1.5 1.98 2.63 3.61 2.96V19H7v2h10v-2h-4v-3.1c1.63-.33 2.98-1.46 3.61-2.96C19.08 12.63 21 10.55 21 8V7c0-1.1-.9-2-2-2zM5 8V7h2v3.82C5.84 10.4 5 9.3 5 8zm14 0c0 1.3-.84 2.4-2 2.82V7h2v1z"/></svg>,
  play:     (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>,
  pause:    (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>,
  settings: (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M19.14,12.94c0.04-0.3,0.06-0.61,0.06-0.94c0-0.32-0.02-0.64-0.07-0.94l2.03-1.58c0.18-0.14,0.23-0.41,0.12-0.61 l-1.92-3.32c-0.12-0.22-0.37-0.29-0.59-0.22l-2.39,0.96c-0.5-0.38-1.03-0.7-1.62-0.94L14.4,2.81c-0.04-0.24-0.24-0.41-0.48-0.41 h-3.84c-0.24,0-0.43,0.17-0.47,0.41L9.25,5.35C8.66,5.59,8.12,5.92,7.63,6.29L5.24,5.33c-0.22-0.08-0.47,0-0.59,0.22L2.74,8.87 C2.62,9.08,2.66,9.34,2.86,9.48l2.03,1.58C4.84,11.36,4.8,11.69,4.8,12s0.02,0.64,0.07,0.94l-2.03,1.58 c-0.18,0.14-0.23,0.41-0.12,0.61l1.92,3.32c0.12,0.22,0.37,0.29,0.59,0.22l2.39-0.96c0.5,0.38,1.03,0.7,1.62,0.94l0.36,2.54 c0.05,0.24,0.24,0.41,0.48,0.41h3.84c0.24,0,0.44-0.17,0.47-0.41l0.36-2.54c0.59-0.24,1.13-0.56,1.62-0.94l2.39,0.96 c0.22,0.08,0.47,0,0.59-0.22l1.92-3.32c0.12-0.22,0.07-0.47-0.12-0.61L19.14,12.94z M12,15.6c-1.98,0-3.6-1.62-3.6-3.6 s1.62-3.6,3.6-3.6s3.6,1.62,3.6,3.6S13.98,15.6,12,15.6z"/></svg>,
  eye:      (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>,
  attach:   (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M16.5 6v11.5c0 2.21-1.79 4-4 4s-4-1.79-4-4V5c0-1.38 1.12-2.5 2.5-2.5s2.5 1.12 2.5 2.5v10.5c0 .55-.45 1-1 1s-1-.45-1-1V6H10v9.5c0 1.38 1.12 2.5 2.5 2.5s2.5-1.12 2.5-2.5V5c0-2.21-1.79-4-4-4S7 2.79 7 5v12.5c0 3.04 2.46 5.5 5.5 5.5s5.5-2.46 5.5-5.5V6h-1.5z"/></svg>,
  edit:     (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>,
  logout:   (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z"/></svg>,
  image:    (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/></svg>,
  link:     (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z"/></svg>,
  skip:     (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>,
  rewind:   (s='w-5 h-5') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M18 9.86v4.28L14.97 12 18 9.86zm-9 0v4.28L5.97 12 9 9.86zM20 6l-7 5 7 5V6zm-9 0l-7 5 7 5V6z"/></svg>,
  chevR:    (s='w-4 h-4') => <svg className={s} viewBox="0 0 24 24" fill="currentColor"><path d="M8.59 16.59L13.17 12 8.59 7.41 10 6l6 6-6 6-1.41-1.41z"/></svg>,
  toggle:   (on: boolean) => (
    <div style={{ width: 44, height: 24, background: on ? '#C9A84C' : '#D1D5DB', borderRadius: 99, position: 'relative', transition: 'background 0.2s', cursor: 'pointer' }}>
      <div style={{ width: 18, height: 18, background: '#fff', borderRadius: '50%', position: 'absolute', top: 3, left: on ? 23 : 3, transition: 'left 0.2s', boxShadow: '0 1px 4px rgba(0,0,0,0.2)' }} />
    </div>
  ),
}

// ─── Types ────────────────────────────────────────────────────────────────────
type Screen =
  | 'splash' | 'login' | 'forgot-password' | 'signup' | 'check-email' | 'complete-profile' | 'reset-password' | 'verify-confirm'
  | 'home' | 'explore' | 'create-modal' | 'chats' | 'profile'
  | 'chat-detail' | 'upload' | 'processing' | 'doc-ready' | 'document-study'
  | 'ai-tutor' | 'flashcards' | 'quiz' | 'podcast-player' | 'podcast-library' | 'summary'
  | 'forum' | 'comments' | 'post-composer' | 'question-composer'
  | 'opportunities' | 'opportunity-detail' | 'share-opp-form' | 'edu-upload-form'
  | 'settings' | 'student-profile' | 'share-sheet'
  | 'notifications' | 'library' | 'mind-map' | 'new-chat' | 'chat-options' | 'edit-profile'
  | 'subscription' | 'payment' | 'payment-success' | 'payment-failure' | 'payment-history'
  | 'publish-library' | 'xp-progress' | 'study-streak' | 'achievements'
  | 'followers' | 'following' | 'group-detail' | 'group-create' | 'ambassador'

// ─── Kenyan Data ──────────────────────────────────────────────────────────────
const USER = { name: 'Arnold Gichuru', initials: 'AG', course: 'Actuarial Science', year: 'Year 1', uni: 'Kenyatta University' }

const studyDocs = [
  { id: 1, subject: 'ACT 101 – Actuarial Mathematics', chapter: 'Ch.3 – Interest Theory & Annuities', progress: 52, color: '#C9A84C', icon: '∑' },
  { id: 2, subject: 'MAT 101 – Calculus I', chapter: 'Ch.5 – Integration Techniques', progress: 34, color: '#4C7BC9', icon: '∫' },
  { id: 3, subject: 'STA 101 – Probability & Statistics', chapter: 'Ch.2 – Probability Distributions', progress: 78, color: '#4CC97B', icon: 'σ' },
]

const forumPosts = [
  { id: 1, user: 'Wanjiru Kamau', avatar: 'WK', course: 'BSc Computer Science · Y2', time: '1h ago', content: "Just used Prepza AI to summarize my ACT 101 notes on Interest Theory. Generated 35 flashcards in 90 seconds. My CATS revision just got 10x easier 🔥", likes: 87, comments: 24, tag: 'Study Win', liked: false, saved: true },
  { id: 2, user: 'Brian Omondi', avatar: 'BO', course: 'B.Com Finance · Y3', time: '3h ago', content: "The podcast feature is a game changer. Created a 10-minute study podcast from my STA 101 notes and listened during my matatu ride to KU. Arrived already revised 🎧", likes: 134, comments: 41, tag: 'Pro Tip', liked: true, saved: false },
  { id: 3, user: 'Aisha Mohamed', avatar: 'AM', course: 'LLB Law · Y2', time: '5h ago', content: "Anyone have the Constitutional Law past papers from 2020-2023? Looking for them in the Prepza library. Will upload my own notes as trade 📚", likes: 43, comments: 18, tag: 'Request', liked: false, saved: false },
  { id: 4, user: 'David Njoroge', avatar: 'DN', course: 'MBBS Medicine · Y3', time: '1d ago', content: "Kenyatta University students — the Physiology library on Prepza has 47 past papers now. Someone uploaded the full KU 2018-2023 set. Go grab them before your upcoming block exam!", likes: 221, comments: 67, tag: 'Announcement', liked: false, saved: false },
]

const opportunities = [
  { id: 1, type: 'Internship', title: 'Technology Intern – Safaricom', org: 'Safaricom PLC', location: 'Nairobi, Kenya', deadline: 'Aug 30, 2025', reward: 'KES 35,000/mo', tag: 'Hot', color: '#4CC97B', desc: 'Join Safaricom\'s technology division for a 3-month internship covering software engineering, data analytics, and network operations. Open to 2nd and 3rd year students in Computer Science, Engineering, and related fields.', reqs: ['2nd or 3rd year student', 'Relevant STEM degree', 'Strong analytical skills', 'Kenyan citizen'] },
  { id: 2, type: 'Scholarship', title: 'Equity Leaders Programme', org: 'Equity Bank Foundation', location: 'All Kenya', deadline: 'Sep 15, 2025', reward: 'Full Scholarship + KES 8,000/mo stipend', tag: 'Flagship', color: '#C9A84C', desc: 'The Equity Leaders Programme offers full scholarships to outstanding Kenyan university students, including tuition, accommodation, mentorship, and a monthly stipend.', reqs: ['Kenyan citizen', 'Mean grade of A- or above', 'Demonstrated financial need', 'Year 1 or 2 student'] },
  { id: 3, type: 'Competition', title: 'Africa Prize for Engineering Innovation', org: 'Royal Academy of Engineering', location: 'Pan-Africa', deadline: 'Oct 1, 2025', reward: 'KES 600,000 prize', tag: 'Prestigious', color: '#4C7BC9', desc: 'The Africa Prize rewards early-stage engineering innovations that can make a real difference to people\'s lives across Sub-Saharan Africa. Open to African engineers with a working prototype.', reqs: ['African engineer', 'Working prototype required', 'Problem must affect Sub-Saharan Africa', 'Open to teams or individuals'] },
  { id: 4, type: 'Job', title: 'Graduate Analyst Programme', org: 'KCB Group', location: 'Nairobi, Kenya', deadline: 'Sep 30, 2025', reward: 'KES 65,000/mo', tag: 'Entry Level', color: '#9B59B6', desc: 'KCB Group\'s Graduate Analyst Programme recruits fresh graduates across Finance, Technology, Risk Management, and Operations. Includes a structured 12-month rotation programme.', reqs: ['University degree (any field)', 'Min. Upper Second class honours', 'Graduated within last 2 years', 'Strong communication skills'] },
  { id: 5, type: 'Event', title: 'Kenya Tech Summit 2025', org: 'ICT Authority Kenya', location: 'KICC, Nairobi', deadline: 'Aug 20, 2025', reward: 'Free (Student Pass)', tag: 'Upcoming', color: '#C94C4C', desc: 'Kenya\'s largest annual technology conference bringing together startups, corporates, government, and students. Features workshops, pitching competitions, and networking events.', reqs: ['Valid student ID', 'Free registration required', 'Open to all students'] },
]

type OpportunityOrg = { id: number; name: string; logo_url: string | null; website: string | null }
type OpportunityPublic = {
  id: number
  title: string
  description: string
  opportunity_type: string
  location: string | null
  is_remote: boolean
  application_url: string | null
  application_instructions: string | null
  application_deadline: string | null
  expiry_date: string | null
  published_at: string | null
  view_count: number
  organisation: OpportunityOrg | null
  promotion_type: string | null
  saved: boolean
}

const OPP_TYPE_META: Record<string, { icon: string; color: string; label: string }> = {
  job: { icon: '📋', color: '#9B59B6', label: 'Job' },
  internship: { icon: '💼', color: '#4CC97B', label: 'Internship' },
  scholarship: { icon: '🎓', color: '#C9A84C', label: 'Scholarship' },
  competition: { icon: '🏆', color: '#4C7BC9', label: 'Competition' },
  volunteering: { icon: '🤲', color: '#4CC97B', label: 'Volunteering' },
  event: { icon: '🎪', color: '#C94C4C', label: 'Event' },
  other: { icon: '🔖', color: '#6B7280', label: 'Other' },
}
function oppTypeMeta(t: string) { return OPP_TYPE_META[t] || OPP_TYPE_META.other }
function fmtDeadline(iso: string | null) {
  if (!iso) return null
  return new Date(iso).toLocaleDateString('en-KE', { month: 'short', day: 'numeric', year: 'numeric' })
}

const OPP_FILTERS = ['All','Internships','Scholarships','Competitions','Jobs','Events','Saved']
const OPP_FILTER_TYPE_MAP: Record<string, string | undefined> = {
  All: undefined, Internships: 'internship', Scholarships: 'scholarship',
  Competitions: 'competition', Jobs: 'job', Events: 'event',
}

const chatList = [
  { id: 1, name: 'ACT 101 Study Group', avatar: '∑', last: 'Wanjiru: Anyone doing Chapter 3 tonight?', time: '9:41', unread: 5, isGroup: true },
  { id: 2, name: 'Wanjiru Kamau', avatar: 'WK', last: 'Thanks for the flashcards! Really helped 🙏', time: '9:20', unread: 0, isGroup: false },
  { id: 3, name: 'KU Actuarial Science Y1', avatar: '📐', last: 'CAT dates confirmed – check pinned message', time: 'Yesterday', unread: 12, isGroup: true },
  { id: 4, name: 'Brian Omondi', avatar: 'BO', last: 'Did you see the new AI Podcast feature?', time: 'Yesterday', unread: 0, isGroup: false },
  { id: 5, name: 'MAT 101 Class', avatar: '∫', last: 'Prepza AI: Here is the Integration summary...', time: 'Mon', unread: 3, isGroup: true },
]

const chatMessages = [
  { sender: 'Wanjiru', text: 'Has anyone done Chapter 3 of ACT 101 yet? The annuities section is confusing 😭', time: '9:10', me: false },
  { sender: 'Me', text: 'Yes! I uploaded the lecture notes to Prepza and asked the AI to explain it. Way clearer now.', time: '9:12', me: true },
  { sender: 'Wanjiru', text: 'Send the link! Did you use the document study feature?', time: '9:13', me: false },
  { sender: 'Me', text: 'Yeah, highlight any paragraph and tap "Explain" – it gives you examples with KES amounts too which makes it actually relatable 😄', time: '9:15', me: true },
  { sender: 'Brian', text: 'I generated a quiz from the notes. Got 14/15 on first try 🔥', time: '9:22', me: false },
  { sender: 'Wanjiru', text: 'Okay I NEED to try this. Uploading now 📤', time: '9:35', me: false },
]

const podcasts = [
  { id: 1, title: 'Interest Theory Explained', subject: 'ACT 101', duration: '9 min', icon: '∑', color: '#C9A84C' },
  { id: 2, title: 'Integration Techniques', subject: 'MAT 101', duration: '12 min', icon: '∫', color: '#4C7BC9' },
  { id: 3, title: 'Normal Distributions', subject: 'STA 101', duration: '7 min', icon: 'σ', color: '#4CC97B' },
  { id: 4, title: 'Probability Foundations', subject: 'STA 101', duration: '14 min', icon: 'P', color: '#9B59B6' },
]

const flashcardData = [
  { q: 'What is the present value formula for an annuity-immediate?', a: 'PV = a(n,i) = (1 - vⁿ) / i\n\nWhere v = 1/(1+i) is the discount factor and i is the interest rate per period.' },
  { q: 'Define the force of interest (δ).', a: 'δ = ln(1+i)\n\nIt is the continuously compounded interest rate equivalent to the effective annual rate i.' },
  { q: 'What is the difference between an annuity-immediate and annuity-due?', a: 'Annuity-immediate: payments at END of each period\nAnnuity-due: payments at BEGINNING of each period\n\nä(n,i) = (1+i) × a(n,i)' },
  { q: 'State the compound interest accumulation function.', a: 'A(t) = A(0)(1+i)ᵗ\n\nFor KES 10,000 at 8% for 3 years:\nA(3) = 10,000 × (1.08)³ = KES 12,597' },
  { q: 'What is a perpetuity-immediate?', a: 'An annuity with payments continuing forever.\n\nPV = 1/i\n\nExample: KES 5,000/year at 10% = PV of KES 50,000' },
]

const quizData = [
  { q: 'If KES 50,000 is invested at 12% p.a. compound interest, what is the accumulated value after 2 years?', opts: ['KES 56,000', 'KES 62,720', 'KES 60,000', 'KES 58,400'], ans: 1 },
  { q: 'The present value of an annuity-immediate of KES 1 per annum for n years at effective interest rate i is:', opts: ['vⁿ/i', '(1-vⁿ)/i', '(1+i)ⁿ-1)/i', 'vⁿ × i'], ans: 1 },
  { q: 'Which of the following correctly defines the discount factor v?', opts: ['v = 1+i', 'v = i/(1+i)', 'v = 1/(1+i)', 'v = ln(1+i)'], ans: 2 },
  { q: 'A perpetuity pays KES 2,400 per month. At an annual effective interest rate of 6%, what is the present value?', opts: ['KES 480,000', 'KES 40,000', 'KES 474,000', 'KES 490,000'], ans: 0 },
]

// ─── Shared atoms ─────────────────────────────────────────────────────────────
const N = { navy: '#0B1437', navy2: '#132046', navy3: '#1A2A5E', gold: '#C9A84C', goldL: '#E8C97E', bg: '#F8F9FC' }

function Pill({ text, color = N.gold, bg }: { text: string; color?: string; bg?: string }) {
  return <span style={{ background: bg ?? color + '20', color, border: `1px solid ${color}33`, borderRadius: 99, fontSize: 10, fontWeight: 700, padding: '2px 9px', letterSpacing: 0.3, whiteSpace: 'nowrap' }}>{text}</span>
}

function Btn({ label, onClick, variant = 'primary', small }: { label: string; onClick?: () => void; variant?: 'primary'|'ghost'|'outline'; small?: boolean }) {
  const styles: Record<string, React.CSSProperties> = {
    primary: { background: `linear-gradient(135deg,${N.navy},${N.navy3})`, color: N.gold, border: 'none' },
    ghost:   { background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, border: 'none' },
    outline: { background: 'transparent', color: N.navy, border: `1.5px solid ${N.navy}22` },
  }
  return (
    <button onClick={onClick} style={{ ...styles[variant], fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: small ? 12 : 14, borderRadius: 14, padding: small ? '8px 16px' : '13px 24px', cursor: 'pointer', letterSpacing: 0.2 }}>{label}</button>
  )
}

function Avi({ name, size = 38, emoji }: { name: string; size?: number; emoji?: string }) {
  return (
    <div style={{ width: size, height: size, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: emoji ? size * 0.45 : size * 0.33, fontWeight: 800, color: N.gold, flexShrink: 0, fontFamily: 'Plus Jakarta Sans' }}>
      {emoji ?? name}
    </div>
  )
}

function Bar({ pct, color = N.gold }: { pct: number; color?: string }) {
  return <div style={{ background: '#E5E7EB', borderRadius: 99, height: 5 }}><div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 99, transition: 'width 0.6s ease' }} /></div>
}

function StatusBar({ dark = true }: { dark?: boolean }) {
  const c = dark ? '#fff' : N.navy
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 22px 6px', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, color: c }}>
      <span>9:41</span>
      <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
        <svg width="16" height="11" viewBox="0 0 16 12" fill={c}><rect x="0" y="4" width="3" height="8" rx="1"/><rect x="4.5" y="2.5" width="3" height="9.5" rx="1"/><rect x="9" y="0.5" width="3" height="11.5" rx="1"/><rect x="13.5" y="0" width="2.5" height="12" rx="1" opacity="0.3"/></svg>
        <svg width="25" height="12" viewBox="0 0 25 12" fill="none"><rect x="0.5" y="0.5" width="21" height="11" rx="3.5" stroke={c} strokeOpacity="0.35"/><rect x="2" y="2" width="16" height="8" rx="2" fill={c}/><path d="M23 4v4a2 2 0 000-4z" fill={c} fillOpacity="0.4"/></svg>
      </div>
    </div>
  )
}

function TopBar({ title, onBack, setScreen, rightEl }: { title?: string; onBack?: () => void; setScreen?: (s: Screen) => void; rightEl?: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 18px 14px' }}>
      {onBack && (
        <button onClick={onBack} style={{ width: 36, height: 36, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 11, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <div style={{ color: '#fff' }}>{Ic.back()}</div>
        </button>
      )}
      {title && <span style={{ flex: 1, fontWeight: 800, fontSize: 17, color: '#fff' }}>{title}</span>}
      {rightEl}
    </div>
  )
}

function BottomNav({ active, setScreen }: { active: Screen; setScreen: (s: Screen) => void }) {
  const isHome  = ['home','ai-tutor','forum','opportunities','opportunity-detail','podcast-player','podcast-library','flashcards','quiz','summary','upload','processing','doc-ready','document-study','share-sheet','comments','post-composer','question-composer','share-opp-form','edu-upload-form','notifications','library','mind-map'].includes(active)
  const isExp   = active === 'explore' || active === 'student-profile'
  const isChat  = active === 'chats' || active === 'chat-detail' || active === 'new-chat' || active === 'chat-options'
  const isProf  = active === 'profile' || active === 'settings' || active === 'edit-profile'
  const tabs = [
    { key: 'home' as Screen, icon: Ic.home, label: 'Home', hit: isHome },
    { key: 'explore' as Screen, icon: Ic.explore, label: 'Explore', hit: isExp },
    { key: 'create-modal' as Screen, icon: Ic.plus, label: '', hit: false },
    { key: 'chats' as Screen, icon: Ic.chat, label: 'Chats', hit: isChat },
    { key: 'profile' as Screen, icon: Ic.person, label: 'Profile', hit: isProf },
  ]
  return (
    <div style={{ background: N.navy, borderTop: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', paddingBottom: 6, flexShrink: 0 }}>
      {tabs.map(t => {
        const isCta = t.key === 'create-modal'
        return (
          <button key={t.key} onClick={() => setScreen(t.key)} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, background: 'none', border: 'none', cursor: 'pointer', padding: isCta ? '0 0 4px' : '8px 0 4px', position: 'relative' }}>
            {isCta ? (
              <div style={{ width: 50, height: 50, borderRadius: '50%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginTop: -22, boxShadow: `0 4px 18px rgba(201,168,76,0.55)` }}>
                <div style={{ color: N.navy }}>{Ic.plus()}</div>
              </div>
            ) : (
              <>
                {t.hit && <div style={{ position: 'absolute', top: 0, left: '50%', transform: 'translateX(-50%)', width: 18, height: 2, background: N.gold, borderRadius: 2 }} />}
                <div style={{ color: t.hit ? N.gold : 'rgba(255,255,255,0.38)' }}>{t.icon()}</div>
                <span style={{ fontSize: 10, fontWeight: t.hit ? 800 : 500, color: t.hit ? N.gold : 'rgba(255,255,255,0.38)', fontFamily: 'Plus Jakarta Sans' }}>{t.label}</span>
              </>
            )}
          </button>
        )
      })}
    </div>
  )
}

// ─── LOADING SYSTEM ───────────────────────────────────────────────────────────

function useLoading(ms = 1200): boolean {
  const [loading, setLoading] = useState(true)
  useEffect(() => { const t = setTimeout(() => setLoading(false), ms); return () => clearTimeout(t) }, [])
  return loading
}

function Sk({ w, h = 14, r = 8, dark, style: sx }: { w?: string | number; h?: number; r?: number; dark?: boolean; style?: React.CSSProperties }) {
  const base: React.CSSProperties = { width: w ?? '100%', height: h, borderRadius: r, flexShrink: 0, ...sx }
  return dark
    ? <div style={{ ...base, background: 'linear-gradient(90deg,rgba(255,255,255,0.05) 25%,rgba(255,255,255,0.12) 50%,rgba(255,255,255,0.05) 75%)', backgroundSize: '200% 100%', animation: 'shimmer 1.8s infinite' }} />
    : <div className="shimmer" style={base} />
}

function SkCircle({ size = 40, dark }: { size?: number; dark?: boolean }) {
  return <Sk w={size} h={size} r={size / 2} dark={dark} />
}

function AsyncBtn({ label, loadLabel, onClick, style, variant = 'primary', loadingMs = 1500 }: {
  label: string; loadLabel?: string; onClick?: () => void; style?: React.CSSProperties
  variant?: 'primary' | 'ghost' | 'danger'; loadingMs?: number
}) {
  const [busy, setBusy] = useState(false)
  const bg = variant === 'primary' ? `linear-gradient(135deg,${N.gold},${N.goldL})` : variant === 'ghost' ? `linear-gradient(135deg,${N.navy},${N.navy3})` : '#C94C4C'
  const fg = variant === 'primary' ? N.navy : variant === 'ghost' ? N.gold : '#fff'
  const handle = () => { if (busy) return; setBusy(true); onClick?.(); setTimeout(() => setBusy(false), loadingMs) }
  return (
    <button onClick={handle} disabled={busy} style={{ background: bg, color: fg, border: 'none', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, borderRadius: 14, cursor: busy ? 'wait' : 'pointer', opacity: busy ? 0.82 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, transition: 'opacity 0.2s', ...style }}>
      {busy
        ? <><div style={{ width: 13, height: 13, border: '2px solid currentColor', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin-slow 0.65s linear infinite', flexShrink: 0 }} />{loadLabel ?? 'Working…'}</>
        : label}
    </button>
  )
}

// ─── SKELETON ATOMS ───────────────────────────────────────────────────────────

function SkPostCard() {
  return (
    <div style={{ background: '#fff', borderRadius: 16, padding: '14px 16px', marginBottom: 10, boxShadow: '0 2px 10px rgba(0,0,0,0.05)' }}>
      <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
        <SkCircle size={38} />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><Sk w="50%" h={13} /><Sk w="70%" h={10} /></div>
        <Sk w={50} h={18} r={99} />
      </div>
      <Sk h={12} style={{ marginBottom: 6 }} /><Sk h={12} w="80%" style={{ marginBottom: 6 }} /><Sk h={12} w="60%" style={{ marginBottom: 14 }} />
      <div style={{ display: 'flex', gap: 16 }}>
        <Sk w={50} h={14} r={6} /><Sk w={50} h={14} r={6} />
        <div style={{ flex: 1 }} /><Sk w={18} h={18} r={4} /><Sk w={18} h={18} r={4} />
      </div>
    </div>
  )
}

function SkDocCard() {
  return (
    <div style={{ background: '#fff', borderRadius: 14, padding: 14, marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
      <Sk w={42} h={42} r={12} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><Sk h={13} w="80%" /><Sk h={10} w="55%" /><Sk h={9} w="40%" /></div>
      <Sk w={36} h={18} r={99} />
    </div>
  )
}

function SkChatRow() {
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid rgba(0,0,0,0.04)' }}>
      <SkCircle size={46} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}><Sk w="45%" h={14} /><Sk w={40} h={11} /></div>
        <Sk w="70%" h={11} />
      </div>
    </div>
  )
}

function SkOppCard() {
  return (
    <div style={{ background: '#fff', borderRadius: 18, overflow: 'hidden', boxShadow: '0 4px 14px rgba(0,0,0,0.08)', marginBottom: 14 }}>
      <div style={{ height: 5, background: '#E5E7EB' }} />
      <div style={{ padding: 16 }}>
        <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
          <Sk w={48} h={48} r={14} />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 7 }}><Sk h={14} w="75%" /><Sk h={11} w="50%" /></div>
          <Sk w={60} h={20} r={99} />
        </div>
        <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>{[80,100,90].map((w, i) => <Sk key={i} w={w} h={11} r={99} />)}</div>
        <div style={{ display: 'flex', gap: 8 }}><Sk h={42} r={12} /><Sk w={44} h={42} r={12} /><Sk w={44} h={42} r={12} /></div>
      </div>
    </div>
  )
}

function SkNotifRow() {
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', background: '#fff', borderRadius: 14, padding: '13px 14px', marginBottom: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
      <Sk w={42} h={42} r={12} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><Sk h={13} w="55%" /><Sk h={11} /><Sk h={11} w="70%" /></div>
      <Sk w={40} h={10} />
    </div>
  )
}

// ─── SCREEN SKELETONS ─────────────────────────────────────────────────────────

function SkeletonHome() {
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Sk w={36} h={36} r={10} dark />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><Sk w={60} h={10} dark /><Sk w={100} h={14} dark /></div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}><Sk w={38} h={38} r={12} dark /><Sk w={38} h={38} r={12} dark /></div>
        </div>
        <Sk h={52} r={14} dark />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24, padding: '20px 18px 24px' }}>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}><Sk w={140} h={14} /><Sk w={70} h={12} /></div>
          <div style={{ background: '#fff', borderRadius: 18, padding: 18, marginBottom: 10 }}>
            <div style={{ display: 'flex', gap: 14, marginBottom: 14 }}>
              <Sk w={48} h={48} r={14} />
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 7 }}><Sk h={14} /><Sk w="65%" h={11} /></div>
            </div>
            <Sk h={5} r={99} />
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}><Sk w={80} h={10} /><Sk w={80} h={28} r={10} /></div>
          </div>
          {[1,2].map(i => (
            <div key={i} style={{ background: '#fff', borderRadius: 14, padding: '12px 14px', marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center' }}>
              <Sk w={40} h={40} r={12} />
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><Sk h={12} w="70%" /><Sk h={10} w="50%" /><Sk h={5} r={99} /></div>
              <Sk w={30} h={12} />
            </div>
          ))}
        </div>
        <div>
          <Sk w={120} h={14} style={{ marginBottom: 14 }} />
          <div style={{ display: 'flex', gap: 8, justifyContent: 'space-between' }}>
            {[1,2,3,4,5].map(i => (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                <Sk w={52} h={52} r={16} /><Sk w={40} h={9} />
              </div>
            ))}
          </div>
        </div>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}><Sk w={150} h={14} /><Sk w={60} h={12} /></div>
          <div style={{ display: 'flex', gap: 12, overflowX: 'hidden' }}>
            {[1,2,3].map(i => (
              <div key={i} style={{ flexShrink: 0, width: 140, borderRadius: 16, overflow: 'hidden' }}>
                <Sk w={140} h={90} r={0} />
                <div style={{ background: '#fff', padding: '10px 10px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <Sk h={12} /><Sk w="60%" h={10} /><Sk w={50} h={10} />
                </div>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}><Sk w={100} h={14} /><Sk w={60} h={12} /></div>
          {[1,2].map(i => <SkPostCard key={i} />)}
        </div>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}><Sk w={140} h={14} /><Sk w={60} h={12} /></div>
          {[1,2].map(i => (
            <div key={i} style={{ background: '#fff', borderRadius: 16, padding: '14px 16px', marginBottom: 10, display: 'flex', gap: 12, alignItems: 'center' }}>
              <Sk w={44} h={44} r={12} />
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><Sk h={13} w="75%" /><Sk h={10} w="50%" /></div>
              <Sk w={60} h={20} r={99} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function SkeletonExplore() {
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <Sk w={80} h={20} dark style={{ marginBottom: 12 }} />
        <Sk h={44} r={13} dark style={{ marginBottom: 12 }} />
        <div style={{ display: 'flex', gap: 8 }}>{[40,70,90,70,80].map((w,i) => <Sk key={i} w={w} h={28} r={20} dark />)}</div>
      </div>
      <div style={{ padding: '20px 18px', display: 'flex', flexDirection: 'column', gap: 24 }}>
        <div>
          <Sk w={220} h={14} style={{ marginBottom: 12 }} />
          <div style={{ display: 'flex', gap: 10, overflowX: 'hidden' }}>
            {[1,2,3].map(i => (
              <div key={i} style={{ flexShrink: 0, background: '#fff', borderRadius: 14, padding: 12, minWidth: 148, display: 'flex', flexDirection: 'column', gap: 7 }}>
                <Sk w={30} h={24} /><Sk h={12} /><Sk w="60%" h={10} />
              </div>
            ))}
          </div>
        </div>
        <div><Sk w={160} h={14} style={{ marginBottom: 12 }} />{[1,2,3].map(i => <SkDocCard key={i} />)}</div>
        <div>
          <Sk w={160} h={14} style={{ marginBottom: 12 }} />
          <div style={{ display: 'flex', gap: 10, overflowX: 'hidden' }}>
            {[1,2,3].map(i => (
              <div key={i} style={{ flexShrink: 0, background: '#fff', borderRadius: 16, padding: '16px 14px', width: 148, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
                <SkCircle size={48} /><Sk h={12} /><Sk h={10} w="70%" /><Sk h={28} r={10} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function SkeletonLibrary() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12 }}><Sk w={34} h={34} r={10} dark /><Sk w={120} h={18} dark /></div>
        <div style={{ display: 'flex', gap: 8 }}>{[40,60,80,70,55].map((w,i) => <Sk key={i} w={w} h={28} r={20} dark />)}</div>
      </div>
      <div style={{ flex: 1, padding: 16 }}>
        {[1,2,3,4,5,6].map(i => (
          <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'center', background: '#fff', borderRadius: 14, padding: '13px 14px', marginBottom: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
            <Sk w={44} h={44} r={12} />
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><Sk h={13} w="75%" /><Sk h={10} w="50%" /></div>
            <Sk w={50} h={18} r={99} />
          </div>
        ))}
      </div>
    </div>
  )
}

function SkeletonDocument() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 14px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12 }}>
          <Sk w={34} h={34} r={10} dark />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 5 }}><Sk h={14} dark /><Sk w="50%" h={10} dark /></div>
          <Sk w={34} h={34} r={10} dark />
        </div>
        <Sk h={34} r={12} dark />
      </div>
      <div style={{ flex: 1, padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', gap: 8 }}>{[1,2,3,4].map(i => <Sk key={i} w={80} h={28} r={20} />)}</div>
        <div style={{ background: '#fff', borderRadius: 16, padding: 18, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <Sk h={18} w="60%" /><Sk h={11} w="40%" /><div style={{ height: 4 }} />
          {[100,85,100,75,100,90,100,65].map((w,i) => <Sk key={i} h={12} w={`${w}%`} />)}
          <div style={{ height: 4 }} />
          {[100,80,100,70].map((w,i) => <Sk key={i} h={12} w={`${w}%`} />)}
          <Sk h={64} r={12} style={{ marginTop: 6 }} />
        </div>
      </div>
    </div>
  )
}

function SkeletonAITutor() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12 }}>
          <Sk w={34} h={34} r={10} dark /><Sk w={38} h={38} r={12} dark />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 5 }}><Sk w={140} h={14} dark /><Sk w={100} h={10} dark /></div>
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>{[1,2,3,4,5].map(i => <Sk key={i} w={70} h={28} r={20} dark />)}</div>
        <div style={{ display: 'flex', gap: 8 }}>{[1,2,3,4,5].map(i => <Sk key={i} w={80} h={28} r={20} dark />)}</div>
      </div>
      <div style={{ flex: 1, padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', gap: 10 }}>
          <Sk w={32} h={32} r={9} />
          <div style={{ maxWidth: '78%', background: '#fff', borderRadius: '0 14px 14px 14px', padding: 14, flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Sk h={12} /><Sk h={12} w="90%" /><Sk h={12} w="75%" />
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <div style={{ maxWidth: '65%', background: N.navy2, borderRadius: '14px 0 14px 14px', padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Sk h={12} dark /><Sk h={12} w="80%" dark />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <Sk w={32} h={32} r={9} />
          <div style={{ background: '#fff', borderRadius: '0 14px 14px 14px', padding: '12px 16px', display: 'flex', gap: 6, alignItems: 'center' }}>
            {[0,1,2].map(i => <div key={i} style={{ width: 8, height: 8, background: '#D1D5DB', borderRadius: '50%', animation: `shimmer ${0.5 + i * 0.25}s ease-in-out infinite alternate` }} />)}
          </div>
        </div>
      </div>
    </div>
  )
}

function SkeletonQuiz() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12 }}>
          <Sk w={34} h={34} r={10} dark />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 5 }}><Sk w={110} h={14} dark /><Sk w={160} h={10} dark /></div>
          <Sk w={60} h={20} r={99} dark />
        </div>
        <Sk h={5} r={99} dark style={{ marginBottom: 4 }} />
        <Sk w={60} h={10} dark style={{ marginLeft: 'auto' }} />
      </div>
      <div style={{ flex: 1, padding: 20 }}>
        <div style={{ background: '#fff', borderRadius: 18, padding: 20, marginBottom: 20, boxShadow: '0 2px 12px rgba(0,0,0,0.07)' }}>
          <Sk w={80} h={10} style={{ marginBottom: 14 }} />
          <Sk h={16} style={{ marginBottom: 8 }} /><Sk h={16} w="80%" />
        </div>
        {[1,2,3,4].map(i => (
          <div key={i} style={{ background: '#fff', border: '2px solid rgba(0,0,0,0.06)', borderRadius: 14, padding: '14px 16px', marginBottom: 10, display: 'flex', gap: 10, alignItems: 'center' }}>
            <Sk w={26} h={26} r={13} /><Sk h={14} />
          </div>
        ))}
      </div>
    </div>
  )
}

function SkeletonFlashcards() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12 }}>
          <Sk w={34} h={34} r={10} dark />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 5 }}><Sk w={100} h={14} dark /><Sk w={200} h={10} dark /></div>
          <Sk w={80} h={20} r={99} dark />
        </div>
        <Sk h={5} r={99} dark style={{ marginBottom: 4 }} />
        <Sk w={50} h={10} dark style={{ marginLeft: 'auto' }} />
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '24px 20px', gap: 24 }}>
        <div style={{ width: '100%', minHeight: 220, background: '#fff', borderRadius: 24, padding: 28, boxShadow: '0 8px 32px rgba(0,0,0,0.1)', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Sk w={140} h={11} /><div style={{ height: 16 }} />
          <Sk h={16} /><Sk h={16} w="80%" /><Sk h={16} w="60%" />
        </div>
        <Sk w={180} h={13} r={99} />
      </div>
    </div>
  )
}

function SkeletonPodcast() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}><Sk w={34} h={34} r={10} dark /><Sk w={120} h={16} dark /></div>
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '32px 28px', gap: 28 }}>
        <Sk w={200} h={200} r={28} />
        <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center' }}>
          <Sk w={200} h={22} /><Sk w={160} h={14} /><Sk w={80} h={18} r={99} />
        </div>
        <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <Sk h={4} r={99} />
          <div style={{ display: 'flex', justifyContent: 'space-between' }}><Sk w={40} h={12} /><Sk w={40} h={12} /></div>
        </div>
        <div style={{ display: 'flex', gap: 28, alignItems: 'center' }}>
          <Sk w={24} h={24} r={4} /><Sk w={64} h={64} r={32} /><Sk w={24} h={24} r={4} />
        </div>
        <div style={{ width: '100%' }}>
          <Sk w={120} h={14} style={{ marginBottom: 12 }} />
          {[1,2,3].map(i => (
            <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'center', background: '#fff', borderRadius: 14, padding: 12, marginBottom: 8 }}>
              <Sk w={42} h={42} r={12} />
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><Sk h={13} w="70%" /><Sk h={10} w="50%" /></div>
              <Sk w={20} h={20} r={4} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function SkeletonPodcastLibrary() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 8 }}><Sk w={34} h={34} r={10} dark /><Sk w={160} h={18} dark /></div>
        <Sk w={200} h={11} dark />
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 16 }} className="scrollbar-hide">
        <Sk w={120} h={13} style={{ marginBottom: 12 }} />
        {[1,2,3,4,5].map(i => (
          <div key={i} style={{ display: 'flex', gap: 14, alignItems: 'center', background: '#fff', borderRadius: 14, padding: '13px 14px', marginBottom: 8 }}>
            <Sk w={52} h={52} r={14} />
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><Sk h={13} w="65%" /><Sk h={10} w="45%" /></div>
            <Sk w={24} h={24} r={4} />
          </div>
        ))}
      </div>
    </div>
  )
}

function SkeletonForum() {
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <Sk w={34} h={34} r={10} dark /><Sk w={120} h={18} dark />
          <Sk w={60} h={32} r={11} dark style={{ marginLeft: 'auto' }} />
        </div>
        <div style={{ display: 'flex', gap: 8 }}>{[1,2,3,4].map(i => <Sk key={i} w={80} h={28} r={20} dark />)}</div>
      </div>
      <div style={{ padding: '16px 16px' }}>{[1,2,3,4].map(i => <SkPostCard key={i} />)}</div>
    </div>
  )
}

function SkeletonOpportunities() {
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <Sk w={34} h={34} r={10} dark />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 5 }}><Sk w={150} h={18} dark /><Sk w={200} h={10} dark /></div>
          <Sk w={60} h={30} r={10} dark />
        </div>
        <div style={{ display: 'flex', gap: 8 }}>{[40,80,100,50,60].map((w,i) => <Sk key={i} w={w} h={28} r={20} dark />)}</div>
      </div>
      <div style={{ padding: 16 }}>{[1,2,3].map(i => <SkOppCard key={i} />)}</div>
    </div>
  )
}

function SkeletonOppDetail() {
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <Sk w={34} h={34} r={10} dark /><Sk w="60%" h={16} dark /><Sk w={34} h={34} r={10} dark />
        </div>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
          <Sk w={60} h={60} r={18} dark />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Sk w={180} h={16} dark /><Sk w={120} h={12} dark /><Sk w={60} h={18} r={99} dark />
          </div>
        </div>
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'flex', gap: 10 }}>{[1,2,3].map(i => <Sk key={i} h={36} r={12} />)}</div>
        <div style={{ background: '#fff', borderRadius: 16, padding: 16 }}>
          <Sk w={180} h={14} style={{ marginBottom: 12 }} />
          {[100,90,100,85,100,70].map((w,i) => <Sk key={i} h={12} w={`${w}%`} style={{ marginBottom: 8 }} />)}
        </div>
        <div style={{ background: '#fff', borderRadius: 16, padding: 16 }}>
          <Sk w={120} h={14} style={{ marginBottom: 12 }} />
          {[1,2,3,4].map(i => (
            <div key={i} style={{ display: 'flex', gap: 10, marginBottom: 10 }}><Sk w={20} h={20} r={10} /><Sk h={13} /></div>
          ))}
        </div>
        <Sk h={50} r={16} /><Sk h={46} r={16} />
      </div>
    </div>
  )
}

function SkeletonChats() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#fff' }}>
      <div style={{ background: N.navy, padding: '0 18px 14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <Sk w={60} h={20} dark /><Sk w={34} h={34} r={10} dark />
        </div>
        <Sk h={40} r={12} dark style={{ marginBottom: 12 }} />
        <Sk h={36} r={12} dark />
      </div>
      <div style={{ background: N.navy2, margin: '12px 14px 0', borderRadius: 14, padding: '12px 14px', display: 'flex', gap: 12, alignItems: 'center' }}>
        <Sk w={44} h={44} r={12} dark />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><Sk w={120} h={14} dark /><Sk w={180} h={10} dark /></div>
      </div>
      <div style={{ flex: 1 }}>{[1,2,3,4,5].map(i => <SkChatRow key={i} />)}</div>
    </div>
  )
}

function SkeletonChatDetail() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 16px 14px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <Sk w={34} h={34} r={10} dark />
          <SkCircle size={38} dark />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 5 }}><Sk w={160} h={14} dark /><Sk w={100} h={10} dark /></div>
          <Sk w={34} h={34} r={10} dark />
        </div>
      </div>
      <div style={{ flex: 1, padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {[
          { me: false, lines: [160, 120] },
          { me: true, lines: [180, 100] },
          { me: false, lines: [200] },
          { me: true, lines: [140, 90] },
          { me: false, lines: [170, 130] },
        ].map(({ me, lines }, i) => (
          <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: me ? 'flex-end' : 'flex-start', gap: 2 }}>
            {!me && <Sk w={60} h={10} />}
            <div style={{ maxWidth: '75%', background: me ? N.navy2 : '#fff', borderRadius: me ? '14px 0 14px 14px' : '0 14px 14px 14px', padding: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {lines.map((w, j) => <Sk key={j} w={w} h={12} dark={me} />)}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function SkeletonProfile() {
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: `linear-gradient(180deg,${N.navy} 0%,${N.navy3} 100%)`, padding: '0 18px 24px' }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}><Sk w={34} h={34} r={10} dark /></div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
          <SkCircle size={76} dark />
          <Sk w={160} h={20} dark /><Sk w={200} h={13} dark /><Sk w={130} h={11} dark />
          <div style={{ display: 'flex', gap: 8 }}><Sk w={80} h={32} r={12} dark /><Sk w={80} h={32} r={12} dark /></div>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, padding: '14px 14px 0' }}>
        {[1,2,3,4].map(i => (
          <div key={i} style={{ background: '#fff', borderRadius: 14, padding: '12px 8px', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center' }}>
            <Sk w={40} h={16} /><Sk w={50} h={10} />
          </div>
        ))}
      </div>
      <div style={{ margin: '14px 14px 0', background: '#fff', borderRadius: 16, padding: 14 }}>
        <Sk w={120} h={14} style={{ marginBottom: 14 }} />
        <div style={{ display: 'flex', gap: 14 }}>
          {[1,2,3,4,5].map(i => (
            <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5 }}>
              <SkCircle size={46} /><Sk w={50} h={9} />
            </div>
          ))}
        </div>
      </div>
      <div style={{ margin: '14px 14px 0', background: '#fff', borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
        <div style={{ display: 'flex' }}>{[1,2,3,4].map(i => <Sk key={i} h={42} r={0} style={{ borderRadius: 0 }} />)}</div>
        <div style={{ padding: 14 }}>{[1,2,3].map(i => <SkDocCard key={i} />)}</div>
      </div>
      <div style={{ height: 24 }} />
    </div>
  )
}

function SkeletonNotifications() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}><Sk w={34} h={34} r={10} dark /><Sk w={130} h={18} dark /></div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }} className="scrollbar-hide">
        {[1,2,3,4,5,6,7].map(i => <SkNotifRow key={i} />)}
      </div>
    </div>
  )
}

function SkeletonMindMap() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <Sk w={34} h={34} r={10} dark />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 5 }}><Sk w={100} h={14} dark /><Sk w={160} h={10} dark /></div>
        </div>
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
        <div style={{ background: '#fff', borderRadius: 20, padding: 16, width: '100%', marginBottom: 16, boxShadow: '0 4px 16px rgba(0,0,0,0.08)' }}>
          <Sk h={260} r={12} />
        </div>
        {[1,2,3,4,5,6].map(i => (
          <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center', background: '#fff', borderRadius: 12, padding: '10px 14px', marginBottom: 8, width: '100%' }}>
            <Sk w={10} h={10} r={5} /><Sk h={13} />
          </div>
        ))}
      </div>
    </div>
  )
}

function SkeletonAdminDashboard() {
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}><Sk w={80} h={12} dark /><Sk w={160} h={20} dark /></div>
          <div style={{ display: 'flex', gap: 8 }}><Sk w={38} h={38} r={12} dark /><SkCircle size={38} dark /></div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 10 }}>
          {[1,2,3,4].map(i => (
            <div key={i} style={{ background: 'rgba(255,255,255,0.08)', borderRadius: 14, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
              <Sk w={80} h={11} dark /><Sk w={60} h={22} dark /><Sk w={90} h={10} dark />
            </div>
          ))}
        </div>
      </div>
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ background: '#fff', borderRadius: 16, padding: 16, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}><Sk w={140} h={14} /><Sk w={60} h={24} r={8} /></div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, height: 100 }}>
            {[70,50,85,60,90,45,75].map((h,i) => <Sk key={i} h={h} r={6} />)}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
            {['M','T','W','T','F','S','S'].map((_,i) => <Sk key={i} w={20} h={10} />)}
          </div>
        </div>
        <div style={{ background: '#fff', borderRadius: 16, padding: 16, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}><Sk w={100} h={14} /><Sk w={60} h={24} r={8} /></div>
          {[1,2,3,4,5].map(i => (
            <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'center', paddingBottom: 12, marginBottom: 12, borderBottom: '1px solid rgba(0,0,0,0.05)' }}>
              <SkCircle size={36} />
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 5 }}><Sk h={12} w="60%" /><Sk h={10} w="40%" /></div>
              <Sk w={50} h={18} r={99} /><Sk w={60} h={12} />
            </div>
          ))}
        </div>
        <div style={{ background: '#fff', borderRadius: 16, padding: 16, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
          <Sk w={120} h={14} style={{ marginBottom: 14 }} />
          {[1,2,3,4].map(i => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 12 }}>
              <Sk w={8} h={8} r={4} style={{ marginTop: 4, flexShrink: 0 }} />
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 5 }}><Sk h={12} /><Sk h={10} w="50%" /></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── SPLASH ───────────────────────────────────────────────────────────────────
function SplashScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  // Restores an existing backend session (cookie lasts 7 days) instead of
  // always dropping the user back to the login screen on every app open.
  // Keeps the branded 2.2s splash beat either way.
  //
  // IMPORTANT: only a confirmed 401 from /me means "not logged in". Any
  // other failure (network blip, the service worker's offline fallback,
  // a timeout while the connection re-establishes - all common right
  // after a PWA refresh on mobile) does NOT mean the session is gone;
  // treating it as a logout was sending people back to the login screen
  // while their cookie was still perfectly valid. So: retry once on a
  // non-401 failure, and if it still fails, offer a manual retry instead
  // of silently signing the user out.
  const [state, setState] = useState<'checking' | 'retry'>('checking')

  const checkSession = async (attempt = 0): Promise<void> => {
    setState('checking')
    try {
      const me = await api<{ university_id: number | null }>('/me')
      setScreen(me.university_id ? 'home' : 'complete-profile')
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setScreen('login')
        return
      }
      if (attempt === 0) {
        setTimeout(() => checkSession(1), 1200)
      } else {
        setState('retry')
      }
    }
  }

  useEffect(() => {
    let cancelled = false
    const t = setTimeout(() => { if (!cancelled) checkSession(0) }, 2200)
    return () => { cancelled = true; clearTimeout(t) }
  }, [])

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: `linear-gradient(160deg, ${N.navy} 0%, ${N.navy2} 60%, ${N.navy3} 100%)` }}>
      <div style={{ position: 'absolute', top: '18%', width: 220, height: 220, background: 'rgba(201,168,76,0.06)', borderRadius: '50%', filter: 'blur(50px)' }} />
      <img src={logoImg} alt="Prepza" style={{ width: 100, height: 100, borderRadius: 28, marginBottom: 20, boxShadow: '0 12px 48px rgba(201,168,76,0.3)' }} />
      <div style={{ fontWeight: 800, fontSize: 30, color: '#fff', letterSpacing: '-1px' }}>PREPZA</div>
      <div style={{ color: N.gold, fontSize: 13, fontWeight: 600, letterSpacing: 2, marginTop: 4, textTransform: 'uppercase' }}>Study Smarter. Together.</div>
      {state === 'checking' ? (
        <div style={{ marginTop: 60, display: 'flex', gap: 6 }}>
          {[0,1,2].map(i => <div key={i} style={{ width: i === 0 ? 20 : 6, height: 6, background: i === 0 ? N.gold : 'rgba(255,255,255,0.2)', borderRadius: 99, transition: 'all 0.3s' }} />)}
        </div>
      ) : (
        <div style={{ marginTop: 48, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
          <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 13, textAlign: 'center', padding: '0 32px' }}>Couldn't reach Prepza. Check your connection.</div>
          <button onClick={() => checkSession(0)} style={{ background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.18)', borderRadius: 12, padding: '10px 22px', color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Retry</button>
        </div>
      )}
    </div>
  )
}

// ─── LOGIN ────────────────────────────────────────────────────────────────────
function LoginScreen({ setScreen, oauthError = '' }: { setScreen: (s: Screen) => void; oauthError?: string }) {
  const [email, setEmail] = useState('')
  const [pass, setPass] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [error, setError] = useState(oauthError)
  const [submitting, setSubmitting] = useState(false)

  const handleLogin = async () => {
    setError('')
    if (!email || !pass) { setError('Please enter both your email and password.'); return }
    setSubmitting(true)
    try {
      await api('/login', { method: 'POST', body: JSON.stringify({ email, password: pass }) })
      setScreen('home')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: `linear-gradient(170deg, ${N.navy} 0%, ${N.navy2} 55%, ${N.bg} 100%)` }} className="scrollbar-hide">
      <div style={{ padding: '20px 28px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 40 }}>
        <img src={logoImg} alt="Prepza" style={{ width: 72, height: 72, borderRadius: 20, marginBottom: 16, boxShadow: '0 8px 32px rgba(201,168,76,0.25)' }} />
        <div style={{ fontWeight: 800, fontSize: 26, color: '#fff', letterSpacing: '-0.5px' }}>Welcome back</div>
        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginTop: 4, marginBottom: 36 }}>Sign in to continue studying</div>

        <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Email / Student ID</div>
            <input value={email} onChange={e => setEmail(e.target.value)} placeholder="arnold@students.ku.ac.ke" style={{ width: '100%', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 16px', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', boxSizing: 'border-box' }} />
          </div>
          <div>
            <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Password</div>
            <div style={{ position: 'relative' }}>
              <input type={showPass ? 'text' : 'password'} value={pass} onChange={e => setPass(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleLogin()} placeholder="••••••••" style={{ width: '100%', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 44px 13px 16px', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', boxSizing: 'border-box' }} />
              <button onClick={() => setShowPass(v => !v)} style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.4)' }}>{Ic.eye()}</button>
            </div>
          </div>
          <div style={{ textAlign: 'right' }}><span onClick={() => setScreen('forgot-password')} style={{ color: N.gold, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>Forgot password?</span></div>

          {error && (
            <div style={{ background: 'rgba(140,29,43,0.25)', border: '1px solid rgba(140,29,43,0.5)', borderRadius: 12, padding: '10px 14px', color: '#ffb4bd', fontSize: 13 }}>{error}</div>
          )}

          <button disabled={submitting} onClick={handleLogin} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: submitting ? 'default' : 'pointer', opacity: submitting ? 0.7 : 1, fontFamily: 'Plus Jakarta Sans', boxShadow: '0 6px 24px rgba(201,168,76,0.4)', marginTop: 4 }}>{submitting ? 'Signing in...' : 'Sign In'}</button>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 8 }}>
            <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.1)' }} />
            <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: 12 }}>or continue with</span>
            <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.1)' }} />
          </div>

          <button onClick={() => { window.location.href = '/auth/google' }} style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 14, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
            <span style={{ fontSize: 18 }}>G</span> Continue with Google
          </button>
        </div>

        <div style={{ marginTop: 28, color: 'rgba(255,255,255,0.5)', fontSize: 13, textAlign: 'center' }}>
          Don't have an account? <span onClick={() => setScreen('signup')} style={{ color: N.gold, fontWeight: 700, cursor: 'pointer' }}>Sign Up</span>
        </div>
      </div>
    </div>
  )
}

// ─── HOME ─────────────────────────────────────────────────────────────────────
type HomeDocument = { id: number; title: string; status: string; file_type: string | null; page_count: number | null; created_at: string | null }
type GamificationSummary = { xp_total: number; level: number; level_title: string; current_streak: number; longest_streak: number; documents_count: number; followers_count: number }

// ─── Social (Chunk 12) ─────────────────────────────────────────────────────────
// No dedicated "public user profile" endpoint exists on the backend beyond
// follow-summary - display_name for a profile you're VIEWING (not your own)
// has to be carried along from wherever the navigation originated (a follow
// list row, a notification body, etc) rather than fetched fresh. This is a
// known backend gap, not something to fabricate around.
type FollowSummary = { user_id: number; followers_count: number; following_count: number; is_following: boolean; is_followed_by: boolean }
type FollowListUser = { user_id: number; display_name: string; is_following: boolean }

function HomeScreen({ setScreen, setActiveDocumentId }: { setScreen: (s: Screen) => void; setActiveDocumentId: (id: number | null) => void }) {
  const [notifCount, setNotifCount] = useState(0)
  const loading = useLoading(1200)

  const [displayName, setDisplayName] = useState<string | null>(null)
  const [documents, setDocuments] = useState<HomeDocument[]>([])
  const [docsLoading, setDocsLoading] = useState(true)
  const [summary, setSummary] = useState<GamificationSummary | null>(null)

  useEffect(() => {
    api<{ display_name: string | null }>('/me')
      .then(me => setDisplayName(me.display_name))
      .catch(() => {})
    api<{ documents: HomeDocument[] }>('/documents')
      .then(res => setDocuments(res.documents))
      .catch(() => {})
      .finally(() => setDocsLoading(false))
    api<GamificationSummary>('/gamification/summary')
      .then(setSummary)
      .catch(() => {})
    api<{ unread_count: number }>('/notifications/unread-count')
      .then(r => setNotifCount(r.unread_count))
      .catch(() => {})
  }, [])

  const greetingName = displayName || 'there'
  const activeDocs = documents.filter(d => !docsLoading)
  const featuredDoc = activeDocs[0]
  const restDocs = activeDocs.slice(1)

  if (loading) return <SkeletonHome />
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      {/* Header */}
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <img src={logoImg} alt="Prepza" style={{ width: 36, height: 36, borderRadius: 10 }} />
            <div>
              <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11, fontWeight: 500 }}>Good morning,</div>
              <div style={{ color: '#fff', fontSize: 17, fontWeight: 800, letterSpacing: '-0.3px' }}>{greetingName} 👋</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setScreen('ai-tutor')} style={{ width: 38, height: 38, background: 'rgba(201,168,76,0.14)', border: '1px solid rgba(201,168,76,0.28)', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <div style={{ color: N.gold, fontSize: 18 }}>✦</div>
            </button>
            <button onClick={() => setScreen('notifications')} style={{ position: 'relative', width: 38, height: 38, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <div style={{ color: '#fff' }}>{Ic.bell()}</div>
              {notifCount > 0 && <div style={{ position: 'absolute', top: 7, right: 7, width: 8, height: 8, background: N.gold, borderRadius: '50%', border: `1.5px solid ${N.navy}` }} />}
            </button>
          </div>
        </div>
        {/* Streak */}
        <div style={{ background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.22)', borderRadius: 14, padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 20 }}>🔥</span>
          <div style={{ flex: 1 }}>
            <div style={{ color: N.gold, fontWeight: 800, fontSize: 13 }}>
              {summary ? `${summary.current_streak}-Day Streak${summary.current_streak > 0 ? ' — Keep it up!' : ''}` : 'Loading streak...'}
            </div>
            <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11 }}>Study 30 mins today to extend it</div>
          </div>
          {summary && <Pill text={`${summary.xp_total.toLocaleString()} XP`} color={N.gold} />}
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 24, paddingBottom: 24 }}>
        {/* Continue Studying */}
        <section style={{ padding: '20px 18px 0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontWeight: 800, fontSize: 15, color: N.navy }}>Continue Studying</span>
            <span onClick={() => setScreen('library')} style={{ fontSize: 12, color: N.gold, fontWeight: 700, cursor: 'pointer' }}>My Library →</span>
          </div>
          {docsLoading ? (
            <div style={{ fontSize: 12, color: '#9CA3AF', padding: '12px 0' }}>Loading your documents...</div>
          ) : !featuredDoc ? (
            <div onClick={() => setScreen('upload')} style={{ background: '#fff', borderRadius: 14, padding: '18px 16px', textAlign: 'center', cursor: 'pointer', border: '1px dashed rgba(0,0,0,0.15)' }}>
              <div style={{ fontSize: 12, color: '#6B7280', fontWeight: 600 }}>No documents yet — upload one to get started 📤</div>
            </div>
          ) : (
            <>
              {/* Featured doc */}
              <div onClick={() => { setActiveDocumentId(featuredDoc.id); setScreen('document-study') }} style={{ background: `linear-gradient(135deg,${N.navy},${N.navy3})`, borderRadius: 18, padding: 18, cursor: 'pointer', position: 'relative', overflow: 'hidden', marginBottom: 10 }}>
                <div style={{ position: 'absolute', right: -20, top: -20, width: 120, height: 120, background: 'rgba(201,168,76,0.07)', borderRadius: '50%' }} />
                <div style={{ display: 'flex', gap: 14, alignItems: 'center', marginBottom: 14 }}>
                  <div style={{ width: 48, height: 48, background: 'rgba(201,168,76,0.15)', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, color: N.gold, fontWeight: 800 }}>📄</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 800, fontSize: 14, color: '#fff' }} className="line-clamp-1">{featuredDoc.title}</div>
                    <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', marginTop: 2, textTransform: 'capitalize' }}>{featuredDoc.status}</div>
                  </div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <button onClick={e => { e.stopPropagation(); setActiveDocumentId(featuredDoc.id); setScreen('document-study') }} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 11, border: 'none', borderRadius: 10, padding: '6px 14px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Continue →</button>
                </div>
              </div>
              {/* Other docs */}
              {restDocs.map(d => (
                <div key={d.id} onClick={() => { setActiveDocumentId(d.id); setScreen('document-study') }} style={{ background: '#fff', borderRadius: 14, padding: '12px 14px', marginBottom: 8, boxShadow: '0 2px 10px rgba(0,0,0,0.05)', display: 'flex', gap: 12, alignItems: 'center', cursor: 'pointer', border: '1px solid rgba(0,0,0,0.04)' }}>
                  <div style={{ width: 40, height: 40, background: N.gold + '18', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, color: N.gold, fontWeight: 800 }}>📄</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 12, color: N.navy }} className="line-clamp-1">{d.title}</div>
                    <div style={{ fontSize: 11, color: '#6B7280', textTransform: 'capitalize' }}>{d.status}</div>
                  </div>
                </div>
              ))}
            </>
          )}
        </section>

        {/* AI Study Tools */}
        <section style={{ padding: '0 18px' }}>
          <div style={{ fontWeight: 800, fontSize: 15, color: N.navy, marginBottom: 14 }}>AI Study Tools</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 8 }}>
            {[
              { icon: '📤', label: 'Upload', action: () => setScreen('upload') },
              { icon: '✦', label: 'AI Tutor', action: () => setScreen('ai-tutor') },
              { icon: '🃏', label: 'Flashcards', action: () => setScreen('flashcards') },
              { icon: '📝', label: 'Practice', action: () => setScreen('quiz') },
              { icon: '🎙️', label: 'Podcasts', action: () => setScreen('podcast-player') },
            ].map((t, i) => (
              <button key={i} onClick={t.action} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                <div style={{ width: 52, height: 52, borderRadius: 16, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, border: '1px solid rgba(201,168,76,0.15)' }}>{t.icon}</div>
                <span style={{ fontSize: 10, fontWeight: 600, color: '#6B7280', fontFamily: 'Plus Jakarta Sans' }}>{t.label}</span>
              </button>
            ))}
          </div>
        </section>

        {/* Podcasts */}
        <section>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 18px', marginBottom: 12 }}>
            <span style={{ fontWeight: 800, fontSize: 15, color: N.navy }}>Study Podcasts 🎙️</span>
            <span onClick={() => setScreen('podcast-library')} style={{ fontSize: 12, color: N.gold, fontWeight: 700, cursor: 'pointer' }}>See all →</span>
          </div>
          <div style={{ display: 'flex', gap: 12, padding: '0 18px', overflowX: 'auto' }} className="scrollbar-hide">
            {podcasts.map(p => (
              <div key={p.id} onClick={() => setScreen('podcast-player')} style={{ flexShrink: 0, width: 140, borderRadius: 16, overflow: 'hidden', boxShadow: '0 4px 14px rgba(0,0,0,0.09)', cursor: 'pointer' }}>
                <div style={{ height: 90, background: `linear-gradient(135deg,${p.color},${p.color}99)`, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', fontSize: 28, color: '#fff', fontWeight: 800 }}>{p.icon}</div>
                <div style={{ background: '#fff', padding: '10px 10px 12px' }}>
                  <div style={{ fontWeight: 700, fontSize: 12, color: N.navy, marginBottom: 2 }} className="line-clamp-1">{p.title}</div>
                  <div style={{ fontSize: 10, color: '#6B7280', marginBottom: 5 }}>{p.subject}</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <div style={{ color: p.color }}>{Ic.play('w-3 h-3')}</div>
                    <span style={{ fontSize: 10, color: p.color, fontWeight: 700 }}>{p.duration}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Community */}
        <section style={{ padding: '0 18px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontWeight: 800, fontSize: 15, color: N.navy }}>Community</span>
            <span onClick={() => setScreen('forum')} style={{ fontSize: 12, color: N.gold, fontWeight: 700, cursor: 'pointer' }}>See all →</span>
          </div>
          {forumPosts.slice(0, 2).map(p => <ForumCard key={p.id} post={p} setScreen={setScreen} />)}
        </section>

        {/* Opportunities */}
        <section style={{ padding: '0 18px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontWeight: 800, fontSize: 15, color: N.navy }}>Opportunities 🚀</span>
            <span onClick={() => setScreen('opportunities')} style={{ fontSize: 12, color: N.gold, fontWeight: 700, cursor: 'pointer' }}>See all →</span>
          </div>
          {opportunities.slice(0, 2).map(o => (
            <OppCard key={o.id} opp={o} setScreen={setScreen} />
          ))}
        </section>
      </div>
    </div>
  )
}

// ─── SHARED CARDS ─────────────────────────────────────────────────────────────
function ForumCard({ post, setScreen }: { post: typeof forumPosts[0]; setScreen: (s: Screen) => void }) {
  const [liked, setLiked] = useState(post.liked)
  const [saved, setSaved] = useState(post.saved)
  return (
    <div style={{ background: '#fff', borderRadius: 16, padding: '14px 16px', marginBottom: 10, boxShadow: '0 2px 10px rgba(0,0,0,0.05)', border: '1px solid rgba(0,0,0,0.04)' }}>
      <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
        <Avi name={post.avatar} size={38} />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>{post.user}</div>
          <div style={{ fontSize: 11, color: '#9CA3AF' }}>{post.course} · {post.time}</div>
        </div>
        <Pill text={post.tag} />
      </div>
      <p style={{ fontSize: 13, color: '#374151', lineHeight: 1.65, margin: '0 0 12px' }}>{post.content}</p>
      <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
        <button onClick={() => setLiked(v => !v)} style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'none', border: 'none', cursor: 'pointer', color: liked ? '#C94C4C' : '#9CA3AF', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>
          {Ic.heart('w-4 h-4')} {post.likes + (liked ? 1 : 0)}
        </button>
        <button onClick={() => setScreen('comments')} style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'none', border: 'none', cursor: 'pointer', color: '#9CA3AF', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>
          {Ic.comment('w-4 h-4')} {post.comments}
        </button>
        <div style={{ flex: 1 }} />
        <button onClick={() => setSaved(v => !v)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: saved ? N.gold : '#9CA3AF' }}>{Ic.bookmark('w-4 h-4')}</button>
        <button onClick={() => setScreen('share-sheet')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9CA3AF' }}>{Ic.share('w-4 h-4')}</button>
      </div>
    </div>
  )
}

// Real, per-unit ForumPost card - separate from the mock ForumCard above
// (still used by the Home screen's preview strip) since ForumPost has no
// like feature and a different shape than the mock forumPosts data.
function RealForumCard({ post, onOpen }: { post: ForumPostSummary; onOpen: () => void }) {
  return (
    <div onClick={onOpen} style={{ background: '#fff', borderRadius: 16, padding: '14px 16px', marginBottom: 10, boxShadow: '0 2px 10px rgba(0,0,0,0.05)', border: '1px solid rgba(0,0,0,0.04)', cursor: 'pointer' }}>
      <div style={{ display: 'flex', gap: 10, marginBottom: 8 }}>
        <Avi name={post.author.slice(0, 2).toUpperCase()} size={38} />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>{post.author}</div>
          <div style={{ fontSize: 11, color: '#9CA3AF' }}>{post.created_at ? new Date(post.created_at).toLocaleString() : ''}</div>
        </div>
      </div>
      <div style={{ fontWeight: 800, fontSize: 14, color: N.navy, marginBottom: 4 }}>{post.title}</div>
      <p style={{ fontSize: 13, color: '#374151', lineHeight: 1.65, margin: '0 0 12px' }} className="line-clamp-2">{post.body}</p>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', color: '#9CA3AF', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>
        {Ic.comment('w-4 h-4')} {post.reply_count} {post.reply_count === 1 ? 'reply' : 'replies'}
        <span style={{ flex: 1 }} />
        <span style={{ color: N.gold, fontWeight: 700 }}>Ask Prepza AI →</span>
      </div>
    </div>
  )
}

function OppCard({ opp, setScreen }: { opp: typeof opportunities[0]; setScreen: (s: Screen) => void }) {
  const [saved, setSaved] = useState(false)
  return (
    <div onClick={() => setScreen('opportunity-detail')} style={{ background: '#fff', borderRadius: 16, padding: '14px 16px', marginBottom: 10, boxShadow: '0 2px 10px rgba(0,0,0,0.05)', display: 'flex', gap: 12, alignItems: 'center', cursor: 'pointer', border: '1px solid rgba(0,0,0,0.04)' }}>
      <div style={{ width: 44, height: 44, background: opp.color + '18', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0 }}>
        {opp.type === 'Internship' ? '💼' : opp.type === 'Scholarship' ? '🎓' : opp.type === 'Competition' ? '🏆' : opp.type === 'Job' ? '📋' : '🎪'}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 700, fontSize: 13, color: N.navy }} className="line-clamp-1">{opp.title}</div>
        <div style={{ fontSize: 11, color: '#6B7280' }}>{opp.org}</div>
        <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 2 }}>📍 {opp.location} · ⏰ {opp.deadline}</div>
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <Pill text={opp.tag} color={opp.color} />
        <div style={{ fontSize: 11, fontWeight: 800, color: opp.color, marginTop: 4 }}>{opp.reward}</div>
      </div>
    </div>
  )
}

// ─── EXPLORE ──────────────────────────────────────────────────────────────────
function ExploreScreen({ setScreen, setActiveGroupId }: { setScreen: (s: Screen) => void; setActiveGroupId: (id: number) => void }) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('All')
  const [following, setFollowing] = useState<string[]>([])
  const loading = useLoading(1000)
  const filters = ['All','Notes','Past Papers','AI Content','Groups','Opportunities','Forums','Students']

  const [groups, setGroups] = useState<GroupSummary[]>([])
  const [loadingGroups, setLoadingGroups] = useState(false)
  const [groupsError, setGroupsError] = useState('')
  const [joiningGroupId, setJoiningGroupId] = useState<number | null>(null)
  const [csrfToken, setCsrfToken] = useState('')

  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  useEffect(() => {
    if (filter !== 'All' && filter !== 'Groups') return
    setLoadingGroups(true); setGroupsError('')
    const params = new URLSearchParams()
    if (query.trim()) params.set('q', query.trim())
    api<{ page: number; groups: GroupSummary[] }>(`/groups?${params.toString()}`)
      .then(res => setGroups(res.groups))
      .catch(() => setGroupsError('Could not load groups.'))
      .finally(() => setLoadingGroups(false))
  }, [filter, query])

  const quickJoin = async (g: GroupSummary) => {
    if (joiningGroupId != null) return
    setJoiningGroupId(g.id)
    try {
      await api(`/groups/${g.id}/join`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      setGroups(gs => gs.map(x => x.id === g.id ? { ...x, is_member: true, member_count: x.is_member ? x.member_count : x.member_count + 1 } : x))
    } catch { /* surfaced inline is overkill for a quick-join button; card still lets them open the group */ }
    finally { setJoiningGroupId(null) }
  }

  const openGroup = (id: number) => { setActiveGroupId(id); setScreen('group-detail') }
  const students = [
    { name: 'Wanjiru Kamau', course: 'Computer Science', year: 'Y2', xp: 3100, initials: 'WK' },
    { name: 'Brian Omondi', course: 'B.Com Finance', year: 'Y3', xp: 2240, initials: 'BO' },
    { name: 'Aisha Mohamed', course: 'LLB Law', year: 'Y2', xp: 1870, initials: 'AM' },
  ]
  const docs = [
    { title: 'ACT 101 Lecture Notes – Week 1-6', by: 'Prof. Kamau', dept: 'Actuarial Science', pages: 38, downloads: 312, type: 'PDF' },
    { title: 'KU Past Papers 2020-2023 (MAT 101)', by: 'Student Library', dept: 'Mathematics', pages: 72, downloads: 891, type: 'PDF' },
    { title: 'STA 101 Probability Slides', by: 'Dr. Njuguna', dept: 'Statistics', pages: 44, downloads: 567, type: 'PPT' },
    { title: 'Interest Theory – Study Guide', by: 'Arnold Gichuru', dept: 'Actuarial Science', pages: 12, downloads: 148, type: 'PDF' },
  ]
  const filtered = filter === 'All' ? docs : filter === 'Notes' ? docs.filter(d => d.by.includes('Prof') || d.by.includes('Dr')) : filter === 'Past Papers' ? docs.filter(d => d.title.includes('Past')) : docs
  if (loading) return <SkeletonExplore />
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ fontWeight: 800, fontSize: 20, color: '#fff', marginBottom: 12 }}>Explore</div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', background: 'rgba(255,255,255,0.09)', borderRadius: 13, padding: '10px 14px', border: '1px solid rgba(255,255,255,0.1)' }}>
          <div style={{ color: 'rgba(255,255,255,0.4)' }}>{Ic.search()}</div>
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search notes, papers, students..." style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: 13, fontFamily: 'Plus Jakarta Sans' }} />
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 12, overflowX: 'auto', paddingBottom: 2 }} className="scrollbar-hide">
          {filters.map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{ flexShrink: 0, padding: '6px 14px', borderRadius: 20, background: filter === f ? N.gold : 'rgba(255,255,255,0.1)', color: filter === f ? N.navy : 'rgba(255,255,255,0.65)', fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{f}</button>
          ))}
        </div>
      </div>

      <div style={{ padding: '20px 18px', display: 'flex', flexDirection: 'column', gap: 24 }}>
        {/* Trending */}
        {(filter === 'All' || filter === 'Notes' || filter === 'Past Papers') && (
          <div>
            <div style={{ fontWeight: 800, fontSize: 14, color: N.navy, marginBottom: 12 }}>🔥 Trending at Kenyatta University</div>
            <div style={{ display: 'flex', gap: 10, overflowX: 'auto' }} className="scrollbar-hide">
              {[
                { label: 'ACT 101 Interest Theory', count: '1.2k views', icon: '∑' },
                { label: 'MAT 101 Integration', count: '980 views', icon: '∫' },
                { label: 'STA 101 Distributions', count: '876 views', icon: 'σ' },
                { label: 'ECO 101 Microeconomics', count: '644 views', icon: '📊' },
              ].map((t, i) => (
                <div key={i} onClick={() => setScreen('document-study')} style={{ flexShrink: 0, background: '#fff', borderRadius: 14, padding: '12px 14px', boxShadow: '0 2px 8px rgba(0,0,0,0.06)', minWidth: 148, cursor: 'pointer' }}>
                  <div style={{ fontWeight: 800, fontSize: 20, color: N.gold, marginBottom: 6, fontFamily: 'Plus Jakarta Sans' }}>{t.icon}</div>
                  <div style={{ fontWeight: 700, fontSize: 12, color: N.navy, marginBottom: 2 }}>{t.label}</div>
                  <div style={{ fontSize: 11, color: '#9CA3AF' }}>{t.count}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Groups */}
        {(filter === 'All' || filter === 'Groups') && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <div style={{ fontWeight: 800, fontSize: 14, color: N.navy }}>👥 Groups</div>
              <button onClick={() => setScreen('group-create')} style={{ fontSize: 12, fontWeight: 700, color: N.gold, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>+ Create</button>
            </div>
            {loadingGroups ? (
              <div style={{ fontSize: 12, color: '#9CA3AF' }}>Loading groups…</div>
            ) : groupsError ? (
              <div style={{ fontSize: 12, color: '#C94C4C' }}>{groupsError}</div>
            ) : groups.length === 0 ? (
              <div style={{ fontSize: 12, color: '#9CA3AF' }}>No groups found yet — be the first to start one.</div>
            ) : (
              groups.map(g => (
                <div key={g.id} onClick={() => openGroup(g.id)} style={{ background: '#fff', borderRadius: 14, padding: 14, marginBottom: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.04)', cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'center' }}>
                  <div style={{ width: 42, height: 42, background: `linear-gradient(135deg,${N.navy},${N.navy3})`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 14, color: N.gold, flexShrink: 0 }}>{g.name.slice(0, 2).toUpperCase()}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 12, color: N.navy }} className="line-clamp-1">{g.name}</div>
                    <div style={{ fontSize: 11, color: '#6B7280' }}>{g.unit_code ? `${g.unit_code} · ` : ''}{g.member_count} member{g.member_count === 1 ? '' : 's'}</div>
                    {g.privacy === 'course_only' && <div style={{ fontSize: 10, color: '#9CA3AF', marginTop: 2 }}>Course-only</div>}
                  </div>
                  {g.is_member ? (
                    <Pill text="Joined" color="#4CC97B" />
                  ) : (
                    <button onClick={e => { e.stopPropagation(); quickJoin(g) }} disabled={joiningGroupId === g.id} style={{ background: N.gold, color: N.navy, fontWeight: 700, fontSize: 11, border: 'none', borderRadius: 9, padding: '6px 12px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: joiningGroupId === g.id ? 0.6 : 1 }}>{joiningGroupId === g.id ? '…' : 'Join'}</button>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {/* Documents */}
        {filter !== 'Students' && filter !== 'Forums' && filter !== 'Opportunities' && filter !== 'Groups' && (
          <div>
            <div style={{ fontWeight: 800, fontSize: 14, color: N.navy, marginBottom: 12 }}>📄 {filter === 'Past Papers' ? 'Past Papers' : filter === 'Notes' ? 'Lecture Notes' : 'Recent Documents'}</div>
            {filtered.map((d, i) => (
              <div key={i} onClick={() => setScreen('document-study')} style={{ background: '#fff', borderRadius: 14, padding: 14, marginBottom: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.04)', cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'center' }}>
                <div style={{ width: 42, height: 42, background: d.type === 'PDF' ? 'rgba(201,68,68,0.1)' : 'rgba(76,123,201,0.1)', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, flexShrink: 0 }}>{d.type === 'PDF' ? '📕' : '📊'}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: 12, color: N.navy }} className="line-clamp-1">{d.title}</div>
                  <div style={{ fontSize: 11, color: '#6B7280' }}>{d.by} · {d.dept}</div>
                  <div style={{ fontSize: 10, color: '#9CA3AF', marginTop: 2 }}>{d.pages} pages · ↓ {d.downloads}</div>
                </div>
                <Pill text={d.type} />
              </div>
            ))}
          </div>
        )}

        {/* Students */}
        {(filter === 'All' || filter === 'Students') && (
          <div>
            <div style={{ fontWeight: 800, fontSize: 14, color: N.navy, marginBottom: 12 }}>👥 Students to Follow</div>
            <div style={{ display: 'flex', gap: 10, overflowX: 'auto' }} className="scrollbar-hide">
              {students.map((s, i) => (
                <div key={i} style={{ flexShrink: 0, background: '#fff', borderRadius: 16, padding: '16px 14px', boxShadow: '0 2px 8px rgba(0,0,0,0.06)', width: 148, textAlign: 'center' }}>
                  <div onClick={() => setScreen('student-profile')} style={{ cursor: 'pointer' }}>
                    <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 8 }}><Avi name={s.initials} size={48} /></div>
                    <div style={{ fontWeight: 700, fontSize: 12, color: N.navy }}>{s.name.split(' ')[0]} {s.name.split(' ')[1]}</div>
                    <div style={{ fontSize: 10, color: '#6B7280', marginBottom: 2 }}>{s.course} · {s.year}</div>
                    <div style={{ fontSize: 10, color: N.gold, fontWeight: 700 }}>⭐ {s.xp.toLocaleString()} XP</div>
                  </div>
                  <button onClick={() => setFollowing(f => f.includes(s.initials) ? f.filter(x => x !== s.initials) : [...f, s.initials])}
                    style={{ marginTop: 10, background: following.includes(s.initials) ? 'rgba(201,168,76,0.15)' : N.navy, color: following.includes(s.initials) ? N.gold : N.gold, border: following.includes(s.initials) ? `1px solid ${N.gold}44` : 'none', borderRadius: 10, padding: '6px 16px', fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
                    {following.includes(s.initials) ? 'Following ✓' : 'Follow'}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── CREATE MODAL ─────────────────────────────────────────────────────────────
function CreateModal({ setScreen }: { setScreen: (s: Screen) => void }) {
  return (
    <div style={{ flex: 1, background: N.bg, overflowY: 'auto' }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontWeight: 800, fontSize: 20, color: '#fff' }}>Create</div>
          <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: '#fff' }}>{Ic.close()}</div>
          </button>
        </div>
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {[
          { icon: '📤', label: 'Upload Document', sub: 'PDF, Word, PowerPoint, Images, Notes', action: () => setScreen('upload'), gold: true },
          { icon: '📖', label: 'Publish to Prepza Library', sub: 'Share educational materials · Earn XP', action: () => setScreen('publish-library') },
          { icon: '💬', label: 'Create Group Post', sub: 'Share in a group or course community', action: () => setScreen('post-composer') },
          { icon: '❓', label: 'Ask a Question', sub: 'Get help from the community', action: () => setScreen('question-composer') },
          { icon: '👥', label: 'Create Group', sub: 'Start a course or study group', action: () => setScreen('group-create') },
          { icon: '🚀', label: 'Share Opportunity', sub: 'Jobs, internships, scholarships, events', action: () => setScreen('share-opp-form') },
        ].map((item, i) => (
          <button key={i} onClick={item.action} style={{ display: 'flex', alignItems: 'center', gap: 14, background: '#fff', border: item.gold ? `2px solid ${N.gold}44` : '1px solid rgba(0,0,0,0.05)', borderRadius: 16, padding: 16, cursor: 'pointer', textAlign: 'left', boxShadow: item.gold ? `0 4px 20px rgba(201,168,76,0.12)` : '0 2px 8px rgba(0,0,0,0.04)', fontFamily: 'Plus Jakarta Sans' }}>
            <div style={{ width: 50, height: 50, borderRadius: 15, background: item.gold ? `linear-gradient(135deg,${N.gold},${N.goldL})` : `linear-gradient(135deg,${N.navy2},${N.navy3})`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, flexShrink: 0 }}>{item.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 800, fontSize: 14, color: N.navy, marginBottom: 3 }}>{item.label}</div>
              <div style={{ fontSize: 12, color: '#6B7280' }}>{item.sub}</div>
            </div>
            {item.gold && <Pill text="CORE" />}
          </button>
        ))}
      </div>
    </div>
  )
}

// ─── POST COMPOSER ────────────────────────────────────────────────────────────
function PostComposer({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [units, setUnits] = useState<UnitOption[]>([])
  const [unitId, setUnitId] = useState<number | null>(null)
  const [csrfToken, setCsrfToken] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api<UnitOption[]>('/units').then(u => { setUnits(u); if (u.length) setUnitId(u[0].id) }).catch(() => setError('Could not load your units.'))
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
  }, [])

  const submit = async () => {
    if (!unitId || !title.trim() || !text.trim() || submitting) return
    setSubmitting(true); setError('')
    try {
      await api('/forum/posts', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ unit_id: unitId, title: title.trim(), body: text.trim() }),
      })
      setScreen('forum')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not post. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('create-modal')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.close()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>New Post</span>
          <button onClick={submit} disabled={submitting || !unitId || !title.trim() || !text.trim()} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 13, border: 'none', borderRadius: 12, padding: '8px 18px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: (submitting || !unitId || !title.trim() || !text.trim()) ? 0.5 : 1 }}>{submitting ? 'Posting…' : 'Post'}</button>
        </div>
      </div>
      <div style={{ flex: 1, padding: 18, display: 'flex', flexDirection: 'column', gap: 14, overflowY: 'auto' }} className="scrollbar-hide">
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <Avi name="AG" size={40} />
          <div>
            <div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>{USER.name}</div>
            <div style={{ fontSize: 11, color: '#6B7280' }}>{USER.course} · {USER.year}</div>
          </div>
        </div>
        {error && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600 }}>{error}</div>}
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 8 }}>Unit</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {units.map(u => (
              <button key={u.id} onClick={() => setUnitId(u.id)} style={{ padding: '7px 14px', borderRadius: 20, background: unitId === u.id ? N.navy : '#F3F4F6', color: unitId === u.id ? N.gold : '#6B7280', fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{u.code}</button>
            ))}
          </div>
        </div>
        <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Title" maxLength={200} style={{ width: '100%', border: '1px solid rgba(0,0,0,0.1)', outline: 'none', fontSize: 14, fontWeight: 700, color: N.navy, fontFamily: 'Plus Jakarta Sans', background: '#fff', borderRadius: 12, padding: '12px 14px', boxSizing: 'border-box' }} />
        <textarea value={text} onChange={e => setText(e.target.value)} placeholder="Share a study tip, ask for help, or start a discussion..." rows={6} style={{ width: '100%', border: '1px solid rgba(0,0,0,0.1)', outline: 'none', fontSize: 14, color: '#374151', fontFamily: 'Plus Jakarta Sans', resize: 'none', background: '#fff', lineHeight: 1.7, borderRadius: 12, padding: 14, boxSizing: 'border-box' }} />
      </div>
    </div>
  )
}

// ─── QUESTION COMPOSER ────────────────────────────────────────────────────────
function QuestionComposer({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [title, setTitle] = useState('')
  const [q, setQ] = useState('')
  const [units, setUnits] = useState<UnitOption[]>([])
  const [unitId, setUnitId] = useState<number | null>(null)
  const [csrfToken, setCsrfToken] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api<UnitOption[]>('/units').then(u => { setUnits(u); if (u.length) setUnitId(u[0].id) }).catch(() => setError('Could not load your units.'))
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
  }, [])

  const submit = async () => {
    if (!unitId || !title.trim() || !q.trim() || submitting) return
    setSubmitting(true); setError('')
    try {
      await api('/forum/posts', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ unit_id: unitId, title: title.trim(), body: q.trim() }),
      })
      setScreen('forum')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not post. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('create-modal')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.close()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Ask a Question</span>
          <button onClick={submit} disabled={submitting || !unitId || !title.trim() || !q.trim()} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 13, border: 'none', borderRadius: 12, padding: '8px 18px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: (submitting || !unitId || !title.trim() || !q.trim()) ? 0.5 : 1 }}>{submitting ? 'Posting…' : 'Post'}</button>
        </div>
      </div>
      <div style={{ flex: 1, padding: 18, display: 'flex', flexDirection: 'column', gap: 16, overflowY: 'auto' }} className="scrollbar-hide">
        {error && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600 }}>{error}</div>}
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 8 }}>Unit</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {units.map(u => (
              <button key={u.id} onClick={() => setUnitId(u.id)} style={{ padding: '7px 14px', borderRadius: 20, background: unitId === u.id ? N.navy : '#F3F4F6', color: unitId === u.id ? N.gold : '#6B7280', fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{u.code}</button>
            ))}
          </div>
        </div>
        <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Title" maxLength={200} style={{ width: '100%', border: '1px solid rgba(0,0,0,0.1)', outline: 'none', fontSize: 14, fontWeight: 700, color: N.navy, fontFamily: 'Plus Jakarta Sans', background: '#fff', borderRadius: 12, padding: '12px 14px', boxSizing: 'border-box' }} />
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>Your question</div>
          <textarea value={q} onChange={e => setQ(e.target.value)} placeholder="e.g. Can someone explain the difference between annuity-immediate and annuity-due?" rows={5} style={{ width: '100%', border: '1px solid rgba(0,0,0,0.1)', outline: 'none', fontSize: 14, color: '#374151', fontFamily: 'Plus Jakarta Sans', resize: 'none', background: '#fff', lineHeight: 1.7, borderRadius: 14, padding: 14, boxSizing: 'border-box' }} />
        </div>
        <div style={{ background: 'rgba(201,168,76,0.08)', border: `1px solid ${N.gold}30`, borderRadius: 14, padding: 14 }}>
          <div style={{ fontSize: 12, color: N.gold, fontWeight: 700, marginBottom: 4 }}>✦ Try Prepza AI first</div>
          <div style={{ fontSize: 12, color: '#6B7280' }}>Your AI tutor might already know the answer. <span onClick={() => setScreen('ai-tutor')} style={{ color: N.gold, fontWeight: 700, cursor: 'pointer' }}>Ask AI instead →</span></div>
        </div>
      </div>
    </div>
  )
}

// ─── SHARE OPP FORM ───────────────────────────────────────────────────────────
function ShareOppForm({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [form, setForm] = useState({ title: '', org: '', type: 'Internship', deadline: '', location: '', reward: '', desc: '', link: '' })
  const upd = (k: string) => (e: React.ChangeEvent<HTMLInputElement|HTMLTextAreaElement|HTMLSelectElement>) => setForm(f => ({ ...f, [k]: e.target.value }))
  const inp = (placeholder: string, key: string, type?: string) => (
    <input type={type ?? 'text'} placeholder={placeholder} value={(form as any)[key]} onChange={upd(key)} style={{ width: '100%', border: '1px solid rgba(0,0,0,0.1)', borderRadius: 12, padding: '12px 14px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: '#374151', background: '#fff', boxSizing: 'border-box' }} />
  )
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('create-modal')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Share Opportunity</span>
          <button onClick={() => setScreen('opportunities')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 13, border: 'none', borderRadius: 12, padding: '8px 18px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Post</button>
        </div>
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
        {[['Title', 'title'], ['Organisation', 'org'], ['Location', 'location'], ['Reward / Stipend (e.g. KES 35,000/mo)', 'reward'], ['Application Link', 'link']].map(([p, k]) => (
          <div key={k}><div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>{p}</div>{inp(p as string, k as string)}</div>
        ))}
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>Category</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {['Internship','Scholarship','Competition','Job','Event'].map(c => (
              <button key={c} onClick={() => setForm(f => ({ ...f, type: c }))} style={{ padding: '7px 14px', borderRadius: 20, background: form.type === c ? N.navy : '#F3F4F6', color: form.type === c ? N.gold : '#6B7280', fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{c}</button>
            ))}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>Deadline</div>
          {inp('e.g. Sep 30, 2025', 'deadline')}
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>Description</div>
          <textarea value={form.desc} onChange={upd('desc')} placeholder="Describe the opportunity, requirements, and how to apply..." rows={4} style={{ width: '100%', border: '1px solid rgba(0,0,0,0.1)', borderRadius: 12, padding: '12px 14px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', resize: 'none', outline: 'none', color: '#374151', background: '#fff', lineHeight: 1.7, boxSizing: 'border-box' }} />
        </div>
      </div>
    </div>
  )
}

// ─── EDU UPLOAD FORM ──────────────────────────────────────────────────────────
function EduUploadForm({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [type, setType] = useState('Notes')
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <TopBar title="Upload Educational Content" onBack={() => setScreen('create-modal')} />
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 8 }}>Content Type</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {['Notes','Summary','Guide','Past Paper','Cheat Sheet','Other'].map(t => (
              <button key={t} onClick={() => setType(t)} style={{ padding: '7px 14px', borderRadius: 20, background: type === t ? N.navy : '#F3F4F6', color: type === t ? N.gold : '#6B7280', fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{t}</button>
            ))}
          </div>
        </div>
        {[['Title', 'e.g. ACT 101 Interest Theory – Complete Notes'], ['Unit / Course', 'e.g. ACT 101'], ['University', 'e.g. Kenyatta University']].map(([l, p]) => (
          <div key={l}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>{l}</div>
            <input placeholder={p} style={{ width: '100%', border: '1px solid rgba(0,0,0,0.1)', borderRadius: 12, padding: '12px 14px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: '#374151', boxSizing: 'border-box' }} />
          </div>
        ))}
        <button onClick={() => setScreen('upload')} style={{ background: `linear-gradient(135deg,${N.navy},${N.navy3})`, color: N.gold, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Select & Upload File →</button>
      </div>
    </div>
  )
}

// ─── UPLOAD ───────────────────────────────────────────────────────────────────
function UploadScreen({ setScreen, setActiveDocumentId }: { setScreen: (s: Screen) => void; setActiveDocumentId: (id: number | null) => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadStage, setUploadStage] = useState('')
  const [error, setError] = useState('')

  const startUpload = async (file: File) => {
    setError('')

    const ext = getFileExtension(file.name)
    if (!ext || !ALLOWED_UPLOAD_EXTENSIONS.includes(ext)) {
      setError(`Unsupported file type. Allowed: ${ALLOWED_UPLOAD_EXTENSIONS.join(', ').toUpperCase()}`)
      return
    }
    if (file.size > MAX_UPLOAD_SIZE_BYTES) {
      setError(`File exceeds the ${MAX_UPLOAD_SIZE_BYTES / (1024 * 1024)} MB limit`)
      return
    }

    setUploading(true)
    try {
      setUploadStage('Hashing file...')
      const contentHash = await sha256Hex(file)

      setUploadStage('Registering upload...')
      const me = await api<{ csrf_token: string }>('/me')
      const title = file.name.includes('.') ? file.name.slice(0, file.name.lastIndexOf('.')) : file.name

      const created = await api<{
        document_id: number; status: string; duplicate: boolean
        upload_url?: string; storage_path?: string
      }>('/documents', {
        method: 'POST',
        headers: { 'X-CSRF-Token': me.csrf_token },
        body: JSON.stringify({
          title,
          original_filename: file.name,
          file_size_bytes: file.size,
          content_hash: contentHash,
        }),
      })

      if (!created.duplicate && created.upload_url) {
        setUploadStage('Uploading file...')
        const putRes = await fetch(created.upload_url, { method: 'PUT', body: file })
        if (!putRes.ok) throw new Error('Upload to storage failed - please try again')

        setUploadStage('Confirming upload...')
        try {
          await api(`/documents/${created.document_id}/uploaded`, {
            method: 'POST',
            headers: { 'X-CSRF-Token': me.csrf_token },
          })
        } catch (e) {
          if (e instanceof ApiError && e.status === 409) {
            await new Promise(r => setTimeout(r, 1500))
            await api(`/documents/${created.document_id}/uploaded`, {
              method: 'POST',
              headers: { 'X-CSRF-Token': me.csrf_token },
            })
          } else {
            throw e
          }
        }
      }

      setActiveDocumentId(created.document_id)
      setScreen('processing')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'Upload failed - please check your connection and try again.')
    } finally {
      setUploading(false)
      setUploadStage('')
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) startUpload(file)
    e.target.value = ''
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <TopBar title="Upload Document" onBack={() => setScreen('home')} />
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', marginTop: -8 }}>Prepza AI processes your document instantly</div>
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 18 }}>
        {error && (
          <div style={{ background: 'rgba(201,68,68,0.08)', border: '1px solid rgba(201,68,68,0.25)', borderRadius: 12, padding: '12px 14px', color: '#C94C4C', fontSize: 12, fontWeight: 600 }}>{error}</div>
        )}
        <div
          onDragOver={e => { e.preventDefault(); if (!uploading) setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={e => { e.preventDefault(); setDragging(false); const file = e.dataTransfer.files?.[0]; if (file && !uploading) startUpload(file) }}
          onClick={() => !uploading && fileRef.current?.click()}
          style={{ border: `2px dashed ${dragging ? N.gold : 'rgba(11,20,55,0.18)'}`, borderRadius: 20, padding: '40px 20px', textAlign: 'center', background: dragging ? 'rgba(201,168,76,0.04)' : '#fff', cursor: uploading ? 'wait' : 'pointer', opacity: uploading ? 0.7 : 1, transition: 'all 0.2s' }}
        >
          <input ref={fileRef} type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png" style={{ display: 'none' }} onChange={handleFileChange} disabled={uploading} />
          <div style={{ fontSize: 48, marginBottom: 12 }}>{uploading ? '⏳' : '📤'}</div>
          <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 6 }}>{uploading ? (uploadStage || 'Uploading...') : 'Drop your file here'}</div>
          {!uploading && <div style={{ fontSize: 13, color: '#6B7280', marginBottom: 16 }}>or tap to browse from your device</div>}
          {!uploading && (
            <div style={{ display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap' }}>
              {['PDF','Word','PowerPoint','JPG','PNG'].map(t => <span key={t} style={{ background: '#F3F4F6', color: '#374151', fontSize: 10, fontWeight: 600, padding: '4px 10px', borderRadius: 20 }}>{t}</span>)}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── PROCESSING ───────────────────────────────────────────────────────────────
function ProcessingScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [pollError, setPollError] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>

    const poll = async () => {
      try {
        const result = await api<DocumentDetail>(`/documents/${activeDocumentId}`)
        if (cancelled) return
        setDoc(result)
        if (result.status === 'ready' || result.status === 'failed') return
        timer = setTimeout(poll, 2500)
      } catch (e) {
        if (cancelled) return
        setPollError(e instanceof ApiError ? e.message : 'Lost connection while checking status - retrying...')
        timer = setTimeout(poll, 2500)
      }
    }
    poll()

    return () => { cancelled = true; clearTimeout(timer) }
  }, [activeDocumentId])

  const status = doc?.status
  const stageLabel = status === 'uploading' ? 'Uploading document…'
    : status === 'processing' ? 'Extracting content & analysing…'
    : status === 'ready' ? 'Ready to study!'
    : status === 'failed' ? 'Something went wrong'
    : 'Getting started…'

  if (activeDocumentId == null) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.navy, padding: 32, textAlign: 'center' }}>
        <div style={{ color: '#fff', fontWeight: 800, fontSize: 18, marginBottom: 10 }}>No upload in progress</div>
        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginBottom: 28 }}>Head back to upload a document to see its processing status here.</div>
        <button onClick={() => setScreen('upload')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '12px 28px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Go to Upload</button>
      </div>
    )
  }

  if (status === 'failed') {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.navy, padding: 32, textAlign: 'center' }}>
        <div style={{ fontSize: 44, marginBottom: 16 }}>⚠️</div>
        <div style={{ color: '#fff', fontWeight: 800, fontSize: 18, marginBottom: 10 }}>Processing failed</div>
        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginBottom: 28, maxWidth: 280 }}>{doc?.error_message || 'This document could not be processed. Please try uploading again.'}</div>
        <button onClick={() => setScreen('upload')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '12px 28px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Try Again</button>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.navy, padding: 32 }}>
      <div style={{ position: 'relative', width: 120, height: 120, marginBottom: 36 }}>
        <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: '3px solid rgba(201,168,76,0.18)' }} />
        <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: '3px solid transparent', borderTopColor: N.gold, animation: 'spin-slow 1.1s linear infinite' }} />
        <div style={{ position: 'absolute', inset: 14, borderRadius: '50%', background: 'rgba(201,168,76,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <img src={logoImg} alt="Prepza" style={{ width: 52, height: 52, borderRadius: 14 }} />
        </div>
      </div>
      <div style={{ color: '#fff', fontWeight: 800, fontSize: 20, marginBottom: 6, textAlign: 'center' }}>{stageLabel}</div>
      <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 13, textAlign: 'center', marginBottom: 20 }}>{doc?.title || 'Your document'}</div>
      {pollError && <div style={{ color: '#E8A54C', fontSize: 12, marginBottom: 20, textAlign: 'center' }}>{pollError}</div>}
      {status === 'ready' && (
        <button onClick={() => setScreen('doc-ready')} style={{ marginTop: 12, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 44px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 4px 20px rgba(201,168,76,0.4)' }}>
          View Document →
        </button>
      )}
    </div>
  )
}

// ─── DOC READY ────────────────────────────────────────────────────────────────
function DocReadyScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) return
    api<DocumentDetail>(`/documents/${activeDocumentId}`)
      .then(setDoc)
      .catch(e => setLoadError(e instanceof ApiError ? e.message : 'Could not load document details.'))
  }, [activeDocumentId])

  const actions: { icon: string; label: string; sub: string; dest: Screen }[] = [
    { icon: '🤖', label: 'Study with AI', sub: 'Ask questions about this doc', dest: 'document-study' },
    { icon: '❓', label: 'Ask Questions', sub: 'AI answers from your notes', dest: 'ai-tutor' },
    { icon: '📝', label: 'Summarize', sub: 'Condensed AI notes', dest: 'summary' },
    { icon: '🧠', label: 'Generate Quiz', sub: 'AI-generated practice quiz', dest: 'quiz' },
    { icon: '🃏', label: 'Flashcards', sub: 'AI-generated flashcard set', dest: 'flashcards' },
    { icon: '🎙️', label: 'Create Podcast', sub: 'AI-generated audio episode', dest: 'podcast-player' },
    { icon: '📚', label: 'Save to Library', sub: 'Access offline anytime', dest: 'library' },
  ]

  const fileTypeLabel = doc?.file_type ? doc.file_type.toUpperCase() : null
  const pageLabel = doc?.page_count != null ? `${doc.page_count} pages` : null
  const sizeLabel = doc?.file_size_bytes != null ? `${(doc.file_size_bytes / (1024 * 1024)).toFixed(1)} MB` : null
  const metaParts = [fileTypeLabel, pageLabel, sizeLabel].filter(Boolean)

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <TopBar title="Document Ready ✓" onBack={() => setScreen('home')} />
        <div style={{ background: 'rgba(76,201,123,0.12)', border: '1px solid rgba(76,201,123,0.3)', borderRadius: 14, padding: '12px 14px', display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ fontSize: 24 }}>✅</span>
          <div>
            <div style={{ color: '#4CC97B', fontWeight: 700, fontSize: 13 }}>Processing Complete!</div>
            <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11 }}>Your document is ready to study</div>
          </div>
        </div>
      </div>
      <div style={{ padding: 18 }}>
        {loadError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 14 }}>{loadError}</div>}
        {/* Doc info */}
        <div style={{ background: '#fff', borderRadius: 16, padding: 16, marginBottom: 20, boxShadow: '0 2px 10px rgba(0,0,0,0.06)', display: 'flex', gap: 14, alignItems: 'center' }}>
          <div style={{ width: 52, height: 52, background: 'rgba(201,68,68,0.1)', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26 }}>📕</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: 14, color: N.navy }} className="line-clamp-1">{doc?.title || 'Loading…'}</div>
            <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>{metaParts.length > 0 ? metaParts.join(' · ') : '—'}</div>
          </div>
        </div>
        <div style={{ fontWeight: 800, fontSize: 15, color: N.navy, marginBottom: 12 }}>What would you like to do?</div>
        {actions.map((a, i) => (
          <button key={i} onClick={() => setScreen(a.dest)} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 14, background: '#fff', border: '1px solid rgba(0,0,0,0.05)', borderRadius: 14, padding: '14px 16px', marginBottom: 8, cursor: 'pointer', textAlign: 'left', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
            <div style={{ width: 44, height: 44, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0 }}>{a.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>{a.label}</div>
              <div style={{ fontSize: 11, color: '#6B7280' }}>{a.sub}</div>
            </div>
            <div style={{ color: '#9CA3AF' }}>{Ic.chevR()}</div>
          </button>
        ))}
      </div>
    </div>
  )
}

// ─── DOCUMENT STUDY ───────────────────────────────────────────────────────────
function DocumentStudyScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const [tab, setTab] = useState<'doc'|'ai'|'tools'>('doc')
  const [askInput, setAskInput] = useState('')
  const [showMenu, setShowMenu] = useState(false)
  const [showDots, setShowDots] = useState(false)
  const [showRename, setShowRename] = useState(false)
  const [showDelete, setShowDelete] = useState(false)
  const [showReport, setShowReport] = useState(false)
  const [renameVal, setRenameVal] = useState('')
  const [savedToLib, setSavedToLib] = useState(false)
  const loading = useLoading(700)
  const [messages, setMessages] = useState([
    { role: 'ai', text: "I've read your document. I can explain concepts, quiz you, create flashcards, or summarise any section. What would you like to do?" },
  ])

  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [docLoadError, setDocLoadError] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) return
    api<DocumentDetail>(`/documents/${activeDocumentId}`)
      .then(d => { setDoc(d); setRenameVal(d.title) })
      .catch(e => setDocLoadError(e instanceof ApiError ? e.message : 'Could not load this document.'))
  }, [activeDocumentId])

  if (loading) return <SkeletonDocument />

  if (activeDocumentId == null) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.bg, padding: 32, textAlign: 'center' }}>
        <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 8 }}>No document selected</div>
        <div style={{ color: '#6B7280', fontSize: 13, marginBottom: 24 }}>Open a document from Home to study it here.</div>
        <button onClick={() => setScreen('home')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '12px 28px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Go Home</button>
      </div>
    )
  }
  const sendMsg = () => {
    if (!askInput.trim()) return
    const q = askInput; setAskInput('')
    setMessages(m => [...m, { role: 'user', text: q }])
    setTimeout(() => setMessages(m => [...m, { role: 'ai', text: `Great question about "${q}"! In the context of your ACT 101 notes, here's a clear explanation…` }]), 900)
  }

  const doExplain = () => {
    setShowMenu(false); setTab('ai')
    setMessages(m => [...m, { role: 'user', text: 'Explain the compound interest accumulation function' }, { role: 'ai', text: 'The compound interest accumulation function is:\n\nA(t) = A(0)(1+i)ᵗ\n\nWhere:\n• A(0) = initial principal\n• i = effective annual interest rate\n• t = time in years\n\nKey insight: under compound interest, each period\'s interest is reinvested, so you earn "interest on interest."\n\nKenyan example: KES 10,000 at 8% for 3 years:\nA(3) = 10,000 × (1.08)³ = KES 12,597.12 ✓' }])
  }
  const doSimplify = () => {
    setShowMenu(false); setTab('ai')
    setMessages(m => [...m, { role: 'user', text: 'Simplify this section for me' }, { role: 'ai', text: '✨ Simplified version:\n\nCompound interest = money growing on top of money that already grew.\n\nThink of it like a snowball rolling downhill — it gets bigger every time it rolls.\n\nSimple rule: A(t) = Starting amount × (1 + rate)^years\n\nAt 8% interest:\n• Year 1: KES 10,000 → KES 10,800\n• Year 2: KES 10,800 → KES 11,664\n• Year 3: KES 11,664 → KES 12,597' }])
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: 14, color: '#fff' }} className="line-clamp-1">{doc?.title || 'Loading…'}</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>{doc?.page_count != null ? `${doc.page_count} pages · ` : ''}{doc?.status ? doc.status.charAt(0).toUpperCase() + doc.status.slice(1) : ''}</div>
          </div>
          <div style={{ position: 'relative' }}>
            <button onClick={() => setShowDots(v => !v)} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.dots()}</div></button>
            {showDots && (
              <div style={{ position: 'absolute', right: 0, top: 40, background: '#fff', borderRadius: 14, boxShadow: '0 8px 24px rgba(0,0,0,0.15)', zIndex: 20, width: 160, overflow: 'hidden' }}>
                <button onClick={() => { setShowDots(false); setShowRename(true) }} style={{ display: 'block', width: '100%', padding: '12px 16px', background: 'none', border: 'none', textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: N.navy, cursor: 'pointer' }}>Rename</button>
                <button onClick={() => { setShowDots(false); setSavedToLib(true); setTimeout(() => setSavedToLib(false), 2000) }} style={{ display: 'block', width: '100%', padding: '12px 16px', background: 'none', border: 'none', textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: N.navy, cursor: 'pointer' }}>Download ↓</button>
                <button onClick={() => { setShowDots(false); setScreen('share-sheet') }} style={{ display: 'block', width: '100%', padding: '12px 16px', background: 'none', border: 'none', textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: N.navy, cursor: 'pointer' }}>Share</button>
                <button onClick={() => { setShowDots(false); setSavedToLib(true); setTimeout(() => setSavedToLib(false), 2000) }} style={{ display: 'block', width: '100%', padding: '12px 16px', background: 'none', border: 'none', textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: N.navy, cursor: 'pointer' }}>Save to Library</button>
                <button onClick={() => { setShowDots(false); setShowDelete(true) }} style={{ display: 'block', width: '100%', padding: '12px 16px', background: 'none', border: 'none', textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: '#C94C4C', cursor: 'pointer' }}>Delete</button>
                <button onClick={() => { setShowDots(false); setShowReport(true) }} style={{ display: 'block', width: '100%', padding: '12px 16px', background: 'none', border: 'none', textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: '#C94C4C', cursor: 'pointer' }}>Report</button>
              </div>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', background: 'rgba(255,255,255,0.08)', borderRadius: 12, padding: 3, gap: 2 }}>
          {(['doc','ai','tools'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{ flex: 1, padding: '7px 0', borderRadius: 9, background: tab === t ? N.gold : 'transparent', color: tab === t ? N.navy : 'rgba(255,255,255,0.55)', fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', transition: 'all 0.2s' }}>
              {t === 'doc' ? '📄 Document' : t === 'ai' ? '✦ AI Chat' : '🛠 Tools'}
            </button>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: 18 }} className="scrollbar-hide">
        {tab === 'doc' && (
          <div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 14, overflowX: 'auto' }} className="scrollbar-hide">
              <button onClick={() => setScreen('summary')} style={{ flexShrink: 0, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, border: `1px solid ${N.gold}33`, color: N.gold, fontSize: 11, fontWeight: 700, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Summarize</button>
              <button onClick={() => setScreen('quiz')} style={{ flexShrink: 0, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, border: `1px solid ${N.gold}33`, color: N.gold, fontSize: 11, fontWeight: 700, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Quiz Me</button>
              <button onClick={() => setScreen('flashcards')} style={{ flexShrink: 0, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, border: `1px solid ${N.gold}33`, color: N.gold, fontSize: 11, fontWeight: 700, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Flashcards</button>
              <button onClick={() => setScreen('mind-map')} style={{ flexShrink: 0, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, border: `1px solid ${N.gold}33`, color: N.gold, fontSize: 11, fontWeight: 700, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Mind Map</button>
            </div>
            {docLoadError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 12 }}>{docLoadError}</div>}
            {doc?.view_url ? (
              <div style={{ background: '#fff', borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 10px rgba(0,0,0,0.06)', height: '60vh' }}>
                {doc.file_type && ['jpg', 'jpeg', 'png'].includes(doc.file_type) ? (
                  <img src={doc.view_url} alt={doc.title} style={{ width: '100%', height: '100%', objectFit: 'contain', background: '#000' }} />
                ) : (
                  <iframe src={doc.view_url} title={doc.title} style={{ width: '100%', height: '100%', border: 'none' }} />
                )}
              </div>
            ) : (
              <div style={{ background: '#fff', borderRadius: 16, padding: 18, boxShadow: '0 2px 10px rgba(0,0,0,0.06)', textAlign: 'center' }}>
                <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 6 }}>{doc?.title || 'Loading document…'}</div>
                <div style={{ fontSize: 12, color: '#9CA3AF' }}>{doc ? 'Preview not available for this file type - use the tools above to study it.' : 'Fetching your document…'}</div>
              </div>
            )}
          </div>
        )}

        {tab === 'ai' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {messages.map((m, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', gap: 10, alignItems: 'flex-start' }}>
                {m.role === 'ai' && <div style={{ width: 30, height: 30, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: 9, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, flexShrink: 0 }}>✦</div>}
                <div style={{ maxWidth: '78%', background: m.role === 'user' ? `linear-gradient(135deg,${N.navy},${N.navy3})` : '#fff', borderRadius: m.role === 'user' ? '14px 0 14px 14px' : '0 14px 14px 14px', padding: '11px 14px', boxShadow: '0 2px 8px rgba(0,0,0,0.07)' }}>
                  <div style={{ fontSize: 13, color: m.role === 'user' ? '#fff' : '#374151', lineHeight: 1.7 }}>{m.text}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === 'tools' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[
              { icon: '🃏', title: 'Flashcards', sub: '35 cards generated', action: () => setScreen('flashcards'), color: N.gold },
              { icon: '🧠', title: 'Practice Quiz', sub: '15 MCQ questions', action: () => setScreen('quiz'), color: '#4C7BC9' },
              { icon: '📝', title: 'Summary', sub: '2-page condensed notes', action: () => setScreen('summary'), color: '#4CC97B' },
              { icon: '🎙️', title: 'Study Podcast', sub: '9 min AI-generated episode', action: () => setScreen('podcast-player'), color: '#C94C4C' },
              { icon: '🗺️', title: 'Mind Map', sub: 'Visual concept overview', action: () => setScreen('mind-map'), color: '#9B59B6' },
              { icon: '📚', title: 'Save to Library', sub: 'Access offline anytime', action: () => setSavedToLib(true), color: '#6B7280' },
            ].map((t, i) => (
              <button key={i} onClick={t.action} style={{ display: 'flex', alignItems: 'center', gap: 12, background: '#fff', border: '1px solid rgba(0,0,0,0.04)', borderRadius: 14, padding: '13px 15px', cursor: 'pointer', boxShadow: '0 2px 8px rgba(0,0,0,0.04)', fontFamily: 'Plus Jakarta Sans' }}>
                <div style={{ width: 44, height: 44, background: t.color + '18', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0 }}>{t.icon}</div>
                <div style={{ flex: 1, textAlign: 'left' }}>
                  <div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>{t.title}</div>
                  <div style={{ fontSize: 11, color: '#6B7280' }}>{t.sub}</div>
                </div>
                <div style={{ color: '#9CA3AF' }}>{Ic.chevR()}</div>
              </button>
            ))}
          </div>
        )}
      </div>

      <div style={{ padding: '10px 14px 14px', background: '#fff', borderTop: '1px solid rgba(0,0,0,0.06)' }}>
        {savedToLib && <div style={{ background: '#D1FAE5', color: '#065F46', fontSize: 12, fontWeight: 700, padding: '8px 14px', borderRadius: 10, marginBottom: 8, textAlign: 'center' }}>✓ Saved to Library</div>}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', background: N.bg, borderRadius: 14, padding: '8px 12px', border: '1px solid rgba(11,20,55,0.08)' }}>
          <input value={askInput} onChange={e => setAskInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && sendMsg()} placeholder="Ask about this document…" style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 13, color: '#374151', fontFamily: 'Plus Jakarta Sans' }} />
          <button onClick={sendMsg} style={{ width: 32, height: 32, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 9, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: N.navy }}>{Ic.send('w-4 h-4')}</div>
          </button>
        </div>
      </div>

      {/* Rename modal */}
      {showRename && (
        <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 50 }}>
          <div style={{ background: '#fff', borderRadius: 20, padding: 24, width: '100%' }}>
            <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 16 }}>Rename Document</div>
            <input value={renameVal} onChange={e => setRenameVal(e.target.value)} style={{ width: '100%', border: '1px solid rgba(0,0,0,0.12)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, boxSizing: 'border-box' }} />
            <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
              <button onClick={() => setShowRename(false)} style={{ flex: 1, background: '#F3F4F6', border: 'none', borderRadius: 12, padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, color: '#374151' }}>Cancel</button>
              <button onClick={() => setShowRename(false)} style={{ flex: 1, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 12, padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 13, color: N.navy }}>Save</button>
            </div>
          </div>
        </div>
      )}
      {/* Delete modal */}
      {showDelete && (
        <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 50 }}>
          <div style={{ background: '#fff', borderRadius: 20, padding: 24, width: '100%' }}>
            <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 8 }}>Delete Document?</div>
            <div style={{ fontSize: 13, color: '#6B7280', marginBottom: 20 }}>This will permanently remove "ACT 101 – Interest Theory" from your library.</div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => setShowDelete(false)} style={{ flex: 1, background: '#F3F4F6', border: 'none', borderRadius: 12, padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, color: '#374151' }}>Cancel</button>
              <button onClick={() => { setShowDelete(false); setScreen('home') }} style={{ flex: 1, background: '#C94C4C', border: 'none', borderRadius: 12, padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 13, color: '#fff' }}>Delete</button>
            </div>
          </div>
        </div>
      )}
      {/* Report modal */}
      {showReport && (
        <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 50 }}>
          <div style={{ background: '#fff', borderRadius: 20, padding: 24, width: '100%' }}>
            <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 14 }}>Report Document</div>
            {['Inaccurate content','Plagiarised material','Inappropriate content','Copyright violation','Other'].map((r, i) => (
              <button key={i} onClick={() => setShowReport(false)} style={{ display: 'block', width: '100%', background: '#F8F9FC', border: 'none', borderRadius: 10, padding: '11px 14px', marginBottom: 8, textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: N.navy, cursor: 'pointer' }}>{r}</button>
            ))}
            <button onClick={() => setShowReport(false)} style={{ width: '100%', background: '#F3F4F6', border: 'none', borderRadius: 12, padding: '12px 0', marginTop: 4, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, color: '#374151' }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── AI TUTOR ─────────────────────────────────────────────────────────────────
function AITutorScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [messages, setMessages] = useState([
    { role: 'ai', text: "Hello Arnold! 👋 I'm your Prepza AI Tutor. I can help you with ACT 101, MAT 101, STA 101 — or any topic you're studying.\n\nWhat would you like to work on today?" },
    { role: 'user', text: 'Explain the concept of present value with a Kenyan example' },
    { role: 'ai', text: "Great question! Present Value (PV) answers: \"How much is a future amount worth today?\"\n\nFormula: PV = FV / (1+i)ⁿ\n\nKenyan Example:\nYou're promised KES 100,000 in 2 years. Safaricom Money offers 10% p.a. What's it worth today?\n\nPV = 100,000 / (1.10)² = KES 82,645\n\nSo KES 82,645 today is equivalent to KES 100,000 in 2 years at 10%. This is exactly the kind of calculation an actuary at Jubilee Insurance would do daily! 💡" },
  ])
  const [input, setInput] = useState('')
  const [context, setContext] = useState('ACT 101')
  const [voiceMode, setVoiceMode] = useState(false)
  const loadingAI = useLoading(600)
  if (loadingAI) return <SkeletonAITutor />

  const send = () => {
    if (!input.trim()) return
    const q = input; setInput('')
    setMessages(m => [...m, { role: 'user', text: q }])
    setTimeout(() => setMessages(m => [...m, { role: 'ai', text: `Good question! Here's a clear explanation related to your ${context} studies…` }]), 900)
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ width: 38, height: 38, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>✦</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>Prepza AI Tutor</div>
            <div style={{ fontSize: 11, color: '#4CC97B', fontWeight: 600 }}>● Online · Ready to help</div>
          </div>
        </div>
        {/* Context selector */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, overflowX: 'auto' }} className="scrollbar-hide">
          {['ACT 101','MAT 101','STA 101','All Materials','General'].map(c => (
            <button key={c} onClick={() => setContext(c)} style={{ flexShrink: 0, padding: '6px 12px', borderRadius: 20, background: context === c ? 'rgba(201,168,76,0.25)' : 'rgba(255,255,255,0.08)', border: `1px solid ${context === c ? N.gold+'55' : 'rgba(255,255,255,0.1)'}`, color: context === c ? N.gold : 'rgba(255,255,255,0.6)', fontWeight: 700, fontSize: 11, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{c}</button>
          ))}
        </div>
        {/* Quick actions */}
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto' }} className="scrollbar-hide">
          {['Explain','Quiz Me','Summarize','Flashcards','Podcast'].map(a => (
            <button key={a} onClick={() => { setInput(a + ' '); }} style={{ flexShrink: 0, padding: '6px 12px', borderRadius: 20, background: `rgba(201,168,76,0.12)`, border: `1px solid ${N.gold}30`, color: N.gold, fontWeight: 700, fontSize: 11, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{a}</button>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: 14 }} className="scrollbar-hide">
        {messages.map((m, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', gap: 10, alignItems: 'flex-start' }}>
            {m.role === 'ai' && <div style={{ width: 32, height: 32, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, flexShrink: 0 }}>✦</div>}
            <div style={{ maxWidth: '80%', background: m.role === 'user' ? `linear-gradient(135deg,${N.navy},${N.navy3})` : '#fff', borderRadius: m.role === 'user' ? '14px 0 14px 14px' : '0 14px 14px 14px', padding: '12px 14px', boxShadow: '0 2px 8px rgba(0,0,0,0.07)' }}>
              <div style={{ fontSize: 13, color: m.role === 'user' ? '#fff' : '#374151', lineHeight: 1.75, whiteSpace: 'pre-line' }}>{m.text}</div>
            </div>
          </div>
        ))}
      </div>

      {voiceMode && (
        <div style={{ margin: '0 16px 8px', background: `linear-gradient(135deg,${N.navy},${N.navy3})`, borderRadius: 16, padding: 16, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 56, height: 56, background: `rgba(201,168,76,0.2)`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', border: `2px solid ${N.gold}`, animation: 'pulse-gold 1.5s infinite' }}>
            <div style={{ color: N.gold }}>{Ic.mic()}</div>
          </div>
          <div style={{ color: '#fff', fontSize: 13, fontWeight: 600 }}>Listening…</div>
          <button onClick={() => setVoiceMode(false)} style={{ background: 'rgba(255,255,255,0.1)', border: 'none', color: '#fff', fontSize: 12, fontWeight: 600, borderRadius: 10, padding: '7px 20px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Cancel</button>
        </div>
      )}

      <div style={{ padding: '10px 14px 14px', background: '#fff', borderTop: '1px solid rgba(0,0,0,0.06)' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', background: N.bg, borderRadius: 14, padding: '8px 12px', border: '1px solid rgba(11,20,55,0.08)' }}>
          <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} placeholder="Ask your AI tutor anything…" style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 13, color: '#374151', fontFamily: 'Plus Jakarta Sans' }} />
          <button onClick={() => setVoiceMode(v => !v)} style={{ width: 32, height: 32, background: voiceMode ? `rgba(201,168,76,0.2)` : '#F3F4F6', border: 'none', borderRadius: 9, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: voiceMode ? N.gold : '#6B7280' }}>{Ic.mic('w-4 h-4')}</div>
          </button>
          <button onClick={send} style={{ width: 32, height: 32, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 9, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: N.navy }}>{Ic.send('w-4 h-4')}</div>
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── FLASHCARDS ───────────────────────────────────────────────────────────────
function FlashcardsScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const [idx, setIdx] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [known, setKnown] = useState<number[]>([])

  const [cards, setCards] = useState<{ q: string; a: string }[]>([])
  const [materialId, setMaterialId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')
  const [finished, setFinished] = useState(false)
  const [completion, setCompletion] = useState<CompletionResponse | null>(null)

  // Normalizes ai_service.py's flashcards payload defensively - tries a
  // few likely field names for the front/back of each card.
  const normalizeCards = (raw: any): { q: string; a: string }[] => {
    const list = Array.isArray(raw) ? raw : Array.isArray(raw?.cards) ? raw.cards : Array.isArray(raw?.flashcards) ? raw.flashcards : []
    return list.map((item: any) => ({
      q: item.q || item.question || item.front || 'Question',
      a: item.a || item.answer || item.back || 'Answer',
    }))
  }

  useEffect(() => {
    if (activeDocumentId == null) { setLoading(false); setError('No document selected.'); return }
    api<{ csrf_token: string }>('/me')
      .then(me => {
        setCsrfToken(me.csrf_token)
        return api<{ material_id: number; reused: boolean; flashcards: any }>(`/documents/${activeDocumentId}/flashcards`, {
          method: 'POST',
          headers: { 'X-CSRF-Token': me.csrf_token },
        })
      })
      .then(res => { setMaterialId(res.material_id); setCards(normalizeCards(res.flashcards)) })
      .catch(e => {
        if (e instanceof ApiError && e.status === 429) setError("You've hit the hourly generation limit - try again later.")
        else if (e instanceof ApiError && e.status === 503) setError('AI budget exceeded for now - try again later.')
        else setError(e instanceof ApiError ? e.message : 'Could not generate flashcards. Please try again.')
      })
      .finally(() => setLoading(false))
  }, [activeDocumentId])

  const complete = async (reviewedCount: number) => {
    setFinished(true)
    if (activeDocumentId == null || materialId == null) return
    try {
      const res = await api<CompletionResponse>(`/documents/${activeDocumentId}/flashcards/${materialId}/complete`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ cards_reviewed: reviewedCount }),
      })
      setCompletion(res)
    } catch {
      // Non-fatal - the review session itself already completed.
    }
  }

  const card = cards[idx]
  const next = (k: boolean) => {
    const newKnown = k ? [...known, idx] : known
    if (k) setKnown(newKnown)
    setFlipped(false)
    setTimeout(() => {
      if (idx + 1 >= cards.length) complete(idx + 1)
      else setIdx(i => i + 1)
    }, 150)
  }

  if (loading) return <GenerationLoading label="Generating your flashcards…" />
  if (error) return <GenerationError error={error} />
  if (cards.length === 0) return <GenerationError error="No flashcards were returned." />

  if (finished) return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.bg, padding: 32 }}>
      <div style={{ fontSize: 56, marginBottom: 16 }}>🎉</div>
      <div style={{ fontWeight: 800, fontSize: 24, color: N.navy, marginBottom: 6 }}>Review Complete!</div>
      <div style={{ fontSize: 15, color: '#6B7280', marginBottom: 16 }}>{known.length}/{cards.length} marked as known</div>
      {completion && completion.xp_awarded > 0 && (
        <div style={{ fontSize: 13, color: N.gold, fontWeight: 700, marginBottom: 8 }}>+{completion.xp_awarded} XP</div>
      )}
      {completion && <AchievementToast codes={completion.newly_unlocked_achievements} />}
      <button onClick={() => setScreen('document-study')} style={{ marginTop: 16, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 13, border: 'none', borderRadius: 14, padding: '12px 20px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Back to Notes</button>
    </div>
  )

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => setScreen('document-study')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>Flashcards</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>{cards.length} cards</div>
          </div>
          <Pill text={`${known.length}/${cards.length} Known`} color="#4CC97B" />
        </div>
        <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 99, height: 5, overflow: 'hidden' }}>
          <div style={{ width: `${((idx + 1) / cards.length) * 100}%`, height: '100%', background: N.gold, borderRadius: 99, transition: 'width 0.3s' }} />
        </div>
        <div style={{ textAlign: 'right', marginTop: 4, fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>{idx + 1} / {cards.length}</div>
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '24px 20px', gap: 24 }}>
        <div onClick={() => setFlipped(v => !v)} style={{ width: '100%', minHeight: 220, background: '#fff', borderRadius: 24, padding: 28, boxShadow: '0 8px 32px rgba(0,0,0,0.1)', cursor: 'pointer', display: 'flex', flexDirection: 'column', justifyContent: 'center', border: `2px solid ${flipped ? N.gold + '44' : 'transparent'}`, transition: 'border-color 0.2s' }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: flipped ? N.gold : '#9CA3AF', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 14 }}>{flipped ? 'Answer' : 'Question — tap to reveal'}</div>
          <div style={{ fontSize: 14, color: N.navy, fontWeight: flipped ? 600 : 700, lineHeight: 1.7, whiteSpace: 'pre-line' }}>{flipped ? card.a : card.q}</div>
        </div>
        {flipped && (
          <div style={{ display: 'flex', gap: 14, width: '100%' }}>
            <button onClick={() => next(false)} style={{ flex: 1, background: '#FEE2E2', color: '#C94C4C', fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>✗ Still Learning</button>
            <button onClick={() => next(true)} style={{ flex: 1, background: '#D1FAE5', color: '#065F46', fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>✓ Got It</button>
          </div>
        )}
        {!flipped && (
          <div style={{ color: '#9CA3AF', fontSize: 12, textAlign: 'center' }}>Tap the card to see the answer</div>
        )}
      </div>
    </div>
  )
}

// ─── QUIZ ─────────────────────────────────────────────────────────────────────
function QuizScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const [qi, setQi] = useState(0)
  const [selected, setSelected] = useState<number|null>(null)
  const [score, setScore] = useState(0)
  const [done, setDone] = useState(false)

  const [questions, setQuestions] = useState<{ q: string; opts: string[]; ans: number }[]>([])
  const [materialId, setMaterialId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')
  const [completion, setCompletion] = useState<CompletionResponse | null>(null)

  // Normalizes ai_service.py's quiz payload defensively: tries a few
  // likely field names for the question text, options list, and
  // correct-answer index rather than assuming one exact shape.
  const normalizeQuiz = (raw: any): { q: string; opts: string[]; ans: number }[] => {
    const list = Array.isArray(raw) ? raw : Array.isArray(raw?.questions) ? raw.questions : []
    return list.map((item: any) => ({
      q: item.question || item.q || item.prompt || 'Question',
      opts: item.options || item.opts || item.choices || [],
      ans: typeof item.answer_index === 'number' ? item.answer_index
        : typeof item.correct_index === 'number' ? item.correct_index
        : typeof item.ans === 'number' ? item.ans : 0,
    }))
  }

  useEffect(() => {
    if (activeDocumentId == null) { setLoading(false); setError('No document selected.'); return }
    api<{ csrf_token: string }>('/me')
      .then(me => {
        setCsrfToken(me.csrf_token)
        return api<{ material_id: number; reused: boolean; quiz: any }>(`/documents/${activeDocumentId}/quiz`, {
          method: 'POST',
          headers: { 'X-CSRF-Token': me.csrf_token },
        })
      })
      .then(res => { setMaterialId(res.material_id); setQuestions(normalizeQuiz(res.quiz)) })
      .catch(e => {
        if (e instanceof ApiError && e.status === 429) setError("You've hit the hourly generation limit - try again later.")
        else if (e instanceof ApiError && e.status === 503) setError('AI budget exceeded for now - try again later.')
        else setError(e instanceof ApiError ? e.message : 'Could not generate a quiz. Please try again.')
      })
      .finally(() => setLoading(false))
  }, [activeDocumentId])

  const finish = async (finalScore: number) => {
    setDone(true)
    if (activeDocumentId == null || materialId == null) return
    try {
      const scorePercent = Math.round((finalScore / questions.length) * 100)
      const res = await api<CompletionResponse>(`/documents/${activeDocumentId}/quiz/${materialId}/complete`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ score_percent: scorePercent }),
      })
      setCompletion(res)
    } catch {
      // Non-fatal - the quiz itself already completed for the student.
    }
  }

  const q = questions[qi]
  const choose = (i: number) => {
    if (selected !== null || !q) return
    setSelected(i)
    const newScore = i === q.ans ? score + 1 : score
    if (i === q.ans) setScore(newScore)
    setTimeout(() => {
      if (qi + 1 >= questions.length) finish(newScore)
      else { setQi(qi + 1); setSelected(null) }
    }, 1100)
  }

  if (loading) return <GenerationLoading label="Generating your quiz…" />
  if (error) return <GenerationError error={error} />
  if (questions.length === 0) return <GenerationError error="No quiz questions were returned." />

  if (done) return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.bg, padding: 32 }}>
      <div style={{ fontSize: 56, marginBottom: 16 }}>🎉</div>
      <div style={{ fontWeight: 800, fontSize: 24, color: N.navy, marginBottom: 6 }}>Quiz Complete!</div>
      <div style={{ fontSize: 15, color: '#6B7280', marginBottom: 16 }}>You scored {score}/{questions.length}</div>
      {completion && completion.xp_awarded > 0 && (
        <div style={{ fontSize: 13, color: N.gold, fontWeight: 700, marginBottom: 8 }}>+{completion.xp_awarded} XP</div>
      )}
      {completion && <AchievementToast codes={completion.newly_unlocked_achievements} />}
      <div style={{ width: 100, height: 100, borderRadius: '50%', background: score / questions.length >= 0.6 ? '#D1FAE5' : '#FEE2E2', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 32 }}>
        <div style={{ fontWeight: 800, fontSize: 26, color: score / questions.length >= 0.6 ? '#065F46' : '#C94C4C' }}>{Math.round((score/questions.length)*100)}%</div>
      </div>
      <div style={{ display: 'flex', gap: 10 }}>
        <button onClick={() => setScreen('document-study')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 13, border: 'none', borderRadius: 14, padding: '12px 20px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Back to Notes</button>
      </div>
    </div>
  )
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => setScreen('document-study')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>Practice Quiz</div>
          </div>
          <Pill text={`${score} correct`} color="#4CC97B" />
        </div>
        <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 99, height: 5, overflow: 'hidden' }}>
          <div style={{ width: `${((qi) / questions.length) * 100}%`, height: '100%', background: N.gold, borderRadius: 99, transition: 'width 0.3s' }} />
        </div>
        <div style={{ textAlign: 'right', marginTop: 4, fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>Q{qi+1} of {questions.length}</div>
      </div>
      <div style={{ flex: 1, padding: 20 }}>
        <div style={{ background: '#fff', borderRadius: 18, padding: 20, marginBottom: 20, boxShadow: '0 2px 12px rgba(0,0,0,0.07)' }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: N.gold, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 }}>Question {qi+1}</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: N.navy, lineHeight: 1.7 }}>{q.q}</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {q.opts.map((opt, i) => {
            const isSelected = selected === i
            const isCorrect = i === q.ans
            const bg = selected !== null
              ? isCorrect ? '#D1FAE5' : isSelected ? '#FEE2E2' : '#fff'
              : '#fff'
            const color = selected !== null
              ? isCorrect ? '#065F46' : isSelected ? '#C94C4C' : N.navy
              : N.navy
            return (
              <button key={i} onClick={() => choose(i)} style={{ background: bg, border: `2px solid ${selected !== null && isCorrect ? '#4CC97B' : selected !== null && isSelected ? '#C94C4C' : 'rgba(0,0,0,0.06)'}`, borderRadius: 14, padding: '14px 16px', cursor: selected !== null ? 'default' : 'pointer', textAlign: 'left', fontFamily: 'Plus Jakarta Sans', fontSize: 13, fontWeight: 600, color, transition: 'all 0.2s', display: 'flex', gap: 10, alignItems: 'center' }}>
                <div style={{ width: 26, height: 26, borderRadius: '50%', background: selected !== null && isCorrect ? '#4CC97B' : selected !== null && isSelected ? '#C94C4C' : 'rgba(0,0,0,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 800, color: selected !== null && (isCorrect || isSelected) ? '#fff' : N.navy, flexShrink: 0 }}>{String.fromCharCode(65+i)}</div>
                {opt}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ─── PODCAST PLAYER ───────────────────────────────────────────────────────────
function PodcastPlayerScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState(0)

  const [stage, setStage] = useState<'script' | 'audio' | 'ready'>('script')
  const [title, setTitle] = useState('Study Podcast')
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) { setError('No document selected.'); return }
    let cancelled = false

    const run = async () => {
      try {
        const me = await api<{ csrf_token: string }>('/me')
        if (cancelled) return
        setCsrfToken(me.csrf_token)

        const scriptRes = await api<{ material_id: number; reused: boolean; podcast: any }>(`/documents/${activeDocumentId}/podcast-script`, {
          method: 'POST',
          headers: { 'X-CSRF-Token': me.csrf_token },
        })
        if (cancelled) return
        if (scriptRes.podcast?.title) setTitle(scriptRes.podcast.title)

        setStage('audio')
        const audioKickoff = await api<{ audio_status: string; material_id: number }>(`/documents/${activeDocumentId}/podcast-audio`, {
          method: 'POST',
          headers: { 'X-CSRF-Token': me.csrf_token },
        })
        if (cancelled) return

        if (audioKickoff.audio_status === 'ready') {
          await pollAudio()
          return
        }

        const poll = async () => {
          if (cancelled) return
          const status = await api<{ audio_status: string; audio_url: string | null; duration_seconds: number | null }>(`/documents/${activeDocumentId}/podcast-audio`)
          if (cancelled) return
          if (status.audio_status === 'ready' && status.audio_url) {
            setAudioUrl(status.audio_url)
            setDuration(status.duration_seconds || 0)
            setStage('ready')
          } else {
            setTimeout(poll, 3000)
          }
        }
        await poll()
      } catch (e) {
        if (cancelled) return
        if (e instanceof ApiError && e.status === 429) setError("You've hit the hourly generation limit - try again later.")
        else if (e instanceof ApiError && e.status === 503) setError('AI budget exceeded for now - try again later.')
        else setError(e instanceof ApiError ? e.message : 'Could not generate this podcast. Please try again.')
      }
    }

    const pollAudio = async () => {
      const status = await api<{ audio_status: string; audio_url: string | null; duration_seconds: number | null }>(`/documents/${activeDocumentId}/podcast-audio`)
      if (status.audio_status === 'ready' && status.audio_url) {
        setAudioUrl(status.audio_url)
        setDuration(status.duration_seconds || 0)
        setStage('ready')
      }
    }

    run()
    return () => { cancelled = true }
  }, [activeDocumentId])

  const togglePlay = () => {
    const el = audioRef.current
    if (!el) return
    if (playing) { el.pause() } else { el.play() }
    setPlaying(!playing)
  }

  const seek = (delta: number) => {
    const el = audioRef.current
    if (!el) return
    el.currentTime = Math.max(0, Math.min(el.duration || duration, el.currentTime + delta))
  }

  const fmt = (s: number) => `${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <TopBar title="Study Podcast" onBack={() => setScreen('document-study')} />
      </div>
      {error ? <GenerationError error={error} /> : stage !== 'ready' ? (
        <GenerationLoading label={stage === 'script' ? 'Writing your podcast script…' : 'Generating audio — this can take a minute…'} />
      ) : (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '32px 28px', gap: 28 }}>
          {audioUrl && (
            <audio
              ref={audioRef}
              src={audioUrl}
              onTimeUpdate={e => setProgress(e.currentTarget.currentTime)}
              onLoadedMetadata={e => setDuration(e.currentTarget.duration)}
              onEnded={() => setPlaying(false)}
            />
          )}
          {/* Album art */}
          <div style={{ width: 200, height: 200, borderRadius: 28, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: `0 16px 48px rgba(201,168,76,0.35)`, fontSize: 80, fontWeight: 800, color: N.navy, fontFamily: 'Plus Jakarta Sans' }}>🎙️</div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontWeight: 800, fontSize: 20, color: N.navy, marginBottom: 4 }}>{title}</div>
            <Pill text="AI Generated" color={N.gold} />
          </div>
          {/* Progress */}
          <div style={{ width: '100%' }}>
            <input type="range" min={0} max={duration || 1} step={0.5} value={progress} onChange={e => { const v = +e.target.value; setProgress(v); if (audioRef.current) audioRef.current.currentTime = v }} style={{ width: '100%', accentColor: N.gold, cursor: 'pointer' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#9CA3AF', marginTop: 4 }}>
              <span>{fmt(progress)}</span><span>{fmt(duration)}</span>
            </div>
          </div>
          {/* Controls */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 28 }}>
            <button onClick={() => seek(-15)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: N.navy }}>{Ic.rewind()}</button>
            <button onClick={togglePlay} style={{ width: 64, height: 64, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: '50%', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: `0 6px 20px rgba(201,168,76,0.4)` }}>
              <div style={{ color: N.navy }}>{playing ? Ic.pause() : Ic.play()}</div>
            </button>
            <button onClick={() => seek(15)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: N.navy }}>{Ic.skip()}</button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── SUMMARY ──────────────────────────────────────────────────────────────────
function SummaryScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const [saved, setSaved] = useState(false)
  const [summary, setSummary] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) { setLoading(false); setError('No document selected.'); return }
    api<{ csrf_token: string }>('/me')
      .then(me => api<{ material_id: number; reused: boolean; summary: any }>(`/documents/${activeDocumentId}/summarize`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': me.csrf_token },
      }))
      .then(res => setSummary(res.summary))
      .catch(e => {
        if (e instanceof ApiError && e.status === 429) setError("You've hit the hourly generation limit - try again later.")
        else if (e instanceof ApiError && e.status === 503) setError('AI budget exceeded for now - try again later.')
        else setError(e instanceof ApiError ? e.message : 'Could not generate a summary. Please try again.')
      })
      .finally(() => setLoading(false))
  }, [activeDocumentId])

  // Renders whatever ai_service.py returned, without assuming one fixed
  // shape: a plain string, an array of {title, body}-like sections, or
  // (as a last resort) raw JSON so nothing is silently hidden.
  const renderSummaryBody = () => {
    if (typeof summary === 'string') {
      return <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.8, whiteSpace: 'pre-line' }}>{summary}</div>
    }
    if (Array.isArray(summary)) {
      return summary.map((s: any, i: number) => (
        <div key={i} style={{ marginBottom: 20 }}>
          {(s.title || s.heading) && <div style={{ fontWeight: 800, fontSize: 14, color: N.navy, marginBottom: 8 }}>{s.title || s.heading}</div>}
          <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.8, whiteSpace: 'pre-line' }}>{s.body || s.content || s.text || JSON.stringify(s)}</div>
          {i < summary.length - 1 && <div style={{ height: 1, background: 'rgba(0,0,0,0.06)', marginTop: 20 }} />}
        </div>
      ))
    }
    if (summary && typeof summary === 'object') {
      const text = summary.text || summary.content || summary.body
      if (text) return <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.8, whiteSpace: 'pre-line' }}>{text}</div>
      return <pre style={{ fontSize: 11, color: '#374151', whiteSpace: 'pre-wrap', background: '#F8F9FC', borderRadius: 10, padding: 12 }}>{JSON.stringify(summary, null, 2)}</pre>
    }
    return null
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('document-study')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>AI Summary</div>
          </div>
          <button onClick={() => setScreen('share-sheet')} style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, padding: '7px 12px', color: '#fff', fontWeight: 600, fontSize: 12, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', marginRight: 6 }}>Share</button>
          <button onClick={() => setSaved(true)} style={{ background: saved ? `linear-gradient(135deg,${N.gold},${N.goldL})` : 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, padding: '7px 12px', color: saved ? N.navy : '#fff', fontWeight: 700, fontSize: 12, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{saved ? '✓ Saved' : 'Save'}</button>
        </div>
        {saved && <div style={{ background: 'rgba(76,201,123,0.15)', border: '1px solid rgba(76,201,123,0.3)', borderRadius: 10, padding: '7px 12px', marginTop: 8, fontSize: 12, color: '#4CC97B', fontWeight: 600 }}>✓ Saved to your Library</div>}
      </div>
      {loading ? <GenerationLoading label="Generating your summary…" /> : error ? <GenerationError error={error} /> : (
        <div style={{ flex: 1, overflowY: 'auto', padding: 18 }} className="scrollbar-hide">
          <div style={{ background: '#fff', borderRadius: 16, padding: 20, boxShadow: '0 2px 10px rgba(0,0,0,0.06)' }}>
            <Pill text="AI Generated" />
            {renderSummaryBody()}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── FORUM ────────────────────────────────────────────────────────────────────
function ForumScreen({ setScreen, setActiveForumPostId, setActiveGroupId }: { setScreen: (s: Screen) => void; setActiveForumPostId: (id: number) => void; setActiveGroupId: (id: number) => void }) {
  const [units, setUnits] = useState<UnitOption[]>([])
  const [unitId, setUnitId] = useState<number | null>(null)
  const [posts, setPosts] = useState<ForumPostSummary[]>([])
  const [loadingUnits, setLoadingUnits] = useState(true)
  const [loadingPosts, setLoadingPosts] = useState(false)
  const [error, setError] = useState('')

  const [myGroups, setMyGroups] = useState<GroupSummary[]>([])
  const [loadingGroups, setLoadingGroups] = useState(true)

  useEffect(() => {
    api<UnitOption[]>('/units')
      .then(u => { setUnits(u); if (u.length) setUnitId(u[0].id) })
      .catch(() => setError('Could not load your units.'))
      .finally(() => setLoadingUnits(false))
  }, [])

  useEffect(() => {
    api<{ groups: GroupSummary[] }>('/groups/mine')
      .then(res => setMyGroups(res.groups))
      .catch(() => {})
      .finally(() => setLoadingGroups(false))
  }, [])

  const openGroup = (id: number) => { setActiveGroupId(id); setScreen('group-detail') }

  useEffect(() => {
    if (unitId == null) return
    setLoadingPosts(true)
    api<{ unit: string; page: number; posts: ForumPostSummary[] }>(`/units/${unitId}/forum`)
      .then(res => setPosts(res.posts))
      .catch(() => setError('Could not load posts for this unit.'))
      .finally(() => setLoadingPosts(false))
  }, [unitId])

  const openPost = (id: number) => { setActiveForumPostId(id); setScreen('comments') }

  if (loadingUnits) return <SkeletonForum />
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 18, color: '#fff' }}>Community</span>
          <button onClick={() => setScreen('post-composer')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 11, padding: '8px 14px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 12, color: N.navy }}>+ Post</button>
        </div>
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto' }} className="scrollbar-hide">
          {units.map(u => (
            <button key={u.id} onClick={() => setUnitId(u.id)} style={{ flexShrink: 0, padding: '6px 14px', borderRadius: 20, background: unitId === u.id ? N.gold : 'rgba(255,255,255,0.1)', color: unitId === u.id ? N.navy : 'rgba(255,255,255,0.65)', fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{u.code}</button>
          ))}
        </div>
      </div>
      {/* My Groups */}
      <div style={{ padding: '14px 16px 0' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>My Groups</div>
          <button onClick={() => setScreen('group-create')} style={{ fontSize: 12, fontWeight: 700, color: N.gold, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>+ New</button>
        </div>
        <div style={{ display: 'flex', gap: 10, overflowX: 'auto', marginBottom: 16 }} className="scrollbar-hide">
          {loadingGroups ? (
            <div style={{ fontSize: 12, color: '#9CA3AF', padding: '10px 0' }}>Loading groups…</div>
          ) : (
            <>
              {myGroups.map(g => (
                <button key={g.id} onClick={() => openGroup(g.id)} style={{ flexShrink: 0, background: '#fff', border: 'none', borderRadius: 14, padding: '12px 14px', textAlign: 'left', cursor: 'pointer', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', fontFamily: 'Plus Jakarta Sans', minWidth: 130 }}>
                  <div style={{ width: 38, height: 38, background: `linear-gradient(135deg,${N.navy},${N.navy3})`, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, color: N.gold, marginBottom: 8 }}>{g.name.slice(0, 2).toUpperCase()}</div>
                  <div style={{ fontWeight: 700, fontSize: 12, color: N.navy, marginBottom: 2 }} className="line-clamp-1">{g.name}</div>
                  <div style={{ fontSize: 10, color: '#9CA3AF' }}>{g.member_count} member{g.member_count === 1 ? '' : 's'}</div>
                </button>
              ))}
              {myGroups.length === 0 && (
                <div style={{ fontSize: 12, color: '#9CA3AF', padding: '10px 0' }}>You haven't joined any groups yet.</div>
              )}
              <button onClick={() => setScreen('explore')} style={{ flexShrink: 0, background: '#F3F4F6', border: '1.5px dashed #D1D5DB', borderRadius: 14, padding: '12px 14px', textAlign: 'left', cursor: 'pointer', boxShadow: 'none', fontFamily: 'Plus Jakarta Sans', minWidth: 130, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                <div style={{ width: 38, height: 38, background: '#E5E7EB', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>+</div>
                <div style={{ fontSize: 11, color: '#6B7280', fontWeight: 600, textAlign: 'center' }}>Find groups</div>
              </button>
            </>
          )}
        </div>
        <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 10 }}>Recent Posts</div>
        {error && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 10 }}>{error}</div>}
        {loadingPosts ? (
          <div style={{ fontSize: 12, color: '#9CA3AF', padding: '20px 0' }}>Loading posts…</div>
        ) : posts.length === 0 ? (
          <EmptyState icon="💬" title="No posts yet" sub="Be the first to post in this unit." action="New Post" onAction={() => setScreen('post-composer')} />
        ) : posts.map(p => <RealForumCard key={p.id} post={p} onOpen={() => openPost(p.id)} />)}
      </div>
    </div>
  )
}

// ─── COMMENTS ────────────────────────────────────────────────────────────────
function CommentsScreen({ setScreen, postId }: { setScreen: (s: Screen) => void; postId: number | null }) {
  const [post, setPost] = useState<ForumPostDetail | null>(null)
  const [input, setInput] = useState('')
  const [csrfToken, setCsrfToken] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [askingAi, setAskingAi] = useState(false)
  const [error, setError] = useState('')

  const loadPost = () => {
    if (postId == null) return
    setLoading(true)
    api<ForumPostDetail>(`/forum/posts/${postId}`)
      .then(setPost)
      .catch(() => setError('Could not load this post.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadPost() }, [postId])
  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  const sendComment = async () => {
    if (!input.trim() || postId == null || sending) return
    setSending(true); setError('')
    try {
      await api(`/forum/posts/${postId}/replies`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ body: input.trim() }),
      })
      setInput('')
      loadPost()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not post your reply.')
    } finally {
      setSending(false)
    }
  }

  const askAi = async () => {
    if (postId == null || askingAi) return
    setAskingAi(true); setError('')
    try {
      await api(`/forum/posts/${postId}/ask-ai`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      loadPost()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Prepza AI could not answer right now.')
    } finally {
      setAskingAi(false)
    }
  }

  if (postId == null) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
        <div style={{ background: N.navy, padding: '0 18px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => setScreen('forum')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Post</span>
          </div>
        </div>
        <EmptyState icon="💬" title="No post selected" sub="Go back and pick a post from the forum." action="Back to Forum" onAction={() => setScreen('forum')} />
      </div>
    )
  }

  const replyCount = post ? post.replies.filter(r => !r.is_removed).length : 0

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('forum')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Replies ({replyCount})</span>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }} className="scrollbar-hide">
        {loading ? (
          <div style={{ fontSize: 12, color: '#9CA3AF', padding: '20px 0' }}>Loading…</div>
        ) : !post ? (
          <div style={{ fontSize: 12, color: '#C94C4C' }}>{error || 'Post not found.'}</div>
        ) : (
          <>
            <div style={{ background: '#fff', borderRadius: 14, padding: 14, boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
              <div style={{ display: 'flex', gap: 10, marginBottom: 8 }}>
                <Avi name={post.author.slice(0, 2).toUpperCase()} size={34} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>{post.author}</div>
                  <div style={{ fontSize: 11, color: '#9CA3AF' }}>{post.created_at ? new Date(post.created_at).toLocaleString() : ''}</div>
                </div>
              </div>
              <div style={{ fontWeight: 800, fontSize: 15, color: N.navy, marginBottom: 6 }}>{post.title}</div>
              <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.65 }}>{post.body}</div>
            </div>
            <button onClick={askAi} disabled={askingAi} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, background: 'rgba(201,168,76,0.1)', border: `1px solid ${N.gold}40`, borderRadius: 12, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 12, color: N.gold, opacity: askingAi ? 0.6 : 1 }}>
              ✦ {askingAi ? 'Asking Prepza AI…' : 'Ask Prepza AI to answer'}
            </button>
            {error && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600 }}>{error}</div>}
            {post.replies.map(r => (
              <div key={r.id} style={{ background: r.is_ai ? 'rgba(201,168,76,0.06)' : '#fff', borderRadius: 14, padding: 14, boxShadow: '0 2px 6px rgba(0,0,0,0.05)', border: r.is_ai ? `1px solid ${N.gold}30` : 'none' }}>
                <div style={{ display: 'flex', gap: 10, marginBottom: 8 }}>
                  {r.is_ai
                    ? <div style={{ width: 34, height: 34, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15, flexShrink: 0 }}>✦</div>
                    : <Avi name={(r.author || '??').slice(0, 2).toUpperCase()} size={34} />}
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>{r.is_ai ? 'Prepza AI' : (r.author || 'Deleted user')}</div>
                    <div style={{ fontSize: 11, color: '#9CA3AF' }}>{r.created_at ? new Date(r.created_at).toLocaleString() : ''}</div>
                  </div>
                </div>
                <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.65, whiteSpace: 'pre-line' }}>{r.is_removed ? '[removed]' : r.body}</div>
              </div>
            ))}
          </>
        )}
      </div>
      <div style={{ padding: '10px 14px 14px', background: '#fff', borderTop: '1px solid rgba(0,0,0,0.06)' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', background: N.bg, borderRadius: 14, padding: '8px 12px', border: '1px solid rgba(0,0,0,0.07)' }}>
          <Avi name={USER.initials} size={28} />
          <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && sendComment()} placeholder="Add a reply… (mention @Prepza AI to ask it directly)" style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 13, color: '#374151', fontFamily: 'Plus Jakarta Sans' }} />
          <button onClick={sendComment} disabled={sending} style={{ width: 30, height: 30, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 9, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: sending ? 0.6 : 1 }}>
            <div style={{ color: N.navy }}>{Ic.send('w-3 h-3')}</div>
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── CHATS ────────────────────────────────────────────────────────────────────
type ChatSummary = { id: number; is_group: boolean; name: string; last_message: string | null; last_message_at: string | null; unread_count: number }

function ChatsScreen({ setScreen, setActiveConversationId }: { setScreen: (s: Screen) => void; setActiveConversationId: (id: number) => void }) {
  const [tab, setTab] = useState<'Chats'|'Groups'|'Requests'>('Chats')
  const [search, setSearch] = useState('')
  const [chats, setChats] = useState<ChatSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    api<{ chats: ChatSummary[] }>('/chats')
      .then(data => { if (!cancelled) setChats(data.chats) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load chats') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  if (loading) return <SkeletonChats />
  const displayed = chats.filter(c => {
    const matchSearch = c.name.toLowerCase().includes(search.toLowerCase())
    const matchTab = tab === 'Groups' ? c.is_group : tab === 'Requests' ? false : true
    return matchSearch && matchTab
  })
  const openChat = (id: number) => { setActiveConversationId(id); setScreen('chat-detail') }
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#fff' }}>
      <div style={{ background: N.navy, padding: '0 18px 14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <span style={{ fontWeight: 800, fontSize: 20, color: '#fff' }}>Chats</span>
          <button onClick={() => setScreen('new-chat')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: '#fff' }}>{Ic.plus()}</div>
          </button>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', background: 'rgba(255,255,255,0.09)', borderRadius: 12, padding: '9px 12px', border: '1px solid rgba(255,255,255,0.08)', marginBottom: 12 }}>
          <div style={{ color: 'rgba(255,255,255,0.4)' }}>{Ic.search('w-4 h-4')}</div>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search conversations…" style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: 13, fontFamily: 'Plus Jakarta Sans' }} />
        </div>
        <div style={{ display: 'flex', gap: 0, background: 'rgba(255,255,255,0.08)', borderRadius: 12, padding: 3 }}>
          {(['Chats','Groups','Requests'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{ flex: 1, padding: '7px 0', borderRadius: 9, background: tab === t ? N.gold : 'transparent', color: tab === t ? N.navy : 'rgba(255,255,255,0.55)', fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', transition: 'all 0.2s' }}>{t}</button>
          ))}
        </div>
      </div>

      {/* Pinned AI */}
      <div onClick={() => setScreen('ai-tutor')} style={{ margin: '12px 14px 0', background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, borderRadius: 14, padding: '12px 14px', display: 'flex', gap: 12, alignItems: 'center', cursor: 'pointer', border: `1px solid ${N.gold}25` }}>
        <div style={{ width: 44, height: 44, background: `rgba(201,168,76,0.18)`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>✦</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 800, fontSize: 14, color: '#fff' }}>Prepza AI Tutor</div>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)' }}>Your personal study assistant</div>
        </div>
        <Pill text="AI" color={N.gold} />
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }} className="scrollbar-hide">
        {error ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 20px', textAlign: 'center' }}>
            <div style={{ fontSize: 44, marginBottom: 12 }}>⚠️</div>
            <div style={{ fontWeight: 700, fontSize: 16, color: N.navy }}>Couldn't load chats</div>
            <div style={{ fontSize: 13, color: '#6B7280', marginTop: 4 }}>{error}</div>
          </div>
        ) : tab === 'Requests' ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 20px', textAlign: 'center' }}>
            <div style={{ fontSize: 44, marginBottom: 12 }}>📬</div>
            <div style={{ fontWeight: 700, fontSize: 16, color: N.navy }}>No requests</div>
            <div style={{ fontSize: 13, color: '#6B7280', marginTop: 4 }}>New chat requests will appear here</div>
          </div>
        ) : displayed.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 20px', textAlign: 'center' }}>
            <div style={{ fontSize: 44, marginBottom: 12 }}>💬</div>
            <div style={{ fontWeight: 700, fontSize: 16, color: N.navy }}>No conversations</div>
            <div style={{ fontSize: 13, color: '#6B7280', marginTop: 4 }}>Start a new chat to connect with classmates</div>
          </div>
        ) : displayed.map(chat => {
          const initials = (chat.name || '??').slice(0, 2).toUpperCase()
          return (
            <div key={chat.id} onClick={() => openChat(chat.id)} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '12px 16px', cursor: 'pointer', borderBottom: '1px solid rgba(0,0,0,0.04)' }}>
              <div style={{ position: 'relative' }}>
                <Avi name={initials} size={46} />
                {chat.is_group && <div style={{ position: 'absolute', bottom: -1, right: -1, width: 15, height: 15, background: N.gold, borderRadius: '50%', border: '2px solid #fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 7, color: N.navy, fontWeight: 800 }}>G</div>}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                  <span style={{ fontWeight: 700, fontSize: 14, color: N.navy }}>{chat.name}</span>
                  <span style={{ fontSize: 11, color: '#9CA3AF' }}>{chat.last_message_at ? new Date(chat.last_message_at).toLocaleString() : ''}</span>
                </div>
                <div style={{ fontSize: 12, color: '#6B7280' }} className="line-clamp-1">{chat.last_message || 'No messages yet'}</div>
              </div>
              {chat.unread_count > 0 && <div style={{ width: 22, height: 22, background: N.gold, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 800, color: N.navy, flexShrink: 0 }}>{chat.unread_count}</div>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── CHAT DETAIL ──────────────────────────────────────────────────────────────
type MessageAttachmentData = { id: number; file_type: string; original_filename: string; file_size_bytes: number; view_url: string | null }
type ChatMessageData = { id: number; conversation_id: number; sender_id: number; body: string | null; is_deleted: boolean; created_at: string | null; edited_at: string | null; attachment: MessageAttachmentData | null }
type ChatDetail = { id: number; is_group: boolean; name: string; created_by: number; created_by_name: string; member_count: number; participants: { user_id: number; display_name: string; role: string }[]; viewer_muted: boolean }

function ChatDetailScreen({ setScreen, conversationId }: { setScreen: (s: Screen) => void; conversationId: number | null }) {
  const [input, setInput] = useState('')
  const [msgs, setMsgs] = useState<ChatMessageData[]>([])
  const [showAttach, setShowAttach] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [csrfToken, setCsrfToken] = useState('')
  const [meId, setMeId] = useState<number | null>(null)
  const [headerName, setHeaderName] = useState('Conversation')
  const [headerIsGroup, setHeaderIsGroup] = useState(false)
  const [senderNames, setSenderNames] = useState<Record<number, string>>({})
  const [uploadingAttachment, setUploadingAttachment] = useState(false)
  const [attachError, setAttachError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api<{ id: number; csrf_token: string }>('/me').then(me => { setCsrfToken(me.csrf_token); setMeId(me.id) }).catch(() => {})
  }, [])

  useEffect(() => {
    if (conversationId == null) { setLoading(false); return }
    let cancelled = false
    setLoading(true)
    setError(null)

    api<ChatDetail>(`/chats/${conversationId}`).then(detail => {
      if (cancelled) return
      setHeaderName(detail.name)
      setHeaderIsGroup(detail.is_group)
      const names: Record<number, string> = {}
      detail.participants.forEach(p => { names[p.user_id] = p.display_name })
      setSenderNames(names)
    }).catch(() => {})

    const loadMessages = () => api<{ messages: ChatMessageData[] }>(`/chats/${conversationId}/messages`)
      .then(data => { if (!cancelled) setMsgs(data.messages) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load messages') })

    loadMessages().finally(() => { if (!cancelled) setLoading(false) })

    api('/chats/' + conversationId + '/read', {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrfToken },
    }).catch(() => {})

    const interval = setInterval(loadMessages, 4000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [conversationId, csrfToken])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [msgs])

  if (loading) return <SkeletonChatDetail />

  const send = async () => {
    if (!input.trim() || sending || conversationId == null) return
    setSending(true)
    setError(null)
    try {
      const message = await api<ChatMessageData>(`/chats/${conversationId}/messages`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ body: input.trim() }),
      })
      setMsgs(m => [...m, message])
      setInput('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not send message')
    } finally {
      setSending(false)
    }
  }

  const startAttachmentUpload = async (file: File) => {
    if (conversationId == null || uploadingAttachment) return
    setAttachError(null)

    const ext = getFileExtension(file.name)
    if (!ext || !ALLOWED_UPLOAD_EXTENSIONS.includes(ext)) {
      setAttachError(`Unsupported file type. Allowed: ${ALLOWED_UPLOAD_EXTENSIONS.join(', ').toUpperCase()}`)
      return
    }
    if (file.size > MAX_CHAT_ATTACHMENT_SIZE_BYTES) {
      setAttachError(`File exceeds the ${MAX_CHAT_ATTACHMENT_SIZE_BYTES / (1024 * 1024)} MB limit`)
      return
    }

    setUploadingAttachment(true)
    try {
      const init = await api<{ attachment_id: number; upload_url: string; storage_path: string }>(
        `/chats/${conversationId}/attachments`,
        {
          method: 'POST',
          headers: { 'X-CSRF-Token': csrfToken },
          body: JSON.stringify({ original_filename: file.name, file_size_bytes: file.size }),
        }
      )

      const putRes = await fetch(init.upload_url, { method: 'PUT', body: file })
      if (!putRes.ok) throw new Error('Upload to storage failed - please try again')

      try {
        await api(`/chats/${conversationId}/attachments/${init.attachment_id}/uploaded`, {
          method: 'POST',
          headers: { 'X-CSRF-Token': csrfToken },
        })
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          await new Promise(r => setTimeout(r, 1500))
          await api(`/chats/${conversationId}/attachments/${init.attachment_id}/uploaded`, {
            method: 'POST',
            headers: { 'X-CSRF-Token': csrfToken },
          })
        } else {
          throw e
        }
      }

      const message = await api<ChatMessageData>(`/chats/${conversationId}/messages`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ attachment_id: init.attachment_id }),
      })
      setMsgs(m => [...m, message])
    } catch (e) {
      setAttachError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'Could not send attachment')
    } finally {
      setUploadingAttachment(false)
    }
  }

  const handleAttachmentFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    setShowAttach(false)
    if (file) startAttachmentUpload(file)
    e.target.value = ''
  }

  const initials = (headerName || '??').slice(0, 2).toUpperCase()

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 16px 14px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <button onClick={() => setScreen('chats')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <Avi name={initials} size={38} />
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 14, color: '#fff' }}>{headerName}</div>
            {headerIsGroup && <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>Group chat</div>}
          </div>
          <button onClick={() => setScreen('chat-options')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.dots()}</div></button>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }} className="scrollbar-hide">
        {error && <div style={{ textAlign: 'center', color: '#C94C4C', fontSize: 12, fontFamily: 'Plus Jakarta Sans' }}>{error}</div>}
        {conversationId == null ? (
          <div style={{ textAlign: 'center', color: '#9CA3AF', fontSize: 13, fontFamily: 'Plus Jakarta Sans', marginTop: 40 }}>No conversation selected</div>
        ) : msgs.length === 0 ? (
          <div style={{ textAlign: 'center', color: '#9CA3AF', fontSize: 13, fontFamily: 'Plus Jakarta Sans', marginTop: 40 }}>No messages yet - say hi 👋</div>
        ) : msgs.map(m => {
          const isMe = m.sender_id === meId
          const time = m.created_at ? new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''
          const senderLabel = senderNames[m.sender_id] || 'Deleted user'
          return (
            <div key={m.id} style={{ display: 'flex', justifyContent: isMe ? 'flex-end' : 'flex-start', flexDirection: 'column', alignItems: isMe ? 'flex-end' : 'flex-start', gap: 2 }}>
              {!isMe && headerIsGroup && <span style={{ fontSize: 11, color: N.gold, fontWeight: 700, marginLeft: 4 }}>{senderLabel}</span>}
              <div style={{ maxWidth: '76%', background: isMe ? `linear-gradient(135deg,${N.navy},${N.navy3})` : '#fff', borderRadius: isMe ? '14px 0 14px 14px' : '0 14px 14px 14px', padding: '10px 13px', boxShadow: '0 2px 6px rgba(0,0,0,0.07)' }}>
                {m.is_deleted ? (
                  <div style={{ fontSize: 13, color: isMe ? 'rgba(255,255,255,0.5)' : '#9CA3AF', lineHeight: 1.6, fontStyle: 'italic' }}>This message was deleted</div>
                ) : (
                  <>
                    {m.attachment && (
                      IMAGE_FILE_TYPES.includes(m.attachment.file_type) ? (
                        <a href={m.attachment.view_url || undefined} target="_blank" rel="noreferrer" style={{ display: 'block', marginBottom: m.body ? 8 : 0 }}>
                          <img src={m.attachment.view_url || undefined} alt={m.attachment.original_filename} style={{ maxWidth: '100%', maxHeight: 220, borderRadius: 10, display: 'block' }} />
                        </a>
                      ) : (
                        <a href={m.attachment.view_url || undefined} target="_blank" rel="noreferrer" style={{ display: 'flex', gap: 10, alignItems: 'center', background: isMe ? 'rgba(255,255,255,0.1)' : '#F8F9FC', borderRadius: 10, padding: '10px 12px', marginBottom: m.body ? 8 : 0, textDecoration: 'none' }}>
                          <div style={{ width: 34, height: 34, background: isMe ? 'rgba(255,255,255,0.15)' : '#fff', borderRadius: 9, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, flexShrink: 0 }}>📎</div>
                          <div style={{ minWidth: 0 }}>
                            <div style={{ fontSize: 12, fontWeight: 700, color: isMe ? '#fff' : N.navy, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.attachment.original_filename}</div>
                            <div style={{ fontSize: 10, color: isMe ? 'rgba(255,255,255,0.5)' : '#9CA3AF' }}>{(m.attachment.file_size_bytes / (1024 * 1024)).toFixed(1)} MB</div>
                          </div>
                        </a>
                      )
                    )}
                    {m.body && <div style={{ fontSize: 13, color: isMe ? '#fff' : '#374151', lineHeight: 1.6 }}>{m.body}</div>}
                  </>
                )}
                <div style={{ fontSize: 10, color: isMe ? 'rgba(255,255,255,0.4)' : '#9CA3AF', textAlign: 'right', marginTop: 3 }}>{time}</div>
              </div>
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>
      <div style={{ padding: '10px 12px 14px', background: '#fff', borderTop: '1px solid rgba(0,0,0,0.06)', position: 'relative' }}>
        <input ref={fileInputRef} type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png" style={{ display: 'none' }} onChange={handleAttachmentFileChange} disabled={uploadingAttachment} />
        {attachError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 8, textAlign: 'center' }}>{attachError}</div>}
        {uploadingAttachment && <div style={{ color: '#9CA3AF', fontSize: 12, fontWeight: 600, marginBottom: 8, textAlign: 'center' }}>Sending attachment…</div>}
        {showAttach && (
          <div style={{ position: 'absolute', bottom: '100%', left: 12, right: 12, background: '#fff', borderRadius: 16, boxShadow: '0 -4px 24px rgba(0,0,0,0.12)', padding: 16, border: '1px solid rgba(0,0,0,0.06)' }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 12 }}>Send Attachment</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
              {[['📄','Document', true],['🖼️','Image', true],['📷','Camera', false],['🎵','Audio', false]].map(([icon,label,enabled],i) => (
                <button key={i} onClick={() => { if (enabled) fileInputRef.current?.click(); else setShowAttach(false) }} disabled={!enabled} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: enabled ? 'pointer' : 'default', opacity: enabled ? 1 : 0.4 }}>
                  <div style={{ width: 52, height: 52, background: '#F3F4F6', borderRadius: 16, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22 }}>{icon}</div>
                  <span style={{ fontSize: 11, color: '#6B7280', fontFamily: 'Plus Jakarta Sans', fontWeight: 600 }}>{enabled ? label : `${label} (soon)`}</span>
                </button>
              ))}
            </div>
            <button onClick={() => setShowAttach(false)} style={{ width: '100%', background: '#F3F4F6', border: 'none', borderRadius: 12, padding: '10px 0', marginTop: 12, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, color: '#374151' }}>Cancel</button>
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button onClick={() => setShowAttach(v => !v)} disabled={uploadingAttachment} style={{ width: 36, height: 36, background: '#F3F4F6', border: 'none', borderRadius: 10, cursor: uploadingAttachment ? 'default' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: uploadingAttachment ? 0.5 : 1 }}>
            <div style={{ color: '#6B7280' }}>{Ic.attach()}</div>
          </button>
          <div style={{ flex: 1, display: 'flex', gap: 8, alignItems: 'center', background: N.bg, borderRadius: 14, padding: '8px 12px', border: '1px solid rgba(0,0,0,0.06)' }}>
            <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} placeholder="Message…" style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 13, color: '#374151', fontFamily: 'Plus Jakarta Sans' }} disabled={sending} />
          </div>
          <button onClick={send} disabled={sending} style={{ width: 36, height: 36, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 10, cursor: sending ? 'default' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: sending ? 0.6 : 1 }}>
            <div style={{ color: N.navy }}>{Ic.send('w-4 h-4')}</div>
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── OPPORTUNITIES ────────────────────────────────────────────────────────────
function OpportunitiesScreen({ setScreen, setActiveOpportunityId }: { setScreen: (s: Screen) => void; setActiveOpportunityId: (id: number | null) => void }) {
  const [filter, setFilter] = useState('All')
  const [query, setQuery] = useState('')
  const [opps, setOpps] = useState<OpportunityPublic[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')
  const [togglingId, setTogglingId] = useState<number | null>(null)

  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError('')
    const load = async () => {
      try {
        if (filter === 'Saved') {
          const res = await api<{ saved: OpportunityPublic[] }>('/opportunities/saved')
          if (!cancelled) setOpps(res.saved)
        } else {
          const params = new URLSearchParams()
          if (query.trim()) params.set('q', query.trim())
          const type = OPP_FILTER_TYPE_MAP[filter]
          if (type) params.set('opportunity_type', type)
          const res = await api<{ page: number; opportunities: OpportunityPublic[] }>(`/opportunities?${params.toString()}`)
          if (!cancelled) setOpps(res.opportunities)
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof ApiError ? e.message : 'Could not load opportunities.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    const t = setTimeout(load, 300)
    return () => { cancelled = true; clearTimeout(t) }
  }, [filter, query])

  const toggleSave = async (o: OpportunityPublic) => {
    if (togglingId != null) return
    setTogglingId(o.id)
    const wasSaved = o.saved
    setOpps(list => list.map(x => x.id === o.id ? { ...x, saved: !wasSaved } : x))
    try {
      if (wasSaved) {
        await api(`/opportunities/${o.id}/save`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
        if (filter === 'Saved') setOpps(list => list.filter(x => x.id !== o.id))
      } else {
        await api(`/opportunities/${o.id}/save`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      }
    } catch {
      setOpps(list => list.map(x => x.id === o.id ? { ...x, saved: wasSaved } : x))
    } finally {
      setTogglingId(null)
    }
  }

  const openDetail = (id: number) => { setActiveOpportunityId(id); setScreen('opportunity-detail') }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Opportunities 🚀</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>Curated for Kenyan students</div>
          </div>
          <button onClick={() => setScreen('share-opp-form')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 10, padding: '7px 12px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 12, color: N.navy }}>+ Share</button>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', background: 'rgba(255,255,255,0.09)', borderRadius: 13, padding: '10px 14px', border: '1px solid rgba(255,255,255,0.1)', marginBottom: 12 }}>
          <div style={{ color: 'rgba(255,255,255,0.4)' }}>{Ic.search()}</div>
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search opportunities..." style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: 13, fontFamily: 'Plus Jakarta Sans' }} />
        </div>
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto' }} className="scrollbar-hide">
          {OPP_FILTERS.map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{ flexShrink: 0, padding: '6px 14px', borderRadius: 20, background: filter === f ? N.gold : 'rgba(255,255,255,0.1)', color: filter === f ? N.navy : 'rgba(255,255,255,0.65)', fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{f}</button>
          ))}
        </div>
      </div>
      <div style={{ padding: 16 }}>
        {loading ? (
          [1,2,3].map(i => <SkOppCard key={i} />)
        ) : error ? (
          <ErrorState onRetry={() => setFilter(f => f)} />
        ) : opps.length === 0 ? (
          <EmptyState icon="🚀" title={filter === 'Saved' ? 'No saved opportunities' : 'No opportunities found'} sub={filter === 'Saved' ? 'Save opportunities to find them here later.' : 'Try a different search or filter.'} />
        ) : opps.map(o => {
          const meta = oppTypeMeta(o.opportunity_type)
          const deadline = fmtDeadline(o.application_deadline)
          return (
            <div key={o.id} onClick={() => openDetail(o.id)} style={{ background: '#fff', borderRadius: 18, overflow: 'hidden', boxShadow: '0 4px 14px rgba(0,0,0,0.08)', marginBottom: 14, cursor: 'pointer' }}>
              <div style={{ height: 5, background: `linear-gradient(90deg,${meta.color},${meta.color}66)` }} />
              <div style={{ padding: 16 }}>
                <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
                  <div style={{ width: 48, height: 48, background: meta.color + '18', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, flexShrink: 0 }}>{meta.icon}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 800, fontSize: 14, color: N.navy }} className="line-clamp-1">{o.title}</div>
                    <div style={{ fontSize: 12, color: '#6B7280' }} className="line-clamp-1">{o.organisation?.name || 'Unknown organisation'}</div>
                  </div>
                  <Pill text={o.promotion_type === 'sponsored' ? 'Sponsored' : o.promotion_type === 'featured' ? 'Featured' : meta.label} color={o.promotion_type ? N.gold : meta.color} />
                </div>
                <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 14 }}>
                  {o.location && <span style={{ fontSize: 11, color: '#6B7280' }}>📍 {o.location}{o.is_remote ? ' · Remote' : ''}</span>}
                  {!o.location && o.is_remote && <span style={{ fontSize: 11, color: '#6B7280' }}>🌐 Remote</span>}
                  {deadline && <span style={{ fontSize: 11, color: '#6B7280' }}>⏰ {deadline}</span>}
                  <span style={{ fontSize: 11, color: '#9CA3AF' }}>👁 {o.view_count}</span>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button onClick={e => { e.stopPropagation(); openDetail(o.id) }} style={{ flex: 1, background: `linear-gradient(135deg,${N.navy},${N.navy3})`, color: N.gold, fontWeight: 700, fontSize: 13, border: 'none', borderRadius: 12, padding: '11px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>View Details →</button>
                  <button onClick={e => { e.stopPropagation(); toggleSave(o) }} disabled={togglingId === o.id} style={{ width: 44, height: 44, background: o.saved ? `${N.gold}20` : '#F8F9FC', border: `1px solid ${o.saved ? N.gold + '55' : 'rgba(0,0,0,0.06)'}`, borderRadius: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: o.saved ? N.gold : '#6B7280' }}>{Ic.bookmark('w-4 h-4')}</div></button>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── OPPORTUNITY DETAIL ───────────────────────────────────────────────────────
function OppDetailScreen({ setScreen, opportunityId }: { setScreen: (s: Screen) => void; opportunityId: number | null }) {
  const [opp, setOpp] = useState<OpportunityPublic | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')
  const [saving, setSaving] = useState(false)
  const [showApply, setShowApply] = useState(false)

  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  useEffect(() => {
    if (opportunityId == null) { setLoading(false); return }
    setLoading(true); setError('')
    api<OpportunityPublic>(`/opportunities/${opportunityId}`)
      .then(setOpp)
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load this opportunity.'))
      .finally(() => setLoading(false))
  }, [opportunityId])

  const toggleSave = async () => {
    if (!opp || saving) return
    setSaving(true)
    const wasSaved = opp.saved
    setOpp({ ...opp, saved: !wasSaved })
    try {
      await api(`/opportunities/${opp.id}/save`, { method: wasSaved ? 'DELETE' : 'POST', headers: { 'X-CSRF-Token': csrfToken } })
    } catch {
      setOpp(o => o ? { ...o, saved: wasSaved } : o)
    } finally {
      setSaving(false)
    }
  }

  if (opportunityId == null) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
        <div style={{ background: N.navy, padding: '0 18px 16px' }}>
          <TopBar title="Opportunity Details" onBack={() => setScreen('opportunities')} />
        </div>
        <EmptyState icon="🚀" title="No opportunity selected" sub="Go back and pick an opportunity to view its details." action="Back to Opportunities" onAction={() => setScreen('opportunities')} />
      </div>
    )
  }

  if (loading) return <SkeletonOppDetail />

  if (error || !opp) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
        <div style={{ background: N.navy, padding: '0 18px 16px' }}>
          <TopBar title="Opportunity Details" onBack={() => setScreen('opportunities')} />
        </div>
        <ErrorState />
      </div>
    )
  }

  const meta = oppTypeMeta(opp.opportunity_type)
  const deadline = fmtDeadline(opp.application_deadline)

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <button onClick={() => setScreen('opportunities')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Opportunity Details</span>
          <button onClick={toggleSave} disabled={saving} style={{ width: 34, height: 34, background: opp.saved ? 'rgba(201,168,76,0.2)' : 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: opp.saved ? N.gold : '#fff' }}>{Ic.bookmark()}</div>
          </button>
        </div>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
          <div style={{ width: 60, height: 60, background: `${meta.color}25`, borderRadius: 18, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 28 }}>{meta.icon}</div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 16, color: '#fff' }}>{opp.title}</div>
            <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.6)' }}>{opp.organisation?.name || 'Unknown organisation'}</div>
            {opp.promotion_type && <Pill text={opp.promotion_type === 'sponsored' ? 'Sponsored' : 'Featured'} color={N.gold} />}
          </div>
        </div>
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {[
            opp.location ? ['📍', opp.location + (opp.is_remote ? ' · Remote' : '')] : (opp.is_remote ? ['🌐', 'Remote'] : null),
            deadline ? ['⏰', `Deadline: ${deadline}`] : null,
            ['👁', `${opp.view_count} views`],
          ].filter((x): x is [string, string] => x !== null).map(([icon, val]) => (
            <div key={val} style={{ background: '#fff', borderRadius: 12, padding: '8px 12px', display: 'flex', gap: 6, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
              <span style={{ fontSize: 14 }}>{icon}</span>
              <span style={{ fontSize: 12, fontWeight: 600, color: N.navy }}>{val}</span>
            </div>
          ))}
        </div>
        <div style={{ background: '#fff', borderRadius: 16, padding: 16, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
          <div style={{ fontWeight: 800, fontSize: 14, color: N.navy, marginBottom: 10 }}>About this Opportunity</div>
          <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.8, whiteSpace: 'pre-line' }}>{opp.description}</div>
        </div>
        {opp.application_instructions && (
          <div style={{ background: '#fff', borderRadius: 16, padding: 16, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
            <div style={{ fontWeight: 800, fontSize: 14, color: N.navy, marginBottom: 10 }}>How to Apply</div>
            <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.8, whiteSpace: 'pre-line' }}>{opp.application_instructions}</div>
          </div>
        )}
        {opp.application_url ? (
          <button onClick={() => setShowApply(true)} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '15px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: `0 6px 20px rgba(201,168,76,0.35)` }}>Apply Now →</button>
        ) : (
          <div style={{ background: '#F3F4F6', borderRadius: 16, padding: '14px 16px', textAlign: 'center', fontSize: 12, color: '#9CA3AF', fontWeight: 600 }}>No application link provided — check the description above for how to apply.</div>
        )}
        <button onClick={() => setScreen('share-sheet')} style={{ background: '#fff', color: N.navy, fontWeight: 700, fontSize: 14, border: '1px solid rgba(0,0,0,0.08)', borderRadius: 16, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          <div style={{ color: '#6B7280' }}>{Ic.share('w-4 h-4')}</div> Share Opportunity
        </button>
      </div>

      {showApply && opp.application_url && (
        <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'flex-end', zIndex: 50 }}>
          <div style={{ background: '#fff', borderRadius: '24px 24px 0 0', padding: '28px 24px 36px', width: '100%' }}>
            <div style={{ width: 40, height: 4, background: '#E5E7EB', borderRadius: 99, margin: '0 auto 20px' }} />
            <div style={{ fontSize: 24, textAlign: 'center', marginBottom: 12 }}>🌐</div>
            <div style={{ fontWeight: 800, fontSize: 17, color: N.navy, textAlign: 'center', marginBottom: 10 }}>You're leaving Prepza</div>
            <div style={{ fontSize: 13, color: '#6B7280', textAlign: 'center', lineHeight: 1.65, marginBottom: 24 }}>
              You will be taken to <strong>{opp.organisation?.name || 'the organisation'}'s</strong> website to complete your application. Prepza is not responsible for third-party application processes.
            </div>
            <a href={opp.application_url} target="_blank" rel="noopener noreferrer" style={{ display: 'block', textAlign: 'center', textDecoration: 'none', width: '100%', boxSizing: 'border-box', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 14, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', marginBottom: 10 }}>Continue to Website →</a>
            <button onClick={() => setShowApply(false)} style={{ width: '100%', background: '#F3F4F6', color: '#374151', fontWeight: 700, fontSize: 14, border: 'none', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── SHARE SHEET ──────────────────────────────────────────────────────────────
// There's no backend "share" endpoint (and no activeShareContext plumbing
// yet to say WHAT is being shared from each of the many screens that open
// this sheet), so this builds a generic Prepza link client-side and uses
// navigator.share()/clipboard - it does not know or claim to know the
// specific document/post/opportunity that triggered it.
function ShareSheetScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [copied, setCopied] = useState(false)
  const shareUrl = typeof window !== 'undefined' ? window.location.origin : 'https://prepza.app'
  const shareText = 'Check this out on Prepza — the AI study companion for Kenyan university students.'

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch { /* clipboard permission denied - link still visible below */ }
  }

  const nativeShare = async () => {
    if (navigator.share) {
      try { await navigator.share({ title: 'Prepza', text: shareText, url: shareUrl }) } catch { /* user cancelled */ }
    } else {
      copyLink()
    }
  }

  const actions: { icon: string; label: string; onClick: () => void }[] = [
    { icon: '💬', label: 'Chats', onClick: () => setScreen('new-chat') },
    { icon: '📲', label: 'WhatsApp', onClick: () => window.open(`https://wa.me/?text=${encodeURIComponent(shareText + ' ' + shareUrl)}`, '_blank') },
    { icon: '📧', label: 'Email', onClick: () => window.open(`mailto:?subject=${encodeURIComponent('Check out Prepza')}&body=${encodeURIComponent(shareText + '\n\n' + shareUrl)}`, '_blank') },
    { icon: '🔗', label: copied ? 'Copied!' : 'Copy Link', onClick: copyLink },
    { icon: '📤', label: 'More', onClick: nativeShare },
  ]

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#00000055', justifyContent: 'flex-end' }}>
      <div style={{ background: '#fff', borderRadius: '24px 24px 0 0', padding: '20px 20px 32px' }}>
        <div style={{ width: 40, height: 4, background: '#E5E7EB', borderRadius: 99, margin: '0 auto 20px' }} />
        <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 6 }}>Share</div>
        <div style={{ fontSize: 13, color: '#6B7280', marginBottom: 20, wordBreak: 'break-all' }}>{shareUrl}</div>
        <div style={{ display: 'flex', gap: 16, marginBottom: 24, overflowX: 'auto' }} className="scrollbar-hide">
          {actions.map((s, i) => (
            <button key={i} onClick={s.onClick} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer', flexShrink: 0 }}>
              <div style={{ width: 52, height: 52, background: '#F3F4F6', borderRadius: 16, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24 }}>{s.icon}</div>
              <span style={{ fontSize: 11, color: '#6B7280', fontFamily: 'Plus Jakarta Sans', fontWeight: 600 }}>{s.label}</span>
            </button>
          ))}
        </div>
        <button onClick={() => setScreen('home')} style={{ width: '100%', background: '#F3F4F6', border: 'none', borderRadius: 14, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 14, color: N.navy }}>Cancel</button>
      </div>
    </div>
  )
}

// ─── STUDENT PROFILE ──────────────────────────────────────────────────────────
// Viewing another student's profile. The backend has no dedicated "public
// profile fields" endpoint (bio/course/university for a user who isn't you) -
// only GET /users/:id/follow-summary, which gives counts + relationship
// flags. fallbackName is whatever display name the calling screen already
// had on hand (a follow-list row, a notification, etc) - real data, just
// carried over rather than invented here.
function StudentProfileScreen({ setScreen, targetUserId, fallbackName, setActiveConversationId }: {
  setScreen: (s: Screen) => void
  targetUserId: number | null
  fallbackName?: string | null
  setActiveConversationId?: (id: number) => void
}) {
  const [summary, setSummary] = useState<FollowSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')
  const [followBusy, setFollowBusy] = useState(false)
  const [messageBusy, setMessageBusy] = useState(false)

  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  useEffect(() => {
    if (targetUserId == null) { setLoading(false); setError('No student selected.'); return }
    setLoading(true)
    setError('')
    api<FollowSummary>(`/users/${targetUserId}/follow-summary`)
      .then(setSummary)
      .catch(() => setError('Could not load this profile.'))
      .finally(() => setLoading(false))
  }, [targetUserId])

  const toggleFollow = async () => {
    if (targetUserId == null || !summary || followBusy) return
    setFollowBusy(true)
    const wasFollowing = summary.is_following
    try {
      const res = wasFollowing
        ? await api<{ followers_count: number }>(`/users/${targetUserId}/follow`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
        : await api<{ followers_count: number }>(`/users/${targetUserId}/follow`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      setSummary(s => s ? { ...s, is_following: !wasFollowing, followers_count: res.followers_count } : s)
    } catch { /* leave state as-is on failure */ }
    setFollowBusy(false)
  }

  // Reuses the Chunk 8 chat infra: starts (or reuses) a 1:1 conversation
  // with this user, then hands off to ChatDetailScreen the same way
  // NewChatScreen does.
  const startMessage = async () => {
    if (targetUserId == null || messageBusy) return
    setMessageBusy(true)
    try {
      const res = await api<{ id: number; reused: boolean }>('/chats', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ is_group: false, participant_ids: [targetUserId] }),
      })
      setActiveConversationId?.(res.id)
      setScreen('chat-detail')
    } catch { /* stay put on failure */ }
    setMessageBusy(false)
  }

  const displayName = fallbackName || 'Student'
  const initials = displayName.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() || 'ST'

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: `linear-gradient(180deg,${N.navy} 0%,${N.navy3} 100%)`, padding: '0 18px 24px' }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
          <button onClick={() => setScreen('explore')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
        </div>
        {loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '20px 0' }}>
            <div style={{ width: 30, height: 30, border: '2.5px solid rgba(255,255,255,0.2)', borderTopColor: N.gold, borderRadius: '50%', animation: 'spin-slow 0.7s linear infinite' }} />
          </div>
        ) : error ? (
          <div style={{ textAlign: 'center', padding: '20px 0' }}>
            <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 13 }}>{error}</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
            <div style={{ marginBottom: 14 }}><Avi name={initials} size={72} /></div>
            <div style={{ fontWeight: 800, fontSize: 20, color: '#fff', marginBottom: 2 }}>{displayName}</div>
            {/* Course/university/year aren't exposed for other users' profiles
                by the current backend (only your own /me includes them) -
                omitted rather than guessed at. */}
            <div style={{ marginBottom: 14 }} />
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={toggleFollow} disabled={followBusy} style={{ background: summary?.is_following ? 'rgba(201,168,76,0.2)' : `linear-gradient(135deg,${N.gold},${N.goldL})`, color: summary?.is_following ? N.gold : N.navy, fontWeight: 800, fontSize: 13, border: summary?.is_following ? `1px solid ${N.gold}44` : 'none', borderRadius: 12, padding: '10px 24px', cursor: followBusy ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: followBusy ? 0.7 : 1 }}>{summary?.is_following ? 'Following ✓' : 'Follow'}</button>
              <button onClick={startMessage} disabled={messageBusy} style={{ background: 'rgba(255,255,255,0.1)', color: '#fff', fontWeight: 700, fontSize: 13, border: '1px solid rgba(255,255,255,0.15)', borderRadius: 12, padding: '10px 20px', cursor: messageBusy ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: messageBusy ? 0.7 : 1 }}>{messageBusy ? 'Opening…' : 'Message'}</button>
            </div>
          </div>
        )}
      </div>
      {!loading && !error && summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 10, padding: '16px 16px 0' }}>
          <div style={{ background: '#fff', borderRadius: 14, padding: '14px 8px', textAlign: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
            <div style={{ fontWeight: 800, fontSize: 18, color: N.gold }}>{summary.followers_count}</div>
            <div style={{ fontSize: 11, color: '#9CA3AF' }}>Followers</div>
          </div>
          <div style={{ background: '#fff', borderRadius: 14, padding: '14px 8px', textAlign: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
            <div style={{ fontWeight: 800, fontSize: 18, color: N.gold }}>{summary.following_count}</div>
            <div style={{ fontSize: 11, color: '#9CA3AF' }}>Following</div>
          </div>
        </div>
      )}
      {/* XP total, document count, and recent posts for another user aren't
          exposed by any current endpoint - not shown, rather than faked. */}
    </div>
  )
}

// ─── PROFILE ──────────────────────────────────────────────────────────────────
type ProfileMe = { id: number; display_name: string | null; bio: string | null; university_id: number | null; program_id: number | null }

function ProfileScreen({ setScreen, setActiveProfileUserId }: { setScreen: (s: Screen) => void; setActiveProfileUserId?: (id: number) => void }) {
  const [tab, setTab] = useState<'posts'|'saved'|'activity'|'materials'>('posts')
  const [showMenu, setShowMenu] = useState(false)
  const [showAvatarPicker, setShowAvatarPicker] = useState(false)
  const loading = useLoading(900)

  const [me, setMe] = useState<ProfileMe | null>(null)
  const [uniName, setUniName] = useState<string | null>(null)
  const [programName, setProgramName] = useState<string | null>(null)
  const [summary, setSummary] = useState<GamificationSummary | null>(null)
  const [achievementsList, setAchievementsList] = useState<Achievement[]>([])

  useEffect(() => {
    api<ProfileMe>('/me').then(setMe).catch(() => {})
    api<GamificationSummary>('/gamification/summary').then(setSummary).catch(() => {})
    api<AchievementsResponse>('/achievements').then(res => setAchievementsList(res.achievements)).catch(() => {})
  }, [])

  useEffect(() => {
    if (me?.university_id == null) return
    api<UniversityOption[]>('/universities')
      .then(list => setUniName(list.find(u => u.id === me.university_id)?.name ?? null))
      .catch(() => {})
    if (me.program_id != null) {
      api<ProgramOption[]>(`/universities/${me.university_id}/programs`)
        .then(list => setProgramName(list.find(p => p.id === me.program_id)?.name ?? null))
        .catch(() => {})
    }
  }, [me?.university_id, me?.program_id])

  if (loading) return <SkeletonProfile />
  const displayName = me?.display_name || 'Student'
  const initials = displayName.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() || 'ST'
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: `linear-gradient(180deg,${N.navy} 0%,${N.navy3} 100%)`, padding: '0 18px 24px' }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
          <div style={{ position: 'relative' }}>
            <button onClick={() => setShowMenu(v => !v)} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.dots()}</div></button>
            {showMenu && (
              <div style={{ position: 'absolute', right: 0, top: 40, background: '#fff', borderRadius: 14, boxShadow: '0 8px 24px rgba(0,0,0,0.15)', zIndex: 20, width: 170, overflow: 'hidden' }}>
                {[['Edit Profile', () => { setShowMenu(false); setScreen('edit-profile') }], ['Ambassador Program', () => { setShowMenu(false); setScreen('ambassador') }], ['Settings', () => { setShowMenu(false); setScreen('settings') }], ['Share Profile', () => { setShowMenu(false); setScreen('share-sheet') }]].map(([label, action]) => (
                  <button key={label as string} onClick={action as () => void} style={{ display: 'block', width: '100%', padding: '13px 16px', background: 'none', border: 'none', textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: N.navy, cursor: 'pointer', borderBottom: '1px solid rgba(0,0,0,0.05)' }}>{label as string}</button>
                ))}
              </div>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
          <div style={{ position: 'relative', marginBottom: 14 }}>
            <div style={{ width: 76, height: 76, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 28, color: N.navy, border: `3px solid rgba(201,168,76,0.4)` }}>{initials}</div>
            <button onClick={() => setShowAvatarPicker(true)} style={{ position: 'absolute', bottom: 0, right: 0, width: 22, height: 22, background: N.gold, borderRadius: '50%', border: `2px solid ${N.navy}`, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <div style={{ color: N.navy }}>{Ic.edit('w-3 h-3')}</div>
            </button>
          </div>
          <div style={{ fontWeight: 800, fontSize: 20, color: '#fff', marginBottom: 2 }}>{displayName}</div>
          {programName && <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.55)' }}>{programName}</div>}
          {uniName && <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.35)', marginTop: 2, marginBottom: 14 }}>{uniName}</div>}
          {!programName && !uniName && <div style={{ marginBottom: 14 }} />}
          <div style={{ display: 'flex', gap: 8 }}>
            <Pill text="🏅 Top Learner" />
            <Pill text="📚 Creator" />
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, padding: '14px 14px 0' }}>
        {[
          { label: 'Streak', value: summary ? `${summary.current_streak}🔥` : '—', color: N.gold, dest: 'study-streak' as Screen },
          { label: 'XP', value: summary ? summary.xp_total.toLocaleString() : '—', color: '#4CC97B', dest: 'xp-progress' as Screen },
          { label: 'Docs', value: summary ? String(summary.documents_count) : '—', color: '#4C7BC9', dest: 'library' as Screen },
          { label: 'Followers', value: summary ? String(summary.followers_count) : '—', color: '#9B59B6', dest: 'followers' as Screen },
        ].map(s => (
          <button key={s.label} onClick={() => {
            // Followers list is always scoped to a specific user id on the
            // backend (GET /users/:id/followers) - carry the viewer's own
            // id along so FollowListScreen knows whose list to fetch.
            if (s.dest === 'followers' && me && setActiveProfileUserId) setActiveProfileUserId(me.id)
            setScreen(s.dest)
          }} style={{ background: '#fff', borderRadius: 14, padding: '12px 8px', textAlign: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 10, color: '#9CA3AF', fontWeight: 600 }}>{s.label}</div>
          </button>
        ))}
      </div>

      <div style={{ margin: '14px 14px 0', background: '#fff', borderRadius: 16, padding: 14, boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div style={{ fontWeight: 800, fontSize: 13, color: N.navy }}>Achievements</div>
          <button onClick={() => setScreen('achievements')} style={{ fontSize: 11, fontWeight: 700, color: N.gold, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>See all</button>
        </div>
        <div style={{ display: 'flex', gap: 14, overflowX: 'auto' }} className="scrollbar-hide">
          {achievementsList.filter(a => a.done).map(a => (
            <button key={a.code} onClick={() => setScreen('achievements')} style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, background: 'none', border: 'none', cursor: 'pointer' }}>
              <div style={{ width: 46, height: 46, background: `${N.gold}18`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, border: `2px solid ${N.gold}33` }}>{a.icon}</div>
              <div style={{ fontSize: 9, color: '#6B7280', textAlign: 'center', maxWidth: 50, lineHeight: 1.3 }}>{a.name}</div>
            </button>
          ))}
        </div>
      </div>

      <div style={{ margin: '14px 14px 0', background: '#fff', borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
        <div style={{ display: 'flex', borderBottom: '1px solid rgba(0,0,0,0.06)' }}>
          {(['posts','saved','activity','materials'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{ flex: 1, padding: '11px 0', background: 'none', border: 'none', fontWeight: tab === t ? 800 : 500, fontSize: 11, color: tab === t ? N.navy : '#9CA3AF', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', borderBottom: tab === t ? `2px solid ${N.gold}` : '2px solid transparent' }}>
              {t === 'posts' ? 'Posts' : t === 'saved' ? 'Saved' : t === 'activity' ? 'Activity' : 'Materials'}
            </button>
          ))}
        </div>
        <div style={{ padding: 14 }}>
          {tab === 'posts' && (
            <div style={{ fontSize: 13, color: '#374151' }}>
              {[{ text: 'Just started my ACT 101 journey on Prepza! First flashcard set generated 🎉', likes: 14, time: '1d ago' }].map((p, i) => (
                <div key={i} style={{ paddingBottom: 12 }}>
                  <div style={{ marginBottom: 6, lineHeight: 1.6 }}>{p.text}</div>
                  <div style={{ display: 'flex', gap: 12, fontSize: 11, color: '#9CA3AF' }}>
                    <span style={{ color: '#C94C4C' }}>❤️ {p.likes}</span><span>{p.time}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          {tab === 'saved' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {['ACT 101 Lecture Notes – Week 1-6', 'Equity Leaders Programme', 'STA 101 Flashcards'].map((item, i) => (
                <button key={i} onClick={() => setScreen(i === 0 ? 'document-study' : i === 1 ? 'opportunity-detail' : 'flashcards')} style={{ display: 'flex', gap: 10, alignItems: 'center', background: 'none', border: 'none', textAlign: 'left', cursor: 'pointer', padding: '6px 0', borderBottom: i < 2 ? '1px solid rgba(0,0,0,0.05)' : 'none', fontFamily: 'Plus Jakarta Sans' }}>
                  <div style={{ width: 32, height: 32, background: '#F3F4F6', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14 }}>{i === 0 ? '📄' : i === 1 ? '🚀' : '🃏'}</div>
                  <div style={{ fontSize: 13, color: N.navy, fontWeight: 600 }}>{item}</div>
                  <div style={{ marginLeft: 'auto', color: '#9CA3AF' }}>{Ic.chevR('w-4 h-4')}</div>
                </button>
              ))}
            </div>
          )}
          {tab === 'activity' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                { icon: '⚗️', action: 'Studied ACT 101 – Interest Theory', time: '2h ago', screen: 'document-study' as Screen },
                { icon: '🃏', action: 'Completed 15 flashcards', time: '4h ago', screen: 'flashcards' as Screen },
                { icon: '🎙️', action: 'Listened to Interest Theory Podcast', time: 'Yesterday', screen: 'podcast-player' as Screen },
                { icon: '📤', action: 'Uploaded ACT 101 Notes – Week 1-6', time: '2d ago', screen: 'upload' as Screen },
              ].map((a, i) => (
                <button key={i} onClick={() => setScreen(a.screen)} style={{ display: 'flex', gap: 10, alignItems: 'center', background: 'none', border: 'none', textAlign: 'left', cursor: 'pointer', padding: 0, fontFamily: 'Plus Jakarta Sans' }}>
                  <span style={{ fontSize: 18 }}>{a.icon}</span>
                  <div style={{ flex: 1, fontSize: 13, color: N.navy, fontWeight: 500 }}>{a.action}</div>
                  <span style={{ fontSize: 11, color: '#9CA3AF', flexShrink: 0 }}>{a.time}</span>
                </button>
              ))}
            </div>
          )}
          {tab === 'materials' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {['ACT 101 Notes – Week 1-6.pdf', 'MAT 101 Past Papers 2023.pdf', 'STA 101 Flashcard Set'].map((m, i) => (
                <button key={i} onClick={() => setScreen(i < 2 ? 'document-study' : 'flashcards')} style={{ display: 'flex', gap: 10, alignItems: 'center', background: '#F8F9FC', border: 'none', borderRadius: 12, padding: 12, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
                  <div style={{ width: 36, height: 36, background: '#fff', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16 }}>{i < 2 ? '📕' : '🃏'}</div>
                  <div style={{ flex: 1, fontSize: 12, color: N.navy, fontWeight: 600, textAlign: 'left' }}>{m}</div>
                  <div style={{ color: '#9CA3AF' }}>{Ic.chevR('w-4 h-4')}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      <div style={{ height: 24 }} />

      {showAvatarPicker && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'flex-end', zIndex: 99 }}>
          <div style={{ background: '#fff', borderRadius: '24px 24px 0 0', padding: '24px 20px 36px', width: '100%' }}>
            <div style={{ width: 40, height: 4, background: '#E5E7EB', borderRadius: 99, margin: '0 auto 20px' }} />
            <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 16 }}>Change Profile Photo</div>
            {[['📷','Take Photo'],['🖼️','Choose from Library'],['🔗','Enter Avatar URL']].map(([icon,label],i) => (
              <button key={i} onClick={() => setShowAvatarPicker(false)} style={{ display: 'flex', alignItems: 'center', gap: 14, width: '100%', background: '#F8F9FC', border: 'none', borderRadius: 12, padding: '13px 16px', marginBottom: 8, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
                <span style={{ fontSize: 22 }}>{icon}</span>
                <span style={{ fontSize: 13, fontWeight: 600, color: N.navy }}>{label}</span>
              </button>
            ))}
            <button onClick={() => setShowAvatarPicker(false)} style={{ width: '100%', background: '#F3F4F6', border: 'none', borderRadius: 12, padding: '12px 0', marginTop: 4, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, color: '#374151' }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── SETTINGS ─────────────────────────────────────────────────────────────────
function SettingsScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [notifs, setNotifs] = useState({ push: true, messages: true, opportunities: false, community: true, reminders: true })
  const [priv, setPriv] = useState({ profilePublic: true, whoMessages: false, whoFollows: true })
  const [showLogout, setShowLogout] = useState(false)
  const [showModal, setShowModal] = useState<string|null>(null)

  const [csrfToken, setCsrfToken] = useState('')
  const [email, setEmail] = useState('')
  const [uniName, setUniName] = useState<string | null>(null)
  const [programName, setProgramName] = useState<string | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  useEffect(() => {
    api<{ email: string; csrf_token: string; university_id: number | null; program_id: number | null }>('/me')
      .then(me => {
        setCsrfToken(me.csrf_token)
        setEmail(me.email)
        if (me.university_id != null) {
          api<UniversityOption[]>('/universities')
            .then(list => setUniName(list.find(u => u.id === me.university_id)?.name ?? null))
            .catch(() => {})
        }
        if (me.university_id != null && me.program_id != null) {
          api<ProgramOption[]>(`/universities/${me.university_id}/programs`)
            .then(list => setProgramName(list.find(p => p.id === me.program_id)?.name ?? null))
            .catch(() => {})
        }
      })
      .catch(() => {})
  }, [])

  const handleDeleteAccount = async () => {
    setDeleting(true)
    setDeleteError('')
    try {
      await api('/delete-account', { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
      setScreen('login')
    } catch (e) {
      setDeleteError(e instanceof ApiError ? e.message : 'Could not delete your account. Please try again.')
      setDeleting(false)
    }
  }
  const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontSize: 11, fontWeight: 800, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: 1, padding: '12px 18px 6px' }}>{title}</div>
      <div style={{ background: '#fff', borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', margin: '0 16px' }}>{children}</div>
    </div>
  )
  const Row = ({ label, sub, onPress, right, danger }: { label: string; sub?: string; onPress?: () => void; right?: React.ReactNode; danger?: boolean }) => (
    <button onClick={onPress} style={{ display: 'flex', alignItems: 'center', width: '100%', gap: 14, padding: '14px 16px', background: 'none', border: 'none', borderBottom: '1px solid rgba(0,0,0,0.05)', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', textAlign: 'left' }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600, fontSize: 13, color: danger ? '#C94C4C' : N.navy }}>{label}</div>
        {sub && <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 1 }}>{sub}</div>}
      </div>
      {right ?? <div style={{ color: '#9CA3AF' }}>{Ic.chevR()}</div>}
    </button>
  )
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 18, color: '#fff' }}>Settings</span>
        </div>
      </div>

      <div style={{ paddingTop: 12, paddingBottom: 32 }}>
        <Section title="Account">
          <Row label="Edit Profile" sub="Name, photo, bio" onPress={() => setScreen('edit-profile')} />
          <Row label="Email" sub={email || 'Loading...'} onPress={() => setShowModal('email')} />
          <Row label="Phone" sub="+254 *** *** **89" onPress={() => setShowModal('phone')} />
          <Row label="University" sub={uniName || 'Not set'} onPress={() => setScreen('edit-profile')} />
          <Row label="Course" sub={programName || 'Not set'} onPress={() => setScreen('edit-profile')} />
        </Section>

        <Section title="Preferences">
          <Row label="Study Preferences" sub="Goals, daily target, subjects" onPress={() => setShowModal('study-prefs')} />
          <Row label="AI Preferences" sub="Language, explanation style" onPress={() => setShowModal('ai-prefs')} />
          <Row label="Language" sub="English" onPress={() => setShowModal('language')} />
          <Row label="Appearance" sub="Light mode" onPress={() => setShowModal('appearance')} />
        </Section>

        <Section title="Notifications">
          {([['push','Push Notifications'],['messages','Messages'],['opportunities','Opportunities'],['community','Community'],['reminders','Study Reminders']] as [keyof typeof notifs, string][]).map(([k, l]) => (
            <Row key={k} label={l} right={<div onClick={e => {
              e.stopPropagation()
              if (k === 'push') {
                const next = !notifs.push
                setNotifs(n => ({ ...n, push: next }))
                if (next) {
                  subscribeToPush(csrfToken).catch(() => setNotifs(n => ({ ...n, push: false })))
                } else {
                  unsubscribeFromPush(csrfToken).catch(() => {})
                }
              } else {
                setNotifs(n => ({ ...n, [k]: !n[k] }))
              }
            }}>{Ic.toggle(notifs[k])}</div>} />
          ))}
        </Section>

        <Section title="Privacy">
          <Row label="Profile Visibility" right={<div onClick={() => setPriv(p => ({ ...p, profilePublic: !p.profilePublic }))}>{Ic.toggle(priv.profilePublic)}</div>} sub={priv.profilePublic ? 'Public' : 'Private'} />
          <Row label="Who can message me" right={<div onClick={() => setPriv(p => ({ ...p, whoMessages: !p.whoMessages }))}>{Ic.toggle(priv.whoMessages)}</div>} sub={priv.whoMessages ? 'Everyone' : 'Followers only'} />
          <Row label="Who can follow me" right={<div onClick={() => setPriv(p => ({ ...p, whoFollows: !p.whoFollows }))}>{Ic.toggle(priv.whoFollows)}</div>} sub={priv.whoFollows ? 'Everyone' : 'Approval required'} />
        </Section>

        <Section title="Security">
          <Row label="Change Password" onPress={() => setShowModal('change-password')} />
          <Row label="Login Sessions" sub="1 active session" onPress={() => setShowModal('sessions')} />
          <Row label="Two-Factor Authentication" sub="Not enabled" onPress={() => setShowModal('2fa')} />
        </Section>

        <Section title="Subscription">
          <Row label="Subscription & Plan" sub="Free plan — Tap to upgrade" right={<Pill text="Upgrade" color={N.gold} />} onPress={() => setScreen('subscription')} />
          <Row label="Payment History" onPress={() => setScreen('payment-history')} />
        </Section>

        <Section title="Support">
          <Row label="Help Centre" onPress={() => setShowModal('help')} />
          <Row label="Contact Support" onPress={() => setShowModal('contact')} />
          <Row label="Report a Problem" onPress={() => setShowModal('report-problem')} />
        </Section>

        <Section title="About">
          <Row label="About Prepza" sub="v1.0.0 · Kenyatta University Launch" onPress={() => setShowModal('about')} />
          <Row label="Terms of Service" onPress={() => setShowModal('terms')} />
          <Row label="Privacy Policy" onPress={() => setShowModal('privacy-policy')} />
        </Section>

        <div style={{ margin: '8px 16px 0', background: '#fff', borderRadius: 16, overflow: 'hidden' }}>
          <Row label="Log Out" danger onPress={() => setShowLogout(true)} right={<div style={{ color: '#C94C4C' }}>{Ic.logout()}</div>} />
        </div>
        <div style={{ margin: '10px 16px 0', background: '#fff', borderRadius: 16, overflow: 'hidden' }}>
          <Row label="Delete Account" sub="Permanently delete your account and data" danger onPress={() => setShowDeleteConfirm(true)} />
        </div>
      </div>

      {/* Generic settings modal */}
      {showModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'flex-end', zIndex: 99 }}>
          <div style={{ background: '#fff', borderRadius: '24px 24px 0 0', padding: '24px 20px 40px', width: '100%' }}>
            <div style={{ width: 40, height: 4, background: '#E5E7EB', borderRadius: 99, margin: '0 auto 20px' }} />
            <div style={{ fontWeight: 800, fontSize: 17, color: N.navy, marginBottom: 8 }}>
              {showModal === 'email' ? 'Change Email' : showModal === 'phone' ? 'Change Phone' : showModal === 'university' ? 'Select University' : showModal === 'course' ? 'Select Course' : showModal === 'study-prefs' ? 'Study Preferences' : showModal === 'ai-prefs' ? 'AI Preferences' : showModal === 'language' ? 'Language' : showModal === 'appearance' ? 'Appearance' : showModal === 'change-password' ? 'Change Password' : showModal === 'sessions' ? 'Login Sessions' : showModal === '2fa' ? 'Two-Factor Authentication' : showModal === 'plan' ? 'Current Plan' : showModal === 'upgrade' ? 'Upgrade to Premium' : showModal === 'billing' ? 'Billing' : showModal === 'help' ? 'Help Centre' : showModal === 'contact' ? 'Contact Support' : showModal === 'report-problem' ? 'Report a Problem' : showModal === 'about' ? 'About Prepza' : showModal === 'terms' ? 'Terms of Service' : 'Privacy Policy'}
            </div>
            <div style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.65, marginBottom: 24 }}>
              {showModal === 'terms' || showModal === 'privacy-policy' ? (
                <div style={{ maxHeight: '50vh', overflowY: 'auto', whiteSpace: 'pre-wrap' }} className="scrollbar-hide">
                  {showModal === 'terms' ? TERMS_TEXT : PRIVACY_TEXT}
                </div>
              ) : showModal === 'upgrade' ? 'Prepza Premium gives you unlimited AI generations, offline access, priority support, and an ad-free experience.' : showModal === 'about' ? 'Prepza v1.0.0 — Kenyatta University Launch\n\nBuilt for Kenyan university students to study smarter with AI.' : showModal === 'help' ? 'Visit prepza.app/help or email support@prepza.app for assistance.' : 'This feature will be available in a future update. Stay tuned!'}
            </div>
            <button onClick={() => setShowModal(null)} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 14, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 14, color: N.navy }}>Got it</button>
          </div>
        </div>
      )}

      {/* Logout confirmation */}
      {showLogout && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 99 }}>
          <div style={{ background: '#fff', borderRadius: 20, padding: 24, width: '100%' }}>
            <div style={{ fontSize: 32, textAlign: 'center', marginBottom: 12 }}>👋</div>
            <div style={{ fontWeight: 800, fontSize: 17, color: N.navy, textAlign: 'center', marginBottom: 8 }}>Log out of Prepza?</div>
            <div style={{ fontSize: 13, color: '#6B7280', textAlign: 'center', marginBottom: 24 }}>You'll need to sign in again to access your study materials.</div>
            <button onClick={() => { api('/logout', { method: 'POST' }).catch(() => {}).finally(() => setScreen('login')) }} style={{ width: '100%', background: '#C94C4C', border: 'none', borderRadius: 14, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 14, color: '#fff', marginBottom: 10 }}>Log Out</button>
            <button onClick={() => setShowLogout(false)} style={{ width: '100%', background: '#F3F4F6', border: 'none', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 14, color: '#374151' }}>Cancel</button>
          </div>
        </div>
      )}

      {/* Delete account confirmation */}
      {showDeleteConfirm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 99 }}>
          <div style={{ background: '#fff', borderRadius: 20, padding: 24, width: '100%' }}>
            <div style={{ fontSize: 32, textAlign: 'center', marginBottom: 12 }}>⚠️</div>
            <div style={{ fontWeight: 800, fontSize: 17, color: N.navy, textAlign: 'center', marginBottom: 8 }}>Delete your account?</div>
            <div style={{ fontSize: 13, color: '#6B7280', textAlign: 'center', marginBottom: 16 }}>This permanently deletes your account and cannot be undone. Your uploaded documents and study history will be lost.</div>
            {deleteError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, textAlign: 'center', marginBottom: 12 }}>{deleteError}</div>}
            <button onClick={handleDeleteAccount} disabled={deleting} style={{ width: '100%', background: '#C94C4C', border: 'none', borderRadius: 14, padding: '14px 0', cursor: deleting ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 14, color: '#fff', marginBottom: 10, opacity: deleting ? 0.7 : 1 }}>{deleting ? 'Deleting...' : 'Yes, Delete My Account'}</button>
            <button onClick={() => { setShowDeleteConfirm(false); setDeleteError('') }} disabled={deleting} style={{ width: '100%', background: '#F3F4F6', border: 'none', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 14, color: '#374151' }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── FORGOT PASSWORD ──────────────────────────────────────────────────────────
function ForgotPasswordScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSend = async () => {
    setError('')
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError('Please enter a valid email address.'); return }
    setSubmitting(true)
    try {
      // Backend always returns the same generic message whether or not the
      // account exists (privacy pattern - see app.py forgot_password()), so
      // there's nothing further to branch on here.
      await api('/forgot-password', { method: 'POST', body: JSON.stringify({ email }) })
      setSent(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: `linear-gradient(170deg,${N.navy} 0%,${N.navy2} 60%,${N.bg} 100%)` }} className="scrollbar-hide">
      <div style={{ padding: '20px 28px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <button onClick={() => setScreen('login')} style={{ alignSelf: 'flex-start', background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, padding: '8px 12px', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 32, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 12 }}>{Ic.back('w-4 h-4')} Back</button>
        <img src={logoImg} alt="Prepza" style={{ width: 64, height: 64, borderRadius: 18, marginBottom: 20 }} />
        {!sent ? (
          <>
            <div style={{ fontWeight: 800, fontSize: 24, color: '#fff', letterSpacing: '-0.5px', textAlign: 'center' }}>Reset Password</div>
            <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginTop: 6, marginBottom: 32, textAlign: 'center' }}>Enter your email and we'll send you a reset link</div>
            {error && (
              <div style={{ width: '100%', background: 'rgba(140,29,43,0.25)', border: '1px solid rgba(140,29,43,0.5)', borderRadius: 12, padding: '10px 14px', color: '#ffb4bd', fontSize: 13, marginBottom: 16, boxSizing: 'border-box' }}>{error}</div>
            )}
            <div style={{ width: '100%' }}>
              <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Email Address</div>
              <input value={email} onChange={e => setEmail(e.target.value)} placeholder="arnold@students.ku.ac.ke" style={{ width: '100%', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 16px', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', boxSizing: 'border-box', marginBottom: 20 }} />
              <button disabled={submitting} onClick={handleSend} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: submitting ? 'default' : 'pointer', opacity: submitting ? 0.6 : 1, fontFamily: 'Plus Jakarta Sans' }}>{submitting ? 'Sending…' : 'Send Reset Link'}</button>
            </div>
          </>
        ) : (
          <>
            <div style={{ fontSize: 56, marginBottom: 16 }}>📧</div>
            <div style={{ fontWeight: 800, fontSize: 22, color: '#fff', textAlign: 'center', marginBottom: 10 }}>Check your email</div>
            <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 13, textAlign: 'center', lineHeight: 1.7, marginBottom: 32 }}>We've sent a password reset link to<br /><strong style={{ color: N.gold }}>{email || 'your email'}</strong></div>
            <button onClick={() => setScreen('login')} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Back to Login</button>
          </>
        )}
      </div>
    </div>
  )
}

// ─── RESET PASSWORD (reached via the emailed /reset-password?token= link) ────
function ResetPasswordScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const token = new URLSearchParams(window.location.search).get('token') || ''
  const [password, setPassword] = useState('')
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const COMMON_WEAK_PASSWORDS = new Set([
    'password', 'password1', 'password12', 'password123',
    '12345678', '123456789', '1234567890', 'qwerty123', 'qwertyuiop',
    'letmein123', 'iloveyou1', 'iloveyou123', 'admin1234', 'welcome123',
    'abc123456', '11111111', '00000000', 'changeme1', 'monkey123',
    'football1', 'sunshine1', 'princess1', 'dragon123',
  ])
  // Mirrors app.py's password_strength_error() branch-for-branch, same as
  // the signup checklist, so this never disagrees with what POST
  // /reset-password will actually accept.
  const passwordChecks = (pw: string) => [
    { label: 'At least 8 characters', met: pw.length >= 8 },
    { label: 'One lowercase letter', met: /[a-z]/.test(pw) },
    { label: 'One uppercase letter', met: /[A-Z]/.test(pw) },
    { label: 'One number', met: /\d/.test(pw) },
    { label: 'One symbol (e.g. ! @ # $ %)', met: /[^A-Za-z0-9]/.test(pw) },
    { label: 'Not a commonly used password', met: pw.length > 0 && !COMMON_WEAK_PASSWORDS.has(pw.toLowerCase()) },
  ]
  const stepValid = passwordChecks(password).every(c => c.met)

  const handleSubmit = async () => {
    setError('')
    if (!token) { setError('This reset link is missing its token - please use the link from your email directly.'); return }
    if (!stepValid) { setError('Please meet all password requirements below.'); return }
    setSubmitting(true)
    try {
      await api('/reset-password', { method: 'POST', body: JSON.stringify({ token, new_password: password }) })
      setDone(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: `linear-gradient(170deg,${N.navy} 0%,${N.navy2} 60%,${N.bg} 100%)` }} className="scrollbar-hide">
      <div style={{ padding: '20px 28px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <img src={logoImg} alt="Prepza" style={{ width: 64, height: 64, borderRadius: 18, marginTop: 20, marginBottom: 20 }} />
        {!done ? (
          <>
            <div style={{ fontWeight: 800, fontSize: 24, color: '#fff', letterSpacing: '-0.5px', textAlign: 'center' }}>Set a new password</div>
            <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginTop: 6, marginBottom: 24, textAlign: 'center' }}>Choose a strong password for your account</div>
            {!token && (
              <div style={{ width: '100%', background: 'rgba(140,29,43,0.25)', border: '1px solid rgba(140,29,43,0.5)', borderRadius: 12, padding: '10px 14px', color: '#ffb4bd', fontSize: 13, marginBottom: 16, boxSizing: 'border-box' }}>
                This link is missing its reset token. Please open the link from your email directly, or request a new one.
              </div>
            )}
            {error && (
              <div style={{ width: '100%', background: 'rgba(140,29,43,0.25)', border: '1px solid rgba(140,29,43,0.5)', borderRadius: 12, padding: '10px 14px', color: '#ffb4bd', fontSize: 13, marginBottom: 16, boxSizing: 'border-box' }}>{error}</div>
            )}
            <div style={{ width: '100%' }}>
              <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12, fontWeight: 600, marginBottom: 6 }}>New Password</div>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" style={{ width: '100%', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 16px', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', boxSizing: 'border-box', marginBottom: 12 }} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 20 }}>
                {passwordChecks(password).map(c => (
                  <div key={c.label} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: c.met ? '#4CC97B' : 'rgba(255,255,255,0.4)', fontFamily: 'Plus Jakarta Sans' }}>
                    <span>{c.met ? '✓' : '○'}</span>{c.label}
                  </div>
                ))}
              </div>
              <button disabled={submitting || !stepValid} onClick={handleSubmit} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: (submitting || !stepValid) ? 'default' : 'pointer', opacity: (submitting || !stepValid) ? 0.45 : 1, fontFamily: 'Plus Jakarta Sans' }}>{submitting ? 'Saving…' : 'Reset Password'}</button>
            </div>
          </>
        ) : (
          <>
            <div style={{ fontSize: 56, marginBottom: 16 }}>✅</div>
            <div style={{ fontWeight: 800, fontSize: 22, color: '#fff', textAlign: 'center', marginBottom: 10 }}>Password reset</div>
            <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 13, textAlign: 'center', lineHeight: 1.7, marginBottom: 32 }}>You can now log in with your new password.</div>
            <button onClick={() => setScreen('login')} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Back to Login</button>
          </>
        )}
      </div>
    </div>
  )
}

// ─── VERIFY EMAIL (reached via the emailed /verify-email?token= link) ────────
function VerifyConfirmScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [status, setStatus] = useState<'confirming' | 'success' | 'error'>('confirming')
  const [error, setError] = useState('')
  const [resendEmail, setResendEmail] = useState('')
  const [resendState, setResendState] = useState<'idle' | 'sending' | 'sent'>('idle')

  // GET /verify-email itself just serves this SPA shell (scanner-safe - a
  // link-preview bot fetching the URL doesn't run JS and so can't silently
  // consume the token). The actual confirmation happens here, via this
  // JS-triggered POST, matching the old static/verify-confirm.html design.
  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token') || ''
    if (!token) {
      setStatus('error')
      setError('This verification link is missing its token.')
      return
    }
    api('/verify-email/confirm', { method: 'POST', body: JSON.stringify({ token }) })
      .then(() => setStatus('success'))
      .catch((e) => {
        setStatus('error')
        setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
      })
  }, [])

  // Backend always returns the same generic message whether or not the
  // account/verification state matches (same privacy pattern as
  // /forgot-password) - nothing to branch on beyond request success.
  const handleResend = async () => {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(resendEmail)) return
    setResendState('sending')
    try {
      await api('/resend-verification', { method: 'POST', body: JSON.stringify({ email: resendEmail }) })
    } catch { /* generic response either way - nothing to surface */ }
    setResendState('sent')
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 32px', background: `linear-gradient(170deg,${N.navy} 0%,${N.navy2} 60%,${N.bg} 100%)`, textAlign: 'center' }}>
      {status === 'confirming' && (
        <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 14 }}>Confirming your email…</div>
      )}
      {status === 'success' && (
        <>
          <div style={{ width: 72, height: 72, borderRadius: '50%', background: 'rgba(76,201,123,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 24 }}>
            <span style={{ fontSize: 32 }}>✅</span>
          </div>
          <div style={{ fontWeight: 800, fontSize: 22, color: '#fff', marginBottom: 10 }}>Email verified</div>
          <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 14, lineHeight: 1.6, marginBottom: 32 }}>Your account is confirmed and you're already signed in.</div>
          <button onClick={() => setScreen('home')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 32px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Continue to Prepza</button>
        </>
      )}
      {status === 'error' && (
        <>
          <div style={{ width: 72, height: 72, borderRadius: '50%', background: 'rgba(140,29,43,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 24 }}>
            <span style={{ fontSize: 32 }}>⚠️</span>
          </div>
          <div style={{ fontWeight: 800, fontSize: 22, color: '#fff', marginBottom: 10 }}>Verification failed</div>
          <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 14, lineHeight: 1.6, marginBottom: 24 }}>{error}</div>

          {resendState === 'sent' ? (
            <div style={{ color: '#4CC97B', fontSize: 13, marginBottom: 24 }}>If that email needs verifying, a new link is on its way.</div>
          ) : (
            <div style={{ width: '100%', maxWidth: 320, marginBottom: 24 }}>
              <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 12, marginBottom: 10 }}>Get a new verification link:</div>
              <input value={resendEmail} onChange={e => setResendEmail(e.target.value)} placeholder="your@email.com" style={{ width: '100%', boxSizing: 'border-box', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 16px', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', marginBottom: 10 }} />
              <button
                disabled={resendState === 'sending' || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(resendEmail)}
                onClick={handleResend}
                style={{ width: '100%', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.18)', borderRadius: 14, padding: '12px 0', color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: resendState === 'sending' ? 0.6 : 1 }}
              >{resendState === 'sending' ? 'Sending…' : 'Resend verification email'}</button>
            </div>
          )}

          <button onClick={() => setScreen('login')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 32px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Back to Sign In</button>
        </>
      )}
    </div>
  )
}

// ─── SIGNUP ───────────────────────────────────────────────────────────────────
type UnitOption = { id: number; code: string; name: string }
type ForumReplyData = { id: number; body: string | null; is_removed: boolean; is_ai: boolean; author: string | null; ai_answer_id: number | null; created_at: string | null }
type ForumPostSummary = { id: number; title: string; body: string; author: string; reply_count: number; created_at: string | null }
type ForumPostDetail = { id: number; title: string; body: string; author: string; unit_id: number; created_at: string | null; replies: ForumReplyData[] }

type UniversityOption = { id: number; name: string; short_code: string; country: string | null }
type ProgramOption = { id: number; name: string; degree_level: string | null; discipline_category: string | null }

// ─── Group types (Chunk 7) ─────────────────────────────────────────────────
type GroupPrivacy = 'public' | 'private' | 'course_only'
type GroupSummary = {
  id: number; name: string; description: string | null; privacy: GroupPrivacy
  university_id: number | null; program_id: number | null; unit_id: number | null; unit_code: string | null
  year: number | null; member_count: number; created_by: number; created_at: string | null
  is_member: boolean; role: 'admin' | 'member' | null
}
type GroupPostData = {
  id: number; group_id: number; post_type: 'post' | 'question'; body: string | null; is_removed: boolean
  author: string; author_id: number; like_count: number | null; viewer_liked: boolean
  vote_count: number | null; viewer_voted: boolean; comment_count: number; created_at: string | null
}
type GroupPostCommentData = {
  id: number; group_post_id: number; body: string | null; is_removed: boolean; author: string; author_id: number
  marked_helpful: boolean; created_at: string | null
}
type GroupPostDetail = GroupPostData & { comments: GroupPostCommentData[] }
type GroupMemberData = { user_id: number; display_name: string; role: 'admin' | 'member'; joined_at: string | null }
type GroupFileData = {
  id: number; group_id: number; document_id: number; title: string | null; file_type: string | null
  file_size_bytes: number | null; page_count: number | null; view_url: string | null
  shared_by: string; shared_by_user_id: number; created_at: string | null
}
// Note: UserSearchResult is declared once already (NewChatScreen), reused here for the
// group-create member picker rather than redeclaring it.
type MyDocumentSummary = { id: number; title: string; status: string; file_type: string | null; page_count: number | null; created_at: string | null }

function SignupScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const steps = ['Name', 'Email', 'Password', 'University', 'Course', 'Year', 'Semester']
  const [step, setStep] = useState(0)
  const [data, setData] = useState({
    display_name: '', email: '', password: '',
    university_id: null as number | null, university_name: '',
    program_id: null as number | null, program_name: '',
    year: null as number | null, semester: null as number | null,
  })

  const [universities, setUniversities] = useState<UniversityOption[]>([])
  const [loadingUniversities, setLoadingUniversities] = useState(true)
  const [uniSearch, setUniSearch] = useState('')

  const [programs, setPrograms] = useState<ProgramOption[]>([])
  const [loadingPrograms, setLoadingPrograms] = useState(false)
  const [courseSearch, setCourseSearch] = useState('')

  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  // True once the user has been bounced back to fix a field after a failed
  // submit - lets Continue skip straight back to resubmitting instead of
  // forcing them to re-click through every already-answered step again.
  const [recovering, setRecovering] = useState(false)

  useEffect(() => {
    api<UniversityOption[]>('/universities')
      .then(setUniversities)
      .catch(() => setError('Could not load the university list. Check your connection and try again.'))
      .finally(() => setLoadingUniversities(false))
  }, [])

  useEffect(() => {
    if (data.university_id == null) { setPrograms([]); return }
    setLoadingPrograms(true)
    api<ProgramOption[]>(`/universities/${data.university_id}/programs`)
      .then(setPrograms)
      .catch(() => setError('Could not load courses for that university.'))
      .finally(() => setLoadingPrograms(false))
  }, [data.university_id])

  const goBack = () => { setError(''); setStep(s => Math.max(0, s - 1)) }
  const advance = () => { setError(''); setStep(s => s + 1) }

  // Mirrors app.py's password_strength_error() exactly, so weak passwords
  // get caught here instead of only failing after the full wizard is done.
  const COMMON_WEAK_PASSWORDS = new Set([
    'password', 'password1', 'password12', 'password123',
    '12345678', '123456789', '1234567890', 'qwerty123', 'qwertyuiop',
    'letmein123', 'iloveyou1', 'iloveyou123', 'admin1234', 'welcome123',
    'abc123456', '11111111', '00000000', 'changeme1', 'monkey123',
    'football1', 'sunshine1', 'princess1', 'dragon123',
  ])
  // Each check mirrors one branch of app.py's password_strength_error()
  // in the same order, so this checklist never disagrees with what the
  // backend will actually accept.
  const passwordChecks = (pw: string) => [
    { label: 'At least 8 characters', met: pw.length >= 8 },
    { label: 'One lowercase letter', met: /[a-z]/.test(pw) },
    { label: 'One uppercase letter', met: /[A-Z]/.test(pw) },
    { label: 'One number', met: /\d/.test(pw) },
    { label: 'One symbol (e.g. ! @ # $ %)', met: /[^A-Za-z0-9]/.test(pw) },
    { label: 'Not a commonly used password', met: pw.length > 0 && !COMMON_WEAK_PASSWORDS.has(pw.toLowerCase()) },
  ]
  const passwordError = (pw: string): string | null => {
    const failed = passwordChecks(pw).find(c => !c.met)
    return failed ? `Password needs: ${failed.label.toLowerCase()}.` : null
  }

  // After steps 0-2 (Name/Email/Password), decide whether to continue
  // forward normally or - if this is a correction after a failed submit
  // and everything else is already filled in - jump straight back to
  // resubmitting instead of re-walking University/Course/Year/Semester.
  const continueFromEarlyStep = () => {
    if (recovering && data.university_id != null && data.program_id != null && data.year != null && data.semester != null) {
      setRecovering(false)
      setError('')
      handleSubmit()
    } else {
      advance()
    }
  }

  const handleSubmit = async (overrides: Partial<typeof data> = {}) => {
    const payload = { ...data, ...overrides }
    setSubmitting(true)
    setError('')
    try {
      await api('/signup', {
        method: 'POST',
        body: JSON.stringify({
          display_name: payload.display_name,
          email: payload.email,
          password: payload.password,
          university_id: payload.university_id,
          program_id: payload.program_id,
          year: payload.year,
          semester: payload.semester,
        }),
      })
      setScreen('check-email')
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Something went wrong. Please try again.'
      setError(msg)
      setRecovering(true)
      const lower = msg.toLowerCase()
      if (lower.includes('display name')) setStep(0)
      else if (lower.includes('email')) setStep(1)
      else if (lower.includes('password')) setStep(2)
      else if (lower.includes('university')) setStep(3)
      else if (lower.includes('course') || lower.includes('program')) setStep(4)
      else if (lower.includes('year')) setStep(5)
      else if (lower.includes('semester')) setStep(6)
    } finally {
      setSubmitting(false)
    }
  }

  const filteredUniversities = universities.filter(u => u.name.toLowerCase().includes(uniSearch.toLowerCase()))
  const filteredPrograms = programs.filter(p => p.name.toLowerCase().includes(courseSearch.toLowerCase()))

  const titles = ["What's your name?", 'Your email address', 'Create a password', 'Your university', 'Your course', 'What year are you?', 'Which semester?']
  const subtitles: Record<number, string> = { 6: "Almost done - we'll personalise your experience" }

  const inputStyle = { width: '100%', boxSizing: 'border-box' as const, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 16px', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', marginBottom: 12 }
  const optionStyle = (selected: boolean) => ({ background: selected ? 'rgba(201,168,76,0.2)' : 'rgba(255,255,255,0.08)', border: `1px solid ${selected ? N.gold + '55' : 'rgba(255,255,255,0.1)'}`, borderRadius: 14, padding: '14px 18px', color: '#fff', fontWeight: 600, fontSize: 14, cursor: 'pointer', textAlign: 'left' as const, fontFamily: 'Plus Jakarta Sans' })
  const primaryBtn = { background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', marginTop: 'auto' }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: `linear-gradient(170deg,${N.navy} 0%,${N.navy2} 60%,${N.bg} 100%)` }}>
      <div style={{ padding: '20px 24px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          {step > 0 && <button onClick={goBack} style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, padding: '8px 10px', color: '#fff', cursor: 'pointer' }}>{Ic.back('w-4 h-4')}</button>}
          <div style={{ flex: 1, background: 'rgba(255,255,255,0.12)', borderRadius: 99, height: 4 }}>
            <div style={{ width: `${((step + 1) / steps.length) * 100}%`, height: '100%', background: N.gold, borderRadius: 99, transition: 'width 0.3s' }} />
          </div>
          <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12, fontWeight: 600 }}>{step + 1}/{steps.length}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 20 }}>
          <img src={logoImg} alt="Prepza" style={{ width: 56, height: 56, borderRadius: 16 }} />
        </div>
      </div>
      <div style={{ flex: 1, padding: '0 24px 32px', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div style={{ fontWeight: 800, fontSize: 26, color: '#fff', marginBottom: 6 }}>{titles[step]}</div>
        <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 13, marginBottom: 20 }}>{subtitles[step] ?? 'Help us personalise your Prepza experience'}</div>

        {error && (
          <div style={{ background: 'rgba(140,29,43,0.25)', border: '1px solid rgba(140,29,43,0.5)', borderRadius: 12, padding: '10px 14px', color: '#ffb4bd', fontSize: 13, marginBottom: 16 }}>{error}</div>
        )}

        {step === 0 && (
          <input value={data.display_name} onChange={e => setData(d => ({ ...d, display_name: e.target.value }))} placeholder="e.g. Arnold Gichuru" maxLength={50} style={inputStyle} />
        )}
        {step === 1 && (
          <input type="text" value={data.email} onChange={e => setData(d => ({ ...d, email: e.target.value }))} placeholder="arnold@students.ku.ac.ke" style={inputStyle} />
        )}
        {step === 2 && (
          <>
            <input type="password" value={data.password} onChange={e => setData(d => ({ ...d, password: e.target.value }))} placeholder="••••••••" style={inputStyle} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
              {passwordChecks(data.password).map(c => (
                <div key={c.label} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: c.met ? '#4CC97B' : 'rgba(255,255,255,0.4)', fontFamily: 'Plus Jakarta Sans' }}>
                  <span>{c.met ? '✓' : '○'}</span>{c.label}
                </div>
              ))}
            </div>
          </>
        )}

        {step === 3 && (
          <>
            <input value={uniSearch} onChange={e => setUniSearch(e.target.value)} placeholder="Type to search your university..." style={inputStyle} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1, overflowY: 'auto', minHeight: 0 }} className="scrollbar-hide">
              {loadingUniversities ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>Loading universities...</div>
              ) : filteredUniversities.length === 0 ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>University not found. Prepza doesn't have your university yet - try a different search, or check back soon.</div>
              ) : filteredUniversities.map(u => (
                <button key={u.id} onClick={() => { setData(d => ({ ...d, university_id: u.id, university_name: u.name, program_id: null, program_name: '' })); setCourseSearch(''); advance() }}
                  style={optionStyle(data.university_id === u.id)}>{u.name}</button>
              ))}
            </div>
          </>
        )}

        {step === 4 && (
          <>
            <input value={courseSearch} onChange={e => setCourseSearch(e.target.value)} placeholder="Type to search your course..." style={inputStyle} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1, overflowY: 'auto', minHeight: 0 }} className="scrollbar-hide">
              {loadingPrograms ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>Loading courses...</div>
              ) : programs.length === 0 ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>No courses listed yet for {data.university_name}. Check back soon - we're adding more universities regularly.</div>
              ) : filteredPrograms.length === 0 ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>Course not found for {data.university_name}. Try a different search.</div>
              ) : filteredPrograms.map(p => (
                <button key={p.id} onClick={() => { setData(d => ({ ...d, program_id: p.id, program_name: p.name })); advance() }}
                  style={optionStyle(data.program_id === p.id)}>{p.name}</button>
              ))}
            </div>
          </>
        )}

        {step === 5 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[1, 2, 3, 4].map(y => (
              <button key={y} onClick={() => { setData(d => ({ ...d, year: y })); advance() }} style={optionStyle(data.year === y)}>Year {y}</button>
            ))}
          </div>
        )}

        {step === 6 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[1, 2].map(s => (
              <button key={s} disabled={submitting} onClick={() => { setData(d => ({ ...d, semester: s })); handleSubmit({ semester: s }) }} style={optionStyle(data.semester === s)}>Semester {s}</button>
            ))}
            {submitting && <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginTop: 8 }}>Creating your account...</div>}
          </div>
        )}

        {step <= 2 && (() => {
          const stepValid =
            step === 0 ? data.display_name.trim().length > 0 :
            step === 1 ? /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email) :
            passwordError(data.password) === null
          return (
            <button
              disabled={!stepValid}
              onClick={() => {
                if (step === 0 && !data.display_name.trim()) { setError('Please enter your name.'); return }
                if (step === 1 && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) { setError('Please enter a valid email address.'); return }
                if (step === 2) {
                  const pwErr = passwordError(data.password)
                  if (pwErr) { setError(pwErr); return }
                }
                continueFromEarlyStep()
              }}
              style={{ ...primaryBtn, opacity: stepValid ? 1 : 0.45, cursor: stepValid ? 'pointer' : 'not-allowed' }}>Continue →</button>
          )
        })()}
      </div>
    </div>
  )
}

// ─── CHECK EMAIL ────────────────────────────────────────────────────────────
function CheckEmailScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 32px', background: `linear-gradient(170deg,${N.navy} 0%,${N.navy2} 60%,${N.bg} 100%)`, textAlign: 'center' }}>
      <div style={{ width: 72, height: 72, borderRadius: '50%', background: 'rgba(201,168,76,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 24 }}>
        <span style={{ fontSize: 32 }}>✉️</span>
      </div>
      <div style={{ fontWeight: 800, fontSize: 22, color: '#fff', marginBottom: 10 }}>Check your email</div>
      <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 14, lineHeight: 1.6, marginBottom: 32 }}>
        We've sent a verification link to your inbox. Click it to activate your account, then come back and sign in.
      </div>
      <button onClick={() => setScreen('login')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 32px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
        Back to Sign In
      </button>
    </div>
  )
}

// ─── COMPLETE PROFILE (lands here after a first-time Google Sign-In) ──────────
function CompleteProfileScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const steps = ['University', 'Course', 'Year', 'Semester']
  const [step, setStep] = useState(0)
  const [data, setData] = useState({
    university_id: null as number | null, university_name: '',
    program_id: null as number | null, program_name: '',
    year: null as number | null, semester: null as number | null,
  })
  const [csrfToken, setCsrfToken] = useState('')
  const [loadingMe, setLoadingMe] = useState(true)

  const [universities, setUniversities] = useState<UniversityOption[]>([])
  const [loadingUniversities, setLoadingUniversities] = useState(true)
  const [uniSearch, setUniSearch] = useState('')

  const [programs, setPrograms] = useState<ProgramOption[]>([])
  const [loadingPrograms, setLoadingPrograms] = useState(false)
  const [courseSearch, setCourseSearch] = useState('')

  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Confirms there's an actual logged-in session (this screen is only ever
  // reached via the /auth/google/callback redirect) and grabs the CSRF
  // token PATCH /profile requires. Pre-fills anything already set, in case
  // this is a re-visit rather than the very first sign-in.
  useEffect(() => {
    api<{ university_id: number | null; program_id: number | null; year: number | null; semester: number | null; csrf_token: string }>('/me')
      .then(me => {
        setCsrfToken(me.csrf_token)
        setData(d => ({ ...d, university_id: me.university_id, program_id: me.program_id, year: me.year, semester: me.semester }))
      })
      .catch(() => setScreen('login'))
      .finally(() => setLoadingMe(false))
  }, [])

  useEffect(() => {
    api<UniversityOption[]>('/universities')
      .then(setUniversities)
      .catch(() => setError('Could not load the university list. Check your connection and try again.'))
      .finally(() => setLoadingUniversities(false))
  }, [])

  useEffect(() => {
    if (data.university_id == null) { setPrograms([]); return }
    setLoadingPrograms(true)
    api<ProgramOption[]>(`/universities/${data.university_id}/programs`)
      .then(setPrograms)
      .catch(() => setError('Could not load courses for that university.'))
      .finally(() => setLoadingPrograms(false))
  }, [data.university_id])

  const goBack = () => { setError(''); setStep(s => Math.max(0, s - 1)) }
  const advance = () => { setError(''); setStep(s => s + 1) }

  const filteredUniversities = universities.filter(u => u.name.toLowerCase().includes(uniSearch.toLowerCase()))
  const filteredPrograms = programs.filter(p => p.name.toLowerCase().includes(courseSearch.toLowerCase()))

  const handleFinish = async (overrides: Partial<typeof data> = {}) => {
    const payload = { ...data, ...overrides }
    setSubmitting(true)
    setError('')
    try {
      await api('/profile', {
        method: 'PATCH',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({
          university_id: payload.university_id,
          program_id: payload.program_id,
          year: payload.year,
          semester: payload.semester,
        }),
      })
      setScreen('home')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const inputStyle = { width: '100%', boxSizing: 'border-box' as const, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 16px', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', marginBottom: 12 }
  const optionStyle = (selected: boolean) => ({ background: selected ? 'rgba(201,168,76,0.2)' : 'rgba(255,255,255,0.08)', border: `1px solid ${selected ? N.gold + '55' : 'rgba(255,255,255,0.1)'}`, borderRadius: 14, padding: '14px 18px', color: '#fff', fontWeight: 600, fontSize: 14, cursor: 'pointer', textAlign: 'left' as const, fontFamily: 'Plus Jakarta Sans' })

  if (loadingMe) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: `linear-gradient(170deg,${N.navy} 0%,${N.navy2} 60%,${N.bg} 100%)` }}>
        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 14 }}>Loading your account...</div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: `linear-gradient(170deg,${N.navy} 0%,${N.navy2} 60%,${N.bg} 100%)` }}>
      <div style={{ padding: '20px 24px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          {step > 0 && <button onClick={goBack} style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, padding: '8px 10px', color: '#fff', cursor: 'pointer' }}>{Ic.back('w-4 h-4')}</button>}
          <div style={{ flex: 1, background: 'rgba(255,255,255,0.12)', borderRadius: 99, height: 4 }}>
            <div style={{ width: `${((step + 1) / steps.length) * 100}%`, height: '100%', background: N.gold, borderRadius: 99, transition: 'width 0.3s' }} />
          </div>
          <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12, fontWeight: 600 }}>{step + 1}/{steps.length}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 20 }}>
          <img src={logoImg} alt="Prepza" style={{ width: 56, height: 56, borderRadius: 16 }} />
        </div>
      </div>
      <div style={{ flex: 1, padding: '0 24px 32px', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div style={{ fontWeight: 800, fontSize: 26, color: '#fff', marginBottom: 6 }}>Finish setting up</div>
        <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 13, marginBottom: 20 }}>Just a few details left to personalise your Prepza experience</div>

        {error && (
          <div style={{ background: 'rgba(140,29,43,0.25)', border: '1px solid rgba(140,29,43,0.5)', borderRadius: 12, padding: '10px 14px', color: '#ffb4bd', fontSize: 13, marginBottom: 16 }}>{error}</div>
        )}

        {step === 0 && (
          <>
            <input value={uniSearch} onChange={e => setUniSearch(e.target.value)} placeholder="Type to search your university..." style={inputStyle} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1, overflowY: 'auto', minHeight: 0 }} className="scrollbar-hide">
              {loadingUniversities ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>Loading universities...</div>
              ) : filteredUniversities.length === 0 ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>University not found. Prepza doesn't have your university yet - try a different search, or check back soon.</div>
              ) : filteredUniversities.map(u => (
                <button key={u.id} onClick={() => { setData(d => ({ ...d, university_id: u.id, university_name: u.name, program_id: null, program_name: '' })); setCourseSearch(''); advance() }}
                  style={optionStyle(data.university_id === u.id)}>{u.name}</button>
              ))}
            </div>
          </>
        )}

        {step === 1 && (
          <>
            <input value={courseSearch} onChange={e => setCourseSearch(e.target.value)} placeholder="Type to search your course..." style={inputStyle} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1, overflowY: 'auto', minHeight: 0 }} className="scrollbar-hide">
              {loadingPrograms ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>Loading courses...</div>
              ) : programs.length === 0 ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>No courses listed yet for {data.university_name}. Check back soon - we're adding more universities regularly.</div>
              ) : filteredPrograms.length === 0 ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>Course not found for {data.university_name}. Try a different search.</div>
              ) : filteredPrograms.map(p => (
                <button key={p.id} onClick={() => { setData(d => ({ ...d, program_id: p.id, program_name: p.name })); advance() }}
                  style={optionStyle(data.program_id === p.id)}>{p.name}</button>
              ))}
            </div>
          </>
        )}

        {step === 2 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[1, 2, 3, 4].map(y => (
              <button key={y} onClick={() => { setData(d => ({ ...d, year: y })); advance() }} style={optionStyle(data.year === y)}>Year {y}</button>
            ))}
          </div>
        )}

        {step === 3 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[1, 2].map(s => (
              <button key={s} disabled={submitting} onClick={() => { setData(d => ({ ...d, semester: s })); handleFinish({ semester: s }) }} style={optionStyle(data.semester === s)}>Semester {s}</button>
            ))}
            {submitting && <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginTop: 8 }}>Saving...</div>}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── NOTIFICATIONS ────────────────────────────────────────────────────────────
type NotificationItem = {
  id: number; type: string; title: string; body: string | null
  related_type: string | null; related_id: number | null
  is_read: boolean; created_at: string | null
}

function NotificationsScreen({ setScreen, setActiveForumPostId, setActiveProfileUserId }: { setScreen: (s: Screen) => void; setActiveForumPostId?: (id: number) => void; setActiveProfileUserId?: (id: number) => void }) {
  const [notifs, setNotifs] = useState<NotificationItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')

  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  useEffect(() => {
    setLoading(true)
    api<{ page: number; notifications: NotificationItem[] }>('/notifications?page=1')
      .then(res => setNotifs(res.notifications))
      .catch(() => setError('Could not load notifications.'))
      .finally(() => setLoading(false))
  }, [])

  const markRead = async (n: NotificationItem) => {
    if (n.is_read) return
    setNotifs(list => list.map(x => x.id === n.id ? { ...x, is_read: true } : x))
    try { await api(`/notifications/${n.id}/read`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } }) } catch {}
  }
  const markAllRead = async () => {
    setNotifs(list => list.map(x => ({ ...x, is_read: true })))
    try { await api('/notifications/read-all', { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } }) } catch {}
  }
  const removeNotif = async (id: number) => {
    setNotifs(list => list.filter(x => x.id !== id))
    try { await api(`/notifications/${id}`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } }) } catch {}
  }
  const openNotif = (n: NotificationItem) => {
    markRead(n)
    if (n.related_type === 'forum_post' && n.related_id && setActiveForumPostId) { setActiveForumPostId(n.related_id); setScreen('comments') }
    else if (n.related_type === 'group' || n.related_type === 'group_post') setScreen('group-detail')
    else if (n.related_type === 'user' && n.related_id && setActiveProfileUserId) { setActiveProfileUserId(n.related_id); setScreen('student-profile') }
  }
  const iconFor = (type: string) => ({
    group_post: '\ud83d\udcac', group_comment: '\ud83d\udcac', group_join_request: '\ud83d\udc65', new_follower: '\u2795',
    forum_ai_reply: '\u2726', study_reminder: '\ud83d\udcda', opportunity: '\ud83d\ude80', achievement: '\ud83c\udfc6',
    announcement: '\ud83d\udce3', group_like: '\u2764\ufe0f', group_vote: '\u2b06\ufe0f', group_promoted: '\u2b50', moderation_warning: '\u26a0\ufe0f',
  } as Record<string,string>)[type] || '\ud83d\udd14'

  if (loading) return <SkeletonNotifications />
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 18, color: '#fff' }}>Notifications</span>
          {notifs.some(n => !n.is_read) && (
            <button onClick={markAllRead} style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, padding: '7px 12px', color: '#fff', fontWeight: 600, fontSize: 11, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Mark all read</button>
          )}
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 8 }} className="scrollbar-hide">
        {error && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600 }}>{error}</div>}
        {!error && notifs.length === 0 && <EmptyState icon="\ud83d\udd14" title="No notifications yet" sub="You'll see updates about study activity, community, and your account here." />}
        {notifs.map(n => (
          <div key={n.id} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', background: n.is_read ? '#fff' : '#FFFBEF', border: n.is_read ? 'none' : `1px solid ${N.gold}30`, borderRadius: 14, padding: '13px 14px', boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
            <button onClick={() => openNotif(n)} style={{ display: 'flex', gap: 12, flex: 1, background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', fontFamily: 'Plus Jakarta Sans', padding: 0 }}>
              <div style={{ width: 42, height: 42, background: `${N.gold}18`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0 }}>{iconFor(n.type)}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 2 }}>{n.title}</div>
                {n.body && <div style={{ fontSize: 12, color: '#6B7280', lineHeight: 1.55 }} className="line-clamp-2">{n.body}</div>}
                <div style={{ fontSize: 10, color: '#9CA3AF', marginTop: 4 }}>{n.created_at ? new Date(n.created_at).toLocaleString() : ''}</div>
              </div>
            </button>
            <button onClick={() => removeNotif(n.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#D1D5DB', flexShrink: 0, padding: 4 }}>{Ic.close('w-4 h-4')}</button>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── LIBRARY ──────────────────────────────────────────────────────────────────
type LibraryPublicationSummary = {
  id: number; title: string; description: string | null; material_type: string
  unit_id: number | null; unit_code: string | null; author: string
  view_count: number; save_count: number; created_at: string | null
}
type SavedLibraryItem = LibraryPublicationSummary & { saved_at: string | null }
type MySubmission = {
  id: number; document_id: number; title: string; description: string | null; material_type: string
  unit_id: number | null; unit_code: string | null; status: string; rejection_reason: string | null
  view_count: number; save_count: number; created_at: string | null; updated_at: string | null
}

function LibraryScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [activeTab, setActiveTab] = useState<'Browse' | 'Saved' | 'Published'>('Browse')
  const [materialTypeFilter, setMaterialTypeFilter] = useState<string | null>(null)
  const [csrfToken, setCsrfToken] = useState('')

  const [browseItems, setBrowseItems] = useState<LibraryPublicationSummary[]>([])
  const [browseLoading, setBrowseLoading] = useState(true)
  const [browseError, setBrowseError] = useState('')

  const [savedItems, setSavedItems] = useState<SavedLibraryItem[]>([])
  const [savedLoading, setSavedLoading] = useState(true)
  const [savedError, setSavedError] = useState('')
  const [savedIds, setSavedIds] = useState<Set<number>>(new Set())

  const [submissions, setSubmissions] = useState<MySubmission[]>([])
  const [submissionsLoading, setSubmissionsLoading] = useState(true)
  const [submissionsError, setSubmissionsError] = useState('')

  const [search, setSearch] = useState('')
  const [unitFilter, setUnitFilter] = useState<number | null>(null)
  const [universityFilter, setUniversityFilter] = useState<number | null>(null)
  const [filterUnits, setFilterUnits] = useState<UnitOption[]>([])
  const [filterUniversities, setFilterUniversities] = useState<UniversityOption[]>([])

  const [reportItem, setReportItem] = useState<LibraryPublicationSummary | null>(null)
  const [reportReason, setReportReason] = useState('')
  const [reportDetails, setReportDetails] = useState('')
  const [reportSubmitting, setReportSubmitting] = useState(false)
  const [reportError, setReportError] = useState('')
  const [reportSubmitted, setReportSubmitted] = useState(false)

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
  }, [])

  useEffect(() => {
    api<UnitOption[]>('/units').then(setFilterUnits).catch(() => {})
    api<UniversityOption[]>('/universities').then(setFilterUniversities).catch(() => {})
  }, [])

  const submitReport = async () => {
    if (!reportItem || !reportReason || reportSubmitting || !csrfToken) return
    setReportSubmitting(true)
    setReportError('')
    try {
      await api(`/library/${reportItem.id}/report`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ reason: reportReason, details: reportDetails.trim() || undefined }),
      })
      setReportSubmitted(true)
    } catch (e) {
      setReportError(e instanceof ApiError ? e.message : 'Could not submit report. Please try again.')
    } finally {
      setReportSubmitting(false)
    }
  }

  const closeReportModal = () => {
    setReportItem(null)
    setReportReason('')
    setReportDetails('')
    setReportError('')
    setReportSubmitted(false)
  }

  const REPORT_REASONS: { value: string; label: string }[] = [
    { value: 'inaccurate_content', label: 'Inaccurate content' },
    { value: 'plagiarised_material', label: 'Plagiarised material' },
    { value: 'inappropriate_content', label: 'Inappropriate content' },
    { value: 'copyright_violation', label: 'Copyright violation' },
    { value: 'other', label: 'Other' },
  ]

  const loadBrowse = () => {
    setBrowseLoading(true)
    setBrowseError('')
    const params = new URLSearchParams({ page: '1' })
    if (materialTypeFilter) params.set('material_type', materialTypeFilter)
    if (search.trim()) params.set('q', search.trim())
    if (unitFilter != null) params.set('unit_id', String(unitFilter))
    if (universityFilter != null) params.set('university_id', String(universityFilter))
    api<{ page: number; publications: LibraryPublicationSummary[] }>(`/library?${params.toString()}`)
      .then(res => setBrowseItems(res.publications))
      .catch(e => setBrowseError(e instanceof ApiError ? e.message : 'Could not load the library - check your connection and try again.'))
      .finally(() => setBrowseLoading(false))
  }

  const loadSaved = () => {
    setSavedLoading(true)
    setSavedError('')
    api<{ saved: SavedLibraryItem[] }>('/library/saved')
      .then(res => { setSavedItems(res.saved); setSavedIds(new Set(res.saved.map(s => s.id))) })
      .catch(e => setSavedError(e instanceof ApiError ? e.message : 'Could not load your saved items.'))
      .finally(() => setSavedLoading(false))
  }

  const loadSubmissions = () => {
    setSubmissionsLoading(true)
    setSubmissionsError('')
    api<{ submissions: MySubmission[] }>('/library/my-submissions')
      .then(res => setSubmissions(res.submissions))
      .catch(e => setSubmissionsError(e instanceof ApiError ? e.message : 'Could not load your submissions.'))
      .finally(() => setSubmissionsLoading(false))
  }

  useEffect(() => {
    const t = setTimeout(() => { loadBrowse() }, search.trim() ? 350 : 0)
    return () => clearTimeout(t)
  }, [materialTypeFilter, unitFilter, universityFilter, search])
  useEffect(() => { loadSaved() }, [])
  useEffect(() => { loadSubmissions() }, [])

  const toggleSave = async (pub: LibraryPublicationSummary) => {
    if (!csrfToken) return
    const isSaved = savedIds.has(pub.id)
    setSavedIds(prev => { const next = new Set(prev); isSaved ? next.delete(pub.id) : next.add(pub.id); return next })
    setBrowseItems(items => items.map(it => it.id === pub.id ? { ...it, save_count: it.save_count + (isSaved ? -1 : 1) } : it))
    try {
      if (isSaved) {
        await api(`/library/${pub.id}/save`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
        setSavedItems(items => items.filter(it => it.id !== pub.id))
      } else {
        await api(`/library/${pub.id}/save`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
        loadSaved()
      }
    } catch {
      setSavedIds(prev => { const next = new Set(prev); isSaved ? next.add(pub.id) : next.delete(pub.id); return next })
      setBrowseItems(items => items.map(it => it.id === pub.id ? { ...it, save_count: it.save_count + (isSaved ? 1 : -1) } : it))
    }
  }

  const statusColor = (status: string) => status === 'approved' ? '#4CC97B' : status === 'rejected' ? '#C94C4C' : N.gold

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      {reportItem && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 99 }}>
          <div style={{ background: '#fff', borderRadius: 20, padding: 24, width: '100%', maxWidth: 360 }}>
            {reportSubmitted ? (
              <>
                <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 8 }}>Report submitted</div>
                <div style={{ fontSize: 13, color: '#6B7280', marginBottom: 20 }}>Thanks - our team will review "{reportItem.title}".</div>
                <button onClick={closeReportModal} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 12, padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 13, color: N.navy }}>Done</button>
              </>
            ) : (
              <>
                <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 4 }}>Report Material</div>
                <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 14 }} className="line-clamp-1">{reportItem.title}</div>
                {REPORT_REASONS.map(r => (
                  <button key={r.value} onClick={() => setReportReason(r.value)} style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', background: reportReason === r.value ? 'rgba(201,168,76,0.12)' : '#F8F9FC', border: reportReason === r.value ? `1px solid ${N.gold}55` : '1px solid transparent', borderRadius: 10, padding: '11px 14px', marginBottom: 8, textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: N.navy, cursor: 'pointer' }}>{r.label}</button>
                ))}
                <textarea value={reportDetails} onChange={e => setReportDetails(e.target.value)} placeholder="Additional details (optional)" rows={2} maxLength={500} style={{ width: '100%', border: '1px solid rgba(0,0,0,0.1)', borderRadius: 10, padding: '10px 12px', fontSize: 12, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, resize: 'none', boxSizing: 'border-box', marginTop: 4, marginBottom: 10 }} />
                {reportError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 10 }}>{reportError}</div>}
                <div style={{ display: 'flex', gap: 10 }}>
                  <button onClick={closeReportModal} style={{ flex: 1, background: '#F3F4F6', border: 'none', borderRadius: 12, padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, color: '#374151' }}>Cancel</button>
                  <button onClick={submitReport} disabled={!reportReason || reportSubmitting} style={{ flex: 1, background: (!reportReason || reportSubmitting) ? '#E5E7EB' : '#C94C4C', border: 'none', borderRadius: 12, padding: '12px 0', cursor: (!reportReason || reportSubmitting) ? 'not-allowed' : 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 13, color: (!reportReason || reportSubmitting) ? '#9CA3AF' : '#fff' }}>{reportSubmitting ? 'Submitting…' : 'Submit'}</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 18, color: '#fff' }}>Prepza Library</span>
          <button onClick={() => setScreen('publish-library')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 11, border: 'none', borderRadius: 10, padding: '7px 12px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>+ Publish</button>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {(['Browse', 'Saved', 'Published'] as const).map(t => (
            <button key={t} onClick={() => setActiveTab(t)} style={{ flexShrink: 0, padding: '6px 14px', borderRadius: 20, background: activeTab === t ? N.gold : 'rgba(255,255,255,0.1)', color: activeTab === t ? N.navy : 'rgba(255,255,255,0.65)', fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{t}</button>
          ))}
        </div>
        {activeTab === 'Browse' && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, background: 'rgba(255,255,255,0.08)', borderRadius: 12, padding: '8px 12px' }}>
              <div style={{ color: 'rgba(255,255,255,0.4)' }}>{Ic.search('w-4 h-4')}</div>
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search the library…" style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: 12, fontFamily: 'Plus Jakarta Sans' }} />
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 10, overflowX: 'auto' }} className="scrollbar-hide">
              <button onClick={() => setMaterialTypeFilter(null)} style={{ flexShrink: 0, padding: '5px 12px', borderRadius: 20, background: !materialTypeFilter ? 'rgba(255,255,255,0.18)' : 'rgba(255,255,255,0.08)', color: '#fff', fontWeight: 600, fontSize: 10, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>All types</button>
              {LIBRARY_MATERIAL_TYPES.map(t => (
                <button key={t.value} onClick={() => setMaterialTypeFilter(t.value)} style={{ flexShrink: 0, padding: '5px 12px', borderRadius: 20, background: materialTypeFilter === t.value ? 'rgba(255,255,255,0.18)' : 'rgba(255,255,255,0.08)', color: '#fff', fontWeight: 600, fontSize: 10, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{t.label}</button>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 8, overflowX: 'auto' }} className="scrollbar-hide">
              <select value={unitFilter ?? ''} onChange={e => setUnitFilter(e.target.value ? Number(e.target.value) : null)} style={{ flexShrink: 0, background: 'rgba(255,255,255,0.08)', color: '#fff', border: 'none', borderRadius: 10, padding: '5px 10px', fontSize: 10, fontFamily: 'Plus Jakarta Sans' }}>
                <option value="">All units</option>
                {filterUnits.map(u => <option key={u.id} value={u.id}>{u.code}</option>)}
              </select>
              <select value={universityFilter ?? ''} onChange={e => setUniversityFilter(e.target.value ? Number(e.target.value) : null)} style={{ flexShrink: 0, background: 'rgba(255,255,255,0.08)', color: '#fff', border: 'none', borderRadius: 10, padding: '5px 10px', fontSize: 10, fontFamily: 'Plus Jakarta Sans' }}>
                <option value="">All universities</option>
                {filterUniversities.map(u => <option key={u.id} value={u.id}>{u.short_code}</option>)}
              </select>
            </div>
          </>
        )}
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 16 }} className="scrollbar-hide">
        {activeTab === 'Browse' && (
          browseLoading ? (
            <div style={{ fontSize: 12, color: '#9CA3AF', padding: '12px 0' }}>Loading the library…</div>
          ) : browseError ? (
            <ErrorState onRetry={loadBrowse} />
          ) : browseItems.length === 0 ? (
            <EmptyState icon="📚" title="Nothing published yet" sub="Be the first to share notes or past papers with other students." action="Publish Material" onAction={() => setScreen('publish-library')} />
          ) : browseItems.map(pub => (
            <div key={pub.id} style={{ background: '#fff', borderRadius: 14, padding: '13px 14px', marginBottom: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', display: 'flex', gap: 12, alignItems: 'center' }}>
              <div style={{ width: 44, height: 44, background: '#F3F4F6', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, flexShrink: 0 }}>📕</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 2 }} className="line-clamp-1">{pub.title}</div>
                <div style={{ fontSize: 11, color: '#9CA3AF' }}>{pub.author}{pub.unit_code ? ` · ${pub.unit_code}` : ''} · {pub.view_count} views · {pub.save_count} saves</div>
              </div>
              <button onClick={() => toggleSave(pub)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: savedIds.has(pub.id) ? N.gold : '#9CA3AF', flexShrink: 0 }}>{Ic.bookmark('w-5 h-5')}</button>
              <button onClick={() => setReportItem(pub)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9CA3AF', flexShrink: 0 }}>{Ic.dots('w-4 h-4')}</button>
            </div>
          ))
        )}
        {activeTab === 'Saved' && (
          savedLoading ? (
            <div style={{ fontSize: 12, color: '#9CA3AF', padding: '12px 0' }}>Loading your saved items…</div>
          ) : savedError ? (
            <ErrorState onRetry={loadSaved} />
          ) : savedItems.length === 0 ? (
            <EmptyState icon="📚" title="No saved items yet" sub="Bookmark items from the library to find them here." action="Browse Library" onAction={() => setActiveTab('Browse')} />
          ) : savedItems.map(pub => (
            <div key={pub.id} style={{ background: '#fff', borderRadius: 14, padding: '13px 14px', marginBottom: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', display: 'flex', gap: 12, alignItems: 'center' }}>
              <div style={{ width: 44, height: 44, background: '#F3F4F6', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, flexShrink: 0 }}>📕</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 2 }} className="line-clamp-1">{pub.title}</div>
                <div style={{ fontSize: 11, color: '#9CA3AF' }}>{pub.author}{pub.unit_code ? ` · ${pub.unit_code}` : ''}</div>
              </div>
              <button onClick={() => toggleSave(pub)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: N.gold, flexShrink: 0 }}>{Ic.bookmark('w-5 h-5')}</button>
            </div>
          ))
        )}
        {activeTab === 'Published' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#9CA3AF' }}>Materials you've submitted to the Prepza Library</div>
              <button onClick={() => setScreen('publish-library')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 11, border: 'none', borderRadius: 10, padding: '6px 12px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>+ Publish</button>
            </div>
            {submissionsLoading ? (
              <div style={{ fontSize: 12, color: '#9CA3AF', padding: '12px 0' }}>Loading your submissions…</div>
            ) : submissionsError ? (
              <ErrorState onRetry={loadSubmissions} />
            ) : submissions.length === 0 ? (
              <EmptyState icon="📖" title="Nothing published yet" sub="Share your notes and materials with students across Kenya. Earn XP for approved contributions." action="Publish Material" onAction={() => setScreen('publish-library')} />
            ) : submissions.map(p => (
              <div key={p.id} style={{ background: '#fff', borderRadius: 16, padding: '14px 16px', marginBottom: 10, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', border: `1.5px solid ${p.status === 'approved' ? 'rgba(76,201,123,0.2)' : 'rgba(0,0,0,0.06)'}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 3 }} className="line-clamp-1">{p.title}</div>
                    <div style={{ fontSize: 11, color: '#9CA3AF' }}>{materialTypeLabel(p.material_type)}{p.unit_code ? ` · ${p.unit_code}` : ''}</div>
                  </div>
                  <Pill text={p.status.charAt(0).toUpperCase() + p.status.slice(1)} color={statusColor(p.status)} />
                </div>
                {p.status === 'approved' && (
                  <div style={{ display: 'flex', gap: 16, fontSize: 11, color: '#9CA3AF', marginTop: 8, paddingTop: 8, borderTop: '1px solid #F3F4F6' }}>
                    <span>{p.view_count} views</span>
                    <span>{p.save_count} saves</span>
                    <span style={{ marginLeft: 'auto' }}>{p.created_at ? new Date(p.created_at).toLocaleDateString() : ''}</span>
                  </div>
                )}
                {p.status === 'pending' && (
                  <div style={{ fontSize: 11, color: '#D97706', marginTop: 6, fontWeight: 600 }}>Submitted {p.created_at ? new Date(p.created_at).toLocaleDateString() : ''} · Review takes 24-48h</div>
                )}
                {p.status === 'rejected' && p.rejection_reason && (
                  <div style={{ fontSize: 11, color: '#C94C4C', marginTop: 6, fontWeight: 600 }}>Rejected: {p.rejection_reason}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}



// ─── PODCAST LIBRARY ──────────────────────────────────────────────────────────
function PodcastLibraryScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const loading = useLoading(900)
  if (loading) return <SkeletonPodcastLibrary />
  const allPodcasts = [
    ...podcasts,
    { id: 5, title: 'Probability Foundations', subject: 'STA 101', duration: '14 min', icon: 'P', color: '#9B59B6' },
    { id: 6, title: 'Microeconomics Basics', subject: 'ECO 101', duration: '11 min', icon: '📊', color: '#C94C4C' },
  ]
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 18, color: '#fff' }}>Study Podcasts 🎙️</span>
        </div>
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>AI-generated from your notes</div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 16 }} className="scrollbar-hide">
        <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 12 }}>Your Episodes</div>
        {allPodcasts.map((p) => (
          <div key={p.id} onClick={() => setScreen('podcast-player')} style={{ display: 'flex', gap: 14, alignItems: 'center', background: '#fff', borderRadius: 14, padding: '13px 14px', marginBottom: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', cursor: 'pointer' }}>
            <div style={{ width: 52, height: 52, background: `linear-gradient(135deg,${p.color},${p.color}99)`, borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, color: '#fff', fontWeight: 800, flexShrink: 0 }}>{p.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>{p.title}</div>
              <div style={{ fontSize: 11, color: '#6B7280', marginTop: 2 }}>{p.subject} · {p.duration}</div>
            </div>
            <div style={{ color: N.gold }}>{Ic.play()}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── MIND MAP ─────────────────────────────────────────────────────────────────
type MindMapNode = { id: string; label: string; x: number; y: number; r: number; color: string; textColor: string; fontSize: number }

function MindMapScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const [raw, setRaw] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) { setLoading(false); setError('No document selected.'); return }
    api<{ csrf_token: string }>('/me')
      .then(me => api<{ material_id: number; reused: boolean; mindmap: any }>(`/documents/${activeDocumentId}/mindmap`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': me.csrf_token },
      }))
      .then(res => setRaw(res.mindmap))
      .catch(e => {
        if (e instanceof ApiError && e.status === 429) setError("You've hit the hourly generation limit - try again later.")
        else if (e instanceof ApiError && e.status === 503) setError('AI budget exceeded for now - try again later.')
        else setError(e instanceof ApiError ? e.message : 'Could not generate a mind map. Please try again.')
      })
      .finally(() => setLoading(false))
  }, [activeDocumentId])

  // Builds a simple radial layout from whatever ai_service.py returned:
  // tries {center, branches:[...]} or {nodes:[...], edges:[...]} shapes.
  // Falls back to raw JSON if neither is recognizable.
  const palette = [N.navy2, N.navy3, '#4C7BC9', '#4CC97B', '#9B59B6', '#C94C4C']
  const buildLayout = (): { nodes: MindMapNode[]; lines: [string, string][] } | null => {
    if (!raw) return null
    const centerLabel: string = raw.center || raw.root || raw.title || 'Overview'
    const branches: string[] = Array.isArray(raw.branches) ? raw.branches
      : Array.isArray(raw.nodes) ? raw.nodes.map((n: any) => n.label || n.name || String(n))
      : []
    if (branches.length === 0) return null

    const nodes: MindMapNode[] = [{ id: 'center', label: centerLabel, x: 150, y: 150, r: 44, color: N.gold, textColor: N.navy, fontSize: 11 }]
    const lines: [string, string][] = []
    const angleStep = (2 * Math.PI) / branches.length
    const radius = 110
    branches.forEach((label, i) => {
      const id = `n${i}`
      const angle = i * angleStep
      nodes.push({
        id, label: String(label),
        x: 150 + radius * Math.cos(angle), y: 150 + radius * Math.sin(angle),
        r: 34, color: palette[i % palette.length], textColor: '#fff', fontSize: 10,
      })
      lines.push(['center', id])
    })
    return { nodes, lines }
  }

  const layout = buildLayout()

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('document-study')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>Mind Map</div>
          </div>
        </div>
      </div>
      {loading ? <GenerationLoading label="Generating your mind map…" /> : error ? <GenerationError error={error} /> : !layout ? (
        <div style={{ flex: 1, overflowY: 'auto', padding: 20 }} className="scrollbar-hide">
          <pre style={{ fontSize: 11, color: '#374151', whiteSpace: 'pre-wrap', background: '#fff', borderRadius: 12, padding: 14, boxShadow: '0 2px 10px rgba(0,0,0,0.06)' }}>{JSON.stringify(raw, null, 2)}</pre>
        </div>
      ) : (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
          <div style={{ background: '#fff', borderRadius: 20, padding: 16, boxShadow: '0 4px 20px rgba(0,0,0,0.08)', width: '100%', marginBottom: 16 }}>
            <svg viewBox="-10 -10 320 320" style={{ width: '100%', height: 300 }}>
              {layout.lines.map(([from, to]) => {
                const f = layout.nodes.find(n => n.id === from)!
                const t = layout.nodes.find(n => n.id === to)!
                return <line key={from+to} x1={f.x} y1={f.y} x2={t.x} y2={t.y} stroke="rgba(11,20,55,0.15)" strokeWidth="2" />
              })}
              {layout.nodes.map(node => (
                <g key={node.id} style={{ cursor: 'pointer' }}>
                  <circle cx={node.x} cy={node.y} r={node.r} fill={node.color} />
                  {node.label.split('\n').map((line, i, arr) => (
                    <text key={i} x={node.x} y={node.y + (i - (arr.length - 1) / 2) * (node.fontSize + 2)} textAnchor="middle" dominantBaseline="middle" fontSize={node.fontSize} fontWeight="700" fill={node.textColor} fontFamily="Plus Jakarta Sans">{line}</text>
                  ))}
                </g>
              ))}
            </svg>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%' }}>
            {layout.nodes.slice(1).map(node => (
              <div key={node.id} style={{ display: 'flex', gap: 10, alignItems: 'center', background: '#fff', borderRadius: 12, padding: '10px 14px', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
                <div style={{ width: 10, height: 10, borderRadius: '50%', background: node.color, flexShrink: 0 }} />
                <div style={{ fontWeight: 600, fontSize: 13, color: N.navy }}>{node.label.replace('\n',' ')}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── NEW CHAT ─────────────────────────────────────────────────────────────────
type UserSearchResult = { id: number; display_name: string; year: number | null; semester: number | null }

function NewChatScreen({ setScreen, setActiveConversationId }: { setScreen: (s: Screen) => void; setActiveConversationId: (id: number) => void }) {
  const [mode, setMode] = useState<'select'|'new-chat'|'new-group'>('select')
  const [search, setSearch] = useState('')
  const [results, setResults] = useState<UserSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [csrfToken, setCsrfToken] = useState('')
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [groupName, setGroupName] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
  }, [])

  useEffect(() => {
    if (mode === 'select') return
    const q = search.trim()
    if (!q) { setResults([]); setSearchError(null); return }
    let cancelled = false
    setSearching(true)
    const t = setTimeout(() => {
      api<{ users: UserSearchResult[] }>(`/users/search?q=${encodeURIComponent(q)}`)
        .then(data => { if (!cancelled) { setResults(data.users); setSearchError(null) } })
        .catch(e => { if (!cancelled) setSearchError(e instanceof Error ? e.message : 'Search failed') })
        .finally(() => { if (!cancelled) setSearching(false) })
    }, 300)
    return () => { cancelled = true; clearTimeout(t) }
  }, [search, mode])

  const startDirectChat = async (userId: number) => {
    if (creating) return
    setCreating(true)
    setCreateError(null)
    try {
      const res = await api<{ id: number; reused: boolean }>('/chats', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ is_group: false, participant_ids: [userId] }),
      })
      setActiveConversationId(res.id)
      setScreen('chat-detail')
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : 'Could not start chat')
    } finally {
      setCreating(false)
    }
  }

  const toggleSelected = (userId: number) => {
    setSelectedIds(ids => ids.includes(userId) ? ids.filter(id => id !== userId) : [...ids, userId])
  }

  const createGroup = async () => {
    if (creating) return
    if (!groupName.trim()) { setCreateError('Group name is required'); return }
    if (selectedIds.length === 0) { setCreateError('Select at least one member'); return }
    setCreating(true)
    setCreateError(null)
    try {
      const res = await api<{ id: number; reused: boolean }>('/chats', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ is_group: true, name: groupName.trim(), participant_ids: selectedIds }),
      })
      setActiveConversationId(res.id)
      setScreen('chat-detail')
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : 'Could not create group')
    } finally {
      setCreating(false)
    }
  }

  if (mode === 'select') return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('chats')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 18, color: '#fff' }}>New Conversation</span>
        </div>
      </div>
      <div style={{ flex: 1, padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <button onClick={() => setMode('new-chat')} style={{ display: 'flex', alignItems: 'center', gap: 14, background: '#fff', border: 'none', borderRadius: 16, padding: 16, cursor: 'pointer', boxShadow: '0 2px 10px rgba(0,0,0,0.05)', fontFamily: 'Plus Jakarta Sans' }}>
          <div style={{ width: 48, height: 48, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22 }}>💬</div>
          <div style={{ textAlign: 'left' }}><div style={{ fontWeight: 800, fontSize: 14, color: N.navy }}>New Chat</div><div style={{ fontSize: 12, color: '#6B7280' }}>Message a classmate directly</div></div>
        </button>
        <button onClick={() => setMode('new-group')} style={{ display: 'flex', alignItems: 'center', gap: 14, background: '#fff', border: 'none', borderRadius: 16, padding: 16, cursor: 'pointer', boxShadow: '0 2px 10px rgba(0,0,0,0.05)', fontFamily: 'Plus Jakarta Sans' }}>
          <div style={{ width: 48, height: 48, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22 }}>👥</div>
          <div style={{ textAlign: 'left' }}><div style={{ fontWeight: 800, fontSize: 14, color: N.navy }}>New Group</div><div style={{ fontSize: 12, color: '#6B7280' }}>Create a study group chat</div></div>
        </button>
      </div>
    </div>
  )
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#fff' }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => setMode('select')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>{mode === 'new-chat' ? 'Select Contact' : 'New Group'}</span>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', background: 'rgba(255,255,255,0.09)', borderRadius: 12, padding: '9px 12px' }}>
          <div style={{ color: 'rgba(255,255,255,0.4)' }}>{Ic.search('w-4 h-4')}</div>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search students…" style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: 13, fontFamily: 'Plus Jakarta Sans' }} />
        </div>
        {mode === 'new-group' && (
          <input value={groupName} onChange={e => setGroupName(e.target.value)} placeholder="Group name…" style={{ marginTop: 10, width: '100%', boxSizing: 'border-box', background: 'rgba(255,255,255,0.09)', border: 'none', borderRadius: 12, padding: '10px 12px', color: '#fff', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none' }} />
        )}
      </div>
      <div style={{ flex: 1, overflowY: 'auto' }} className="scrollbar-hide">
        {createError && <div style={{ padding: '10px 16px', color: '#C94C4C', fontSize: 12, fontFamily: 'Plus Jakarta Sans' }}>{createError}</div>}
        {searchError && <div style={{ padding: '10px 16px', color: '#C94C4C', fontSize: 12, fontFamily: 'Plus Jakarta Sans' }}>{searchError}</div>}
        {!search.trim() ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 20px', textAlign: 'center' }}>
            <div style={{ fontSize: 44, marginBottom: 12 }}>🔍</div>
            <div style={{ fontWeight: 700, fontSize: 16, color: N.navy }}>Search for students</div>
            <div style={{ fontSize: 13, color: '#6B7280', marginTop: 4 }}>Start typing a name to find classmates</div>
          </div>
        ) : searching ? (
          <div style={{ padding: '20px 16px', textAlign: 'center', color: '#9CA3AF', fontSize: 13, fontFamily: 'Plus Jakarta Sans' }}>Searching…</div>
        ) : results.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 20px', textAlign: 'center' }}>
            <div style={{ fontSize: 44, marginBottom: 12 }}>🙁</div>
            <div style={{ fontWeight: 700, fontSize: 16, color: N.navy }}>No students found</div>
          </div>
        ) : results.map(c => {
          const initials = (c.display_name || '??').slice(0, 2).toUpperCase()
          const course = c.year != null && c.semester != null ? `Year ${c.year} · Semester ${c.semester}` : 'Prepza student'
          const selected = selectedIds.includes(c.id)
          return (
            <div key={c.id} onClick={() => mode === 'new-chat' ? startDirectChat(c.id) : toggleSelected(c.id)} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '13px 16px', cursor: 'pointer', borderBottom: '1px solid rgba(0,0,0,0.04)', opacity: creating ? 0.6 : 1 }}>
              <Avi name={initials} size={44} />
              <div style={{ flex: 1 }}><div style={{ fontWeight: 700, fontSize: 14, color: N.navy }}>{c.display_name}</div><div style={{ fontSize: 12, color: '#6B7280' }}>{course}</div></div>
              {mode === 'new-chat' && <div style={{ color: N.gold }}>{Ic.chevR()}</div>}
              {mode === 'new-group' && (
                <div style={{ width: 22, height: 22, borderRadius: '50%', border: `2px solid ${selected ? N.gold : '#D1D5DB'}`, background: selected ? N.gold : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, color: N.navy, fontWeight: 800, flexShrink: 0 }}>{selected ? '✓' : ''}</div>
              )}
            </div>
          )
        })}
        {mode === 'new-group' && (
          <div style={{ padding: '20px 16px' }}>
            <button onClick={createGroup} disabled={creating} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '14px 0', cursor: creating ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: creating ? 0.7 : 1 }}>{creating ? 'Creating…' : `Create Group${selectedIds.length ? ` (${selectedIds.length})` : ''} →`}</button>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── CHAT OPTIONS ─────────────────────────────────────────────────────────────
type SharedMediaItem = { id: number; message_id: number; file_type: string; original_filename: string; file_size_bytes: number; view_url: string | null; uploaded_by_user_id: number; uploaded_by_name: string; created_at: string | null }

function ChatOptionsScreen({ setScreen, conversationId }: { setScreen: (s: Screen) => void; conversationId: number | null }) {
  const [detail, setDetail] = useState<ChatDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [csrfToken, setCsrfToken] = useState('')
  const [showRename, setShowRename] = useState(false)
  const [renameVal, setRenameVal] = useState('')
  const [renaming, setRenaming] = useState(false)
  const [renameError, setRenameError] = useState<string | null>(null)
  const [leaving, setLeaving] = useState(false)
  const [leaveError, setLeaveError] = useState<string | null>(null)
  const [mutingBusy, setMutingBusy] = useState(false)
  const [muteError, setMuteError] = useState<string | null>(null)
  const [showSearch, setShowSearch] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<ChatMessageData[]>([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [showMedia, setShowMedia] = useState(false)
  const [mediaItems, setMediaItems] = useState<SharedMediaItem[]>([])
  const [mediaLoading, setMediaLoading] = useState(false)
  const [mediaError, setMediaError] = useState<string | null>(null)

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
  }, [])

  useEffect(() => {
    if (conversationId == null) { setLoading(false); return }
    let cancelled = false
    setLoading(true)
    setError(null)
    api<ChatDetail>(`/chats/${conversationId}`)
      .then(d => { if (!cancelled) { setDetail(d); setRenameVal(d.name) } })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load chat info') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [conversationId])

  useEffect(() => {
    if (!showSearch || conversationId == null) return
    const q = searchQuery.trim()
    if (!q) { setSearchResults([]); setSearchError(null); setSearching(false); return }
    let cancelled = false
    setSearching(true)
    const t = setTimeout(() => {
      api<{ messages: ChatMessageData[] }>(`/chats/${conversationId}/messages/search?q=${encodeURIComponent(q)}`)
        .then(res => { if (!cancelled) { setSearchResults(res.messages); setSearchError(null) } })
        .catch(e => { if (!cancelled) setSearchError(e instanceof Error ? e.message : 'Search failed') })
        .finally(() => { if (!cancelled) setSearching(false) })
    }, 300)
    return () => { cancelled = true; clearTimeout(t) }
  }, [searchQuery, showSearch, conversationId])

  useEffect(() => {
    if (!showMedia || conversationId == null) return
    let cancelled = false
    setMediaLoading(true)
    setMediaError(null)
    api<{ attachments: SharedMediaItem[] }>(`/chats/${conversationId}/attachments`)
      .then(res => { if (!cancelled) setMediaItems(res.attachments) })
      .catch(e => { if (!cancelled) setMediaError(e instanceof Error ? e.message : 'Could not load shared media') })
      .finally(() => { if (!cancelled) setMediaLoading(false) })
    return () => { cancelled = true }
  }, [showMedia, conversationId])

  const saveRename = async () => {
    if (!renameVal.trim() || conversationId == null || renaming) return
    setRenaming(true)
    setRenameError(null)
    try {
      const res = await api<{ id: number; name: string }>(`/chats/${conversationId}`, {
        method: 'PATCH',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ name: renameVal.trim() }),
      })
      setDetail(d => d ? { ...d, name: res.name } : d)
      setShowRename(false)
    } catch (e) {
      setRenameError(e instanceof Error ? e.message : 'Could not rename group')
    } finally {
      setRenaming(false)
    }
  }

  const leaveGroup = async () => {
    if (conversationId == null || leaving) return
    setLeaving(true)
    setLeaveError(null)
    try {
      await api(`/chats/${conversationId}/leave`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      setScreen('chats')
    } catch (e) {
      setLeaveError(e instanceof Error ? e.message : 'Could not leave group')
    } finally {
      setLeaving(false)
    }
  }

  const toggleMute = async () => {
    if (conversationId == null || detail == null || mutingBusy) return
    setMutingBusy(true)
    setMuteError(null)
    const next = !detail.viewer_muted
    try {
      const res = await api<{ muted: boolean }>(`/chats/${conversationId}/mute`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ muted: next }),
      })
      setDetail(d => d ? { ...d, viewer_muted: res.muted } : d)
    } catch (e) {
      setMuteError(e instanceof Error ? e.message : 'Could not update notifications')
    } finally {
      setMutingBusy(false)
    }
  }

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
        <div style={{ background: N.navy, padding: '0 18px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => setScreen('chat-detail')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Chat Info</span>
          </div>
        </div>
        <div style={{ padding: '40px 20px', textAlign: 'center', color: '#9CA3AF', fontSize: 13, fontFamily: 'Plus Jakarta Sans' }}>Loading…</div>
      </div>
    )
  }

  const initials = (detail?.name || '??').slice(0, 2).toUpperCase()

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg, position: 'relative' }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <button onClick={() => setScreen('chat-detail')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>{detail?.is_group ? 'Group Info' : 'Chat Info'}</span>
        </div>
        {error ? (
          <div style={{ color: '#ffb4bd', fontSize: 13, textAlign: 'center' }}>{error}</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <Avi name={initials} size={64} />
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff', marginTop: 12 }}>{detail?.name}</div>
            {detail?.is_group && <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.5)', marginTop: 4 }}>{detail.member_count} member{detail.member_count === 1 ? '' : 's'} · Created by {detail.created_by_name}</div>}
          </div>
        )}
      </div>
      <div style={{ padding: 16 }}>
        {detail?.is_group && (
          <div onClick={() => { setRenameError(null); setShowRename(true) }} style={{ background: '#fff', borderRadius: 14, padding: '13px 16px', marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', cursor: 'pointer' }}>
            <span style={{ fontSize: 20 }}>✏️</span>
            <div style={{ flex: 1 }}><div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>Rename Group</div><div style={{ fontSize: 11, color: '#9CA3AF' }}>{detail.name}</div></div>
            {Ic.chevR()}
          </div>
        )}
        <div onClick={() => { setMediaError(null); setShowMedia(true) }} style={{ background: '#fff', borderRadius: 14, padding: '13px 16px', marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', cursor: 'pointer' }}>
          <span style={{ fontSize: 20 }}>🖼️</span>
          <div style={{ flex: 1 }}><div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>Shared Media</div><div style={{ fontSize: 11, color: '#9CA3AF' }}>Files and images shared here</div></div>
          {Ic.chevR()}
        </div>
        <div onClick={() => { setSearchError(null); setShowSearch(true) }} style={{ background: '#fff', borderRadius: 14, padding: '13px 16px', marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', cursor: 'pointer' }}>
          <span style={{ fontSize: 20 }}>🔍</span>
          <div style={{ flex: 1 }}><div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>Search Messages</div><div style={{ fontSize: 11, color: '#9CA3AF' }}>Find something in this chat</div></div>
          {Ic.chevR()}
        </div>
        <div style={{ background: '#fff', borderRadius: 14, padding: '13px 16px', marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', opacity: mutingBusy ? 0.6 : 1 }}>
          <span style={{ fontSize: 20 }}>🔔</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>Notifications</div>
            <div style={{ fontSize: 11, color: '#9CA3AF' }}>{detail && !detail.viewer_muted ? 'On' : 'Muted'}</div>
            {muteError && <div style={{ fontSize: 11, color: '#C94C4C', marginTop: 2 }}>{muteError}</div>}
          </div>
          <div onClick={toggleMute}>{Ic.toggle(!!detail && !detail.viewer_muted)}</div>
        </div>
        {detail?.is_group && detail.participants.length > 0 && (
          <div style={{ background: '#fff', borderRadius: 14, marginBottom: 8, overflow: 'hidden', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
            <div style={{ padding: '12px 16px 8px', fontWeight: 700, fontSize: 12, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: 0.4 }}>Members ({detail.participants.length})</div>
            {detail.participants.map(p => (
              <div key={p.user_id} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '10px 16px', borderTop: '1px solid rgba(0,0,0,0.04)' }}>
                <Avi name={(p.display_name || '??').slice(0, 2).toUpperCase()} size={34} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, color: N.navy }} className="line-clamp-1">{p.display_name}{p.user_id === detail.created_by ? ' (Creator)' : ''}</div>
                </div>
                {p.role === 'admin' && <Pill text="Admin" />}
              </div>
            ))}
          </div>
        )}
        {detail?.is_group && (
          <div style={{ background: '#fff', borderRadius: 14, marginTop: 12, overflow: 'hidden' }}>
            {leaveError && <div style={{ padding: '10px 16px', color: '#C94C4C', fontSize: 12, fontFamily: 'Plus Jakarta Sans' }}>{leaveError}</div>}
            <button onClick={leaveGroup} disabled={leaving} style={{ display: 'flex', gap: 12, alignItems: 'center', width: '100%', padding: '14px 16px', background: 'none', border: 'none', cursor: leaving ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: leaving ? 0.6 : 1 }}>
              <span style={{ fontSize: 20 }}>🚪</span>
              <span style={{ fontWeight: 700, fontSize: 13, color: '#C94C4C' }}>{leaving ? 'Leaving…' : 'Leave Group'}</span>
            </button>
          </div>
        )}
      </div>

      {showRename && (
        <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 50 }}>
          <div style={{ background: '#fff', borderRadius: 20, padding: 24, width: '100%' }}>
            <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 16 }}>Rename Group</div>
            <input value={renameVal} onChange={e => setRenameVal(e.target.value)} maxLength={100} style={{ width: '100%', border: '1px solid rgba(0,0,0,0.12)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, boxSizing: 'border-box' }} />
            {renameError && <div style={{ color: '#C94C4C', fontSize: 12, marginTop: 8 }}>{renameError}</div>}
            <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
              <button onClick={() => setShowRename(false)} style={{ flex: 1, background: '#F3F4F6', border: 'none', borderRadius: 12, padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, color: '#374151' }}>Cancel</button>
              <button onClick={saveRename} disabled={renaming} style={{ flex: 1, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 12, padding: '12px 0', cursor: renaming ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 13, color: N.navy, opacity: renaming ? 0.7 : 1 }}>{renaming ? 'Saving…' : 'Save'}</button>
            </div>
          </div>
        </div>
      )}
      {showSearch && (
        <div style={{ position: 'absolute', inset: 0, background: N.bg, display: 'flex', flexDirection: 'column', zIndex: 50 }}>
          <div style={{ background: N.navy, padding: '0 18px 14px', flexShrink: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <button onClick={() => { setShowSearch(false); setSearchQuery(''); setSearchResults([]) }} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
              <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Search Messages</span>
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', background: 'rgba(255,255,255,0.09)', borderRadius: 12, padding: '9px 12px' }}>
              <div style={{ color: 'rgba(255,255,255,0.4)' }}>{Ic.search('w-4 h-4')}</div>
              <input autoFocus value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Search this conversation…" style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: 13, fontFamily: 'Plus Jakarta Sans' }} />
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }} className="scrollbar-hide">
            {searchError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 10 }}>{searchError}</div>}
            {!searchQuery.trim() ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 20px', textAlign: 'center' }}>
                <div style={{ fontSize: 44, marginBottom: 12 }}>🔍</div>
                <div style={{ fontWeight: 700, fontSize: 16, color: N.navy }}>Search this chat</div>
                <div style={{ fontSize: 13, color: '#6B7280', marginTop: 4 }}>Start typing to find a message</div>
              </div>
            ) : searching ? (
              <div style={{ padding: '20px 0', textAlign: 'center', color: '#9CA3AF', fontSize: 13, fontFamily: 'Plus Jakarta Sans' }}>Searching…</div>
            ) : searchResults.length === 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 20px', textAlign: 'center' }}>
                <div style={{ fontSize: 44, marginBottom: 12 }}>🙁</div>
                <div style={{ fontWeight: 700, fontSize: 16, color: N.navy }}>No messages found</div>
              </div>
            ) : searchResults.map(m => {
              const sender = detail?.participants.find(p => p.user_id === m.sender_id)
              const senderName = sender?.display_name || 'Deleted user'
              return (
                <div key={m.id} style={{ background: '#fff', borderRadius: 14, padding: '12px 14px', marginBottom: 8, boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ fontWeight: 700, fontSize: 12, color: N.gold }}>{senderName}</span>
                    <span style={{ fontSize: 11, color: '#9CA3AF' }}>{m.created_at ? new Date(m.created_at).toLocaleString() : ''}</span>
                  </div>
                  <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.55 }}>{m.body}</div>
                </div>
              )
            })}
          </div>
        </div>
      )}
      {showMedia && (
        <div style={{ position: 'absolute', inset: 0, background: N.bg, display: 'flex', flexDirection: 'column', zIndex: 50 }}>
          <div style={{ background: N.navy, padding: '0 18px 14px', flexShrink: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button onClick={() => setShowMedia(false)} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
              <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Shared Media</span>
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }} className="scrollbar-hide">
            {mediaError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 10 }}>{mediaError}</div>}
            {mediaLoading ? (
              <div style={{ padding: '20px 0', textAlign: 'center', color: '#9CA3AF', fontSize: 13, fontFamily: 'Plus Jakarta Sans' }}>Loading…</div>
            ) : mediaItems.length === 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 20px', textAlign: 'center' }}>
                <div style={{ fontSize: 44, marginBottom: 12 }}>🖼️</div>
                <div style={{ fontWeight: 700, fontSize: 16, color: N.navy }}>Nothing shared yet</div>
                <div style={{ fontSize: 13, color: '#6B7280', marginTop: 4 }}>Files and images sent in this chat will show up here</div>
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8 }}>
                {mediaItems.map(item => (
                  <a key={item.id} href={item.view_url || undefined} target="_blank" rel="noreferrer" style={{ textDecoration: 'none' }}>
                    {IMAGE_FILE_TYPES.includes(item.file_type) ? (
                      <div style={{ aspectRatio: '1', borderRadius: 10, overflow: 'hidden', background: '#F3F4F6' }}>
                        <img src={item.view_url || undefined} alt={item.original_filename} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
                      </div>
                    ) : (
                      <div style={{ aspectRatio: '1', borderRadius: 10, background: '#F3F4F6', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4, padding: 8 }}>
                        <div style={{ fontSize: 22 }}>📎</div>
                        <div style={{ fontSize: 9, color: '#6B7280', textAlign: 'center', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', width: '100%' }}>{item.original_filename}</div>
                      </div>
                    )}
                  </a>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── EDIT PROFILE ─────────────────────────────────────────────────────────────
type EditProfileMe = { display_name: string | null; bio: string | null; year: number | null; semester: number | null; university_id: number | null; program_id: number | null; csrf_token: string }

function EditProfileScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [csrfToken, setCsrfToken] = useState('')
  const [loadingMe, setLoadingMe] = useState(true)
  const [loadError, setLoadError] = useState('')

  const [form, setForm] = useState({
    display_name: '', bio: '',
    university_id: null as number | null, program_id: null as number | null,
    year: null as number | null, semester: null as number | null,
  })

  const [universities, setUniversities] = useState<UniversityOption[]>([])
  const [programs, setPrograms] = useState<ProgramOption[]>([])

  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api<EditProfileMe>('/me')
      .then(me => {
        setCsrfToken(me.csrf_token)
        setForm({
          display_name: me.display_name || '',
          bio: me.bio || '',
          university_id: me.university_id,
          program_id: me.program_id,
          year: me.year,
          semester: me.semester,
        })
      })
      .catch(() => setLoadError('Could not load your profile. Check your connection and try again.'))
      .finally(() => setLoadingMe(false))
  }, [])

  useEffect(() => {
    api<UniversityOption[]>('/universities').then(setUniversities).catch(() => {})
  }, [])

  useEffect(() => {
    if (form.university_id == null) { setPrograms([]); return }
    api<ProgramOption[]>(`/universities/${form.university_id}/programs`).then(setPrograms).catch(() => {})
  }, [form.university_id])

  const handleSave = async () => {
    setSaving(true)
    setSaveError('')
    try {
      await api('/profile', {
        method: 'PATCH',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({
          display_name: form.display_name.trim() || null,
          bio: form.bio.trim() || null,
          university_id: form.university_id,
          program_id: form.program_id,
          year: form.year,
          semester: form.semester,
        }),
      })
      setSaved(true)
      setTimeout(() => setScreen('profile'), 1000)
    } catch (e) {
      setSaveError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const inputStyle = { width: '100%', border: '1px solid rgba(0,0,0,0.1)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, boxSizing: 'border-box' as const }
  const initials = (form.display_name || 'ST').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()

  if (loadingMe) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: N.bg }}>
        <div style={{ color: '#9CA3AF', fontSize: 14 }}>Loading your profile...</div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Edit Profile</span>
          <button onClick={handleSave} disabled={saving} style={{ background: saved ? '#4CC97B' : `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 12, padding: '8px 16px', cursor: saving ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 13, color: saved ? '#fff' : N.navy, opacity: saving ? 0.7 : 1 }}>{saved ? '✓ Saved' : saving ? 'Saving...' : 'Save'}</button>
        </div>
      </div>
      {loadError && <div style={{ margin: '14px 20px 0', color: '#C94C4C', fontSize: 12, fontWeight: 600 }}>{loadError}</div>}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '24px 20px 12px' }}>
        <div style={{ position: 'relative', marginBottom: 20 }}>
          <div style={{ width: 80, height: 80, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 28, color: N.navy }}>{initials}</div>
          <div style={{ position: 'absolute', bottom: 0, right: 0, width: 26, height: 26, background: N.gold, borderRadius: '50%', border: '2px solid #fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: N.navy }}>{Ic.edit('w-3 h-3')}</div>
          </div>
        </div>
        <div style={{ fontSize: 12, color: '#9CA3AF' }}>Change photo (coming soon)</div>
      </div>
      <div style={{ padding: '0 20px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>Full Name</div>
          <input value={form.display_name} onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))} maxLength={50} style={inputStyle} />
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>Bio</div>
          <textarea value={form.bio} onChange={e => setForm(f => ({ ...f, bio: e.target.value }))} rows={3} maxLength={160} style={{ ...inputStyle, resize: 'none', lineHeight: 1.6 }} />
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>University</div>
          <select value={form.university_id ?? ''} onChange={e => setForm(f => ({ ...f, university_id: e.target.value ? Number(e.target.value) : null, program_id: null }))} style={inputStyle}>
            <option value="">Select university</option>
            {universities.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>Course</div>
          <select value={form.program_id ?? ''} onChange={e => setForm(f => ({ ...f, program_id: e.target.value ? Number(e.target.value) : null }))} disabled={!form.university_id} style={{ ...inputStyle, opacity: form.university_id ? 1 : 0.5 }}>
            <option value="">Select course</option>
            {programs.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>Year</div>
            <select value={form.year ?? ''} onChange={e => setForm(f => ({ ...f, year: e.target.value ? Number(e.target.value) : null }))} style={inputStyle}>
              <option value="">—</option>
              {[1, 2, 3, 4].map(y => <option key={y} value={y}>Year {y}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>Semester</div>
            <select value={form.semester ?? ''} onChange={e => setForm(f => ({ ...f, semester: e.target.value ? Number(e.target.value) : null }))} style={inputStyle}>
              <option value="">—</option>
              {[1, 2].map(s => <option key={s} value={s}>Semester {s}</option>)}
            </select>
          </div>
        </div>
        {saveError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600 }}>{saveError}</div>}
        <button onClick={handleSave} disabled={saving} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '14px 0', cursor: saving ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: saving ? 0.7 : 1 }}>{saving ? 'Saving...' : 'Save Changes'}</button>
      </div>
    </div>
  )
}

// ─── PUBLISH TO LIBRARY ───────────────────────────────────────────────────────

type PublishableDoc = { id: number; title: string; file_type: string | null; page_count: number | null }
type PublishUnit = { id: number; code: string; name: string }

const LIBRARY_MATERIAL_TYPES: { value: string; label: string }[] = [
  { value: 'lecture_notes', label: 'Lecture Notes' },
  { value: 'past_paper', label: 'Past Paper' },
  { value: 'summary', label: 'Summary' },
  { value: 'other', label: 'Other' },
]
const materialTypeLabel = (v: string) => LIBRARY_MATERIAL_TYPES.find(t => t.value === v)?.label ?? v

function PublishLibraryScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [step, setStep] = useState(1)

  const [csrfToken, setCsrfToken] = useState('')
  const [docs, setDocs] = useState<PublishableDoc[]>([])
  const [docsLoading, setDocsLoading] = useState(true)
  const [docsError, setDocsError] = useState('')

  const [units, setUnits] = useState<PublishUnit[]>([])
  const [unitsLoading, setUnitsLoading] = useState(true)

  const [selectedDocId, setSelectedDocId] = useState<number | null>(null)
  const [title, setTitle] = useState('')
  const [matType, setMatType] = useState(LIBRARY_MATERIAL_TYPES[0].value)
  const [unitId, setUnitId] = useState<number | null>(null)
  const [desc, setDesc] = useState('')
  const [rightsChecked, setRightsChecked] = useState(false)

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [submittedStatus, setSubmittedStatus] = useState<string | null>(null)

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
    api<{ documents: { id: number; title: string; status: string; file_type: string | null; page_count: number | null }[] }>('/documents')
      .then(res => setDocs(res.documents.filter(d => d.status === 'ready')))
      .catch(() => setDocsError('Could not load your documents - check your connection and try again.'))
      .finally(() => setDocsLoading(false))
    api<PublishUnit[]>('/units')
      .then(setUnits)
      .catch(() => {})
      .finally(() => setUnitsLoading(false))
  }, [])

  const canProceed1 = selectedDocId != null && title.trim().length > 0
  const canProceed2 = true
  const canProceed3 = rightsChecked

  const submit = async () => {
    if (selectedDocId == null) return
    setSubmitting(true)
    setSubmitError('')
    setStep(4)
    try {
      const result = await api<{ publication_id: number; status: string }>('/library/publish', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({
          document_id: selectedDocId,
          title: title.trim(),
          description: desc.trim() || undefined,
          material_type: matType,
          unit_id: unitId ?? undefined,
        }),
      })
      setSubmittedStatus(result.status)
      setStep(5)
    } catch (e) {
      setSubmitError(e instanceof ApiError ? e.message : 'Something went wrong submitting your material. Please try again.')
      setStep(3)
    } finally {
      setSubmitting(false)
    }
  }

  const stepLabel = ['Select Document', 'Add Details', 'Confirm Rights', '', ''][step - 1]

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      {/* Header */}
      <div style={{ background: N.navy, padding: '0 18px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: step <= 3 ? 14 : 0 }}>
          <button onClick={() => step > 1 && step <= 3 ? setStep(s => s - 1) : setScreen('create-modal')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 17, color: '#fff' }}>Publish to Prepza Library</div>
            {step <= 3 && <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>Step {step} of 3 — {stepLabel}</div>}
          </div>
        </div>
        {step <= 3 && (
          <div style={{ display: 'flex', gap: 4 }}>
            {[1, 2, 3].map(s => (
              <div key={s} style={{ flex: 1, height: 3, borderRadius: 99, background: s <= step ? N.gold : 'rgba(255,255,255,0.15)', transition: 'background 0.3s' }} />
            ))}
          </div>
        )}
      </div>

      {/* Step 1: Select doc + title */}
      {step === 1 && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
          <div style={{ background: `${N.gold}10`, border: `1px solid ${N.gold}30`, borderRadius: 14, padding: '12px 16px', marginBottom: 20 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: N.gold, marginBottom: 4 }}>Free to publish · Earn XP on approval</div>
            <div style={{ fontSize: 12, color: '#6B7280', lineHeight: 1.6 }}>Share educational materials with students across Kenya. Approved contributions earn XP and build your contributor reputation.</div>
          </div>
          <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 10 }}>Select a document</div>
          {docsLoading ? (
            <div style={{ fontSize: 12, color: '#9CA3AF', padding: '12px 0' }}>Loading your documents…</div>
          ) : docsError ? (
            <div style={{ fontSize: 12, color: '#C94C4C', fontWeight: 600, padding: '12px 0' }}>{docsError}</div>
          ) : docs.length === 0 ? (
            <EmptyState icon="📄" title="No ready documents" sub="Upload and finish processing a document before publishing it to the library." action="Upload Document" onAction={() => setScreen('upload')} />
          ) : docs.map(d => (
            <div key={d.id} onClick={() => { setSelectedDocId(d.id); setTitle(d.title) }}
              style={{ background: '#fff', borderRadius: 14, padding: '14px 16px', marginBottom: 10, border: `2px solid ${selectedDocId === d.id ? N.gold : 'rgba(0,0,0,0.06)'}`, cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'center', boxShadow: selectedDocId === d.id ? `0 4px 16px ${N.gold}20` : '0 2px 8px rgba(0,0,0,0.04)', transition: 'all 0.2s' }}>
              <div style={{ width: 40, height: 44, background: '#F3F4F6', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <svg width="20" height="24" viewBox="0 0 20 24" fill="none"><path d="M4 0h8l8 8v16H4V0z" fill="#E5E7EB"/><path d="M12 0l8 8h-8V0z" fill="#D1D5DB"/><rect x="6" y="12" width="8" height="1.5" rx="0.75" fill="#9CA3AF"/><rect x="6" y="15" width="6" height="1.5" rx="0.75" fill="#9CA3AF"/><rect x="6" y="18" width="7" height="1.5" rx="0.75" fill="#9CA3AF"/></svg>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: N.navy, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.title}</div>
                <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 2 }}>{(d.file_type || '').toUpperCase()}{d.page_count != null ? ` · ${d.page_count} pages` : ''}</div>
              </div>
              {selectedDocId === d.id && <div style={{ color: N.gold, flexShrink: 0 }}>{Ic.check('w-5 h-5')}</div>}
            </div>
          ))}
          <div style={{ marginTop: 8, marginBottom: 20 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 8 }}>Publication title</div>
            <input value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. ACT 101 Lecture Notes – Semester 1" maxLength={200} style={{ width: '100%', border: '1.5px solid rgba(0,0,0,0.12)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, boxSizing: 'border-box' }} />
            <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 6 }}>This will be the public title visible to other students.</div>
          </div>
          <button onClick={() => canProceed1 && setStep(2)} style={{ width: '100%', background: canProceed1 ? `linear-gradient(135deg,${N.gold},${N.goldL})` : '#E5E7EB', color: canProceed1 ? N.navy : '#9CA3AF', fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: canProceed1 ? 'pointer' : 'not-allowed', fontFamily: 'Plus Jakarta Sans' }}>
            Continue
          </button>
        </div>
      )}

      {/* Step 2: Details */}
      {step === 2 && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 8 }}>Material Type</div>
            <select value={matType} onChange={e => setMatType(e.target.value)} style={{ width: '100%', border: '1.5px solid rgba(0,0,0,0.12)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, background: '#fff', appearance: 'none' }}>
              {LIBRARY_MATERIAL_TYPES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 8 }}>Unit / Module <span style={{ color: '#9CA3AF', fontWeight: 500 }}>(optional)</span></div>
            <select value={unitId ?? ''} onChange={e => setUnitId(e.target.value ? Number(e.target.value) : null)} disabled={unitsLoading} style={{ width: '100%', border: '1.5px solid rgba(0,0,0,0.12)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, background: '#fff', appearance: 'none' }}>
              <option value="">{unitsLoading ? 'Loading units…' : 'No specific unit'}</option>
              {units.map(u => <option key={u.id} value={u.id}>{u.code} — {u.name}</option>)}
            </select>
          </div>
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 8 }}>Description <span style={{ color: '#9CA3AF', fontWeight: 500 }}>(optional)</span></div>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={3} maxLength={1000} placeholder="What does this material cover? Who is it useful for?" style={{ width: '100%', border: '1.5px solid rgba(0,0,0,0.12)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, resize: 'none', lineHeight: 1.6, boxSizing: 'border-box' }} />
          </div>
          <button onClick={() => canProceed2 && setStep(3)} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
            Continue
          </button>
        </div>
      )}

      {/* Step 3: Rights confirmation */}
      {step === 3 && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
          <div style={{ background: '#fff', borderRadius: 16, padding: '18px 18px', marginBottom: 16, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
            <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 12 }}>Publishing: {title}</div>
            {[['Type', materialTypeLabel(matType)], ['Unit', units.find(u => u.id === unitId)?.code ?? 'Not specified']].map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #F3F4F6' }}>
                <span style={{ fontSize: 12, color: '#9CA3AF' }}>{k}</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: N.navy, maxWidth: 180, textAlign: 'right' }}>{v}</span>
              </div>
            ))}
          </div>
          <div style={{ background: '#FEF9F0', border: '1px solid rgba(201,168,76,0.25)', borderRadius: 14, padding: '16px 16px', marginBottom: 20 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: '#92400E', marginBottom: 8 }}>Content responsibility</div>
            <div style={{ fontSize: 12, color: '#6B7280', lineHeight: 1.75 }}>
              You are responsible for ensuring you have the right or permission to share this material. Prepza does not claim ownership of student-uploaded content. Unauthorised sharing of copyrighted materials may result in removal of the content and restrictions on your account.
            </div>
          </div>
          {submitError && (
            <div style={{ background: 'rgba(201,68,68,0.08)', border: '1px solid rgba(201,68,68,0.25)', borderRadius: 12, padding: '12px 14px', color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 16 }}>{submitError}</div>
          )}
          <div onClick={() => setRightsChecked(r => !r)} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', padding: '14px 16px', background: '#fff', borderRadius: 14, border: `2px solid ${rightsChecked ? N.gold : 'rgba(0,0,0,0.08)'}`, cursor: 'pointer', marginBottom: 16, transition: 'border-color 0.2s' }}>
            <div style={{ width: 22, height: 22, borderRadius: 6, border: `2px solid ${rightsChecked ? N.gold : '#D1D5DB'}`, background: rightsChecked ? N.gold : '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, transition: 'all 0.2s' }}>
              {rightsChecked && <div style={{ color: N.navy }}>{Ic.check('w-3 h-3')}</div>}
            </div>
            <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.6 }}>I confirm that I have the right or permission to share this material, and I agree to Prepza's <span style={{ color: N.gold, fontWeight: 700 }}>Terms of Service</span>, <span style={{ color: N.gold, fontWeight: 700 }}>Content Policy</span>, and <span style={{ color: N.gold, fontWeight: 700 }}>Copyright Policy</span>.</div>
          </div>
          <button onClick={() => canProceed3 && !submitting && submit()} style={{ width: '100%', background: canProceed3 ? `linear-gradient(135deg,${N.gold},${N.goldL})` : '#E5E7EB', color: canProceed3 ? N.navy : '#9CA3AF', fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: canProceed3 ? 'pointer' : 'not-allowed', fontFamily: 'Plus Jakarta Sans', boxShadow: canProceed3 ? `0 6px 24px ${N.gold}40` : 'none' }}>
            Submit for Review
          </button>
          <button onClick={() => setScreen('home')} style={{ width: '100%', background: 'transparent', color: '#9CA3AF', fontSize: 12, fontWeight: 600, border: 'none', padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Cancel — don't publish</button>
        </div>
      )}

      {/* Step 4: Submitting */}
      {step === 4 && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 20, padding: '0 32px', textAlign: 'center' }}>
          <div style={{ width: 72, height: 72, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ width: 28, height: 28, border: '3px solid rgba(11,20,55,0.4)', borderTopColor: N.navy, borderRadius: '50%', animation: 'spin-slow 0.7s linear infinite' }} />
          </div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 18, color: N.navy, marginBottom: 6 }}>Submitting…</div>
            <div style={{ fontSize: 13, color: '#9CA3AF' }}>Uploading to Prepza Library</div>
          </div>
        </div>
      )}

      {/* Step 5: Submitted for review */}
      {step === 5 && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px 20px' }} className="scrollbar-hide">
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <div style={{ width: 72, height: 72, background: 'rgba(76,201,123,0.1)', borderRadius: '50%', border: '3px solid #4CC97B', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px', fontSize: 28 }}>📥</div>
            <div style={{ fontWeight: 800, fontSize: 20, color: N.navy, marginBottom: 8 }}>Submitted for Review</div>
            <div style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.65 }}>Your material has been received and is {submittedStatus || 'pending'}. Our team reviews every submission to maintain quality standards — this usually takes 24-48h. You'll be notified of the outcome.</div>
          </div>

          <div style={{ background: '#fff', borderRadius: 14, padding: '14px 16px', marginBottom: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: N.navy, marginBottom: 4 }}>What happens if rejected?</div>
            <div style={{ fontSize: 12, color: '#6B7280', lineHeight: 1.65 }}>You'll receive a notification with the reason. You can revise and resubmit, or contact support if you believe it's a mistake.</div>
          </div>

          <button onClick={() => setScreen('library')} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: `0 6px 24px ${N.gold}40` }}>
            Go to My Library
          </button>
          <button onClick={() => setScreen('home')} style={{ width: '100%', background: 'transparent', color: '#9CA3AF', fontSize: 12, fontWeight: 600, border: 'none', padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Back to Home</button>
        </div>
      )}
    </div>
  )
}



// ─── XP PROGRESS ──────────────────────────────────────────────────────────────
type XpHistoryItem = { icon: string; label: string; xp: number; created_at: string | null }
type HowToEarnItem = { label: string; xp: string }
type XpProgressResponse = {
  level: number
  level_title: string
  xp_total: number
  xp_into_level: number
  xp_for_level_gap: number
  next_level_xp: number
  page: number
  history: XpHistoryItem[]
  how_to_earn: HowToEarnItem[]
}

function formatXpDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const startOfDay = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate())
  const diffDays = Math.round((startOfDay(now).getTime() - startOfDay(d).getTime()) / 86400000)
  if (diffDays <= 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  return `${diffDays} days ago`
}

function XPProgressScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<XpProgressResponse | null>(null)
  const [history, setHistory] = useState<XpHistoryItem[]>([])
  const [page, setPage] = useState(1)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    api<XpProgressResponse>('/xp/progress?page=1')
      .then(res => {
        if (cancelled) return
        setData(res)
        setHistory(res.history)
        setPage(1)
        setHasMore(res.history.length >= 20)
      })
      .catch(err => { if (!cancelled) setError(err instanceof ApiError ? err.message : 'Failed to load XP progress') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const loadMore = () => {
    if (loadingMore || !hasMore) return
    const nextPage = page + 1
    setLoadingMore(true)
    api<XpProgressResponse>(`/xp/progress?page=${nextPage}`)
      .then(res => {
        setHistory(prev => [...prev, ...res.history])
        setPage(nextPage)
        setHasMore(res.history.length >= 20)
      })
      .catch(() => { /* keep existing history on failure */ })
      .finally(() => setLoadingMore(false))
  }

  const xpTotal = data?.xp_total ?? 0
  const level = data?.level ?? 1
  const levelTitle = data?.level_title ?? 'Scholar'
  const xpIntoLevel = data?.xp_into_level ?? 0
  const xpForLevelGap = data?.xp_for_level_gap ?? 1
  const nextLevelXp = data?.next_level_xp ?? 0
  const pct = xpForLevelGap > 0 ? (xpIntoLevel / xpForLevelGap) * 100 : 0
  const howToEarn = data?.how_to_earn ?? []

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
        <div style={{ background: N.navy, padding: '0 18px 24px', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>XP & Progress</div>
          </div>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: '#9CA3AF' }}>Loading…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
        <div style={{ background: N.navy, padding: '0 18px 24px', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>XP & Progress</div>
          </div>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: '#EF4444', padding: '0 24px', textAlign: 'center' }}>{error}</div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 24px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>XP & Progress</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <div style={{ position: 'relative', width: 80, height: 80, flexShrink: 0 }}>
            <svg width="80" height="80" viewBox="0 0 80 80">
              <circle cx="40" cy="40" r="34" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="8" />
              <circle cx="40" cy="40" r="34" fill="none" stroke={N.gold} strokeWidth="8" strokeLinecap="round"
                strokeDasharray={`${2 * Math.PI * 34 * pct / 100} ${2 * Math.PI * 34}`} strokeDashoffset={2 * Math.PI * 34 * 0.25} />
            </svg>
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ fontWeight: 800, fontSize: 18, color: '#fff', lineHeight: 1 }}>{level}</div>
              <div style={{ fontSize: 9, color: N.gold, fontWeight: 700, letterSpacing: 0.5 }}>LEVEL</div>
            </div>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 20, color: '#fff', marginBottom: 2 }}>{levelTitle}</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)', marginBottom: 10 }}>{xpTotal.toLocaleString()} XP · {xpForLevelGap - xpIntoLevel} XP to Level {level + 1}</div>
            <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 99, height: 6, overflow: 'hidden' }}>
              <div style={{ background: `linear-gradient(90deg,${N.gold},${N.goldL})`, height: 6, width: `${pct}%`, borderRadius: 99, transition: 'width 1s ease' }} />
            </div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginTop: 4 }}>{xpForLevelGap - xpIntoLevel} XP to next level (Level {level + 1} at {nextLevelXp.toLocaleString()} XP total)</div>
          </div>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 18px' }} className="scrollbar-hide">
        <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 12 }}>Recent XP activity</div>
        {history.length === 0 && (
          <div style={{ fontSize: 13, color: '#9CA3AF', padding: '12px 0 20px' }}>No XP activity yet — study a document or complete a quiz to start earning.</div>
        )}
        {history.map((h, i) => (
          <div key={i} style={{ background: '#fff', borderRadius: 14, padding: '12px 16px', marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
            <div style={{ width: 38, height: 38, background: `${N.gold}15`, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, flexShrink: 0 }}>{h.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: N.navy }}>{h.label}</div>
              <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 2 }}>{formatXpDate(h.created_at)}</div>
            </div>
            <div style={{ fontWeight: 800, fontSize: 14, color: '#16A34A' }}>+{h.xp}</div>
          </div>
        ))}
        {hasMore && history.length > 0 && (
          <button onClick={loadMore} disabled={loadingMore} style={{ width: '100%', background: 'none', border: 'none', color: N.gold, fontWeight: 700, fontSize: 12, padding: '10px 0 4px', cursor: loadingMore ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
            {loadingMore ? 'Loading…' : 'Load more'}
          </button>
        )}
        <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, margin: '20px 0 12px' }}>How to earn XP</div>
        <div style={{ background: '#fff', borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
          {howToEarn.map((h, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: i < howToEarn.length - 1 ? '1px solid #F3F4F6' : 'none' }}>
              <span style={{ fontSize: 13, color: '#374151' }}>{h.label}</span>
              <Pill text={h.xp} color={N.gold} />
            </div>
          ))}
        </div>
        <div style={{ height: 20 }} />
      </div>
    </div>
  )
}

// ─── STUDY STREAK ─────────────────────────────────────────────────────────────
type StreakCalendarDay = { date: string; studied: boolean }
type StreakMilestone = { days: number; label: string; xp: string; done: boolean }
type StreakResponse = {
  current_streak: number
  longest_streak: number
  calendar: StreakCalendarDay[]
  milestones: StreakMilestone[]
}

function StudyStreakScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<StreakResponse | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    api<StreakResponse>('/streak')
      .then(res => { if (!cancelled) setData(res) })
      .catch(err => { if (!cancelled) setError(err instanceof ApiError ? err.message : 'Failed to load streak') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const current = data?.current_streak ?? 0
  const longest = data?.longest_streak ?? 0
  const days = data?.calendar ?? []
  const milestones = data?.milestones ?? []

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
        <div style={{ background: N.navy, padding: '0 18px 24px', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Study Streak</div>
          </div>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: '#9CA3AF' }}>Loading…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
        <div style={{ background: N.navy, padding: '0 18px 24px', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Study Streak</div>
          </div>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: '#EF4444', padding: '0 24px', textAlign: 'center' }}>{error}</div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 24px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Study Streak</div>
        </div>
        <div style={{ display: 'flex', gap: 14 }}>
          <div style={{ flex: 1, background: 'rgba(255,255,255,0.08)', borderRadius: 14, padding: '14px 16px' }}>
            <div style={{ fontSize: 38, fontWeight: 800, color: N.gold, lineHeight: 1 }}>{current}</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)', marginTop: 4 }}>day streak 🔥</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginTop: 2 }}>Current</div>
          </div>
          <div style={{ flex: 1, background: 'rgba(255,255,255,0.08)', borderRadius: 14, padding: '14px 16px' }}>
            <div style={{ fontSize: 38, fontWeight: 800, color: 'rgba(255,255,255,0.9)', lineHeight: 1 }}>{longest}</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)', marginTop: 4 }}>days</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginTop: 2 }}>Personal best</div>
          </div>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
        <div style={{ background: '#fff', borderRadius: 16, padding: '16px 16px', marginBottom: 16, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 14 }}>Last 42 days</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 5 }}>
            {['S','M','T','W','T','F','S'].map((d, i) => <div key={i} style={{ textAlign: 'center', fontSize: 10, color: '#9CA3AF', fontWeight: 600, marginBottom: 4 }}>{d}</div>)}
            {days.map((d, i) => (
              <div key={i} style={{ aspectRatio: '1', borderRadius: 6, background: d.studied ? N.gold : '#F3F4F6', transition: 'background 0.2s' }} title={new Date(d.date).toLocaleDateString()} />
            ))}
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 14, alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}><div style={{ width: 12, height: 12, borderRadius: 3, background: N.gold }} /><span style={{ fontSize: 11, color: '#9CA3AF' }}>Studied</span></div>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}><div style={{ width: 12, height: 12, borderRadius: 3, background: '#F3F4F6', border: '1px solid #E5E7EB' }} /><span style={{ fontSize: 11, color: '#9CA3AF' }}>No activity</span></div>
          </div>
        </div>
        <div style={{ background: '#fff', borderRadius: 16, padding: '14px 16px', marginBottom: 16, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 12 }}>Streak milestones</div>
          {milestones.map((m, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: i < milestones.length - 1 ? 12 : 0 }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: m.done ? `${N.gold}20` : '#F3F4F6', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                {m.done ? <span style={{ fontSize: 16 }}>🏆</span> : <span style={{ fontSize: 16, opacity: 0.4 }}>🔒</span>}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: m.done ? N.navy : '#9CA3AF' }}>{m.days}-Day Streak</div>
                <div style={{ fontSize: 11, color: '#9CA3AF' }}>{m.label}</div>
              </div>
              <Pill text={m.xp} color={m.done ? N.gold : '#9CA3AF'} />
            </div>
          ))}
        </div>
        <button onClick={() => setScreen('share-sheet')} style={{ width: '100%', background: 'transparent', border: `1.5px solid ${N.gold}`, color: N.gold, fontWeight: 700, fontSize: 14, borderRadius: 16, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
          Share {current}-Day Streak
        </button>
        <div style={{ height: 20 }} />
      </div>
    </div>
  )
}

// ─── ACHIEVEMENTS ─────────────────────────────────────────────────────────────
type Achievement = {
  code: string
  icon: string
  name: string
  desc: string
  done: boolean
  unlocked_at: string | null
  progress: number
  total: number
}
type AchievementsResponse = { unlocked_count: number; total_count: number; achievements: Achievement[] }

function formatAchievementDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function AchievementsScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [sharing, setSharing] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [achievementsList, setAchievementsList] = useState<Achievement[]>([])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    api<AchievementsResponse>('/achievements')
      .then(res => { if (!cancelled) setAchievementsList(res.achievements) })
      .catch(err => { if (!cancelled) setError(err instanceof ApiError ? err.message : 'Failed to load achievements') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const unlocked = achievementsList.filter(a => a.done)
  const locked = achievementsList.filter(a => !a.done)

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
        <div style={{ background: N.navy, padding: '0 18px 16px', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Achievements</div>
          </div>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: '#9CA3AF' }}>Loading…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
        <div style={{ background: N.navy, padding: '0 18px 16px', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Achievements</div>
          </div>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, color: '#EF4444', padding: '0 24px', textAlign: 'center' }}>{error}</div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      {sharing && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 200, display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
          <div style={{ width: 390, background: '#fff', borderRadius: '24px 24px 0 0', padding: '24px 20px 32px' }}>
            <div style={{ width: 40, height: 4, background: '#E5E7EB', borderRadius: 99, margin: '0 auto 20px' }} />
            {(() => { const a = achievementsList.find(x => x.code === sharing)!; return (
              <div>
                <div style={{ background: N.navy, borderRadius: 16, padding: '20px', marginBottom: 16, textAlign: 'center' }}>
                  <div style={{ fontSize: 40, marginBottom: 10 }}>{a.icon}</div>
                  <div style={{ fontWeight: 800, fontSize: 16, color: '#fff', marginBottom: 4 }}>Achievement Unlocked</div>
                  <div style={{ fontWeight: 700, fontSize: 20, color: N.gold, marginBottom: 8 }}>{a.name}</div>
                  <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>{a.desc}</div>
                  <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid rgba(255,255,255,0.1)', fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>Join me on Prepza · prepza.app</div>
                </div>
                <div style={{ display: 'flex', gap: 10 }}>
                  <button onClick={() => setScreen('share-sheet')} style={{ flex: 1, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Share</button>
                  <button onClick={() => setSharing(null)} style={{ flex: 1, background: '#F3F4F6', color: '#374151', fontWeight: 700, fontSize: 14, border: 'none', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Close</button>
                </div>
              </div>
            ) })()}
          </div>
        </div>
      )}
      <div style={{ background: N.navy, padding: '0 18px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Achievements</div>
          <div style={{ marginLeft: 'auto' }}><Pill text={`${unlocked.length} of ${achievementsList.length}`} color={N.gold} /></div>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 18px' }} className="scrollbar-hide">
        <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 12 }}>Unlocked ({unlocked.length})</div>
        {unlocked.map(a => (
          <div key={a.code} style={{ background: '#fff', borderRadius: 16, padding: '14px 16px', marginBottom: 10, border: `1.5px solid ${N.gold}30`, boxShadow: `0 4px 16px ${N.gold}10`, display: 'flex', gap: 12, alignItems: 'center' }}>
            <div style={{ width: 48, height: 48, background: `${N.gold}15`, borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, flexShrink: 0 }}>{a.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 14, color: N.navy }}>{a.name}</div>
              <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>{a.desc}</div>
              <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 4 }}>Achieved {formatAchievementDate(a.unlocked_at)}</div>
            </div>
            <button onClick={() => setSharing(a.code)} style={{ background: '#F3F4F6', border: 'none', borderRadius: 8, padding: '6px 12px', cursor: 'pointer', fontSize: 12, fontWeight: 600, color: '#374151', fontFamily: 'Plus Jakarta Sans', flexShrink: 0 }}>Share</button>
          </div>
        ))}
        <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, margin: '20px 0 12px' }}>In progress ({locked.length})</div>
        {locked.map(a => (
          <div key={a.code} style={{ background: '#fff', borderRadius: 16, padding: '14px 16px', marginBottom: 10, opacity: 0.7, boxShadow: '0 2px 6px rgba(0,0,0,0.04)', display: 'flex', gap: 12, alignItems: 'center' }}>
            <div style={{ width: 48, height: 48, background: '#F3F4F6', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, flexShrink: 0, filter: 'grayscale(1)', opacity: 0.5 }}>{a.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 14, color: '#6B7280' }}>{a.name}</div>
              <div style={{ fontSize: 12, color: '#9CA3AF', marginTop: 2 }}>{a.desc}</div>
              <div style={{ background: '#F3F4F6', borderRadius: 99, height: 5, marginTop: 8, overflow: 'hidden' }}>
                <div style={{ background: '#D1D5DB', height: 5, width: `${a.total > 0 ? (a.progress / a.total) * 100 : 0}%`, borderRadius: 99 }} />
              </div>
              <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 4 }}>{a.progress} / {a.total}</div>
            </div>
          </div>
        ))}
        <div style={{ height: 20 }} />
      </div>
    </div>
  )
}

// ─── FOLLOWERS / FOLLOWING ────────────────────────────────────────────────────
const followPeople = [
  { name: 'Wanjiru Kamau', username: '@wanjiru.ku', uni: 'UoN', course: 'Computer Science', following: false },
  { name: 'Brian Omondi', username: '@brian.str', uni: 'Strathmore', course: 'B.Com Finance', following: true },
  { name: 'Aisha Mohamed', username: '@aisha.mku', uni: 'MKU', course: 'LLB Law', following: false },
  { name: 'David Njoroge', username: '@david.ku', uni: 'Kenyatta University', course: 'MBBS Medicine', following: true },
  { name: 'Faith Njeri', username: '@faith.daystar', uni: 'Daystar University', course: 'BA Psychology', following: false },
  { name: 'James Kariuki', username: '@james.uon', uni: 'UoN', course: 'BSc Economics', following: false },
]

function FollowListScreen({ mode, setScreen, targetUserId, setActiveProfileUserId, setActiveProfileName }: {
  mode: 'followers' | 'following'
  setScreen: (s: Screen) => void
  targetUserId: number | null
  setActiveProfileUserId?: (id: number) => void
  setActiveProfileName?: (name: string) => void
}) {
  const [search, setSearch] = useState('')
  const [people, setPeople] = useState<FollowListUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<Record<number, boolean>>({})
  const [csrfToken, setCsrfToken] = useState('')

  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  useEffect(() => {
    if (targetUserId == null) { setLoading(false); setError('No student selected.'); return }
    setLoading(true)
    setError('')
    const key = mode // 'followers' | 'following'
    api<{ page: number; followers?: FollowListUser[]; following?: FollowListUser[] }>(`/users/${targetUserId}/${key}?page=1`)
      .then(res => setPeople((mode === 'followers' ? res.followers : res.following) || []))
      .catch(() => setError(`Could not load ${mode}.`))
      .finally(() => setLoading(false))
  }, [mode, targetUserId])

  const filtered = people.filter(p => !search || p.display_name.toLowerCase().includes(search.toLowerCase()))

  const toggle = async (person: FollowListUser) => {
    if (busy[person.user_id]) return
    setBusy(b => ({ ...b, [person.user_id]: true }))
    const wasFollowing = person.is_following
    try {
      wasFollowing
        ? await api(`/users/${person.user_id}/follow`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
        : await api(`/users/${person.user_id}/follow`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      setPeople(list => list.map(p => p.user_id === person.user_id ? { ...p, is_following: !wasFollowing } : p))
    } catch { /* leave state as-is on failure */ }
    setBusy(b => ({ ...b, [person.user_id]: false }))
  }

  const openProfile = (person: FollowListUser) => {
    setActiveProfileUserId?.(person.user_id)
    setActiveProfileName?.(person.display_name)
    setScreen('student-profile')
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>{mode === 'followers' ? 'Followers' : 'Following'}</div>
          <div style={{ marginLeft: 'auto' }}><Pill text={filtered.length.toString()} color={N.gold} /></div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, padding: '10px 14px' }}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="6" cy="6" r="5" stroke="rgba(255,255,255,0.4)" strokeWidth="1.5"/><path d="M10 10l2.5 2.5" stroke="rgba(255,255,255,0.4)" strokeWidth="1.5" strokeLinecap="round"/></svg>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search…" style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans' }} />
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 18px' }} className="scrollbar-hide">
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '30px 0' }}>
            <div style={{ width: 26, height: 26, border: '2.5px solid #E5E7EB', borderTopColor: N.gold, borderRadius: '50%', animation: 'spin-slow 0.7s linear infinite' }} />
          </div>
        ) : error ? (
          <div style={{ textAlign: 'center', padding: '30px 0', color: '#9CA3AF', fontSize: 13 }}>{error}</div>
        ) : filtered.length === 0 ? (
          <EmptyState icon="👥" title={mode === 'followers' ? 'No followers yet' : 'Not following anyone'} sub={mode === 'followers' ? "When students follow you, they'll appear here." : 'Discover students and follow them from their profiles.'} action="Explore Students" onAction={() => setScreen('explore')} />
        ) : filtered.map(p => {
          const isLoading = !!busy[p.user_id]
          return (
            <div key={p.user_id} style={{ background: '#fff', borderRadius: 14, padding: '14px 16px', marginBottom: 10, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
              <div onClick={() => openProfile(p)} style={{ width: 44, height: 44, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 16, color: N.navy, flexShrink: 0, cursor: 'pointer' }}>
                {p.display_name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
              </div>
              <div style={{ flex: 1, minWidth: 0, cursor: 'pointer' }} onClick={() => openProfile(p)}>
                <div style={{ fontWeight: 700, fontSize: 14, color: N.navy }}>{p.display_name}</div>
              </div>
              <button onClick={() => toggle(p)} disabled={isLoading} style={{ background: p.is_following ? '#F3F4F6' : `linear-gradient(135deg,${N.gold},${N.goldL})`, color: p.is_following ? '#374151' : N.navy, fontWeight: 700, fontSize: 12, border: 'none', borderRadius: 10, padding: '8px 14px', cursor: isLoading ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans', flexShrink: 0, opacity: isLoading ? 0.7 : 1, display: 'flex', alignItems: 'center', gap: 5, transition: 'all 0.2s' }}>
                {isLoading ? <div style={{ width: 10, height: 10, border: '1.5px solid currentColor', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin-slow 0.6s linear infinite' }} /> : null}
                {p.is_following ? 'Following' : 'Follow'}
              </button>
            </div>
          )
        })}
        <div style={{ height: 16 }} />
      </div>
    </div>
  )
}

// ─── GROUP DETAIL ─────────────────────────────────────────────────────────────
function GroupDetailScreen({ setScreen, groupId }: { setScreen: (s: Screen) => void; groupId: number | null }) {
  const [tab, setTab] = useState<'Posts' | 'Questions' | 'Files' | 'Members'>('Posts')
  const [group, setGroup] = useState<GroupSummary | null>(null)
  const [loadingGroup, setLoadingGroup] = useState(true)
  const [groupError, setGroupError] = useState('')
  const [joining, setJoining] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const [actionError, setActionError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')

  const [posts, setPosts] = useState<GroupPostData[]>([])
  const [loadingPosts, setLoadingPosts] = useState(false)
  const [postsError, setPostsError] = useState('')
  const [composeText, setComposeText] = useState('')
  const [composing, setComposing] = useState(false)

  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [expandedDetail, setExpandedDetail] = useState<GroupPostDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [commentInput, setCommentInput] = useState('')
  const [sendingComment, setSendingComment] = useState(false)

  const [members, setMembers] = useState<GroupMemberData[]>([])
  const [loadingMembers, setLoadingMembers] = useState(false)
  const [membersError, setMembersError] = useState('')

  const [files, setFiles] = useState<GroupFileData[]>([])
  const [loadingFiles, setLoadingFiles] = useState(false)
  const [filesError, setFilesError] = useState('')
  const [shareableDocs, setShareableDocs] = useState<MyDocumentSummary[]>([])
  const [showFilePicker, setShowFilePicker] = useState(false)
  const [sharing, setSharing] = useState(false)

  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  const loadGroup = () => {
    if (groupId == null) return
    setLoadingGroup(true); setGroupError('')
    api<GroupSummary>(`/groups/${groupId}`)
      .then(setGroup)
      .catch(() => setGroupError('Could not load this group.'))
      .finally(() => setLoadingGroup(false))
  }
  useEffect(loadGroup, [groupId])

  const postType = tab === 'Questions' ? 'question' : 'post'
  const loadPosts = () => {
    if (groupId == null || (tab !== 'Posts' && tab !== 'Questions')) return
    setLoadingPosts(true); setPostsError('')
    api<{ page: number; posts: GroupPostData[] }>(`/groups/${groupId}/posts?type=${postType}`)
      .then(res => setPosts(res.posts))
      .catch(() => setPostsError('Could not load this tab.'))
      .finally(() => setLoadingPosts(false))
  }
  useEffect(loadPosts, [groupId, tab])

  useEffect(() => {
    if (groupId == null || tab !== 'Members') return
    setLoadingMembers(true); setMembersError('')
    api<{ members: GroupMemberData[] }>(`/groups/${groupId}/members`)
      .then(res => setMembers(res.members))
      .catch(() => setMembersError('Could not load members.'))
      .finally(() => setLoadingMembers(false))
  }, [groupId, tab])

  const loadFiles = () => {
    if (groupId == null || tab !== 'Files') return
    setLoadingFiles(true); setFilesError('')
    api<{ files: GroupFileData[] }>(`/groups/${groupId}/files`)
      .then(res => setFiles(res.files))
      .catch(() => setFilesError('Could not load files.'))
      .finally(() => setLoadingFiles(false))
  }
  useEffect(loadFiles, [groupId, tab])

  const doJoin = async () => {
    if (groupId == null || joining) return
    setJoining(true); setActionError('')
    try {
      await api(`/groups/${groupId}/join`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      loadGroup()
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Could not join this group.')
    } finally { setJoining(false) }
  }

  const doLeave = async () => {
    if (groupId == null || leaving) return
    setLeaving(true); setActionError('')
    try {
      await api(`/groups/${groupId}/leave`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      loadGroup()
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Could not leave this group.')
    } finally { setLeaving(false) }
  }

  const submitPost = async () => {
    if (groupId == null || !composeText.trim() || composing) return
    setComposing(true); setPostsError('')
    try {
      await api(`/groups/${groupId}/posts`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ post_type: postType, body: composeText.trim() }),
      })
      setComposeText('')
      loadPosts()
    } catch (e) {
      setPostsError(e instanceof ApiError ? e.message : 'Could not post. Please try again.')
    } finally { setComposing(false) }
  }

  const toggleLike = async (p: GroupPostData) => {
    if (groupId == null) return
    const method = p.viewer_liked ? 'DELETE' : 'POST'
    try {
      const res = await api<{ like_count: number }>(`/groups/${groupId}/posts/${p.id}/like`, { method, headers: { 'X-CSRF-Token': csrfToken } })
      setPosts(ps => ps.map(x => x.id === p.id ? { ...x, viewer_liked: !p.viewer_liked, like_count: res.like_count } : x))
    } catch { /* transient failure - the button just won't visually update, safe to ignore */ }
  }

  const toggleVote = async (p: GroupPostData) => {
    if (groupId == null) return
    const method = p.viewer_voted ? 'DELETE' : 'POST'
    try {
      const res = await api<{ vote_count: number }>(`/groups/${groupId}/posts/${p.id}/vote`, { method, headers: { 'X-CSRF-Token': csrfToken } })
      setPosts(ps => ps.map(x => x.id === p.id ? { ...x, viewer_voted: !p.viewer_voted, vote_count: res.vote_count } : x))
    } catch { /* transient failure - safe to ignore, same reasoning as toggleLike */ }
  }

  const openPost = (p: GroupPostData) => {
    if (expandedId === p.id) { setExpandedId(null); setExpandedDetail(null); return }
    if (groupId == null) return
    setExpandedId(p.id); setLoadingDetail(true); setExpandedDetail(null)
    api<GroupPostDetail>(`/groups/${groupId}/posts/${p.id}`)
      .then(setExpandedDetail)
      .catch(() => setPostsError('Could not load that thread.'))
      .finally(() => setLoadingDetail(false))
  }

  const submitComment = async () => {
    if (groupId == null || expandedId == null || !commentInput.trim() || sendingComment) return
    setSendingComment(true)
    try {
      await api(`/groups/${groupId}/posts/${expandedId}/comments`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ body: commentInput.trim() }),
      })
      setCommentInput('')
      const detail = await api<GroupPostDetail>(`/groups/${groupId}/posts/${expandedId}`)
      setExpandedDetail(detail)
      setPosts(ps => ps.map(x => x.id === expandedId ? { ...x, comment_count: detail.comments.length } : x))
    } catch { /* best-effort; the comment box just stays populated so the user can retry */ }
    finally { setSendingComment(false) }
  }

  const markHelpful = async (commentId: number) => {
    if (groupId == null || expandedId == null) return
    try {
      await api(`/groups/${groupId}/posts/${expandedId}/comments/${commentId}/helpful`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      const detail = await api<GroupPostDetail>(`/groups/${groupId}/posts/${expandedId}`)
      setExpandedDetail(detail)
    } catch { /* best-effort */ }
  }

  const changeRole = async (userId: number, role: 'admin' | 'member') => {
    if (groupId == null) return
    try {
      await api(`/groups/${groupId}/members/${userId}`, { method: 'PATCH', headers: { 'X-CSRF-Token': csrfToken }, body: JSON.stringify({ role }) })
      setMembers(ms => ms.map(m => m.user_id === userId ? { ...m, role } : m))
    } catch (e) { setMembersError(e instanceof ApiError ? e.message : 'Could not update that member.') }
  }

  const removeMember = async (userId: number) => {
    if (groupId == null) return
    try {
      await api(`/groups/${groupId}/members/${userId}`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
      setMembers(ms => ms.filter(m => m.user_id !== userId))
      setGroup(g => g ? { ...g, member_count: Math.max(0, g.member_count - 1) } : g)
    } catch (e) { setMembersError(e instanceof ApiError ? e.message : 'Could not remove that member.') }
  }

  const openFilePicker = () => {
    setShowFilePicker(true)
    api<{ documents: MyDocumentSummary[] }>('/documents')
      .then(res => setShareableDocs(res.documents.filter(d => d.status === 'ready')))
      .catch(() => setShareableDocs([]))
  }

  const shareDoc = async (documentId: number) => {
    if (groupId == null || sharing) return
    setSharing(true)
    try {
      await api(`/groups/${groupId}/files`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken }, body: JSON.stringify({ document_id: documentId }) })
      setShowFilePicker(false)
      loadFiles()
    } catch (e) {
      setFilesError(e instanceof ApiError ? e.message : 'Could not share that file.')
    } finally { setSharing(false) }
  }

  const removeFile = async (fileId: number) => {
    if (groupId == null) return
    try {
      await api(`/groups/${groupId}/files/${fileId}`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
      setFiles(fs => fs.filter(f => f.id !== fileId))
    } catch (e) { setFilesError(e instanceof ApiError ? e.message : 'Could not remove that file.') }
  }

  if (groupId == null) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
        <div style={{ background: N.navy, padding: '0 18px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => setScreen('forum')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Group</span>
          </div>
        </div>
        <EmptyState icon="👥" title="No group selected" sub="Go back and pick a group first." action="Find Groups" onAction={() => setScreen('explore')} />
      </div>
    )
  }

  if (loadingGroup) {
    return <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: N.bg, fontSize: 12, color: '#9CA3AF' }}>Loading group…</div>
  }

  if (!group) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
        <div style={{ background: N.navy, padding: '0 18px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={() => setScreen('forum')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
            <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Group</span>
          </div>
        </div>
        <ErrorState onRetry={loadGroup} />
      </div>
    )
  }

  const joined = group.is_member
  const isAdmin = group.role === 'admin'

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      {/* Header */}
      <div style={{ background: N.navy, padding: '0 18px 0', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <button onClick={() => setScreen('forum')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: 16, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{group.name}</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginTop: 1 }}>{group.member_count} member{group.member_count === 1 ? '' : 's'}{group.unit_code ? ` · ${group.unit_code}` : ''}</div>
          </div>
          {joined ? (
            <button onClick={doLeave} disabled={leaving} style={{ background: 'rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.8)', fontWeight: 700, fontSize: 12, border: 'none', borderRadius: 10, padding: '8px 14px', cursor: leaving ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{leaving ? '…' : 'Joined'}</button>
          ) : (
            <button onClick={doJoin} disabled={joining} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 700, fontSize: 12, border: 'none', borderRadius: 10, padding: '8px 14px', cursor: joining ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{joining ? '…' : 'Join'}</button>
          )}
        </div>
        {actionError && <div style={{ color: '#FFB4B4', fontSize: 11, fontWeight: 600, marginBottom: 10 }}>{actionError}</div>}
        <div style={{ display: 'flex', gap: 0 }}>
          {(['Posts', 'Questions', 'Files', 'Members'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{ flex: 1, background: 'none', border: 'none', borderBottom: `2px solid ${tab === t ? N.gold : 'transparent'}`, color: tab === t ? N.gold : 'rgba(255,255,255,0.5)', fontWeight: tab === t ? 700 : 500, fontSize: 13, padding: '10px 0 10px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', transition: 'all 0.2s' }}>
              {t}
            </button>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }} className="scrollbar-hide">
        {(tab === 'Posts' || tab === 'Questions') && (
          <div style={{ padding: '14px 18px' }}>
            {!joined && (
              <div style={{ background: 'rgba(201,168,76,0.08)', border: `1px solid ${N.gold}30`, borderRadius: 12, padding: '10px 14px', marginBottom: 14, fontSize: 12, color: '#6B7280' }}>Join this group to post, comment, like, and vote.</div>
            )}
            {joined && (
              <div style={{ background: '#fff', border: '1.5px solid rgba(0,0,0,0.08)', borderRadius: 14, padding: 12, marginBottom: 14, boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
                <textarea value={composeText} onChange={e => setComposeText(e.target.value)} placeholder={tab === 'Questions' ? 'Ask the group a question…' : 'Write something…'} rows={2} style={{ width: '100%', border: 'none', outline: 'none', fontSize: 13, color: '#374151', fontFamily: 'Plus Jakarta Sans', resize: 'none', boxSizing: 'border-box' }} />
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 6 }}>
                  <button onClick={submitPost} disabled={!composeText.trim() || composing} style={{ background: composeText.trim() ? `linear-gradient(135deg,${N.gold},${N.goldL})` : '#E5E7EB', color: composeText.trim() ? N.navy : '#9CA3AF', fontWeight: 700, fontSize: 12, border: 'none', borderRadius: 10, padding: '7px 16px', cursor: composeText.trim() ? 'pointer' : 'not-allowed', fontFamily: 'Plus Jakarta Sans' }}>{composing ? 'Posting…' : tab === 'Questions' ? 'Ask' : 'Post'}</button>
                </div>
              </div>
            )}
            {postsError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 10 }}>{postsError}</div>}
            {loadingPosts ? (
              <div style={{ fontSize: 12, color: '#9CA3AF', padding: '20px 0' }}>Loading…</div>
            ) : posts.length === 0 ? (
              <EmptyState icon={tab === 'Questions' ? '❓' : '💬'} title={tab === 'Questions' ? 'No questions yet' : 'No posts yet'} sub={joined ? 'Be the first to share something.' : 'Join the group to get things started.'} />
            ) : posts.map(p => (
              <div key={p.id} style={{ background: '#fff', borderRadius: 16, padding: '14px 16px', marginBottom: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
                <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
                  <div style={{ width: 36, height: 36, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, color: N.navy, flexShrink: 0 }}>{p.author.slice(0, 2).toUpperCase()}</div>
                  <div><div style={{ fontWeight: 700, fontSize: 13, color: N.navy }}>{p.author}</div><div style={{ fontSize: 11, color: '#9CA3AF' }}>{p.created_at ? new Date(p.created_at).toLocaleString() : ''}</div></div>
                </div>
                <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.65, marginBottom: 12 }}>{p.is_removed ? '[removed]' : p.body}</div>
                <div style={{ display: 'flex', gap: 16, borderTop: '1px solid #F3F4F6', paddingTop: 10 }}>
                  {tab === 'Posts' ? (
                    <button onClick={() => toggleLike(p)} disabled={!joined} style={{ background: 'none', border: 'none', display: 'flex', alignItems: 'center', gap: 5, color: p.viewer_liked ? N.gold : '#9CA3AF', cursor: joined ? 'pointer' : 'default', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>
                      <svg width="14" height="14" viewBox="0 0 14 14" fill={p.viewer_liked ? N.gold : 'none'} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M7 12.5S1.5 9 1.5 5a2.5 2.5 0 015-0 2.5 2.5 0 015 0c0 4-5.5 7.5-5.5 7.5z"/></svg>
                      {p.like_count ?? 0}
                    </button>
                  ) : (
                    <button onClick={() => toggleVote(p)} disabled={!joined} style={{ background: 'none', border: 'none', display: 'flex', alignItems: 'center', gap: 5, color: p.viewer_voted ? N.gold : '#9CA3AF', cursor: joined ? 'pointer' : 'default', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M7 2v10M3 6l4-4 4 4" /></svg>
                      {p.vote_count ?? 0} vote{(p.vote_count ?? 0) === 1 ? '' : 's'}
                    </button>
                  )}
                  <button onClick={() => openPost(p)} style={{ background: 'none', border: 'none', display: 'flex', alignItems: 'center', gap: 5, color: '#9CA3AF', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M2 2h10a1 1 0 011 1v6a1 1 0 01-1 1H5l-3 3V3a1 1 0 011-1z"/></svg>
                    {p.comment_count} {expandedId === p.id ? '· hide' : ''}
                  </button>
                </div>
                {expandedId === p.id && (
                  <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #F3F4F6' }}>
                    {loadingDetail ? (
                      <div style={{ fontSize: 12, color: '#9CA3AF' }}>Loading replies…</div>
                    ) : !expandedDetail ? (
                      <div style={{ fontSize: 12, color: '#C94C4C' }}>Could not load replies.</div>
                    ) : (
                      <>
                        {expandedDetail.comments.length === 0 && <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 10 }}>No replies yet.</div>}
                        {expandedDetail.comments.map(c => (
                          <div key={c.id} style={{ background: N.bg, borderRadius: 12, padding: '10px 12px', marginBottom: 8 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                              <span style={{ fontWeight: 700, fontSize: 12, color: N.navy }}>{c.author}{c.marked_helpful && <span style={{ marginLeft: 6, color: '#4CC97B', fontWeight: 700 }}>✓ Helpful</span>}</span>
                              {tab === 'Questions' && p.author_id !== c.author_id && !c.marked_helpful && !c.is_removed && (
                                <button onClick={() => markHelpful(c.id)} style={{ background: 'none', border: 'none', color: N.gold, fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Mark helpful</button>
                              )}
                            </div>
                            <div style={{ fontSize: 12, color: '#374151' }}>{c.is_removed ? '[removed]' : c.body}</div>
                          </div>
                        ))}
                        {joined && (
                          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                            <input value={commentInput} onChange={e => setCommentInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && submitComment()} placeholder="Reply…" style={{ flex: 1, border: '1px solid rgba(0,0,0,0.1)', borderRadius: 10, padding: '8px 12px', fontSize: 12, outline: 'none', fontFamily: 'Plus Jakarta Sans' }} />
                            <button onClick={submitComment} disabled={!commentInput.trim() || sendingComment} style={{ background: N.gold, color: N.navy, border: 'none', borderRadius: 10, padding: '8px 14px', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{sendingComment ? '…' : 'Send'}</button>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        {tab === 'Files' && (
          <div style={{ padding: '14px 18px' }}>
            {joined && (
              <button onClick={openFilePicker} style={{ width: '100%', background: '#fff', border: '1.5px dashed rgba(0,0,0,0.12)', borderRadius: 14, padding: '12px 16px', marginBottom: 14, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontSize: 13, color: N.gold, fontWeight: 700, textAlign: 'center' }}>+ Share a document</button>
            )}
            {filesError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 10 }}>{filesError}</div>}
            {loadingFiles ? (
              <div style={{ fontSize: 12, color: '#9CA3AF', padding: '20px 0' }}>Loading…</div>
            ) : files.length === 0 ? (
              <EmptyState icon="📁" title="No files shared yet" sub="Members can share their own ready documents here." />
            ) : files.map(f => (
              <div key={f.id} style={{ background: '#fff', borderRadius: 14, padding: '14px 16px', marginBottom: 10, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
                <div style={{ width: 40, height: 44, background: '#F3F4F6', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, cursor: f.view_url ? 'pointer' : 'default' }} onClick={() => f.view_url && window.open(f.view_url, '_blank')}>
                  <svg width="18" height="22" viewBox="0 0 20 24" fill="none"><path d="M4 0h8l8 8v16H4V0z" fill="#E5E7EB"/><path d="M12 0l8 8h-8V0z" fill="#D1D5DB"/></svg>
                </div>
                <div style={{ flex: 1, minWidth: 0, cursor: f.view_url ? 'pointer' : 'default' }} onClick={() => f.view_url && window.open(f.view_url, '_blank')}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: N.navy, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.title || 'Untitled document'}</div>
                  <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 2 }}>{f.shared_by}{f.page_count ? ` · ${f.page_count} pages` : ''}</div>
                </div>
                {(isAdmin || f.shared_by_user_id !== undefined) && (
                  <button onClick={() => removeFile(f.id)} style={{ background: 'none', border: 'none', color: '#C94C4C', fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Remove</button>
                )}
              </div>
            ))}
            {showFilePicker && (
              <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'flex-end', zIndex: 100 }} onClick={() => setShowFilePicker(false)}>
                <div style={{ background: '#fff', width: '100%', borderRadius: '18px 18px 0 0', padding: 18, maxHeight: '60vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
                  <div style={{ fontWeight: 800, fontSize: 14, color: N.navy, marginBottom: 12 }}>Share a document</div>
                  {shareableDocs.length === 0 ? (
                    <div style={{ fontSize: 12, color: '#9CA3AF' }}>You have no ready documents to share yet.</div>
                  ) : shareableDocs.map(d => (
                    <button key={d.id} onClick={() => shareDoc(d.id)} disabled={sharing} style={{ width: '100%', textAlign: 'left', background: N.bg, border: 'none', borderRadius: 12, padding: '10px 14px', marginBottom: 8, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontSize: 13, color: N.navy }}>{d.title}</button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
        {tab === 'Members' && (
          <div style={{ padding: '14px 18px' }}>
            <div style={{ fontSize: 12, color: '#9CA3AF', fontWeight: 600, marginBottom: 12 }}>{group.member_count} MEMBER{group.member_count === 1 ? '' : 'S'}</div>
            {membersError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 10 }}>{membersError}</div>}
            {loadingMembers ? (
              <div style={{ fontSize: 12, color: '#9CA3AF', padding: '20px 0' }}>Loading…</div>
            ) : members.map(m => (
              <div key={m.user_id} style={{ background: '#fff', borderRadius: 14, padding: '12px 16px', marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.04)' }}>
                <div style={{ width: 38, height: 38, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, color: N.navy, flexShrink: 0 }}>{m.display_name.slice(0, 2).toUpperCase()}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, color: N.navy }}>{m.display_name}</div>
                </div>
                {m.role === 'admin' && <Pill text="Admin" color={N.gold} />}
                {isAdmin && (
                  <div style={{ display: 'flex', gap: 6, marginLeft: 8 }}>
                    <button onClick={() => changeRole(m.user_id, m.role === 'admin' ? 'member' : 'admin')} style={{ background: 'none', border: 'none', color: N.gold, fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{m.role === 'admin' ? 'Demote' : 'Promote'}</button>
                    {m.role !== 'admin' && <button onClick={() => removeMember(m.user_id)} style={{ background: 'none', border: 'none', color: '#C94C4C', fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Remove</button>}
                  </div>
                )}
              </div>
            ))}
            <div style={{ height: 16 }} />
          </div>
        )}
      </div>
    </div>
  )
}

// ─── GROUP CREATE ─────────────────────────────────────────────────────────────
function GroupCreateScreen({ setScreen, setActiveGroupId }: { setScreen: (s: Screen) => void; setActiveGroupId: (id: number) => void }) {
  const [step, setStep] = useState(1)
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [privacy, setPrivacy] = useState<'Public' | 'Private' | 'Course-only'>('Public')

  const [universities, setUniversities] = useState<UniversityOption[]>([])
  const [universityId, setUniversityId] = useState<number | null>(null)
  const [programs, setPrograms] = useState<ProgramOption[]>([])
  const [programId, setProgramId] = useState<number | null>(null)
  const [units, setUnits] = useState<UnitOption[]>([])
  const [unitId, setUnitId] = useState<number | null>(null)
  const [year, setYear] = useState<number | null>(null)

  const [memberSearch, setMemberSearch] = useState('')
  const [candidates, setCandidates] = useState<UserSearchResult[]>([])
  const [selected, setSelected] = useState<UserSearchResult[]>([])
  const [csrfToken, setCsrfToken] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => {
    api<{ csrf_token: string; university_id: number | null }>('/me')
      .then(me => { setCsrfToken(me.csrf_token); if (me.university_id) setUniversityId(me.university_id) })
      .catch(() => {})
    api<UniversityOption[]>('/universities').then(setUniversities).catch(() => {})
    api<UnitOption[]>('/units').then(setUnits).catch(() => {})
  }, [])

  useEffect(() => {
    if (universityId == null) { setPrograms([]); return }
    api<ProgramOption[]>(`/universities/${universityId}/programs`).then(setPrograms).catch(() => setPrograms([]))
  }, [universityId])

  useEffect(() => {
    if (!memberSearch.trim()) { setCandidates([]); return }
    const handle = setTimeout(() => {
      api<{ users: UserSearchResult[] }>(`/users/search?q=${encodeURIComponent(memberSearch.trim())}`)
        .then(res => setCandidates(res.users))
        .catch(() => setCandidates([]))
    }, 300)
    return () => clearTimeout(handle)
  }, [memberSearch])

  const create = async () => {
    if (!name.trim() || creating) return
    setCreating(true); setError('')
    try {
      const privacyValue: GroupPrivacy = privacy === 'Public' ? 'public' : privacy === 'Private' ? 'private' : 'course_only'
      const res = await api<{ id: number }>('/groups', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({
          name: name.trim(),
          description: desc.trim() || undefined,
          privacy: privacyValue,
          university_id: universityId ?? undefined,
          program_id: programId ?? undefined,
          unit_id: unitId ?? undefined,
          year: year ?? undefined,
          member_user_ids: selected.map(s => s.id),
        }),
      })
      setDone(true)
      setActiveGroupId(res.id)
      setTimeout(() => setScreen('group-detail'), 1400)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not create the group. Please try again.')
    } finally {
      setCreating(false)
    }
  }

  if (done) return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.bg, gap: 20, padding: '0 28px', textAlign: 'center', animation: 'fadeSlideUp 0.4s ease' }}>
      <div style={{ width: 72, height: 72, background: 'rgba(76,201,123,0.1)', borderRadius: '50%', border: '3px solid #4CC97B', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 28 }}>✓</div>
      <div>
        <div style={{ fontWeight: 800, fontSize: 20, color: N.navy, marginBottom: 8 }}>{name} created!</div>
        <div style={{ fontSize: 13, color: '#6B7280' }}>Taking you to the group…</div>
      </div>
    </div>
  )

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: step < 3 ? 14 : 0 }}>
          <button onClick={() => step > 1 ? setStep(s => s - 1) : setScreen('create-modal')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Create Group</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>Step {step} of 3</div>
          </div>
        </div>
        {step < 3 && (
          <div style={{ display: 'flex', gap: 4 }}>
            {[1,2,3].map(s => <div key={s} style={{ flex: 1, height: 3, borderRadius: 99, background: s <= step ? N.gold : 'rgba(255,255,255,0.15)', transition: 'background 0.3s' }} />)}
          </div>
        )}
      </div>

      {step === 1 && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 8 }}>Group name</div>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. ACT 101 — Year 1 · KU" style={{ width: '100%', border: '1.5px solid rgba(0,0,0,0.12)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, boxSizing: 'border-box' }} />
          </div>
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 8 }}>Description <span style={{ color: '#9CA3AF', fontWeight: 500 }}>(optional)</span></div>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={3} placeholder="What is this group for?" style={{ width: '100%', border: '1.5px solid rgba(0,0,0,0.12)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, resize: 'none', lineHeight: 1.6, boxSizing: 'border-box' }} />
          </div>
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 10 }}>Privacy</div>
            {(['Public', 'Private', 'Course-only'] as const).map(p => (
              <div key={p} onClick={() => setPrivacy(p)} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '12px 14px', background: '#fff', borderRadius: 12, border: `1.5px solid ${privacy === p ? N.gold : 'rgba(0,0,0,0.08)'}`, marginBottom: 8, cursor: 'pointer', transition: 'border-color 0.2s' }}>
                <div style={{ width: 18, height: 18, borderRadius: '50%', border: `2px solid ${privacy === p ? N.gold : '#D1D5DB'}`, background: privacy === p ? N.gold : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  {privacy === p && <div style={{ width: 6, height: 6, borderRadius: '50%', background: N.navy }} />}
                </div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13, color: N.navy }}>{p}</div>
                  <div style={{ fontSize: 11, color: '#9CA3AF' }}>{p === 'Public' ? 'Anyone can find and join' : p === 'Private' ? 'Invite-only, hidden from search' : 'Only students on this course'}</div>
                </div>
              </div>
            ))}
          </div>
          <button onClick={() => name.trim() && setStep(2)} style={{ width: '100%', background: name.trim() ? `linear-gradient(135deg,${N.gold},${N.goldL})` : '#E5E7EB', color: name.trim() ? N.navy : '#9CA3AF', fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: name.trim() ? 'pointer' : 'not-allowed', fontFamily: 'Plus Jakarta Sans' }}>Continue</button>
        </div>
      )}

      {step === 2 && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 8 }}>University <span style={{ color: '#9CA3AF', fontWeight: 500 }}>(optional)</span></div>
            <select value={universityId ?? ''} onChange={e => { setUniversityId(e.target.value ? Number(e.target.value) : null); setProgramId(null) }} style={{ width: '100%', border: '1.5px solid rgba(0,0,0,0.12)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, background: '#fff', appearance: 'none', boxSizing: 'border-box' }}>
              <option value="">Any university</option>
              {universities.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          </div>
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 8 }}>Course <span style={{ color: '#9CA3AF', fontWeight: 500 }}>(optional)</span></div>
            <select value={programId ?? ''} onChange={e => setProgramId(e.target.value ? Number(e.target.value) : null)} disabled={!universityId} style={{ width: '100%', border: '1.5px solid rgba(0,0,0,0.12)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, background: '#fff', appearance: 'none', boxSizing: 'border-box', opacity: universityId ? 1 : 0.6 }}>
              <option value="">Any course</option>
              {programs.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 8 }}>Unit / Module <span style={{ color: '#9CA3AF', fontWeight: 500 }}>(optional)</span></div>
            <select value={unitId ?? ''} onChange={e => setUnitId(e.target.value ? Number(e.target.value) : null)} style={{ width: '100%', border: '1.5px solid rgba(0,0,0,0.12)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, background: '#fff', appearance: 'none', boxSizing: 'border-box' }}>
              <option value="">Not tied to a unit</option>
              {units.map(u => <option key={u.id} value={u.id}>{u.code} — {u.name}</option>)}
            </select>
          </div>
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 8 }}>Year of Study <span style={{ color: '#9CA3AF', fontWeight: 500 }}>(optional)</span></div>
            <select value={year ?? ''} onChange={e => setYear(e.target.value ? Number(e.target.value) : null)} style={{ width: '100%', border: '1.5px solid rgba(0,0,0,0.12)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, background: '#fff', appearance: 'none', boxSizing: 'border-box' }}>
              <option value="">Mixed</option>
              {[1,2,3,4,5].map(y => <option key={y} value={y}>Year {y}</option>)}
            </select>
          </div>
          <button onClick={() => setStep(3)} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', marginTop: 8 }}>Continue</button>
        </div>
      )}

      {step === 3 && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '14px 18px 0' }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: N.navy, marginBottom: 10 }}>Add members <span style={{ color: '#9CA3AF', fontWeight: 500 }}>(optional — you can add later)</span></div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: '#fff', border: '1.5px solid rgba(0,0,0,0.1)', borderRadius: 12, padding: '10px 14px', marginBottom: 12 }}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="6" cy="6" r="5" stroke="#9CA3AF" strokeWidth="1.5"/><path d="M10 10l2.5 2.5" stroke="#9CA3AF" strokeWidth="1.5" strokeLinecap="round"/></svg>
              <input value={memberSearch} onChange={e => setMemberSearch(e.target.value)} placeholder="Search students…" style={{ flex: 1, border: 'none', outline: 'none', fontSize: 14, fontFamily: 'Plus Jakarta Sans', color: N.navy }} />
            </div>
            {selected.length > 0 && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                {selected.map(s => (
                  <div key={s.id} style={{ background: `${N.gold}20`, borderRadius: 99, padding: '4px 10px 4px 8px', display: 'flex', gap: 5, alignItems: 'center' }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: N.navy }}>{s.display_name.split(' ')[0]}</span>
                    <button onClick={() => setSelected(arr => arr.filter(x => x.id !== s.id))} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9CA3AF', fontSize: 14, lineHeight: 1, padding: 0 }}>×</button>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '0 18px' }} className="scrollbar-hide">
            {memberSearch.trim() === '' ? (
              <div style={{ fontSize: 12, color: '#9CA3AF', padding: '14px 0' }}>Search by name to invite classmates.</div>
            ) : candidates.length === 0 ? (
              <div style={{ fontSize: 12, color: '#9CA3AF', padding: '14px 0' }}>No students match "{memberSearch.trim()}".</div>
            ) : candidates.map(p => {
              const sel = selected.some(s => s.id === p.id)
              return (
                <div key={p.id} onClick={() => setSelected(arr => sel ? arr.filter(x => x.id !== p.id) : [...arr, p])} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '12px 0', borderBottom: '1px solid #F3F4F6', cursor: 'pointer' }}>
                  <div style={{ width: 38, height: 38, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, color: N.navy, flexShrink: 0 }}>{p.display_name.slice(0, 2).toUpperCase()}</div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 13, color: N.navy }}>{p.display_name}</div>
                    {p.year != null && <div style={{ fontSize: 11, color: '#9CA3AF' }}>Year {p.year}{p.semester != null ? `, Sem ${p.semester}` : ''}</div>}
                  </div>
                  <div style={{ width: 22, height: 22, borderRadius: 6, border: `2px solid ${sel ? N.gold : '#D1D5DB'}`, background: sel ? N.gold : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 0.2s' }}>
                    {sel && <div style={{ color: N.navy }}>{Ic.check('w-3 h-3')}</div>}
                  </div>
                </div>
              )
            })}
          </div>
          <div style={{ padding: '14px 18px 20px', flexShrink: 0 }}>
            {error && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 10 }}>{error}</div>}
            <button onClick={create} disabled={creating} style={{ width: '100%', background: creating ? '#E5E7EB' : `linear-gradient(135deg,${N.gold},${N.goldL})`, color: creating ? '#9CA3AF' : N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: creating ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, boxShadow: creating ? 'none' : `0 6px 24px ${N.gold}40` }}>
              {creating && <div style={{ width: 16, height: 16, border: '2px solid #9CA3AF', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin-slow 0.65s linear infinite' }} />}
              {creating ? 'Creating group…' : `Create Group${selected.length > 0 ? ` with ${selected.length} member${selected.length > 1 ? 's' : ''}` : ''}`}
            </button>
            <button onClick={() => !creating && setScreen('home')} style={{ width: '100%', background: 'transparent', color: '#9CA3AF', fontSize: 12, fontWeight: 600, border: 'none', padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── EMPTY & ERROR STATES ─────────────────────────────────────────────────────

function EmptyState({ icon, title, sub, action, onAction }: { icon: string; title: string; sub: string; action?: string; onAction?: () => void }) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 32px', textAlign: 'center', gap: 14 }}>
      <div style={{ fontSize: 52, lineHeight: 1, marginBottom: 4 }}>{icon}</div>
      <div style={{ fontWeight: 800, fontSize: 18, color: N.navy }}>{title}</div>
      <div style={{ fontSize: 13, color: '#9CA3AF', lineHeight: 1.65, maxWidth: 260 }}>{sub}</div>
      {action && onAction && (
        <button onClick={onAction} style={{ marginTop: 8, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 13, border: 'none', borderRadius: 14, padding: '12px 24px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: `0 4px 16px rgba(201,168,76,0.35)` }}>{action}</button>
      )}
    </div>
  )
}

function ErrorState({ onRetry }: { onRetry?: () => void }) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 32px', textAlign: 'center', gap: 14 }}>
      <div style={{ fontSize: 52 }}>⚠️</div>
      <div style={{ fontWeight: 800, fontSize: 18, color: N.navy }}>Something went wrong</div>
      <div style={{ fontSize: 13, color: '#9CA3AF', lineHeight: 1.65 }}>We couldn't load this content. Check your connection and try again.</div>
      {onRetry && <button onClick={onRetry} style={{ marginTop: 8, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 13, border: 'none', borderRadius: 14, padding: '12px 24px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Try Again</button>}
    </div>
  )
}

// ─── SUBSCRIPTION ─────────────────────────────────────────────────────────────
type SubscriptionPlan = { id: string; name: string; price: number; period: string | null }
type SubscriptionStatus = { plan: string; is_active: boolean; expires_at: string | null }

// Static display metadata (badges/colors/feature bullets) keyed by plan id -
// the backend only knows price/period, not marketing copy, so this stays
// client-side and is merged onto whatever plans GET /subscription/plans
// actually returns.
const SUBSCRIPTION_PLAN_META: Record<string, { badge?: string; badgeColor?: string; color: string; features: string[] }> = {
  free: { color: '#6B7280', features: ['5 AI sessions/month', '3 document uploads', 'Basic flashcards', 'Forum browsing'] },
  semester: { badge: 'Popular', badgeColor: N.gold, color: N.gold, features: ['Unlimited AI sessions', 'Unlimited uploads', 'All learning tools', 'Priority processing', 'Offline access', 'Full forum access'] },
  annual: { badge: 'Best Value', badgeColor: '#4CC97B', color: '#4C7BC9', features: ['Everything in Semester', '2 months free', 'Early feature access', 'Group study tools', 'Priority support'] },
}

function SubscriptionScreen({ setScreen, selectedPlan, setSelectedPlan }: { setScreen: (s: Screen) => void; selectedPlan: string; setSelectedPlan: (p: string) => void }) {
  const [plans, setPlans] = useState<SubscriptionPlan[]>([])
  const [status, setStatus] = useState<SubscriptionStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true); setError('')
    Promise.all([
      api<{ plans: SubscriptionPlan[] }>('/subscription/plans'),
      api<SubscriptionStatus>('/subscription/status'),
    ])
      .then(([plansRes, statusRes]) => { setPlans(plansRes.plans); setStatus(statusRes) })
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load subscription plans - check your connection and try again.'))
      .finally(() => setLoading(false))
  }, [])

  const paidPlans = plans.filter(p => p.id !== 'free')
  const selected = paidPlans.find(p => p.id === selectedPlan) || paidPlans[0]

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('settings')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}><div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Prepza Premium</div><div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>Unlock all AI study tools</div></div>
        </div>
        <div style={{ marginTop: 16, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 14, padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 20 }}>🎓</span>
          <div style={{ flex: 1 }}>
            <div style={{ color: '#fff', fontWeight: 700, fontSize: 13 }}>
              {status ? `Current Plan: ${status.plan.charAt(0).toUpperCase() + status.plan.slice(1)}` : 'Loading plan…'}
            </div>
            <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11 }}>
              {status?.is_active && status.expires_at
                ? `Renews/expires ${new Date(status.expires_at).toLocaleDateString()}`
                : 'Upgrade to unlock everything'}
            </div>
          </div>
          {status && <Pill text={status.is_active ? 'Active' : status.plan === 'free' ? 'Free' : 'Expired'} color={status.is_active ? '#4CC97B' : '#9CA3AF'} />}
        </div>
      </div>
      <div style={{ padding: '20px 18px' }}>
        {loading ? (
          <div style={{ fontSize: 13, color: '#9CA3AF', textAlign: 'center', padding: '30px 0' }}>Loading plans…</div>
        ) : error ? (
          <ErrorState />
        ) : (
          <>
            {plans.map(p => {
              const meta = SUBSCRIPTION_PLAN_META[p.id] || { color: '#6B7280', features: [] }
              const isCurrent = status?.plan === p.id && status.is_active
              const isSelectable = p.id !== 'free'
              const isSelected = selected?.id === p.id
              return (
                <div key={p.id} onClick={() => isSelectable && setSelectedPlan(p.id)}
                  style={{ background: '#fff', borderRadius: 18, padding: 18, marginBottom: 12, border: `2px solid ${isSelectable && isSelected ? meta.color : 'rgba(0,0,0,0.06)'}`, cursor: isSelectable ? 'pointer' : 'default', position: 'relative', boxShadow: isSelectable && isSelected ? `0 4px 20px ${meta.color}25` : '0 2px 8px rgba(0,0,0,0.05)', transition: 'all 0.2s' }}>
                  {meta.badge && <div style={{ position: 'absolute', top: -11, right: 16, background: meta.badgeColor, color: p.id === 'semester' ? N.navy : '#fff', fontSize: 10, fontWeight: 800, padding: '3px 10px', borderRadius: 99, fontFamily: 'Plus Jakarta Sans' }}>{meta.badge}</div>}
                  {isCurrent && <div style={{ position: 'absolute', top: -11, left: 16, background: '#E5E7EB', color: '#6B7280', fontSize: 10, fontWeight: 700, padding: '3px 10px', borderRadius: 99, fontFamily: 'Plus Jakarta Sans' }}>Current</div>}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                    <div>
                      <div style={{ fontWeight: 800, fontSize: 16, color: N.navy }}>{p.name}</div>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 2, marginTop: 2 }}>
                        <span style={{ fontWeight: 800, fontSize: 22, color: meta.color }}>KES {p.price.toLocaleString()}</span>
                        <span style={{ fontSize: 11, color: '#9CA3AF' }}>{p.period ? `/${p.period}` : ''}</span>
                      </div>
                    </div>
                    {isSelectable && (
                      <div style={{ width: 24, height: 24, borderRadius: '50%', border: `2px solid ${isSelected ? meta.color : '#D1D5DB'}`, background: isSelected ? meta.color : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        {isSelected && <div style={{ color: p.id === 'semester' ? N.navy : '#fff' }}>{Ic.check('w-3 h-3')}</div>}
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                    {meta.features.map((f, i) => (
                      <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <div style={{ width: 16, height: 16, borderRadius: '50%', background: `${meta.color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><div style={{ color: meta.color }}>{Ic.check('w-2.5 h-2.5')}</div></div>
                        <span style={{ fontSize: 12, color: '#4B5563' }}>{f}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
            <button onClick={() => selected && setScreen('payment')} disabled={!selected} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: selected ? 'pointer' : 'default', fontFamily: 'Plus Jakarta Sans', boxShadow: `0 6px 24px rgba(201,168,76,0.4)`, marginTop: 4, opacity: selected ? 1 : 0.6 }}>
              {selected ? `Upgrade — KES ${selected.price.toLocaleString()}` : 'Upgrade'}
            </button>
          </>
        )}
        <button onClick={() => setScreen('payment-history')} style={{ width: '100%', background: 'transparent', color: '#9CA3AF', fontSize: 12, fontWeight: 600, border: 'none', padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>View payment history</button>
        <div style={{ textAlign: 'center', fontSize: 11, color: '#D1D5DB', lineHeight: 1.6 }}>🔒 Secured payments via M-Pesa & card, powered by Pesapal.</div>
      </div>
    </div>
  )
}

// ─── PAYMENT ──────────────────────────────────────────────────────────────────
// Real Pesapal checkout: POST /subscription/upgrade returns a redirect_url
// to Pesapal's own hosted payment page (which handles M-Pesa/card itself),
// so this screen no longer simulates a method picker or an STK push - it
// just collects an optional phone number, kicks off the order, and does a
// full-page redirect. Success/failure are decided on Pesapal's side and
// land on /payment/pesapal/callback, which today renders a plain HTML page
// outside the SPA rather than routing back here - see payment-history for
// how a student confirms status after returning to the app.
function PaymentScreen({ setScreen, selectedPlan }: { setScreen: (s: Screen) => void; selectedPlan: string }) {
  const [phone, setPhone] = useState('')
  const [plan, setPlan] = useState<SubscriptionPlan | null>(null)
  const [loadingPlan, setLoadingPlan] = useState(true)
  const [redirecting, setRedirecting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api<{ plans: SubscriptionPlan[] }>('/subscription/plans')
      .then(res => setPlan(res.plans.find(p => p.id === selectedPlan) || null))
      .catch(() => setError('Could not load plan details.'))
      .finally(() => setLoadingPlan(false))
  }, [selectedPlan])

  const pay = async () => {
    if (redirecting) return
    setError('')
    setRedirecting(true)
    try {
      const me = await api<{ csrf_token: string }>('/me')
      const res = await api<{ redirect_url: string; order_tracking_id: string; merchant_reference: string }>('/subscription/upgrade', {
        method: 'POST',
        headers: { 'X-CSRF-Token': me.csrf_token },
        body: JSON.stringify({ plan: selectedPlan, phone_number: phone.trim() || undefined }),
      })
      window.location.href = res.redirect_url
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not start checkout - please try again.')
      setRedirecting(false)
    }
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 20px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <button onClick={() => setScreen('subscription')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Checkout</div>
        </div>
        <div style={{ background: 'rgba(255,255,255,0.08)', borderRadius: 14, padding: '14px 16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ color: 'rgba(255,255,255,0.7)', fontSize: 13 }}>{plan ? `Prepza ${plan.name} Plan` : 'Loading plan…'}</span>
            <span style={{ color: N.gold, fontWeight: 800 }}>{plan ? `KES ${plan.price.toLocaleString()}` : '—'}</span>
          </div>
          <div style={{ height: 1, background: 'rgba(255,255,255,0.1)', marginBottom: 8 }} />
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: '#fff', fontWeight: 700, fontSize: 14 }}>Total</span>
            <span style={{ color: '#fff', fontWeight: 800, fontSize: 16 }}>{plan ? `KES ${plan.price.toLocaleString()}` : '—'}</span>
          </div>
        </div>
      </div>
      {redirecting ? (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 20, padding: '0 32px', textAlign: 'center' }}>
          <div style={{ width: 72, height: 72, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 36, animation: 'pulse-gold 2s infinite' }}>🔒</div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 17, color: N.navy, marginBottom: 8 }}>Taking you to secure checkout…</div>
            <div style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.65 }}>You'll complete payment on Pesapal's secure page, then return to Prepza.</div>
          </div>
        </div>
      ) : (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
          {error && (
            <div style={{ background: 'rgba(201,68,68,0.08)', border: '1px solid rgba(201,68,68,0.25)', borderRadius: 12, padding: '12px 14px', color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 16 }}>{error}</div>
          )}
          <div style={{ background: '#fff', borderRadius: 16, padding: 18, marginBottom: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
              <div style={{ width: 40, height: 40, background: '#4CC97B20', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>📱</div>
              <div><div style={{ fontWeight: 700, fontSize: 14, color: N.navy }}>M-Pesa number</div><div style={{ fontSize: 11, color: '#9CA3AF' }}>Optional - speeds up checkout on Pesapal's page</div></div>
            </div>
            <input value={phone} onChange={e => setPhone(e.target.value)} placeholder="07XX XXX XXX" style={{ width: '100%', border: '1.5px solid rgba(0,0,0,0.12)', borderRadius: 12, padding: '12px 14px', fontSize: 15, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, boxSizing: 'border-box', letterSpacing: 0.5 }} />
          </div>
          <button onClick={pay} disabled={loadingPlan || !plan} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: (loadingPlan || !plan) ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 6px 24px rgba(201,168,76,0.4)', opacity: (loadingPlan || !plan) ? 0.6 : 1 }}>
            {plan ? `Continue to Payment — KES ${plan.price.toLocaleString()}` : 'Loading…'}
          </button>
          <div style={{ textAlign: 'center', marginTop: 12, fontSize: 11, color: '#D1D5DB' }}>🔒 Secured by Pesapal (M-Pesa & card)</div>
        </div>
      )}
    </div>
  )
}

function PaymentSuccessScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  useEffect(() => { const t = setTimeout(() => setScreen('home'), 5000); return () => clearTimeout(t) }, [])
  const ref = `PZA-${Math.floor(100000 + Math.random() * 900000)}`
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.bg, padding: '0 28px', textAlign: 'center', gap: 20 }}>
      <div style={{ width: 80, height: 80, background: 'rgba(76,201,123,0.12)', borderRadius: '50%', border: '3px solid #4CC97B', display: 'flex', alignItems: 'center', justifyContent: 'center', animation: 'fadeSlideUp 0.5s ease both' }}>
        <div style={{ color: '#4CC97B' }}>{Ic.check('w-10 h-10')}</div>
      </div>
      <div>
        <div style={{ fontWeight: 800, fontSize: 22, color: N.navy, marginBottom: 8 }}>Payment Successful! 🎉</div>
        <div style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.7 }}>Welcome to Prepza Premium. Your Semester plan is now active — enjoy unlimited AI sessions and all learning tools.</div>
      </div>
      <div style={{ background: '#fff', borderRadius: 16, padding: '16px 20px', width: '100%', boxShadow: '0 2px 8px rgba(0,0,0,0.06)', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {[['Plan','Semester'],['Amount','KES 599'],['Valid Until','Jan 15, 2026'],['Reference',ref]].map(([k,v]) => (
          <div key={k} style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 12, color: '#9CA3AF' }}>{k}</span>
            <span style={{ fontSize: 12, fontWeight: 700, color: N.navy, fontFamily: k === 'Reference' ? 'monospace' : 'Plus Jakarta Sans' }}>{v}</span>
          </div>
        ))}
      </div>
      <button onClick={() => setScreen('home')} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 6px 24px rgba(201,168,76,0.4)' }}>
        Start Studying Premium
      </button>
      <div style={{ fontSize: 11, color: '#D1D5DB' }}>Redirecting to home in a moment…</div>
    </div>
  )
}

function PaymentFailureScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.bg, padding: '0 28px', textAlign: 'center', gap: 20 }}>
      <div style={{ width: 80, height: 80, background: 'rgba(201,76,76,0.1)', borderRadius: '50%', border: '3px solid #C94C4C', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ color: '#C94C4C' }}>{Ic.close('w-9 h-9')}</div>
      </div>
      <div>
        <div style={{ fontWeight: 800, fontSize: 22, color: N.navy, marginBottom: 8 }}>Payment Failed</div>
        <div style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.7 }}>Your M-Pesa request was cancelled or timed out. Please try again or switch to card payment.</div>
      </div>
      <div style={{ background: '#fff', borderRadius: 16, padding: '14px 18px', width: '100%', border: '1px solid rgba(201,76,76,0.2)', textAlign: 'left' }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#C94C4C', marginBottom: 8 }}>Common reasons:</div>
        {['Insufficient M-Pesa balance','Incorrect PIN entered','Payment request timed out','Phone off or unavailable'].map((r, i) => (
          <div key={i} style={{ fontSize: 12, color: '#6B7280', marginBottom: 4 }}>• {r}</div>
        ))}
      </div>
      <button onClick={() => setScreen('payment')} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Try Again</button>
      <button onClick={() => setScreen('subscription')} style={{ width: '100%', background: 'transparent', color: '#6B7280', fontWeight: 600, fontSize: 13, border: '1.5px solid rgba(0,0,0,0.1)', borderRadius: 16, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Back to Plans</button>
    </div>
  )
}

type PaymentHistoryItem = {
  id: number
  payment_type: string
  content_title: string | null
  plan: string | null
  amount: number
  status: string
  provider: string | null
  merchant_reference: string | null
  created_at: string | null
}

const PAYMENT_STATUS_META: Record<string, { icon: string; color: string; label: string }> = {
  success: { icon: '✅', color: '#4CC97B', label: 'Success' },
  pending: { icon: '⏳', color: '#D97706', label: 'Pending' },
  failed: { icon: '❌', color: '#C94C4C', label: 'Failed' },
  refunded: { icon: '↩️', color: '#6B7280', label: 'Refunded' },
}

function PaymentHistoryScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [payments, setPayments] = useState<PaymentHistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api<{ payments: PaymentHistoryItem[] }>('/payment-history')
      .then(res => setPayments(res.payments))
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load payment history - check your connection and try again.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: N.bg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('subscription')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Payment History</div>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 18px' }} className="scrollbar-hide">
        {loading ? (
          <div style={{ fontSize: 13, color: '#9CA3AF', textAlign: 'center', padding: '30px 0' }}>Loading…</div>
        ) : error ? (
          <ErrorState />
        ) : payments.length === 0 ? (
          <EmptyState icon="💳" title="No payments yet" sub="Your subscription and content purchases will show up here." />
        ) : payments.map(p => {
          const meta = PAYMENT_STATUS_META[p.status] || { icon: '•', color: '#6B7280', label: p.status }
          const label = p.payment_type === 'subscription'
            ? `${(p.plan || 'Subscription').charAt(0).toUpperCase()}${(p.plan || 'Subscription').slice(1)} Plan`
            : (p.content_title || 'Content purchase')
          return (
            <div key={p.id} style={{ background: '#fff', borderRadius: 16, padding: '14px 16px', marginBottom: 10, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', display: 'flex', gap: 12, alignItems: 'center' }}>
              <div style={{ width: 44, height: 44, background: `${meta.color}18`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0 }}>{meta.icon}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: N.navy }} className="line-clamp-1">{label}</div>
                <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 2 }}>{p.created_at ? new Date(p.created_at).toLocaleDateString() : ''}{p.provider ? ` · ${p.provider.charAt(0).toUpperCase()}${p.provider.slice(1)}` : ''}</div>
                {p.merchant_reference && <div style={{ fontSize: 10, color: '#D1D5DB', fontFamily: 'monospace', marginTop: 2 }}>{p.merchant_reference}</div>}
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontWeight: 800, fontSize: 14, color: N.navy, marginBottom: 4 }}>KES {p.amount.toLocaleString()}</div>
                <Pill text={meta.label} color={meta.color} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── ADMIN PLATFORM ───────────────────────────────────────────────────────────

const adminNav = [
  { key: 'dashboard', label: 'Dashboard', icon: '📊' },
  { key: 'users', label: 'Users', icon: '👥' },
  { key: 'content', label: 'Content', icon: '📄' },
  { key: 'universities', label: 'Universities', icon: '🏛️' },
  { key: 'community', label: 'Community', icon: '💬' },
  { key: 'opportunities', label: 'Opportunities', icon: '🚀' },
  { key: 'organisations', label: 'Organisations', icon: '🏢' },
  { key: 'ai-usage', label: 'AI & Usage', icon: '🤖' },
  { key: 'payments', label: 'Payments', icon: '💳' },
  { key: 'communications', label: 'Communications', icon: '📢' },
  { key: 'analytics', label: 'Analytics', icon: '📈' },
  { key: 'moderation', label: 'Moderation', icon: '🛡️' },
  { key: 'system', label: 'System', icon: '⚙️' },
  { key: 'ambassadors', label: 'Ambassadors', icon: '🤝' },
]

const aUsers = [
  { id: 'U001', name: 'Arnold Gichuru', email: 'arnold@ku.ac.ke', uni: 'Kenyatta University', course: 'Actuarial Science', year: 'Y1', sub: 'Semester', status: 'Active', joined: 'Aug 1, 2025', docs: 8, aiReqs: 142 },
  { id: 'U002', name: 'Wanjiru Kamau', email: 'wanjiru@uon.ac.ke', uni: 'UoN', course: 'Computer Science', year: 'Y2', sub: 'Annual', status: 'Active', joined: 'Jul 15, 2025', docs: 24, aiReqs: 389 },
  { id: 'U003', name: 'Brian Omondi', email: 'brian@strathmore.edu', uni: 'Strathmore', course: 'B.Com Finance', year: 'Y3', sub: 'Semester', status: 'Active', joined: 'Jul 10, 2025', docs: 15, aiReqs: 211 },
  { id: 'U004', name: 'Aisha Mohamed', email: 'aisha@mku.ac.ke', uni: 'MKU', course: 'LLB Law', year: 'Y2', sub: 'Free', status: 'Active', joined: 'Jun 28, 2025', docs: 3, aiReqs: 12 },
  { id: 'U005', name: 'David Njoroge', email: 'david@ku.ac.ke', uni: 'Kenyatta University', course: 'MBBS Medicine', year: 'Y3', sub: 'Annual', status: 'Active', joined: 'Jun 20, 2025', docs: 31, aiReqs: 456 },
  { id: 'U006', name: 'Grace Muthoni', email: 'grace@jkuat.ac.ke', uni: 'JKUAT', course: 'BSc Comp Sci', year: 'Y1', sub: 'Free', status: 'Suspended', joined: 'Jun 5, 2025', docs: 0, aiReqs: 0 },
  { id: 'U007', name: 'James Kariuki', email: 'james@uon.ac.ke', uni: 'UoN', course: 'BSc Economics', year: 'Y2', sub: 'Semester', status: 'Active', joined: 'May 30, 2025', docs: 11, aiReqs: 178 },
  { id: 'U008', name: 'Faith Njeri', email: 'faith@daystar.ac.ke', uni: 'Daystar University', course: 'BA Psychology', year: 'Y3', sub: 'Free', status: 'Active', joined: 'May 20, 2025', docs: 4, aiReqs: 28 },
]

function AdminBadge({ text, color }: { text: string; color: string }) {
  const bg = color === 'green' ? '#DCFCE7' : color === 'amber' ? '#FEF3C7' : color === 'red' ? '#FEE2E2' : color === 'blue' ? '#DBEAFE' : '#F3F4F6'
  const fg = color === 'green' ? '#16A34A' : color === 'amber' ? '#D97706' : color === 'red' ? '#DC2626' : color === 'blue' ? '#2563EB' : '#6B7280'
  return <span style={{ background: bg, color: fg, fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 99, fontFamily: 'Plus Jakarta Sans', whiteSpace: 'nowrap' }}>{text}</span>
}

function AdminBarChart({ data, labels, height = 80, color = N.gold }: { data: number[]; labels?: string[]; height?: number; color?: string }) {
  const max = Math.max(...data) || 1
  const w = data.length * 28
  return (
    <svg width="100%" height={height + (labels ? 18 : 0)} viewBox={`0 0 ${w} ${height + (labels ? 18 : 0)}`} preserveAspectRatio="none">
      {data.map((v, i) => {
        const bh = Math.max(2, (v / max) * (height - 4))
        return (
          <g key={i}>
            <rect x={i * 28 + 2} y={height - bh} width={24} height={bh} rx={4} fill={color} opacity={0.75 + (i === data.length - 1 ? 0.25 : 0)} />
            {labels && <text x={i * 28 + 14} y={height + 14} textAnchor="middle" fontSize="9" fill="#9CA3AF" fontFamily="Plus Jakarta Sans">{labels[i]}</text>}
          </g>
        )
      })}
    </svg>
  )
}

function AdminLineChart({ data, color = N.gold, height = 60 }: { data: number[]; color?: string; height?: number }) {
  const max = Math.max(...data) || 1
  const min = Math.min(...data)
  const range = max - min || 1
  const W = 300
  const pts = data.map((v, i) => [
    (i / (data.length - 1)) * W,
    height - 8 - ((v - min) / range) * (height - 16)
  ])
  const linePath = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')
  const areaPath = `${linePath} L${W},${height} L0,${height} Z`
  const gid = `ag${color.replace('#','')}`
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.18} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gid})`} />
      <path d={linePath} stroke={color} strokeWidth={2.5} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      {pts.map((p, i) => i === pts.length - 1 && <circle key={i} cx={p[0]} cy={p[1]} r={4} fill={color} stroke="#fff" strokeWidth={1.5} />)}
    </svg>
  )
}

function AdminKPI({ label, value, sub, trend, color = N.navy, chartData }: { label: string; value: string; sub?: string; trend?: string; color?: string; chartData?: number[] }) {
  const isUp = trend?.startsWith('+')
  return (
    <div style={{ background: '#fff', borderRadius: 14, padding: '16px 18px', boxShadow: '0 1px 4px rgba(0,0,0,0.06)', border: '1px solid rgba(0,0,0,0.05)', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: '#9CA3AF', letterSpacing: 0.3 }}>{label}</div>
      <div style={{ fontWeight: 800, fontSize: 24, color, letterSpacing: '-0.5px', lineHeight: 1 }}>{value}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: 11, color: '#9CA3AF' }}>{sub}</div>
        {trend && <span style={{ fontSize: 11, fontWeight: 700, color: isUp ? '#16A34A' : '#DC2626' }}>{trend}</span>}
      </div>
      {chartData && <div style={{ marginTop: 4 }}><AdminLineChart data={chartData} color={color === N.navy ? N.gold : color} height={40} /></div>}
    </div>
  )
}

function AdminTable({ cols, rows, actions }: { cols: string[]; rows: (string | React.ReactNode)[][]; actions?: (i: number) => React.ReactNode }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, fontFamily: 'Plus Jakarta Sans' }}>
        <thead>
          <tr style={{ background: '#F9FAFB', borderBottom: '1px solid #E5E7EB' }}>
            {cols.map(c => <th key={c} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, color: '#6B7280', fontSize: 11, whiteSpace: 'nowrap' }}>{c}</th>)}
            {actions && <th style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 700, color: '#6B7280', fontSize: 11 }}>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ borderBottom: '1px solid #F3F4F6', transition: 'background 0.1s' }}>
              {row.map((cell, j) => <td key={j} style={{ padding: '12px 14px', color: j === 0 ? N.navy : '#4B5563', fontWeight: j === 0 ? 600 : 400, verticalAlign: 'middle', whiteSpace: 'nowrap' }}>{cell}</td>)}
              {actions && <td style={{ padding: '12px 14px', textAlign: 'right' }}>{actions(i)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AdminCard({ title, children, action, actionLabel }: { title: string; children: React.ReactNode; action?: () => void; actionLabel?: string }) {
  return (
    <div style={{ background: '#fff', borderRadius: 14, boxShadow: '0 1px 4px rgba(0,0,0,0.06)', border: '1px solid rgba(0,0,0,0.05)', overflow: 'hidden' }}>
      <div style={{ padding: '14px 18px', borderBottom: '1px solid #F3F4F6', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontWeight: 700, fontSize: 14, color: N.navy }}>{title}</div>
        {action && <button onClick={action} style={{ fontSize: 12, fontWeight: 600, color: N.gold, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{actionLabel ?? 'View all'}</button>}
      </div>
      {children}
    </div>
  )
}

type AdminAnnouncementItem = { id: number; title: string; body: string; reach: number; created_at: string | null }

function AdminSection({ section, setSection }: { section: string; setSection: (s: string) => void }) {
  const [search, setSearch] = useState('')
  const [userFilter, setUserFilter] = useState('All')
  const [selectedUser, setSelectedUser] = useState<typeof aUsers[0] | null>(null)
  const [confirmAction, setConfirmAction] = useState<{ type: string; target: string } | null>(null)
  const [contentTab, setContentTab] = useState('Documents')
  const [commTab, setCommTab] = useState('Announcements')
  const [csrfToken, setCsrfToken] = useState('')
  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  const [annTitle, setAnnTitle] = useState('')
  const [annBody, setAnnBody] = useState('')
  const [annUniversityId, setAnnUniversityId] = useState<number | null>(null)
  const [annProgramId, setAnnProgramId] = useState<number | null>(null)
  const [annYear, setAnnYear] = useState<number | null>(null)
  const [annSemester, setAnnSemester] = useState<number | null>(null)
  const [annGroupId, setAnnGroupId] = useState<number | null>(null)
  const [annGroupName, setAnnGroupName] = useState('')
  const [annGroupSearch, setAnnGroupSearch] = useState('')
  const [annGroupResults, setAnnGroupResults] = useState<{ id: number; name: string }[]>([])
  const [annUniversities, setAnnUniversities] = useState<{ id: number; name: string }[]>([])
  const [annPrograms, setAnnPrograms] = useState<{ id: number; name: string }[]>([])
  const [annSending, setAnnSending] = useState(false)
  const [annError, setAnnError] = useState('')
  const [annSent, setAnnSent] = useState(false)

  const [announcements, setAnnouncements] = useState<AdminAnnouncementItem[]>([])
  const [announcementsLoading, setAnnouncementsLoading] = useState(true)

  const loadAnnouncements = () => {
    setAnnouncementsLoading(true)
    api<AdminAnnouncementItem[]>('/admin/announcements')
      .then(setAnnouncements)
      .catch(() => {})
      .finally(() => setAnnouncementsLoading(false))
  }

  useEffect(() => {
    if (section !== 'communications') return
    loadAnnouncements()
    api<{ id: number; name: string }[]>('/universities').then(setAnnUniversities).catch(() => {})
  }, [section])

  useEffect(() => {
    if (annUniversityId == null) { setAnnPrograms([]); setAnnProgramId(null); return }
    api<{ id: number; name: string }[]>(`/universities/${annUniversityId}/programs`).then(setAnnPrograms).catch(() => {})
  }, [annUniversityId])

  useEffect(() => {
    if (section !== 'communications') return
    const q = annGroupSearch.trim()
    if (!q) { setAnnGroupResults([]); return }
    const t = setTimeout(() => {
      api<{ page: number; groups: { id: number; name: string }[] }>(`/groups?q=${encodeURIComponent(q)}`)
        .then(res => setAnnGroupResults(res.groups))
        .catch(() => {})
    }, 300)
    return () => clearTimeout(t)
  }, [annGroupSearch, section])

  const sendAnnouncement = async () => {
    if (!annTitle.trim() || !annBody.trim() || annSending) return
    setAnnSending(true); setAnnError(''); setAnnSent(false)
    try {
      const payload: Record<string, number | string> = { title: annTitle.trim(), body: annBody.trim() }
      if (annUniversityId != null) payload.university_id = annUniversityId
      if (annProgramId != null) payload.program_id = annProgramId
      if (annYear != null) payload.year = annYear
      if (annSemester != null) payload.semester = annSemester
      if (annGroupId != null) payload.group_id = annGroupId
      await api('/admin/announcements', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify(payload),
      })
      setAnnTitle(''); setAnnBody('')
      setAnnUniversityId(null); setAnnProgramId(null); setAnnYear(null); setAnnSemester(null)
      setAnnGroupId(null); setAnnGroupName(''); setAnnGroupSearch(''); setAnnGroupResults([])
      setAnnSent(true)
      loadAnnouncements()
    } catch (e) {
      setAnnError(e instanceof ApiError ? e.message : 'Could not send announcement.')
    } finally {
      setAnnSending(false)
    }
  }

  const filteredUsers = aUsers.filter(u => {
    const q = search.toLowerCase()
    const matchQ = !q || u.name.toLowerCase().includes(q) || u.email.includes(q) || u.uni.toLowerCase().includes(q)
    const matchF = userFilter === 'All' || (userFilter === 'Active' && u.status === 'Active') || (userFilter === 'Suspended' && u.status === 'Suspended') || (userFilter === 'Premium' && u.sub !== 'Free') || (userFilter === 'Free' && u.sub === 'Free')
    return matchQ && matchF
  })

  const revenueData = [89000, 102000, 118000, 95000, 134000, 127000, 142250]
  const revLabels = ['Feb','Mar','Apr','May','Jun','Jul','Aug']
  const studentsData = [1840, 1980, 2124, 2267, 2488, 2643, 2847]
  const aiData = [2840, 3100, 2650, 3890, 4234, 3102, 3214]
  const aiLabels = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
  const uploadsData = [45, 62, 38, 74, 55, 68, 59, 83, 71, 49, 94, 78, 65, 72]

  const ActivityDot = ({ color }: { color: string }) => <div style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0, marginTop: 3 }} />

  if (section === 'dashboard') return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* KPI grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14 }}>
        <AdminKPI label="Total Students" value="2,847" sub="All time" trend="+124 this week" color={N.navy} chartData={studentsData} />
        <AdminKPI label="Active Today" value="891" sub="31% of total" trend="+8% vs yesterday" color="#4C7BC9" chartData={aiData} />
        <AdminKPI label="Revenue (MTD)" value="KES 142K" sub="Aug 2025" trend="+12% vs Jul" color="#16A34A" chartData={revenueData} />
        <AdminKPI label="Active Subscriptions" value="893" sub="Free: 1,954" trend="+34 this week" color={N.gold} chartData={studentsData.map(v => v * 0.31)} />
        <AdminKPI label="AI Requests Today" value="3,214" sub="Avg 1.13 per user" trend="+18% vs yesterday" color="#7C3AED" chartData={aiData} />
        <AdminKPI label="Est. AI Cost (MTD)" value="KES 12.4K" sub="~KES 4.35/user" trend="-3% vs Jul" color="#DC2626" chartData={aiData.map(v => v * 3.9)} />
        <AdminKPI label="Docs Uploaded" value="14,302" sub="Today: 72" trend="+287 this week" color={N.navy} chartData={uploadsData} />
        <AdminKPI label="Storage Used" value="342 GB" sub="of 1 TB (34%)" color="#6B7280" chartData={[210,240,265,290,315,328,342]} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: 14 }}>
        {/* Revenue chart */}
        <AdminCard title="Revenue — Last 7 Months">
          <div style={{ padding: '16px 18px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ fontSize: 11, color: '#9CA3AF' }}>KES</span>
              <AdminBadge text="+12% MoM" color="green" />
            </div>
            <AdminBarChart data={revenueData} labels={revLabels} height={100} color={N.gold} />
          </div>
        </AdminCard>
        {/* AI usage */}
        <AdminCard title="AI Requests — This Week">
          <div style={{ padding: '16px 18px' }}>
            <AdminBarChart data={aiData} labels={aiLabels} height={100} color="#7C3AED" />
          </div>
        </AdminCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        {/* Student growth */}
        <AdminCard title="Student Growth — Last 7 Months">
          <div style={{ padding: '16px 18px' }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: N.navy, marginBottom: 4 }}>2,847 <span style={{ fontSize: 13, color: '#9CA3AF', fontWeight: 500 }}>total</span></div>
            <AdminLineChart data={studentsData} color={N.navy} height={60} />
          </div>
        </AdminCard>

        {/* Recent activity */}
        <AdminCard title="Recent Activity">
          <div style={{ padding: '0 18px' }}>
            {[
              { dot: '#4CC97B', text: 'Faith Njeri registered · Daystar University', time: '2 min ago' },
              { dot: N.gold, text: 'Arnold Gichuru upgraded to Semester Plan', time: '5 min ago' },
              { dot: '#7C3AED', text: 'AI processed ACT 101 (3 flashcard sets, 1 podcast)', time: '9 min ago' },
              { dot: '#4C7BC9', text: 'Brian Omondi uploaded MAT 101 Past Papers.pdf', time: '14 min ago' },
              { dot: '#DC2626', text: 'Report: Aisha Mohamed reported post #1047', time: '22 min ago' },
              { dot: N.gold, text: 'James Kariuki renewed Annual Plan — KES 999', time: '31 min ago' },
              { dot: '#6B7280', text: 'System: Nightly AI job completed (847 docs processed)', time: '2h ago' },
            ].map((a, i) => (
              <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', padding: '10px 0', borderBottom: i < 6 ? '1px solid #F3F4F6' : 'none' }}>
                <ActivityDot color={a.dot} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, color: '#374151', lineHeight: 1.4 }}>{a.text}</div>
                  <div style={{ fontSize: 11, color: '#D1D5DB', marginTop: 2 }}>{a.time}</div>
                </div>
              </div>
            ))}
          </div>
        </AdminCard>
      </div>

      {/* Alerts */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12 }}>
        {[
          { icon: '🛡️', label: 'Pending Reports', value: '7', color: '#FEF3C7', fg: '#D97706', action: () => setSection('moderation') },
          { icon: '📄', label: 'Content Awaiting Review', value: '23', color: '#DBEAFE', fg: '#2563EB', action: () => setSection('content') },
          { icon: '💳', label: 'Failed Payments', value: '14', color: '#FEE2E2', fg: '#DC2626', action: () => setSection('payments') },
        ].map(a => (
          <button key={a.label} onClick={a.action} style={{ background: a.color, border: 'none', borderRadius: 14, padding: '14px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', display: 'flex', gap: 12, alignItems: 'center', textAlign: 'left' }}>
            <span style={{ fontSize: 22 }}>{a.icon}</span>
            <div>
              <div style={{ fontSize: 20, fontWeight: 800, color: a.fg }}>{a.value}</div>
              <div style={{ fontSize: 11, fontWeight: 600, color: a.fg, opacity: 0.8 }}>{a.label}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )

  if (section === 'users') return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* User detail panel */}
      {selectedUser && (
        <div style={{ background: '#fff', borderRadius: 14, padding: 20, boxShadow: '0 1px 4px rgba(0,0,0,0.06)', border: '1px solid rgba(0,0,0,0.05)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
            <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
              <div style={{ width: 52, height: 52, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 18, color: N.navy }}>{selectedUser.name.split(' ').map(n => n[0]).join('')}</div>
              <div>
                <div style={{ fontWeight: 800, fontSize: 17, color: N.navy }}>{selectedUser.name}</div>
                <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>{selectedUser.email}</div>
                <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                  <AdminBadge text={selectedUser.status} color={selectedUser.status === 'Active' ? 'green' : 'red'} />
                  <AdminBadge text={selectedUser.sub} color={selectedUser.sub === 'Free' ? 'gray' : 'amber'} />
                </div>
              </div>
            </div>
            <button onClick={() => setSelectedUser(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9CA3AF', fontSize: 20 }}>×</button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, marginBottom: 16 }}>
            {[['University', selectedUser.uni], ['Course', selectedUser.course], ['Year', selectedUser.year], ['Joined', selectedUser.joined], ['Documents', selectedUser.docs.toString()], ['AI Requests', selectedUser.aiReqs.toString()], ['User ID', selectedUser.id], ['Subscription', selectedUser.sub]].map(([k, v]) => (
              <div key={k} style={{ background: '#F9FAFB', borderRadius: 10, padding: '10px 12px' }}>
                <div style={{ fontSize: 10, color: '#9CA3AF', fontWeight: 600, marginBottom: 3 }}>{k}</div>
                <div style={{ fontSize: 13, fontWeight: 600, color: N.navy }}>{v}</div>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {[
              { label: 'Suspend', color: '#FEF3C7', fg: '#D97706' },
              { label: 'Reset Password', color: '#DBEAFE', fg: '#2563EB' },
              { label: 'Change Role', color: '#F3F4F6', fg: '#374151' },
              { label: 'View Activity', color: '#F0FDF4', fg: '#16A34A' },
            ].map(a => (
              <button key={a.label} onClick={() => setConfirmAction({ type: a.label, target: selectedUser.name })} style={{ background: a.color, color: a.fg, border: 'none', borderRadius: 10, padding: '8px 14px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 12 }}>{a.label}</button>
            ))}
          </div>
        </div>
      )}

      {/* Confirm modal */}
      {confirmAction && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setConfirmAction(null)}>
          <div style={{ background: '#fff', borderRadius: 16, padding: 24, maxWidth: 380, width: '90%', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }} onClick={e => e.stopPropagation()}>
            <div style={{ fontWeight: 800, fontSize: 17, color: N.navy, marginBottom: 8 }}>Confirm: {confirmAction.type}</div>
            <div style={{ fontSize: 13, color: '#6B7280', marginBottom: 20, lineHeight: 1.6 }}>Are you sure you want to <strong>{confirmAction.type.toLowerCase()}</strong> for <strong>{confirmAction.target}</strong>? This action will be logged.</div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => setConfirmAction(null)} style={{ flex: 1, background: '#F3F4F6', color: '#374151', border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 13 }}>Cancel</button>
              <button onClick={() => setConfirmAction(null)} style={{ flex: 1, background: '#DC2626', color: '#fff', border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13 }}>Confirm</button>
            </div>
          </div>
        </div>
      )}

      <AdminCard title={`Users — ${filteredUsers.length} of ${aUsers.length}`}>
        <div style={{ padding: '12px 18px', borderBottom: '1px solid #F3F4F6', display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8, background: '#F9FAFB', border: '1px solid #E5E7EB', borderRadius: 10, padding: '8px 12px', minWidth: 200 }}>
            <span style={{ color: '#9CA3AF', fontSize: 14 }}>🔍</span>
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name, email, university…" style={{ flex: 1, border: 'none', background: 'none', outline: 'none', fontSize: 13, fontFamily: 'Plus Jakarta Sans', color: N.navy }} />
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {['All','Active','Suspended','Premium','Free'].map(f => (
              <button key={f} onClick={() => setUserFilter(f)} style={{ padding: '7px 14px', borderRadius: 8, background: userFilter === f ? N.navy : '#F3F4F6', color: userFilter === f ? '#fff' : '#6B7280', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>{f}</button>
            ))}
          </div>
        </div>
        <AdminTable
          cols={['User', 'University', 'Plan', 'Docs', 'AI Reqs', 'Status', 'Joined']}
          rows={filteredUsers.map(u => [
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <div style={{ width: 32, height: 32, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 11, color: N.navy, flexShrink: 0 }}>{u.name.split(' ').map(n => n[0]).join('')}</div>
              <div><div style={{ fontWeight: 600, color: N.navy }}>{u.name}</div><div style={{ fontSize: 11, color: '#9CA3AF' }}>{u.email}</div></div>
            </div>,
            u.uni, u.sub, u.docs.toString(), u.aiReqs.toString(),
            <AdminBadge text={u.status} color={u.status === 'Active' ? 'green' : 'red'} />,
            u.joined
          ])}
          actions={i => (
            <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
              <button onClick={() => setSelectedUser(filteredUsers[i])} style={{ background: '#F3F4F6', border: 'none', borderRadius: 7, padding: '5px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, color: '#374151', fontFamily: 'Plus Jakarta Sans' }}>View</button>
              <button onClick={() => setConfirmAction({ type: 'Suspend', target: filteredUsers[i].name })} style={{ background: '#FEF3C7', border: 'none', borderRadius: 7, padding: '5px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, color: '#D97706', fontFamily: 'Plus Jakarta Sans' }}>Suspend</button>
            </div>
          )}
        />
        <div style={{ padding: '12px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid #F3F4F6' }}>
          <span style={{ fontSize: 12, color: '#9CA3AF' }}>Showing {filteredUsers.length} results</span>
          <div style={{ display: 'flex', gap: 4 }}>
            {[1,2,3,'…',47].map((p, i) => <button key={i} style={{ width: 30, height: 30, borderRadius: 6, background: p === 1 ? N.navy : '#F3F4F6', color: p === 1 ? '#fff' : '#374151', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>{p}</button>)}
          </div>
        </div>
      </AdminCard>
    </div>
  )

  if (section === 'content') {
    const contentRows: Record<string,(string|React.ReactNode)[][]> = {
      Documents: [
        ['ACT 101 Lecture Notes – Week 1-6', 'Arnold Gichuru', 'Kenyatta University', 'PDF · 38p', 'Aug 10', <AdminBadge text="Approved" color="green" />],
        ['KU Past Papers 2020-2023 (MAT 101)', 'Student Library', 'Kenyatta University', 'PDF · 72p', 'Aug 9', <AdminBadge text="Approved" color="green" />],
        ['STA 101 Probability Slides', 'Dr. Njuguna', 'University of Nairobi', 'PPT · 44p', 'Aug 8', <AdminBadge text="Pending" color="amber" />],
        ['Constitutional Law Notes 2025', 'Aisha Mohamed', 'Mount Kenya University', 'PDF · 55p', 'Aug 7', <AdminBadge text="Pending" color="amber" />],
        ['MBBS Pharmacology Revision', 'David Njoroge', 'Kenyatta University', 'PDF · 91p', 'Aug 6', <AdminBadge text="Flagged" color="red" />],
      ],
      Podcasts: [
        ['Introduction to Interest Theory', 'Arnold Gichuru', 'AI-Generated', '9 min', 'Aug 10', <AdminBadge text="Published" color="green" />],
        ['Present Value Explained Simply', 'Brian Omondi', 'AI-Generated', '12 min', 'Aug 9', <AdminBadge text="Published" color="green" />],
        ['Probability Foundations', 'Wanjiru Kamau', 'AI-Generated', '14 min', 'Aug 8', <AdminBadge text="Review" color="amber" />],
      ],
      Flashcards: [
        ['ACT 101 – Interest Theory (35 cards)', 'Arnold Gichuru', 'AI-Generated', '35 cards', 'Aug 10', <AdminBadge text="Active" color="green" />],
        ['STA 101 Probability (28 cards)', 'Faith Njeri', 'AI-Generated', '28 cards', 'Aug 9', <AdminBadge text="Active" color="green" />],
      ],
      Quizzes: [
        ['ACT 101 – Interest Theory Quiz', 'Arnold Gichuru', 'AI-Generated', '15 Qs', 'Aug 10', <AdminBadge text="Active" color="green" />],
        ['MAT 101 Integration Quiz', 'James Kariuki', 'AI-Generated', '10 Qs', 'Aug 8', <AdminBadge text="Active" color="green" />],
      ],
    }
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <AdminCard title="Content Management">
          <div style={{ padding: '12px 18px', borderBottom: '1px solid #F3F4F6', display: 'flex', gap: 6 }}>
            {Object.keys(contentRows).map(t => <button key={t} onClick={() => setContentTab(t)} style={{ padding: '7px 16px', borderRadius: 8, background: contentTab === t ? N.navy : '#F3F4F6', color: contentTab === t ? '#fff' : '#6B7280', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>{t}</button>)}
          </div>
          <AdminTable
            cols={['Title', 'Author', 'Institution', 'Size', 'Date', 'Status']}
            rows={contentRows[contentTab]}
            actions={() => (
              <div style={{ display: 'flex', gap: 5 }}>
                <button style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Approve</button>
                <button style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Remove</button>
              </div>
            )}
          />
        </AdminCard>
      </div>
    )
  }

  if (section === 'ai-usage') return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
        <AdminKPI label="AI Requests Today" value="3,214" sub="Successful: 3,188" trend="+18% vs yesterday" color="#7C3AED" chartData={aiData} />
        <AdminKPI label="Failed Requests" value="26" sub="0.8% error rate" trend="-2% vs yesterday" color="#DC2626" chartData={[40,28,35,22,30,18,26]} />
        <AdminKPI label="Tokens Used (MTD)" value="84.2M" sub="~KES 12,400 cost" trend="+9% vs Jul" color={N.gold} chartData={aiData.map(v => v * 870)} />
        <AdminKPI label="Avg Response Time" value="1.4s" sub="P95: 3.2s" trend="-0.2s vs last week" color="#16A34A" chartData={[1.8, 1.9, 1.6, 1.7, 1.5, 1.4, 1.4]} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <AdminCard title="AI Requests by Feature">
          <div style={{ padding: '16px 18px' }}>
            {[
              { label: 'Document Processing', pct: 38, color: N.navy, count: '1,221' },
              { label: 'Flashcard Generation', pct: 24, color: N.gold, count: '772' },
              { label: 'Quiz Generation', pct: 18, color: '#7C3AED', count: '579' },
              { label: 'Podcast Creation', pct: 12, color: '#4C7BC9', count: '386' },
              { label: 'AI Tutor Chat', pct: 8, color: '#4CC97B', count: '256' },
            ].map(r => (
              <div key={r.label} style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 12, color: '#374151', fontWeight: 500 }}>{r.label}</span>
                  <span style={{ fontSize: 12, fontWeight: 700, color: '#374151' }}>{r.count}</span>
                </div>
                <div style={{ background: '#F3F4F6', borderRadius: 99, height: 6 }}>
                  <div style={{ background: r.color, borderRadius: 99, height: 6, width: `${r.pct}%`, transition: 'width 0.5s' }} />
                </div>
              </div>
            ))}
          </div>
        </AdminCard>
        <AdminCard title="AI Requests — Last 7 Days">
          <div style={{ padding: '16px 18px' }}>
            <AdminBarChart data={aiData} labels={aiLabels} height={120} color="#7C3AED" />
          </div>
        </AdminCard>
      </div>
      <AdminCard title="Recent AI Jobs">
        <AdminTable
          cols={['Job ID', 'Type', 'User', 'Document', 'Status', 'Duration', 'Time']}
          rows={[
            ['AI-9847', 'Quiz Generation', 'Arnold Gichuru', 'ACT 101 Notes', <AdminBadge text="Success" color="green" />, '1.2s', '2 min ago'],
            ['AI-9846', 'Flashcard Gen.', 'Wanjiru Kamau', 'CS 201 Algorithms', <AdminBadge text="Success" color="green" />, '0.9s', '5 min ago'],
            ['AI-9845', 'Podcast Creation', 'Brian Omondi', 'MAT 101 Notes', <AdminBadge text="Processing" color="blue" />, '—', '8 min ago'],
            ['AI-9844', 'Doc Processing', 'David Njoroge', 'Pharmacology.pdf', <AdminBadge text="Success" color="green" />, '3.4s', '12 min ago'],
            ['AI-9843', 'AI Tutor Chat', 'Faith Njeri', 'Context: STA 101', <AdminBadge text="Success" color="green" />, '0.6s', '15 min ago'],
            ['AI-9842', 'Quiz Generation', 'James Kariuki', 'ECO 101 Notes', <AdminBadge text="Failed" color="red" />, '—', '18 min ago'],
          ]}
        />
      </AdminCard>
    </div>
  )

  if (section === 'payments') return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
        <AdminKPI label="Revenue (MTD)" value="KES 142K" sub="Aug 2025" trend="+12% vs Jul" color="#16A34A" chartData={revenueData} />
        <AdminKPI label="Active Subscriptions" value="893" sub="Semester: 721 · Annual: 172" trend="+34 this week" color={N.gold} chartData={studentsData.map(v => v * 0.31)} />
        <AdminKPI label="Failed Payments" value="14" sub="Aug 2025" trend="+3 this week" color="#DC2626" chartData={[8,12,7,15,11,9,14]} />
        <AdminKPI label="Avg. Plan Value" value="KES 159" sub="Weighted average" trend="+KES 8 vs Jul" color={N.navy} chartData={[140,142,148,151,155,156,159]} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: 14 }}>
        <AdminCard title="Revenue — Last 7 Months">
          <div style={{ padding: '16px 18px' }}>
            <AdminBarChart data={revenueData} labels={revLabels} height={100} color={N.gold} />
          </div>
        </AdminCard>
        <AdminCard title="Subscription Breakdown">
          <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            {[
              { label: 'Semester Plan', count: 721, pct: 81, color: N.gold, price: 'KES 599' },
              { label: 'Annual Plan', count: 172, pct: 19, color: '#4C7BC9', price: 'KES 999' },
            ].map(r => (
              <div key={r.label}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: N.navy }}>{r.label}</span>
                  <span style={{ fontSize: 12, color: '#6B7280' }}>{r.count} · {r.price}</span>
                </div>
                <div style={{ background: '#F3F4F6', borderRadius: 99, height: 8 }}>
                  <div style={{ background: r.color, borderRadius: 99, height: 8, width: `${r.pct}%` }} />
                </div>
              </div>
            ))}
            <div style={{ marginTop: 8, padding: '12px 14px', background: '#F9FAFB', borderRadius: 10 }}>
              <div style={{ fontSize: 11, color: '#9CA3AF' }}>Free plan</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: N.navy }}>1,954</div>
              <div style={{ fontSize: 11, color: '#9CA3AF' }}>Conversion opportunity</div>
            </div>
          </div>
        </AdminCard>
      </div>
      <AdminCard title="Recent Transactions">
        <AdminTable
          cols={['Reference', 'Student', 'Plan', 'Amount', 'Method', 'Status', 'Date']}
          rows={[
            ['PZA-849201', 'Arnold Gichuru', 'Semester', 'KES 599', 'M-Pesa', <AdminBadge text="Success" color="green" />, 'Aug 10, 2025'],
            ['PZA-849198', 'James Kariuki', 'Annual', 'KES 999', 'Card', <AdminBadge text="Success" color="green" />, 'Aug 10, 2025'],
            ['PZA-849190', 'Faith Njeri', 'Semester', 'KES 599', 'M-Pesa', <AdminBadge text="Failed" color="red" />, 'Aug 10, 2025'],
            ['PZA-849187', 'Wanjiru Kamau', 'Annual', 'KES 999', 'M-Pesa', <AdminBadge text="Success" color="green" />, 'Aug 9, 2025'],
            ['PZA-849173', 'Brian Omondi', 'Semester', 'KES 599', 'Card', <AdminBadge text="Success" color="green" />, 'Aug 9, 2025'],
            ['PZA-849160', 'David Njoroge', 'Annual', 'KES 999', 'M-Pesa', <AdminBadge text="Refunded" color="amber" />, 'Aug 8, 2025'],
          ]}
          actions={() => <button style={{ background: '#F3F4F6', color: '#374151', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>View</button>}
        />
        <div style={{ padding: '12px 18px', borderTop: '1px solid #F3F4F6', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: '#9CA3AF' }}>Page 1 of 312</span>
          <div style={{ display: 'flex', gap: 4 }}>
            {['←', '1', '2', '3', '→'].map((p, i) => <button key={i} style={{ width: 30, height: 30, borderRadius: 6, background: p === '1' ? N.navy : '#F3F4F6', color: p === '1' ? '#fff' : '#374151', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>{p}</button>)}
          </div>
        </div>
      </AdminCard>
    </div>
  )

  if (section === 'moderation') return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
        <AdminKPI label="Open Reports" value="7" sub="Avg resolution: 4h" trend="+2 since yesterday" color="#DC2626" />
        <AdminKPI label="Resolved Today" value="3" sub="Dismiss: 2 · Remove: 1" color="#16A34A" />
        <AdminKPI label="Total Posts" value="1,247" sub="Forums + Comments" color={N.navy} />
        <AdminKPI label="Suspended Users" value="1" sub="Pending review: 0" color="#D97706" />
      </div>
      <AdminCard title="Report Queue — 7 Open">
        <AdminTable
          cols={['#', 'Type', 'Content', 'Reported By', 'Reason', 'Priority', 'Received']}
          rows={[
            ['R-107', 'Post', '"Does anyone have exam leaks for…"', 'Wanjiru Kamau', 'Academic Dishonesty', <AdminBadge text="High" color="red" />, '2h ago'],
            ['R-106', 'Document', 'ACT 101 Notes (copyrighted claim)', 'Anonymous', 'Copyright', <AdminBadge text="High" color="red" />, '4h ago'],
            ['R-105', 'User', 'User selling answers in DMs', 'Brian Omondi', 'Spam / Scam', <AdminBadge text="Medium" color="amber" />, '6h ago'],
            ['R-104', 'Comment', 'Offensive reply in forum', 'David Njoroge', 'Offensive Content', <AdminBadge text="Medium" color="amber" />, '8h ago'],
            ['R-103', 'Post', 'Misleading study tips post', 'Faith Njeri', 'Misinformation', <AdminBadge text="Low" color="gray" />, '1d ago'],
            ['R-102', 'Document', 'Duplicate upload of same notes', 'James Kariuki', 'Duplicate', <AdminBadge text="Low" color="gray" />, '1d ago'],
            ['R-101', 'User', 'Suspected spam account', 'System (Auto)', 'Bot Activity', <AdminBadge text="Low" color="gray" />, '2d ago'],
          ]}
          actions={() => (
            <div style={{ display: 'flex', gap: 5 }}>
              <button style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Dismiss</button>
              <button style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Remove</button>
              <button style={{ background: '#FEF3C7', color: '#D97706', border: 'none', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Warn</button>
            </div>
          )}
        />
      </AdminCard>
    </div>
  )

  if (section === 'analytics') return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <AdminCard title="Student Growth — 7 Months">
          <div style={{ padding: '16px 18px' }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: N.navy, marginBottom: 4 }}>+54% <span style={{ fontSize: 13, color: '#9CA3AF', fontWeight: 500 }}>growth this semester</span></div>
            <AdminLineChart data={studentsData} color={N.navy} height={80} />
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
              {revLabels.map(l => <span key={l} style={{ fontSize: 10, color: '#D1D5DB' }}>{l}</span>)}
            </div>
          </div>
        </AdminCard>
        <AdminCard title="Revenue Growth — 7 Months">
          <div style={{ padding: '16px 18px' }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: '#16A34A', marginBottom: 4 }}>KES 807K <span style={{ fontSize: 13, color: '#9CA3AF', fontWeight: 500 }}>total 7-month</span></div>
            <AdminLineChart data={revenueData} color="#16A34A" height={80} />
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
              {revLabels.map(l => <span key={l} style={{ fontSize: 10, color: '#D1D5DB' }}>{l}</span>)}
            </div>
          </div>
        </AdminCard>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <AdminCard title="Document Uploads — 14 Days">
          <div style={{ padding: '16px 18px' }}><AdminBarChart data={uploadsData} height={80} color="#4C7BC9" /></div>
        </AdminCard>
        <AdminCard title="AI Requests — 7 Days">
          <div style={{ padding: '16px 18px' }}><AdminBarChart data={aiData} labels={aiLabels} height={80} color="#7C3AED" /></div>
        </AdminCard>
      </div>
      <AdminCard title="Top Universities by Engagement">
        <AdminTable
          cols={['University', 'Students', 'Documents', 'AI Requests', 'Premium Users', 'Engagement']}
          rows={[
            ['Kenyatta University', '843', '4,102', '28,441', '287', <AdminBadge text="Very High" color="green" />],
            ['University of Nairobi', '621', '2,890', '19,882', '194', <AdminBadge text="High" color="green" />],
            ['Strathmore University', '412', '1,744', '13,102', '178', <AdminBadge text="High" color="green" />],
            ['JKUAT', '389', '1,502', '11,441', '134', <AdminBadge text="Medium" color="amber" />],
            ['Mount Kenya University', '334', '1,203', '9,812', '87', <AdminBadge text="Medium" color="amber" />],
            ['Daystar University', '248', '891', '7,102', '63', <AdminBadge text="Medium" color="amber" />],
          ]}
        />
      </AdminCard>
    </div>
  )

  if (section === 'system') return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
        {[
          { label: 'API Gateway', status: 'Operational', uptime: '99.98%', color: 'green', ping: '12ms' },
          { label: 'AI Service (Claude)', status: 'Operational', uptime: '99.91%', color: 'green', ping: '1.4s avg' },
          { label: 'M-Pesa API', status: 'Operational', uptime: '99.85%', color: 'green', ping: '340ms' },
          { label: 'Email (SendGrid)', status: 'Degraded', uptime: '97.20%', color: 'amber', ping: '—' },
          { label: 'File Storage (S3)', status: 'Operational', uptime: '100%', color: 'green', ping: '28ms' },
          { label: 'Database (Postgres)', status: 'Operational', uptime: '99.99%', color: 'green', ping: '4ms' },
          { label: 'Auth Service', status: 'Operational', uptime: '99.97%', color: 'green', ping: '18ms' },
          { label: 'Push Notifications', status: 'Operational', uptime: '99.76%', color: 'green', ping: '89ms' },
        ].map(s => (
          <div key={s.label} style={{ background: '#fff', borderRadius: 14, padding: '14px 16px', border: '1px solid rgba(0,0,0,0.05)', boxShadow: '0 1px 4px rgba(0,0,0,0.06)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <span style={{ fontSize: 12, fontWeight: 700, color: N.navy }}>{s.label}</span>
              <AdminBadge text={s.status} color={s.color} />
            </div>
            <div style={{ display: 'flex', gap: 12 }}>
              <div><div style={{ fontSize: 10, color: '#9CA3AF' }}>Uptime</div><div style={{ fontSize: 14, fontWeight: 700, color: '#16A34A' }}>{s.uptime}</div></div>
              <div><div style={{ fontSize: 10, color: '#9CA3AF' }}>Response</div><div style={{ fontSize: 14, fontWeight: 700, color: N.navy }}>{s.ping}</div></div>
            </div>
          </div>
        ))}
      </div>
      <AdminCard title="System Resources">
        <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {[
            { label: 'Storage', used: 342, total: 1024, unit: 'GB', color: N.gold },
            { label: 'Database', used: 18, total: 100, unit: 'GB', color: '#7C3AED' },
            { label: 'API Credits (MTD)', used: 84, total: 200, unit: 'M tokens', color: '#4C7BC9' },
            { label: 'CPU (average)', used: 34, total: 100, unit: '%', color: '#4CC97B' },
          ].map(r => (
            <div key={r.label}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: N.navy }}>{r.label}</span>
                <span style={{ fontSize: 12, color: '#9CA3AF' }}>{r.used} / {r.total} {r.unit}</span>
              </div>
              <div style={{ background: '#F3F4F6', borderRadius: 99, height: 8 }}>
                <div style={{ background: r.color, borderRadius: 99, height: 8, width: `${(r.used / r.total) * 100}%`, transition: 'width 0.5s' }} />
              </div>
            </div>
          ))}
        </div>
      </AdminCard>
      <AdminCard title="Admin Accounts">
        <AdminTable
          cols={['Name', 'Email', 'Role', 'Last Login', 'Status']}
          rows={[
            ['Prepza Admin', 'admin@prepza.co', 'Super Admin', 'Aug 10, 2025 09:14', <AdminBadge text="Active" color="green" />],
            ['Content Lead', 'content@prepza.co', 'Content Manager', 'Aug 9, 2025 14:22', <AdminBadge text="Active" color="green" />],
            ['Support Lead', 'support@prepza.co', 'Support', 'Aug 8, 2025 11:05', <AdminBadge text="Active" color="green" />],
          ]}
          actions={() => <button style={{ background: '#F3F4F6', color: '#374151', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Edit</button>}
        />
      </AdminCard>
    </div>
  )

  if (section === 'ambassadors') return <AdminAmbassadorsPanel />

  if (section === 'communications') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <AdminCard title="Send Announcement">
          <div style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <input value={annTitle} onChange={e => setAnnTitle(e.target.value)} placeholder="Announcement title…" maxLength={200} style={{ border: '1.5px solid #E5E7EB', borderRadius: 10, padding: '10px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy }} />
            <textarea value={annBody} onChange={e => setAnnBody(e.target.value)} placeholder="Write your message…" rows={4} maxLength={500} style={{ border: '1.5px solid #E5E7EB', borderRadius: 10, padding: '10px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, resize: 'none', lineHeight: 1.6 }} />

            <div style={{ fontSize: 11, fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 4 }}>Audience (leave blank for everyone)</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 10 }}>
              <select value={annUniversityId ?? ''} onChange={e => setAnnUniversityId(e.target.value ? Number(e.target.value) : null)} style={{ border: '1.5px solid #E5E7EB', borderRadius: 10, padding: '9px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', color: N.navy, background: '#fff' }}>
                <option value="">All universities</option>
                {annUniversities.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
              </select>
              <select value={annProgramId ?? ''} onChange={e => setAnnProgramId(e.target.value ? Number(e.target.value) : null)} disabled={!annUniversityId} style={{ border: '1.5px solid #E5E7EB', borderRadius: 10, padding: '9px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', color: N.navy, background: '#fff', opacity: annUniversityId ? 1 : 0.5 }}>
                <option value="">All courses</option>
                {annPrograms.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <select value={annYear ?? ''} onChange={e => setAnnYear(e.target.value ? Number(e.target.value) : null)} style={{ border: '1.5px solid #E5E7EB', borderRadius: 10, padding: '9px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', color: N.navy, background: '#fff' }}>
                <option value="">All years</option>
                {[1,2,3,4].map(y => <option key={y} value={y}>Year {y}</option>)}
              </select>
              <select value={annSemester ?? ''} onChange={e => setAnnSemester(e.target.value ? Number(e.target.value) : null)} style={{ border: '1.5px solid #E5E7EB', borderRadius: 10, padding: '9px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', color: N.navy, background: '#fff' }}>
                <option value="">All semesters</option>
                {[1,2].map(s => <option key={s} value={s}>Semester {s}</option>)}
              </select>
            </div>

            <div>
              {annGroupId ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: `${N.gold}15`, border: `1px solid ${N.gold}40`, borderRadius: 10, padding: '8px 12px' }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: N.navy, flex: 1 }}>Group: {annGroupName}</span>
                  <button onClick={() => { setAnnGroupId(null); setAnnGroupName('') }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9CA3AF', fontSize: 14 }}>×</button>
                </div>
              ) : (
                <div style={{ position: 'relative' }}>
                  <input value={annGroupSearch} onChange={e => setAnnGroupSearch(e.target.value)} placeholder="Or search a specific group…" style={{ width: '100%', border: '1.5px solid #E5E7EB', borderRadius: 10, padding: '9px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, boxSizing: 'border-box' }} />
                  {annGroupResults.length > 0 && (
                    <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, background: '#fff', border: '1px solid #E5E7EB', borderRadius: 10, marginTop: 4, boxShadow: '0 4px 16px rgba(0,0,0,0.08)', zIndex: 10, maxHeight: 180, overflowY: 'auto' }}>
                      {annGroupResults.map(g => (
                        <button key={g.id} onClick={() => { setAnnGroupId(g.id); setAnnGroupName(g.name); setAnnGroupSearch(''); setAnnGroupResults([]) }} style={{ display: 'block', width: '100%', padding: '10px 12px', background: 'none', border: 'none', textAlign: 'left', cursor: 'pointer', fontSize: 13, fontFamily: 'Plus Jakarta Sans', color: N.navy }}>{g.name}</button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {annError && <div style={{ color: '#DC2626', fontSize: 12, fontWeight: 600 }}>{annError}</div>}
            {annSent && <div style={{ color: '#16A34A', fontSize: 12, fontWeight: 600 }}>Announcement sent.</div>}

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={sendAnnouncement} disabled={annSending || !annTitle.trim() || !annBody.trim()} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, border: 'none', borderRadius: 10, padding: '8px 20px', cursor: annSending ? 'wait' : 'pointer', fontWeight: 800, fontSize: 13, fontFamily: 'Plus Jakarta Sans', opacity: (!annTitle.trim() || !annBody.trim()) ? 0.5 : 1 }}>{annSending ? 'Sending…' : 'Send Now'}</button>
            </div>
          </div>
          <div style={{ borderTop: '1px solid #F3F4F6' }}>
            {announcementsLoading ? (
              <div style={{ padding: '18px 20px', fontSize: 12, color: '#9CA3AF' }}>Loading…</div>
            ) : announcements.length === 0 ? (
              <div style={{ padding: '18px 20px', fontSize: 12, color: '#9CA3AF' }}>No announcements sent yet.</div>
            ) : announcements.map((a, i) => (
              <div key={a.id} style={{ padding: '14px 20px', borderBottom: i < announcements.length - 1 ? '1px solid #F3F4F6' : 'none', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13, color: N.navy }}>{a.title}</div>
                  <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>{a.body}</div>
                  <div style={{ fontSize: 11, color: '#D1D5DB', marginTop: 4 }}>{a.created_at ? new Date(a.created_at).toLocaleString() : ''} · Reached {a.reach} students</div>
                </div>
                <AdminBadge text="Sent" color="green" />
              </div>
            ))}
          </div>
        </AdminCard>
      </div>
    )
  }

  if (section === 'opportunities') return <AdminOpportunitiesPanel />

  if (section === 'organisations') return <AdminOrganisationsPanel />

  // Light sections for community, universities, opportunities
  const lightSections: Record<string, { icon: string; title: string; desc: string; features: string[] }> = {
    universities: { icon: '🏛️', title: 'University Management', desc: 'Manage universities, faculties, departments, courses, and units.', features: ['Kenyatta University — 843 students','University of Nairobi — 621 students','Strathmore University — 412 students','JKUAT — 389 students','Mount Kenya University — 334 students'] },
    community: { icon: '💬', title: 'Community Moderation', desc: 'Manage forum posts, comments, reports, and community health.', features: ['1,247 total posts','127 comments today','7 pending reports','0 active suspensions'] },
    opportunities: { icon: '🚀', title: 'Opportunities Management', desc: 'Create, approve, feature, and archive opportunities for students.', features: ['48 active opportunities','12 pending approval','3 featured','5 expiring this week'] },
  }
  if (lightSections[section]) {
    const s = lightSections[section]
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ background: '#fff', borderRadius: 16, padding: '24px 28px', boxShadow: '0 1px 4px rgba(0,0,0,0.06)', border: '1px solid rgba(0,0,0,0.05)' }}>
          <div style={{ fontSize: 40, marginBottom: 14 }}>{s.icon}</div>
          <div style={{ fontWeight: 800, fontSize: 22, color: N.navy, marginBottom: 8 }}>{s.title}</div>
          <div style={{ fontSize: 14, color: '#6B7280', lineHeight: 1.7, marginBottom: 20 }}>{s.desc}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {s.features.map((f, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center', background: '#F9FAFB', borderRadius: 10, padding: '10px 14px' }}>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: N.gold, flexShrink: 0 }} />
                <span style={{ fontSize: 13, color: N.navy, fontWeight: 500 }}>{f}</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 20, padding: '14px 16px', background: `${N.gold}10`, border: `1px solid ${N.gold}30`, borderRadius: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: N.gold }}>Full implementation in progress</div>
            <div style={{ fontSize: 12, color: '#6B7280', marginTop: 4 }}>This section is live and will be expanded with full CRUD interfaces in the next sprint.</div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, color: '#9CA3AF', fontSize: 14 }}>Select a section from the sidebar</div>
  )
}

// ─── ADMIN: AMBASSADORS (Chunk 9 admin review) ──────────────────────────────
// Self-contained admin panel: fetches from GET/POST /admin/ambassadors* and
// /admin/payouts* (see app.py). Owns all its own hooks so it can be dropped
// into a section branch without touching AdminSection's existing state.

interface AdminAmbassadorRow {
  id: number
  user_id: number
  email: string | null
  display_name: string | null
  referral_code: string
  status: 'pending' | 'active' | 'suspended' | 'rejected'
  applied_at: string | null
  reviewed_at: string | null
  rejection_reason: string | null
}

interface AdminAmbassadorReferralRow {
  id: number
  referred_email: string | null
  status: string
  channel: string | null
  converted: boolean
  commission_amount: number | null
  unlock_at: string | null
  voided: boolean
  void_reason: string | null
  created_at: string | null
}

interface AdminAmbassadorDetail extends AdminAmbassadorRow {
  reviewed_by: number | null
  referred_count: number
  paying_count: number
  total_commission_awarded_kes: number
  total_paid_kes: number
  referrals: AdminAmbassadorReferralRow[]
}

interface AdminPayoutRow {
  id: number
  ambassador_id: number
  email: string | null
  amount: number
  status: 'pending' | 'approved' | 'rejected' | 'paid'
  payout_destination: string
  kasapay_reference: string | null
  requested_at: string | null
  reviewed_at: string | null
  rejection_reason: string | null
  paid_at: string | null
}

const ADMIN_AMB_STATUS_COLOR: Record<string, string> = {
  pending: 'amber', active: 'green', suspended: 'red', rejected: 'gray',
  approved: 'blue', paid: 'green',
}

function AdminAmbassadorsPanel() {
  const [tab, setTab] = useState<'applications' | 'payouts'>('applications')
  const [csrfToken, setCsrfToken] = useState('')

  const [appStatusFilter, setAppStatusFilter] = useState('pending')
  const [applications, setApplications] = useState<AdminAmbassadorRow[]>([])
  const [loadingApps, setLoadingApps] = useState(true)
  const [appsError, setAppsError] = useState('')

  const [selected, setSelected] = useState<AdminAmbassadorDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  const [payoutStatusFilter, setPayoutStatusFilter] = useState('pending')
  const [payouts, setPayouts] = useState<AdminPayoutRow[]>([])
  const [loadingPayouts, setLoadingPayouts] = useState(true)
  const [payoutsError, setPayoutsError] = useState('')

  const [actionBusy, setActionBusy] = useState(false)
  const [rejectTarget, setRejectTarget] = useState<{ kind: 'ambassador' | 'payout'; id: number } | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
  }, [])

  const loadApplications = (status: string) => {
    setLoadingApps(true)
    setAppsError('')
    api<{ ambassadors: AdminAmbassadorRow[] }>(`/admin/ambassadors${status === 'all' ? '' : `?status=${status}`}`)
      .then(res => setApplications(res.ambassadors))
      .catch(e => setAppsError(e instanceof ApiError ? e.message : 'Could not load ambassador applications.'))
      .finally(() => setLoadingApps(false))
  }

  const loadPayouts = (status: string) => {
    setLoadingPayouts(true)
    setPayoutsError('')
    api<{ payouts: AdminPayoutRow[] }>(`/admin/payouts${status === 'all' ? '' : `?status=${status}`}`)
      .then(res => setPayouts(res.payouts))
      .catch(e => setPayoutsError(e instanceof ApiError ? e.message : 'Could not load payout requests.'))
      .finally(() => setLoadingPayouts(false))
  }

  useEffect(() => { loadApplications(appStatusFilter) }, [appStatusFilter])
  useEffect(() => { loadPayouts(payoutStatusFilter) }, [payoutStatusFilter])

  const openDetail = (id: number) => {
    setLoadingDetail(true)
    api<AdminAmbassadorDetail>(`/admin/ambassadors/${id}`)
      .then(setSelected)
      .catch(e => alert(e instanceof ApiError ? e.message : 'Could not load ambassador detail.'))
      .finally(() => setLoadingDetail(false))
  }

  const runAmbassadorAction = async (id: number, action: 'approve' | 'suspend' | 'reinstate') => {
    setActionBusy(true)
    try {
      await api(`/admin/ambassadors/${id}/${action}`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
      })
      loadApplications(appStatusFilter)
      if (selected?.id === id) openDetail(id)
    } catch (e) {
      alert(e instanceof ApiError ? e.message : `Could not ${action} this ambassador.`)
    } finally {
      setActionBusy(false)
    }
  }

  const rejectAmbassador = async (id: number, reason: string) => {
    setActionBusy(true)
    try {
      await api(`/admin/ambassadors/${id}/reject`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ reason }),
      })
      loadApplications(appStatusFilter)
      setSelected(null)
      setRejectTarget(null)
      setRejectReason('')
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not reject this ambassador.')
    } finally {
      setActionBusy(false)
    }
  }

  const approvePayout = async (id: number) => {
    setActionBusy(true)
    try {
      await api(`/admin/payouts/${id}/approve`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
      })
      loadPayouts(payoutStatusFilter)
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not approve this payout.')
    } finally {
      setActionBusy(false)
    }
  }

  const rejectPayout = async (id: number, reason: string) => {
    setActionBusy(true)
    try {
      await api(`/admin/payouts/${id}/reject`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ reason }),
      })
      loadPayouts(payoutStatusFilter)
      setRejectTarget(null)
      setRejectReason('')
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not reject this payout.')
    } finally {
      setActionBusy(false)
    }
  }

  const submitReject = () => {
    if (!rejectTarget || !rejectReason.trim()) return
    if (rejectTarget.kind === 'ambassador') rejectAmbassador(rejectTarget.id, rejectReason.trim())
    else rejectPayout(rejectTarget.id, rejectReason.trim())
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', gap: 6 }}>
        {(['applications', 'payouts'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{ padding: '8px 18px', borderRadius: 10, background: tab === t ? N.navy : '#F3F4F6', color: tab === t ? '#fff' : '#6B7280', border: 'none', cursor: 'pointer', fontWeight: 700, fontSize: 12, fontFamily: 'Plus Jakarta Sans' }}>
            {t === 'applications' ? 'Applications' : 'Payout Requests'}
          </button>
        ))}
      </div>

      {tab === 'applications' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {selected && (
            <div style={{ background: '#fff', borderRadius: 14, padding: 20, boxShadow: '0 1px 4px rgba(0,0,0,0.06)', border: '1px solid rgba(0,0,0,0.05)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                <div>
                  <div style={{ fontWeight: 800, fontSize: 16, color: N.navy }}>{selected.display_name || selected.email}</div>
                  <div style={{ fontSize: 12, color: '#6B7280', marginTop: 2 }}>{selected.email} · code {selected.referral_code}</div>
                  <div style={{ marginTop: 6 }}><AdminBadge text={selected.status} color={ADMIN_AMB_STATUS_COLOR[selected.status] || 'gray'} /></div>
                </div>
                <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9CA3AF', fontSize: 20 }}>×</button>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, marginBottom: 16 }}>
                {[['Referred', selected.referred_count.toString()], ['Paying', selected.paying_count.toString()], ['Commission Awarded', 'KES ' + selected.total_commission_awarded_kes.toLocaleString()], ['Paid Out', 'KES ' + selected.total_paid_kes.toLocaleString()]].map(([k, v]) => (
                  <div key={k} style={{ background: '#F9FAFB', borderRadius: 10, padding: '10px 12px' }}>
                    <div style={{ fontSize: 10, color: '#9CA3AF', fontWeight: 600, marginBottom: 3 }}>{k}</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: N.navy }}>{v}</div>
                  </div>
                ))}
              </div>
              {selected.status === 'pending' && (
                <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                  <button disabled={actionBusy} onClick={() => runAmbassadorAction(selected.id, 'approve')} style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 10, padding: '8px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 12 }}>Approve</button>
                  <button disabled={actionBusy} onClick={() => setRejectTarget({ kind: 'ambassador', id: selected.id })} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 10, padding: '8px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 12 }}>Reject</button>
                </div>
              )}
              {selected.status === 'active' && (
                <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                  <button disabled={actionBusy} onClick={() => runAmbassadorAction(selected.id, 'suspend')} style={{ background: '#FEF3C7', color: '#D97706', border: 'none', borderRadius: 10, padding: '8px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 12 }}>Suspend</button>
                </div>
              )}
              {selected.status === 'suspended' && (
                <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                  <button disabled={actionBusy} onClick={() => runAmbassadorAction(selected.id, 'reinstate')} style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 10, padding: '8px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 12 }}>Reinstate</button>
                </div>
              )}
              {selected.rejection_reason && (
                <div style={{ fontSize: 12, color: '#DC2626', marginBottom: 12 }}>Rejection reason: {selected.rejection_reason}</div>
              )}
              <div style={{ fontWeight: 700, fontSize: 12, color: N.navy, marginBottom: 8 }}>Referrals ({selected.referrals.length})</div>
              {selected.referrals.length === 0 ? (
                <div style={{ fontSize: 12, color: '#9CA3AF' }}>No referrals yet.</div>
              ) : (
                <AdminTable
                  cols={['Referred', 'Status', 'Commission', 'Voided']}
                  rows={selected.referrals.map(r => [
                    r.referred_email || `#${r.id}`,
                    r.status,
                    r.commission_amount != null ? 'KES ' + r.commission_amount.toLocaleString() : '—',
                    r.voided ? (r.void_reason || 'Yes') : 'No',
                  ])}
                />
              )}
            </div>
          )}

          <AdminCard title={`Ambassador Applications — ${applications.length}`}>
            <div style={{ padding: '12px 18px', borderBottom: '1px solid #F3F4F6', display: 'flex', gap: 6 }}>
              {['pending', 'active', 'suspended', 'rejected', 'all'].map(f => (
                <button key={f} onClick={() => setAppStatusFilter(f)} style={{ padding: '7px 14px', borderRadius: 8, background: appStatusFilter === f ? N.navy : '#F3F4F6', color: appStatusFilter === f ? '#fff' : '#6B7280', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans', textTransform: 'capitalize' }}>{f}</button>
              ))}
            </div>
            {loadingApps ? (
              <div style={{ padding: 24, textAlign: 'center', color: '#9CA3AF', fontSize: 13 }}>Loading…</div>
            ) : appsError ? (
              <div style={{ padding: 24, textAlign: 'center', color: '#C94C4C', fontSize: 13 }}>{appsError}</div>
            ) : applications.length === 0 ? (
              <div style={{ padding: 24, textAlign: 'center', color: '#9CA3AF', fontSize: 13 }}>No applications with this status.</div>
            ) : (
              <AdminTable
                cols={['Name', 'Email', 'Code', 'Applied', 'Status']}
                rows={applications.map(a => [
                  a.display_name || '—', a.email || '—', a.referral_code,
                  a.applied_at ? new Date(a.applied_at).toLocaleDateString() : '—',
                  <AdminBadge text={a.status} color={ADMIN_AMB_STATUS_COLOR[a.status] || 'gray'} />,
                ])}
                actions={i => (
                  <button onClick={() => openDetail(applications[i].id)} style={{ background: '#F3F4F6', color: '#374151', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>{loadingDetail ? '…' : 'Review'}</button>
                )}
              />
            )}
          </AdminCard>
        </div>
      )}

      {tab === 'payouts' && (
        <AdminCard title={`Payout Requests — ${payouts.length}`}>
          <div style={{ padding: '12px 18px', borderBottom: '1px solid #F3F4F6', display: 'flex', gap: 6 }}>
            {['pending', 'approved', 'paid', 'rejected', 'all'].map(f => (
              <button key={f} onClick={() => setPayoutStatusFilter(f)} style={{ padding: '7px 14px', borderRadius: 8, background: payoutStatusFilter === f ? N.navy : '#F3F4F6', color: payoutStatusFilter === f ? '#fff' : '#6B7280', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans', textTransform: 'capitalize' }}>{f}</button>
            ))}
          </div>
          {loadingPayouts ? (
            <div style={{ padding: 24, textAlign: 'center', color: '#9CA3AF', fontSize: 13 }}>Loading…</div>
          ) : payoutsError ? (
            <div style={{ padding: 24, textAlign: 'center', color: '#C94C4C', fontSize: 13 }}>{payoutsError}</div>
          ) : payouts.length === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', color: '#9CA3AF', fontSize: 13 }}>No payout requests with this status.</div>
          ) : (
            <AdminTable
              cols={['Email', 'Amount', 'Destination', 'Requested', 'Status']}
              rows={payouts.map(p => [
                p.email || `#${p.ambassador_id}`,
                'KES ' + p.amount.toLocaleString(),
                p.payout_destination,
                p.requested_at ? new Date(p.requested_at).toLocaleDateString() : '—',
                <AdminBadge text={p.status} color={ADMIN_AMB_STATUS_COLOR[p.status] || 'gray'} />,
              ])}
              actions={i => payouts[i].status === 'pending' ? (
                <div style={{ display: 'flex', gap: 5, justifyContent: 'flex-end' }}>
                  <button disabled={actionBusy} onClick={() => approvePayout(payouts[i].id)} style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Approve</button>
                  <button disabled={actionBusy} onClick={() => setRejectTarget({ kind: 'payout', id: payouts[i].id })} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Reject</button>
                </div>
              ) : null}
            />
          )}
        </AdminCard>
      )}

      {rejectTarget && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setRejectTarget(null)}>
          <div style={{ background: '#fff', borderRadius: 16, padding: 24, maxWidth: 380, width: '90%' }} onClick={e => e.stopPropagation()}>
            <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 10 }}>Reason for rejection</div>
            <textarea value={rejectReason} onChange={e => setRejectReason(e.target.value)} rows={3} placeholder="Explain why this is being rejected…" style={{ width: '100%', boxSizing: 'border-box', border: '1.5px solid rgba(0,0,0,0.12)', borderRadius: 12, padding: '10px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', resize: 'none', marginBottom: 14 }} />
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => { setRejectTarget(null); setRejectReason('') }} style={{ flex: 1, background: '#F3F4F6', color: '#374151', border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 13 }}>Cancel</button>
              <button disabled={actionBusy || !rejectReason.trim()} onClick={submitReject} style={{ flex: 1, background: '#DC2626', color: '#fff', border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, opacity: (actionBusy || !rejectReason.trim()) ? 0.6 : 1 }}>Confirm Reject</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── ADMIN: OPPORTUNITIES REVIEW (Chunk 9 continued) ────────────────────────

interface AdminOpportunityRow {
  id: number
  organisation_id: number
  organisation_name: string | null
  organisation_verification_status: string | null
  organisation_is_active: boolean | null
  title: string
  opportunity_type: string
  location: string | null
  is_remote: boolean
  application_deadline: string | null
  expiry_date: string | null
  status: string
  rejection_reason: string | null
  submitted_at: string | null
  created_at: string | null
}

const ADMIN_OPP_STATUS_COLOR: Record<string, string> = {
  draft: 'gray', pending_review: 'amber', approved: 'blue', rejected: 'red',
  published: 'green', expired: 'gray', archived: 'gray', removed: 'red',
}

function AdminOpportunitiesPanel() {
  const [csrfToken, setCsrfToken] = useState('')
  const [statusFilter, setStatusFilter] = useState('pending_review')
  const [rows, setRows] = useState<AdminOpportunityRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionBusy, setActionBusy] = useState(false)
  const [reasonTarget, setReasonTarget] = useState<{ kind: 'reject' | 'remove'; id: number } | null>(null)
  const [reasonText, setReasonText] = useState('')

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
  }, [])

  const load = (status: string) => {
    setLoading(true)
    setError('')
    api<{ opportunities: AdminOpportunityRow[] }>(`/admin/opportunities?status=${status}`)
      .then(res => setRows(res.opportunities))
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load opportunities.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load(statusFilter) }, [statusFilter])

  const runAction = async (id: number, action: 'approve' | 'publish' | 'archive') => {
    setActionBusy(true)
    try {
      await api(`/admin/opportunities/${id}/${action}`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      load(statusFilter)
    } catch (e) {
      alert(e instanceof ApiError ? e.message : `Could not ${action} this opportunity.`)
    } finally {
      setActionBusy(false)
    }
  }

  const submitReason = async () => {
    if (!reasonTarget) return
    if (reasonTarget.kind === 'reject' && !reasonText.trim()) return
    setActionBusy(true)
    try {
      const path = reasonTarget.kind === 'reject'
        ? `/admin/opportunities/${reasonTarget.id}/reject`
        : `/admin/opportunities/${reasonTarget.id}/remove`
      await api(path, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ reason: reasonText.trim() || undefined }),
      })
      load(statusFilter)
      setReasonTarget(null)
      setReasonText('')
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not complete this action.')
    } finally {
      setActionBusy(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <AdminCard title={`Opportunities — ${rows.length}`}>
        <div style={{ padding: '12px 18px', borderBottom: '1px solid #F3F4F6', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {['pending_review', 'approved', 'published', 'rejected', 'expired', 'archived', 'removed', 'all'].map(f => (
            <button key={f} onClick={() => setStatusFilter(f)} style={{ padding: '7px 14px', borderRadius: 8, background: statusFilter === f ? N.navy : '#F3F4F6', color: statusFilter === f ? '#fff' : '#6B7280', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans', textTransform: 'capitalize' }}>{f.replace('_', ' ')}</button>
          ))}
        </div>
        {loading ? (
          <div style={{ padding: 24, textAlign: 'center', color: '#9CA3AF', fontSize: 13 }}>Loading…</div>
        ) : error ? (
          <div style={{ padding: 24, textAlign: 'center', color: '#C94C4C', fontSize: 13 }}>{error}</div>
        ) : rows.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: '#9CA3AF', fontSize: 13 }}>No opportunities with this status.</div>
        ) : (
          <AdminTable
            cols={['Title', 'Organisation', 'Type', 'Deadline', 'Status']}
            rows={rows.map(r => [
              r.title,
              r.organisation_name || `#${r.organisation_id}`,
              r.opportunity_type,
              r.application_deadline ? new Date(r.application_deadline).toLocaleDateString() : '—',
              <AdminBadge text={r.status.replace('_', ' ')} color={ADMIN_OPP_STATUS_COLOR[r.status] || 'gray'} />,
            ])}
            actions={i => {
              const r = rows[i]
              return (
                <div style={{ display: 'flex', gap: 5, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                  {r.status === 'pending_review' && (
                    <>
                      <button disabled={actionBusy} onClick={() => runAction(r.id, 'approve')} style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Approve</button>
                      <button disabled={actionBusy} onClick={() => setReasonTarget({ kind: 'reject', id: r.id })} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Reject</button>
                    </>
                  )}
                  {r.status === 'approved' && (
                    <button disabled={actionBusy} onClick={() => runAction(r.id, 'publish')} style={{ background: '#DBEAFE', color: '#2563EB', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Publish</button>
                  )}
                  {(r.status === 'approved' || r.status === 'published' || r.status === 'expired') && (
                    <button disabled={actionBusy} onClick={() => runAction(r.id, 'archive')} style={{ background: '#F3F4F6', color: '#6B7280', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Archive</button>
                  )}
                  {r.status !== 'removed' && (
                    <button disabled={actionBusy} onClick={() => setReasonTarget({ kind: 'remove', id: r.id })} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Remove</button>
                  )}
                </div>
              )
            }}
          />
        )}
      </AdminCard>

      {reasonTarget && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setReasonTarget(null)}>
          <div style={{ background: '#fff', borderRadius: 16, padding: 24, maxWidth: 380, width: '90%' }} onClick={e => e.stopPropagation()}>
            <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 10 }}>{reasonTarget.kind === 'reject' ? 'Reason for rejection' : 'Reason for removal (optional)'}</div>
            <textarea value={reasonText} onChange={e => setReasonText(e.target.value)} rows={3} placeholder="Explain why…" style={{ width: '100%', boxSizing: 'border-box', border: '1.5px solid rgba(0,0,0,0.12)', borderRadius: 12, padding: '10px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', resize: 'none', marginBottom: 14 }} />
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => { setReasonTarget(null); setReasonText('') }} style={{ flex: 1, background: '#F3F4F6', color: '#374151', border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 13 }}>Cancel</button>
              <button disabled={actionBusy || (reasonTarget.kind === 'reject' && !reasonText.trim())} onClick={submitReason} style={{ flex: 1, background: '#DC2626', color: '#fff', border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, opacity: (actionBusy || (reasonTarget.kind === 'reject' && !reasonText.trim())) ? 0.6 : 1 }}>Confirm</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── ADMIN: ORGANISATIONS VERIFICATION (Chunk 9 continued) ──────────────────

interface AdminOrganisationRow {
  id: number
  name: string
  contact_email: string
  contact_phone: string | null
  website: string | null
  verification_status: 'pending' | 'verified' | 'rejected'
  verification_notes: string | null
  is_active: boolean
  owner_email: string | null
  created_at: string | null
}

const ADMIN_ORG_STATUS_COLOR: Record<string, string> = {
  pending: 'amber', verified: 'green', rejected: 'red',
}

function AdminOrganisationsPanel() {
  const [csrfToken, setCsrfToken] = useState('')
  const [statusFilter, setStatusFilter] = useState('pending')
  const [rows, setRows] = useState<AdminOrganisationRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionBusy, setActionBusy] = useState(false)
  const [rejectTarget, setRejectTarget] = useState<number | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
  }, [])

  const load = (status: string) => {
    setLoading(true)
    setError('')
    const qs = status === 'all' ? '' : `?verification_status=${status}`
    api<{ organisations: AdminOrganisationRow[] }>(`/admin/organisations${qs}`)
      .then(res => setRows(res.organisations))
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load organisations.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load(statusFilter) }, [statusFilter])

  const verify = async (id: number) => {
    setActionBusy(true)
    try {
      await api(`/admin/organisations/${id}/verify`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      load(statusFilter)
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not verify this organisation.')
    } finally {
      setActionBusy(false)
    }
  }

  const submitReject = async () => {
    if (rejectTarget == null || !rejectReason.trim()) return
    setActionBusy(true)
    try {
      await api(`/admin/organisations/${rejectTarget}/reject`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ reason: rejectReason.trim() }),
      })
      load(statusFilter)
      setRejectTarget(null)
      setRejectReason('')
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not reject this organisation.')
    } finally {
      setActionBusy(false)
    }
  }

  const toggleActive = async (id: number, nextActive: boolean) => {
    setActionBusy(true)
    try {
      await api(`/admin/organisations/${id}`, {
        method: 'PATCH',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ is_active: nextActive }),
      })
      load(statusFilter)
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not update this organisation.')
    } finally {
      setActionBusy(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <AdminCard title={`Organisations — ${rows.length}`}>
        <div style={{ padding: '12px 18px', borderBottom: '1px solid #F3F4F6', display: 'flex', gap: 6 }}>
          {['pending', 'verified', 'rejected', 'all'].map(f => (
            <button key={f} onClick={() => setStatusFilter(f)} style={{ padding: '7px 14px', borderRadius: 8, background: statusFilter === f ? N.navy : '#F3F4F6', color: statusFilter === f ? '#fff' : '#6B7280', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans', textTransform: 'capitalize' }}>{f}</button>
          ))}
        </div>
        {loading ? (
          <div style={{ padding: 24, textAlign: 'center', color: '#9CA3AF', fontSize: 13 }}>Loading…</div>
        ) : error ? (
          <div style={{ padding: 24, textAlign: 'center', color: '#C94C4C', fontSize: 13 }}>{error}</div>
        ) : rows.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: '#9CA3AF', fontSize: 13 }}>No organisations with this status.</div>
        ) : (
          <AdminTable
            cols={['Name', 'Contact', 'Owner', 'Active', 'Status']}
            rows={rows.map(r => [
              r.name,
              r.contact_email,
              r.owner_email || '—',
              r.is_active ? 'Yes' : 'No',
              <AdminBadge text={r.verification_status} color={ADMIN_ORG_STATUS_COLOR[r.verification_status] || 'gray'} />,
            ])}
            actions={i => {
              const r = rows[i]
              return (
                <div style={{ display: 'flex', gap: 5, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                  {r.verification_status !== 'verified' && (
                    <button disabled={actionBusy} onClick={() => verify(r.id)} style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Verify</button>
                  )}
                  {r.verification_status === 'pending' && (
                    <button disabled={actionBusy} onClick={() => setRejectTarget(r.id)} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Reject</button>
                  )}
                  <button disabled={actionBusy} onClick={() => toggleActive(r.id, !r.is_active)} style={{ background: r.is_active ? '#FEF3C7' : '#DBEAFE', color: r.is_active ? '#D97706' : '#2563EB', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>{r.is_active ? 'Deactivate' : 'Activate'}</button>
                </div>
              )
            }}
          />
        )}
      </AdminCard>

      {rejectTarget != null && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setRejectTarget(null)}>
          <div style={{ background: '#fff', borderRadius: 16, padding: 24, maxWidth: 380, width: '90%' }} onClick={e => e.stopPropagation()}>
            <div style={{ fontWeight: 800, fontSize: 16, color: N.navy, marginBottom: 10 }}>Reason for rejection</div>
            <textarea value={rejectReason} onChange={e => setRejectReason(e.target.value)} rows={3} placeholder="Explain why this organisation is being rejected…" style={{ width: '100%', boxSizing: 'border-box', border: '1.5px solid rgba(0,0,0,0.12)', borderRadius: 12, padding: '10px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', resize: 'none', marginBottom: 14 }} />
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => { setRejectTarget(null); setRejectReason('') }} style={{ flex: 1, background: '#F3F4F6', color: '#374151', border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 13 }}>Cancel</button>
              <button disabled={actionBusy || !rejectReason.trim()} onClick={submitReject} style={{ flex: 1, background: '#DC2626', color: '#fff', border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, opacity: (actionBusy || !rejectReason.trim()) ? 0.6 : 1 }}>Confirm Reject</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function AdminPlatform({ onExit }: { onExit: () => void }) {
  const [section, setSection] = useState('dashboard')
  const sectionLabels: Record<string, string> = { dashboard: 'Dashboard', users: 'Users', content: 'Content', universities: 'Universities', community: 'Community', opportunities: 'Opportunities', organisations: 'Organisations', 'ai-usage': 'AI & Usage', payments: 'Payments', communications: 'Communications', analytics: 'Analytics', moderation: 'Moderation', system: 'System' }

  return (
    <div style={{ display: 'flex', width: '100vw', height: '100vh', background: '#F4F6FA', fontFamily: 'Plus Jakarta Sans', overflow: 'hidden' }}>
      {/* Sidebar */}
      <div style={{ width: 220, background: N.navy, display: 'flex', flexDirection: 'column', flexShrink: 0, overflowY: 'auto' }} className="scrollbar-hide">
        <div style={{ padding: '20px 16px 14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <img src={logoImg} alt="Prepza" style={{ width: 32, height: 32, borderRadius: 9 }} />
            <div>
              <div style={{ fontWeight: 800, fontSize: 14, color: '#fff', letterSpacing: '-0.3px' }}>PREPZA</div>
              <div style={{ fontSize: 10, color: N.gold, fontWeight: 600 }}>Admin Platform</div>
            </div>
          </div>
        </div>
        <div style={{ height: 1, background: 'rgba(255,255,255,0.08)', margin: '0 14px 10px' }} />
        <div style={{ flex: 1, padding: '0 8px' }}>
          {adminNav.map(n => {
            const active = section === n.key
            const hasBadge: Record<string, string> = { moderation: '7', content: '23', payments: '14' }
            return (
              <button key={n.key} onClick={() => setSection(n.key)} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 10, background: active ? 'rgba(201,168,76,0.15)' : 'transparent', border: `1px solid ${active ? 'rgba(201,168,76,0.25)' : 'transparent'}`, cursor: 'pointer', marginBottom: 2, transition: 'all 0.15s' }}>
                <span style={{ fontSize: 15 }}>{n.icon}</span>
                <span style={{ flex: 1, fontSize: 13, fontWeight: active ? 700 : 500, color: active ? N.gold : 'rgba(255,255,255,0.65)', textAlign: 'left' }}>{n.label}</span>
                {hasBadge[n.key] && <span style={{ background: '#DC2626', color: '#fff', fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 99 }}>{hasBadge[n.key]}</span>}
              </button>
            )
          })}
        </div>
        <div style={{ padding: '10px 8px 20px' }}>
          <div style={{ height: 1, background: 'rgba(255,255,255,0.08)', margin: '0 6px 10px' }} />
          <div style={{ padding: '10px 12px', display: 'flex', gap: 10, alignItems: 'center' }}>
            <div style={{ width: 32, height: 32, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, color: N.navy, flexShrink: 0 }}>PA</div>
            <div style={{ flex: 1 }}><div style={{ fontSize: 12, fontWeight: 700, color: '#fff' }}>Prepza Admin</div><div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)' }}>Super Admin</div></div>
          </div>
          <button onClick={onExit} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 10, background: 'transparent', border: '1px solid rgba(255,255,255,0.1)', cursor: 'pointer', marginTop: 6 }}>
            <span style={{ fontSize: 14 }}>📱</span>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'rgba(255,255,255,0.5)' }}>Student App</span>
          </button>
        </div>
      </div>

      {/* Main */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
        {/* Top bar */}
        <div style={{ background: '#fff', borderBottom: '1px solid #E5E7EB', padding: '0 24px', height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: 18, color: N.navy }}>{sectionLabels[section]}</div>
            <div style={{ fontSize: 11, color: '#9CA3AF' }}>Prepza Admin · {new Date().toLocaleDateString('en-KE', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</div>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 99, padding: '4px 12px' }}>
              <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#16A34A' }} />
              <span style={{ fontSize: 11, fontWeight: 600, color: '#16A34A' }}>All Systems Operational</span>
            </div>
            <button style={{ width: 36, height: 36, background: '#F3F4F6', border: 'none', borderRadius: 10, cursor: 'pointer', fontSize: 16 }}>🔔</button>
            <div style={{ width: 36, height: 36, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, color: N.navy }}>PA</div>
          </div>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 24 }} className="scrollbar-hide">
          <AdminSection section={section} setSection={setSection} />
        </div>
      </div>
    </div>
  )
}

// ─── APP SHELL ────────────────────────────────────────────────────────────────
// ─── AMBASSADOR PROGRAM ────────────────────────────────────────────────────
// Wired to the live Chunk 9 backend endpoints:
//   GET  /ambassador/status              -> { enrolled, status, referral_code, rejection_reason }
//   GET  /ambassador/dashboard           -> tier/earnings/funnel snapshot
//   GET  /ambassador/referrals           -> { referrals: [...] }
//   GET  /ambassador/payouts             -> { payouts: [...] }
//   POST /ambassador/apply               -> { id, status, referral_code }
//   POST /ambassador/payouts/request     -> { id, amount, status }
// Follows this file's existing per-screen CSRF pattern (fetch /me once on
// mount, store csrf_token in local state, attach it to mutating calls).

const AMB_COLORS = { navy: '#0B1437', navy3: '#1A2A5E', gold: '#C9A84C', goldLight: '#E8C97E', bg: '#F8F9FC', green: '#16A34A', red: '#C94C4C', gray: '#9CA3AF' }

interface AmbassadorStatusResp {
  enrolled: boolean
  status?: 'pending' | 'active' | 'suspended' | 'rejected'
  referral_code?: string
  applied_at?: string
  rejection_reason?: string | null
}
interface AmbassadorDashboardResp {
  referral_code: string
  referral_link: string
  status: 'active' | 'suspended'
  tier: number
  commission_pct: number
  next_tier_at: number | null
  funnel: { referred: number; verified: number; activated: number; paying: number; conversion_rate: number }
  earnings: { pending_kes: number; available_kes: number; paid_kes: number }
  min_payout_kes: number
  payout_hold_days: number
}
interface AmbassadorReferral {
  id: number
  status: 'signed_up' | 'verified' | 'activated'
  channel: string | null
  converted: boolean
  commission_amount: number | null
  voided: boolean
  created_at: string
}
interface AmbassadorPayout {
  id: number
  amount: number
  status: 'pending' | 'approved' | 'rejected' | 'paid'
  payout_destination: string
  requested_at: string
  rejection_reason: string | null
}

const AMB_STATUS_META: Record<string, { label: string; color: string }> = {
  signed_up: { label: 'Signed up', color: AMB_COLORS.gray },
  verified: { label: 'Verified', color: '#4C7BC9' },
  activated: { label: 'Activated', color: AMB_COLORS.green },
}
const AMB_PAYOUT_META: Record<string, { label: string; color: string }> = {
  pending: { label: 'Pending', color: AMB_COLORS.gold },
  approved: { label: 'Approved', color: '#4C7BC9' },
  paid: { label: 'Paid', color: AMB_COLORS.green },
  rejected: { label: 'Rejected', color: AMB_COLORS.red },
}
function amPill(text: string, color: string) {
  return <span style={{ display: 'inline-block', fontSize: 10, fontWeight: 700, color, background: color + '20', border: `1px solid ${color}55`, borderRadius: 99, padding: '2px 9px' }}>{text}</span>
}
function fmtKes(n: number) {
  return 'KES ' + Math.round(n).toLocaleString('en-KE')
}

function AmbassadorScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [csrfToken, setCsrfToken] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [statusData, setStatusData] = useState<AmbassadorStatusResp | null>(null)
  const [dashboard, setDashboard] = useState<AmbassadorDashboardResp | null>(null)
  const [referrals, setReferrals] = useState<AmbassadorReferral[]>([])
  const [payouts, setPayouts] = useState<AmbassadorPayout[]>([])
  const [tab, setTab] = useState<'overview' | 'referrals' | 'payouts'>('overview')
  const [applying, setApplying] = useState(false)
  const [copied, setCopied] = useState(false)
  const [showSheet, setShowSheet] = useState(false)
  const [payoutPhone, setPayoutPhone] = useState('')
  const [payoutError, setPayoutError] = useState('')
  const [submittingPayout, setSubmittingPayout] = useState(false)

  const loadAll = () => {
    setLoadError('')
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
    api<AmbassadorStatusResp>('/ambassador/status')
      .then(async status => {
        setStatusData(status)
        if (status.enrolled && (status.status === 'active' || status.status === 'suspended')) {
          const [d, r, p] = await Promise.all([
            api<AmbassadorDashboardResp>('/ambassador/dashboard'),
            api<{ referrals: AmbassadorReferral[] }>('/ambassador/referrals?page=1'),
            api<{ payouts: AmbassadorPayout[] }>('/ambassador/payouts'),
          ])
          setDashboard(d)
          setReferrals(r.referrals)
          setPayouts(p.payouts)
        }
      })
      .catch((e: any) => setLoadError(e?.message || 'Could not load the Ambassador program right now.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadAll() }, [])

  const handleApply = async () => {
    setApplying(true)
    try {
      await api('/ambassador/apply', { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      setLoading(true)
      loadAll()
    } catch (e: any) {
      alert(e?.message || 'Could not submit application.')
    } finally {
      setApplying(false)
    }
  }

  const copyLink = () => {
    if (!dashboard) return
    navigator.clipboard?.writeText(dashboard.referral_link).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    })
  }

  const shareLink = async () => {
    if (!dashboard) return
    const text = `Study smarter with Prepza - sign up with my link: ${dashboard.referral_link}`
    if ((navigator as any).share) {
      try { await (navigator as any).share({ text, url: dashboard.referral_link }) } catch {}
    } else {
      copyLink()
    }
  }

  const requestPayout = async () => {
    if (!/^\+?\d{9,15}$/.test(payoutPhone.trim())) {
      setPayoutError('Enter a valid phone number (e.g. +254712345678).')
      return
    }
    setSubmittingPayout(true)
    setPayoutError('')
    try {
      await api('/ambassador/payouts/request', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ payout_destination: payoutPhone.trim() }),
      })
      setShowSheet(false)
      loadAll()
    } catch (e: any) {
      setPayoutError(e?.message || 'Could not submit the payout request.')
    } finally {
      setSubmittingPayout(false)
    }
  }

  const Header = ({ title }: { title: string }) => (
    <div style={{ background: AMB_COLORS.navy, padding: '0 18px 16px', flexShrink: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', color: '#fff' }}>‹</button>
        <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>{title}</div>
      </div>
    </div>
  )

  if (loading) return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: AMB_COLORS.bg }}>
      <Header title="Ambassador Program" />
      <div style={{ padding: 40, textAlign: 'center', color: AMB_COLORS.gray, fontSize: 13 }}>Loading…</div>
    </div>
  )

  if (loadError && !statusData) return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: AMB_COLORS.bg }}>
      <Header title="Ambassador Program" />
      <div style={{ padding: 40, textAlign: 'center' }}>
        <div style={{ fontSize: 13, color: AMB_COLORS.gray, marginBottom: 14 }}>{loadError}</div>
        <button onClick={() => { setLoading(true); loadAll() }} style={{ background: AMB_COLORS.gold, color: AMB_COLORS.navy, border: 'none', borderRadius: 12, padding: '12px 24px', fontWeight: 800, fontSize: 13, cursor: 'pointer' }}>Retry</button>
      </div>
    </div>
  )

  const enrolled = statusData?.enrolled ?? false
  const appStatus = statusData?.status

  if (!enrolled || appStatus === 'rejected') return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: AMB_COLORS.bg }}>
      <Header title="Ambassador Program" />
      <div style={{ flex: 1, overflowY: 'auto', padding: 18 }}>
        <div style={{ background: `linear-gradient(135deg,${AMB_COLORS.navy},${AMB_COLORS.navy3})`, borderRadius: 20, padding: 22, marginBottom: 16, textAlign: 'center' }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>🤝</div>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff', marginBottom: 6 }}>Earn by sharing Prepza</div>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)', lineHeight: 1.6 }}>Get a personal referral link. Earn a one-time commission on every friend's first payment.</div>
        </div>
        {appStatus === 'rejected' && (
          <div style={{ background: '#FEE2E2', border: '1px solid #FCA5A5', borderRadius: 14, padding: 14, marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 12, color: '#B91C1C', marginBottom: 4 }}>Previous application declined</div>
            {!!statusData?.rejection_reason && <div style={{ fontSize: 12, color: '#991B1B' }}>{statusData.rejection_reason}</div>}
          </div>
        )}
        <div style={{ fontWeight: 700, fontSize: 13, color: AMB_COLORS.navy, marginBottom: 10 }}>Commission tiers</div>
        <div style={{ background: '#fff', borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', marginBottom: 20 }}>
          {[[1, 10, '0–4 paying referrals'], [2, 15, '5–19 paying referrals'], [3, 20, '20+ paying referrals']].map(([t, pct, range], i) => (
            <div key={t as number} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px', borderBottom: i < 2 ? '1px solid #F3F4F6' : 'none' }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: AMB_COLORS.gold + '18', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, color: AMB_COLORS.gold }}>T{t}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: AMB_COLORS.navy }}>{pct}% commission</div>
                <div style={{ fontSize: 11, color: AMB_COLORS.gray }}>{range}</div>
              </div>
            </div>
          ))}
        </div>
        <button onClick={handleApply} disabled={applying} style={{ width: '100%', padding: '15px 0', fontSize: 14, background: AMB_COLORS.gold, color: AMB_COLORS.navy, border: 'none', borderRadius: 14, fontWeight: 800, cursor: applying ? 'default' : 'pointer', opacity: applying ? 0.7 : 1 }}>
          {applying ? 'Submitting…' : (appStatus === 'rejected' ? 'Reapply' : 'Apply to become an ambassador')}
        </button>
      </div>
    </div>
  )

  if (appStatus === 'pending') return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: AMB_COLORS.bg }}>
      <Header title="Ambassador Program" />
      <div style={{ padding: 18 }}>
        <div style={{ background: '#fff', borderRadius: 18, padding: 26, textAlign: 'center', boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
          <div style={{ fontSize: 32, marginBottom: 10 }}>⏳</div>
          <div style={{ fontWeight: 800, fontSize: 16, color: AMB_COLORS.navy, marginBottom: 6 }}>Application under review</div>
          <div style={{ fontSize: 12, color: AMB_COLORS.gray, lineHeight: 1.6 }}>We're reviewing your application - usually within 1-2 days.</div>
        </div>
      </div>
    </div>
  )

  if (!dashboard) return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: AMB_COLORS.bg }}>
      <Header title="Ambassador Program" />
      <div style={{ padding: 40, textAlign: 'center', color: AMB_COLORS.gray, fontSize: 13 }}>Loading dashboard…</div>
    </div>
  )

  const canRequestPayout = dashboard.status === 'active' && dashboard.earnings.available_kes >= dashboard.min_payout_kes
  const tierPct = dashboard.next_tier_at ? Math.min(100, (dashboard.funnel.paying / dashboard.next_tier_at) * 100) : 100

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: AMB_COLORS.bg }}>
      <Header title="Ambassador Program" />
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {dashboard.status === 'suspended' && (
          <div style={{ margin: '14px 18px', background: '#FEF3C7', border: '1px solid #FDE68A', borderRadius: 14, padding: '12px 14px' }}>
            <div style={{ fontWeight: 700, fontSize: 12, color: '#92400E', marginBottom: 2 }}>Account suspended</div>
            <div style={{ fontSize: 11, color: '#92400E' }}>Existing commissions are safe, but new payout requests are disabled.</div>
          </div>
        )}
        <div style={{ margin: '14px 18px', background: `linear-gradient(135deg,${AMB_COLORS.navy},${AMB_COLORS.navy3})`, borderRadius: 18, padding: 18 }}>
          <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginBottom: 6 }}>Your referral link</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 12, padding: '10px 12px', marginBottom: 10 }}>
            <div style={{ flex: 1, fontSize: 12, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{dashboard.referral_link}</div>
            <button onClick={copyLink} style={{ color: AMB_COLORS.gold, background: 'none', border: 'none', cursor: 'pointer', fontSize: 11, fontWeight: 700 }}>{copied ? 'Copied ✓' : 'Copy'}</button>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={shareLink} style={{ flex: 1, background: `linear-gradient(135deg,${AMB_COLORS.gold},${AMB_COLORS.goldLight})`, color: AMB_COLORS.navy, border: 'none', borderRadius: 12, padding: '11px 0', fontWeight: 800, fontSize: 12, cursor: 'pointer' }}>Share link</button>
            <div style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 12, padding: '11px 14px', display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)' }}>Code</span>
              <span style={{ fontSize: 12, fontWeight: 800, color: AMB_COLORS.gold }}>{dashboard.referral_code}</span>
            </div>
          </div>
        </div>
        <div style={{ margin: '0 18px 14px', background: '#fff', borderRadius: 16, padding: 16, boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <div>
              <div style={{ fontWeight: 800, fontSize: 15, color: AMB_COLORS.navy }}>Tier {dashboard.tier} · {dashboard.commission_pct}% commission</div>
              <div style={{ fontSize: 11, color: AMB_COLORS.gray }}>{dashboard.next_tier_at ? `${Math.max(0, dashboard.next_tier_at - dashboard.funnel.paying)} more paying referrals to Tier ${dashboard.tier + 1}` : 'Top tier reached'}</div>
            </div>
            {amPill(`${dashboard.funnel.paying} paying`, AMB_COLORS.gold)}
          </div>
          {!!dashboard.next_tier_at && (
            <div style={{ background: '#F3F4F6', borderRadius: 99, height: 7, overflow: 'hidden' }}>
              <div style={{ background: `linear-gradient(90deg,${AMB_COLORS.gold},${AMB_COLORS.goldLight})`, height: 7, width: `${tierPct}%`, borderRadius: 99 }} />
            </div>
          )}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8, margin: '0 18px 14px' }}>
          {[['Pending', dashboard.earnings.pending_kes, AMB_COLORS.gray], ['Available', dashboard.earnings.available_kes, AMB_COLORS.green], ['Paid out', dashboard.earnings.paid_kes, AMB_COLORS.navy]].map(([label, val, color]) => (
            <div key={label as string} style={{ background: '#fff', borderRadius: 14, padding: '12px 6px', textAlign: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
              <div style={{ fontWeight: 800, fontSize: 13, color: color as string }}>{fmtKes(val as number)}</div>
              <div style={{ fontSize: 10, color: AMB_COLORS.gray, fontWeight: 600, marginTop: 2 }}>{label as string}</div>
            </div>
          ))}
        </div>
        <div style={{ margin: '0 18px 16px' }}>
          <button onClick={() => canRequestPayout && setShowSheet(true)} disabled={!canRequestPayout} style={{ width: '100%', padding: '13px 0', fontSize: 13, background: AMB_COLORS.gold, color: AMB_COLORS.navy, border: 'none', borderRadius: 14, fontWeight: 800, opacity: canRequestPayout ? 1 : 0.5, cursor: canRequestPayout ? 'pointer' : 'not-allowed' }}>
            {canRequestPayout ? `Request payout — ${fmtKes(dashboard.earnings.available_kes)}` : dashboard.status === 'suspended' ? 'Payouts disabled while suspended' : `Min. payout is ${fmtKes(dashboard.min_payout_kes)}`}
          </button>
          <div style={{ fontSize: 10, color: '#D1D5DB', textAlign: 'center', marginTop: 8 }}>Commissions unlock {dashboard.payout_hold_days} days after the qualifying payment</div>
        </div>
        <div style={{ margin: '0 18px', background: '#fff', borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
          <div style={{ display: 'flex', borderBottom: '1px solid rgba(0,0,0,0.06)' }}>
            {(['overview', 'referrals', 'payouts'] as const).map(t => (
              <button key={t} onClick={() => setTab(t)} style={{ flex: 1, padding: '11px 0', background: 'none', border: 'none', fontWeight: tab === t ? 800 : 500, fontSize: 11, color: tab === t ? AMB_COLORS.navy : AMB_COLORS.gray, cursor: 'pointer', borderBottom: tab === t ? `2px solid ${AMB_COLORS.gold}` : '2px solid transparent' }}>
                {t === 'overview' ? 'Funnel' : t === 'referrals' ? 'Referrals' : 'Payouts'}
              </button>
            ))}
          </div>
          <div style={{ padding: 14 }}>
            {tab === 'overview' && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 10 }}>
                {[['Referred', dashboard.funnel.referred], ['Verified', dashboard.funnel.verified], ['Activated', dashboard.funnel.activated], ['Paying', dashboard.funnel.paying]].map(([label, val]) => (
                  <div key={label as string} style={{ background: AMB_COLORS.bg, borderRadius: 12, padding: 12 }}>
                    <div style={{ fontWeight: 800, fontSize: 18, color: AMB_COLORS.navy }}>{val as number}</div>
                    <div style={{ fontSize: 10, color: AMB_COLORS.gray, fontWeight: 600 }}>{label as string}</div>
                  </div>
                ))}
                <div style={{ gridColumn: '1 / -1', background: AMB_COLORS.gold + '12', borderRadius: 12, padding: 12, textAlign: 'center' }}>
                  <span style={{ fontSize: 11, color: '#6B7280' }}>Signup → paying conversion: </span>
                  <span style={{ fontWeight: 800, fontSize: 12, color: AMB_COLORS.gold }}>{dashboard.funnel.conversion_rate}%</span>
                </div>
              </div>
            )}
            {tab === 'referrals' && (
              <div>
                {referrals.length === 0 && <div style={{ fontSize: 12, color: AMB_COLORS.gray, textAlign: 'center', padding: '20px 0' }}>No referrals yet - share your link to get started.</div>}
                {referrals.map((r, i) => {
                  const meta = AMB_STATUS_META[r.status]
                  return (
                    <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 0', borderBottom: i < referrals.length - 1 ? '1px solid #F3F4F6' : 'none' }}>
                      <div style={{ width: 34, height: 34, borderRadius: 10, background: meta.color + '18', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15 }}>{r.channel === 'whatsapp' ? '💬' : r.channel === 'instagram' ? '📸' : r.channel === 'tiktok' ? '🎵' : '🔗'}</div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: AMB_COLORS.navy }}>Referral #{r.id}{r.channel ? ` · via ${r.channel}` : ''}</div>
                        <div style={{ fontSize: 10, color: AMB_COLORS.gray }}>{r.created_at}{r.voided ? ' · voided (refunded)' : ''}</div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        {r.converted && !r.voided ? <div style={{ fontWeight: 800, fontSize: 12, color: '#16A34A', marginBottom: 3 }}>+{fmtKes(r.commission_amount || 0)}</div> : <div style={{ height: 15 }} />}
                        {amPill(r.voided ? 'Voided' : meta.label, r.voided ? AMB_COLORS.red : meta.color)}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
            {tab === 'payouts' && (
              <div>
                {payouts.length === 0 && <div style={{ fontSize: 12, color: AMB_COLORS.gray, textAlign: 'center', padding: '20px 0' }}>No payout requests yet.</div>}
                {payouts.map((p, i) => {
                  const meta = AMB_PAYOUT_META[p.status]
                  return (
                    <div key={p.id} style={{ padding: '10px 0', borderBottom: i < payouts.length - 1 ? '1px solid #F3F4F6' : 'none' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 3 }}>
                        <span style={{ fontWeight: 800, fontSize: 13, color: AMB_COLORS.navy }}>{fmtKes(p.amount)}</span>
                        {amPill(meta.label, meta.color)}
                      </div>
                      <div style={{ fontSize: 10, color: AMB_COLORS.gray }}>{p.payout_destination} · requested {p.requested_at}</div>
                      {p.status === 'rejected' && !!p.rejection_reason && <div style={{ fontSize: 10, color: AMB_COLORS.red, marginTop: 3 }}>{p.rejection_reason}</div>}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
        <div style={{ height: 24 }} />
      </div>
      {showSheet && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'flex-end', zIndex: 99 }}>
          <div style={{ background: '#fff', borderRadius: '24px 24px 0 0', padding: '24px 20px 36px', width: '100%' }}>
            <div style={{ width: 40, height: 4, background: '#E5E7EB', borderRadius: 99, margin: '0 auto 20px' }} />
            <div style={{ fontWeight: 800, fontSize: 16, color: AMB_COLORS.navy, marginBottom: 4 }}>Request payout</div>
            <div style={{ fontSize: 12, color: AMB_COLORS.gray, marginBottom: 18 }}>Available balance: {fmtKes(dashboard.earnings.available_kes)}</div>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#6B7280', marginBottom: 6 }}>M-Pesa number</div>
            <input value={payoutPhone} onChange={e => setPayoutPhone(e.target.value)} placeholder="+254712345678" style={{ width: '100%', boxSizing: 'border-box', background: AMB_COLORS.bg, border: '1px solid #E5E7EB', borderRadius: 12, padding: '13px 14px', fontSize: 13, color: AMB_COLORS.navy, marginBottom: 8 }} />
            {!!payoutError && <div style={{ fontSize: 11, color: AMB_COLORS.red, marginBottom: 10 }}>{payoutError}</div>}
            <button onClick={requestPayout} disabled={submittingPayout} style={{ width: '100%', padding: '14px 0', fontSize: 14, background: AMB_COLORS.gold, color: AMB_COLORS.navy, border: 'none', borderRadius: 14, fontWeight: 800, cursor: 'pointer', opacity: submittingPayout ? 0.7 : 1 }}>
              {submittingPayout ? 'Submitting…' : 'Confirm request'}
            </button>
            <button onClick={() => setShowSheet(false)} style={{ width: '100%', background: 'none', border: 'none', padding: '12px 0', marginTop: 4, cursor: 'pointer', fontWeight: 700, fontSize: 13, color: AMB_COLORS.gray }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('splash')
  const [adminMode, setAdminMode] = useState(false)
  const [oauthError, setOauthError] = useState('')
  const [isAdmin, setIsAdmin] = useState(false)
  // Which ForumPost is open in CommentsScreen, and which Document is open
  // in SummaryScreen. Screens communicate purely via the Screen string (no
  // route params), so these - like other "currently open X" ids - have to
  // be lifted here rather than living inside the screens themselves, which
  // unmount on navigation.
  const [activeForumPostId, setActiveForumPostId] = useState<number | null>(null)
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null)
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null)
  const [activeGroupId, setActiveGroupId] = useState<number | null>(null)
  // Which subscription plan the user picked on SubscriptionScreen, carried
  // over to PaymentScreen the same way activeDocumentId etc. are - these
  // are two separate mounted components, not steps of one component, so
  // the selection has to be lifted here rather than living in either screen.
  const [selectedPlan, setSelectedPlan] = useState('semester')
  // Which user's profile is open in StudentProfileScreen / whose followers-
  // following list is open in FollowListScreen. activeProfileName is a
  // best-effort label carried over from wherever the navigation started
  // (never fetched separately - there's no endpoint for it), so the screen
  // isn't stuck showing "Student" when we already know the real name.
  const [activeProfileUserId, setActiveProfileUserId] = useState<number | null>(null)
  const [activeProfileName, setActiveProfileName] = useState<string | null>(null)
  const [activeOpportunityId, setActiveOpportunityId] = useState<number | null>(null)

  // Handles the round-trip back from /auth/google/callback, which appends
  // ?complete_profile=1 (new Google account, needs university/course/year/
  // semester) or ?auth_error=... (Google sign-in failed) to the redirect.
  // This does NOT do general "am I still logged in" session restore on
  // every page load - only this specific OAuth round-trip.
  useEffect(() => {
    const path = window.location.pathname
    const params = new URLSearchParams(window.location.search)

    // Direct hits from emailed links - Flask serves this same SPA shell for
    // both paths, so routing happens client-side off the pathname. The
    // token itself stays in the query string; ResetPasswordScreen and
    // VerifyConfirmScreen each read it themselves.
    if (path === '/reset-password') {
      setScreen('reset-password')
      return
    }
    if (path === '/verify-email') {
      setScreen('verify-confirm')
      return
    }

    const wantsCompleteProfile = params.get('complete_profile') === '1'
    const authError = params.get('auth_error')
    if (wantsCompleteProfile) {
      setScreen('complete-profile')
    } else if (authError) {
      setOauthError(decodeURIComponent(authError))
      setScreen('login')
    }
    if (wantsCompleteProfile || authError) {
      const url = new URL(window.location.href)
      url.searchParams.delete('complete_profile')
      url.searchParams.delete('auth_error')
      window.history.replaceState({}, '', url.toString())
    }

    // Admin Platform is only ever shown to a confirmed admin session -
    // fails silently (stays false) for logged-out visitors or regular
    // students, on top of every /admin/* route already being server-side
    // gated via @require_admin.
    api<{ is_admin: boolean }>('/me')
      .then(me => setIsAdmin(!!me.is_admin))
      .catch(() => setIsAdmin(false))
  }, [])

  if (adminMode) return <AdminPlatform onExit={() => setAdminMode(false)} />

  const noNav: Screen[] = ['splash','login','forgot-password','signup','check-email','complete-profile','reset-password','verify-confirm','processing','payment','payment-success','payment-failure']
  const darkHomeIndicator: Screen[] = ['processing','splash','login']

  const renderScreen = () => {
    switch (screen) {
      case 'ambassador': return <AmbassadorScreen setScreen={setScreen} />
      case 'splash':            return <SplashScreen setScreen={setScreen} />
      case 'login':             return <LoginScreen setScreen={setScreen} oauthError={oauthError} />
      case 'forgot-password':   return <ForgotPasswordScreen setScreen={setScreen} />
      case 'signup':            return <SignupScreen setScreen={setScreen} />
      case 'check-email':       return <CheckEmailScreen setScreen={setScreen} />
      case 'complete-profile':  return <CompleteProfileScreen setScreen={setScreen} />
      case 'reset-password':    return <ResetPasswordScreen setScreen={setScreen} />
      case 'verify-confirm':    return <VerifyConfirmScreen setScreen={setScreen} />
      case 'home':              return <HomeScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} />
      case 'explore':           return <ExploreScreen setScreen={setScreen} setActiveGroupId={setActiveGroupId} />
      case 'create-modal':      return <CreateModal setScreen={setScreen} />
      case 'post-composer':     return <PostComposer setScreen={setScreen} />
      case 'question-composer': return <QuestionComposer setScreen={setScreen} />
      case 'share-opp-form':    return <ShareOppForm setScreen={setScreen} />
      case 'edu-upload-form':   return <EduUploadForm setScreen={setScreen} />
      case 'upload':            return <UploadScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} />
      case 'processing':        return <ProcessingScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'doc-ready':         return <DocReadyScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'document-study':    return <DocumentStudyScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'ai-tutor':          return <AITutorScreen setScreen={setScreen} />
      case 'flashcards':        return <FlashcardsScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'quiz':              return <QuizScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'podcast-player':    return <PodcastPlayerScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'podcast-library':   return <PodcastLibraryScreen setScreen={setScreen} />
      case 'summary':           return <SummaryScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'forum':             return <ForumScreen setScreen={setScreen} setActiveForumPostId={setActiveForumPostId} setActiveGroupId={setActiveGroupId} />
      case 'comments':          return <CommentsScreen setScreen={setScreen} postId={activeForumPostId} />
      case 'chats':             return <ChatsScreen setScreen={setScreen} setActiveConversationId={setActiveConversationId} />
      case 'chat-detail':       return <ChatDetailScreen setScreen={setScreen} conversationId={activeConversationId} />
      case 'opportunities':     return <OpportunitiesScreen setScreen={setScreen} setActiveOpportunityId={setActiveOpportunityId} />
      case 'opportunity-detail':return <OppDetailScreen setScreen={setScreen} opportunityId={activeOpportunityId} />
      case 'share-sheet':       return <ShareSheetScreen setScreen={setScreen} />
      case 'student-profile':   return <StudentProfileScreen setScreen={setScreen} targetUserId={activeProfileUserId} fallbackName={activeProfileName} setActiveConversationId={setActiveConversationId} />
      case 'profile':           return <ProfileScreen setScreen={setScreen} setActiveProfileUserId={setActiveProfileUserId} />
      case 'settings':          return <SettingsScreen setScreen={setScreen} />
      case 'notifications':     return <NotificationsScreen setScreen={setScreen} setActiveForumPostId={setActiveForumPostId} setActiveProfileUserId={setActiveProfileUserId} />
      case 'library':           return <LibraryScreen setScreen={setScreen} />
      case 'mind-map':          return <MindMapScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'new-chat':          return <NewChatScreen setScreen={setScreen} setActiveConversationId={setActiveConversationId} />
      case 'chat-options':      return <ChatOptionsScreen setScreen={setScreen} conversationId={activeConversationId} />
      case 'edit-profile':      return <EditProfileScreen setScreen={setScreen} />
      case 'subscription':      return <SubscriptionScreen setScreen={setScreen} selectedPlan={selectedPlan} setSelectedPlan={setSelectedPlan} />
      case 'payment':           return <PaymentScreen setScreen={setScreen} selectedPlan={selectedPlan} />
      case 'payment-success':   return <PaymentSuccessScreen setScreen={setScreen} />
      case 'payment-failure':   return <PaymentFailureScreen setScreen={setScreen} />
      case 'payment-history':   return <PaymentHistoryScreen setScreen={setScreen} />
      case 'publish-library':   return <PublishLibraryScreen setScreen={setScreen} />
      case 'xp-progress':       return <XPProgressScreen setScreen={setScreen} />
      case 'study-streak':      return <StudyStreakScreen setScreen={setScreen} />
      case 'achievements':      return <AchievementsScreen setScreen={setScreen} />
      case 'followers':         return <FollowListScreen mode="followers" setScreen={setScreen} targetUserId={activeProfileUserId} setActiveProfileUserId={setActiveProfileUserId} setActiveProfileName={setActiveProfileName} />
      case 'following':         return <FollowListScreen mode="following" setScreen={setScreen} targetUserId={activeProfileUserId} setActiveProfileUserId={setActiveProfileUserId} setActiveProfileName={setActiveProfileName} />
      case 'group-detail':      return <GroupDetailScreen setScreen={setScreen} groupId={activeGroupId} />
      case 'group-create':      return <GroupCreateScreen setScreen={setScreen} setActiveGroupId={setActiveGroupId} />
      default:                  return <HomeScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} />
    }
  }

  const isDark = ['splash','login','processing'].includes(screen)

  return (
    <div style={{ width: '100%', height: '100dvh', background: isDark ? N.navy : N.bg, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Content */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {renderScreen()}
      </div>
      {/* Bottom nav */}
      {!noNav.includes(screen) && <BottomNav active={screen} setScreen={setScreen} />}
      {/* Real admins only - hidden for everyone else, on top of every
          /admin/* route already being server-side gated via @require_admin. */}
      {isAdmin && (
        <button onClick={() => setAdminMode(true)} style={{ position: 'fixed', bottom: 10, right: 10, color: 'rgba(255,255,255,0.18)', fontSize: 10, fontFamily: 'Plus Jakarta Sans', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 99, padding: '3px 12px', cursor: 'pointer', letterSpacing: '0.5px', zIndex: 200 }}>
          ⚙ Admin Platform
        </button>
      )}
    </div>
  )
}
