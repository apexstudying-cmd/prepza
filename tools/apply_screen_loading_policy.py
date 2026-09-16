from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'

text = APP.read_text(encoding='utf-8')

# The cached-first API policy belongs to apply_offline_data_foundation.py so
# there is exactly one API/cache implementation. This script only owns the
# generation loading surface and must never replace the API helper.
if 'const PREPZA_OFFLINE_DB' not in text:
    raise SystemExit('Loading policy: offline data foundation must run first')
if text.count('async function api<T = any>') != 1:
    raise SystemExit('Loading policy: expected exactly one api helper')

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
print('Screen loading policy applied without duplicating the API/cache layer.')
