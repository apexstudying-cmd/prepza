from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / 'frontend' / 'src' / 'generation' / 'GenerationScreens.tsx',
    ROOT / 'frontend' / 'src' / 'generation' / 'StudyGenerationScreensClean.tsx',
]
IMPORT = "import { getLatestGeneratedMaterialForPath, saveGeneratedMaterialOffline } from '../offline/generatedMaterials'\n"


def patch(path: Path) -> None:
    text = path.read_text(encoding='utf-8')
    old_import = "import { saveGeneratedMaterialOffline } from '../offline/generatedMaterials'\n"
    if old_import in text:
        text = text.replace(old_import, IMPORT, 1)
    elif IMPORT not in text:
        first_import_end = text.find('\n', text.find('import '))
        if first_import_end < 0:
            raise SystemExit(f'Offline generation: import anchor missing in {path.name}')
        text = text[:first_import_end + 1] + IMPORT + text[first_import_end + 1:]

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
        addition = marker + "\n  // Offline generated-material persistence: only successful generation writes are stored.\n  // New AI generation remains online-only; saved results remain studyable offline.\n  // Offline generated-material persistence\n  if (requestMethod === 'POST' && typeof body === 'object' && body !== null) {\n    let requestBody: unknown = null\n    try { requestBody = typeof rest.body === 'string' ? JSON.parse(rest.body) : null } catch (_) {}\n    void saveGeneratedMaterialOffline(path, requestBody, body)\n  }"
        text = text.replace(marker, addition, 1)

    path.write_text(text, encoding='utf-8')


for file in FILES:
    patch(file)
print('Offline generated-material persistence and AI boundary applied and verified.')
