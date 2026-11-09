from pathlib import Path
import re

APP = Path('frontend/src/App.tsx')


def replace_mind_map(text: str) -> str:
    # Mind Map is owned by the clean generation build component now; leave the
    # legacy section untouched here so the build transformation can replace it.
    return text


def _transform_function(text: str, function_name: str, transform) -> str:
    """Apply a transformation only inside one named top-level screen function."""
    marker = f"function {function_name}("
    start = text.find(marker)
    if start < 0:
        return text
    end = text.find("\\nfunction ", start + len(marker))
    if end < 0:
        end = len(text)
    block = text[start:end]
    updated = transform(block)
    return text[:start] + updated + text[end:]


def remove_document_opening_interstitials(text: str) -> str:
    """Make the document-study hub and native reader cache-first.

    Keep the transform scoped to the owning screen functions. App.tsx also has
    unrelated local variables named doc and document; global first-match
    replacements can mutate the wrong screen and are not idempotent.
    """
    def update_hub(block: str) -> str:
        hub_state = "  const [document, setDocument] = useState<DocumentDetail | null>(null)"
        hub_cached_state = "  const [document, setDocument] = useState<DocumentDetail | null>(() => activeDocumentId != null ? DOC_CACHE[activeDocumentId] ?? null : null)"
        if hub_state in block and hub_cached_state not in block:
            block = block.replace(hub_state, hub_cached_state, 1)
        block = block.replace(
            "        setDocument(data)\\n        setReadingPage(Math.max(0, progress.page_num || 0))",
            "        setDocument(data)\\n        DOC_CACHE[activeDocumentId] = data\\n        setReadingPage(Math.max(0, progress.page_num || 0))",
            1,
        )
        block = block.replace(
            '  if (loading) return <GenerationLoading label="Opening your document…"/>\\n  if (error || !document) return <GenerationError error={error || \'Document unavailable.\'} />',
            '  if (loading && !document) return <GenerationLoading label="Loading study hub…"/>\\n  if (error || !document) return <GenerationError error={error || \'Document unavailable.\'} />',
            1,
        )
        return block

    def update_reader(block: str) -> str:
        reader_state = "  const [doc, setDoc] = useState<DocumentDetail | null>(null)"
        reader_cached_state = "  const [doc, setDoc] = useState<DocumentDetail | null>(() => activeDocumentId != null ? DOC_CACHE[activeDocumentId] ?? null : null)"
        if reader_state in block and reader_cached_state not in block:
            block = block.replace(reader_state, reader_cached_state, 1)
        block = block.replace(
            '  if (loading) return <GenerationLoading label="Opening your document…"/>\\n  if (error) return <GenerationError error={error} />',
            '  if (loading && !doc) return <GenerationLoading label="Loading reader…"/>\\n  if (error) return <GenerationError error={error} />',
            1,
        )
        block = block.replace('Opening your document…', 'Loading…')
        block = block.replace('Opening your document...', 'Loading…')
        block = block.replace('Opening your document', 'Loading…')
        return block

    text = _transform_function(text, "DocumentStudyScreen", update_hub)
    text = _transform_function(text, "DocumentReaderScreen", update_reader)
    return text


def harden_document_navigation(text: str) -> str:
    """Keep the native reader cache-first and avoid redundant history entries."""
    def update_reader(block: str) -> str:
        old_state = "  const [doc, setDoc] = useState<DocumentDetail | null>(null)\\n"
        new_state = "  const [doc, setDoc] = useState<DocumentDetail | null>(() => activeDocumentId != null ? DOC_CACHE[activeDocumentId] ?? null : null)\\n"
        if old_state in block and new_state not in block:
            block = block.replace(old_state, new_state, 1)
        return block

    def remove_study_hub_interstitial(block: str) -> str:
        block, _ = re.subn(
            r"\\n\\s*// Only pending while there's an active document[\\s\\S]*?\\n\\s*const docLoading = activeDocumentId != null && doc === null && !docLoadError\\n\\s*if \\(docLoading\\) return <SkeletonDocument \\/>\\n",
            "\\n",
            block,
            count=1,
        )
        block = re.sub(
            r"\\n\\s*const docLoading = activeDocumentId != null && doc === null && !docLoadError\\n\\s*if \\(docLoading\\) return <SkeletonDocument \\/>\\n",
            "\\n",
            block,
            count=1,
        )
        return block

    text = _transform_function(text, "DocumentReaderScreen", update_reader)
    text = _transform_function(text, "DocumentStudyScreen", remove_study_hub_interstitial)

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
    if old_set_screen in text and new_set_screen not in text:
        text = text.replace(old_set_screen, new_set_screen, 1)
    return text



