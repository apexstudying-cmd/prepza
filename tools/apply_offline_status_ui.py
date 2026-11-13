from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'
APP_SHELL = ROOT / 'frontend' / 'src' / 'navigation' / 'AppShell.tsx'


def transform(text: str) -> str:
    if '<OfflineStatusBanner />' in text:
        return text

    is_app_shell = 'export default function AppShell' in text
    if is_app_shell:
        import_line = "import OfflineStatusBanner from '../offline/OfflineStatusBanner'\\n"
        anchor = "import CallExperience from '../crypto/CallExperience'\\n"
        root_child_anchor = "        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>"

        banner = '        <OfflineStatusBanner />\\n'
    else:
        import_line = "import OfflineStatusBanner from './offline/OfflineStatusBanner'\\n"
        anchor = "import CallExperience from './crypto/CallExperience'\\n"
        root_child_anchor = "      {/* Content */}"
        banner = '      <OfflineStatusBanner />\\n'

    if import_line not in text:
        if anchor not in text:
            raise SystemExit('Offline status UI: app-shell call overlay import anchor missing')
        text = text.replace(anchor, anchor + import_line, 1)

    start_marker = 'export default function AppShell' if is_app_shell else 'export default function App'
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit('Offline status UI: app-shell component not found')

    root_container_anchor = "<div style={{ width: '100%', height: '100dvh'"
    root_container = text.find(root_container_anchor, start)
    if root_container < 0:
        raise SystemExit('Offline status UI: app-shell root container anchor missing')

    child_pos = text.find(root_child_anchor, root_container)
    if child_pos < 0:
        raise SystemExit('Offline status UI: app-shell root content anchor missing')

    return text[:child_pos] + banner + text[child_pos:]


def main() -> None:
    target = APP_SHELL if APP_SHELL.exists() else APP
    text = target.read_text(encoding='utf-8')
    updated = transform(text)
    if updated == text:
        print('Offline connection/sync status UI already present; no changes needed.')
        return
    target.write_text(updated, encoding='utf-8')
    print(f'Offline connection/sync status UI applied to {target.relative_to(ROOT)}.')


if __name__ == '__main__':
    main()
