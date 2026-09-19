import { useEffect, useMemo, useState } from 'react'

type SetScreen = (screen: any) => void

type Theme = ReturnType<typeof theme>

async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const { headers: extra, ...rest } = options
  const res = await fetch(path, { credentials: 'include', ...rest, headers: { 'Content-Type': 'application/json', ...(extra || {}) } })
  let body: any = {}
  try { body = await res.json() } catch {}
  if (!res.ok) throw new Error(body?.error || body?.message || `Request failed (${res.status})`)
  return body as T
}

async function pollJob<T = any>(jobId: number, onProgress?: (percent: number, stage: string) => void): Promise<T> {
  for (;;) {
    const job = await api<{ status: string; progress_percent: number; progress_stage: string; error?: string; payload?: T }>(`/ai-jobs/${jobId}`)
    onProgress?.(Number(job.progress_percent || 0), job.progress_stage || 'working')
    if (job.status === 'completed') return (job.payload ?? {}) as T
    if (job.status === 'failed') throw new Error(job.error || 'Generation failed. Please try again.')
    await new Promise(resolve => window.setTimeout(resolve, 1800))
  }
}
function ProgressCard({ title, subtitle, percent, stage, T }: { title: string; subtitle: string; percent: number; stage: string; T: Theme }) {
  const safe = Math.max(0, Math.min(100, Math.round(percent)))
  return <div style={{ width: '100%', background: T.card, border: `1px solid ${T.border}`, borderRadius: 22, padding: 22 }}>
    <div style={{ color: T.gold, fontSize: 10, fontWeight: 900, letterSpacing: 1, textTransform: 'uppercase' }}>Prepza · Generating</div>
    <div style={{ color: T.text, fontSize: 18, fontWeight: 850, marginTop: 7 }}>{title}</div>
    <div style={{ color: T.muted, fontSize: 11, marginTop: 4 }}>{subtitle}</div>
    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 20, marginBottom: 8 }}><span style={{ color: T.muted, fontSize: 11 }}>{stage}</span><strong style={{ color: T.text, fontSize: 15 }}>{safe}%</strong></div>
    <div style={{ height: 9, background: T.border, borderRadius: 99, overflow: 'hidden' }}><div style={{ width: `${safe}%`, height: '100%', background: `linear-gradient(90deg,${T.gold},#E3C873)`, transition: 'width .45s ease' }}/></div>
    <div style={{ color: T.muted, fontSize: 11, lineHeight: 1.5, marginTop: 12 }}>You can leave this screen. Prepza keeps working in the background.</div>
  </div>
}

function useDarkMode() {
  const [dark, setDark] = useState(() => typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => setDark(media.matches)
    onChange()
    media.addEventListener?.('change', onChange)
    return () => media.removeEventListener?.('change', onChange)
  }, [])
  return dark
}

function theme(dark: boolean) {
  return dark ? { page: '#080D1D', card: '#101A31', card2: '#14203A', text: '#F4F6FB', muted: '#9AA6BE', border: '#263554', navy: '#0B1437', gold: '#D5B65A', goldSoft: 'rgba(213,182,90,0.12)', green: '#62D991', red: '#FF7777' } : { page: '#F7F8FB', card: '#FFFFFF', card2: '#F1F3F8', text: '#172033', muted: '#7A8498', border: '#E1E5EE', navy: '#0B1437', gold: '#C9A84C', goldSoft: 'rgba(201,168,76,0.08)', green: '#4CC97B', red: '#C94C4C' }
}

function Header({ title, subtitle, onBack, T }: { title: string; subtitle?: string; onBack: () => void; T: Theme }) {
  return <div style={{ background: T.navy, color: '#fff', padding: '0 18px 16px' }}><div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><button onClick={onBack} aria-label="Back" style={{ width: 34, height: 34, border: 0, borderRadius: 10, background: 'rgba(255,255,255,.1)', color: '#fff', fontSize: 21 }}>‹</button><div style={{ flex: 1, minWidth: 0 }}><div style={{ fontSize: 16, fontWeight: 800 }}>{title}</div>{subtitle && <div style={{ fontSize: 11, marginTop: 2, color: 'rgba(255,255,255,.55)' }}>{subtitle}</div>}</div></div></div>
}

