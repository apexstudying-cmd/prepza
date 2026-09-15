from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'

text = APP.read_text(encoding='utf-8')
original = text

# Navigation persistence must use localStorage in the final generated source.
text = text.replace("sessionStorage.getItem('prepza-navigation-state')", "localStorage.getItem('prepza-navigation-state')")
text = text.replace("sessionStorage.setItem('prepza-navigation-state'", "localStorage.setItem('prepza-navigation-state'")

new_set_screen = """  const setScreen = (s: Screen) => {
    if (s === screen) return
    if (screenStack.length > 1 && screenStack[screenStack.length - 2] === s) {
      window.history.back()
      return
    }
    const nextStack = [...screenStack, s]
    setScreenStack(nextStack)
    try {
      const raw = localStorage.getItem('prepza-navigation-state')
      const existing = raw ? JSON.parse(raw) : {}
      localStorage.setItem('prepza-navigation-state', JSON.stringify({
        ...existing,
        stack: nextStack,
        activeConversationId,
        activeDocumentId,
        activeGroupId,
        activeProfileUserId,
        activeOpportunityId,
      }))
    } catch { /* navigation persistence is optional */ }
    window.history.pushState({ prepzaNav: true }, '')
  }
"""

start = text.find("  const setScreen = (s: Screen) => {")
if start >= 0:
    end_marker = "\n  }\n\n  useEffect(() => {"
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit('Instant navigation patch: transformed setScreen boundary not found')
    text = text[:start] + new_set_screen.rstrip('\n') + text[end + len("\n  }"):]
elif new_set_screen.strip() not in text:
    raise SystemExit('Instant navigation patch: setScreen function not found')

# Study Hub must render its actual shell immediately. Never replace it with a
# full-screen loading interstitial while the document request is in flight.
text = text.replace(
    "  const docLoading = activeDocumentId != null && doc === null && !docLoadError\n  if (docLoading) return <SkeletonDocument />\n",
    "",
    1,
)
text = text.replace("{doc?.title || 'Loading…'}", "{doc?.title || 'Study Hub'}", 1)
text = text.replace(
    "{doc ? 'Preview not available for this file type - use the tools above to study it.' : 'Fetching your document…'}",
    "{doc ? 'Preview not available for this file type - use the tools above to study it.' : ''}",
    1,
)

# Do not show the remaining reader skeleton/interstitial when entering a
# document from Continue Studying. The reader shell should appear immediately;
# its existing document-shaped content/fallbacks handle the short fetch window.
text = text.replace(
    '  if (loading && !doc) return <SkeletonDocument />\n',
    '',
    1,
)
text = text.replace('Opening your document…', 'Loading…')
text = text.replace('Opening your document...', 'Loading…')
text = text.replace('Opening your document', 'Loading…')

if text == original:
    raise SystemExit('Instant navigation patch made no changes')

APP.write_text(text, encoding='utf-8')
print('Instant navigation and reload fixes applied and verified.')
