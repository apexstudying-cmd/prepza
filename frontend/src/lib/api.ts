// Minimal fetch wrapper for the Prepza Flask backend.
//
// Uses relative paths (e.g. "/chats") rather than an absolute base URL
// so this works unmodified in production, where the built frontend is
// served from Flask's static/ folder (same origin as the API). In
// local dev (`npm run dev`), Vite runs on its own port, so these
// relative paths need a dev proxy - add a server.proxy entry in
// vite.config.ts pointing the relevant paths at your local Flask
// origin (e.g. http://127.0.0.1:5000). Without that proxy, requests
// from the dev server will 404 against Vite itself instead of Flask.
//
// Session auth is cookie-based (SameSite=Lax), so every request must
// include credentials so the cookie rides along. Every mutating
// request (POST/PATCH/DELETE) also needs the X-CSRF-Token header -
// call setCsrfToken() once after a successful login (from /me's
// response) before calling any mutating endpoint below. Until login
// is wired, calls here will fail with a 401 - that's expected, not a
// bug in this client.

let csrfToken: string | null = null

export function setCsrfToken(token: string | null) {
  csrfToken = token
}

// Set once by the login flow (from /me's response) once that's wired.
// Chat screens use this to tell "my" messages apart from others'.
let currentUserId: number | null = null

export function setCurrentUserId(id: number | null) {
  currentUserId = id
}

export function getCurrentUserId(): number | null {
  return currentUserId
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || 'GET').toUpperCase()
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  }
  if (options.body) headers['Content-Type'] = 'application/json'
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken

  const res = await fetch(path, {
    ...options,
    method,
    headers,
    credentials: 'include',
  })

  let data: any = null
  try {
    data = await res.json()
  } catch {
    // Some responses (e.g. a bare 204) may have no JSON body - that's fine.
  }

  if (!res.ok) {
    const message = (data && data.error) || `Request failed (${res.status})`
    throw new ApiError(message, res.status)
  }
  return data as T
}

// ── Types matching the /chats API response shapes ──────────────────

export interface ChatSummary {
  id: number
  is_group: boolean
  name: string
  last_message: string | null
  last_message_at: string | null
  unread_count: number
}

export interface ChatMessage {
  id: number
  conversation_id: number
  sender_id: number
  body: string | null
  is_deleted: boolean
  created_at: string | null
  edited_at: string | null
}

export interface UserSearchResult {
  id: number
  display_name: string
  year: number | null
  semester: number | null
}

// ── Chat endpoints ───────────────────────────────────────────────────

export const chatApi = {
  list: () => request<{ chats: ChatSummary[] }>('/chats'),

  create: (params: { is_group: boolean; participant_ids: number[]; name?: string }) =>
    request<{ id: number; reused: boolean }>('/chats', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  messages: (conversationId: number, beforeId?: number) =>
    request<{ messages: ChatMessage[] }>(
      `/chats/${conversationId}/messages${beforeId ? `?before_id=${beforeId}` : ''}`,
    ),

  send: (conversationId: number, body: string) =>
    request<ChatMessage>(`/chats/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ body }),
    }),

  markRead: (conversationId: number) =>
    request<{ message: string }>(`/chats/${conversationId}/read`, { method: 'POST' }),

  rename: (conversationId: number, name: string) =>
    request<{ id: number; name: string }>(`/chats/${conversationId}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),

  leave: (conversationId: number) =>
    request<{ message: string }>(`/chats/${conversationId}/leave`, { method: 'POST' }),
}

export const userApi = {
  search: (q: string) =>
    request<{ users: UserSearchResult[] }>(`/users/search?q=${encodeURIComponent(q)}`),
}
