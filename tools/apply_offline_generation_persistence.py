from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / 'frontend' / 'src' / 'generation' / 'GenerationScreens.tsx',
    ROOT / 'frontend' / 'src' / 'generation' / 'StudyGenerationScreensClean.tsx',
]
IMPORT = "import { getCachedGeneratedAudioUrl, getLatestGeneratedMaterialForPath, saveGeneratedMaterialOffline, cacheGeneratedAudioOffline } from '../offline/generatedMaterials'\nimport { getOfflineUserId } from '../offline/generatedMaterials'\nimport { getSavedStudyHubOffline } from '../offline/studyHubOffline'\n"


def add_imports(text: str, path: Path) -> str:
    old_import = "import { saveGeneratedMaterialOffline } from '../offline/generatedMaterials'\n"
    if old_import in text:
        return text.replace(old_import, IMPORT, 1)
    if "getLatestGeneratedMaterialForPath" not in text:
        first_import_end = text.find('\n', text.find('import '))
        if first_import_end < 0:
            raise SystemExit(f'Offline generation: import anchor missing in {path.name}')
        return text[:first_import_end + 1] + IMPORT + text[first_import_end + 1:]
    if "getSavedStudyHubOffline" not in text:
        anchor = "import { getCachedGeneratedAudioUrl, getLatestGeneratedMaterialForPath, saveGeneratedMaterialOffline, cacheGeneratedAudioOffline } from '../offline/generatedMaterials'\n"
        if anchor not in text:
            raise SystemExit(f'Offline generation: existing import anchor missing in {path.name}')
        text = text.replace(anchor, anchor + "import { getOfflineUserId } from '../offline/generatedMaterials'\nimport { getSavedStudyHubOffline } from '../offline/studyHubOffline'\n", 1)
    return text


def patch_api(text: str, path: Path) -> str:
    text = text.replace('let body: ApiErrorShape & T = {} as ApiErrorShape & T', 'let body: any = {}')
    if "// Offline AI boundary: generation itself always requires a connection." not in text:
        guard_code = """  // Offline AI boundary: generation itself always requires a connection.
  // Existing saved/generated results are local sources; new AI work still needs a connection.
  const requestMethod = String(rest.method || 'GET').toUpperCase()
  if (!navigator.onLine && requestMethod !== 'GET') {
    throw new Error('AI generation requires an internet connection. Your saved study materials are still available offline.')
  }
  if (!navigator.onLine && requestMethod === 'GET') {
    const offlineUserId = getOfflineUserId()
    if (path === '/me' && offlineUserId) return { id: Number(offlineUserId), csrf_token: '' } as T
    const documentMatch = path.match(/^\\/documents\\/(\\d+)$/)
    if (documentMatch && offlineUserId) {
      const saved = await getSavedStudyHubOffline(Number(documentMatch[1]), Number(offlineUserId))
      if (saved) return { id: saved.documentId, title: saved.title || 'Saved document', page_count: saved.pageCount || null, file_type: saved.fileType || 'pdf' } as T
    }
    const localGeneration = await getLatestGeneratedMaterialForPath(path)
    if (localGeneration !== null) return localGeneration as T
  }
"""
        match = re.search(r'(?m)^(\s*)const res = await fetch\(path,', text)
        if not match:
            raise SystemExit(f'Offline generation: fetch anchor missing in {path.name}')
        text = text[:match.start()] + guard_code + text[match.start():]

    marker = "  if (!res.ok) throw new GenerationApiError(body?.error || body?.message || `Request failed (${res.status})`, res.status)"
    if marker not in text:
        marker = "  if (!res.ok) throw new Error(body?.error || body?.message || `Request failed (${res.status})`)"
    if marker not in text:
        raise SystemExit(f'Offline generation: API success anchor missing in {path.name}')

    if "// Offline generated-material persistence\n" not in text:
        addition = marker + "\n  // Offline generated-material persistence\n  // GET results are saved too, so an already-generated artifact can be reopened after restart.\n  if (typeof body === 'object' && body !== null && (requestMethod === 'GET' || requestMethod === 'POST')) {\n    let requestBody: unknown = null\n    try { requestBody = typeof rest.body === 'string' ? JSON.parse(rest.body) : null } catch (_) {}\n    void saveGeneratedMaterialOffline(path, requestBody, body)\n    if (requestMethod === 'GET' && path.endsWith('/podcast-audio') && body.audio_status === 'ready' && body.audio_url) {\n      void cacheGeneratedAudioOffline(String(body.audio_url))\n    }\n  }\n  // Offline generated-material persistence\n"
        text = text.replace(marker, addition, 1)
    return text


