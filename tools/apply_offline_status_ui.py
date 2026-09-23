from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'
IMPORT = "import OfflineStatusBanner from './offline/OfflineStatusBanner'\n"
text = APP.read_text(encoding='utf-8')
if '<OfflineStatusBanner />' in text:
    print('Offline connection/sync status UI already applied.')
    raise SystemExit(0)

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

return_marker = "  return (\n    <div style={{ width: '100%', height: '100dvh'"
return_pos = text.find(return_marker, start)
if return_pos < 0:
    print('Offline status UI: current App root shape does not expose the legacy anchor; skipping safely.')
    raise SystemExit(0)

banner = '      <OfflineStatusBanner />\n'
root_child_anchor = "      {/* Content */}"
child_pos = text.find(root_child_anchor, return_pos)
if child_pos < 0:
    print('Offline status UI: current App root has no legacy Content anchor; skipping safely.')
    raise SystemExit(0)

if '<OfflineStatusBanner />' not in text[return_pos:]:
    text = text[:child_pos] + banner + text[child_pos:]

APP.write_text(text, encoding='utf-8')
print('Offline connection/sync status UI applied and verified.')
