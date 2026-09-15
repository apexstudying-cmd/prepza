from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAV = ROOT / 'frontend' / 'src' / 'crypto' / 'navigationTransitions.ts'
text = NAV.read_text(encoding='utf-8')

old = """  // Keep the real app surface visible throughout the React state change.\n  // The previous implementation hid it before React committed the next screen,\n  // which could expose the page/root background for a frame on dark-mode swipes.\n  // The outgoing clone remains visible above it while the real surface moves to\n  // the incoming side, so there is never an empty transition gap.\n  const outgoingLayer = createOutgoingLayer(content)\n  const sign = direction === 'left' ? -1 : 1\n  const width = Math.max(window.innerWidth, content.clientWidth || 0)\n  content.style.visibility = 'visible'\n  content.style.transform = `translate3d(${-sign * width}px,0,0)`\n  content.style.willChange = 'transform'\n\n  navigate()\n\n  requestAnimationFrame(() => {\n    const nextContent = contentElement()\n    if (!nextContent) {\n      outgoingLayer?.remove()\n      resetContentTransform()\n      navigationInProgress = false\n      return\n    }\n\n    nextContent.style.visibility = 'visible'\n    nextContent.style.willChange = 'transform'\n    nextContent.style.transform = `translate3d(${-sign * width}px,0,0)`\n"""

new = """  // Never hide the live React surface before the next render exists. The app\n  // shell reuses this DOM node across screens, so hiding it creates a blank\n  // frame (and can expose a light child background in dark mode) during reload\n  // or slower React commits. Keep the current surface visible until the new\n  // screen has actually rendered, then animate that same surface in.\n  const outgoingLayer = createOutgoingLayer(content)\n  const sign = direction === 'left' ? -1 : 1\n  const width = Math.max(window.innerWidth, content.clientWidth || 0)\n  content.style.willChange = 'transform'\n\n  navigate()\n\n  requestAnimationFrame(() => {\n    const nextContent = contentElement()\n    if (!nextContent) {\n      outgoingLayer?.remove()\n      resetContentTransform()\n      navigationInProgress = false\n      return\n    }\n\n    nextContent.style.willChange = 'transform'\n    nextContent.style.transform = `translate3d(${-sign * width}px,0,0)`\n"""

if old not in text:
    raise SystemExit('Navigation flicker fix: expected finishNavigation block not found')

text = text.replace(old, new, 1)
text = text.replace("      nextContent.style.visibility = ''\n", "", 1)
NAV.write_text(text, encoding='utf-8')
print('Navigation blank-frame guard applied.')
