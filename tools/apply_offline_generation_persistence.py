from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / 'frontend' / 'src' / 'generation' / 'GenerationScreens.tsx',
    ROOT / 'frontend' / 'src' / 'generation' / 'StudyGenerationScreensClean.tsx',
]
IMPORT = "import { getCachedGeneratedAudioUrl, getLatestGeneratedMaterialForPath, saveGeneratedMaterialOffline, cacheGeneratedAudioOffline } from '../offline/generatedMaterials'\n"


def patch(path: Path) -> None:
    text = path.read_text(encoding='utf-8')
    old_import = "import { saveGeneratedMaterialOffline } from '../offline/generatedMaterials'\n"
    if old_import in text:
        text = text.replace(old_import, IMPORT, 1)
    elif "getLatestGeneratedMaterialForPath" not in text:
        first_import_end = text.find('\n', text.find('import '))
        if first_import_end < 0:
            raise SystemExit(f'Offline generation: import anchor missing in {path.name}')
        text = text[:first_import_end + 1] + IMPORT + text[first_import_end + 1:]

    # Keep the API response deliberately runtime-shaped. Generated endpoint
    # responses vary by material type, so the persistence layer must not make
    # the generic T type pretend that every response has every media field.
    text = text.replace('let body: ApiErrorShape & T = {} as ApiErrorShape & T', 'let body: any = {}')

    guard = "  // Offline AI boundary: generation itself always requires a connection."
    if guard not in text:
        guard_code = """  // Offline AI boundary: generation itself always requires a connection.
  // Previously generated results are persisted locally and remain studyable offline.
  const requestMethod = String(rest.method || 'GET').toUpperCase()
  if (!navigator.onLine && requestMethod !== 'GET') {
    throw new Error('AI generation requires an internet connection. Your saved study materials are still available offline.')
  }
  if (!navigator.onLine && requestMethod === 'GET') {
    const localGeneration = await getLatestGeneratedMaterialForPath(path)
    if (localGeneration !== null) return localGeneration as T
  }
"""
        match = re.search(r'(?m)^(\s*)const res = await fetch\(path,', text)
        if not match:
            raise SystemExit(f'Offline generation: fetch anchor missing in {path.name}')
        insert_at = match.start()
        text = text[:insert_at] + guard_code + text[insert_at:]

    marker = "  if (!res.ok) throw new GenerationApiError(body?.error || body?.message || `Request failed (${res.status})`, res.status)"
    if marker not in text:
        marker = "  if (!res.ok) throw new Error(body?.error || body?.message || `Request failed (${res.status})`)"
    if marker not in text:
        raise SystemExit(f'Offline generation: API success anchor missing in {path.name}')

    persistence = "  // Offline generated-material persistence\n"
    if persistence not in text:
        addition = marker + "\n  // Offline generated-material persistence: successful generation responses are stored locally.\n  // This includes GET status/result responses so generated materials can be reopened offline.\n  if (typeof body === 'object' && body !== null && (requestMethod === 'GET' || requestMethod === 'POST')) {\n    let requestBody: unknown = null\n    try { requestBody = typeof rest.body === 'string' ? JSON.parse(rest.body) : null } catch (_) {}\n    void saveGeneratedMaterialOffline(path, requestBody, body)\n    if (requestMethod === 'GET' && path.endsWith('/podcast-audio') && body.audio_status === 'ready' && body.audio_url) {\n      void cacheGeneratedAudioOffline(String(body.audio_url))\n    }\n  }\n  // Offline generated-material persistence\n"
        text = text.replace(marker, addition, 1)

    # Podcast audio playback: online signed URLs are cached, and offline opens use the cached bytes.
    if 'getCachedGeneratedAudioUrl' in text and 'offlinePodcastAudio' not in text and 'PodcastGenerationScreen' in text:
        hook_anchor = "  const [playing, setPlaying] = useState(false)\n"
        if hook_anchor not in text:
            raise SystemExit(f'Offline generation: podcast state anchor missing in {path.name}')
        text = text.replace(hook_anchor, hook_anchor + "  const [offlinePodcastAudio, setOfflinePodcastAudio] = useState<string | null>(null)\n", 1)

        ready_anchor = "          setAudioUrl(res.audio_url); setAudioDuration(res.duration_seconds || 0); setPhase('ready'); return"
        ready_replacement = "          setAudioUrl(res.audio_url); setAudioDuration(res.duration_seconds || 0); void cacheGeneratedAudioOffline(res.audio_url); setPhase('ready'); return"
        if ready_anchor not in text:
            raise SystemExit(f'Offline generation: podcast ready anchor missing in {path.name}')
        text = text.replace(ready_anchor, ready_replacement, 1)

        effect_anchor = "  useEffect(() => {\n    const audio = audioRef.current\n"
        if effect_anchor not in text:
            raise SystemExit(f'Offline generation: podcast audio effect anchor missing in {path.name}')
        offline_effect = """  useEffect(() => {
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

        audio_src_anchor = '<audio ref={audioRef} src={audioUrl} preload="metadata" />'
        if audio_src_anchor not in text:
            raise SystemExit(f'Offline generation: podcast audio element anchor missing in {path.name}')
        text = text.replace(audio_src_anchor, '<audio ref={audioRef} src={offlinePodcastAudio || audioUrl} preload="metadata" />', 1)

    path.write_text(text, encoding='utf-8')


for file in FILES:
    patch(file)
print('Offline generated-material persistence, podcast audio caching, and AI boundary applied and verified.')