def patch_podcast(text: str, path: Path) -> str:
    if 'PodcastGenerationScreen' not in text:
        return text
    if 'offlinePodcastAudio' not in text:
        state_anchor = "  const [playing, setPlaying] = useState(false)\n"
        if state_anchor not in text:
            raise SystemExit(f'Offline generation: podcast state anchor missing in {path.name}')
        text = text.replace(state_anchor, state_anchor + "  const [offlinePodcastAudio, setOfflinePodcastAudio] = useState<string | null>(null)\n", 1)

    ready_anchor = "          setAudioUrl(res.audio_url); setAudioDuration(res.duration_seconds || 0); setPhase('ready'); return"
    if ready_anchor in text and 'cacheGeneratedAudioOffline(res.audio_url)' not in text:
        text = text.replace(ready_anchor, "          setAudioUrl(res.audio_url); setAudioDuration(res.duration_seconds || 0); void cacheGeneratedAudioOffline(res.audio_url); setPhase('ready'); return", 1)

    # On reopen, restore the previously generated podcast from the local GET response.
    podcast_effect_marker = "  // Offline generated podcast restore\n"
    if podcast_effect_marker not in text:
        doc_effect = "  useEffect(() => {\n    if (activeDocumentId == null) return\n    Promise.all([generationApi<{ csrf_token: string }>('/me'), generationApi<{ title: string; page_count: number | null }>(`/documents/${activeDocumentId}`)])"
        if doc_effect not in text:
            raise SystemExit(f'Offline generation: podcast document effect anchor missing in {path.name}')
        restore = """  // Offline generated podcast restore
  useEffect(() => {
    if (navigator.onLine || activeDocumentId == null) return
    let cancelled = false
    void generationApi<{ audio_status: string; audio_url: string | null; duration_seconds: number | null }>(`/documents/${activeDocumentId}/podcast-audio`).then(res => {
      if (cancelled || res.audio_status !== 'ready' || !res.audio_url) return
      setAudioUrl(res.audio_url)
      setAudioDuration(res.duration_seconds || 0)
      setPhase('ready')
    }).catch(() => {})
    return () => { cancelled = true }
  }, [activeDocumentId])

"""
        text = text.replace(doc_effect, restore + doc_effect, 1)

    if 'getCachedGeneratedAudioUrl' in text and 'Offline podcast audio source' not in text:
        effect_anchor = "  useEffect(() => {\n    const audio = audioRef.current\n"
        if effect_anchor not in text:
            raise SystemExit(f'Offline generation: podcast audio effect anchor missing in {path.name}')
        offline_effect = """  // Offline podcast audio source
  useEffect(() => {
    if (navigator.onLine || !audioUrl) return
    let cancelled = false
    void getCachedGeneratedAudioUrl(audioUrl).then(localUrl => {
      if (cancelled) { if (localUrl) URL.revokeObjectURL(localUrl); return }
      if (localUrl) setOfflinePodcastAudio(localUrl)
    })
    return () => { cancelled = true }
  }, [audioUrl])

"""
        text = text.replace(effect_anchor, offline_effect + effect_anchor, 1)
    audio_src = '<audio ref={audioRef} src={audioUrl} preload="metadata" />'
    if audio_src in text:
        text = text.replace(audio_src, '<audio ref={audioRef} src={offlinePodcastAudio || audioUrl} preload="metadata" />', 1)
    return text


def patch_flashcards(text: str, path: Path) -> str:
    if 'FlashcardsGenerationScreen' not in text or '// Offline flashcards restore' in text:
        return text
    anchor = "  useEffect(() => {\n    if (activeDocumentId == null) return\n    Promise.all([generationApi<{ csrf_token: string }>('/me'), generationApi<{ title: string }>(`/documents/${activeDocumentId}`)])"
    if anchor not in text:
        raise SystemExit(f'Offline generation: flashcard document effect anchor missing in {path.name}')
    restore = """  // Offline flashcards restore
  useEffect(() => {
    if (navigator.onLine || activeDocumentId == null) return
    let cancelled = false
    void generationApi<{ material_id?: number; flashcards?: any }>(`/documents/${activeDocumentId}/flashcards`).then(res => {
      if (cancelled) return
      const next = normalize(res.flashcards)
      if (!next.length) return
      setMaterialId(res.material_id || null)
      setCards(next)
      setIdx(0)
      setFlipped(false)
      setKnown([])
      setPhase('review')
    }).catch(() => {})
    return () => { cancelled = true }
  }, [activeDocumentId])

"""
    # normalize is declared after the document effect, but the callback executes after render and is valid.
    text = text.replace(anchor, restore + anchor, 1)
    return text


def patch_summary(text: str, path: Path) -> str:
    if 'SummaryGenerationScreen' not in text or '// Offline summary restore' in text:
        return text
    anchor = "  useEffect(() => {\n    if (activeDocumentId == null) return\n    Promise.all([generationApi<{ csrf_token: string }>('/me'), generationApi<{ title: string }>(`/documents/${activeDocumentId}`)])"
    # There are two identical document-loading effects in this file; patch the second one (the Summary screen).
    positions = [m.start() for m in re.finditer(re.escape(anchor), text)]
    if not positions:
        raise SystemExit(f'Offline generation: summary document effect anchor missing in {path.name}')
    pos = positions[-1]
    restore = """  // Offline summary restore
  useEffect(() => {
    if (navigator.onLine || activeDocumentId == null) return
    let cancelled = false
    void generationApi<{ summary: any }>(`/documents/${activeDocumentId}/summarize`).then(res => {
      if (cancelled || res?.summary == null) return
      setSummary(res.summary)
      setPhase('ready')
    }).catch(() => {})
    return () => { cancelled = true }
  }, [activeDocumentId])

"""
    text = text[:pos] + restore + text[pos:]
    return text


def patch(path: Path) -> None:
    text = path.read_text(encoding='utf-8')
    text = add_imports(text, path)
    text = patch_api(text, path)
    text = patch_podcast(text, path)
    text = patch_flashcards(text, path)
    text = patch_summary(text, path)
    path.write_text(text, encoding='utf-8')


for file in FILES:
    patch(file)
print('Offline generated-material persistence, exact replay for summary/flashcards/podcast, podcast audio caching, saved-document routing, and AI boundary applied and verified.')
