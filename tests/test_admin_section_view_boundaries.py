from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN_DIR = ROOT / "frontend" / "src" / "admin"
ADMIN_SECTION = ADMIN_DIR / "AdminSection.tsx"
VIEW_TYPES = ADMIN_DIR / "AdminSectionViewProps.ts"
CORE_VIEWS = ADMIN_DIR / "AdminSectionCoreViews.tsx"
PLATFORM_VIEWS = ADMIN_DIR / "AdminSectionPlatformViews.tsx"


def test_admin_state_and_api_ownership_stays_in_the_section_controller():
    source = ADMIN_SECTION.read_text(encoding="utf-8")

    assert "useEffect(" in source
    assert "api<" in source
    assert "X-CSRF-Token" in source
    assert "setPrepzaControlEnabled" in source
    assert "Disable Control Access" in source


def test_admin_view_modules_own_the_existing_section_renderers():
    section = ADMIN_SECTION.read_text(encoding="utf-8")
    core = CORE_VIEWS.read_text(encoding="utf-8")
    platform = PLATFORM_VIEWS.read_text(encoding="utf-8")

    for key in ("dashboard", "users", "content", "ai-usage", "payments", "moderation", "analytics"):
        assert f"Admin{key.title().replace('-', '')}Section" in core or key in core
        assert f"if (section === '{key}')" not in section

    for key in ("system", "communications"):
        assert key in platform
        assert f"if (section === '{key}')" not in section

    assert "AdminDashboardSection" in section
    assert "AdminSystemSection" in section
    assert "AdminCommunicationsSection" in section


def test_admin_views_receive_typed_props_and_do_not_own_api_calls():
    types = VIEW_TYPES.read_text(encoding="utf-8")
    core = CORE_VIEWS.read_text(encoding="utf-8")
    platform = PLATFORM_VIEWS.read_text(encoding="utf-8")

    assert "export type AdminSectionViewProps" in types
    assert "Pick<AdminSectionViewProps" in core
    assert "Pick<AdminSectionViewProps" in platform
    assert "from '../lib/appApi'" not in core
    assert "from '../lib/appApi'" not in platform


def test_admin_refactor_files_are_bounded_and_settings_remain_in_the_state_owner():
    section_lines = len(ADMIN_SECTION.read_text(encoding="utf-8").splitlines())
    core_lines = len(CORE_VIEWS.read_text(encoding="utf-8").splitlines())
    platform_lines = len(PLATFORM_VIEWS.read_text(encoding="utf-8").splitlines())

    assert section_lines < 1000
    assert core_lines < 1000
    assert platform_lines < 1000
    assert "if (section === 'settings')" in ADMIN_SECTION.read_text(encoding="utf-8")
