from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'

text = APP.read_text(encoding='utf-8')

api_start = text.find('async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {')
if api_start < 0:
    raise SystemExit('Loading policy: api helper not found')
api_end = text.find('\n}\n\n// ─── Document upload helpers', api_start)
if api_end < 0:
    raise SystemExit('Loading policy: api helper boundary not found')

api_block = '''const SCREEN_API_CACHE_TTL_MS = 2 * 60 * 1000
const screenApiCache = new Map<string, { value: any; expiresAt: number }>()
let screenApiRefreshes = new Map<string, Promise<void>>()

function isCacheableApiRequest(path: string, method: string): boolean {
  if (method !== 'GET') return false
  // Keep document/file payloads on their dedicated Study Hub/offline paths.
  if (path.startsWith('/documents/')) return false
  if (path.includes('/reading/')) return false
  return true
}

async function requestApiJson<T>(path: string, options: RequestInit): Promise<T> {
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

async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const method = String(options.method || 'GET').toUpperCase()
  const cacheable = isCacheableApiRequest(path, method)

  if (cacheable) {
    const cached = screenApiCache.get(path)
    if (cached && cached.expiresAt > Date.now()) {
      // Cached data wins the render race. Refresh quietly in the background so
      // the next visit sees newer data without flashing a loading state.
      if (!screenApiRefreshes.has(path)) {
        const refresh = requestApiJson<T>(path, options).then(fresh => {
          screenApiCache.set(path, { value: fresh, expiresAt: Date.now() + SCREEN_API_CACHE_TTL_MS })
        }).catch(() => {}).finally(() => {
          screenApiRefreshes.delete(path)
        })
        screenApiRefreshes.set(path, refresh.then(() => undefined))
      }
      return cached.value as T
    }
  }

  const value = await requestApiJson<T>(path, options)
  if (cacheable) {
    screenApiCache.set(path, { value, expiresAt: Date.now() + SCREEN_API_CACHE_TTL_MS })
  } else if (method !== 'GET') {
    // Mutations can invalidate any screen-level cached snapshot.
    screenApiCache.clear()
  }
  return value
}
'''

text = text[:api_start] + api_block + text[api_end + 2:]

loading_start = text.find('function GenerationLoading({ label }: { label: string }) {')
if loading_start < 0:
    raise SystemExit('Loading policy: GenerationLoading not found')
loading_end = text.find('\n}\n\n// ─── Icon helpers', loading_start)
if loading_end < 0:
    raise SystemExit('Loading policy: GenerationLoading boundary not found')

loading_block = '''function GenerationLoading({ label }: { label: string }) {
  const { tokens: T } = useTheme()
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(true), 280)
    return () => window.clearTimeout(timer)
  }, [])

  if (!visible) return null
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 32 }}>
      <div style={{ width: 40, height: 40, border: `3px solid rgba(201,168,76,0.2)`, borderTopColor: N.gold, borderRadius: '50%', animation: 'spin-slow 0.8s linear infinite', marginBottom: 16 }} />
      <div style={{ color: T.textMuted, fontSize: 13 }}>{label}</div>
    </div>
  )
}
'''
text = text[:loading_start] + loading_block + text[loading_end + 2:]

APP.write_text(text, encoding='utf-8')
print('Cached-first screen loading policy applied.')
