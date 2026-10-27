"""Idempotently wire the Shop screen and five Home quick actions into the SPA."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "App.tsx"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise SystemExit(f"Shop frontend patch anchor missing: {label}")


def main() -> None:
    text = APP.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "import logoImg from './imports/logo.svg'\n",
        "import logoImg from './imports/logo.svg'\nimport ShopScreen from './shop/ShopScreen'\n",
        "ShopScreen import",
    )
    text = replace_once(
        text,
        "  | 'home' | 'explore' | 'create-modal' | 'chats' | 'profile'\n",
        "  | 'home' | 'explore' | 'create-modal' | 'chats' | 'profile'\n  | 'shop'\n",
        "Shop screen union",
    )
    old_actions = """            {[
              { icon: Ic.upload('w-6 h-6'), label: 'Upload', action: () => setScreen('upload') },
              { icon: Ic.book('w-6 h-6'), label: 'My Study', action: () => setScreen('study-materials') },
              { icon: Ic.explore('w-6 h-6'), label: 'Library', action: () => setScreen('library') },
              { icon: Ic.flash('w-6 h-6'), label: 'Ada', action: () => setScreen('ai-tutor') },
              { icon: Ic.podcast('w-6 h-6'), label: 'Podcasts', action: () => setScreen('podcast-library') },
            ].map((t, i) => ("""
    new_actions = """            {[
              { icon: Ic.upload('w-6 h-6'), label: 'Upload', action: () => setScreen('upload') },
              { icon: Ic.book('w-6 h-6'), label: 'My Study', action: () => setScreen('study-materials') },
              { icon: Ic.explore('w-6 h-6'), label: 'Library', action: () => setScreen('library') },
              { icon: Ic.flash('w-6 h-6'), label: 'Ada', action: () => setScreen('ai-tutor') },
              { icon: Ic.image('w-6 h-6'), label: 'Shop', action: () => setScreen('shop') },
            ].map((t, i) => ("""
    text = replace_once(text, old_actions, new_actions, "five Home quick actions")

    text = replace_once(
        text,
        "'mind-map','document-reader'].includes(active)",
        "'mind-map','document-reader','shop'].includes(active)",
        "Shop Home-tab selection",
    )
    old_case = """      case 'home':              return <HomeScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} setActiveOpportunityId={setActiveOpportunityId} />
      case 'explore':"""
    new_case = """      case 'home':              return <HomeScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} setActiveOpportunityId={setActiveOpportunityId} />
      case 'shop':              return <ShopScreen setScreen={setScreen} setActiveConversationId={setActiveConversationId} />
      case 'explore':"""
    text = replace_once(text, old_case, new_case, "Shop screen renderer")
    APP.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
