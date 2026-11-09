"""Study Library publication, bookmark, and moderation ORM models."""

from datetime import datetime

from extensions import db


class LibraryPublication(db.Model):
    """
    A student's document submitted for publication to the public Prepza
    Library. One Document can have at most one active publication - if
    rejected, the student is expected to resubmit as a new row (keeps a
    clean history rather than mutating a rejected submission back to
    pending).
    """
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey("document.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    university_id = db.Column(db.Integer, db.ForeignKey("university.id"), nullable=True)
    program_id = db.Column(db.Integer, db.ForeignKey("program.id"), nullable=True)
    year = db.Column(db.Integer, nullable=True)
    semester = db.Column(db.Integer, nullable=True)

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(1000), nullable=True)
    material_type = db.Column(db.String(30), nullable=False)
    # lecture_notes | past_paper | summary | other
    status = db.Column(db.String(20), nullable=False, default="pending")
    # pending -> approved | rejected -> removed
    rejection_reason = db.Column(db.String(500), nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    view_count = db.Column(db.Integer, nullable=False, default=0)
    save_count = db.Column(db.Integer, nullable=False, default=0)
    xp_awarded = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SavedLibraryMaterial(db.Model):
    """A student bookmarking a published library item (Library > Saved tab)."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    library_publication_id = db.Column(db.Integer, db.ForeignKey("library_publication.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("user_id", "library_publication_id", name="uq_saved_material_user_pub"),
    )

class LibraryReport(db.Model):
    """
    Student report against a *published* library item (distinct from
    Document.report_reason, which covers a student's own personal upload
    before/without publication). Feeds the admin moderation queue.
    """
    id = db.Column(db.Integer, primary_key=True)
    library_publication_id = db.Column(db.Integer, db.ForeignKey("library_publication.id"), nullable=False)
    reporter_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    reason = db.Column(db.String(50), nullable=False)
    details = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    # pending -> dismissed | actioned
    reviewed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    admin_notes = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


from study_models import (
    XpEvent, StudyStreak, StudyActivityLog, StudyTimeLog,
    QuizAttempt, FlashcardSession, UserAchievement, AiUsageLog,
    STUDY_TIME_FEATURES,
)
