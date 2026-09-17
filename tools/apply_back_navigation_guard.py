from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend/src/App.tsx"


def replace_once(old: str, new: str) -> None:
    text = APP.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit("Back-navigation patch anchor missing")
    APP.write_text(text.replace(old, new, 1), encoding="utf-8")


old_effect = '''  useEffect(() => {\n    window.history.replaceState({ prepzaNav: true }, '')\n    const onPopState = () => {\n      setScreenStack(stack => (stack.length > 1 ? stack.slice(0, -1) : stack))\n    }\n    window.addEventListener('popstate', onPopState)\n    return () => window.removeEventListener('popstate', onPopState)\n  }, [])'''
new_effect = '''  useEffect(() => {\n    window.history.replaceState({ prepzaNav: true }, '')\n    const onPopState = () => {\n      setScreenStack(stack => {\n        if (stack.length <= 1) return stack\n        const next = stack.slice(0, -1)\n        // Home is the authenticated navigation floor. Never send an\n        // authenticated back action through the branding Splash screen.\n        return next.length === 1 && next[0] === 'splash' ? ['home'] : next\n      })\n    }\n    const onBackButtonCapture = (event: MouseEvent) => {\n      const target = event.target instanceof HTMLElement ? event.target.closest('button') : null\n      if (!(target instanceof HTMLButtonElement)) return\n      const label = `${target.getAttribute('aria-label') || ''} ${target.getAttribute('title') || ''}`.trim().toLowerCase()\n      if (!/\\bback\\b/.test(label)) return\n      event.preventDefault()\n      event.stopPropagation()\n      window.history.back()\n    }\n    window.addEventListener('popstate', onPopState)\n    document.addEventListener('click', onBackButtonCapture, true)\n    return () => {\n      window.removeEventListener('popstate', onPopState)\n      document.removeEventListener('click', onBackButtonCapture, true)\n    }\n  }, [])'''
replace_once(old_effect, new_effect)
