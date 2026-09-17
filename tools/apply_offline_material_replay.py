from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / 'frontend' / 'src' / 'generation' / 'GenerationScreens.tsx'
CLEAN = ROOT / 'frontend' / 'src' / 'generation' / 'StudyGenerationScreensClean.tsx'


def inject_before_first_effect(text: str, function_name: str, marker: str, code: str) -> str:
    if marker in text:
        return text
    start = text.find(function_name)
    if start < 0:
        raise SystemExit(f'Offline material replay: function missing: {function_name}')
    target = text.find('  useEffect(() => {', start)
    if target < 0:
        raise SystemExit(f'Offline material replay: useEffect anchor missing: {function_name}')
    return text[:target] + code + '\n' + text[target:]


def patch_generation():
    s = GEN.read_text(encoding='utf-8')
    s = inject_before_first_effect(s, 'export function SummaryGenerationScreen', 'Offline replay: summary', """  // Offline replay: a saved summary is restored through generationApi's local GET path.
  useEffect(() => {
    if (activeDocumentId == null) return
    void generationApi<any>(`/documents/${activeDocumentId}/summarize`).then((res: any) => {
      if (res?.summary != null) { setSummary(res.summary); setPhase('ready') }
    }).catch(() => {})
  }, [activeDocumentId])""")
    s = inject_before_first_effect(s, 'export function FlashcardsGenerationScreen', 'Offline replay: flashcards', """  // Offline replay: saved flashcards are restored through generationApi's local GET path.
  useEffect(() => {
    if (activeDocumentId == null) return
    void generationApi<any>(`/documents/${activeDocumentId}/flashcards`).then((res: any) => {
      const next = normalize(res?.flashcards ?? res)
      if (next.length) { setCards(next); setIdx(0); setFlipped(false); setKnown([]); setPhase('review') }
    }).catch(() => {})
  }, [activeDocumentId])""")
    required = ['Offline replay: summary', 'Offline replay: flashcards']
    missing = [x for x in required if x not in s]
    if missing: raise SystemExit('Offline generation replay verification failed: ' + ', '.join(missing))
    GEN.write_text(s, encoding='utf-8')


def patch_clean():
    s = CLEAN.read_text(encoding='utf-8')
    s = inject_before_first_effect(s, 'export function PracticeQuestionsGenerationScreen', 'Offline replay: practice questions', """  // Offline replay: saved practice questions are restored through the local GET path.
  useEffect(() => {
    if (activeDocumentId == null) return
    void api<any>(`/documents/${activeDocumentId}/quiz`).then(payload => {
      const next = questionsFrom(payload)
      if (next.length) { setQuestions(next); setIndex(0); setSelected(null); setScore(0); setPhase('quiz') }
    }).catch(() => {})
  }, [activeDocumentId])""")
    s = inject_before_first_effect(s, 'export function MindMapGenerationScreen', 'Offline replay: mind map', """  // Offline replay: saved mind maps are restored through the local GET path.
  useEffect(() => {
    if (activeDocumentId == null) return
    void api<any>(`/documents/${activeDocumentId}/mind-map`).then(payload => {
      const root = mapRoot(payload)
      if (root && (typeof root !== 'object' || Object.keys(root).length)) { setMap(root); setPhase('ready') }
    }).catch(() => {})
  }, [activeDocumentId])""")
    required = ['Offline replay: practice questions', 'Offline replay: mind map']
    missing = [x for x in required if x not in s]
    if missing: raise SystemExit('Offline clean replay verification failed: ' + ', '.join(missing))
    CLEAN.write_text(s, encoding='utf-8')


patch_generation()
patch_clean()
print('Offline replay for saved summaries, flashcards, practice questions, and mind maps applied and verified.')
