from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend/src/App.tsx'


def home_section(text: str) -> tuple[str, str, str]:
    match = re.search(r"(?ms)^function HomeScreen\b.*?(?=^function |^const |^export default |\Z)", text)
    if not match:
        raise SystemExit('Home architecture patch: HomeScreen section not found')
    return text[:match.start()], match.group(0), text[match.end():]


def main() -> None:
    text = APP.read_text(encoding='utf-8')
    before, home, after = home_section(text)

    home = home.replace(
        "{ icon: '▣', label: 'My Study', action: () => setScreen('study-materials') },\n              { icon: '✦', label: 'Ada'",
        "{ icon: '▣', label: 'My Study', action: () => setScreen('study-materials') },\n              { icon: '▤', label: 'Library', action: () => setScreen('library') },\n              { icon: '✦', label: 'Ada'",
        1,
    )

    # The old Home shortcut is a span, not a button. Target it exactly so the
    # transformation cannot consume the Continue Study card/button.
    home = re.sub(
        r"\n\s*<span[^>]*onClick=\{\(\) => setScreen\('library'\)\}[^>]*>My Library →</span>",
        '',
        home,
        count=1,
    )

    if 'My Library' in home:
        raise SystemExit('Home architecture patch: duplicate My Library entry remains')
    if "label: 'Library'" not in home or "setScreen('library')" not in home:
        raise SystemExit('Home architecture patch: Library quick action was not installed')
    if "label: 'My Study'" not in home or "setScreen('study-materials')" not in home:
        raise SystemExit('Home architecture patch: My Study quick action missing')
    if "setActiveDocumentId(featuredDoc.id); setScreen('document-study')" not in home:
        raise SystemExit('Home architecture patch: Continue Study navigation contract missing')

    APP.write_text(before + home + after, encoding='utf-8')
    print('Home architecture applied and verified.')


if __name__ == '__main__':
    main()
