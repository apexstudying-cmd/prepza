"""Guard Library publication and moderation model extraction."""

from pathlib import Path

from extensions import db


ROOT = Path(__file__).resolve().parents[1]


def test_library_models_register_with_original_bookmark_constraint():
    import library_models

    expected = {"library_publication", "saved_library_material", "library_report"}
    assert expected <= set(db.metadata.tables)
    assert library_models.LibraryPublication.__tablename__ == "library_publication"
    assert library_models.SavedLibraryMaterial.__tablename__ == "saved_library_material"
    assert library_models.LibraryReport.__tablename__ == "library_report"
    constraints = {
        item.name for item in db.metadata.tables["saved_library_material"].constraints
    }
    assert "uq_saved_material_user_pub" in constraints
    report_columns = set(db.metadata.tables["library_report"].columns.keys())
    assert {"library_publication_id", "reporter_user_id", "reason", "status", "reviewed_by"} <= report_columns


def test_app_reexports_library_models_for_legacy_imports():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    expected_import = (
        "from library_models import (\n"
        "    LibraryPublication, SavedLibraryMaterial, LibraryReport,\n"
        ")"
    )
    assert expected_import in source
    for name in ("LibraryPublication", "SavedLibraryMaterial", "LibraryReport"):
        assert f"class {name}(db.Model):" not in source


def test_library_prebuild_transforms_follow_the_extracted_model_owner():
    root = Path(__file__).resolve().parents[1]
    academic = (root / "tools" / "apply_library_academic_context.py").read_text(encoding="utf-8")
    eligibility = (root / "tools" / "apply_library_exact_academic_eligibility.py").read_text(encoding="utf-8")
    assert 'LIBRARY_MODELS = ROOT / "library_models.py"' in academic
    assert 'library_model_text = LIBRARY_MODELS.read_text(encoding="utf-8")' in academic
    assert 'LIBRARY_ROUTES = ROOT / "library_routes.py"' in academic
    assert 'route_source = LIBRARY_ROUTES.read_text(encoding="utf-8")' in academic
    assert 'LIBRARY_MODELS = ROOT / "library_models.py"' in eligibility
    assert 'library_model_text = LIBRARY_MODELS.read_text(encoding="utf-8")' in eligibility
    assert 'LIBRARY_ROUTES = ROOT / "library_routes.py"' in eligibility
    assert 'route_source = LIBRARY_ROUTES.read_text(encoding="utf-8")' in eligibility

def test_library_route_transformers_target_library_routes_module():
    root = Path(__file__).resolve().parents[1]
    exact = (root / "tools" / "apply_library_exact_academic_eligibility.py").read_text(encoding="utf-8")
    studyhub = (root / "tools" / "apply_studyhub_library_rules.py").read_text(encoding="utf-8")
    unit_audit = (root / "tools" / "audit_unit_references.py").read_text(encoding="utf-8")
    assert 'LIBRARY_ROUTES = ROOT / "library_routes.py"' in exact
    assert 'LIBRARY_ROUTES = ROOT / "library_routes.py"' in studyhub
    assert 'RUNTIME_SOURCES = [APP, LIBRARY_ROUTES, GROUP_ROUTES]' in unit_audit


def test_exact_library_eligibility_transform_updates_extracted_routes_idempotently(tmp_path):
    import shutil
    import subprocess
    import sys

    for relative in ("app.py", "library_routes.py", "library_models.py", "tools/apply_library_exact_academic_eligibility.py"):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    script = tmp_path / "tools" / "apply_library_exact_academic_eligibility.py"
    app = tmp_path / "app.py"
    routes = tmp_path / "library_routes.py"

    first = subprocess.run([sys.executable, str(script)], cwd=tmp_path, text=True, capture_output=True, check=False)
    assert first.returncode == 0, first.stdout + first.stderr
    transformed_app = app.read_text(encoding="utf-8")
    transformed_routes = routes.read_text(encoding="utf-8")
    assert 'LIBRARY_MATERIAL_TYPES = {"lecture_notes", "past_paper"}' in transformed_app
    assert "def _library_context_matches(viewer, publication):" in transformed_app
    assert "Selected course does not belong to the selected university" in transformed_routes
    assert "LibraryPublication.semester == viewer.semester" in transformed_routes
    assert "_library_context_matches(viewer, publication)" in transformed_routes

    second = subprocess.run([sys.executable, str(script)], cwd=tmp_path, text=True, capture_output=True, check=False)
    assert second.returncode == 0, second.stdout + second.stderr
    assert app.read_text(encoding="utf-8") == transformed_app
    assert routes.read_text(encoding="utf-8") == transformed_routes
