from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
SCREEN = (
    ROOT / "frontend" / "src" / "screens" / "ambassador" / "AmbassadorScreen.tsx"
)


def test_ambassador_screen_is_owned_by_its_feature_module():
    assert "import AmbassadorScreen from './screens/ambassador/AmbassadorScreen'" in APP
    assert "case 'ambassador':" in APP
    assert "function AmbassadorScreen(" not in APP
    assert "interface AmbassadorStatusResp" not in APP
    assert "const AMB_COLORS =" not in APP


def test_ambassador_screen_preserves_existing_api_and_navigation_contract():
    source = SCREEN.read_text(encoding="utf-8")
    for path in (
        "/ambassador/status",
        "/ambassador/dashboard",
        "/ambassador/referrals?page=1",
        "/ambassador/payouts",
        "/ambassador/apply",
        "/ambassador/payouts/request",
        "/ambassador/referral-qr",
    ):
        assert path in source
    assert "setScreen('profile')" in source
    assert "export default function AmbassadorScreen(" in source
    assert "import { api } from '../../lib/appApi'" in source
    assert "import { useTheme } from '../../theme/theme'" in source
