from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / 'frontend' / 'src' / 'generation' / 'GenerationScreens.tsx'
CLEAN = ROOT / 'frontend' / 'src' / 'generation' / 'StudyGenerationScreensClean.tsx'


def patch_generation():
    s = GEN.read_text(encoding='utf-8')
    if 'Offline replay: summary' not in s:
        anchor = "  useEffect(() => {\n    if (activeDocumentId == null) return\n    Promise.all([generationApi<{ csrf_token: string }>('/me'), generationApi<{ title: string }>(`/documents/${activeDocumentId}`)])\n      .then(([me, doc]) => { setCsrf(me.csrf_token); setTitle(doc.title) })\n      .catch(e => setError(e instanceof Error ? e.message : 'Could not load the document.'))\n  }, [activeDocumentId])\n\n  const generate = async () => {\n    if (activeDocumentId == null || !csrf) return\n"
        if anchor not in s: raise SystemExit('Offline material replay: summary anchor missing')
        replacement = anchor.replace("\n\n  const generate", "\n    // Offline replay: summary GET resolves to the locally saved artifact when disconnected.\n    void generationApi<any>(`/documents/${activeDocumentId}/summarize`).then((res: any) => { if (res?.summary != null) { setSummary(res.summary); setPhase('ready') } }).catch(() => {})\n  }, [activeDocumentId])\n\n  const generate", 1)
        s = s.replace(anchor, replacement, 1)
    if 'Offline replay: flashcards' not in s:
        anchor = "  useEffect(() => {\n    if (activeDocumentId == null) return\n    Promise.all([generationApi<{ csrf_token: string }>('/me'), generationApi<{ title: string }>(`/documents/${activeDocumentId}`)])\n      .then(([me, doc]) => { setCsrf(me.csrf_token); setTitle(doc.title) })\n      .catch(e => setError(e instanceof Error ? e.message : 'Could not load the document.'))\n  }, [activeDocumentId])\n\n  const normalize = (raw: any) => {\n"
        if anchor not in s: raise SystemExit('Offline material replay: flashcards anchor missing')
        replacement = anchor.replace("\n\n  const normalize", "\n    // Offline replay: flashcards GET resolves to the locally saved artifact when disconnected.\n    void generationApi<any>(`/documents/${activeDocumentId}/flashcards`).then((res: any) => { const next = normalize(res?.flashcards ?? res); if (next.length) { setCards(next); setIdx(0); setFlipped(false); setKnown([]); setPhase('review') } }).catch(() => {})\n  }, [activeDocumentId])\n\n  const normalize", 1)
        s = s.replace(anchor, replacement, 1)
    required = ['Offline replay: summary', 'Offline replay: flashcards']
    missing = [x for x in required if x not in s]
    if missing: raise SystemExit('Offline material replay verification failed: ' + ', '.join(missing))
    GEN.write_text(s, encoding='utf-8')


def patch_clean():
    s = CLEAN.read_text(encoding='utf-8')
    if 'Offline replay: practice questions' not in s:
        match = re.search(r'(export function PracticeQuestionsGenerationScreen[\s\S]*?useEffect\(\(\) => \{[^\n]*\}, \[activeDocumentId\]\))', s)
        if not match: raise SystemExit('Offline material replay: practice questions effect missing')
        s = s[:match.end()] + "\n  // Offline replay: the GET endpoint resolves to the saved local artifact when disconnected.\n  useEffect(() => { if (activeDocumentId == null) return; api<any>(`/documents/${activeDocumentId}/quiz`).then(payload => { const next = questionsFrom(payload); if (next.length) { setQuestions(next); setIndex(0); setSelected(null); setScore(0); setPhase('quiz') } }).catch(() => {}) }, [activeDocumentId])" + s[match.end():]
    if 'Offline replay: mind map' not in s:
        match = re.search(r'(export function MindMapGenerationScreen[\s\S]*?useEffect\(\(\) => \{[^\n]*\}, \[activeDocumentId\]\))', s)
        if not match: raise SystemExit('Offline material replay: mind map effect missing')
        s = s[:match.end()] + "\n  // Offline replay: the GET endpoint resolves to the saved local artifact when disconnected.\n  useEffect(() => { if (activeDocumentId == null) return; api<any>(`/documents/${activeDocumentId}/mind-map`).then(payload => { const root = mapRoot(payload); if (root && (typeof root !== 'object' || Object.keys(root).length)) { setMap(root); setPhase('ready') } }).catch(() => {}) }, [activeDocumentId])" + s[match.end():]
    required = ['Offline replay: practice questions', 'Offline replay: mind map']
    missing = [x for x in required if x not in s]
    if missing: raise SystemExit('Offline clean replay verification failed: ' + ', '.join(missing))
    CLEAN.write_text(s, encoding='utf-8')


patch_generation()
patch_clean()
print('Offline replay for saved summaries, flashcards, practice questions, and mind maps applied and verified.')
