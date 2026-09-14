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
gen_text = gen_text.replace("background: disabled ? '#D9DDE5' :", "background: disabled ? 'light-dark(#D9DDE5, #29344C)' :", 1)
gen_text = gen_text.replace("border: `2px solid ${selected ? C.gold : '#B9BFCC}'`", "border: `2px solid ${selected ? C.gold : 'light-dark(#B9BFCC, #66718A)'}`", 1)
gen_text = gen_text.replace("{ pages: 10, label: 'Comprehensive summary', description: 'Maximum detail within the summary format.' },", "{ pages: 10, label: 'Extended summary', description: 'More room for detail, examples, and connections.' },\n  { pages: 20, label: 'Deep comprehensive summary', description: 'Maximum depth for long-form study and exam preparation.' },", 1)
GEN.write_text(gen_text, encoding='utf-8')

scroll_style = "colorScheme: 'light dark', flex: 1, minHeight: 0, minWidth: 0, overflowY: 'auto', overflowX: 'hidden', WebkitOverflowScrolling: 'touch'"
base_style = "colorScheme: 'light dark', flex: 1, minHeight: 0"
text = text.replace(base_style, scroll_style)

replacements = [
    ('// ─── PODCAST PLAYER', '// ─── SUMMARY', '''// ─── PODCAST PLAYER
function PodcastPlayerScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  return <div style={{ colorScheme: 'light dark', flex: 1, minHeight: 0, minWidth: 0, overflowY: 'auto', overflowX: 'hidden', WebkitOverflowScrolling: 'touch', background: 'light-dark(#F7F8FB,#080D1D)' }}><PodcastGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} /></div>
}

'''),
    ('// ─── FLASHCARDS', '// ─── QUIZ', '''// ─── FLASHCARDS
function FlashcardsScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  return <div style={{ colorScheme: 'light dark', flex: 1, minHeight: 0, minWidth: 0, overflowY: 'auto', overflowX: 'hidden', WebkitOverflowScrolling: 'touch', background: 'light-dark(#F7F8FB,#080D1D)' }}><FlashcardsGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} /></div>
}

'''),
    ('// ─── SUMMARY', '// ─── CHATS', '''// ─── SUMMARY
function SummaryScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  return <div style={{ colorScheme: 'light dark', flex: 1, minHeight: 0, minWidth: 0, overflowY: 'auto', overflowX: 'hidden', WebkitOverflowScrolling: 'touch', background: 'light-dark(#F7F8FB,#080D1D)' }}><SummaryGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} /></div>
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

text = text.replace(
    "return <PracticeQuestionsGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />",
    "return <div style={{ flex: 1, minHeight: 0, minWidth: 0, overflowY: 'auto', overflowX: 'hidden', WebkitOverflowScrolling: 'touch', background: 'light-dark(#F7F8FB,#080D1D)' }}><PracticeQuestionsGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} /></div>"
)
text = text.replace(
    "return <MindMapGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />",
    "return <div style={{ flex: 1, minHeight: 0, minWidth: 0, overflowY: 'auto', overflowX: 'hidden', WebkitOverflowScrolling: 'touch', background: 'light-dark(#F7F8FB,#080D1D)' }}><MindMapGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} /></div>"
)

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
  return <div style={{ flex: 1, minHeight: 0, minWidth: 0, overflowY: 'auto', overflowX: 'hidden', WebkitOverflowScrolling: 'touch', background: 'light-dark(#F7F8FB,#080D1D)' }}><PracticeQuestionsGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} /></div>
}

''')
replace_section('// ─── MIND MAP', '''// ─── MIND MAP
function MindMapScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  return <div style={{ flex: 1, minHeight: 0, minWidth: 0, overflowY: 'auto', overflowX: 'hidden', WebkitOverflowScrolling: 'touch', background: 'light-dark(#F7F8FB,#080D1D)' }}><MindMapGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId} /></div>
}

''', aliases=('// ─── MINDMAP',))

# Remove the actual document-study interstitial, not merely its label.
# The study screen itself already fetches the document and renders a usable shell,
# so navigation is immediate while the document request resolves.
doc_loading_block = '''  // Only pending while there's an active document whose fetch hasn't yet
  // resolved (success or error) - if no document is selected, this stays
  // false so the "no document selected" state below can render immediately.
  const docLoading = activeDocumentId != null && doc === null && !docLoadError
  if (docLoading) return <SkeletonDocument />

'''
if doc_loading_block in text:
    text = text.replace(doc_loading_block, '', 1)
else:
    # Idempotent fallback for whitespace/comment drift.
    text = re.sub(r"\s*// Only pending while there's an active document[\s\S]*?if \(docLoading\) return <SkeletonDocument />\n", "\n", text, count=1)

# Remove any stale visible label from older generated variants.
text = text.replace('Opening document…', '')
text = text.replace('Opening document...', '')
text = text.replace('Opening document', '')

APP.write_text(text, encoding='utf-8')
print('Generation UI build transformation applied.')
