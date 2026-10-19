from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'
IMPORT = "import OfflineStatusBanner from './offline/OfflineStatusBanner'\n"
text = APP.read_text(encoding='utf-8')

if '<OfflineStatusBanner />' in text:
    print('Offline status UI already present; skipping root-shape transformer.')
    raise SystemExit(0)

if IMPORT not in text:
    anchor = next((line for line in text.splitlines(True) if line.startswith("import {") and "joinRealtimeChat" in line and "from './crypto/chatRealtime'" in line), "")
    if not anchor:
        raise SystemExit('Offline status UI: realtime chat import anchor missing')
    text = text.replace(anchor, anchor + IMPORT, 1)

start = text.find('export default function App')
if start < 0:
    start = text.find('function App')
if start < 0:
    raise SystemExit('Offline status UI: App function not found')

root_container_pattern = re.compile(
    r"<div style=\{\{\s*width:\s*'100%'\s*,\s*height:\s*'100dvh'",
    re.MULTILINE,
)
root_container = root_container_pattern.search(text, start)
if not root_container:
    raise SystemExit('Offline status UI: App root container anchor not found; expected a full-height app root.')
return_pos = root_container.start()


banner = '      <OfflineStatusBanner />\n'
root_child_anchor = "      {/* Content */}"
child_pos = text.find(root_child_anchor, return_pos)
if child_pos < 0:
    raise SystemExit('Offline status UI: App root content anchor not found')

if '<OfflineStatusBanner />' not in text[return_pos:]:
    text = text[:child_pos] + banner + text[child_pos:]

APP.write_text(text, encoding='utf-8')
print('Offline connection/sync status UI applied and verified.')
