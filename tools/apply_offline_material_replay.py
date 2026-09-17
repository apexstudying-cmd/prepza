from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / 'frontend' / 'src' / 'generation' / 'GenerationScreens.tsx'
CLEAN = ROOT / 'frontend' / 'src' / 'generation' / 'StudyGenerationScreensClean.tsx'


def patch_generation():
    s = GEN.read_text(encoding='utf-8')

    summary_anchor = """  useEffect(() => {\n    if (activeDocumentId == null) return\n    Promise.all([generationApi<{ csrf_token: string }>('/me'), generationApi<{ title: string }>(`/documents/${activeDocumentId}`)])\n      .then(([me, doc]) => { setCsrf(me.csrf_token); setTitle(doc.title) })\n      .catch(e => setError(e instanceof Error ? e.message : 'Could not load the document.'))\n  }, [activeDocumentId])\n\n  const generate = async () => {\n    if (activeDocumentId == null || !csrf) return\n"""
    summary_repl = """  useEffect(() => {\n    if (activeDocumentId == null) return\n    let cancelled = false\n    Promise.all([generationApi<{ csrf_token: string }>('/me'), generationApi<{ title: string }>(`/documents/${activeDocumentId}`)])\n      .then(([me, doc]) => { if (cancelled) return; setCsrf(me.csrf_token); setTitle(doc.title) })\n      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load the document.') })\n    void generationApi<any>(`/documents/${activeDocumentId}/summarize`)\n      .then((res: any) => {\n        if (cancelled || !res) return\n        const saved = res?.summary ?? res\n        if (saved != null) { setSummary(saved); setPhase('ready') }\n      })\n      .catch(() => {})\n    return () => { cancelled = true }\n  }, [activeDocumentId])\n\n  const generate = async () => {\n    if (activeDocumentId == null || !csrf) return\n"""
    if 'Offline replay: summary' not in s:
        if summary_anchor not in s:
            raise SystemExit('Offline material replay: summary anchor missing')
        summary_repl = summary_repl.replace("    void generationApi<any>(`/documents/${activeDocumentId}/summarize`)", "    // Offline replay: summary GET resolves to the locally saved artifact when disconnected.\n    void generationApi<any>(`/documents/${activeDocumentId}/summarize`)", 1)
        s = s.replace(summary_anchor, summary_repl, 1)

    flash_anchor = """  useEffect(() => {\n    if (activeDocumentId == null) return\n    Promise.all([generationApi<{ csrf_token: string }>('/me'), generationApi<{ title: string }>(`/documents/${activeDocumentId}`)])\n      .then(([me, doc]) => { setCsrf(me.csrf_token); setTitle(doc.title) })\n      .catch(e => setError(e instanceof Error ? e.message : 'Could not load the document.'))\n  }, [activeDocumentId])\n\n  const normalize = (raw: any) => {\n"""
    flash_repl = """  useEffect(() => {\n    if (activeDocumentId == null) return\n    let cancelled = false\n    Promise.all([generationApi<{ csrf_token: string }>('/me'), generationApi<{ title: string }>(`/documents/${activeDocumentId}`)])\n      .then(([me, doc]) => { if (cancelled) return; setCsrf(me.csrf_token); setTitle(doc.title) })\n      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load the document.') })\n    void generationApi<any>(`/documents/${activeDocumentId}/flashcards`)\n      .then((res: any) => {\n        if (cancelled || !res) return\n        const next = normalize(res?.flashcards ?? res)\n        if (next.length) { setCards(next); setIdx(0); setFlipped(false); setKnown([]); setPhase('review') }\n      })\n      .catch(() => {})\n    return () => { cancelled = true }\n  }, [activeDocumentId])\n\n  const normalize = (raw: any) => {\n"""
    if 'Offline replay: flashcards' not in s:
        if flash_anchor not in s:
            raise SystemExit('Offline material replay: flashcards anchor missing')
        flash_repl = flash_repl.replace("    void generationApi<any>(`/documents/${activeDocumentId}/flashcards`)", "    // Offline replay: flashcards GET resolves to the locally saved artifact when disconnected.\n    void generationApi<any>(`/documents/${activeDocumentId}/flashcards`)", 1)
        s = s.replace(flash_anchor, flash_repl, 1)

    required = ['Offline replay: summary', 'Offline replay: flashcards']
    missing = [x for x in required if x not in s]
    if missing: raise SystemExit('Offline material replay verification failed: ' + ', '.join(missing))
    GEN.write_text(s, encoding='utf-8')


def patch_clean():
    s = CLEAN.read_text(encoding='utf-8')
    anchor = "  useEffect(() => { if (activeDocumentId == null) return; api<any>('/me').then(v => setCsrf(v.csrf_token || '')).catch(e => setError(e.message)); api<any>(`/documents/${activeDocumentId}`).then(v => setTitle(v.title || 'Practice Questions')).catch(() => {}) }, [activeDocumentId])\n"
    if 'Offline replay: practice questions' not in s:
        if anchor not in s:
            raise SystemExit('Offline material replay: practice questions anchor missing')
        replacement = anchor + "  // Offline replay: the GET endpoint resolves to the saved local artifact when disconnected.\n  useEffect(() => { if (activeDocumentId == null) return; api<any>(`/documents/${activeDocumentId}/quiz`).then(payload => { const next = questionsFrom(payload); if (next.length) { setQuestions(next); setIndex(0); setSelected(null); setScore(0); setPhase('quiz') } }).catch(() => {}) }, [activeDocumentId])\n"
        s = s.replace(anchor, replacement, 1)
    required = ['Offline replay: practice questions']
    missing = [x for x in required if x not in s]
    if missing: raise SystemExit('Offline practice replay verification failed')
    CLEAN.write_text(s, encoding='utf-8')


patch_generation()
patch_clean()
print('Offline replay for saved summaries, flashcards, and practice questions applied and verified.')
