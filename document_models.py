"""Document storage, generated study material, and tutor ORM models."""

import json
import os
import re
from datetime import datetime

from sqlalchemy import and_, or_, text

from extensions import db


class DocumentContent(db.Model):
    """
    Deduplicated file content, keyed by a SHA-256 hash computed client-side
    before upload. Multiple students' Document rows can point at the same
    DocumentContent row when they upload byte-identical files - this avoids
    re-uploading, re-extracting, and re-generating AI materials for content
    Prepza has already processed once.
    """
    id = db.Column(db.Integer, primary_key=True)
    content_hash = db.Column(db.String(64), unique=True, nullable=False)
    storage_path = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(20), nullable=False)
    file_size_bytes = db.Column(db.Integer, nullable=False)
    page_count = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    # pending -> processing -> ready | failed
    error_message = db.Column(db.String(500), nullable=True)
    material_id = db.Column(db.Integer, db.ForeignKey("generated_material.id"), nullable=True)
    extracted_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DocumentPageText(db.Model):
    """Page-preserving extracted text for citations and authorized retrieval."""
    id = db.Column(db.Integer, primary_key=True)
    document_content_id = db.Column(
        db.Integer, db.ForeignKey("document_content.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    page_number = db.Column(db.Integer, nullable=False)
    page_text = db.Column(db.Text, nullable=False)
    content_hash = db.Column(db.String(64), nullable=False)
    source_version = db.Column(db.String(64), nullable=False)
    extractor_version = db.Column(db.String(50), nullable=False)
    extracted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (
        db.UniqueConstraint(
            "document_content_id", "page_number",
            name="uq_document_page_text_content_page",
        ),
        db.Index(
            "ix_document_page_text_source_version",
            "document_content_id", "source_version",
        ),
    )

class Document(db.Model):
    """
    A student's personal reference to a piece of DocumentContent. Several
    students can each have their own Document row (own title, own status,
    own delete/report state) pointing at the same underlying DocumentContent
    once dedup kicks in.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    document_content_id = db.Column(db.Integer, db.ForeignKey("document_content.id"), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="uploading")
    # uploading -> processing -> ready | failed ; removed (soft delete) is
    # tracked separately via is_removed so a failed/ready doc can still be
    # cleanly hidden without losing its terminal status.
    is_removed = db.Column(db.Boolean, nullable=False, default=False)
    reported_at = db.Column(db.DateTime, nullable=True)
    report_reason = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_opened_at = db.Column(db.DateTime, nullable=True)

class DocumentReadingProgress(db.Model):
    """Durable per-student page position for the native document reader."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey("document.id"), nullable=False)
    page_num = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("user_id", "document_id", name="uq_document_reading_progress_user_document"),)

class GeneratedMaterial(db.Model):
    """
    AI-generated study material tied to DocumentContent (not to any one
    student's Document row), so it is produced once and reused by every
    student who later matches the same content hash. Populated by the AI
    pipeline in a later chunk - this table just reserves the shape now.
    """
    id = db.Column(db.Integer, primary_key=True)
    document_content_id = db.Column(db.Integer, db.ForeignKey("document_content.id"), nullable=False)
    material_type = db.Column(db.String(20), nullable=False)
    # summary | quiz | flashcards | podcast | mind_map
    status = db.Column(db.String(20), nullable=False, default="pending")
    # pending -> generating -> ready | failed
    payload = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    generation_fingerprint = db.Column(db.String(128), nullable=False)
    generation_parameters = db.Column(db.JSON, nullable=True)
    generation_version = db.Column(db.String(50), nullable=False, default="v2")
    scope = db.Column(db.String(20), nullable=False, default="shared")
    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # ---- Content review (Chunk 10) ----
    # Flagging a material does NOT block a student from generating/
    # studying it privately - it only keeps it out of the public Library
    # (see _flagged_document_ids() / the publish/browse/saved gates
    # below), same reactive kill-switch pattern as Group.is_active /
    # University.is_active elsewhere in this file.
    is_flagged = db.Column(db.Boolean, nullable=False, default=False)
    flagged_reason = db.Column(db.String(500), nullable=True)
    flagged_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    flagged_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.Index("uq_generated_material_fingerprint", "generation_fingerprint", unique=True),
    )


