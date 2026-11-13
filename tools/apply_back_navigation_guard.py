from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAVIGATION = ROOT / "frontend/src/navigation/useAppNavigation.ts"


def replace_once(old: str, new: str) -> None:
    text = NAVIGATION.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        if "onBackButtonCapture" in text and "authenticated navigation floor" in text:
            print("Back-navigation guard is already source-owned; skipping legacy transform.")
            return
        raise SystemExit("Back-navigation patch anchor missing")
    NAVIGATION.write_text(text.replace(old, new, 1), encoding="utf-8")


old_effect = '''  useEffect(() => {
    window.history.replaceState({ prepzaNav: true }, window.location.pathname)
    const onPopState = () => {
      setScreenStack(stack => (stack.length > 1 ? stack.slice(0, -1) : stack))
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])'''
new_effect = '''  useEffect(() => {
    window.history.replaceState({ prepzaNav: true }, window.location.pathname)
    const onPopState = () => {
      setScreenStack(stack => {
        if (stack.length <= 1) return stack
        const next = stack.slice(0, -1)
        // Home is the authenticated navigation floor. Never send an
        // authenticated back action through the branding Splash screen.
        return next.length === 1 && next[0] === 'splash' ? ['home'] : next
      })
    }
    const onBackButtonCapture = (event: MouseEvent) => {
      const target = event.target instanceof HTMLElement ? event.target.closest('button') : null
      if (!(target instanceof HTMLButtonElement)) return
      const label = ((target.getAttribute('aria-label') || '') + ' ' + (target.getAttribute('title') || '')).trim().toLowerCase()
      if (!/\bback\b/.test(label)) return
      event.preventDefault()
      event.stopPropagation()
      window.history.back()
    }
    window.addEventListener('popstate', onPopState)
    document.addEventListener('click', onBackButtonCapture, true)
    return () => {
      window.removeEventListener('popstate', onPopState)
      document.removeEventListener('click', onBackButtonCapture, true)
    }
  }, [])'''
replace_once(old_effect, new_effect)
