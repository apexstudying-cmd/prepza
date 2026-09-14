from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'
IMPORT = "import { PodcastGenerationScreen, FlashcardsGenerationScreen, SummaryGenerationScreen } from './generation/GenerationScreens'\n"

text = APP.read_text(encoding='utf-8')

if IMPORT not in text:
    first_import = text.find("\n", text.find("import "))
    text = text[: first_import + 1] + IMPORT + text[first_import + 1 :]

replacements = [
    (
        '// ─── PODCAST PLAYER',
        '// ─── SUMMARY',
        '''// ─── PODCAST PLAYER\nfunction PodcastPlayerScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {\n  return <PodcastGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />\n}\n\n''',
    ),
    (
        '// ─── FLASHCARDS',
        '// ─── QUIZ',
        '''// ─── FLASHCARDS\nfunction FlashcardsScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {\n  return <FlashcardsGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />\n}\n\n''',
    ),
    (
        '// ─── SUMMARY',
        '// ─── CHATS',
        '''// ─── SUMMARY\nfunction SummaryScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {\n  return <SummaryGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />\n}\n\n''',
    ),
]

for start_marker, end_marker, replacement in replacements:
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit(f'missing start marker: {start_marker}')
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        raise SystemExit(f'missing end marker: {end_marker}')
    current = text[start:end]
    if 'GenerationScreen' not in current:
        text = text[:start] + replacement + text[end:]

APP.write_text(text, encoding='utf-8')
print('Generation UI build transformation applied.')
