from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
SCREENS = (ROOT / "frontend/src/screens/study/GeneratedStudyScreens.tsx").read_text(encoding="utf-8")
GENERATION = (ROOT / "frontend/src/generation/GenerationScreens.tsx").read_text(encoding="utf-8")
STUDY_GENERATION = (ROOT / "frontend/src/generation/StudyGenerationScreensClean.tsx").read_text(encoding="utf-8")
ACHIEVEMENTS = (ROOT / "frontend/src/screens/gamification/AchievementsScreen.tsx").read_text(encoding="utf-8")


def test_active_summary_and_mind_map_routes_are_study_module_owned() -> None:
    assert "SummaryStudyScreen" in APP
    assert "MindMapStudyScreen" in APP
    assert "function SummaryScreen(" not in APP
    assert "function MindMapScreen(" not in APP
    assert "type MindMapNode" not in APP
    assert "case 'summary':" in APP
    assert "case 'mind-map':" in APP


def test_generated_material_route_wrappers_preserve_shell_layout_and_navigation() -> None:
    assert "export function SummaryStudyScreen(" in SCREENS
    assert "export function MindMapStudyScreen(" in SCREENS
    assert "setScreen('share-sheet')" in ACHIEVEMENTS
    assert "setScreen('document-study')" in STUDY_GENERATION
    assert "var(--prepza-generation-color-scheme, light)" in SCREENS
    assert "var(--prepza-generation-page, #F8F9FC)" in SCREENS
    assert "WebkitOverflowScrolling: 'touch'" in SCREENS


def test_generation_logic_remains_owned_by_existing_generation_modules() -> None:
    for contract in (
        "export function SummaryGenerationScreen(",
        "export function FlashcardsGenerationScreen(",
        "loadSelectedGeneratedMaterial",
        "normalizeSelectedMaterialType",
        "prepza-open-material",
    ):
        assert contract in GENERATION
    for contract in (
        "export function MindMapGenerationScreen(",
        "export function PracticeQuestionsGenerationScreen(",
        "loadSelectedGeneratedMaterial",
        "prepza-open-material",
    ):
        assert contract in STUDY_GENERATION


def test_generation_build_transform_targets_feature_module_not_app_shell() -> None:
    transform = (ROOT / "tools/apply_generation_ui_build.py").read_text(encoding="utf-8")
    assert "SummaryStudyScreen" in transform
    assert "MindMapStudyScreen" in transform
    assert "SummaryGenerationScreen" in transform
    assert "MindMapGenerationScreen" in transform
    assert "from './generation/GenerationScreens'" not in transform
    assert "from './generation/StudyGenerationScreensClean'" not in transform
