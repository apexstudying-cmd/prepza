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
return_pos = start + match.start()
return_text = text[return_pos:]
if '<OfflineStatusBanner />' not in return_text:
    insert_at = start + match.end()
    text = text[:insert_at] + '\n      <OfflineStatusBanner />' + text[insert_at:]
APP.write_text(text, encoding='utf-8')
print('Offline connection/sync status UI applied and verified.')
