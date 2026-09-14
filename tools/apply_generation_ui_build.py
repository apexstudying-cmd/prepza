from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'
GEN = ROOT / 'frontend' / 'src' / 'generation' / 'GenerationScreens.tsx'
IMPORT = "import { PodcastGenerationScreen, FlashcardsGenerationScreen, SummaryGenerationScreen } from './generation/GenerationScreens'\n"
STUDY_IMPORT = "import { PracticeQuestionsGenerationScreen, MindMapGenerationScreen } from './generation/StudyGenerationScreensClean'\n"

text = APP.read_text(encoding='utf-8')
gen_text = GEN.read_text(encoding='utf-8')

if IMPORT not in text:
    first_import = text.find("\n", text.find("import "))
    text = text[: first_import + 1] + IMPORT + text[first_import + 1 :]
if STUDY_IMPORT not in text:
    first_import = text.find("\n", text.find("import "))
    text = text[: first_import + 1] + STUDY_IMPORT + text[first_import + 1 :]

# The generation components were intentionally kept as a standalone module.
# Convert their palette to CSS light-dark() values at build time so the same
# components follow the device/browser color preference without duplicating UI.
old_palette = """const C = {
  navy: '#0B1437',
  navy2: '#162342',
  navy3: '#24345B',
  gold: '#C9A84C',
  goldLight: '#E3C873',
  text: '#172033',
  muted: '#7A8498',
  page: '#F7F8FB',
  card: '#FFFFFF',
  border: '#E7E9EF',
  green: '#4CC97B',
  red: '#C94C4C',
}
"""
new_palette = """const C = {
  navy: '#0B1437',
  navy2: '#162342',
  navy3: '#24345B',
  gold: 'light-dark(#C9A84C, #D5B65A)',
  goldLight: 'light-dark(#E3C873, #E6CC7A)',
  text: 'light-dark(#172033, #F4F6FB)',
  muted: 'light-dark(#7A8498, #9AA6BE)',
  page: 'light-dark(#F7F8FB, #080D1D)',
  card: 'light-dark(#FFFFFF, #101A31)',
  border: 'light-dark(#E7E9EF, #263554)',
  green: 'light-dark(#4CC97B, #62D991)',
  red: 'light-dark(#C94C4C, #FF7777)',
}
"""
if old_palette in gen_text:
    gen_text = gen_text.replace(old_palette, new_palette, 1)
# These two hard-coded neutrals are also visible on the generated config cards.
gen_text = gen_text.replace("background: disabled ? '#D9DDE5' :", "background: disabled ? 'light-dark(#D9DDE5, #29344C)' :", 1)
gen_text = gen_text.replace("border: `2px solid ${selected ? C.gold : '#B9BFCC}'`", "border: `2px solid ${selected ? C.gold : 'light-dark(#B9BFCC, #66718A)'}`", 1)
GEN.write_text(gen_text, encoding='utf-8')

replacements = [
    ('// ─── PODCAST PLAYER', '// ─── SUMMARY', '''// ─── PODCAST PLAYER
function PodcastPlayerScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  return <div style={{ colorScheme: 'light dark', flex: 1, minHeight: 0 }}><PodcastGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} /></div>
}

'''),
    ('// ─── FLASHCARDS', '// ─── QUIZ', '''// ─── FLASHCARDS
function FlashcardsScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  return <div style={{ colorScheme: 'light dark', flex: 1, minHeight: 0 }}><FlashcardsGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} /></div>
}

'''),
    ('// ─── SUMMARY', '// ─── CHATS', '''// ─── SUMMARY
function SummaryScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  return <div style={{ colorScheme: 'light dark', flex: 1, minHeight: 0 }}><SummaryGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} /></div>
}

'''),
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
    elif '<div style={{ colorScheme:' not in current:
        text = text[:start] + replacement + text[end:]


def replace_section(start_marker: str, replacement: str, aliases: tuple[str, ...] = ()):
    global text
    markers = (start_marker,) + aliases
    start = -1
    marker_used = None
    for marker in markers:
        pos = text.find(marker)
        if pos >= 0 and (start < 0 or pos < start):
            start, marker_used = pos, marker
    if start < 0:
        return
    match = re.search(r'// ─── [^\n]+', text[start + len(marker_used):])
    if not match:
        raise SystemExit(f'missing end section marker after: {marker_used}')
    end = start + len(marker_used) + match.start()
    current = text[start:end]
    if 'GenerationScreen' not in current:
        text = text[:start] + replacement + text[end:]

replace_section('// ─── QUIZ', '''// ─── QUIZ
function QuizScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  return <PracticeQuestionsGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
}

''')
replace_section('// ─── MIND MAP', '''// ─── MIND MAP
function MindMapScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  return <MindMapGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
}

''', aliases=('// ─── MINDMAP',))

APP.write_text(text, encoding='utf-8')
print('Generation UI build transformation applied.')
