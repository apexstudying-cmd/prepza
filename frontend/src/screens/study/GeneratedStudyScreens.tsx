import { useEffect, useState, type ComponentType } from 'react'

import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Pill from '../../ui/Pill'

type StudyMaterialScreenTarget = 'document-study'

type CompletionResponse = { xp_awarded: number; newly_unlocked_achievements: string[] }
type GeneratedMaterialResponse = { material_id: number; reused: boolean; flashcards?: any; quiz?: any }
type GenerationProgress = { progress_percent: number; progress_stage: string; status: string }

type StudyMaterialScreensProps = {
  setScreen: (screen: StudyMaterialScreenTarget) => void
  activeDocumentId: number | null
  GenerationLoading: ComponentType<{ label: string }>
  GenerationError: ComponentType<{ error: string }>
  AchievementToast: ComponentType<{ codes: string[] }>
  generationRequest: <T = any>(path: string, options?: RequestInit, onProgress?: (progress: GenerationProgress) => void, currentUserId?: number) => Promise<T>
  replaySelectedGeneratedMaterialOffline: (documentId: string | number, feature: string) => Promise<any | null>
  getLatestGeneratedMaterialForPath: (path: string) => Promise<any | null>
}

function FlashcardsScreen({ setScreen, activeDocumentId, GenerationLoading, GenerationError, AchievementToast, generationRequest, replaySelectedGeneratedMaterialOffline, getLatestGeneratedMaterialForPath }: StudyMaterialScreensProps) {
  const { tokens: T } = useTheme()
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
  const [heartbeatCsrf, setHeartbeatCsrf] = useState('')

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setHeartbeatCsrf(me.csrf_token)).catch(() => {})
  }, [])

  useEffect(() => {
    if (loading || error || cards.length === 0 || finished || !heartbeatCsrf) return
    const ping = () => {
      if (document.visibilityState !== 'visible') return
      api('/study-time/heartbeat', {
        method: 'POST',
        headers: { 'X-CSRF-Token': heartbeatCsrf },
        body: JSON.stringify({ feature: 'flashcards' }),
      }).catch(() => {})
    }
    const interval = setInterval(ping, 20000)
    return () => clearInterval(interval)
  }, [loading, error, cards.length, finished, heartbeatCsrf])

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
    const path = `/documents/${activeDocumentId}/flashcards`
    const loadFlashcards = async () => {
      if (!navigator.onLine) return generationRequest<{ material_id: number; reused: boolean; flashcards: any }>(path)
      const me = await api<{ id: number; csrf_token: string }>('/me')
      setCsrfToken(me.csrf_token)
      return generationRequest<{ material_id: number; reused: boolean; flashcards: any }>(path, {
        method: 'POST',
        headers: { 'X-CSRF-Token': me.csrf_token },
      }, undefined, me.id)
    }
    void loadFlashcards()
      .then(res => { setMaterialId(res.material_id); setCards(normalizeCards(res.flashcards)) })
      .catch(async e => {
        const selected = await replaySelectedGeneratedMaterialOffline(activeDocumentId, 'flashcards')
        if (selected) { setMaterialId(selected.material_id); setCards(normalizeCards(selected.flashcards)); setError(''); return }
        const cached = await getLatestGeneratedMaterialForPath(path)
        if (cached) { setMaterialId(cached.material_id ?? null); setCards(normalizeCards(cached.flashcards ?? cached.payload ?? cached)); setError('') }
        else if (e instanceof ApiError && e.status === 429) setError("You've hit the hourly generation limit - try again later.")
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
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: T.pageBg, padding: 32 }}>
      <div style={{ fontSize: 56, marginBottom: 16 }}>🎉</div>
      <div style={{ fontWeight: 800, fontSize: 24, color: T.text, marginBottom: 6 }}>Review Complete!</div>
      <div style={{ fontSize: 15, color: T.textMuted, marginBottom: 16 }}>{known.length}/{cards.length} marked as known</div>
      {completion && completion.xp_awarded > 0 && (
        <div style={{ fontSize: 13, color: N.gold, fontWeight: 700, marginBottom: 8 }}>+{completion.xp_awarded} XP</div>
      )}
      {completion && <AchievementToast codes={completion.newly_unlocked_achievements} />}
      <button onClick={() => setScreen('document-study')} style={{ marginTop: 16, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 13, border: 'none', borderRadius: 14, padding: '12px 20px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Back to Notes</button>
    </div>
  )

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
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
        <div onClick={() => setFlipped(v => !v)} style={{ width: '100%', minHeight: 220, background: T.card, borderRadius: 24, padding: 28, boxShadow: '0 8px 32px rgba(0,0,0,0.1)', cursor: 'pointer', display: 'flex', flexDirection: 'column', justifyContent: 'center', border: `2px solid ${flipped ? N.gold + '44' : 'transparent'}`, transition: 'border-color 0.2s' }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: flipped ? N.gold : T.textMuted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 14 }}>{flipped ? 'Answer' : 'Question — tap to reveal'}</div>
          <div style={{ fontSize: 14, color: T.text, fontWeight: flipped ? 600 : 700, lineHeight: 1.7, whiteSpace: 'pre-line' }}>{flipped ? card.a : card.q}</div>
        </div>
        {flipped && (
          <div style={{ display: 'flex', gap: 14, width: '100%' }}>
            <button onClick={() => next(false)} style={{ flex: 1, background: '#FEE2E2', color: '#C94C4C', fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>✗ Still Learning</button>
            <button onClick={() => next(true)} style={{ flex: 1, background: '#D1FAE5', color: '#065F46', fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>✓ Got It</button>
          </div>
        )}
        {!flipped && (
          <div style={{ color: T.textMuted, fontSize: 12, textAlign: 'center' }}>Tap the card to see the answer</div>
        )}
      </div>
    </div>
  )
}

// ─── QUIZ ─────────────────────────────────────────────────────────────────────
function QuizScreen({ setScreen, activeDocumentId, GenerationLoading, GenerationError, AchievementToast, generationRequest, replaySelectedGeneratedMaterialOffline, getLatestGeneratedMaterialForPath }: StudyMaterialScreensProps) {
  const { tokens: T } = useTheme()
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
  const [heartbeatCsrf, setHeartbeatCsrf] = useState('')

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setHeartbeatCsrf(me.csrf_token)).catch(() => {})
  }, [])

  useEffect(() => {
    if (loading || error || questions.length === 0 || done || !heartbeatCsrf) return
    const ping = () => {
      if (document.visibilityState !== 'visible') return
      api('/study-time/heartbeat', {
        method: 'POST',
        headers: { 'X-CSRF-Token': heartbeatCsrf },
        body: JSON.stringify({ feature: 'quiz' }),
      }).catch(() => {})
    }
    const interval = setInterval(ping, 20000)
    return () => clearInterval(interval)
  }, [loading, error, questions.length, done, heartbeatCsrf])

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
    const path = `/documents/${activeDocumentId}/quiz`
    const loadQuiz = async () => {
      if (!navigator.onLine) return generationRequest<{ material_id: number; reused: boolean; quiz: any }>(path)
      const me = await api<{ id: number; csrf_token: string }>('/me')
      setCsrfToken(me.csrf_token)
      return generationRequest<{ material_id: number; reused: boolean; quiz: any }>(path, {
        method: 'POST',
        headers: { 'X-CSRF-Token': me.csrf_token },
      }, undefined, me.id)
    }
    void loadQuiz()
      .then(res => { setMaterialId(res.material_id); setQuestions(normalizeQuiz(res.quiz)) })
      .catch(async e => {
        const selected = await replaySelectedGeneratedMaterialOffline(activeDocumentId, 'quiz')
        if (selected) { setMaterialId(selected.material_id); setQuestions(normalizeQuiz(selected.quiz)); setError(''); return }
        const cached = await getLatestGeneratedMaterialForPath(path)
        if (cached) { setMaterialId(cached.material_id ?? null); setQuestions(normalizeQuiz(cached.quiz ?? cached.payload ?? cached)); setError('') }
        else if (e instanceof ApiError && e.status === 429) setError("You've hit the hourly generation limit - try again later.")
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
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: T.pageBg, padding: 32 }}>
      <div style={{ fontSize: 56, marginBottom: 16 }}>🎉</div>
      <div style={{ fontWeight: 800, fontSize: 24, color: T.text, marginBottom: 6 }}>Quiz Complete!</div>
      <div style={{ fontSize: 15, color: T.textMuted, marginBottom: 16 }}>You scored {score}/{questions.length}</div>
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
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
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
        <div style={{ background: T.card, borderRadius: 18, padding: 20, marginBottom: 20, boxShadow: '0 2px 12px rgba(0,0,0,0.07)' }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: N.gold, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 }}>Question {qi+1}</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: T.text, lineHeight: 1.7 }}>{q.q}</div>
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

export function FlashcardsStudyScreen(props: StudyMaterialScreensProps) {
  return <FlashcardsScreen {...props} />
}

export function QuizStudyScreen(props: StudyMaterialScreensProps) {
  return <QuizScreen {...props} />
}
