from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN_DIR = ROOT / "frontend" / "src" / "admin"
ADMIN_SECTION = ADMIN_DIR / "AdminSection.tsx"
CONTROLLER = ADMIN_DIR / "useAdminSectionController.ts"
VIEW_TYPES = CONTROLLER
CORE_VIEWS = ADMIN_DIR / "AdminSectionCoreViews.tsx"
PLATFORM_VIEWS = ADMIN_DIR / "AdminSectionPlatformViews.tsx"


def test_admin_state_and_api_ownership_stays_in_the_section_controller():
    section = ADMIN_SECTION.read_text(encoding="utf-8")
    controller = CONTROLLER.read_text(encoding="utf-8")

    assert "useAdminSectionController(section, setSection)" in section
    assert "useEffect(" in controller
    assert "api<" in controller
    assert "X-CSRF-Token" in controller
    assert "setPrepzaControlEnabled" in controller
    assert "Disable Control Access" in section
    assert "from '../lib/appApi'" not in section


def test_admin_view_modules_own_the_existing_section_renderers():
    section = ADMIN_SECTION.read_text(encoding="utf-8")
    core = CORE_VIEWS.read_text(encoding="utf-8")
    platform = PLATFORM_VIEWS.read_text(encoding="utf-8")

    core_components = {
        "dashboard": "AdminDashboardSection",
        "users": "AdminUsersSection",
        "content": "AdminContentSection",
        "ai-usage": "AdminAiUsageSection",
        "payments": "AdminPaymentsSection",
        "moderation": "AdminModerationSection",
        "analytics": "AdminAnalyticsSection",
    }
    for key, component in core_components.items():
        assert component in core
        assert f"if (section === '{key}') return <{component} controller={controller} />" in section

    for key, component in (("system", "AdminSystemSection"), ("communications", "AdminCommunicationsSection")):
        assert component in platform
        assert f"if (section === '{key}') return <{component} controller={controller} />" in section

    assert "AdminDashboardSection" in section
    assert "AdminSystemSection" in section
    assert "AdminCommunicationsSection" in section


def test_admin_views_receive_typed_props_and_do_not_own_api_calls():
    types = VIEW_TYPES.read_text(encoding="utf-8")
    core = CORE_VIEWS.read_text(encoding="utf-8")
    platform = PLATFORM_VIEWS.read_text(encoding="utf-8")

    assert "export type AdminSectionController" in types
    assert "Pick<AdminSectionController" in core
    assert "Pick<AdminSectionController" in platform
    assert "from '../lib/appApi'" not in core
    assert "from '../lib/appApi'" not in platform


def test_admin_refactor_files_are_bounded_and_settings_remain_in_the_state_owner():
    section_lines = len(ADMIN_SECTION.read_text(encoding="utf-8").splitlines())
    controller_lines = len(CONTROLLER.read_text(encoding="utf-8").splitlines())
    core_lines = len(CORE_VIEWS.read_text(encoding="utf-8").splitlines())
    platform_lines = len(PLATFORM_VIEWS.read_text(encoding="utf-8").splitlines())

    assert section_lines < 500
    assert controller_lines < 1000
    assert core_lines < 1000
    assert platform_lines < 1000
    assert "if (section === 'settings')" in ADMIN_SECTION.read_text(encoding="utf-8")
