from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'
IMPORT = "import OfflineStatusBanner from './offline/OfflineStatusBanner'\\n"


def transform(text: str) -> str:
    if '<OfflineStatusBanner />' in text:
        return text

    if IMPORT not in text:
        # Offline status is app-shell UI, not chat behavior. Anchor it to the
        # persistent call overlay import so extracting ChatDetail cannot break
        # this unrelated prebuild transformation.
        anchor = "import CallExperience from './crypto/CallExperience'\\n"
        if anchor not in text:
            raise SystemExit('Offline status UI: app-shell call overlay import anchor missing')
        text = text.replace(anchor, anchor + IMPORT, 1)

    start = text.find('export default function App')
    if start < 0:
        start = text.find('function App')
    if start < 0:
        raise SystemExit('Offline status UI: App function not found')

    root_container_pattern = re.compile(
        r"<div style=\\{\\{\\s*width:\\s*'100%'\\s*,\\s*height:\\s*'100dvh'",
        re.MULTILINE,
    )
    root_container = root_container_pattern.search(text, start)
    if not root_container:
        raise SystemExit('Offline status UI: App root container anchor not found; expected a full-height app root.')

    root_child_anchor = "      {/* Content */}"
    child_pos = text.find(root_child_anchor, root_container.start())
    if child_pos < 0:
        raise SystemExit('Offline status UI: App root content anchor not found')

    banner = '      <OfflineStatusBanner />\\n'
    return text[:child_pos] + banner + text[child_pos:]


def main() -> None:
    text = APP.read_text(encoding='utf-8')
    updated = transform(text)
    if updated == text:
        print('Offline connection/sync status UI already present; no changes needed.')
        return
    APP.write_text(updated, encoding='utf-8')
    print('Offline connection/sync status UI applied and verified.')


if __name__ == '__main__':
    main()