def get_generated_material_for_user(document_content_id, material_type, user_id):
    """Return ready material without crossing the public/private boundary."""
    owned = (
        db.session.query(Document.id)
        .filter(
            Document.user_id == user_id,
            Document.document_content_id == document_content_id,
            Document.is_removed.is_(False),
        )
        .first()
    )
    query = GeneratedMaterial.query.filter_by(
        document_content_id=document_content_id, material_type=material_type, status="ready", generation_version="v2"
    )
    if owned:
        # An owner can replay both their own private generations and any
        # shared/published generation. Publishing a document must never make
        # the student's previously generated private material disappear.
        return query.filter(
            db.or_(
                GeneratedMaterial.scope == "shared",
                db.and_(
                    GeneratedMaterial.scope == "private",
                    GeneratedMaterial.owner_user_id == user_id,
                ),
            )
        ).order_by(GeneratedMaterial.updated_at.desc()).first()

    public = (
        db.session.query(LibraryPublication.id)
        .join(Document, LibraryPublication.document_id == Document.id)
        .filter(Document.document_content_id == document_content_id, LibraryPublication.status == "approved")
        .first()
    )
    if public:
        return query.filter(GeneratedMaterial.scope == "shared").first()
    return None


def _resolve_material_generation(feature, content, user_id, parameters):
    """Resolve generation through the reusable fingerprinted path.

    This is deliberately the same path used by async jobs so the requested
    configuration, variant, quota reservation, artifact identity, and
    privacy scope cannot diverge between sync and async generation.
    """
    from ai_reusable_generation import generate_document_material

    return generate_document_material(
        material_type=feature,
        document_content_id=content.id,
        triggering_user_id=user_id,
        plan_tier=get_ai_plan_tier(user_id),
        parameters=parameters,
    )


AI_JOB_STALE_AFTER_SECONDS = max(300, int(os.environ.get("AI_JOB_STALE_AFTER_SECONDS", "3600")))


def _recover_stale_ai_jobs():
    """Fail abandoned in-process jobs instead of leaving students on 'processing' forever.

    The current worker is intentionally process-local. If Gunicorn/Render kills the
    process, the database row survives but the Python thread does not. This recovery
    boundary makes that failure explicit and safe; the existing fingerprint/idempotency
    layer makes a later retry collapse onto the same artifact instead of double-generating.
    """
    cutoff = datetime.utcnow() - timedelta(seconds=AI_JOB_STALE_AFTER_SECONDS)
    stale_jobs = (
        AiJob.query
        .filter(
            AiJob.status == "processing",
            AiJob.started_at.isnot(None),
            AiJob.started_at < cutoff,
        )
        .all()
    )
    if not stale_jobs:
        return 0
    recovered = 0
    for stale_job in stale_jobs:
        stale_job.status = "failed"
        stale_job.retry_count = int(stale_job.retry_count or 0) + 1
        stale_job.progress_stage = "worker stopped; retry required"
        stale_job.error_message = (
            f"Background worker stopped before completion. The job exceeded the "
            f"{AI_JOB_STALE_AFTER_SECONDS}-second recovery window; retry is safe."
        )[:500]
        stale_job.completed_at = datetime.utcnow()
        recovered += 1
    db.session.commit()
    app.logger.warning("Recovered %s stale AI generation job(s)", recovered)
    return recovered


