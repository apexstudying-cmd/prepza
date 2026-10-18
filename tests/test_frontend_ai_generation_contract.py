"""Production AI-generation contract checks spanning Flask routes and the active frontend.

These tests do not contact OpenAI, Paystack, R2, or Kokoro. Existing
provider-free generation tests cover the reusable generation pipeline.
"""

from pathlib import Path
import shutil
import subprocess
import sys


def test_backend_generation_routes_and_payload_keys_match_contract():
    from app import app

    expected = {
        "/documents/<int:document_id>/summarize": "summary",
        "/documents/<int:document_id>/quiz": "quiz",
        "/documents/<int:document_id>/flashcards": "flashcards",
        "/documents/<int:document_id>/mind-map": "mind_map",
        "/documents/<int:document_id>/podcast-script": "podcast",
    }
    routes = {
        (rule.rule, method)
        for rule in app.url_map.iter_rules()
        for method in rule.methods
        if method not in {"HEAD", "OPTIONS"}
    }
    for path, feature in expected.items():
        assert (path, "POST") in routes, f"Missing backend route for {feature}: {path}"


def test_active_frontend_generation_contract_matches_backend():
    source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    expected_paths = {
        "/documents/${activeDocumentId}/summarize": "summary",
        "/documents/${activeDocumentId}/quiz": "quiz",
        "/documents/${activeDocumentId}/flashcards": "flashcards",
        "/documents/${activeDocumentId}/mind-map": "mind_map",
        "/documents/${activeDocumentId}/podcast-script": "podcast",
    }
    for path, feature in expected_paths.items():
        assert path in source, f"Active frontend no longer calls expected {feature} endpoint"

    assert "path.match" in source
    assert "mind-map" in source
    assert "mind_map" in source
    assert "setRaw(res.mind_map)" in source
    assert "res.mindmap" not in source


def test_frontend_usage_contract_uses_canonical_usage_endpoint():
    usage = Path("frontend/src/generation/usagePlan.ts").read_text(encoding="utf-8")
    assert "/api/usage/me" in usage
    assert "remaining_units" in usage
    assert "max_units_per_generation" in usage
    assert "return units <= maxPerGeneration" in usage


def test_mind_map_replay_survives_prebuild_transform(tmp_path):
    """The prebuild source transformer must not erase ready-artifact replay."""
    root = Path(__file__).resolve().parents[1]
    isolated = tmp_path / "prepza-transform-fixture"
    script_rel = Path("tools/apply_study_generation_polish.py")
    screen_rel = Path("frontend/src/generation/StudyGenerationScreensClean.tsx")

    for relative_path in (script_rel, screen_rel):
        destination = isolated / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative_path, destination)

    subprocess.run(
        [sys.executable, str(isolated / script_rel)],
        cwd=isolated,
        check=True,
        capture_output=True,
        text=True,
    )

    transformed = (isolated / screen_rel).read_text(encoding="utf-8")
    assert "loadSelectedGeneratedMaterial(activeDocumentId, 'mind_map')" in transformed
    assert "The saved mind map is empty." in transformed
    assert "setMap(root)" in transformed
    assert "setPhase('ready')" in transformed

def test_podcast_replay_uses_selected_material_and_accessible_player_controls():
    """Podcast replay must use the chosen ready artifact, not a document-wide latest audio."""
    source = Path("frontend/src/generation/GenerationScreens.tsx").read_text(encoding="utf-8")
    offline_transform = Path("tools/apply_offline_generation_persistence.py").read_text(encoding="utf-8")

    assert "loadSelectedGeneratedMaterial(activeDocumentId, 'podcast')" in source
    assert "material_id=${audioMaterialId}" in source
    assert "aria-label={playing ? 'Pause podcast' : 'Play podcast'}" in source
    assert "playing ? 'Ⅱ' : '▶'" in source
    assert "if (navigator.onLine && !csrf) return" in source
    assert "if (!navigator.onLine && selectedId == null) return" in source
    assert "void fetchPrepzaUsage()" in source
    assert "if (readSelectedPodcastMaterialId(activeDocumentId) != null) return" in source
    assert "path.split('?')[0].endsWith('/podcast-audio')" in offline_transform

def test_podcast_replay_cache_wait_uses_playwright_keyword_argument():
    """The installed Playwright API makes the evaluation payload keyword-only."""
    browser_test = Path("scripts/test_browser_study_hub_offline_content.py").read_text(encoding="utf-8")
    helper_start = browser_test.index("def wait_for_cached_podcast(")
    helper_end = browser_test.index("\n\ndef main()", helper_start)
    helper = browser_test[helper_start:helper_end]

    assert "arg={" in helper
    assert "timeout=15000" in helper

def test_primary_bottom_navigation_exposes_accessible_names_and_current_location():
    source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    start = source.index("function BottomNav(")
    end = source.index("// ─── LOADING SYSTEM", start)
    nav = source[start:end]

    assert "{ key: 'create-modal' as Screen, icon: Ic.plus, label: 'Create', hit: false }" in nav
    assert "aria-label={tab.label}" in nav
    assert "aria-current={tab.hit ? 'page' : undefined}" in nav
    assert "minWidth: 44" in nav
    assert "minHeight: 44" in nav

    styles = Path("frontend/src/index.css").read_text(encoding="utf-8")
    assert ":focus-visible" in styles
    assert "prefers-reduced-motion: reduce" in styles

def test_generation_screens_follow_manual_theme_tokens():
    generation = Path("frontend/src/generation/GenerationScreens.tsx").read_text(encoding="utf-8")
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    build_transform = Path("tools/apply_generation_ui_build.py").read_text(encoding="utf-8")

    for token in ("text", "muted", "page", "card", "border"):
        assert f"var(--prepza-generation-{token}," in generation
        assert f"'--prepza-generation-{token}'" in app
    assert "background: 'var(--prepza-generation-page, #F8F9FC)'" in build_transform

