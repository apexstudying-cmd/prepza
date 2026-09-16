from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'
IMPORT = "import OfflineStatusBanner from './offline/OfflineStatusBanner'\n"
text = APP.read_text(encoding='utf-8')
if IMPORT not in text:
    anchor = "import { joinRealtimeChat, leaveRealtimeChat, sendReadRealtime, sendTypingRealtime } from './crypto/chatRealtime'\n"
    if anchor not in text:
        raise SystemExit('Offline status UI: import anchor missing')
    text = text.replace(anchor, anchor + IMPORT, 1)

start = text.find('export default function App')
if start < 0:
    start = text.find('function App')
if start < 0:
    raise SystemExit('Offline status UI: App function not found')
match = re.search(r'\n\s*return\s*\(', text[start:])
if not match:
    raise SystemExit('Offline status UI: App return anchor not found')
section = text[start:]
return_open = start + match.end()
if '<OfflineStatusBanner />' not in section:
    # Keep the existing App tree intact by wrapping it in a fragment rather than
    # introducing a second top-level JSX sibling.
    text = text[:return_open] + '\n      <>' + text[return_open:]
    section = text[start:]
    close = section.rfind('\n  )')
    if close < 0:
        raise SystemExit('Offline status UI: App return close anchor not found')
    close_abs = start + close
    text = text[:close_abs] + '\n      </>' + text[close_abs:]
    # Place the banner as the first child of the fragment.
    fragment_start = text.find('\n      <>', return_open)
    if fragment_start < 0:
        raise SystemExit('Offline status UI: fragment insertion failed')
    child_insert = fragment_start + len('\n      <>')
    text = text[:child_insert] + '\n      <OfflineStatusBanner />' + text[child_insert:]
APP.write_text(text, encoding='utf-8')
print('Offline connection/sync status UI applied and verified.')
