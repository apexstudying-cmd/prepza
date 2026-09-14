from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / 'frontend' / 'src' / 'generation' / 'StudyGenerationScreensClean.tsx'

text = GEN.read_text(encoding='utf-8')
marker = 'export function MindMapGenerationScreen('
start = text.find(marker)
if start < 0:
    raise SystemExit('MindMapGenerationScreen not found')

replacement = r'''export function MindMapGenerationScreen({ setScreen, activeDocumentId }: { setScreen: SetScreen; activeDocumentId: number | null }) {
  const dark = useDarkMode()
  const T = theme(dark)
  const [nodes, setNodes] = useState(30)
  const [csrf, setCsrf] = useState('')
  const [title, setTitle] = useState('Mind Map')
  const [phase, setPhase] = useState<'config'|'loading'|'ready'|'error'>('config')
  const [map, setMap] = useState<any>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) return
    Promise.all([
      api<any>('/me'),
      api<any>(`/documents/${activeDocumentId}`),
    ])
      .then(([me, doc]) => { setCsrf(me.csrf_token || ''); setTitle(doc.title || 'Mind Map') })
      .catch(e => setError(e instanceof Error ? e.message : 'Could not load the document.'))
  }, [activeDocumentId])

  const generate = async () => {
    if (activeDocumentId == null || !csrf) return
    setError('')
    setPhase('loading')
    try {
      const payload = await api<any>(`/documents/${activeDocumentId}/mind-map`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrf },
        body: JSON.stringify({ node_count: nodes, language: 'en' }),
      })
      const root = mapRoot(payload)
      if (!root || (typeof root === 'object' && !Object.keys(root).length)) throw new Error('The generated mind map was empty. Please try again.')
      setMap(root)
      setPhase('ready')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not generate the mind map.')
      setPhase('error')
    }
  }

  const backToDocument = () => setScreen('document-study')
  if (activeDocumentId == null) return <Failure message="No document selected." onBack={backToDocument} onRetry={backToDocument} T={T}/>
  if (phase === 'error') return <Failure message={error} onBack={() => setPhase('config')} onRetry={generate} T={T}/>

  if (phase === 'loading') {
    return <div style={{ flex: 1, minHeight: 0, background: T.page, color: T.text, display: 'flex', flexDirection: 'column' }}>
      <Header title="Building your mind map" subtitle={title} onBack={() => setPhase('config')} T={T}/>
      <div style={{ flex: 1, minHeight: 0, padding: 16, display: 'flex', alignItems: 'stretch' }}>
        <div style={{ flex: 1, minHeight: 360, background: T.card, border: `1px solid ${T.border}`, borderRadius: 22, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 28, textAlign: 'center', boxSizing: 'border-box' }}>
          <div style={{ width: 50, height: 50, borderRadius: 16, background: T.goldSoft, display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
            <div style={{ width: 25, height: 25, border: `3px solid ${dark ? 'rgba(255,255,255,.12)' : 'rgba(11,20,55,.1)'}`, borderTopColor: T.gold, borderRadius: '50%', animation: 'spin-slow .8s linear infinite' }}/>
          </div>
          <div style={{ color: T.text, fontWeight: 850, fontSize: 16 }}>Building your mind map</div>
          <div style={{ color: T.muted, fontSize: 12, lineHeight: 1.55, maxWidth: 310, marginTop: 6 }}>Organising the important ideas in your document and connecting related concepts.</div>
        </div>
      </div>
    </div>
  }

  if (phase === 'ready') {
    const root = mapRoot({ root: map }) || map
    const center = mapTitle(root)
    const children = mapChildren(root)
    const branchColors = dark ? ['#24345B', '#355A91', '#2D7251', '#6B4A8A', '#7F3B3B', '#5A476E'] : ['#162342', '#24345B', '#4C7BC9', '#4CC97B', '#9B59B6', '#C94C4C']
    const radius = children.length <= 4 ? 98 : children.length <= 8 ? 112 : 124
    const points = children.map((child, i) => {
      const angle = -Math.PI / 2 + i * ((2 * Math.PI) / Math.max(children.length, 1))
      return { child, x: 150 + Math.cos(angle) * radius, y: 150 + Math.sin(angle) * radius, color: branchColors[i % branchColors.length] }
    })

    return <div style={{ flex: 1, minHeight: 0, background: T.page, color: T.text, display: 'flex', flexDirection: 'column' }}>
      <Header title="Mind Map" subtitle={title} onBack={() => setPhase('config')} T={T}/>
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: 16 }} className="scrollbar-hide">
        <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 22, overflow: 'hidden', boxShadow: dark ? '0 14px 40px rgba(0,0,0,.25)' : '0 8px 30px rgba(11,20,55,.08)' }}>
          <div style={{ padding: '16px 16px 12px', borderBottom: `1px solid ${T.border}`, background: T.card2 }}>
            <div style={{ color: T.text, fontWeight: 850, fontSize: 15 }}>Concept map</div>
            <div style={{ color: T.muted, fontSize: 11, lineHeight: 1.5, marginTop: 3 }}>Start at the centre and follow each branch to revise the document.</div>
          </div>
          {children.length ? <div style={{ padding: 12, background: T.page, overflowX: 'auto' }}>
            <svg viewBox="0 0 300 300" width="100%" height="min(72vw,430px)" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Generated mind map" style={{ display: 'block', minWidth: 280 }}>
              <defs><filter id="prepza-mindmap-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="3" stdDeviation="3" floodOpacity={dark ? '.45' : '.14'}/></filter></defs>
              {points.map(({ child, x, y }) => <line key={`line-${mapTitle(child)}`} x1="150" y1="150" x2={x} y2={y} stroke={dark ? 'rgba(255,255,255,.16)' : 'rgba(11,20,55,.14)'} strokeWidth="2.5" strokeLinecap="round"/>)}
              <circle cx="150" cy="150" r="47" fill={T.gold} filter="url(#prepza-mindmap-shadow)"/>
              {center.split('\n').slice(0, 3).map((line, i, arr) => <text key={`center-${i}`} x="150" y={150 + (i - (arr.length - 1) / 2) * 13} textAnchor="middle" dominantBaseline="middle" fontSize="10" fontWeight="800" fill={T.navy} fontFamily="Plus Jakarta Sans">{line.slice(0, 32)}</text>)}
              {points.map(({ child, x, y, color }, i) => <g key={`node-${i}`}><circle cx={x} cy={y} r="34" fill={color} filter="url(#prepza-mindmap-shadow)"/>{mapTitle(child).split('\n').slice(0, 3).map((line, j, arr) => <text key={j} x={x} y={y + (j - (arr.length - 1) / 2) * 11} textAnchor="middle" dominantBaseline="middle" fontSize="8.5" fontWeight="750" fill="#fff" fontFamily="Plus Jakarta Sans">{line.slice(0, 28)}</text>)}</g>)}
            </svg>
          </div> : <div style={{ padding: 28, textAlign: 'center', color: T.muted, fontSize: 12 }}>The generated map did not contain any branches to display.</div>}
          <div style={{ padding: '10px 14px 14px', borderTop: `1px solid ${T.border}`, background: T.card2, display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: T.gold, flexShrink: 0 }}/>
            <span style={{ color: T.muted, fontSize: 10 }}>Central idea</span>
            <span style={{ marginLeft: 'auto', color: T.muted, fontSize: 10 }}>{children.length} branches</span>
          </div>
        </div>
      </div>
    </div>
  }

  return <div style={{ flex: 1, minHeight: 0, background: T.page, color: T.text, display: 'flex', flexDirection: 'column' }}>
    <Header title="Mind Map" subtitle={title} onBack={backToDocument} T={T}/>
    <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: 18 }} className="scrollbar-hide">
      <div style={{ color: T.text, fontSize: 20, fontWeight: 900, margin: '8px 0 5px' }}>Choose map depth</div>
      <div style={{ color: T.muted, fontSize: 12, lineHeight: 1.55, marginBottom: 17 }}>More nodes give broader coverage; fewer nodes keep the structure focused.</div>
      <div style={{ color: T.text, fontSize: 11, fontWeight: 900, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>Coverage</div>
      {COUNTS.map(n => <Choice key={n} selected={nodes === n} title={`${n} nodes`} description={n === 50 ? 'Broadest map for dense material.' : n === 10 ? 'High-level structure only.' : 'Balanced concept coverage.'} onClick={() => setNodes(n)} T={T}/>)}
      <div style={{ marginTop: 10 }}><Generate disabled={!csrf} onClick={generate} T={T}>{csrf ? 'Generate mind map' : 'Loading…'}</Generate></div>
    </div>
  </div>
}
'''

GEN.write_text(text[:start] + replacement + '\n', encoding='utf-8')
print('Study generation screen polish applied.')
