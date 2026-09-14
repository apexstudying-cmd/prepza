from pathlib import Path
import re

APP = Path('frontend/src/App.tsx')


def replace_mind_map(text: str) -> str:
    # Mind Map is owned by the clean generation build component now; leave the
    # legacy section untouched here so the build transformation can replace it.
    return text


def remove_document_opening_interstitials(text: str) -> str:
    """Make document study/reader navigation cache-first and never show the
    old full-screen 'Opening your document' interstitial when returning from a
    generation screen.

    The document-study hub and native reader are separate screens, so fixing
    only the legacy docLoading gate was insufficient. Both screens need to
    participate in the same DOC_CACHE.
    """
    # Document Study Hub: render cached data immediately and cache every fresh
    # response so generation -> back -> study never starts from null again.
    hub_state = "  const [document, setDocument] = useState<DocumentDetail | null>(null)"
    hub_cached_state = "  const [document, setDocument] = useState<DocumentDetail | null>(() => activeDocumentId != null ? DOC_CACHE[activeDocumentId] ?? null : null)"
    if hub_state in text and hub_cached_state not in text:
        text = text.replace(hub_state, hub_cached_state, 1)

    text = text.replace(
        "        setDocument(data)\n        setReadingPage(Math.max(0, progress.page_num || 0))",
        "        setDocument(data)\n        DOC_CACHE[activeDocumentId] = data\n        setReadingPage(Math.max(0, progress.page_num || 0))",
        1,
    )

    # If a cached document exists, never gate the hub on the refresh request.
    text = text.replace(
        '  if (loading) return <GenerationLoading label="Opening your document…" />\n  if (error || !document) return <GenerationError error={error || \'Document unavailable.\'} />',
        '  if (loading && !document) return <GenerationLoading label="Loading study hub…" />\n  if (error || !document) return <GenerationError error={error || \'Document unavailable.\'} />',
        1,
    )

    # Native reader: use the same cache and avoid the old opening interstitial
    # when coming from Document Study.
    reader_state = "  const [doc, setDoc] = useState<DocumentDetail | null>(null)"
    reader_cached_state = "  const [doc, setDoc] = useState<DocumentDetail | null>(() => activeDocumentId != null ? DOC_CACHE[activeDocumentId] ?? null : null)"
    if reader_state in text and reader_cached_state not in text:
        # The first matching state is the Document Study state in older builds,
        # so replace the remaining null state (the reader's own state).
        text = text.replace(reader_state, reader_cached_state, 1)

    text = text.replace(
        '  if (loading) return <GenerationLoading label="Opening your document…" />\n  if (error) return <GenerationError error={error} />',
        '  if (loading && !doc) return <GenerationLoading label="Loading reader…" />\n  if (error) return <GenerationError error={error} />',
        1,
    )

    # Defensive final sweep: no generated source should contain the obsolete
    # user-facing wording, even if an older surrounding implementation returns
    # a slightly different loading branch.
    text = text.replace('Opening your document…', 'Loading…')
    text = text.replace('Opening your document...', 'Loading…')
    text = text.replace('Opening your document', 'Loading…')
    return text


def harden_document_navigation(text: str) -> str:
    # Keep the main document-study screen cache-first as well.
    old_state = "  const [doc, setDoc] = useState<DocumentDetail | null>(null)\n"
    new_state = "  const [doc, setDoc] = useState<DocumentDetail | null>(() => activeDocumentId != null ? DOC_CACHE[activeDocumentId] ?? null : null)\n"
    if old_state in text:
        text = text.replace(old_state, new_state, 1)

    text, _ = re.subn(
        r"\n\s*// Only pending while there's an active document[\s\S]*?\n\s*const docLoading = activeDocumentId != null && doc === null && !docLoadError\n\s*if \(docLoading\) return <SkeletonDocument />\n",
        "\n",
        text,
        count=1,
    )
    text = re.sub(
        r"\n\s*const docLoading = activeDocumentId != null && doc === null && !docLoadError\n\s*if \(docLoading\) return <SkeletonDocument />\n",
        "\n",
        text,
        count=1,
    )

    old_set_screen = """  const setScreen = (s: Screen) => {
    if (s === screen) return
    setScreenStack(stack => [...stack, s])
    window.history.pushState({ prepzaNav: true }, '')
  }
"""
    new_set_screen = """  const setScreen = (s: Screen) => {
    if (s === screen) return
    // Back-style buttons should reuse the existing history entry rather than
    // pushing the same destination again. This prevents a visible remount of
    // Document Study when returning from generation screens.
    if (screenStack.length > 1 && screenStack[screenStack.length - 2] === s) {
      window.history.back()
      return
    }
    setScreenStack(stack => [...stack, s])
    window.history.pushState({ prepzaNav: true }, '')
  }
"""
    if old_set_screen in text:
        text = text.replace(old_set_screen, new_set_screen, 1)
    return text


def main():
    text = APP.read_text(encoding='utf-8')
    text = replace_mind_map(text)
    text = harden_document_navigation(text)
    text = remove_document_opening_interstitials(text)
    APP.write_text(text, encoding='utf-8')
    print('study navigation polish applied')


if __name__ == '__main__':
    main()
