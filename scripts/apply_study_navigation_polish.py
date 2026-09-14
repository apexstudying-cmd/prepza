from pathlib import Path
import re

APP = Path('frontend/src/App.tsx')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'Expected {label} anchor not found')
    return text.replace(old, new, 1)


def replace_mind_map(text: str) -> str:
    marker = r"// ─── MIND MAP ─────────────────────────────────────────────────────────────────\n"
    next_marker = r"// ─── PODCAST PLAYER ───────────────────────────────────────────────────────────\n"
    start = text.find(marker)
    end = text.find(next_marker, start + len(marker)) if start >= 0 else -1
    if start < 0 or end < 0:
        raise SystemExit('Mind Map section boundaries not found')
    return text[:start] + text[start:end] + text[end:]


def harden_document_navigation(text: str) -> str:
    # Keep the document cache as the immediate render source when available.
    old_state = "  const [doc, setDoc] = useState<DocumentDetail | null>(null)\n"
    new_state = "  const [doc, setDoc] = useState<DocumentDetail | null>(() => activeDocumentId != null ? DOC_CACHE[activeDocumentId] ?? null : null)\n"
    if old_state in text:
        text = text.replace(old_state, new_state, 1)

    # This is deliberately regex-based: comments around the old interstitial
    # have changed over time, so an exact multi-line string is too fragile.
    text, removed = re.subn(
        r"\n\s*// Only pending while there's an active document[\s\S]*?\n\s*const docLoading = activeDocumentId != null && doc === null && !docLoadError\n\s*if \(docLoading\) return <SkeletonDocument />\n",
        "\n",
        text,
        count=1,
    )
    if not removed:
        text = re.sub(
            r"\n\s*const docLoading = activeDocumentId != null && doc === null && !docLoadError\n\s*if \(docLoading\) return <SkeletonDocument />\n",
            "\n",
            text,
            count=1,
        )[0] if isinstance(text, tuple) else text

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
    APP.write_text(text, encoding='utf-8')
    print('study navigation polish applied')


if __name__ == '__main__':
    main()
