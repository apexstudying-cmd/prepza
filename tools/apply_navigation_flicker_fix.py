from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAV = ROOT / 'frontend' / 'src' / 'crypto' / 'navigationTransitions.ts'
text = NAV.read_text(encoding='utf-8')

old = """  content.style.visibility = 'hidden'\n  content.style.transform = `translate3d(${-sign * width}px,0,0)`\n  content.style.willChange = 'transform'\n  navigate()\n  requestAnimationFrame(() => {\n    const nextContent = contentElement()\n    if (!nextContent) { outgoingLayer?.remove(); navigationInProgress = false; return }\n    nextContent.style.visibility = 'visible'\n    nextContent.style.willChange = 'transform'\n    nextContent.style.transform = `translate3d(${-sign * width}px,0,0)`\n"""

new = """  // Never hide the live React surface before the next render exists. The app\n  // shell reuses this DOM node across screens, so hiding it creates a blank\n  // frame (and can expose a light child background in dark mode) during reload\n  // or slower React commits. Keep the current surface visible until the new\n  // screen has actually rendered, then animate that same surface in.\n  content.style.willChange = 'transform'\n  navigate()\n  requestAnimationFrame(() => {\n    const nextContent = contentElement()\n    if (!nextContent) {\n      outgoingLayer?.remove()\n      content.style.willChange = ''\n      content.style.transform = ''\n      navigationInProgress = false\n      return\n    }\n    nextContent.style.willChange = 'transform'\n    nextContent.style.transform = `translate3d(${-sign * width}px,0,0)`\n"""

if old not in text:
    raise SystemExit('Navigation flicker fix: expected finishNavigation block not found')

text = text.replace(old, new, 1)
text = text.replace("      nextContent.style.visibility = ''\n", "", 1)
NAV.write_text(text, encoding='utf-8')
print('Navigation blank-frame guard applied.')