def _start_async_material_generation(document_content_id, user_id, feature, parameters):
    """Create a user-visible job and run the exact requested generation off-request."""
    _recover_stale_ai_jobs()
    if not isinstance(parameters, dict):
        raise ValueError("AI generation parameters must be an object")
    job = AiJob(
        document_content_id=document_content_id,
        user_id=user_id,
        feature=feature,
        generation_parameters=dict(parameters),
        status="processing",
        progress_percent=5,
        progress_stage="queued",
        started_at=datetime.utcnow(),
    )
    db.session.add(job)
    db.session.commit()
    job_id = job.id
    app_obj = app

    def worker():
        with app_obj.app_context():
            local_job = db.session.get(AiJob, job_id)
            try:
                local_job.progress_percent = 12
                local_job.progress_stage = "preparing"
                db.session.commit()
                from ai_reusable_generation import generate_document_material
                requested_parameters = dict(local_job.generation_parameters or {})
                local_job.progress_percent = 20
                local_job.progress_stage = "generating with AI"
                db.session.commit()
                result = generate_document_material(
                    material_type=feature,
                    document_content_id=document_content_id,
                    triggering_user_id=user_id,
                    plan_tier=get_ai_plan_tier(user_id),
                    parameters=requested_parameters,
                )
                local_job.material_id = result.get("material_id")
                local_job.progress_percent = 92
                local_job.progress_stage = "saving generated material"
                db.session.commit()
                local_job.status = "completed"
                local_job.progress_percent = 100
                local_job.progress_stage = "ready"
                local_job.completed_at = datetime.utcnow()
                db.session.commit()
                return result
            except Exception as exc:
                db.session.rollback()
                local_job = db.session.get(AiJob, job_id)
                if local_job:
                    local_job.status = "failed"
                    local_job.progress_stage = "failed"
                    local_job.error_message = str(exc)[:500]
                    local_job.completed_at = datetime.utcnow()
                    db.session.commit()
                print(f"ERROR: async {feature} generation job {job_id} failed: {exc}")

    Thread(target=worker, daemon=True).start()
    return job_id


@app.route("/ai-jobs/<int:job_id>")
def get_ai_job_status(job_id):
    # Reconcile abandoned process-local jobs before reporting status so a
    # student never sees an indefinitely stuck "processing" job.
    _recover_stale_ai_jobs()
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    job = db.session.get(AiJob, job_id)
    if not job:
        return jsonify({"error": "Generation job not found"}), 404
    document = Document.query.filter_by(document_content_id=job.document_content_id, user_id=user_id, is_removed=False).first()
    if not document:
        return jsonify({"error": "Generation job not found"}), 404
    progress_job = job
    if job.status == "processing":
        nested = (
            AiJob.query
            .filter(AiJob.document_content_id == job.document_content_id, AiJob.feature == job.feature, AiJob.id > job.id)
            .order_by(AiJob.id.desc())
            .first()
        )
        if nested:
            progress_job = nested
    payload = None
    if job.status == "completed" and job.material_id:
        material = db.session.get(GeneratedMaterial, job.material_id)
        if material and material.payload:
            try:
                payload = json.loads(material.payload)
            except (TypeError, ValueError):
                payload = None
    return jsonify({
        "job_id": job.id,
        "status": job.status,
        "progress_percent": int(progress_job.progress_percent or 0),
        "progress_stage": progress_job.progress_stage or "working",
        "error": job.error_message,
        "material_id": job.material_id,
        "payload": payload,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    })

