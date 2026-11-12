from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN_DIR = ROOT / "frontend" / "src" / "admin"
BARREL = ADMIN_DIR / "AdminPanels.tsx"
GROWTH = ADMIN_DIR / "AdminGrowthPanels.tsx"
DOMAIN = ADMIN_DIR / "AdminDomainPanels.tsx"


def test_admin_panels_are_reexported_from_bounded_domain_modules():
    barrel = BARREL.read_text(encoding="utf-8")
    growth = GROWTH.read_text(encoding="utf-8")
    domain = DOMAIN.read_text(encoding="utf-8")

    assert "from './AdminGrowthPanels'" in barrel
    assert "from './AdminDomainPanels'" in barrel
    assert len(barrel.splitlines()) <= 3

    for component in ("AdminAmbassadorsPanel", "AdminOpportunitiesPanel"):
        assert f"export function {component}" in growth

    for component in (
        "AdminPromotionsPanel",
        "AdminOrganisationsPanel",
        "AdminGroupsPanel",
        "AdminUniversitiesPanel",
        "AdminCommunityPanel",
    ):
        assert f"export function {component}" in domain

    assert len(growth.splitlines()) < 1000
    assert len(domain.splitlines()) < 1000


def test_extracted_admin_panels_keep_the_existing_api_and_csrf_ownership():
    growth = GROWTH.read_text(encoding="utf-8")
    domain = DOMAIN.read_text(encoding="utf-8")

    for source in (growth, domain):
        assert "from '../lib/appApi'" in source
        assert "X-CSRF-Token" in source
        assert "useEffect(" in source
