from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'

text = APP.read_text(encoding='utf-8')
original = text

# Navigation persistence must use localStorage in the final generated source.
# This is intentionally enforced after every earlier build-time transform so a
# future patch cannot silently reintroduce session-only reload behaviour.
text = text.replace("sessionStorage.getItem('prepza-navigation-state')", "localStorage.getItem('prepza-navigation-state')")
text = text.replace("sessionStorage.setItem('prepza-navigation-state'", "localStorage.setItem('prepza-navigation-state'")

old_set_screen = """  const setScreen = (s: Screen) => {
    if (s === screen) return
    setScreenStack(stack => [...stack, s])
    window.history.pushState({ prepzaNav: true }, '')
  }
"""
new_set_screen = """  const setScreen = (s: Screen) => {
    if (s === screen) return
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
if old_set_screen in text:
    text = text.replace(old_set_screen, new_set_screen, 1)
elif new_set_screen not in text:
    raise SystemExit('Instant navigation patch: setScreen anchor not found')

# Study Hub must render its actual shell immediately. The old full-screen
# SkeletonDocument/"Loading study hub" interstitial was especially jarring in
# dark mode. DOC_CACHE still supplies stale data instantly when available, and
# the normal document fetch continues in the background.
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

# Native reader keeps the same document-shaped skeleton rather than ever
# displaying the old generic full-screen "Opening your document" page.
text = text.replace(
    '  if (loading) return <GenerationLoading label="Opening your document…" />',
    '  if (loading && !doc) return <SkeletonDocument />',
    1,
)
text = text.replace('Opening your document…', 'Loading…')
text = text.replace('Opening your document...', 'Loading…')
text = text.replace('Opening your document', 'Loading…')

if text == original:
    raise SystemExit('Instant navigation patch made no changes')

APP.write_text(text, encoding='utf-8')
print('Instant navigation and reload fixes applied and verified.')
