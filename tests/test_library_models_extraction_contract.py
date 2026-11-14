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
    assert 'text = LIBRARY_ROUTES.read_text(encoding="utf-8")' in academic
    assert 'LIBRARY_MODELS = ROOT / "library_models.py"' in eligibility
    assert 'library_model = LIBRARY_MODELS.read_text(encoding="utf-8")' in eligibility
    assert 'LIBRARY_ROUTES = ROOT / "library_routes.py"' in eligibility
    assert 'route_text = LIBRARY_ROUTES.read_text(encoding="utf-8")' in eligibility
