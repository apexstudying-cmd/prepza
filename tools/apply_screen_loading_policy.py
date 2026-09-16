from pathlib import Path

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
const screenApiCache = new Map<string, { value: any; fetchedAt: number }>()
const screenApiRefreshes = new Map<string, Promise<void>>()

function isCacheableApiRequest(path: string, method: string): boolean {
  if (method !== 'GET') return false
  // Document/file payloads have their own Study Hub/offline lifecycle and can
  // be large or user-specific, so they must not enter the generic screen cache.
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

function refreshScreenApiCache<T>(path: string, options: RequestInit): void {
  if (screenApiRefreshes.has(path)) return
  const refresh = requestApiJson<T>(path, options).then(fresh => {
    screenApiCache.set(path, { value: fresh, fetchedAt: Date.now() })
  }).catch(() => {
    // Stale data remains usable when a background refresh fails. The next
    // visit can retry instead of replacing useful UI with an error state.
  }).finally(() => {
    screenApiRefreshes.delete(path)
  })
  screenApiRefreshes.set(path, refresh.then(() => undefined))
}

async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const method = String(options.method || 'GET').toUpperCase()
  const cacheable = isCacheableApiRequest(path, method)

  if (cacheable) {
    const cached = screenApiCache.get(path)
    if (cached) {
      const age = Date.now() - cached.fetchedAt
      // Any previously rendered snapshot is immediately usable. Fresh entries
      // avoid a network request; stale entries render first and revalidate in
      // the background (stale-while-refresh).
      if (age >= SCREEN_API_CACHE_TTL_MS) {
        refreshScreenApiCache<T>(path, options)
      } else if (!screenApiRefreshes.has(path)) {
        // Keep data reasonably fresh without making navigation wait for it.
        refreshScreenApiCache<T>(path, options)
      }
      return cached.value as T
    }
  }

  const value = await requestApiJson<T>(path, options)
  if (cacheable) {
    screenApiCache.set(path, { value, fetchedAt: Date.now() })
  } else if (method !== 'GET') {
    // Mutations can change multiple screens; invalidate the generic snapshot
    // cache rather than risking stale user-facing state after a write.
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
    // Never flash a loading surface for a fast request. If generation really
    // takes time, the delayed state communicates that work is still happening.
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
