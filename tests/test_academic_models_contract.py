"""Guard the academic catalog ORM mappings while extracting them into a shared module."""

from pathlib import Path

from extensions import db
from academic_models import Program, University

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
USER_MODELS_SOURCE = (ROOT / "user_models.py").read_text(encoding="utf-8")
CORE_MODELS_SOURCE = (ROOT / "core_models.py").read_text(encoding="utf-8")
ACADEMIC_MODELS_SOURCE = (ROOT / "academic_models.py").read_text(encoding="utf-8")


def test_academic_models_share_the_existing_sqlalchemy_metadata():
    assert University.metadata is db.Model.metadata
    assert Program.metadata is db.Model.metadata
    assert University.__table__.metadata is Program.__table__.metadata


def test_university_table_name_columns_constraints_and_defaults_are_unchanged():
    table = University.__table__
    assert table.name == "university"
    assert table.c.id.primary_key
    assert table.c.name.type.length == 150
    assert not table.c.name.nullable
    assert table.c.short_code.type.length == 20
    assert not table.c.short_code.nullable
    assert table.c.short_code.unique is True
    assert table.c.country.type.length == 80
    assert table.c.country.nullable
    assert table.c.is_active.type.python_type is bool
    assert not table.c.is_active.nullable
    assert table.c.is_active.default.arg is True
    assert table.c.created_at.default.arg.__name__ == "utcnow"


def test_program_table_name_columns_foreign_key_and_defaults_are_unchanged():
    table = Program.__table__
    assert table.name == "program"
    assert table.c.id.primary_key
    assert table.c.university_id.type.python_type is int
    assert not table.c.university_id.nullable
    assert {fk.target_fullname for fk in table.c.university_id.foreign_keys} == {"university.id"}
    assert table.c.name.type.length == 150
    assert not table.c.name.nullable
    assert table.c.degree_level.type.length == 50
    assert table.c.degree_level.nullable
    assert table.c.discipline_category.type.length == 80
    assert table.c.discipline_category.nullable
    assert table.c.is_active.type.python_type is bool
    assert not table.c.is_active.nullable
    assert table.c.is_active.default.arg is True
    assert table.c.created_at.default.arg.__name__ == "utcnow"


def test_app_reexports_model_classes_from_their_shared_feature_modules():
    assert "from user_models import User" in APP_SOURCE
    assert "from core_models import ContentItem, Payment, SystemSetting, ViewProgress" in APP_SOURCE
    assert "from academic_models import University, Program" in APP_SOURCE

    assert "class User(db.Model):" not in APP_SOURCE
    assert "class ContentItem(db.Model):" not in APP_SOURCE
    assert "class University(db.Model):" not in APP_SOURCE
    assert "class Program(db.Model):" not in APP_SOURCE

    assert "class User(db.Model):" in USER_MODELS_SOURCE
    assert "class ContentItem(db.Model):" in CORE_MODELS_SOURCE
    assert "class University(db.Model):" in ACADEMIC_MODELS_SOURCE
    assert "class Program(db.Model):" in ACADEMIC_MODELS_SOURCE
