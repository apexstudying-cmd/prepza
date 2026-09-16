from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'

text = APP.read_text(encoding='utf-8')

# Loading architecture sits above the existing API/offline/queue stack.
# Never replace that stack: those transforms intentionally share one API layer.
if 'async function baseApi<T = any>' not in text:
    api_start = text.find('async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {')
    if api_start < 0:
        raise SystemExit('Loading policy: api helper not found')
    text = text[:api_start] + text[api_start:].replace(
        'async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {',
        'async function baseApi<T = any>(path: string, options: RequestInit = {}): Promise<T> {',
        1,
    )

    wrapper = '''

const SCREEN_API_CACHE_TTL_MS = 2 * 60 * 1000
const screenApiCache = new Map<string, { value: any; fetchedAt: number }>()
const screenApiRefreshes = new Map<string, Promise<void>>()

function isScreenCacheableApiRequest(path: string, method: string): boolean {
  if (method !== 'GET') return false
  if (path.startsWith('/documents/') || path.includes('/reading/')) return false
  return path.startsWith('/') && !path.startsWith('/socket.io/')
}

function refreshScreenApiCache<T>(path: string, options: RequestInit): void {
  if (screenApiRefreshes.has(path)) return
  const refresh = baseApi<T>(path, options).then(fresh => {
    screenApiCache.set(path, { value: fresh, fetchedAt: Date.now() })
  }).catch(() => {
    // Stale data remains usable when background refresh fails.
  }).finally(() => screenApiRefreshes.delete(path))
  screenApiRefreshes.set(path, refresh)
}

async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const method = String(options.method || 'GET').toUpperCase()
  const cacheable = isScreenCacheableApiRequest(path, method)

  if (cacheable) {
    const cached = screenApiCache.get(path)
    if (cached) {
      if (Date.now() - cached.fetchedAt >= SCREEN_API_CACHE_TTL_MS) {
        refreshScreenApiCache<T>(path, options)
      }
      return cached.value as T
    }
  } else if (method !== 'GET') {
    screenApiCache.clear()
  }

  return baseApi<T>(path, options).then(value => {
    if (cacheable) screenApiCache.set(path, { value, fetchedAt: Date.now() })
    return value
  })
}
'''

    marker = '\n// ─── Document upload helpers'
    marker_index = text.find(marker)
    if marker_index < 0:
        raise SystemExit('Loading policy: document helper marker not found')
    text = text[:marker_index] + wrapper + text[marker_index:]

# Cached-first data should not briefly reveal a skeleton while the cached API
# promise resolves. Slow/no-cache requests still get a skeleton after a short
# delay, which prevents the "loading flash" without removing useful feedback.
if 'function DelayedScreenSkeleton' not in text:
    skeleton = '''

function DelayedScreenSkeleton({ children }: { children: React.ReactNode }) {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(true), 220)
    return () => window.clearTimeout(timer)
  }, [])
  if (!visible) return null
  return <>{children}</>
}
'''
    marker = '\nfunction GenerationLoading({ label }: { label: string }) {'
    marker_index = text.find(marker)
    if marker_index < 0:
        raise SystemExit('Loading policy: GenerationLoading insertion marker not found')
    text = text[:marker_index] + skeleton + text[marker_index:]

# Wrap simple one-line screen skeleton returns. Keep the original skeleton
# components themselves untouched so their layout/design remains stable.
pattern = re.compile(r'if\s*\(loading\)\s*return\s*(<Skeleton[A-Za-z0-9_]+\s*/>)')
text, wrapped_count = pattern.subn(
    r'if (loading) return <DelayedScreenSkeleton>\1</DelayedScreenSkeleton>',
    text,
)

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

if text.count('async function api<T = any>') != 1:
    raise SystemExit('Loading policy: public API wrapper generation invariant failed')
if text.count('async function baseApi<T = any>') != 1:
    raise SystemExit('Loading policy: underlying API generation invariant failed')
if text.count('const screenApiCache = new Map') != 1:
    raise SystemExit('Loading policy: duplicate screen cache detected')
if text.count('function DelayedScreenSkeleton') != 1:
    raise SystemExit('Loading policy: duplicate delayed skeleton helper detected')

APP.write_text(text, encoding='utf-8')
print(f'Screen loading policy applied: single API cache wrapper, delayed skeleton fallback, wrapped skeleton returns={wrapped_count}.')
