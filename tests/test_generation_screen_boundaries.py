from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
GENERATION = (ROOT / "frontend/src/generation/GenerationScreens.tsx").read_text(encoding="utf-8")
STUDY_GENERATION = (ROOT / "frontend/src/generation/StudyGenerationScreensClean.tsx").read_text(encoding="utf-8")
TRANSFORM = (ROOT / "tools/apply_generation_ui_build.py").read_text(encoding="utf-8")


def test_summary_and_mind_map_source_routes_remain_mounted_in_the_app_shell() -> None:
    assert "function SummaryScreen(" in APP
    assert "function MindMapScreen(" in APP
    assert "case 'summary':" in APP
    assert "case 'mind-map':" in APP


def test_generation_logic_is_owned_by_the_existing_generation_modules() -> None:
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


def test_prebuild_wraps_generation_owners_without_changing_route_keys() -> None:
    for contract in (
        "import { FlashcardsGenerationScreen, SummaryGenerationScreen } from './generation/GenerationScreens'",
        "import { PracticeQuestionsGenerationScreen, MindMapGenerationScreen } from './generation/StudyGenerationScreensClean'",
        "function SummaryScreen(",
        "SummaryGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId}",
        "function MindMapScreen(",
        "MindMapGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId}",
        "PracticeQuestionsGenerationScreen setScreen={setScreen} activeDocumentId={activeDocumentId}",
        "var(--prepza-generation-color-scheme, light)",
        "var(--prepza-generation-page, #F8F9FC)",
        "WebkitOverflowScrolling: 'touch'",
    ):
        assert contract in TRANSFORM, f"missing generation build contract: {contract}"
    assert "case 'summary':" in APP
    assert "case 'mind-map':" in APP


def test_generation_navigation_and_offline_artifact_replay_contracts_remain_owned() -> None:
    assert "setScreen('document-study')" in GENERATION
    assert "setScreen('document-study')" in STUDY_GENERATION
    assert "prepza-open-material" in GENERATION
    assert "prepza-open-material" in STUDY_GENERATION
