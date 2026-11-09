"""Guard the study and gamification model extraction."""

from pathlib import Path

from extensions import db


ROOT = Path(__file__).resolve().parents[1]


def test_study_models_register_on_shared_metadata_with_original_constraints():
    import study_models

    expected_tables = {
        "xp_event",
        "study_streak",
        "study_activity_log",
        "study_time_log",
        "quiz_attempt",
        "flashcard_session",
        "user_achievement",
        "ai_usage_log",
    }
    assert expected_tables <= set(db.metadata.tables)
    assert study_models.STUDY_TIME_FEATURES == {
        "reading", "podcast", "quiz", "flashcards", "tutor_chat", "mindmap", "offline"
    }
    assert study_models.XpEvent.__tablename__ == "xp_event"
    assert study_models.StudyStreak.__tablename__ == "study_streak"
    assert study_models.StudyActivityLog.__tablename__ == "study_activity_log"
    assert study_models.StudyTimeLog.__tablename__ == "study_time_log"
    assert study_models.QuizAttempt.__tablename__ == "quiz_attempt"
    assert study_models.FlashcardSession.__tablename__ == "flashcard_session"
    assert study_models.UserAchievement.__tablename__ == "user_achievement"
    assert study_models.AiUsageLog.__tablename__ == "ai_usage_log"

    constraint_names = {
        table: {constraint.name for constraint in db.metadata.tables[table].constraints}
        for table in (
            "xp_event",
            "study_activity_log",
            "study_time_log",
            "user_achievement",
        )
    }
    assert "uq_xp_event_user_type_related" in constraint_names["xp_event"]
    assert "uq_study_activity_user_doc_date" in constraint_names["study_activity_log"]
    assert "uq_study_time_user_date_feature" in constraint_names["study_time_log"]
    assert "uq_user_achievement_user_code" in constraint_names["user_achievement"]


def test_app_reexports_study_models_for_legacy_imports():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    expected_import = (
        "from study_models import (\n"
        "    XpEvent, StudyStreak, StudyActivityLog, StudyTimeLog,\n"
        "    QuizAttempt, FlashcardSession, UserAchievement, AiUsageLog,\n"
        "    STUDY_TIME_FEATURES,\n"
        ")"
    )
    assert expected_import in source
    for name in (
        "XpEvent", "StudyStreak", "StudyActivityLog", "StudyTimeLog",
        "QuizAttempt", "FlashcardSession", "UserAchievement", "AiUsageLog",
    ):
        assert f"class {name}(db.Model):" not in source
