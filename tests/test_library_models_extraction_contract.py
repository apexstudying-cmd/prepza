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
