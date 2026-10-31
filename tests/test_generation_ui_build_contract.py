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
