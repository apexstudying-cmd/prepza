from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
HOME = (ROOT / "frontend/src/screens/home/HomeScreen.tsx").read_text(encoding="utf-8") if (ROOT / "frontend/src/screens/home/HomeScreen.tsx").exists() else ""
EXPLORE = (ROOT / "frontend/src/screens/explore/ExploreScreen.tsx").read_text(encoding="utf-8") if (ROOT / "frontend/src/screens/explore/ExploreScreen.tsx").exists() else ""


def test_home_route_and_student_workspace_are_module_owned() -> None:
    assert "import HomeScreen from './screens/home/HomeScreen'" in APP
    assert "case 'home':" in APP
    assert "return <HomeScreen" in APP
    assert "function HomeScreen(" not in APP
    assert "const HOME_CACHE" not in APP
    assert "export default function HomeScreen(" in HOME
    for route in ("setScreen('upload')", "setScreen('study-materials')", "setScreen('library')", "setScreen('ai-tutor')", "setScreen('shop')"):
        assert route in HOME


def test_home_quick_actions_keep_the_approved_five_in_order() -> None:
    start = HOME.index("AI Study Tools")
    actions_start = HOME.index("{[", start)
    actions_end = HOME.index("].map((t, i) => (", actions_start)
    actions = HOME[actions_start:actions_end]
    expected = ["label: 'Upload'", "label: 'My Study'", "label: 'Library'", "label: 'Morio'", "label: 'Shop'"]
    positions = [actions.index(label) for label in expected]
    assert positions == sorted(positions)
    assert "label: 'Podcasts'" not in actions
    assert "My Library →" not in HOME
    assert "setActiveDocumentId(featuredDoc.id); setScreen('document-study')" in HOME
    assert "readLastStudyDocumentId()" in HOME
    assert "rememberLastStudyDocument(featuredDoc.id)" in HOME


def test_explore_route_is_resolved_by_the_feature_module() -> None:
    assert "import ExploreScreen from './screens/explore/ExploreScreen'" in APP
    assert "case 'explore':" in APP
    assert "return <ExploreScreen" in APP
    assert "function ExploreSurface(" not in APP
    assert "export default function ExploreScreen(" in EXPLORE
    for contract in (
        "api<{ groups: GroupSummary[] }>('/groups')",
        "api<{ students: ExploreStudent[] }>('/students')",
        "api<{ opportunities: OpportunityPublic[] }>('/opportunities')",
        "placement=explore",
        "placement=trending",
        "'X-CSRF-Token': csrfToken",
        "setScreen('student-profile')",
        "setScreen('group-detail')",
        "setScreen('group-create')",
    ):
        assert contract in EXPLORE


def test_home_and_explore_keep_their_shell_dependencies_explicit() -> None:
    for contract in ("loadingView", "SponsoredOpportunityCard", "setActiveDocumentId", "setActiveOpportunityId"):
        assert contract in HOME
    for contract in ("loadingView", "ErrorView", "SponsoredOpportunityCard", "setActiveGroupId", "setActiveProfileUserId", "setActiveProfileName"):
        assert contract in EXPLORE


def test_home_and_explore_prebuild_steps_validate_feature_owned_sources() -> None:
    home_patch = (ROOT / "scripts/apply_home_architecture_v2.py").read_text(encoding="utf-8")
    shop_patch = (ROOT / "scripts/apply_shop_frontend.py").read_text(encoding="utf-8")
    explore_patch = (ROOT / "scripts/apply_explore_architecture.py").read_text(encoding="utf-8")
    assert "HOME = ROOT / 'frontend' / 'src' / 'screens' / 'home' / 'HomeScreen.tsx'" in home_patch
    assert 'HOME = ROOT / "frontend" / "src" / "screens" / "home" / "HomeScreen.tsx"' in shop_patch
    assert 'BOTTOM_NAV = ROOT / "frontend" / "src" / "navigation" / "BottomNav.tsx"' in shop_patch
    assert "EXPLORE = ROOT / 'frontend' / 'src' / 'screens' / 'explore' / 'ExploreScreen.tsx'" in explore_patch
    assert "function HomeScreen" not in home_patch
    assert "if 'function ExploreSurface(' in app or 'export default function ExploreScreen(' not in explore" in explore_patch


def test_morio_identity_contract_reads_the_home_feature_module() -> None:
    identity_test = (ROOT / "scripts/test_morio_identity_contract.py").read_text(encoding="utf-8")
    assert 'source("frontend/src/screens/home/HomeScreen.tsx")' in identity_test
    assert 'app.index("function HomeScreen(")' not in identity_test


def test_explore_imports_opportunity_presentation_helpers_from_shared_module() -> None:
    assert "import { fmtDeadline, oppTypeMeta } from '../../lib/opportunities'" in EXPLORE
