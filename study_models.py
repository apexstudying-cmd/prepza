"""Study activity, streak, assessment, and AI usage ORM models."""

from datetime import datetime

from extensions import db


class XpEvent(db.Model):
    """
    Minimal server-side XP ledger. Each row is one XP-earning event: the
    unique constraint on (user_id, event_type, related_id) makes awarding
    idempotent - re-running an approval action can never double-award XP
    for the same publication.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    event_type = db.Column(db.String(40), nullable=False)
    # library_publication_approved | ... (more event types added in later chunks)
    xp_amount = db.Column(db.Integer, nullable=False)
    related_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("user_id", "event_type", "related_id", name="uq_xp_event_user_type_related"),
    )


class StudyStreak(db.Model):
    """
    One row per user - the running streak counter. Recomputed
    incrementally whenever a new StudyActivityLog day is recorded
    (see record_study_activity()), not by scanning history on every
    request.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    current_streak = db.Column(db.Integer, nullable=False, default=0)
    longest_streak = db.Column(db.Integer, nullable=False, default=0)
    last_study_date = db.Column(db.Date, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class StudyActivityLog(db.Model):
    """
    One row per user per calendar day that had at least one qualifying
    study action (document studied, quiz completed, flashcards
    completed, podcast generated). Drives both the streak calendar and
    the "once per document per day" XP cap on record_document_studied()
    - the unique constraint is what makes that cap idempotent, not the
    XpEvent table (which has no date dimension).
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    document_content_id = db.Column(db.Integer, db.ForeignKey("document_content.id"), nullable=True)
    activity_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "document_content_id", "activity_date",
            name="uq_study_activity_user_doc_date",
        ),
    )


STUDY_TIME_FEATURES = {"reading", "podcast", "quiz", "flashcards", "tutor_chat", "mindmap", "offline"}


class StudyTimeLog(db.Model):
    """
    Authoritative Study Hub learning time, one row per user per Nairobi
    calendar day using the single STUDY_TIME_FEATURE key. Documents,
    pages, and features are context in the client, not independent
    authoritative clocks. Study time is reconciled from absolute client
    totals; last_heartbeat_at is retained only for backward schema
    compatibility and is no longer used for credit calculation.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    activity_date = db.Column(db.Date, nullable=False)
    feature = db.Column(db.String(20), nullable=False, default="reading")
    study_time_seconds = db.Column(db.Integer, nullable=False, default=0)
    last_heartbeat_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (
        db.UniqueConstraint("user_id", "activity_date", "feature", name="uq_study_time_user_date_feature"),
    )


class QuizAttempt(db.Model):
    """
    A single quiz completion. Deliberately not deduplicated - a student
    retaking the same quiz is a legitimate new attempt, both for XP and
    for the "Quiz Master" achievement's attempt count. Abuse is bounded
    by the rate limit on the completion endpoint, same pattern as
    generation.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    generated_material_id = db.Column(db.Integer, db.ForeignKey("generated_material.id"), nullable=False)
    document_content_id = db.Column(db.Integer, db.ForeignKey("document_content.id"), nullable=False)
    score_percent = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class FlashcardSession(db.Model):
    """A single completed flashcard review session. Same reasoning as
    QuizAttempt - every session is a legitimate new event."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    generated_material_id = db.Column(db.Integer, db.ForeignKey("generated_material.id"), nullable=False)
    document_content_id = db.Column(db.Integer, db.ForeignKey("document_content.id"), nullable=False)
    cards_reviewed = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class UserAchievement(db.Model):
    """
    Unlocked achievements. The achievement catalog itself
    (ACHIEVEMENT_DEFINITIONS) is a hardcoded constant, not a DB table -
    same MVP tradeoff as the fixed XP_* amounts below. Unique constraint
    makes unlock_achievement() idempotent.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    achievement_code = db.Column(db.String(40), nullable=False)
    unlocked_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("user_id", "achievement_code", name="uq_user_achievement_user_code"),
    )


class AiUsageLog(db.Model):
    # forum_reply_id FK below is left in place (nullable, never populated
    # elsewhere in this file) rather than removed - same FK-safety
    # precedent as Unit/UnitProgram: this repo has no db.create_all()/
    # Alembic, so dropping the column would need its own hand-written
    # migration, and the column costs nothing sitting unused.
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    forum_reply_id = db.Column(db.Integer, db.ForeignKey("forum_reply.id"), nullable=True)
    request_type = db.Column(db.String(20), nullable=False)
    model = db.Column(db.String(50), nullable=True)
    provider = db.Column(db.String(20), nullable=True)
    input_tokens = db.Column(db.Integer, default=0)
    output_tokens = db.Column(db.Integer, default=0)
    cache_read_tokens = db.Column(db.Integer, default=0)
    cache_creation_tokens = db.Column(db.Integer, default=0)
    cost_usd = db.Column(db.Numeric(10, 6), default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
