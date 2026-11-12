"""Guard the learning-model extraction without changing SQLAlchemy metadata."""

from pathlib import Path

from extensions import db


ROOT = Path(__file__).resolve().parents[1]


def test_learning_models_are_registered_on_the_shared_database_metadata():
    import learning_models

    expected = {
        "student_learning_profile",
        "learning_concept",
        "learning_event",
        "student_concept_mastery",
        "concept_prerequisite",
    }
    assert expected <= set(db.metadata.tables)
    assert learning_models.StudentLearningProfile.__tablename__ == "student_learning_profile"
    assert learning_models.LearningConcept.__tablename__ == "learning_concept"
    assert learning_models.LearningEvent.__tablename__ == "learning_event"
    assert learning_models.StudentConceptMastery.__tablename__ == "student_concept_mastery"
    assert learning_models.ConceptPrerequisite.__tablename__ == "concept_prerequisite"


def test_app_keeps_legacy_learning_model_imports_and_threshold_constant():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    module = (ROOT / "learning_models.py").read_text(encoding="utf-8")
    expected_import = (
        "from learning_models import (\n"
        "    StudentLearningProfile, LearningConcept, LearningEvent,\n"
        "    StudentConceptMastery, ConceptPrerequisite,\n"
        ")"
    )
    assert expected_import in source
    for name in (
        "StudentLearningProfile",
        "LearningConcept",
        "LearningEvent",
        "StudentConceptMastery",
        "ConceptPrerequisite",
    ):
        assert f"class {name}(db.Model):" in module
        assert f"class {name}(db.Model):" not in source
    assert 'MASTERY_CONFIDENCE_THRESHOLDS = {"moderate": 3, "high": 7}' in source
