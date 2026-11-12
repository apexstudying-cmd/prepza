from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'
EXPLORE = ROOT / 'frontend' / 'src' / 'screens' / 'explore' / 'ExploreScreen.tsx'


def main() -> None:
    app = APP.read_text(encoding='utf-8')
    explore = EXPLORE.read_text(encoding='utf-8')
    required_app = (
        "import ExploreScreen from './screens/explore/ExploreScreen'",
        "case 'explore':",
        "return <ExploreScreen",
    )
    missing = [item for item in required_app if item not in app]
    if missing:
        raise SystemExit(f'Explore architecture: app-shell route contract missing: {missing}')
    if 'function ExploreSurface(' in app or 'export default function ExploreScreen(' not in explore:
        raise SystemExit('Explore architecture: Explore feature module ownership is incomplete')
    print('Explore architecture module verified; no source mutation required.')


if __name__ == '__main__':
    main()
