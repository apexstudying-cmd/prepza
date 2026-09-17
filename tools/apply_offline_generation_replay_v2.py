from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / 'frontend' / 'src' / 'generation' / 'GenerationScreens.tsx',
    ROOT / 'frontend' / 'src' / 'generation' / 'StudyGenerationScreensClean.tsx',
]

OLD = """  // Offline AI boundary: generation itself always requires a connection.\n  // Saved StudyHub metadata and previously generated results are local sources.\n  const requestMethod = String(rest.method || 'GET').toUpperCase()\n  if (!navigator.onLine && requestMethod !== 'GET') {\n    throw new Error('AI generation requires an internet connection. Your saved study materials are still available offline.')\n  }\n  if (!navigator.onLine && requestMethod === 'GET') {\n    const offlineUserId = getOfflineUserId()\n    if (path === '/me' && offlineUserId) return { id: Number(offlineUserId), csrf_token: '' } as T\n    const documentMatch = path.match(/^\\/documents\\/(\\d+)$/)\n    if (documentMatch && offlineUserId) {\n      const saved = await getSavedStudyHubOffline(Number(documentMatch[1]), Number(offlineUserId))\n      if (saved) return { id: saved.documentId, title: saved.title || 'Saved document', page_count: saved.pageCount || null, file_type: saved.fileType || 'pdf' } as T\n    }\n    const localGeneration = await getLatestGeneratedMaterialForPath(path)\n    if (localGeneration !== null) return localGeneration as T\n  }\n"""

NEW = """  // Offline AI boundary: generation itself requires a connection only when\n  // the exact requested material has not already been generated and stored\n  // locally. This makes existing summaries/quizzes/flashcards/mind maps and\n  // podcast results reopenable after restart with zero network dependency.\n  const requestMethod = String(rest.method || 'GET').toUpperCase()\n  if (!navigator.onLine) {\n    const offlineUserId = getOfflineUserId()\n    if (path === '/me' && offlineUserId) return { id: Number(offlineUserId), csrf_token: '' } as T\n    const documentMatch = path.match(/^\\/documents\\/(\\d+)$/)\n    if (documentMatch && offlineUserId) {\n      const saved = await getSavedStudyHubOffline(Number(documentMatch[1]), Number(offlineUserId))\n      if (saved) return { id: saved.documentId, title: saved.title || 'Saved document', page_count: saved.pageCount || null, file_type: saved.fileType || 'pdf' } as T\n    }\n\n    let requestBody: unknown = null\n    try { requestBody = typeof rest.body === 'string' ? JSON.parse(rest.body) : null } catch (_) {}\n    const localGeneration = await getGeneratedMaterialOffline(path, requestBody)\n    if (localGeneration !== null) return localGeneration as T\n\n    if (requestMethod !== 'GET') {\n      throw new Error('AI generation requires an internet connection. Your saved study materials are still available offline.')\n    }\n  }\n"""

IMPORT_OLD = "import { getCachedGeneratedAudioUrl, getLatestGeneratedMaterialForPath, saveGeneratedMaterialOffline, cacheGeneratedAudioOffline } from '../offline/generatedMaterials'\n"
IMPORT_NEW = "import { getCachedGeneratedAudioUrl, getLatestGeneratedMaterialForPath, getGeneratedMaterialOffline, saveGeneratedMaterialOffline, cacheGeneratedAudioOffline } from '../offline/generatedMaterials'\n"

for path in FILES:
    text = path.read_text(encoding='utf-8')
    if 'getGeneratedMaterialOffline' not in text:
        if IMPORT_OLD not in text:
            raise SystemExit(f'Offline replay v2: generated-material import anchor missing in {path.name}')
        text = text.replace(IMPORT_OLD, IMPORT_NEW, 1)
    if OLD not in text:
        raise SystemExit(f'Offline replay v2: expected offline guard missing in {path.name}')
    text = text.replace(OLD, NEW, 1)
    path.write_text(text, encoding='utf-8')

print('Offline generation replay v2: exact local material lookup enabled for GET and previously generated POST requests.')
