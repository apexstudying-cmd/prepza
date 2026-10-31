"""Production AI-generation contract checks spanning Flask routes and the active frontend.

These tests do not contact OpenAI, Paystack, R2, or Kokoro. Existing
provider-free generation tests cover the reusable generation pipeline.
"""

from pathlib import Path
import re
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
    assert "<span style={{ fontSize: 11, fontWeight: 700, color: N.gold, fontFamily: 'Plus Jakarta Sans' }}>Create</span>" in nav

    study_start = source.index("function StudyMaterialsScreen")
    study_end = source.index("// ─── DOCUMENT STUDY HUB", study_start)
    study = source[study_start:study_end]
    assert "if (key === 'quiz' || key === 'practice_questions') return Ic.check('w-5 h-5')" in study
    assert "aria-hidden=\"true\"" in study

    styles = Path("frontend/src/index.css").read_text(encoding="utf-8")
    assert ":focus-visible" in styles
    assert "prefers-reduced-motion: reduce" in styles

def test_generation_screens_follow_manual_theme_tokens():
    generation = Path("frontend/src/generation/GenerationScreens.tsx").read_text(encoding="utf-8")
    theme = Path("frontend/src/theme/theme.ts").read_text(encoding="utf-8")
    build_transform = Path("tools/apply_generation_ui_build.py").read_text(encoding="utf-8")

    for token in ("text", "muted", "page", "card", "border"):
        assert f"var(--prepza-generation-{token}," in generation
        assert f"'--prepza-generation-{token}'" in theme
    assert "background: 'var(--prepza-generation-page, #F8F9FC)'" in build_transform
    assert "'--prepza-generation-color-scheme', mode" in theme
    assert "colorScheme: 'var(--prepza-generation-color-scheme, light)'" in build_transform

def test_generation_controls_have_accessible_selection_and_large_back_target():
    source = Path("frontend/src/generation/GenerationScreens.tsx").read_text(encoding="utf-8")

    assert 'aria-label="Back"' in source
    assert "width: 44, height: 44" in source
    assert "aria-pressed={selected}" in source
    assert "color: disabled ? C.muted : C.text" in source
    assert "background: disabled ? C.border" in source

def test_theme_muted_text_meets_wcag_aa_on_light_and_dark_surfaces():
    source = Path("frontend/src/theme/theme.ts").read_text(encoding="utf-8")
    light_match = re.search(r"const LIGHT_THEME: ThemeTokens = \{[^\n]*textMuted: '([^']+)'", source)
    dark_match = re.search(r"const DARK_THEME: ThemeTokens = \{[^\n]*textMuted: '([^']+)'", source)
    assert light_match and dark_match

    def relative_luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def contrast_ratio(foreground, background):
        foreground_luminance = relative_luminance(foreground)
        background_luminance = relative_luminance(background)
        lighter, darker = sorted((foreground_luminance, background_luminance), reverse=True)
        return (lighter + 0.05) / (darker + 0.05)

    assert contrast_ratio(light_match.group(1), "#F8F9FC") >= 4.5
    assert contrast_ratio(light_match.group(1), "#FFFFFF") >= 4.5
    assert contrast_ratio(dark_match.group(1), "#0A0E1A") >= 4.5

