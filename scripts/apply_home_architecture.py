from pathlib import Path
import re

APP = Path('frontend/src/App.tsx')


def home_section(text: str) -> tuple[str, str, str]:
    match = re.search(r"(?ms)^function HomeScreen\b.*?(?=^function |^const |^export default |\Z)", text)
    if not match:
        raise SystemExit('Home architecture patch: HomeScreen section not found')
    return text[:match.start()], match.group(0), text[match.end():]


def main() -> None:
    text = APP.read_text(encoding='utf-8')
    before, home, after = home_section(text)

    # The previous navigation work already established My Study as the saved
    # student workspace. Home should therefore expose Library as discovery,
    # not expose a second entry point to the same Study Hub.
    home = home.replace("{ icon: '▣', label: 'My Study', action: () => setScreen('study-materials') },\n              { icon: '✦', label: 'Ada'", "{ icon: '▣', label: 'My Study', action: () => setScreen('study-materials') },\n              { icon: 'Library', label: 'Library', action: () => setScreen('library') },\n              { icon: '✦', label: 'Ada'", 1)

    # Replace the icon with a neutral text glyph if the source expects an icon
    # string; this keeps the existing quick-action renderer intact.
    home = home.replace("{ icon: 'Library', label: 'Library'", "{ icon: '▤', label: 'Library'", 1)

    # Remove the duplicate My Library shortcut from Home. This is intentionally
    # scoped to HomeScreen so Library navigation elsewhere is untouched.
    patterns = [
        r"\n\s*<button[^>]*>[^<]*.*?My Library.*?</button>",
        r"\n\s*<button[^>]*>[\s\S]*?My Library[\s\S]*?</button>",
    ]
    original_home = home
    for pattern in patterns:
        home = re.sub(pattern, '', home, count=1)
        if home != original_home:
            break

    if 'My Library' in home:
        raise SystemExit('Home architecture patch: duplicate My Library entry remains')
    if "label: 'Library'" not in home or "setScreen('library')" not in home:
        raise SystemExit('Home architecture patch: Library quick action was not installed')
    if "label: 'My Study'" not in home or "setScreen('study-materials')" not in home:
        raise SystemExit('Home architecture patch: My Study quick action missing')
    if 'Continue Studying' not in home:
        raise SystemExit('Home architecture patch: Continue Studying section missing')

    APP.write_text(before + home + after, encoding='utf-8')
    print('Home architecture applied and verified.')


if __name__ == '__main__':
    main()