function Choice({ selected, title, description, onClick, T }: { selected: boolean; title: string; description: string; onClick: () => void; T: Theme }) {
  return <button onClick={onClick} style={{ width: '100%', textAlign: 'left', border: `1.5px solid ${selected ? T.gold : T.border}`, background: selected ? T.goldSoft : T.card, color: T.text, borderRadius: 15, padding: '13px 14px', marginBottom: 8, fontFamily: 'Plus Jakarta Sans', fontWeight: 800 }}><div style={{ display: 'flex', gap: 11, alignItems: 'center' }}><div style={{ width: 19, height: 19, borderRadius: '50%', border: `2px solid ${selected ? T.gold : T.muted}`, background: selected ? T.gold : 'transparent', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{selected && <div style={{ width: 7, height: 7, borderRadius: '50%', background: T.navy }} />}</div><div><div style={{ fontSize: 13 }}>{title}</div><div style={{ color: T.muted, fontSize: 11, lineHeight: 1.45, marginTop: 2 }}>{description}</div></div></div></button>
}

function Generate({ disabled, onClick, T, children }: { disabled: boolean; onClick: () => void; T: Theme; children: React.ReactNode }) {
  return <button disabled={disabled} onClick={onClick} style={{ width: '100%', border: 0, borderRadius: 15, padding: 14, background: disabled ? T.border : `linear-gradient(135deg,${T.gold},#E3C873)`, color: disabled ? T.muted : T.navy, fontWeight: 900, fontFamily: 'Plus Jakarta Sans' }}>{children}</button>
}

function Failure({ message, onBack, onRetry, T }: { message: string; onBack: () => void; onRetry: () => void; T: Theme }) {
  return <div style={{ flex: 1, background: T.page }}><Header title="Generation failed" onBack={onBack} T={T}/><div style={{ padding: 28, minHeight: 340, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center' }}><div style={{ color: T.red, fontWeight: 900, fontSize: 22 }}>!</div><div style={{ color: T.text, fontWeight: 800, fontSize: 17, marginTop: 10 }}>We couldn't finish this</div><div style={{ color: T.muted, fontSize: 12, lineHeight: 1.6, maxWidth: 320, margin: '8px 0 18px' }}>{message}</div><button onClick={onRetry} style={{ border: 0, borderRadius: 12, padding: '11px 22px', background: T.navy, color: T.gold, fontWeight: 800 }}>Try again</button></div></div>
}

const COUNTS = [10, 20, 30, 50]
const DIFFICULTIES = [['easy', 'Easy', 'Confidence-building recall and core concepts.'], ['balanced', 'Balanced', 'Mixes recall, understanding, and application.'], ['hard', 'Hard', 'More demanding application and exam-style thinking.']] as const

function questionsFrom(payload: any): any[] {
  const value = payload?.questions || payload?.quiz?.questions || payload?.items || (Array.isArray(payload) ? payload : [])
  return Array.isArray(value) ? value : []
}
function qText(q: any) { return q?.question || q?.prompt || q?.text || 'Practice question' }
function qOptions(q: any): string[] { const value = q?.options || q?.choices || []; return Array.isArray(value) ? value.map(String) : [] }
function qAnswer(q: any) { return q?.correct_answer ?? q?.correctAnswer ?? q?.answer ?? q?.correct ?? null }
function qExplanation(q: any) { return q?.explanation || q?.rationale || q?.feedback || '' }

export function PracticeQuestionsGenerationScreen({ setScreen, activeDocumentId }: { setScreen: SetScreen; activeDocumentId: number | null }) {
  const dark = useDarkMode(); const T = theme(dark)
  const [count, setCount] = useState(20); const [difficulty, setDifficulty] = useState('balanced'); const [csrf, setCsrf] = useState(''); const [title, setTitle] = useState('Practice Questions')
  const [phase, setPhase] = useState<'config'|'loading'|'quiz'|'error'>('config'); const [generationPercent, setGenerationPercent] = useState(0); const [generationStage, setGenerationStage] = useState('preparing'); const [questions, setQuestions] = useState<any[]>([]); const [index, setIndex] = useState(0); const [selected, setSelected] = useState<string | null>(null); const [score, setScore] = useState(0); const [error, setError] = useState('')
  useEffect(() => { if (activeDocumentId == null) return; api<any>('/me').then(v => setCsrf(v.csrf_token || '')).catch(e => setError(e.message)); api<any>(`/documents/${activeDocumentId}`).then(v => setTitle(v.title || 'Practice Questions')).catch(() => {}) }, [activeDocumentId])
  const current = questions[index]; const options = useMemo(() => qOptions(current), [current]); const submitted = selected !== null
  const answer = qAnswer(current); const correct = submitted && (String(selected) === String(answer) || (typeof answer === 'number' && options[answer] === selected))
  const generate = async () => { if (activeDocumentId == null || !csrf) return; setError(''); setGenerationPercent(0); setGenerationStage('preparing'); setPhase('loading'); try { const started = await api<{ job_id: number }>(`/documents/${activeDocumentId}/quiz?async=1`, { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ question_count: count, difficulty, language: 'en' }) }); const next = questionsFrom(payload); if (!next.length) throw new Error('The generated practice set was empty. Please try again.'); setQuestions(next); setIndex(0); setSelected(null); setScore(0); setPhase('quiz') } catch (e) { setError(e instanceof Error ? e.message : 'Could not generate practice questions.'); setPhase('error') } }
  const advance = () => { if (!submitted) return; if (correct) setScore(v => v + 1); if (index < questions.length - 1) { setIndex(v => v + 1); setSelected(null) } }
  if (activeDocumentId == null) return <Failure message="No document selected." onBack={() => setScreen('document-study')} onRetry={() => setScreen('document-study')} T={T}/>
  if (phase === 'error') return <Failure message={error} onBack={() => setPhase('config')} onRetry={generate} T={T}/>
  if (phase === 'loading') return <div style={{ flex: 1, background: T.page }}><Header title="Preparing practice" subtitle={`${count} questions · ${difficulty}`} onBack={() => setPhase('config')} T={T}/><div style={{ padding: 22, minHeight: 380, display: 'flex', alignItems: 'center' }}><ProgressCard title="Generating your practice set" subtitle={`${count} questions · ${difficulty}`} percent={generationPercent} stage={generationStage} T={T}/></div></div>
  if (phase === 'quiz' && questions.length && index >= questions.length - 1 && submitted) return <div style={{ flex: 1, background: T.page }}><Header title="Practice complete" subtitle={title} onBack={() => setPhase('config')} T={T}/><div style={{ padding: 22, minHeight: 380, display: 'flex', alignItems: 'center' }}><div style={{ width: '100%', background: T.card, border: `1px solid ${T.border}`, borderRadius: 22, padding: 24, textAlign: 'center' }}><div style={{ color: T.gold, fontSize: 11, fontWeight: 900, letterSpacing: 1 }}>RESULT</div><div style={{ color: T.text, fontSize: 34, fontWeight: 900, marginTop: 8 }}>{score} / {questions.length}</div><div style={{ color: T.muted, fontSize: 12, lineHeight: 1.55, marginTop: 6 }}>Active recall plus feedback is a strong evidence-based study method.</div><button onClick={() => { setIndex(0); setSelected(null); setScore(0) }} style={{ marginTop: 18, border: 0, borderRadius: 12, padding: '11px 20px', background: T.navy, color: T.gold, fontWeight: 800 }}>Retry set</button></div></div></div>
  if (phase === 'quiz' && questions.length) return <div style={{ flex: 1, background: T.page }}><Header title="Practice Questions" subtitle={`${index + 1} of ${questions.length} · ${difficulty}`} onBack={() => setPhase('config')} T={T}/><div style={{ padding: 18 }}><div style={{ color: T.muted, fontSize: 11, marginBottom: 8 }}>{title}</div><div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 20, padding: 20 }}><div style={{ color: T.text, fontSize: 17, lineHeight: 1.45, fontWeight: 800 }}>{qText(current)}</div><div style={{ marginTop: 18 }}>{options.map((opt, i) => { const isCorrect = String(opt) === String(answer) || (typeof answer === 'number' && i === answer); const picked = selected === opt; return <button key={`${opt}-${i}`} onClick={() => !submitted && setSelected(opt)} style={{ width: '100%', textAlign: 'left', marginBottom: 9, border: `1.5px solid ${picked ? (isCorrect ? T.green : T.red) : submitted && isCorrect ? T.green : T.border}`, background: picked ? (isCorrect ? 'rgba(76,201,123,.12)' : 'rgba(201,76,76,.12)') : T.card2, color: T.text, borderRadius: 13, padding: '12px 13px', fontSize: 12, fontWeight: 700 }}>{String.fromCharCode(65 + i)}. {opt}</button> })}</div>{submitted && <div style={{ marginTop: 10, color: correct ? T.green : T.red, fontSize: 12, lineHeight: 1.5, fontWeight: 800 }}>{correct ? 'Correct.' : `Not quite.${answer != null ? ` Answer: ${answer}` : ''}`} {qExplanation(current) && <span style={{ color: T.muted, fontWeight: 600 }}>{qExplanation(current)}</span>}</div>}<button disabled={!submitted} onClick={advance} style={{ width: '100%', marginTop: 18, border: 0, borderRadius: 13, padding: 13, background: submitted ? T.gold : T.border, color: submitted ? T.navy : T.muted, fontWeight: 900 }}>{index === questions.length - 1 ? 'Finish' : 'Next question'}</button></div></div></div>
  return <div style={{ flex: 1, background: T.page }}><Header title="Practice Questions" subtitle={title} onBack={() => setScreen('document-study')} T={T}/><div style={{ padding: 18 }}><div style={{ color: T.text, fontSize: 20, fontWeight: 900, margin: '8px 0 5px' }}>Choose your practice set</div><div style={{ color: T.muted, fontSize: 12, lineHeight: 1.55, marginBottom: 17 }}>Build a set around the amount of practice and challenge you want today.</div><div style={{ color: T.text, fontSize: 11, fontWeight: 900, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>Questions</div>{COUNTS.map(n => <Choice key={n} selected={count === n} title={`${n} questions`} description={n === 50 ? 'Longest and most comprehensive practice set.' : `${n} questions grounded in the document.`} onClick={() => setCount(n)} T={T}/>)}<div style={{ color: T.text, fontSize: 11, fontWeight: 900, textTransform: 'uppercase', letterSpacing: 1, margin: '14px 0 8px' }}>Difficulty</div>{DIFFICULTIES.map(([value, label, desc]) => <Choice key={value} selected={difficulty === value} title={label} description={desc} onClick={() => setDifficulty(value)} T={T}/>)}<div style={{ marginTop: 10 }}><Generate disabled={!csrf} onClick={generate} T={T}>{csrf ? 'Generate practice set' : 'Loading…'}</Generate></div></div></div>
}

function mapRoot(payload: any) { const root = payload?.mind_map || payload?.mindmap || payload?.map || payload; return root?.root || root }
function mapTitle(node: any) { return node?.title || node?.label || node?.name || node?.topic || 'Concept' }
function mapChildren(node: any): any[] { const value = node?.children || node?.branches || node?.nodes || []; return Array.isArray(value) ? value : [] }
function MindNode({ node, depth, T }: { node: any; depth: number; T: Theme }) { const [open, setOpen] = useState(depth < 2); const children = mapChildren(node); return <div style={{ marginLeft: depth ? 16 : 0, borderLeft: depth ? `1px solid ${T.border}` : 'none', paddingLeft: depth ? 12 : 0, marginTop: 8 }}><button onClick={() => children.length && setOpen(v => !v)} style={{ width: '100%', textAlign: 'left', border: `1px solid ${depth === 0 ? T.gold : T.border}`, background: depth === 0 ? T.goldSoft : T.card, color: T.text, borderRadius: 13, padding: depth === 0 ? 14 : 11, fontWeight: depth < 2 ? 850 : 700, fontSize: depth === 0 ? 15 : 12 }}>{children.length ? (open ? '− ' : '+ ') : ''}{mapTitle(node)}</button>{open && children.map((child, i) => <MindNode key={`${mapTitle(child)}-${i}`} node={child} depth={depth + 1} T={T}/>)}</div> }

export function MindMapGenerationScreen({ setScreen, activeDocumentId }: { setScreen: SetScreen; activeDocumentId: number | null }) {
  const dark = useDarkMode(); const T = theme(dark); const [nodes, setNodes] = useState(30); const [csrf, setCsrf] = useState(''); const [title, setTitle] = useState('Mind Map'); const [phase, setPhase] = useState<'config'|'loading'|'ready'|'error'>('config'); const [generationPercent, setGenerationPercent] = useState(0); const [generationStage, setGenerationStage] = useState('preparing'); const [map, setMap] = useState<any>(null); const [error, setError] = useState('')
  useEffect(() => { if (activeDocumentId == null) return; api<any>('/me').then(v => setCsrf(v.csrf_token || '')).catch(e => setError(e.message)); api<any>(`/documents/${activeDocumentId}`).then(v => setTitle(v.title || 'Mind Map')).catch(() => {}) }, [activeDocumentId])
  const generate = async () => { if (activeDocumentId == null || !csrf) return; setError(''); setPhase('loading'); try { const started = await api<{ job_id: number }>(`/documents/${activeDocumentId}/mind-map?async=1`, { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ node_count: nodes, language: 'en' }) }); const payload = await pollJob<any>(started.job_id, (p, s) => { setGenerationPercent(p); setGenerationStage(s) }); const root = mapRoot(payload); if (!root || (typeof root === 'object' && !Object.keys(root).length)) throw new Error('The generated mind map was empty. Please try again.'); setMap(root); setPhase('ready') } catch (e) { setError(e instanceof Error ? e.message : 'Could not generate the mind map.'); setPhase('error') } }
  if (activeDocumentId == null) return <Failure message="No document selected." onBack={() => setScreen('document-study')} onRetry={() => setScreen('document-study')} T={T}/>
  if (phase === 'error') return <Failure message={error} onBack={() => setPhase('config')} onRetry={generate} T={T}/>
  if (phase === 'loading') return <div style={{ flex: 1, background: T.page }}><Header title="Building your mind map" subtitle={`${nodes} nodes · ${title}`} onBack={() => setPhase('config')} T={T}/><div style={{ padding: 22, minHeight: 380, display: 'flex', alignItems: 'center' }}><ProgressCard title="Generating your mind map" subtitle={`${nodes} nodes`} percent={generationPercent} stage={generationStage} T={T}/></div></div>
  if (phase === 'ready') return <div style={{ flex: 1, background: T.page }}><Header title="Mind Map" subtitle={title} onBack={() => setPhase('config')} T={T}/><div style={{ padding: 18 }}><div style={{ color: T.muted, fontSize: 11, lineHeight: 1.5, marginBottom: 12 }}>Start with the central idea and expand branches to review how concepts connect.</div><div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 20, padding: 14 }}><MindNode node={map} depth={0} T={T}/></div></div></div>
  return <div style={{ flex: 1, background: T.page }}><Header title="Mind Map" subtitle={title} onBack={() => setScreen('document-study')} T={T}/><div style={{ padding: 18 }}><div style={{ color: T.text, fontSize: 20, fontWeight: 900, margin: '8px 0 5px' }}>Choose map depth</div><div style={{ color: T.muted, fontSize: 12, lineHeight: 1.55, marginBottom: 17 }}>More nodes give broader coverage; fewer nodes keep the structure focused.</div>{COUNTS.map(n => <Choice key={n} selected={nodes === n} title={`${n} nodes`} description={n === 50 ? 'Broadest map for dense material.' : n === 10 ? 'High-level structure only.' : 'Balanced concept coverage.'} onClick={() => setNodes(n)} T={T}/>)}<div style={{ marginTop: 10 }}><Generate disabled={!csrf} onClick={generate} T={T}>{csrf ? 'Generate mind map' : 'Loading…'}</Generate></div></div></div>
}
