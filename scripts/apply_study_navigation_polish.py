from pathlib import Path
import re

APP = Path('frontend/src/App.tsx')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'Expected {label} anchor not found')
    return text.replace(old, new, 1)


def replace_mind_map(text: str) -> str:
    marker = r"// ─── MIND MAP ─────────────────────────────────────────────────────────────────\n"
    next_marker = r"// ─── PODCAST PLAYER ───────────────────────────────────────────────────────────\n"
    start = text.find(marker)
    end = text.find(next_marker, start + len(marker)) if start >= 0 else -1
    if start < 0 or end < 0:
        raise SystemExit('Mind Map section boundaries not found')

    component = r'''// ─── MIND MAP ─────────────────────────────────────────────────────────────────
type MindMapNode = { id: string; label: string; x: number; y: number; r: number; color: string; textColor: string; fontSize: number }

function MindMapScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const { mode, tokens: T } = useTheme()
  const [raw, setRaw] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [heartbeatCsrf, setHeartbeatCsrf] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) { setLoading(false); setError('No document selected.'); return }
    let cancelled = false
    setLoading(true)
    setError('')
    api<{ csrf_token: string }>('/me')
      .then(me => {
        if (cancelled) return
        setHeartbeatCsrf(me.csrf_token)
        return api<{ material_id: number; reused: boolean; mindmap: any }>(`/documents/${activeDocumentId}/mindmap`, {
          method: 'POST',
          headers: { 'X-CSRF-Token': me.csrf_token },
        })
      })
      .then(res => { if (!cancelled && res) setRaw(res.mindmap) })
      .catch(e => {
        if (cancelled) return
        if (e instanceof ApiError && e.status === 429) setError("You've hit the hourly generation limit - try again later.")
        else if (e instanceof ApiError && e.status === 503) setError('AI budget exceeded for now - try again later.')
        else setError(e instanceof ApiError ? e.message : 'Could not generate a mind map. Please try again.')
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [activeDocumentId])

  useEffect(() => {
    if (loading || error || !raw || !heartbeatCsrf) return
    const ping = () => {
      if (document.visibilityState !== 'visible') return
      api('/study-time/heartbeat', {
        method: 'POST',
        headers: { 'X-CSRF-Token': heartbeatCsrf },
        body: JSON.stringify({ feature: 'mindmap' }),
      }).catch(() => {})
    }
    ping()
    const interval = setInterval(ping, 20000)
    return () => clearInterval(interval)
  }, [loading, error, raw, heartbeatCsrf])

  const buildLayout = (): { nodes: MindMapNode[]; lines: [string, string][] } | null => {
    if (!raw) return null
    const centerLabel = String(raw.center || raw.root || raw.title || 'Overview')
    const branches: string[] = Array.isArray(raw.branches)
      ? raw.branches.map((v: any) => typeof v === 'string' ? v : v?.label || v?.name || v?.title || JSON.stringify(v))
      : Array.isArray(raw.nodes)
        ? raw.nodes.map((n: any) => n?.label || n?.name || n?.title || String(n))
        : []
    if (!branches.length) return null

    const nodes: MindMapNode[] = [{ id: 'center', label: centerLabel, x: 150, y: 150, r: 46, color: N.gold, textColor: N.navy, fontSize: 11 }]
    const lines: [string, string][] = []
    const angleStep = (2 * Math.PI) / branches.length
    const radius = branches.length <= 4 ? 105 : branches.length <= 8 ? 118 : 128
    branches.forEach((label, i) => {
      const angle = -Math.PI / 2 + i * angleStep
      const x = 150 + Math.cos(angle) * radius
      const y = 150 + Math.sin(angle) * radius
      const color = mode === 'dark' ? [N.navy2, N.navy3, '#355A91', '#2D7251', '#6B4A8A', '#7F3B3B'][i % 6] : [N.navy2, N.navy3, '#4C7BC9', '#4CC97B', '#9B59B6', '#C94C4C'][i % 6]
      nodes.push({ id: `n${i}`, label: String(label), x, y, r: 34, color, textColor: '#fff', fontSize: 9 })
      lines.push(['center', `n${i}`])
    })
    return { nodes, lines }
  }

  const layout = buildLayout()
  const page = T.pageBg
  const panel = T.card
  const subtle = mode === 'dark' ? 'rgba(255,255,255,0.055)' : 'rgba(11,20,55,0.035)'

  if (activeDocumentId == null) return <GenerationError error="No document selected." />

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', background: page, color: T.text }}>
      <div style={{ background: N.navy, padding: '0 18px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('document-study')} aria-label="Back to document" style={{ width: 36, height: 36, background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 11, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: 16, color: '#fff' }}>Mind Map</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginTop: 2 }}>Visualise how the ideas in your document connect</div>
          </div>
          <div style={{ width: 34, height: 34, borderRadius: 11, background: 'rgba(201,168,76,0.14)', color: N.gold, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900, fontSize: 17 }}>⌘</div>
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: 16 }} className="scrollbar-hide">
        {loading ? (
          <div style={{ minHeight: 'calc(100% - 1px)', background: panel, border: `1px solid ${T.border}`, borderRadius: 20, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 28, textAlign: 'center', boxSizing: 'border-box' }}>
            <div style={{ width: 46, height: 46, borderRadius: 15, background: T.goldSoft || 'rgba(201,168,76,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
              <div style={{ width: 24, height: 24, border: `3px solid ${mode === 'dark' ? 'rgba(255,255,255,0.12)' : 'rgba(11,20,55,0.1)'}`, borderTopColor: N.gold, borderRadius: '50%', animation: 'spin-slow .8s linear infinite' }} />
            </div>
            <div style={{ color: T.text, fontWeight: 800, fontSize: 15 }}>Building your mind map</div>
            <div style={{ color: T.textMuted, fontSize: 12, lineHeight: 1.55, maxWidth: 300, marginTop: 6 }}>Organising the important ideas and showing how they relate.</div>
          </div>
        ) : error ? (
          <GenerationError error={error} />
        ) : !layout ? (
          <div style={{ background: panel, border: `1px solid ${T.border}`, borderRadius: 20, padding: 22, textAlign: 'center' }}>
            <div style={{ width: 52, height: 52, borderRadius: 16, background: subtle, color: T.textMuted, display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 12px', fontSize: 22 }}>⌘</div>
            <div style={{ color: T.text, fontWeight: 800, fontSize: 15 }}>This map could not be displayed</div>
            <div style={{ color: T.textMuted, fontSize: 12, lineHeight: 1.55, marginTop: 5 }}>The generated material did not contain a visual branch structure.</div>
          </div>
        ) : (
          <div style={{ background: panel, border: `1px solid ${T.border}`, borderRadius: 22, overflow: 'hidden', boxShadow: mode === 'dark' ? '0 14px 40px rgba(0,0,0,0.24)' : '0 8px 30px rgba(11,20,55,0.08)' }}>
            <div style={{ padding: '16px 16px 12px', borderBottom: `1px solid ${T.border}`, background: subtle }}>
              <div style={{ color: T.text, fontWeight: 800, fontSize: 15 }}>Concept map</div>
              <div style={{ color: T.textMuted, fontSize: 11, lineHeight: 1.5, marginTop: 3 }}>Start at the centre and follow each branch.</div>
            </div>
            <div style={{ padding: 12, overflowX: 'auto', background: page }}>
              <svg viewBox="0 0 300 300" width="100%" height="min(68vw,420px)" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Generated mind map" style={{ display: 'block', minWidth: 280 }}>
                <defs>
                  <filter id="mindmap-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="3" stdDeviation="3" floodOpacity={mode === 'dark' ? '0.45' : '0.14'} /></filter>
                </defs>
                {layout.lines.map(([from, to]) => {
                  const f = layout.nodes.find(n => n.id === from)!
                  const t = layout.nodes.find(n => n.id === to)!
                  return <line key={`${from}-${to}`} x1={f.x} y1={f.y} x2={t.x} y2={t.y} stroke={mode === 'dark' ? 'rgba(255,255,255,0.16)' : 'rgba(11,20,55,0.14)'} strokeWidth="2.5" strokeLinecap="round" />
                })}
                {layout.nodes.map(node => (
                  <g key={node.id}>
                    <circle cx={node.x} cy={node.y} r={node.r} fill={node.color} filter="url(#mindmap-shadow)" />
                    {String(node.label).split('\n').slice(0, 3).map((line, i, arr) => (
                      <text key={i} x={node.x} y={node.y + (i - (arr.length - 1) / 2) * (node.fontSize + 2)} textAnchor="middle" dominantBaseline="middle" fontSize={node.fontSize} fontWeight="700" fill={node.textColor} fontFamily="Plus Jakarta Sans">{line.slice(0, 34)}</text>
                    ))}
                  </g>
                ))}
              </svg>
            </div>
            <div style={{ padding: '10px 14px 14px', borderTop: `1px solid ${T.border}`, background: subtle, display: 'flex', gap: 8, alignItems: 'center' }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: N.gold, flexShrink: 0 }} />
              <div style={{ color: T.textMuted, fontSize: 10, lineHeight: 1.45 }}>Central idea</div>
              <div style={{ marginLeft: 'auto', color: T.textMuted, fontSize: 10 }}>{layout.nodes.length - 1} branches</div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

'''
    return text[:start] + component + text[end:]


