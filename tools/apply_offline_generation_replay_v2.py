from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / 'frontend' / 'src' / 'generation' / 'GenerationScreens.tsx',
    ROOT / 'frontend' / 'src' / 'generation' / 'StudyGenerationScreensClean.tsx',
]

IMPORT_OLD = "import { getCachedGeneratedAudioUrl, getLatestGeneratedMaterialForPath, saveGeneratedMaterialOffline, cacheGeneratedAudioOffline } from '../offline/generatedMaterials'\n"
IMPORT_NEW = "import { getCachedGeneratedAudioUrl, getLatestGeneratedMaterialForPath, getGeneratedMaterialOffline, saveGeneratedMaterialOffline, cacheGeneratedAudioOffline } from '../offline/generatedMaterials'\n"

for path in FILES:
    text = path.read_text(encoding='utf-8')
    if 'getGeneratedMaterialOffline' not in text and IMPORT_OLD in text:
        text = text.replace(IMPORT_OLD, IMPORT_NEW, 1)
    # The persistence pass already installs the offline guard. Do not attempt
    # a second brittle source transformation; this script is intentionally
    # idempotent and build-safe.
    if '// Offline AI boundary: generation itself always requires a connection.' not in text:
        raise SystemExit(f'Offline replay v2: offline persistence guard missing in {path.name}')
    path.write_text(text, encoding='utf-8')

print('Offline generation replay v2: build-safe validation passed; persistence guard retained.')
