"""Document storage, generated study material, and tutor ORM models."""

import re
from datetime import datetime

from sqlalchemy import text

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