class AiJob(db.Model):
    """
    Tracks one background AI/processing run (text extraction today;
    summary/quiz/flashcard/podcast/mind_map generation later) so it can
    be inspected, retried, and eventually picked up by a real queue
    without changing this bookkeeping shape.
    """
    id = db.Column(db.Integer, primary_key=True)
    document_content_id = db.Column(db.Integer, db.ForeignKey("document_content.id"), nullable=False)
    # Nullable for legacy text-extraction jobs; required on all student generation jobs.
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    feature = db.Column(db.String(30), nullable=False)
    # text_extraction | summary | quiz | flashcards | podcast | podcast_audio | mind_map
    status = db.Column(db.String(20), nullable=False, default="pending")
    progress_percent = db.Column(db.Integer, nullable=False, default=0)
    progress_stage = db.Column(db.String(80), nullable=True)
    # pending -> processing -> completed | failed
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.String(500), nullable=True)
    retry_count = db.Column(db.Integer, nullable=False, default=0)
    material_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    batch_id = db.Column(db.String(100), nullable=True)
    # Immutable request configuration used by the generation worker. Keeping
    # it on the job makes the requested generation auditable and prevents a
    # future retry worker from reconstructing a different request.
    generation_parameters = db.Column(db.JSON, nullable=False, default=dict)
    # Notification row to finalize when a background generation completes.
    notification_id = db.Column(db.Integer, db.ForeignKey("notification.id"), nullable=True)
    # Worker identity that owns an active podcast-audio claim. This is
    # fenced during stale-worker recovery so a replacement worker cannot
    # accidentally complete an old claim.
    claimed_worker_id = db.Column(db.String(64), nullable=True, index=True)
    # legacy provider Message Batch id, when this job's AI call(s) went through
    # the Batch API instead of a synchronous call - lets an admin look up
    # the batch directly in the legacy provider Console if a job seems stuck.


# ---------- Ada Phase 1 (tutor chat + learning foundation) ----------

