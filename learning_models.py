"""Student learning domain ORM models.

These classes use the shared SQLAlchemy metadata from extensions.py. app.py
re-exports them below to preserve legacy imports while model ownership moves
into domain modules.
"""

from datetime import datetime

from extensions import db


class StudentLearningProfile(db.Model):
    """
    One row per user, capturing inferred learning preferences. Every
    preference field starts NULL and is only filled in gradually from
    observed behavior - nothing here is set at signup or assumed on
    day one, per the Ada design doc's "do not assume immediately"
    principle. No inference logic lands with this patch - just the
    shape to write into once it does.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    preferred_explanation_style = db.Column(db.String(30), nullable=True)
    # direct | socratic | analogy | worked_example
    prefers_examples = db.Column(db.Boolean, nullable=True)
    prefers_theory_vs_practice = db.Column(db.String(20), nullable=True)
    # theory | practice | balanced
    preferred_difficulty = db.Column(db.String(20), nullable=True)
    # easier | standard | harder
    typical_session_length_minutes = db.Column(db.Integer, nullable=True)
    learning_pace = db.Column(db.String(20), nullable=True)
    # slow | moderate | fast
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LearningConcept(db.Model):
    """
    A simple, ungoverned concept catalog - rows are upserted on first
    mention via generate_tutor_reply()'s trailing [[CONCEPT: ...]]
    marker (see the concept-detection design decision), no admin
    curation for MVP. unit_id is optional and best-effort: personal
    Documents aren't unit-scoped in the current schema (only
    ContentItem is), so this stays NULL whenever that link can't be
    inferred confidently.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class LearningEvent(db.Model):
    """
    One row per tutor turn where a concept was detected - the raw
    signal a later mastery-scoring pass (Ada Phase 2, not built here)
    will aggregate over. Deliberately NOT computing a mastery number in
    this patch, per the Ada doc's phasing. evidence_snippet is a short
    excerpt, not the full message, to keep this table lean rather than
    duplicating tutor_message.content. document_content_id is
    denormalized from the parent conversation so mastery-by-document
    queries won't need to join through tutor_message -> 
    tutor_conversation every time.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    concept_id = db.Column(db.Integer, db.ForeignKey("learning_concept.id"), nullable=False)
    tutor_message_id = db.Column(db.Integer, db.ForeignKey("tutor_message.id"), nullable=True)
    # nullable - a future non-tutor-chat learning signal (e.g. a quiz
    # misconception) could populate this table too without a schema
    # change, per the Ada doc's generalized learning-event system.
    document_content_id = db.Column(db.Integer, db.ForeignKey("document_content.id"), nullable=True)
    evidence_snippet = db.Column(db.String(500), nullable=True)
    misconception = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------- Ada Phase 2 (concept mastery) ----------

class StudentConceptMastery(db.Model):
    """
    One row per (user, concept), aggregating LearningEvent rows into a
    running mastery estimate. Deliberately naive for this first pass -
    every LearningEvent today is an "exposure" signal only (a concept
    came up in a tutor turn), with no correctness signal yet, per the
    Ada doc's "initial algorithm can be simple, architecture should
    allow improvement later" guidance (see section 19, MASTERy MODEL).
    Real correctness data (quiz/past-paper attempts) will feed into
    update_concept_mastery() once Phase 4 exists, without a schema
    change here - misconception_count and the scoring inputs below are
    already shaped to take that signal when it lands.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    concept_id = db.Column(db.Integer, db.ForeignKey("learning_concept.id"), nullable=False)
    mastery_score = db.Column(db.Integer, nullable=False, default=0)
    # 0-100. Naive exposure-based estimate for now - see class docstring.
    confidence = db.Column(db.String(20), nullable=False, default="low")
    # low | moderate | high - reflects how much EVIDENCE backs the
    # score, not the score itself. A student could have a high
    # mastery_score off few exposures, which is exactly what "low"
    # confidence here is meant to flag as not yet reliable.
    exposure_count = db.Column(db.Integer, nullable=False, default=0)
    misconception_count = db.Column(db.Integer, nullable=False, default=0)
    last_practiced_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("user_id", "concept_id", name="uq_concept_mastery_user_concept"),
    )


class ConceptPrerequisite(db.Model):
    """
    A directed edge: concept_id requires prerequisite_concept_id.
    Deliberately ungoverned/no admin curation for MVP, same tradeoff as
    LearningConcept itself - rows are upserted organically whenever the
    tutor names a prerequisite via its trailing [[PREREQUISITE: ...]]
    marker (see the marker-protocol extension in ai_service.py).
    Global, not per-student, same scope as LearningConcept - "Bayes
    Theorem requires Conditional Probability" is a fact about the
    subject matter, not about any one student.
    """
    id = db.Column(db.Integer, primary_key=True)
    concept_id = db.Column(db.Integer, db.ForeignKey("learning_concept.id"), nullable=False)
    prerequisite_concept_id = db.Column(db.Integer, db.ForeignKey("learning_concept.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("concept_id", "prerequisite_concept_id", name="uq_concept_prerequisite_pair"),
    )
