from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / 'frontend' / 'src' / 'screens' / 'home' / 'HomeScreen.tsx'


def main() -> None:
    source = HOME.read_text(encoding='utf-8')
    start = source.index('AI Study Tools')
    actions_start = source.index('{[', start)
    actions_end = source.index('].map((t, i) => (', actions_start)
    actions = source[actions_start:actions_end]
    expected = (
        "label: 'Upload'",
        "label: 'My Study'",
        "label: 'Library'",
        "label: 'Morio'",
        "label: 'Shop'",
    )
    positions = [actions.index(label) if label in actions else -1 for label in expected]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise SystemExit('Home architecture: expected five ordered Quick Actions are missing')
    if 'My Library →' in source:
        raise SystemExit('Home architecture: duplicate My Library shortcut remains')
    if "setActiveDocumentId(featuredDoc.id); setScreen('document-study')" not in source:
        raise SystemExit('Home architecture: Continue Study navigation contract missing')
    print('Home architecture module verified; no source mutation required.')


if __name__ == '__main__':
    main()