def harden_document_navigation(text: str) -> str:
    old_state = "  const [doc, setDoc] = useState<DocumentDetail | null>(null)\n"
    new_state = "  const [doc, setDoc] = useState<DocumentDetail | null>(() => activeDocumentId != null ? DOC_CACHE[activeDocumentId] ?? null : null)\n"
    text = replace_once(text, old_state, new_state, 'document cache state')

    old_loading = "  const docLoading = activeDocumentId != null && doc === null && !docLoadError\n  if (docLoading) return <SkeletonDocument />\n\n"
    if old_loading in text:
        text = text.replace(old_loading, '', 1)

    old_set_screen = """  const setScreen = (s: Screen) => {
    if (s === screen) return
    setScreenStack(stack => [...stack, s])
    window.history.pushState({ prepzaNav: true }, '')
  }
"""
    new_set_screen = """  const setScreen = (s: Screen) => {
    if (s === screen) return
    // Back-style buttons commonly target the immediately previous screen.
    // Reuse that existing history entry instead of pushing a duplicate route.
    if (screenStack.length > 1 && screenStack[screenStack.length - 2] === s) {
      window.history.back()
      return
    }
    setScreenStack(stack => [...stack, s])
    window.history.pushState({ prepzaNav: true }, '')
  }
"""
    text = replace_once(text, old_set_screen, new_set_screen, 'screen navigation setter')
    return text


def main():
    text = APP.read_text()
    text = replace_mind_map(text)
    text = harden_document_navigation(text)
    APP.write_text(text)
    print('study navigation polish applied')


if __name__ == '__main__':
    main()
