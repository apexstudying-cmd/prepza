from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / 'frontend' / 'src' / 'generation' / 'GenerationScreens.tsx',
    ROOT / 'frontend' / 'src' / 'generation' / 'StudyGenerationScreensClean.tsx',
]
IMPORT = "import { saveGeneratedMaterialOffline } from '../offline/generatedMaterials'\n"


def patch(path: Path) -> None:
    text = path.read_text(encoding='utf-8')
    if IMPORT not in text:
        first_import_end = text.find('\n', text.find('import '))
        if first_import_end < 0:
            raise SystemExit(f'Offline generation: import anchor missing in {path.name}')
        text = text[:first_import_end + 1] + IMPORT + text[first_import_end + 1:]

    if 'Offline generated-material persistence' in text:
        path.write_text(text, encoding='utf-8')
        return

    marker = "  if (!res.ok) throw new GenerationApiError(body?.error || body?.message || `Request failed (${res.status})`, res.status)"
    if marker not in text:
        marker = "  if (!res.ok) throw new Error(body?.error || body?.message || `Request failed (${res.status})`)"
    if marker not in text:
        raise SystemExit(f'Offline generation: API success anchor missing in {path.name}')

    addition = marker + "\n  // Offline generated-material persistence: only successful generation writes are stored.\n  // New AI generation remains online-only; saved results remain studyable offline.\n  // Offline generated-material persistence\n  if (String(rest.method || 'GET').toUpperCase() === 'POST' && typeof body === 'object' && body !== null) {\n    let requestBody: unknown = null\n    try { requestBody = typeof rest.body === 'string' ? JSON.parse(rest.body) : null } catch (_) {}\n    void saveGeneratedMaterialOffline(path, requestBody, body)\n  }"
    text = text.replace(marker, addition, 1)
    path.write_text(text, encoding='utf-8')


for file in FILES:
    patch(file)
print('Offline generated-material persistence applied and verified.')
