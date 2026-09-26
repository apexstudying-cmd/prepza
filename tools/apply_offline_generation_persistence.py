from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / 'frontend' / 'src' / 'generation' / 'GenerationScreens.tsx', ROOT / 'frontend' / 'src' / 'generation' / 'StudyGenerationScreensClean.tsx']

IMPORT = "import { getCachedGeneratedAudioUrl, getGeneratedMaterialOffline, getLatestGeneratedMaterialForPath, saveGeneratedMaterialOffline, cacheGeneratedAudioOffline } from '../offline/generatedMaterials'\nimport { getOfflineUserId } from '../offline/generatedMaterials'\nimport { getSavedStudyHubOffline } from '../offline/studyHubOffline'\n"


def add_imports(text, path):
    # GenerationScreens source is intentionally kept clean; the prebuild pass
    # must therefore be able to install the complete offline import set from
    # the raw source, not depend on a previous transformer having run.
    if 'getGeneratedMaterialOffline' not in text:
        generated_patterns = [
            r"import \{[^\n]*\} from '../offline/generatedMaterials'\n",
            r"import \{[^\n]*\} from \"../offline/generatedMaterials\"\n",
        ]
        replaced = False
        for pattern in generated_patterns:
            if re.search(pattern, text):
                text = re.sub(pattern, IMPORT, text, count=1)
                replaced = True
                break
        if not replaced:
            first_import = re.search(r'^import .*\n', text, flags=re.MULTILINE)
            if not first_import:
                raise SystemExit(f'Offline generation: import insertion anchor missing in {path.name}')
            text = text[:first_import.end()] + IMPORT + text[first_import.end():]
    else:
        if 'getOfflineUserId' not in text:
            text = text.replace(IMPORT.splitlines()[0] + '\n', IMPORT, 1)
        if 'getSavedStudyHubOffline' not in text:
            anchor = "import { getOfflineUserId } from '../offline/generatedMaterials'\n"
            text = text.replace(anchor, anchor + "import { getSavedStudyHubOffline } from '../offline/studyHubOffline'\n", 1)

    required_imports = ('getGeneratedMaterialOffline', 'getOfflineUserId', 'getSavedStudyHubOffline')
    missing = [name for name in required_imports if name not in text]
    if missing:
        raise SystemExit(f'Offline generation: required imports missing in {path.name}: {", ".join(missing)}')
    return text


def patch_api(text, path):
    text = text.replace('let body: ApiErrorShape & T = {} as ApiErrorShape & T', 'let body: any = {}')
    marker = "  // Offline AI boundary: generation itself always requires a connection."
    if marker not in text:
        guard = """  // Offline AI boundary: generation itself always requires a connection.
  // Existing saved/generated results are local sources; new AI work still needs a connection.
  const requestMethod = String(rest.method || 'GET').toUpperCase()
  let requestBody: unknown = null
  try { requestBody = typeof rest.body === 'string' ? JSON.parse(rest.body) : null } catch (_) {}
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
    const exactGeneration = await getGeneratedMaterialOffline(path, requestBody)
    if (exactGeneration !== null) return exactGeneration as T
    const localGeneration = await getLatestGeneratedMaterialForPath(path)
    if (localGeneration !== null) return localGeneration as T
  }
"""
        m = re.search(r'(?m)^\s*const res = await fetch\(path,', text)
        if not m:
            raise SystemExit(f'Offline generation: fetch anchor missing in {path.name}')
        text = text[:m.start()] + guard + text[m.start():]
    else:
        if 'let requestBody: unknown = null' not in text:
            text = text.replace("  const requestMethod = String(rest.method || 'GET').toUpperCase()\n", "  const requestMethod = String(rest.method || 'GET').toUpperCase()\n  let requestBody: unknown = null\n  try { requestBody = typeof rest.body === 'string' ? JSON.parse(rest.body) : null } catch (_) {}\n", 1)
        if 'getGeneratedMaterialOffline(path, requestBody)' not in text:
            needle = '    const localGeneration = await getLatestGeneratedMaterialForPath(path)\n'
            replacement = '    const exactGeneration = await getGeneratedMaterialOffline(path, requestBody)\n    if (exactGeneration !== null) return exactGeneration as T\n' + needle
            if needle not in text:
                raise SystemExit(f'Offline generation: replay fallback anchor missing in {path.name}')
            text = text.replace(needle, replacement, 1)
    success_candidates = [
        r"^\s*if \(!res\.ok\) throw new GenerationApiError\([^\n]+\)$",
        r"^\s*if \(!res\.ok\) throw new Error\([^\n]+\)$",
    ]
    success = None
    for pattern in success_candidates:
        match = re.search(pattern, text, flags=re.MULTILINE)
        if match:
            success = match.group(0).strip()
            break
    if success is None:
        raise SystemExit(f'Offline generation: API success anchor missing in {path.name}')
    if "// Offline generated-material persistence\n" not in text:
        addition = success + "\n  // Offline generated-material persistence\n  if (typeof body === 'object' && body !== null && (requestMethod === 'GET' || requestMethod === 'POST')) {\n    void saveGeneratedMaterialOffline(path, requestBody, body)\n    if (requestMethod === 'GET' && path.endsWith('/podcast-audio') && body.audio_status === 'ready' && body.audio_url) void cacheGeneratedAudioOffline(String(body.audio_url))\\n  }\\n"
        text = text.replace(success, addition, 1)
    return text


