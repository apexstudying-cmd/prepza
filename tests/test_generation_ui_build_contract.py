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

    assert "('// ─── PODCAST PLAYER', '// ─── SUMMARY'" in source
    assert "aliases = ('// ─── FLASHCARDS',) if start_marker == '// ─── PODCAST PLAYER' else ()" in source
    assert "is_study_flashcards = end_marker == '// ─── QUIZ'" in source
    assert "// ─── FLASHCARDS" in study
    assert "function FlashcardsScreen(" in study
    assert ("// ─── PODCAST PLAYER" in app) or ("// ─── FLASHCARDS" in app)
    assert "function PodcastPlayerScreen(" in app


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