def harden_offline_startup(text: str) -> str:
    """When the network is unavailable at cold start, resume the last known
    authenticated screen from the persisted navigation state instead of
    trapping the user behind the splash/session-check error screen.

    This is intentionally navigation-only. Screen data remains uncached until
    O2 (persistent local data), so uncached sections may still show their own
    data-unavailable states while the app shell remains usable.
    """
    marker = "  const [state, setState] = useState<'checking' | 'retry'>('checking')\n"
    injection = """  const [state, setState] = useState<'checking' | 'retry'>('checking')

  const resumeOffline = () => {
    const stored = readStoredNavigationState()
    const resumeable: Screen[] = [
      'home', 'explore', 'chats', 'profile', 'library', 'document-study',
      'document-reader', 'ai-tutor', 'study-materials', 'podcast-player',
      'podcast-library', 'flashcards', 'quiz', 'summary', 'mind-map',
      'opportunities', 'opportunity-detail', 'notifications', 'student-profile',
      'chat-detail', 'new-chat', 'chat-options', 'settings', 'edit-profile',
    ]
    const target = [...(stored?.stack || [])].reverse().find(s => resumeable.includes(s))
    if (target) {
      setScreen(target)
      return true
    }
    return false
  }
"""
    if marker in text and 'const resumeOffline = () =>' not in text:
        text = text.replace(marker, injection, 1)

    old = """  const checkSession = async (attempt = 0): Promise<void> => {
    setState('checking')
    try {
      const me = await api<{ university_id: number | null }>('/me')
      setScreen(me.university_id ? 'home' : 'complete-profile')
    } catch (e) {
"""
    new = """  const checkSession = async (attempt = 0): Promise<void> => {
    setState('checking')
    // A cold offline launch should behave like reopening a native app: the
    // cached shell is immediately usable. Do not wait through the splash's
    // network timeout before restoring the last authenticated screen.
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      if (resumeOffline()) return
    }
    try {
      const me = await api<{ university_id: number | null }>('/me')
      setScreen(me.university_id ? 'home' : 'complete-profile')
    } catch (e) {
"""
    if old in text:
        text = text.replace(old, new, 1)

    old_error = """      if (attempt === 0) {
        setTimeout(() => checkSession(1), 1200)
      } else {
        setState('retry')
      }
"""
    new_error = """      if (attempt === 0) {
        // If the browser reports offline, there is no value in waiting for a
        // second network attempt. Resume the cached shell immediately.
        if (typeof navigator !== 'undefined' && !navigator.onLine && resumeOffline()) return
        setTimeout(() => checkSession(1), 1200)
      } else {
        // A server/network failure must not erase a still-valid local
        // navigation session. Only a confirmed 401 above is allowed to force
        // the login screen.
        if (resumeOffline()) return
        setState('retry')
      }
"""
    if old_error in text:
        text = text.replace(old_error, new_error, 1)
    return text



def harden_extracted_splash_startup(app_text: str) -> str:
    """Keep offline resume when SplashScreen is owned by its feature module."""
    splash_path = Path('frontend/src/screens/onboarding/SplashScreen.tsx')
    if not splash_path.exists():
        return app_text

    app_call = "<SplashScreen setScreen={setScreen} brandline={PREPZA_BRANDLINE} />"
    app_call_with_resume = """<SplashScreen
        setScreen={setScreen}
        brandline={PREPZA_BRANDLINE}
        resumeOffline={() => {
          const stored = readStoredNavigationState()
          const resumeable: Screen[] = [
            'home', 'explore', 'chats', 'profile', 'library', 'document-study',
            'document-reader', 'ai-tutor', 'study-materials', 'podcast-player',
            'podcast-library', 'flashcards', 'quiz', 'summary', 'mind-map',
            'opportunities', 'opportunity-detail', 'notifications', 'student-profile',
            'chat-detail', 'new-chat', 'chat-options', 'settings', 'edit-profile',
          ]
          const target = [...(stored?.stack || [])].reverse().find(s => resumeable.includes(s))
          if (target) {
            setScreen(target)
            return true
          }
          return false
        }}
      />"""
    if app_call in app_text:
        app_text = app_text.replace(app_call, app_call_with_resume, 1)

    module = splash_path.read_text(encoding='utf-8')
    if "resumeOffline: () => boolean" not in module:
        module = module.replace(
            "brandline: string })",
            "brandline: string; resumeOffline: () => boolean })",
            1,
        )
    if "brandline, resumeOffline" not in module:
        module = module.replace(
            "{ setScreen, brandline }:",
            "{ setScreen, brandline, resumeOffline }:",
            1,
        )

    marker = "    setState('checking')\n"
    offline_guard = """    setState('checking')
    if (typeof navigator !== 'undefined' && !navigator.onLine && resumeOffline()) return
"""
    if offline_guard not in module and marker in module:
        module = module.replace(marker, offline_guard, 1)

    old_error = """      if (attempt === 0) {
        setTimeout(() => checkSession(1), 1200)
      } else {
        setState('retry')
      }
"""
    new_error = """      if (attempt === 0) {
        if (typeof navigator !== 'undefined' && !navigator.onLine && resumeOffline()) return
        setTimeout(() => checkSession(1), 1200)
      } else {
        if (resumeOffline()) return
        setState('retry')
      }
"""
    if old_error in module:
        module = module.replace(old_error, new_error, 1)

    splash_path.write_text(module, encoding='utf-8')
    return app_text


def persist_navigation_across_restarts(text: str) -> str:
    """Navigation state must survive a fully closed PWA process.

    sessionStorage survives normal reloads but is not a reliable persistence
    boundary for a standalone mobile app after the process is killed. The
    navigation record contains only screen names and non-sensitive numeric
    resource IDs, so localStorage is the appropriate O1 persistence layer.
    """
    text = text.replace(
        "sessionStorage.getItem('prepza-navigation-state')",
        "localStorage.getItem('prepza-navigation-state')",
    )
    text = text.replace(
        "sessionStorage.setItem('prepza-navigation-state'",
        "localStorage.setItem('prepza-navigation-state'",
    )
    return text


PATCH_MARKER = "// prepza: study-navigation-polish-v2"

def main():
    text = APP.read_text(encoding='utf-8')
    text = replace_mind_map(text)
    text = harden_document_navigation(text)
    text = remove_document_opening_interstitials(text)
    text = harden_offline_startup(text)
    text = harden_extracted_splash_startup(text)
    text = persist_navigation_across_restarts(text)
    if PATCH_MARKER not in text:
        text = text.rstrip() + "\n" + PATCH_MARKER + "\n"
    APP.write_text(text, encoding='utf-8')
    print('study navigation polish applied')

if __name__ == '__main__':
    main()
