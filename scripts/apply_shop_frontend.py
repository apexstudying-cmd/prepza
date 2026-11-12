"""Idempotently wire Shop into the app shell and preserve Home's five Quick Actions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "App.tsx"
HOME = ROOT / "frontend" / "src" / "screens" / "home" / "HomeScreen.tsx"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise SystemExit(f"Shop frontend patch anchor missing: {label}")


def main() -> None:
    text = APP.read_text(encoding="utf-8")
    home = HOME.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "import CompleteProfileScreen from './screens/onboarding/CompleteProfileScreen'\\n",
        "import CompleteProfileScreen from './screens/onboarding/CompleteProfileScreen'\\nimport ShopScreen from './shop/ShopScreen'\\n",
        "ShopScreen import",
    )
    text = replace_once(
        text,
        "  | 'home' | 'explore' | 'create-modal' | 'chats' | 'profile'\\n",
        "  | 'home' | 'explore' | 'create-modal' | 'chats' | 'profile'\\n  | 'shop'\\n",
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
              { icon: Ic.flash('w-6 h-6'), label: 'Morio', action: () => setScreen('ai-tutor') },
              { icon: Ic.image('w-6 h-6'), label: 'Shop', action: () => setScreen('shop') },
            ].map((t, i) => ("""
    home = replace_once(home, old_actions, new_actions, "five Home quick actions")

    text = replace_once(
        text,
        "'mind-map','document-reader'].includes(active)",
        "'mind-map','document-reader','shop'].includes(active)",
        "Shop Home-tab selection",
    )
    old_case = """      case 'home':              return <HomeScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} setActiveOpportunityId={setActiveOpportunityId} SponsoredOpportunityCard={SponsoredOpportunityCard} loadingView={<SkeletonHome />} />
      case 'explore':"""
    new_case = """      case 'home':              return <HomeScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} setActiveOpportunityId={setActiveOpportunityId} SponsoredOpportunityCard={SponsoredOpportunityCard} loadingView={<SkeletonHome />} />
      case 'shop':              return <ShopScreen setScreen={setScreen} setActiveConversationId={setActiveConversationId} />
      case 'explore':"""
    text = replace_once(text, old_case, new_case, "Shop screen renderer")
    APP.write_text(text, encoding="utf-8")
    HOME.write_text(home, encoding="utf-8")


if __name__ == "__main__":
    main()
