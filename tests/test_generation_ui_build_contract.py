"""Regression test for source-section boundaries in the frontend build transform."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _summary_replacement():
    source = (ROOT / "tools" / "apply_generation_ui_build.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in ast.walk(module):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "replacements" for target in node.targets):
            continue
        replacements = ast.literal_eval(node.value)
        return next(item for item in replacements if item[0] == "// ─── SUMMARY")
    raise AssertionError("Summary replacement not found in build transform")


def test_summary_build_transform_preserves_explore_screen_definition():
    start_marker, end_marker, replacement = _summary_replacement()
    app_source = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

    start = app_source.find(start_marker)
    end = app_source.find(end_marker, start + len(start_marker))
    assert start >= 0, "Summary section marker must exist"
    assert end >= 0, "Summary replacement boundary must exist"

    transformed = app_source[:start] + replacement + app_source[end:]

    assert "function ExploreScreen(" in transformed, (
        "The Summary build transform must not delete the ExploreScreen wrapper"
    )
    assert "case 'explore':" in transformed, (
        "The Explore navigation route must remain registered"
    )


def test_podcast_generation_build_transform_uses_the_existing_app_section_boundary():
    source = (ROOT / "tools" / "apply_generation_ui_build.py").read_text(encoding="utf-8")
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    study = (ROOT / "frontend" / "src" / "screens" / "study" / "GeneratedStudyScreens.tsx").read_text(encoding="utf-8")

    player = (ROOT / "frontend" / "src" / "screens" / "podcast" / "PodcastPlayerScreen.tsx").read_text(encoding="utf-8")

    assert "PLAYER.write_text" not in source
    assert "PodcastPlayerScreen is an extracted feature module" in source
    assert "setActiveOpportunityId: (id: number | null) => void" in player
    assert "getCachedPodcastAudio(podcastAudioPath)" in player
    assert "('// ─── PODCAST PLAYER', '// ─── SUMMARY'" not in source
    assert "is_study_flashcards = end_marker == '// ─── QUIZ'" in source
    assert "// ─── FLASHCARDS" in study
    assert "function FlashcardsScreen(" in study
    assert "function PodcastPlayerScreen(" not in app
    assert "export default function PodcastPlayerScreen(" in player


def test_library_academic_context_transform_accepts_extracted_canonical_state_and_is_idempotent(tmp_path):
    import shutil
    import subprocess
    import sys

    (tmp_path / "tools").mkdir()
    for relative in ("app.py", "library_models.py", "tools/apply_library_academic_context.py"):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    script = tmp_path / "tools" / "apply_library_academic_context.py"
    app = tmp_path / "app.py"

    first = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert first.returncode == 0, first.stdout + first.stderr

    transformed = app.read_text(encoding="utf-8")
    browse = transformed.split("def browse_library():", 1)[1].split("\n@app.route", 1)[0]
    assert "viewer = db.session.get(User, user_id)" in browse
    assert "relevance_order = []" in browse
    assert "query.order_by(*relevance_order, order_col)" in browse

    second = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert second.returncode == 0, second.stdout + second.stderr
    assert app.read_text(encoding="utf-8") == transformed


def test_admin_platform_is_owned_by_a_dedicated_admin_module_without_changing_route_keys():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    admin_dir = ROOT / "frontend" / "src" / "admin"
    platform_path = admin_dir / "AdminPlatform.tsx"
    section_path = admin_dir / "AdminSection.tsx"
    panels_path = admin_dir / "AdminPanels.tsx"
    shared_path = admin_dir / "AdminShared.tsx"
    assert all(path.exists() for path in (platform_path, section_path, panels_path, shared_path)), (
        "Admin UI should be split into platform, section, domain-panel, and shared modules"
    )
    platform = platform_path.read_text(encoding="utf-8")
    section_module = section_path.read_text(encoding="utf-8")
    panels = panels_path.read_text(encoding="utf-8")
    growth_panels = (admin_dir / "AdminGrowthPanels.tsx").read_text(encoding="utf-8")
    domain_panels = (admin_dir / "AdminDomainPanels.tsx").read_text(encoding="utf-8")
    shared = shared_path.read_text(encoding="utf-8")

    assert "import AdminPlatform from './admin/AdminPlatform'" in app
    assert "function AdminSection(" not in app
    assert "function AdminPlatform(" not in app
    assert "import AdminSection from './AdminSection'" in platform
    assert "export default function AdminPlatform(" in platform
    assert "export default function AdminSection(" in section_module
    assert "AdminAmbassadorsPanel" in panels and "AdminGrowthPanels" in panels
    assert "AdminCommunityPanel" in panels and "AdminDomainPanels" in panels
    assert "export function AdminAmbassadorsPanel(" in growth_panels
    assert "export function AdminOpportunitiesPanel(" in growth_panels
    assert "export function AdminCommunityPanel(" in domain_panels
    assert "export function AdminCard(" in shared
    assert "export type AdminUserRow" in shared

    combined = platform + section_module + panels + growth_panels + domain_panels + shared
    for section in (
        "dashboard", "users", "content", "ai-usage", "b2b-finance",
        "payments", "moderation", "analytics", "operations", "system",
        "settings", "groups", "ambassadors", "communications",
        "opportunities", "promotions", "organisations", "universities",
        "community",
    ):
        assert f"'{section}'" in combined, f"Existing admin section key {section!r} must remain"
