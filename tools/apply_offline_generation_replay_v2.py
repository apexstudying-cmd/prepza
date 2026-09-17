from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / 'frontend' / 'src' / 'generation' / 'GenerationScreens.tsx',
    ROOT / 'frontend' / 'src' / 'generation' / 'StudyGenerationScreensClean.tsx',
]

# This pass is a validator only. The persistence pass owns the actual source
# transformation; keeping this check deterministic prevents build-time source
# rewrites from fighting each other.
REQUIRED = [
    'getGeneratedMaterialOffline',
    'const requestMethod = String(rest.method || \'GET\').toUpperCase()',
    'let requestBody: unknown = null',
    'getGeneratedMaterialOffline(path, requestBody)',
    '// Offline AI boundary: generation itself always requires a connection.',
]

for path in FILES:
    text = path.read_text(encoding='utf-8')
    missing = [needle for needle in REQUIRED if needle not in text]
    if missing:
        raise SystemExit(
            f"Offline generation replay v2: exact replay wiring missing in {path.name}: "
            + ', '.join(missing)
        )

print('Offline generation replay v2: exact request-aware replay wiring validated.')