class TutorConversation(db.Model):
    """
    One persistent conversation per (student, document) pair - not a
    global tutor thread, not session-only/ephemeral. Every other
    feature in Prepza persists (quiz attempts, flashcard sessions, view
    progress) and grounding each conversation in one specific document
    is what makes tutoring useful vs. generic chat - locked decision,
    see the tutor chat design handoff.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    document_content_id = db.Column(db.Integer, db.ForeignKey("document_content.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("user_id", "document_content_id", name="uq_tutor_conv_user_doc"),
    )

class TutorMessage(db.Model):
    """
    Deliberately lean - no per-message token/cost tracking on this row
    itself; usage stays centralized in AiUsageLog like every other AI
    feature (request_type="tutor_message").
    """
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("tutor_conversation.id", ondelete="CASCADE"), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # "user" | "assistant"
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


from learning_models import (
    StudentLearningProfile, LearningConcept, LearningEvent,
    StudentConceptMastery, ConceptPrerequisite,
)


MASTERY_CONFIDENCE_THRESHOLDS = {"moderate": 3, "high": 7}
# exposure_count needed to reach each confidence tier - below
# "moderate"'s threshold, confidence stays "low" regardless of score.


def _mastery_gain_for_exposure(exposure_count_before):
    """
    Diminishing-returns gain curve: an early exposure moves the needle
    a lot (a student's first few encounters with a concept are the
    most informative), later exposures move it less. Floor of 3 so
    mastery never fully plateaus from continued engagement alone.
    Deliberately simple - see StudentConceptMastery's docstring.
    """
    return max(3, 20 - 2 * exposure_count_before)


def update_concept_mastery(user_id, concept_id, had_misconception=False):
    """
    Get-or-creates a StudentConceptMastery row and applies one
    exposure update. Called from ai_service.generate_tutor_reply()
    right after a LearningEvent is logged for this concept - one call
    per detected concept per tutor turn.

    On a normal exposure, mastery_score increases per
    _mastery_gain_for_exposure() (diminishing returns, capped at 100).
    On a flagged misconception, mastery_score decreases by a fixed
    penalty instead (floored at 0) and misconception_count increments -
    LearningEvent.misconception isn't populated by anything yet as of
    this patch, so this branch is currently unreachable in practice,
    but the scoring function is ready for whenever misconception
    detection lands rather than needing another schema/logic change.

    Does NOT commit - caller is expected to commit alongside whatever
    else it's persisting in the same request (matches award_xp() /
    record_study_activity()'s pattern elsewhere in this file, which
    also leave the commit to their caller).
    """
    row = StudentConceptMastery.query.filter_by(user_id=user_id, concept_id=concept_id).first()
    if not row:
        row = StudentConceptMastery(user_id=user_id, concept_id=concept_id)
        db.session.add(row)
        db.session.flush()

    if had_misconception:
        row.misconception_count = (row.misconception_count or 0) + 1
        row.mastery_score = max(0, row.mastery_score - 10)
    else:
        gain = _mastery_gain_for_exposure(row.exposure_count)
        row.mastery_score = min(100, row.mastery_score + gain)

    row.exposure_count = (row.exposure_count or 0) + 1
    row.last_practiced_at = datetime.utcnow()

    if row.exposure_count >= MASTERY_CONFIDENCE_THRESHOLDS["high"]:
        row.confidence = "high"
    elif row.exposure_count >= MASTERY_CONFIDENCE_THRESHOLDS["moderate"]:
        row.confidence = "moderate"
    else:
        row.confidence = "low"

    return row


def get_student_mastery_snapshot(user_id, document_content_id, limit=10):
    """
    Returns this student's current mastery for concepts already touched
    within THIS document's tutoring conversation - e.g.
    [{"name": "Conditional Probability", "mastery_score": 54, "confidence":
    "moderate"}, ...], most-recently-practiced first. Used to give Ada
    per-turn calibration context (don't re-explain something already
    mastered, don't assume a weak prerequisite is understood).

    Deliberately scoped to THIS document, not the student's entire
    history - TutorConversation itself is per (user, document), so this
    matches that boundary. A longer-term, cross-document profile is a
    later Ada phase (see LONG-TERM ACADEMIC MEMORY in the Ada design
    doc), not built here.
    """
    concept_ids = [
        row[0] for row in
        db.session.query(LearningEvent.concept_id)
        .filter(
            LearningEvent.user_id == user_id,
            LearningEvent.document_content_id == document_content_id,
        )
        .distinct()
        .all()
    ]
    if not concept_ids:
        return []

    rows = (
        StudentConceptMastery.query
        .filter(
            StudentConceptMastery.user_id == user_id,
            StudentConceptMastery.concept_id.in_(concept_ids),
        )
        .order_by(StudentConceptMastery.last_practiced_at.desc())
        .limit(limit)
        .all()
    )

    snapshot = []
    for row in rows:
        concept = db.session.get(LearningConcept, row.concept_id)
        if not concept:
            continue
        snapshot.append({
            "name": concept.name,
            "mastery_score": row.mastery_score,
            "confidence": row.confidence,
        })
    return snapshot


def get_current_conversation_concept_id(user_id, document_content_id):
    """
    Returns the concept_id of the most recently detected concept in
    this student's tutoring conversation for this document, or None if
    no concept has been detected yet. Used to decide whether a
    diagnostic check-in is warranted before generating this turn's
    reply - see should_diagnose() below. Deliberately scoped to this
    document only, same boundary as get_student_mastery_snapshot().
    """
    latest_event = (
        LearningEvent.query
        .filter_by(user_id=user_id, document_content_id=document_content_id)
        .order_by(LearningEvent.created_at.desc())
        .first()
    )
    return latest_event.concept_id if latest_event else None


def should_diagnose(user_id, concept_id):
    """
    Ada Phase 2: decides whether Ada should check the student's grasp
    of a prerequisite before continuing to teach `concept_id`. Fires
    only when there's a real gap signal, not on every turn - see the
    Ada design doc's "diagnosis should be used when useful, not
    mandatory" guidance (section 6).

    Returns the prerequisite LearningConcept row to diagnose against,
    or None if no diagnostic is warranted. Deliberately checks at most
    one prerequisite per call - asking about several at once would
    feel like an interrogation, not a natural check-in - so if a
    concept has multiple prerequisites, this returns whichever one has
    the lowest (or entirely missing) mastery for this student.
    """
    target_mastery = StudentConceptMastery.query.filter_by(
        user_id=user_id, concept_id=concept_id
    ).first()
    # A student with solid, well-evidenced mastery of the target
    # concept itself doesn't need a prerequisite check gating further
    # teaching - diagnosis is for shoring up shaky ground, not
    # interrupting a student who's already doing fine.
    if target_mastery and target_mastery.confidence == "high":
        return None

    prereq_edges = ConceptPrerequisite.query.filter_by(concept_id=concept_id).all()
    if not prereq_edges:
        return None

    weakest_concept = None
    weakest_score = None
    for edge in prereq_edges:
        prereq_mastery = StudentConceptMastery.query.filter_by(
            user_id=user_id, concept_id=edge.prerequisite_concept_id
        ).first()
        # No evidence at all reads as "unknown", scored below any real
        # measured score - never assume an unpracticed prerequisite is
        # fine just because nothing negative has been observed yet.
        score = prereq_mastery.mastery_score if prereq_mastery else -1
        if score >= 40:
            continue
        if weakest_score is None or score < weakest_score:
            weakest_score = score
            weakest_concept = db.session.get(LearningConcept, edge.prerequisite_concept_id)

    return weakest_concept


# Days since last practiced before a well-established concept counts
# as "stale" and worth a spaced-review nudge. Deliberately a flat
# constant for now, not per-concept/per-student - same "simple
# algorithm, upgradeable later" tradeoff as _mastery_gain_for_exposure()
# above (see section 19, MASTERy MODEL, and section 20, RETENTION AND
# SPACED LEARNING, in the Ada design doc).
REVIEW_STALENESS_DAYS = 7


def get_concepts_due_for_review(user_id, document_content_id, limit=3):
    """
    Returns concepts this student has previously learned (within THIS
    document's tutoring conversation - same per-document scoping as
    get_student_mastery_snapshot(), for the same reason: a longer-term
    cross-document profile is a later Ada phase, not built here) that
    are now stale enough to be worth a review nudge.

    "Due" means: genuinely learned (mastery_score >= 50, confidence
    moderate or high - a "low" confidence concept hasn't really been
    established yet, so recommending a review of it doesn't make sense;
    that's a job for normal teaching, not spaced review) AND not
    practiced in at least REVIEW_STALENESS_DAYS days.

    Returns a list of dicts (most-overdue first), each:
    {"name": str, "mastery_score": int, "days_since_practiced": int}.
    Empty list if nothing is due - callers should treat that as "don't
    mention review", never fabricate a reason to nudge.
    """
    concept_ids = [
        row[0] for row in
        db.session.query(LearningEvent.concept_id)
        .filter(
            LearningEvent.user_id == user_id,
            LearningEvent.document_content_id == document_content_id,
        )
        .distinct()
        .all()
    ]
    if not concept_ids:
        return []

    cutoff = datetime.utcnow() - timedelta(days=REVIEW_STALENESS_DAYS)
    rows = (
        StudentConceptMastery.query
        .filter(
            StudentConceptMastery.user_id == user_id,
            StudentConceptMastery.concept_id.in_(concept_ids),
            StudentConceptMastery.mastery_score >= 50,
            StudentConceptMastery.confidence.in_(("moderate", "high")),
            StudentConceptMastery.last_practiced_at.isnot(None),
            StudentConceptMastery.last_practiced_at <= cutoff,
        )
        .order_by(StudentConceptMastery.last_practiced_at.asc())
        .limit(limit)
        .all()
    )

    now = datetime.utcnow()
    due = []
    for row in rows:
        concept = db.session.get(LearningConcept, row.concept_id)
        if not concept:
            continue
        due.append({
            "name": concept.name,
            "mastery_score": row.mastery_score,
            "days_since_practiced": (now - row.last_practiced_at).days,
        })
    return due
