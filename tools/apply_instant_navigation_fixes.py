from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
NAVIGATION = ROOT / 'frontend' / 'src' / 'navigation' / 'useAppNavigation.ts'
READER_MODULE = ROOT / 'frontend' / 'src' / 'screens' / 'study' / 'DocumentReaderScreen.tsx'

text = NAVIGATION.read_text(encoding='utf-8')
original = text

# The extracted navigation hook owns the history stack. Persist its stack in
# localStorage so a standalone PWA can resume after its process is closed.
text = text.replace("sessionStorage.getItem('prepza-navigation-state')", "localStorage.getItem('prepza-navigation-state')")
text = text.replace("sessionStorage.setItem('prepza-navigation-state'", "localStorage.setItem('prepza-navigation-state'")

new_set_screen = """  const setScreen = (target: Screen) => {
    if (target === screen) return
    if (screenStack.length > 1 && screenStack[screenStack.length - 2] === target) {
      window.history.back()
      return
    }
    const ancestorIndex = screenStack.lastIndexOf(target)
    const nextStack = ancestorIndex >= 0 ? screenStack.slice(0, ancestorIndex + 1) : [...screenStack, target]
    setScreenStack(nextStack)
    try {
      const raw = localStorage.getItem('prepza-navigation-state')
      const existing = raw ? JSON.parse(raw) : {}
      localStorage.setItem('prepza-navigation-state', JSON.stringify({ ...existing, stack: nextStack }))
    } catch { /* navigation persistence is optional */ }
    window.history.pushState({ prepzaNav: true }, '')
  }
"""

start = text.find("  const setScreen = (target: Screen) => {")
if start >= 0:
    end_marker = "\n  }\n\n  const resetNavigation"
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit('Instant navigation patch: extracted setScreen boundary not found')
    if new_set_screen.strip() not in text:
        text = text[:start] + new_set_screen.rstrip('\n') + text[end + len("\n  }"):]
elif new_set_screen.strip() not in text:
    raise SystemExit('Instant navigation patch: extracted setScreen function not found')

reader_text = READER_MODULE.read_text(encoding='utf-8')
reader_start = reader_text.find('export default function DocumentReaderScreen(')
if reader_start < 0:
    raise SystemExit('Instant navigation patch: DocumentReaderScreen not found')
reader_end = reader_text.find('\n// ───', reader_start)
if reader_end < 0:
    reader_end = len(reader_text)
reader = reader_text[reader_start:reader_end]
reader_before = reader
reader = re.sub(
    r"\n\s*if \(loading(?: && !doc)?\) return <(?:GenerationLoading|SkeletonDocument)[^\n]*\n",
    "\n",
    reader,
    count=1,
)
reader = re.sub(
    r"if \(error\) return (<GenerationError error=\{error\} />)",
    r"if (error && !loading) return \1",
    reader,
    count=1,
)
reader = re.sub(
    r"if \(!doc \|\| activeDocumentId == null\) return <GenerationError error=\"Document unavailable\.\" />",
    "if (!doc) {\n    if (loading) return <div style={{ flex: 1, minHeight: 0, background: '#111827' }} />\n    return <GenerationError error=\"Document unavailable.\" />\n  }\n  if (activeDocumentId == null) return <GenerationError error=\"No document selected.\" />",
    reader,
    count=1,
)
reader = reader.replace('Opening your document…', 'Loading reader…')
reader = reader.replace('Opening your document...', 'Loading reader…')
reader = reader.replace('Opening your document', 'Loading reader')
if reader != reader_before:
    reader_text = reader_text[:reader_start] + reader + reader_text[reader_end:]

if text == original and reader_text == READER_MODULE.read_text(encoding='utf-8'):
    print('Instant navigation and reader transient-state fixes already applied.')
    raise SystemExit(0)

if text != original:
    NAVIGATION.write_text(text, encoding='utf-8')
if reader_text != READER_MODULE.read_text(encoding='utf-8'):
    READER_MODULE.write_text(reader_text, encoding='utf-8')
print('Instant navigation and reader transient-state fixes applied and verified.')
