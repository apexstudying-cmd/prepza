from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / 'frontend' / 'src' / 'generation' / 'GenerationScreens.tsx'
CLEAN = ROOT / 'frontend' / 'src' / 'generation' / 'StudyGenerationScreensClean.tsx'

# Build-safe placeholder. Generated-material persistence remains enabled.
# Explicit replay UI wiring is deferred until the generation-source transforms
# have a deterministic order that can be verified in production builds.
def main():
    if not GEN.exists() or not CLEAN.exists():
        raise SystemExit('Offline material replay: expected generation sources are missing')
    print('Offline material replay: deferred; generation persistence remains enabled.')

if __name__ == '__main__':
    main()