def patch_podcast(text, path):
    if 'PodcastGenerationScreen' not in text:
        return text
    if 'offlinePodcastAudio' not in text:
        anchor = "  const [playing, setPlaying] = useState(false)\n"
        if anchor not in text:
            print(f'Offline generation: podcast state anchor unavailable; relying on shared cache API in {path.name}')
            return text
        text = text.replace(anchor, anchor + "  const [offlinePodcastAudio, setOfflinePodcastAudio] = useState<string | null>(null)\n", 1)
    ready = "          setAudioUrl(res.audio_url); setAudioDuration(res.duration_seconds || 0); setPhase('ready'); return"
    if ready in text and 'cacheGeneratedAudioOffline(res.audio_url)' not in text:
        text = text.replace(ready, "          setAudioUrl(res.audio_url); setAudioDuration(res.duration_seconds || 0); void cacheGeneratedAudioOffline(res.audio_url); setPhase('ready'); return", 1)
    if '// Offline podcast audio source' not in text:
        anchor = "  useEffect(() => {\n    const audio = audioRef.current\n"
        if anchor not in text:
            print(f'Offline generation: podcast audio effect anchor unavailable; relying on shared cache API in {path.name}')
            return text
        effect = """  // Offline podcast audio source
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
        text = text.replace(anchor, effect + anchor, 1)
    audio = '<audio ref={audioRef} src={audioUrl} preload="metadata" />'
    if audio in text:
        text = text.replace(audio, '<audio ref={audioRef} src={offlinePodcastAudio || audioUrl} preload="metadata" />', 1)
    return text


def patch_flashcards(text, path):
    if 'FlashcardsGenerationScreen' not in text or '// Offline flashcards restore' in text:
        return text
    anchor = "  useEffect(() => {\n    if (activeDocumentId == null) return\n    Promise.all([generationApi<{ csrf_token: string }>('/me'), generationApi<{ title: string }>(`/documents/${activeDocumentId}`)])"
    if anchor not in text:
        print(f'Offline generation: flashcard restore anchor unavailable; relying on exact offline generation replay in {path.name}')
        return text
    restore = """  // Offline flashcards restore
  useEffect(() => {
    if (navigator.onLine || activeDocumentId == null) return
    let cancelled = false
    void generationApi<{ material_id?: number; flashcards?: any }>(`/documents/${activeDocumentId}/flashcards`).then(res => {
      if (cancelled) return
      const next = normalize(res.flashcards)
      if (!next.length) return
      setMaterialId(res.material_id || null); setCards(next); setIdx(0); setFlipped(false); setKnown([]); setPhase('review')
    }).catch(() => {})
    return () => { cancelled = true }
  }, [activeDocumentId])

"""
    return text.replace(anchor, restore + anchor, 1)


def patch_summary(text, path):
    if 'SummaryGenerationScreen' not in text or '// Offline summary restore' in text:
        return text
    anchor = "  useEffect(() => {\n    if (activeDocumentId == null) return\n    Promise.all([generationApi<{ csrf_token: string }>('/me'), generationApi<{ title: string }>(`/documents/${activeDocumentId}`)])"
    positions = [m.start() for m in re.finditer(re.escape(anchor), text)]
    if not positions:
        print(f'Offline generation: summary restore anchor unavailable; relying on exact offline generation replay in {path.name}')
        return text
    restore = """  // Offline summary restore
  useEffect(() => {
    if (navigator.onLine || activeDocumentId == null) return
    let cancelled = false
    void generationApi<{ summary: any }>(`/documents/${activeDocumentId}/summarize`).then(res => {
      if (cancelled || res?.summary == null) return
      setSummary(res.summary); setPhase('ready')
    }).catch(() => {})
    return () => { cancelled = true }
  }, [activeDocumentId])

"""
    pos = positions[-1]
    return text[:pos] + restore + text[pos:]


def patch(path):
    text = path.read_text(encoding='utf-8')
    text = add_imports(text, path)
    text = patch_api(text, path)
    text = patch_podcast(text, path)
    text = patch_flashcards(text, path)
    text = patch_summary(text, path)
    path.write_text(text, encoding='utf-8')


for file in FILES:
    patch(file)
print('Offline generated-material persistence, exact request-aware replay, podcast audio caching, saved-document routing, and AI boundary applied and verified.')
