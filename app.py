import os
import re
import base64
import secrets
import hmac
import hashlib
import json
import requests
import sentry_sdk
import fitz  # PyMuPDF - used to rasterize + watermark view-only Q&A pages
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, session, Response, send_from_directory, redirect
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_, and_, text
from threading import Lock, Thread
from sqlalchemy.exc import IntegrityError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import ai_service
import document_pipeline
import podcast_audio
from pywebpush import webpush, WebPushException
from urllib.parse import urlencode

load_dotenv()

sentry_dsn = os.environ.get("SENTRY_DSN")
anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY")
PAYSTACK_PUBLIC_KEY = os.environ.get("PAYSTACK_PUBLIC_KEY")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=0,  # Error monitoring only, no performance tracing
        send_default_pii=False,  # Skip sending user IPs/headers by default
    )

app = Flask(__name__, static_folder="frontend/dist", static_url_path="")
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per hour"])
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")


@app.after_request
def add_security_headers(response):
    # Auth/reset/verification URLs can contain one-time tokens. Prevent
    # those query strings from becoming Referer data on subsequent requests.
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

db = SQLAlchemy(app)
from usage_billing import register_usage_billing
register_usage_billing(app, db)
from ai_economics import register_ai_economics
register_ai_economics(app, db)
from organisation_billing import register_organisation_billing
register_organisation_billing(app, db)
from discovery_billing import register_discovery
register_discovery(app, db)

# Offline chat retries need a server-side idempotency record. The client keeps
# one stable UUID for a queued send; this table lets a retry return the
# already-created message instead of creating a second message when the first
# response was lost during reconnect.
_CHAT_IDEMPOTENCY_SCHEMA_READY = False
_CHAT_IDEMPOTENCY_SCHEMA_LOCK = Lock()


def _ensure_chat_idempotency_schema():
    global _CHAT_IDEMPOTENCY_SCHEMA_READY
    if _CHAT_IDEMPOTENCY_SCHEMA_READY:
        return True
    with _CHAT_IDEMPOTENCY_SCHEMA_LOCK:
        if _CHAT_IDEMPOTENCY_SCHEMA_READY:
            return True
        try:
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_message_idempotency (
                    conversation_id INTEGER NOT NULL,
                    sender_id INTEGER NOT NULL,
                    client_message_id VARCHAR(128) NOT NULL,
                    message_id INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (conversation_id, sender_id, client_message_id)
                )
            """))
            db.session.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS ix_chat_message_idempotency_message
                ON chat_message_idempotency (message_id)
            """))
            db.session.commit()
            _CHAT_IDEMPOTENCY_SCHEMA_READY = True
            return True
        except Exception:
            db.session.rollback()
            app.logger.exception("Could not initialize chat idempotency schema")
            return False

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PHONE_NUMBER_REGEX = re.compile(r"^\+?\d{9,15}$")
BASE_URL = os.environ.get("BASE_URL", "https://prepza-sf60.onrender.com")

COMMON_WEAK_PASSWORDS = {
    "password", "password1", "password12", "password123",
    "12345678", "123456789", "1234567890", "qwerty123", "qwertyuiop",
    "letmein123", "iloveyou1", "iloveyou123", "admin1234", "welcome123",
    "abc123456", "11111111", "00000000", "changeme1", "monkey123",
    "football1", "sunshine1", "princess1", "dragon123",
}


def password_strength_error(password):
    """
    Lightweight strength check (no external dependency). Returns an
    error message string if the password is too weak, or None if it's
    acceptable. Caller is expected to have already checked length.
    """
    if password.lower() in COMMON_WEAK_PASSWORDS:
        return "That password is too common - please choose something more unique."
    if not re.search(r"[a-z]", password):
        return "Password must include at least one lowercase letter."
    if not re.search(r"[A-Z]", password):
        return "Password must include at least one uppercase letter."
    if not re.search(r"\d", password):
        return "Password must include at least one number."
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Password must include at least one symbol (e.g. ! @ # $ %)."
    return None


@app.after_request
def set_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"

    # Long-lived caching for static assets (images, CSS, JS) so repeat
    # visitors don't re-download unchanged files on every page load.
    # Unrelated to the "no-store" header on the watermarked PDF viewer route
    # below - that one intentionally stays uncached since it's private,
    # paid content.
    if request.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"

    return response


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    year = db.Column(db.Integer, nullable=True)
    semester = db.Column(db.Integer, nullable=True)
    display_name = db.Column(db.String(50), nullable=True)
    bio = db.Column(db.String(160), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    # Private field only - never exposed on public/other-user profile
    # endpoints, not searchable. See patch_add_phone_number.py.
    email_verified = db.Column(db.Boolean, default=False)
    profile_visibility = db.Column(db.String(10), nullable=False, default="public")
    # public | private
    who_can_message = db.Column(db.String(10), nullable=False, default="everyone")
    # everyone | followers
    who_can_follow = db.Column(db.String(20), nullable=False, default="everyone")
    read_receipts_enabled = db.Column(db.Boolean, nullable=False, default=True)
    # everyone | approval_required
    verification_token = db.Column(db.String(64), nullable=True)
    reset_token = db.Column(db.String(64), nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    university_id = db.Column(db.Integer, db.ForeignKey("university.id"), nullable=True)
    program_id = db.Column(db.Integer, db.ForeignKey("program.id"), nullable=True)
    requested_program_name = db.Column(db.String(150), nullable=True)


    created_at = db.Column(db.DateTime, nullable=True)
    signup_source = db.Column(db.String(100), nullable=True)
    is_suspended = db.Column(db.Boolean, nullable=False, default=False)
    last_active_at = db.Column(db.DateTime, nullable=True)
    # Bumped whenever this user's password changes (or an admin needs to
    # force-logout them). Every request compares this to the number
    # stamped in the session cookie at login time - a mismatch means the
    # cookie is stale and gets cleared. See enforce_session_version().
    session_version = db.Column(db.Integer, nullable=False, default=0)
    # Updated (throttled, see track_last_active()) on any authenticated
    # request - login, browsing, chatting, anything - not just specific
    # study actions. That's a different, broader signal than
    # StudyActivityLog, which only covers document/quiz/flashcard study.
class University(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    short_code = db.Column(db.String(20), nullable=False, unique=True)
    country = db.Column(db.String(80), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Program(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    university_id = db.Column(db.Integer, db.ForeignKey("university.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    degree_level = db.Column(db.String(50), nullable=True)
    discipline_category = db.Column(db.String(80), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Unit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    university_id = db.Column(db.Integer, db.ForeignKey("university.id"), nullable=True)


class UnitProgram(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey("unit.id"), nullable=False)
    program_id = db.Column(db.Integer, db.ForeignKey("program.id"), nullable=False)
    __table_args__ = (
        db.UniqueConstraint("unit_id", "program_id", name="uq_unit_program"),
    )


class ContentItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey("unit.id"), nullable=False)
    content_type = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    file_url = db.Column(db.String(500), nullable=True)
    paper_year = db.Column(db.Integer, nullable=True)
    is_downloadable = db.Column(db.Boolean, default=True)
    price = db.Column(db.Integer, default=0)


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    content_item_id = db.Column(db.Integer, db.ForeignKey("content_item.id"), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    amount = db.Column(db.Integer, nullable=False)
    # Unused since the Daraja -> Pesapal swap (Chunk 8). Left in place
    # rather than dropped, per the no-destructive-migrations convention.
    checkout_request_id = db.Column(db.String(100), unique=True, nullable=True)
    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ---- Paystack (Chunk 8, migrated from Pesapal) ----
    provider = db.Column(db.String(20), nullable=False, default="paystack")
    reference = db.Column(db.String(50), unique=True, nullable=True)
    # Reference WE generate and pass to Paystack on initialize - this is
    # what Paystack's webhook/callback hand back to us, and what
    # /transaction/verify/<reference> is keyed on. Renamed from
    # merchant_reference (Pesapal-specific naming).
    provider_reference = db.Column(db.String(100), unique=True, nullable=True)
    # Paystack's own internal transaction id (the "id" field from a
    # verify-transaction response), stored for support/audit lookups in
    # the Paystack dashboard. Renamed from order_tracking_id.

    # 'content' (one-off document/item purchase) or 'subscription' (plan purchase)
    payment_type = db.Column(db.String(20), nullable=False, default="content")
    plan = db.Column(db.String(20), nullable=True)  # 'plus' | 'pro' - subscription only
    subscription_expires_at = db.Column(db.DateTime, nullable=True)  # subscription only
    # Organisation promotion billing. Nullable so existing student/content/subscription
    # payments remain unchanged.
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisation.id"), nullable=True)
    opportunity_promotion_id = db.Column(db.Integer, db.ForeignKey("opportunity_promotion.id"), nullable=True)


class SystemSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False, default="")


class ViewProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    content_item_id = db.Column(db.Integer, db.ForeignKey("content_item.id"), nullable=False)
    page_num = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("user_id", "content_item_id", name="uq_view_progress_user_item"),
    )


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
    generator = {
        "summary": ai_service.generate_document_summary,
        "quiz": ai_service.generate_document_quiz,
        "flashcards": ai_service.generate_document_flashcards,
        "podcast": ai_service.generate_document_podcast_script,
        "mind_map": ai_service.generate_document_mindmap,
    }[feature]
    return generator(
        document_content_id=content.id,
        triggering_user_id=user_id,
        plan_tier=get_ai_plan_tier(user_id),
        parameters=parameters,
    )


def _start_async_material_generation(document_content_id, user_id, feature, parameters):
    """Create a user-visible generation job and run the existing generator off-request."""
    job = AiJob(
        document_content_id=document_content_id,
        user_id=user_id,
        feature=feature,
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
                generator = {
                    "summary": ai_service.generate_document_summary,
                    "quiz": ai_service.generate_document_quiz,
                    "flashcards": ai_service.generate_document_flashcards,
                    "podcast": ai_service.generate_document_podcast_script,
                    "mind_map": ai_service.generate_document_mindmap,
                }[feature]
                local_job.progress_percent = 20
                local_job.progress_stage = "generating with AI"
                db.session.commit()
                result = generator(
                    document_content_id=document_content_id,
                    triggering_user_id=user_id,
                    plan_tier=get_ai_plan_tier(user_id),
                    parameters=parameters,
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
    # Notification row to finalize when a background generation completes.
    notification_id = db.Column(db.Integer, db.ForeignKey("notification.id"), nullable=True)
    # Anthropic Message Batch id, when this job's AI call(s) went through
    # the Batch API instead of a synchronous call - lets an admin look up
    # the batch directly in the Anthropic Console if a job seems stuck.


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
    unit_id = db.Column(db.Integer, db.ForeignKey("unit.id"), nullable=True)
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
    unit_id = db.Column(db.Integer, db.ForeignKey("unit.id"), nullable=True)
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


STUDY_TIME_FEATURES = {"reading", "podcast", "quiz", "flashcards", "tutor_chat", "mindmap"}


class StudyTimeLog(db.Model):
    """
    Minutes actually spent studying, one row per user per calendar
    day PER FEATURE (reading/podcast/quiz/flashcards/tutor_chat).
    Deliberately a SEPARATE table from StudyActivityLog - see the
    design note at the top of the patch script that added this.
    study_time_seconds accumulates across every heartbeat that day
    for that feature; last_heartbeat_at is used server-side to
    compute each new heartbeat's elapsed time, capped per call, so a
    backgrounded tab can never retroactively credit a large gap. The
    8h/day anti-gaming ceiling (MAX_STUDY_TIME_SECONDS_PER_DAY) is
    enforced across ALL of a user's feature rows for that day
    combined, not per-feature - see record_study_time_heartbeat().
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


class Conversation(db.Model):
    """
    A 1:1 or group chat thread (Chunk 6). Message delivery is
    polling-based for MVP - clients re-fetch /chats/<id>/messages on an
    interval rather than holding a persistent connection, since the
    current Render/gunicorn setup runs sync workers with no websocket
    infra. Direct-message conversations always have exactly 2
    ConversationParticipant rows and name=None; group conversations set
    is_group=True and require a name.
    """
    id = db.Column(db.Integer, primary_key=True)
    is_group = db.Column(db.Boolean, nullable=False, default=False)
    name = db.Column(db.String(100), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # updated_at is bumped on every new message so /chats can sort by
    # most recent activity without a join + max(created_at) per row.
    status = db.Column(db.String(20), nullable=False, default="accepted")
    # E2EE state is nullable only at the application-compatibility level;
    # the database migration defaults these columns to legacy/0. Keeping
    # them on the ORM model makes fresh chat tables match the live schema.
    e2ee_mode = db.Column(db.String(20), nullable=False, default="legacy")
    key_epoch = db.Column(db.Integer, nullable=False, default=0)
    # accepted | pending. Only meaningful for 1:1 (is_group=False)
    # conversations created against a who_can_message="followers"
    # target by a non-follower - Instagram-style message requests.
    # The requester (created_by) sees a pending conversation in their
    # normal /chats list immediately; the other participant only sees
    # it in GET /message-requests until they accept (-> "accepted",
    # merges into their normal list) or decline (row is deleted
    # outright, letting the requester try again with a clean slate).
    # Groups and normal chats are always "accepted".


class ConversationParticipant(db.Model):
    """
    One user's membership in a Conversation. last_read_at drives the
    unread badge on /chats: unread_count = messages in this
    conversation created after last_read_at, excluding the viewer's own
    messages. left_at soft-marks a group departure; 1:1 conversations
    are never left.
    """
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="member")
    # member | admin (group only - reserved for later moderation controls)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_read_at = db.Column(db.DateTime, nullable=True)
    left_at = db.Column(db.DateTime, nullable=True)
    muted = db.Column(db.Boolean, nullable=False, default=False)
    # Per-participant notification mute for this conversation - local to
    # each participant row, so muting a group chat only silences it for
    # you, not for other members. Purely a notification-suppression flag;
    # does not affect message visibility, read receipts, or unread counts.
    __table_args__ = (
        db.UniqueConstraint("conversation_id", "user_id", name="uq_participant_conversation_user"),
    )


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.Text, nullable=True)
    # E2EE (Chats only, 1:1 chunk): body is AES-GCM ciphertext,
    # base64-encoded, client-encrypted before it ever reaches this
    # server. Widened from String(3000) to Text because ciphertext
    # + base64 encoding overhead can exceed the old plaintext-sized
    # cap - CHAT_MESSAGE_CIPHERTEXT_MAX enforces the real ceiling at
    # the application layer instead. Still nullable so an
    # attachment-only message (no caption) is valid - see
    # send_message()'s "must include text or an attachment" check.
    nonce = db.Column(db.String(64), nullable=True)
    # AES-GCM IV used to encrypt body, base64 - required whenever
    # body is set, meaningless (and left null) for attachment-only
    # messages. The server never has the key to decrypt this; it
    # only stores and returns nonce+body together so the recipient's
    # own client can.
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    edited_at = db.Column(db.DateTime, nullable=True)
    # E2EE group messages/edits are bound to the exact group key epoch used
    # for encryption. Nullable for legacy/direct messages.
    e2ee_key_epoch = db.Column(db.Integer, nullable=False, default=0)


class MessageAttachment(db.Model):
    """
    One file attached to (or in the process of being attached to) a chat
    message. Two-phase upload, same pattern as Document/DocumentContent:
    a row is created here first (status='uploading', message_id=None -
    not yet linked to any sent message), the client PUTs bytes directly
    to Supabase Storage via the returned signed URL, then confirms via
    POST /chats/<id>/attachments/<id>/uploaded. Only once the message is
    actually sent (POST /chats/<id>/messages with attachment_id) does
    message_id get set - an initiated-but-abandoned upload just stays
    orphaned (message_id NULL) rather than blocking anything; no cleanup
    sweep for those yet, same "no cleanup job yet" tradeoff as other
    unreferenced-storage notes elsewhere in this file.
    """
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey("message.id", ondelete="CASCADE"), nullable=True)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    storage_path = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(20), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_size_bytes = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="uploading")
    # uploading -> ready | failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    cached_view_url = db.Column(db.String(1000), nullable=True)
    cached_view_url_expires_at = db.Column(db.DateTime, nullable=True)
    # Chat redesign Phase 1a: see get_cached_chat_attachment_url() below.
    # Populated lazily on first serialization, refreshed only once
    # close to actual expiry - keeps the URL returned to the client
    # STABLE across repeated polls, so the browser can actually cache
    # the image instead of re-downloading it every ~4s poll cycle.


class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.String(1000), nullable=True)
    privacy = db.Column(db.String(20), nullable=False, default="public")
    # public | private | course_only
    university_id = db.Column(db.Integer, db.ForeignKey("university.id"), nullable=True)
    program_id = db.Column(db.Integer, db.ForeignKey("program.id"), nullable=True)
    unit_id = db.Column(db.Integer, db.ForeignKey("unit.id"), nullable=True)
    year = db.Column(db.Integer, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    member_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Admin kill-switch (Chunk 10) - deactivating a group hides it from
    # browse/join and blocks new posts/comments/joins for existing
    # members too (see _get_group_visible() and the is_active checks in
    # create_group_post/create_group_post_comment/join_group below).
    # Same reactive pattern as Organisation.is_active elsewhere in this
    # file, but stricter: Organisation only hides new opportunities,
    # this also blocks ongoing member activity.


class GroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("group.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="member")
    # admin | member
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("group_id", "user_id", name="uq_group_member_group_user"),
    )


class GroupPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("group.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_type = db.Column(db.String(20), nullable=False, default="post")
    # post | question - Posts tab vs Questions tab in GroupDetailScreen
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_removed = db.Column(db.Boolean, nullable=False, default=False)


class GroupPostComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_post_id = db.Column(db.Integer, db.ForeignKey("group_post.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_removed = db.Column(db.Boolean, nullable=False, default=False)
    # Used for both Posts-tab comments and Questions-tab replies - the
    # frontend's shared CommentsScreen doesn't distinguish them either.
    marked_helpful = db.Column(db.Boolean, nullable=False, default=False)
    # Set once by the original post's author via /helpful below - awards
    # XP_COMMUNITY_HELPFUL_REPLY to the comment's author (Chunk 7).


class GroupPostLike(db.Model):
    """Heart/like on a Posts-tab GroupPost."""
    id = db.Column(db.Integer, primary_key=True)
    group_post_id = db.Column(db.Integer, db.ForeignKey("group_post.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("group_post_id", "user_id", name="uq_group_post_like_post_user"),
    )


class GroupQuestionVote(db.Model):
    """Upvote on a Questions-tab GroupPost. Kept separate from
    GroupPostLike since a post can only be one type (post XOR question)
    but the two interactions have different semantics and copy."""
    id = db.Column(db.Integer, primary_key=True)
    group_post_id = db.Column(db.Integer, db.ForeignKey("group_post.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("group_post_id", "user_id", name="uq_group_question_vote_post_user"),
    )


class GroupFile(db.Model):
    """Shares an existing personal Document into a group's Files tab -
    does not duplicate storage, just links to the student's own
    Document row (must already be status=ready)."""
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("group.id", ondelete="CASCADE"), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey("document.id"), nullable=False)
    shared_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("group_id", "document_id", name="uq_group_file_group_document"),
    )


class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("follower_id", "followed_id", name="uq_follow_follower_followed"),
    )


PROFILE_VISIBILITY_VALUES = {"public", "private"}
WHO_CAN_MESSAGE_VALUES = {"everyone", "followers"}
WHO_CAN_FOLLOW_VALUES = {"everyone", "approval_required"}


class FollowRequest(db.Model):
    """
    A pending/accepted/declined follow request, used only when the
    target has who_can_follow='approval_required' (private-account-
    style gating, see PATCH /profile). Unique on (requester, target)
    so a re-request after a decline updates the same row back to
    pending rather than creating duplicates - same reapply pattern
    as Ambassador elsewhere in this file. Accepting a request creates
    a real Follow row; the FollowRequest row itself is not the
    source of truth for "is following" once accepted.
    """
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    target_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(10), nullable=False, default="pending")
    # pending -> accepted | declined
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (
        db.UniqueConstraint("requester_id", "target_id", name="uq_follow_request_requester_target"),
    )


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    type = db.Column(db.String(40), nullable=False)
    # e.g. group_post, group_comment, group_join_request, new_follower,
    # forum_ai_reply, study_reminder, opportunity, achievement, announcement
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.String(500), nullable=True)
    related_type = db.Column(db.String(40), nullable=True)
    # e.g. "group", "group_post", "user", "forum_post" - paired with
    # related_id so the frontend notification tap-target can be resolved
    # without a different table shape per notification type.
    related_id = db.Column(db.Integer, nullable=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class NotificationPreference(db.Model):
    """
    Per-user, per-category notification opt-out (Settings > Notifications).
    A missing row means "everything on" (see get_or_create_notification_prefs) -
    rows are created lazily on first read/write, not at signup. Only
    categories with an actual notification-producing code path are
    represented here - "push" (browser subscription on/off) is handled
    entirely by PushSubscription and isn't duplicated here.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    community_enabled = db.Column(db.Boolean, nullable=False, default=True)
    # gates: new_follower, group_like, group_vote, group_comment, group_promoted
    messages_enabled = db.Column(db.Boolean, nullable=False, default=True)
    # gates: chat DM push (see send_message())
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Announcement(db.Model):
    """
    A record of one admin broadcast (Communications tab). Sending an
    announcement fans out a Notification(type="announcement") row to
    every eligible user at send time - reach is snapshotted here rather
    than recomputed later, since the user population (and who was
    suspended at send time) will keep changing after the fact.
    """
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.String(500), nullable=False)
    sent_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    reach = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------- Moderation (Chunk 10) ----------

CONTENT_REPORT_TARGET_TYPES = (
    "group_post", "group_post_comment", "user",
)
CONTENT_REPORT_REASONS = {
    # reason -> auto-assigned priority. Deliberately a fixed mapping
    # rather than an admin-editable one for MVP, same tradeoff as the
    # hardcoded XP_* amounts elsewhere in this file.
    "academic_dishonesty": "high",
    "harassment": "high",
    "offensive_content": "medium",
    "misinformation": "medium",
    "spam_scam": "medium",
    "duplicate": "low",
    "bot_activity": "low",
    "other": "low",
}
CONTENT_REPORT_STATUSES = ("pending", "dismissed", "actioned")
CONTENT_REPORT_ACTIONS = ("dismissed", "removed", "warned")


class ContentReport(db.Model):
    """
    A student report against a piece of community content (forum
    posts/replies, group posts/comments) or against a user directly.
    Deliberately separate from LibraryReport, which already covers
    document/library-item reports with its own queue - this table
    fills the gap for everything else, which previously had no
    reporting mechanism at all.
    """
    id = db.Column(db.Integer, primary_key=True)
    target_type = db.Column(db.String(30), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    reporter_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    # nullable to leave room for future automated/system-flagged reports
    reason = db.Column(db.String(40), nullable=False)
    details = db.Column(db.String(500), nullable=True)
    priority = db.Column(db.String(10), nullable=False)
    # high | medium | low - derived from `reason` at creation time
    status = db.Column(db.String(20), nullable=False, default="pending")
    # pending -> dismissed | actioned
    action_taken = db.Column(db.String(20), nullable=True)
    # set alongside status='actioned': 'removed' | 'warned'
    admin_notes = db.Column(db.String(500), nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class UserWarning(db.Model):
    """
    A formal warning issued to a student, always paired with a
    Notification(type='moderation_warning') so the student actually
    sees it - not just an internal admin note. `message` states what
    they did wrong, `consequence` states what happens as a result /
    next time, both admin-authored per warning rather than templated,
    since the punishment should match the specific violation.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    issued_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    content_report_id = db.Column(db.Integer, db.ForeignKey("content_report.id"), nullable=True)
    reason = db.Column(db.String(40), nullable=False)
    # same vocabulary as ContentReport.reason, so warnings and reports
    # can be filtered/grouped consistently
    message = db.Column(db.String(500), nullable=False)
    consequence = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------- Opportunities + Organisation portal ----------

ORGANISATION_VERIFICATION_STATUSES = ("pending", "verified", "rejected")


class Organisation(db.Model):
    """
    An employer/institution/sponsor account that can submit and manage
    its own Opportunities. Verification is admin-gated - an unverified
    organisation can still be created and staffed (OrganisationMember),
    but its opportunities cannot be published until the org itself is
    verified (enforced in the routes patch, not here).
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.String(1000), nullable=True)
    website = db.Column(db.String(500), nullable=True)
    logo_url = db.Column(db.String(500), nullable=True)
    contact_email = db.Column(db.String(120), nullable=False)
    contact_phone = db.Column(db.String(20), nullable=True)
    verification_status = db.Column(db.String(20), nullable=False, default="pending")
    # pending -> verified | rejected
    verification_notes = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Admin kill-switch - deactivating an org hides all its opportunities
    # without deleting anything, same soft-disable pattern as
    # University.is_active / Program.is_active elsewhere in this file.
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OrganisationMember(db.Model):
    """
    A User's membership/role within an Organisation - same shape as
    GroupMember. 'owner' is the org's primary account holder (set on
    creation, cannot be removed without transferring ownership first,
    mirrored after the sole-admin protections on GroupMember); 'manager'
    can submit/edit opportunities but not manage other staff or billing.
    """
    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisation.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="manager")
    # owner | manager
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("organisation_id", "user_id", name="uq_org_member_org_user"),
    )


OPPORTUNITY_TYPES = ("job", "internship", "scholarship", "competition", "volunteering", "event", "other")
OPPORTUNITY_STATUSES = (
    "draft", "pending_review", "approved", "rejected",
    "published", "expired", "archived", "removed",
)


class Opportunity(db.Model):
    """
    Full lifecycle: draft -> pending_review -> approved/rejected ->
    published -> expired -> archived/removed. Expiry is computed
    server-side off expiry_date (see is_opportunity_expired() /
    the expiry sweep in the routes patch) - never trust a frontend
    clock for this, per the MVP spec.
    """
    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisation.id", ondelete="CASCADE"), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    # the OrganisationMember (by user_id) who submitted this - kept even
    # if that member later leaves the org, same pattern as
    # LibraryPublication.user_id.
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    opportunity_type = db.Column(db.String(20), nullable=False)
    location = db.Column(db.String(200), nullable=True)
    is_remote = db.Column(db.Boolean, nullable=False, default=False)
    application_url = db.Column(db.String(500), nullable=True)
    application_instructions = db.Column(db.Text, nullable=True)
    application_deadline = db.Column(db.DateTime, nullable=False)
    expiry_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="draft")
    rejection_reason = db.Column(db.String(500), nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    published_at = db.Column(db.DateTime, nullable=True)
    view_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


OPPORTUNITY_PROMOTION_TYPES = ("standard", "featured", "sponsored")
OPPORTUNITY_PROMOTION_APPROVAL_STATUSES = ("pending", "approved", "rejected")
OPPORTUNITY_PROMOTION_PAYMENT_STATUSES = ("unpaid", "pending", "paid", "refunded")


class OpportunityPromotion(db.Model):
    """
    One promotion campaign for an Opportunity. Deliberately separate
    from Opportunity itself (rather than fields on it) since an org can
    run more than one promotion over an opportunity's lifetime, each
    with its own window/price/approval. price is a snapshot captured at
    creation time from admin-configurable SystemSetting pricing (same
    pattern as get_content_prices()) - NOT hard-coded here. Actual
    payment collection/webhook wiring belongs to the Payments chunk;
    payment_status exists now so that schema is ready for it.
    """
    id = db.Column(db.Integer, primary_key=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("opportunity.id", ondelete="CASCADE"), nullable=False)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisation.id"), nullable=False)
    # denormalized for admin filtering, per the MVP spec's stored-fields list
    promotion_type = db.Column(db.String(20), nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    price = db.Column(db.Integer, nullable=False, default=0)
    payment_status = db.Column(db.String(20), nullable=False, default="unpaid")
    approval_status = db.Column(db.String(20), nullable=False, default="pending")
    reviewed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Ambassador(db.Model):
    """
    A user's enrollment in the referral/ambassador program (Chunk 9).
    One row per user - applying again after rejection just resets this
    same row back to 'pending' rather than creating duplicates, since
    referral_code needs to stay stable once anything has been shared
    publicly under it.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    referral_code = db.Column(db.String(20), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    # pending -> active | rejected ; active -> suspended -> active (admin can reinstate)
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Referral(db.Model):
    """
    One referred signup and its progress through the funnel:
    signed_up -> verified -> activated, with paying/commission tracked
    via first_payment_id rather than a status value (a referral can be
    "activated" for months before ever converting - those aren't
    mutually exclusive states). commission_rate_applied and
    commission_amount are snapshotted at conversion time so a later
    change to the tier thresholds/percentages in SystemSetting never
    rewrites history for referrals that already converted.
    """
    id = db.Column(db.Integer, primary_key=True)
    ambassador_id = db.Column(db.Integer, db.ForeignKey("ambassador.id"), nullable=False)
    referred_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    referral_code_used = db.Column(db.String(20), nullable=False)
    channel = db.Column(db.String(30), nullable=True)
    # optional ?via= tag captured at signup (e.g. "whatsapp", "instagram")

    status = db.Column(db.String(20), nullable=False, default="signed_up")
    # signed_up -> verified -> activated
    verified_at = db.Column(db.DateTime, nullable=True)
    activated_at = db.Column(db.DateTime, nullable=True)

    first_payment_id = db.Column(db.Integer, db.ForeignKey("payment.id"), unique=True, nullable=True)
    first_payment_at = db.Column(db.DateTime, nullable=True)
    commission_rate_applied = db.Column(db.Integer, nullable=True)  # whole percent, e.g. 15
    commission_amount = db.Column(db.Integer, nullable=True)  # KES, snapshotted
    unlock_at = db.Column(db.DateTime, nullable=True)
    # first_payment_at + the hold period in effect at conversion time -
    # commission becomes requestable once now() >= unlock_at.

    payout_id = db.Column(db.Integer, db.ForeignKey("ambassador_payout.id"), nullable=True)
    # set once bundled into a payout request; NULL means still available.

    voided_at = db.Column(db.DateTime, nullable=True)
    void_reason = db.Column(db.String(200), nullable=True)
    # set if the qualifying payment is later refunded - only allowed
    # while payout_id is still NULL (see admin_refund_payment).

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AmbassadorPayout(db.Model):
    """
    One payout request, bundling every currently-unlocked Referral
    commission for an ambassador at request time. amount is a snapshot
    of the sum at request time - Referral rows keep their own
    commission_amount as the source of truth, this is just the total
    actually requested/approved/paid.
    """
    id = db.Column(db.Integer, primary_key=True)
    ambassador_id = db.Column(db.Integer, db.ForeignKey("ambassador.id"), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    # pending -> approved -> paid ; pending -> rejected (bundled referrals released)
    payout_destination = db.Column(db.String(20), nullable=False)
    # phone number for Paystack mobile money transfer
    recipient_first_name = db.Column(db.String(100), nullable=False)
    recipient_last_name = db.Column(db.String(100), nullable=False)
    # Paystack's transfer recipient payload requires a real first/last
    # name, not just a phone number - collected explicitly at request
    # time rather than split from User.display_name, since that field
    # is an optional nickname and unreliable for an actual money transfer.
    paystack_recipient_code = db.Column(db.String(100), nullable=True)
    # Paystack recipient_code from POST /transferrecipient - created
    # once per payout on first approval attempt, then reused. Paystack
    # requires a recipient to exist before a transfer can be initiated,
    # unlike Kasapay's single-call B2C.
    paystack_transfer_code = db.Column(db.String(100), nullable=True)
    # Our own reference string passed to POST /transfer - this is what
    # GET /transfer/verify/<reference> and the transfer.* webhook events
    # are keyed on. Named to mirror Payment.reference/provider_reference
    # naming from the checkout migration.
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(500), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)


# ---------- Student orders / exact fulfillment ----------
from student_orders import register_student_orders

_student_order_helpers = register_student_orders(app, db, Payment, ContentItem, User, require_csrf)


# ---------- Paystack (Chunk 8, migrated from Pesapal) ----------
# Docs: paystack.com/docs/payments/accept-payments /
# paystack.com/docs/api/transaction. PAYSTACK_SECRET_KEY's own prefix
# (sk_test_ vs sk_live_) determines sandbox vs live - unlike Pesapal,
# Paystack has no separate base URL per environment.
PAYSTACK_BASE_URL = "https://api.paystack.co"
SUBSCRIPTION_PLAN_DURATIONS_MONTHS = {"plus": 1, "pro": 1}

def _add_subscription_month(value):
    import calendar
    year, month = value.year, value.month
    if month == 12:
        year, month = year + 1, 1
    else:
        month += 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def paystack_request(method, path, **kwargs):
    if not PAYSTACK_SECRET_KEY:
        raise RuntimeError("PAYSTACK_SECRET_KEY is not configured")
    headers = kwargs.pop("headers", {})
    headers.setdefault("Accept", "application/json")
    headers.setdefault("Content-Type", "application/json")
    headers["Authorization"] = f"Bearer {PAYSTACK_SECRET_KEY}"
    response = requests.request(
        method, f"{PAYSTACK_BASE_URL}{path}", headers=headers, timeout=20, **kwargs
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("status"):
        raise RuntimeError(f"Paystack request failed: {data.get('message') or data}")
    return data


def create_paystack_transaction(reference, amount, description, user, paystack_plan_code=None):
    """
    Initializes a Paystack transaction. amount is in whole KES (same unit
    the rest of this file uses) - Paystack expects the lowest currency
    unit, so it's multiplied by 100 here. Returns (provider_reference,
    authorization_url) - provider_reference is Paystack's own transaction
    id (from the initialize response's "reference" field, which Paystack
    generates unless overridden; we pass our own `reference` as the
    canonical merchant-side identifier and get it back unchanged on
    webhook/callback).
    """
    payload = {
        "reference": reference,
        "amount": amount * 100,
        "currency": "KES",
        "email": user.email,
        "callback_url": f"{BASE_URL}/payment/paystack/callback",
        "metadata": {"description": description[:100]},
    }
    # Passing a Paystack plan code turns the first checkout into a recurring
    # subscription. Paystack's subscription plans are card-only in Kenya;
    # M-PESA/Airtel Money remain available for non-recurring checkout flows.
    if paystack_plan_code:
        plan_result = paystack_request("GET", f"/plan/{paystack_plan_code}")
        paystack_plan = plan_result.get("data") or {}
        expected_amount = int(amount) * 100
        actual_amount = int(paystack_plan.get("amount") or 0)
        interval = str(paystack_plan.get("interval") or "").lower()
        currency = str(paystack_plan.get("currency") or "").upper()
        if actual_amount != expected_amount or interval != "monthly" or currency != "KES":
            raise RuntimeError(
                "Paystack recurring plan does not exactly match Prepza's configured "
                "price, monthly interval, and KES currency"
            )
        payload["plan"] = paystack_plan_code
    data = paystack_request("POST", "/transaction/initialize", json=payload)
    tx = data.get("data") or {}
    authorization_url = tx.get("authorization_url")
    provider_reference = tx.get("reference") or reference
    if not authorization_url:
        raise RuntimeError(f"Paystack transaction initialization failed: {data}")
    return provider_reference, authorization_url


def get_plan_prices():
    """Return canonical monthly student subscription prices."""
    from ai_economics import get_plan
    plus = get_plan(db, "plus") or {}
    pro = get_plan(db, "pro") or {}
    return {"plus": int(plus.get("price_kes", 499)), "pro": int(pro.get("price_kes", 999))}


# ---------- Ambassador / Referral program (Chunk 9) ----------

AMBASSADOR_PAYOUT_HOLD_DAYS_DEFAULT = 21


def get_ambassador_settings():
    """
    Returns the admin-configurable ambassador program settings, sourced
    from SystemSetting rows - same pattern as get_content_prices() /
    get_plan_prices(). Tier percentages are whole-number percents
    (e.g. 15 means 15%), applied to a referral's first successful
    payment amount only - not to any payment after that.
    """
    keys = (
        "ambassador_program_enabled",
        "ambassador_tier1_pct", "ambassador_tier2_pct", "ambassador_tier3_pct",
        "ambassador_tier2_threshold", "ambassador_tier3_threshold",
        "ambassador_payout_hold_days", "ambassador_min_payout_kes",
    )
    settings = {
        s.key: s.value
        for s in SystemSetting.query.filter(SystemSetting.key.in_(keys)).all()
    }

    def parse_int(key, default):
        try:
            return int(settings.get(key) or default)
        except (TypeError, ValueError):
            return default

    return {
        "enabled": settings.get("ambassador_program_enabled", "true") == "true",
        "tier1_pct": parse_int("ambassador_tier1_pct", 10),
        "tier2_pct": parse_int("ambassador_tier2_pct", 15),
        "tier3_pct": parse_int("ambassador_tier3_pct", 20),
        "tier2_threshold": parse_int("ambassador_tier2_threshold", 5),
        "tier3_threshold": parse_int("ambassador_tier3_threshold", 20),
        "payout_hold_days": parse_int("ambassador_payout_hold_days", AMBASSADOR_PAYOUT_HOLD_DAYS_DEFAULT),
        "min_payout_kes": parse_int("ambassador_min_payout_kes", 500),
    }


def compute_ambassador_tier(prior_converted_count, settings=None):
    """
    Returns (tier_number, commission_pct) for an ambassador's NEXT
    conversion, based on how many of their referrals have already
    converted (voided ones don't count - see the query in the
    conversion hook, added in the next patch). Tier climbs
    automatically; no manual admin bump needed unless overriding via
    the SystemSetting thresholds above.
    """
    settings = settings or get_ambassador_settings()
    if prior_converted_count >= settings["tier3_threshold"]:
        return 3, settings["tier3_pct"]
    if prior_converted_count >= settings["tier2_threshold"]:
        return 2, settings["tier2_pct"]
    return 1, settings["tier1_pct"]


def generate_referral_code(display_name=None):
    """
    Generates a short, shareable referral code. Prefixed from the
    user's display name where possible (e.g. "JOHN4F2A") purely for
    memorability - uniqueness comes from the random suffix, not the
    prefix, so a caller hitting a collision just re-rolls rather than
    needing a different scheme.
    """
    prefix = "".join(ch for ch in (display_name or "").upper() if ch.isalnum())[:6] or "PREPZA"
    suffix = secrets.token_hex(3).upper()
    return f"{prefix}{suffix}"


def _sync_referral_progress(user):
    """
    Advances a referred user's Referral row through
    signed_up -> verified -> activated as their account state crosses
    each threshold. "Activated" requires BOTH a verified email AND a
    completed profile (university/year/semester all set) - whichever
    of the two happens second is what triggers the jump to activated,
    so this only ever moves the status forward, never backward, and
    it's safe to call redundantly (e.g. on every /profile PATCH).
    No-ops if this user was never referred.
    """
    referral = Referral.query.filter_by(referred_user_id=user.id).first()
    if not referral or referral.status == "activated":
        return

    now = datetime.utcnow()

    if user.email_verified and referral.status == "signed_up":
        referral.status = "verified"
        referral.verified_at = now

    profile_complete = bool(user.university_id and user.year and user.semester)
    if user.email_verified and profile_complete and referral.status in ("signed_up", "verified"):
        referral.status = "activated"
        referral.activated_at = now
        if not referral.verified_at:
            referral.verified_at = now


def _maybe_award_referral_commission(payment):
    """
    Called from sync_paystack_payment_status() right after a Payment's
    status is set to 'success' in memory, before that change is
    committed. Awards a ONE-TIME referral commission on a user's FIRST
    successful payment ever (content or subscription) - never on
    repeat payments. No-ops entirely if the user wasn't referred,
    already has an earlier successful payment on record, their
    referral was voided, or the program is disabled.

    A payment succeeding here also counts as "activated" even if the
    referred student somehow paid before finishing their profile -
    paying is a stronger engagement signal than the profile-completion
    check alone.
    """
    if not payment.user_id:
        return

    referral = Referral.query.filter_by(referred_user_id=payment.user_id).first()
    if not referral or referral.first_payment_id is not None or referral.voided_at is not None:
        return

    prior_success_count = Payment.query.filter(
        Payment.user_id == payment.user_id,
        Payment.status == "success",
        Payment.id != payment.id,
    ).count()
    if prior_success_count > 0:
        return  # not their first successful payment - no commission

    settings = get_ambassador_settings()
    if not settings["enabled"]:
        return

    prior_converted_count = Referral.query.filter(
        Referral.ambassador_id == referral.ambassador_id,
        Referral.first_payment_id.isnot(None),
        Referral.voided_at.is_(None),
    ).count()
    _tier, commission_pct = compute_ambassador_tier(prior_converted_count, settings)

    referral.first_payment_id = payment.id
    referral.first_payment_at = datetime.utcnow()
    referral.commission_rate_applied = commission_pct
    referral.commission_amount = round(payment.amount * commission_pct / 100)
    referral.unlock_at = referral.first_payment_at + timedelta(days=settings["payout_hold_days"])
    if referral.status != "activated":
        referral.status = "activated"
        referral.activated_at = referral.activated_at or referral.first_payment_at


def get_user_subscription_status(user_id):
    """
    A user's plan is derived from their most recent successful subscription
    Payment row rather than a separate table - mirrors how content access
    already works off the Payment table.
    """
    # A successful Payment row alone is not enough to grant a plan.
    # The immutable student_order ledger must also say that this exact
    # subscription checkout was fulfilled. This prevents orphaned/tampered
    # payment rows from becoming entitlements.
    latest = (
        Payment.query
        .filter(
            Payment.user_id == user_id,
            Payment.payment_type == "subscription",
            Payment.status == "success",
            Payment.subscription_expires_at.isnot(None),
            text("""
                payment.id IN (
                    SELECT so.payment_id
                    FROM student_order AS so
                    WHERE so.user_id = :subscription_user_id
                      AND so.order_type = 'subscription'
                      AND so.status = 'fulfilled'
                      AND so.plan = payment.plan
                      AND so.item_id IS NULL
                      AND so.quantity = 1
                      AND so.currency = 'KES'
                )
            """),
        )
        .params(subscription_user_id=user_id)
        .order_by(Payment.subscription_expires_at.desc())
        .first()
    )
    if not latest:
        return {
            "plan": "free", "is_active": False, "expires_at": None,
            "cancel_at_period_end": False, "recurring": False,
        }

    is_active = latest.subscription_expires_at > datetime.utcnow()
    recurring = db.session.execute(text("""
        SELECT cancel_at_period_end
        FROM student_subscription
        WHERE user_id=:uid AND plan=:plan
        ORDER BY id DESC LIMIT 1
    """), {"uid": user_id, "plan": latest.plan}).scalar_one_or_none()
    return {
        "plan": latest.plan if is_active else "free",
        "is_active": is_active,
        "expires_at": latest.subscription_expires_at.isoformat(),
        "cancel_at_period_end": bool(recurring),
        "recurring": True,
    }


def get_ai_plan_tier(user_id):
    """
    Maps a user's subscription status to the plan_tier kwarg ai_service's
    generate_* functions expect ("free" or "premium"), so daily AI limits
    actually reflect what the user is paying for instead of every call
    silently running at the free-tier cap. Only "free"/"premium" are real
    products today - the "plus" tier already present in
    DAILY_FRESH_GENERATION_LIMITS / DAILY_FRESH_TUTOR_LIMITS is dormant
    scaffolding for a tier that hasn't shipped, so it's never returned here.
    """
    status = get_user_subscription_status(user_id)
    return "premium" if status["is_active"] else "free"


def compute_new_subscription_expiry(user_id, plan):
    """Stacks on top of an unexpired plan rather than resetting it."""
    if plan not in SUBSCRIPTION_PLAN_DURATIONS_MONTHS:
        return datetime.utcnow()
    current = get_user_subscription_status(user_id)
    base = datetime.utcnow()
    if current["is_active"] and current["expires_at"]:
        current_expiry = datetime.fromisoformat(current["expires_at"])
        if current_expiry > base:
            base = current_expiry
    return _add_subscription_month(base)


def recompute_subscription_expiries(user_id):
    """
    Rebuilds subscription_expires_at for every remaining successful
    subscription Payment a user has, replaying the same additive-stacking
    logic compute_new_subscription_expiry() uses for a live purchase -
    except here we're reconstructing history, not computing "now", so
    each payment's own created_at (not utcnow()) is the stacking base.
    Needed because admin_refund_payment() can refund an EARLIER payment
    in a stack after LATER ones already had their expiry frozen assuming
    the refunded days were real.

    Call this AFTER flipping a subscription payment's status to
    "refunded" (and before commit) so the remaining chain reflects the
    correct history. No-op if the user has no remaining subscription
    payments.
    """
    remaining = (
        Payment.query.filter(
            Payment.user_id == user_id,
            Payment.payment_type == "subscription",
            Payment.status == "success",
        )
        .order_by(Payment.created_at.asc())
        .all()
    )

    running_expiry = None
    for p in remaining:
        if p.plan not in SUBSCRIPTION_PLAN_DURATIONS_MONTHS:
            continue
        base = p.created_at or datetime.utcnow()
        if running_expiry and running_expiry > base:
            base = running_expiry
        running_expiry = _add_subscription_month(base)
        p.subscription_expires_at = running_expiry


def sync_paystack_payment_status(reference):
    """
    Fetches the authoritative status from Paystack's verify-transaction
    endpoint and updates the matching Payment row. Idempotent - a payment
    already resolved is left alone. Called from both the browser callback
    (best-effort, user is waiting) and the webhook (authoritative,
    server-to-server) - either can be first, both are safe to call.
    """
    # Serialize verification for a single payment. Callback + webhook can
    # legitimately arrive at the same time; without a row lock both requests
    # could observe "pending" and a subscription could be extended twice.
    payment = (
        Payment.query.filter_by(reference=reference)
        .with_for_update()
        .first()
    )
    if not payment or payment.status != "pending":
        return payment

    data = paystack_request("GET", f"/transaction/verify/{reference}")
    tx = data.get("data") or {}
    tx_status = tx.get("status")  # "success" | "failed" | "abandoned" | ...
    payment.provider_reference = str(tx.get("id")) if tx.get("id") is not None else payment.provider_reference

    if tx_status == "success":
        paid_amount_kobo = tx.get("amount")
        paid_currency = (tx.get("currency") or "").upper()
        amount_matches = (
            paid_amount_kobo is not None
            and int(paid_amount_kobo) == int(payment.amount) * 100
        )
        currency_matches = paid_currency == "KES"
        if not amount_matches or not currency_matches:
            print(
                f"Paystack payment mismatch on payment {payment.id}: "
                f"expected {payment.amount * 100} KES kobo, "
                f"got {paid_amount_kobo} {paid_currency or 'UNKNOWN'}"
            )
            payment.status = "failed"
            _student_order_helpers["mark_failed"](payment.id)
        else:
            payment.status = "success"
            if payment.payment_type == "promotion" and payment.opportunity_promotion_id:
                promo = db.session.get(OpportunityPromotion, payment.opportunity_promotion_id)
                if promo:
                    promo.payment_status = "success"

            # Student subscriptions are only activated after the durable order
            # ledger confirms that the payment matches the exact checkout
            # snapshot. A successful provider transaction without a valid
            # order must never grant plan access.
            if payment.payment_type in ("subscription", "content"):
                fulfilled = _student_order_helpers["mark_paid_and_fulfilled"](payment)
                if not fulfilled:
                    payment.status = "failed"
                elif payment.payment_type == "subscription" and payment.plan:
                    payment.subscription_expires_at = compute_new_subscription_expiry(
                        payment.user_id, payment.plan
                    )

            if payment.status == "success":
                _maybe_award_referral_commission(payment)
    elif tx_status in ("failed", "abandoned", "reversed"):
        # A payment that definitively failed cannot fulfill the order.
        _student_order_helpers["mark_failed"](payment.id)
        payment.status = "failed"
        if payment.payment_type == "promotion" and payment.opportunity_promotion_id:
            promo = db.session.get(OpportunityPromotion, payment.opportunity_promotion_id)
            if promo and promo.payment_status != "success":
                promo.payment_status = "failed"
    # else: still processing on Paystack's side, leave as pending

    db.session.commit()
    return payment


def send_verification_email(to_email, token):
    api_key = os.environ.get("BREVO_API_KEY")
    verify_link = f"{BASE_URL}/verify-email?token={token}"

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }
    payload = {
        "sender": {"name": "Prepza", "email": "prepza2026@gmail.com"},
        "to": [{"email": to_email}],
        "subject": "Verify your Prepza account",
        "htmlContent": f"""
            <p>Welcome to Prepza!</p>
            <p>Please verify your email by clicking the link below:</p>
            <p><a href="{verify_link}">{verify_link}</a></p>
            <p>If you didn't sign up for Prepza, you can ignore this email.</p>
        """,
    }

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()


def send_reset_email(to_email, token):
    api_key = os.environ.get("BREVO_API_KEY")
    reset_link = f"{BASE_URL}/reset-password?token={token}"

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }
    payload = {
        "sender": {"name": "Prepza", "email": "prepza2026@gmail.com"},
        "to": [{"email": to_email}],
        "subject": "Reset your Prepza password",
        "htmlContent": f"""
            <p>We received a request to reset your Prepza password.</p>
            <p>Click the link below to choose a new password. This link expires in 1 hour.</p>
            <p><a href="{reset_link}">{reset_link}</a></p>
            <p>If you did not request this, you can safely ignore this email.</p>
        """,
    }

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()


def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        user = db.session.get(User, user_id)
        if not user or not user.is_admin:
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated


def require_csrf(f):
    """
    Requires a valid X-CSRF-Token header matching this session's token.
    Only meaningful for endpoints that also check session["user_id"] -
    this does not replace login checks, it supplements them.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        provided = request.headers.get("X-CSRF-Token")
        expected = session.get("csrf_token")
        if not provided or not expected or not hmac.compare_digest(provided, expected):
            return jsonify({"error": "Missing or invalid CSRF token"}), 403
        return f(*args, **kwargs)
    return decorated


def get_content_prices():
    """
    Returns a dict of content_type -> price (KES), sourced from
    SystemSetting rows (price_notes, price_past_paper, price_qna).
    Missing or invalid settings default to 0 (free).
    """
    keys = ("price_notes", "price_past_paper", "price_qna")
    settings = {
        s.key: s.value
        for s in SystemSetting.query.filter(SystemSetting.key.in_(keys)).all()
    }

    def parse(key):
        try:
            return int(settings.get(key, "0") or "0")
        except (TypeError, ValueError):
            return 0

    return {
        "notes": parse("price_notes"),
        "past_paper": parse("price_past_paper"),
        "qna": parse("price_qna"),
    }


def get_price_for_type(content_type):
    return get_content_prices().get(content_type, 0)


def get_fulfilled_content_file_path(user_id, content_item_id):
    """Return the immutable file path captured by the student's fulfilled order."""
    row = db.session.execute(
        text("""
            SELECT item_file_url_snapshot
            FROM student_order
            WHERE user_id = :user_id
              AND item_id = :item_id
              AND order_type = 'content'
              AND status = 'fulfilled'
              AND quantity = 1
              AND item_file_url_snapshot IS NOT NULL
            ORDER BY fulfilled_at DESC NULLS LAST, id DESC
            LIMIT 1
        """),
        {"user_id": user_id, "item_id": content_item_id},
    ).mappings().first()
    return row["item_file_url_snapshot"] if row else None


def has_access(user_id, content_item):
    if get_price_for_type(content_item.content_type) == 0:
        return True

    successful_payment = Payment.query.filter_by(
        user_id=user_id,
        content_item_id=content_item.id,
        status="success",
    ).first()
    if not successful_payment:
        return False

    # New purchases are entitled through the durable student-order ledger.
    # The payment alone proves money was recorded; the fulfilled order proves
    # the exact requested item was fulfilled for this student. Legacy
    # successful content payments created before the order ledger existed are
    # retained as a compatibility fallback only when no order row exists.
    order_row = db.session.execute(
        text("""
            SELECT status, user_id, item_id, payment_id, order_type, quantity
            FROM student_order
            WHERE payment_id = :payment_id
            LIMIT 1
        """),
        {"payment_id": successful_payment.id},
    ).mappings().first()

    if not order_row:
        # New entitlement flow: a successful payment without a durable order
        # is an invariant failure, not a reason to grant access.
        return False

    return bool(
        order_row["status"] == "fulfilled"
        and order_row["user_id"] == user_id
        and order_row["item_id"] == content_item.id
        and order_row["payment_id"] == successful_payment.id
        and order_row["order_type"] == "content"
        and int(order_row["quantity"] or 0) == 1
    )


def get_signed_url(bucket_path, expires_in=60, bucket="content"):
    """
    Generates a temporary signed URL for a file stored in the private
    "content" bucket on Supabase Storage. Returns None if anything fails,
    rather than raising - a missing file shouldn't crash the whole request.
    """
    if not bucket_path:
        return None

    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not supabase_url or not service_key:
        print("WARNING: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set")
        return None

    sign_url = f"{supabase_url}/storage/v1/object/sign/{bucket}/{bucket_path}"
    headers = {
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(sign_url, json={"expiresIn": expires_in}, headers=headers)
        response.raise_for_status()
        signed_path = response.json().get("signedURL")
        if not signed_path:
            return None
        return f"{supabase_url}/storage/v1{signed_path}"
    except Exception as e:
        print(f"ERROR generating signed URL for {bucket_path}: {e}")
        return None


CHAT_ATTACHMENT_URL_TTL_SECONDS = 3600
CHAT_ATTACHMENT_URL_REFRESH_BUFFER_SECONDS = 300


def get_cached_chat_attachment_url(attachment):
    """
    Chat redesign Phase 1a. Returns a signed URL for a chat
    MessageAttachment, reusing the cached one on the row if it is
    still valid (with a 5-minute safety buffer), otherwise
    generating a fresh one and caching it.

    This is the actual fix for the confirmed root cause of chat
    images feeling slow: without caching, every poll of
    GET /chats/<id>/messages regenerated a brand-new signed URL
    (new token) for every attachment, so the browser could never
    cache the image - a new URL is always a cache miss. Returning
    the SAME URL across polls lets normal HTTP image caching work.

    Does not raise - mirrors get_signed_url()'s own "return None
    rather than crash the request" posture, since a missing/failed
    attachment URL shouldn't break the whole message list.
    """
    if not attachment or not attachment.storage_path:
        return None

    now = datetime.utcnow()
    if (
        attachment.cached_view_url
        and attachment.cached_view_url_expires_at
        and attachment.cached_view_url_expires_at - timedelta(seconds=CHAT_ATTACHMENT_URL_REFRESH_BUFFER_SECONDS) > now
    ):
        return attachment.cached_view_url

    fresh_url = get_signed_url(
        attachment.storage_path, expires_in=CHAT_ATTACHMENT_URL_TTL_SECONDS, bucket="documents"
    )
    if not fresh_url:
        return None

    attachment.cached_view_url = fresh_url
    attachment.cached_view_url_expires_at = now + timedelta(seconds=CHAT_ATTACHMENT_URL_TTL_SECONDS)
    db.session.commit()

    return fresh_url


def fetch_private_file_bytes(bucket_path, bucket="content"):
    """
    Downloads the raw file bytes for a path in the private "content" bucket,
    using the service role key. This happens server-side only - the raw
    bytes/URL are never sent to the browser, only the watermarked, rendered
    page images are (see render_watermarked_page + the /view/page route).
    Returns None if anything fails.
    """
    if not bucket_path:
        return None

    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not supabase_url or not service_key:
        print("WARNING: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set")
        return None

    download_url = f"{supabase_url}/storage/v1/object/{bucket}/{bucket_path}"
    headers = {
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
    }

    try:
        response = requests.get(download_url, headers=headers)
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"ERROR fetching private file {bucket_path}: {e}")
        return None


def render_watermarked_page(pdf_bytes, page_num, watermark_text, zoom=2.0):
    """
    Renders a single page of a PDF as PNG bytes with a tiled, semi-transparent
    watermark (the viewing student's email) stamped across it.

    The watermark is drawn directly onto the PDF page BEFORE rasterizing, so
    it's baked into the same pixels as the real content - not a separate
    layer that could be cropped or edited out afterward.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    if page_num < 0 or page_num >= doc.page_count:
        total_pages = doc.page_count
        doc.close()
        raise ValueError(f"page_num {page_num} out of range (doc has {total_pages} pages)")

    page = doc[page_num]
    rect = page.rect
    tile_w, tile_h = 220, 140
    angle = 30
    morph_matrix = fitz.Matrix(angle)

    y = 20
    row = 0
    while y < rect.height:
        x = -60 if row % 2 == 0 else -60 + tile_w / 2
        while x < rect.width:
            point = fitz.Point(x, y)
            page.insert_text(
                point,
                watermark_text,
                fontsize=11,
                color=(0.6, 0.6, 0.6),
                fill_opacity=0.4,
                overlay=False,  # draw BEHIND existing content - hidden under
                                # real text, visible only in whitespace/margins
                morph=(point, morph_matrix),
            )
            x += tile_w
        y += tile_h
        row += 1

    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    png_bytes = pix.tobytes("png")
    page_count = doc.page_count
    doc.close()
    return png_bytes, page_count


# ---------- Maintenance mode ----------
# Blocks only content/user-data routes. Everything else (auth lifecycle,
# admin, payments callback, health check, static assets) stays open even
# during maintenance so admins can still work and M-Pesa callbacks still
# land.
MAINTENANCE_BLOCKED_PREFIXES = (
    "/library",
    "/payment-history",
    "/profile",
    "/delete-account",
    "/content/",
    "/documents",
)
MAINTENANCE_NEVER_BLOCK_PREFIXES = (
    "/admin",
    "/mpesa/callback/",
    "/me",
    "/login",
    "/logout",
    "/health",
    "/static/",
    "/sw.js",
)
MAINTENANCE_CACHE_TTL = timedelta(seconds=30)
_maintenance_cache = {"value": None, "checked_at": None}


def _invalidate_maintenance_cache():
    _maintenance_cache["value"] = None
    _maintenance_cache["checked_at"] = None


def is_maintenance_mode():
    now = datetime.utcnow()
    checked_at = _maintenance_cache["checked_at"]
    if checked_at is not None and (now - checked_at) < MAINTENANCE_CACHE_TTL:
        return _maintenance_cache["value"]
    setting = SystemSetting.query.filter_by(key="maintenance_mode").first()
    value = bool(setting and setting.value == "true")
    _maintenance_cache["value"] = value
    _maintenance_cache["checked_at"] = now
    return value


@app.before_request
def enforce_maintenance_mode():
    path = request.path
    if any(path.startswith(p) for p in MAINTENANCE_NEVER_BLOCK_PREFIXES):
        return None
    if not any(path.startswith(p) for p in MAINTENANCE_BLOCKED_PREFIXES):
        return None
    if not is_maintenance_mode():
        return None
    setting = SystemSetting.query.filter_by(key="maintenance_message").first()
    message = (
        setting.value
        if setting and setting.value
        else "Prepza is temporarily down for maintenance. Please check back shortly."
    )
    return jsonify({"error": "maintenance", "message": message}), 503


# ---------- Session invalidation ----------
# Lets the server kill an existing session early (e.g. on password change)
# without waiting for the 7-day cookie to naturally expire. Every login
# stamps the CURRENT session_version into the cookie; this hook compares
# that stamp against the live database value on every request.
@app.before_request
def enforce_session_version():
    user_id = session.get("user_id")
    if not user_id:
        return None

    stamped_version = session.get("_session_version")
    user = db.session.get(User, user_id)
    if not user:
        session.pop("user_id", None)
        session.pop("_session_version", None)
        return None

    if stamped_version is None:
        # Legacy session created before this feature existed - it has no
        # stamp to compare against. Trust it once (it was already a valid
        # login) and stamp the current version in, so any FUTURE password
        # change still invalidates it correctly from this point on.
        session["_session_version"] = user.session_version
        return None

    if stamped_version != user.session_version:
        session.pop("user_id", None)
        session.pop("_session_version", None)

    return None


# ---------- Activity tracking (for admin "Active Today") ----------
# Broad, cheap DAU signal: touches on ANY authenticated request (login,
# browsing, chatting, studying - not just specific study actions like
# StudyActivityLog). Throttled via the session so this costs at most one
# UPDATE per user per ACTIVITY_SYNC_INTERVAL, not one per request.

ACTIVITY_TRACKING_SKIP_PREFIXES = ("/static/", "/sw.js", "/health")
ACTIVITY_SYNC_INTERVAL = timedelta(minutes=5)


@app.before_request
def track_last_active():
    if request.path.startswith(ACTIVITY_TRACKING_SKIP_PREFIXES):
        return None
    user_id = session.get("user_id")
    if not user_id:
        return None

    now = datetime.utcnow()
    last_sync_raw = session.get("_last_active_sync")
    if last_sync_raw:
        try:
            last_sync = datetime.fromisoformat(last_sync_raw)
        except ValueError:
            last_sync = None
        if last_sync and (now - last_sync) < ACTIVITY_SYNC_INTERVAL:
            return None

    # Bulk UPDATE (no SELECT) so this stays a single cheap query - we
    # don't need the User object, just to touch the timestamp.
    User.query.filter_by(id=user_id).update({"last_active_at": now})
    db.session.commit()
    session["_last_active_sync"] = now.isoformat()
    return None


@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/sw.js")
def service_worker():
    """
    Served at the root URL (not /static/sw.js) so its scope covers the
    whole site, not just the static folder. Deliberately not cached
    long-term, unlike images/CSS/JS, so browsers pick up updates to this
    file quickly.
    """
    response = send_from_directory(app.static_folder, "sw.js")
    response.headers["Content-Type"] = "application/javascript"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/health")
@limiter.exempt
def health():
    """
    Lightweight status check. Pinged automatically every ~10 minutes by a
    GitHub Actions workflow to prevent Render's free tier from spinning down
    and Supabase's free tier from auto-pausing due to inactivity.

    Deliberately excluded from rate limiting (it's an automated, low-value
    target for abuse) and returns no sensitive data.
    """
    from sqlalchemy import text
    try:
        db.session.execute(text("SELECT 1"))
        _sweep_expired_opportunities_safe()
        return jsonify({"status": "ok"}), 200
    except Exception:
        return jsonify({"status": "error"}), 503


# ---------- Auth routes ----------

@app.route("/universities")
def list_universities():
    """
    Public, unauthenticated - the signup wizard needs this before a
    session exists. Only returns active universities so a
    deactivated one can't be selected by new signups.
    """
    universities = University.query.filter_by(is_active=True).order_by(University.name).all()
    return jsonify([
        {"id": u.id, "name": u.name, "short_code": u.short_code, "country": u.country}
        for u in universities
    ])


@app.route("/universities/<int:university_id>/programs")
def list_programs(university_id):
    """
    Public, unauthenticated - same reasoning as /universities above.
    404s on an unknown or inactive university instead of silently
    returning an empty list, so the frontend can tell 'no programs
    yet' apart from 'that university id doesn't exist'.
    """
    university = University.query.filter_by(id=university_id, is_active=True).first()
    if not university:
        return jsonify({"error": "University not found"}), 404

    programs = Program.query.filter_by(university_id=university_id, is_active=True).order_by(Program.name).all()
    return jsonify([
        {
            "id": p.id,
            "name": p.name,
            "degree_level": p.degree_level,
            "discipline_category": p.discipline_category,
        }
        for p in programs
    ])


@app.route("/signup", methods=["POST"])
@limiter.limit("5 per hour")
def signup():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    year = data.get("year")
    semester = data.get("semester")
    university_id = data.get("university_id")
    program_id = data.get("program_id")
    requested_program_name = data.get("requested_program_name")
    display_name = data.get("display_name")

    if display_name is not None:
        if not isinstance(display_name, str):
            return jsonify({"error": "Invalid display name"}), 400
        display_name = display_name.strip()
        if len(display_name) > 50:
            return jsonify({"error": "Display name must be 50 characters or fewer"}), 400
        display_name = display_name or None

    if not email:
        return jsonify({"error": "Email is required"}), 400
    if not EMAIL_REGEX.match(email):
        return jsonify({"error": "Email format is invalid"}), 400

    if not password:
        return jsonify({"error": "Password is required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters long"}), 400
    strength_error = password_strength_error(password)
    if strength_error:
        return jsonify({"error": strength_error}), 400

    if year is None or not isinstance(year, int) or year < 1 or year > 4:
        return jsonify({"error": "Year is required and must be a number between 1 and 4"}), 400

    if semester is None or not isinstance(semester, int) or semester not in (1, 2):
        return jsonify({"error": "Semester is required and must be 1 or 2"}), 400

    if not university_id or not isinstance(university_id, int):
        return jsonify({"error": "University is required"}), 400
    university = University.query.filter_by(id=university_id, is_active=True).first()
    if not university:
        return jsonify({"error": "Selected university was not found"}), 400

    if not program_id or not isinstance(program_id, int):
        return jsonify({"error": "Course is required"}), 400
    program = Program.query.filter_by(id=program_id, university_id=university_id, is_active=True).first()
    if not program:
        return jsonify({"error": "Selected course does not belong to the selected university"}), 400

    if requested_program_name is not None:
        if not isinstance(requested_program_name, str):
            return jsonify({"error": "Invalid course name"}), 400
        requested_program_name = requested_program_name.strip()[:150] or None

    raw_signup_source = data.get("signup_source")
    signup_source = None
    if raw_signup_source is not None and isinstance(raw_signup_source, str):
        cleaned = raw_signup_source.strip().lower()[:50]
        cleaned = "".join(ch for ch in cleaned if ch.isalnum() or ch in ("_", "-"))
        signup_source = cleaned or None
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({"error": "An account with this email already exists"}), 409

    token = secrets.token_urlsafe(32)

    new_user = User(
        email=email,
        password_hash=generate_password_hash(password),
        year=year,
        semester=semester,
        display_name=display_name,
        email_verified=False,
        verification_token=token,
        signup_source=signup_source,
        university_id=university_id,
        program_id=program_id,
        requested_program_name=requested_program_name,
    )
    db.session.add(new_user)
    db.session.commit()

    raw_ref_code = data.get("ref")
    if raw_ref_code and isinstance(raw_ref_code, str):
        try:
            ref_code_clean = raw_ref_code.strip().upper()[:20]
            ambassador = Ambassador.query.filter_by(
                referral_code=ref_code_clean, status="active"
            ).first()
            if ambassador:
                raw_channel = data.get("via")
                channel = None
                if raw_channel and isinstance(raw_channel, str):
                    channel = "".join(
                        ch for ch in raw_channel.strip().lower()[:30]
                        if ch.isalnum() or ch in ("_", "-")
                    ) or None
                db.session.add(Referral(
                    ambassador_id=ambassador.id,
                    referred_user_id=new_user.id,
                    referral_code_used=ref_code_clean,
                    channel=channel,
                ))
                db.session.commit()
        except Exception as e:
            # Never let referral-tracking issues affect the already-created
            # account - same defensive stance as the verification email
            # try/except right below.
            db.session.rollback()
            print(f"WARNING: referral capture failed for new user {new_user.id}: {e}")

    try:
        send_verification_email(email, token)
        email_status = "Verification email sent"
    except Exception as e:
        email_status = f"Account created but verification email failed to send: {str(e)}"

    return jsonify({
        "message": "Account created successfully",
        "user_id": new_user.id,
        "email_status": email_status,
    }), 201


@app.route("/verify-email")
def verify_email():
    """
    Serves a lightweight landing page instead of verifying directly on
    this GET request. Email link scanners fetch this URL but don't run
    JavaScript, so they can no longer silently consume the token - the
    actual verification happens via the JS-triggered POST below, from
    the React app's VerifyConfirmScreen, reached at this same URL.
    """
    return send_from_directory(app.static_folder, "index.html")


@app.route("/reset-password")
def reset_password_page():
    """
    Serves the React app shell so the emailed reset link
    (?token=... in the query string) has somewhere to land.
    ResetPasswordScreen reads the token client-side and POSTs it to
    POST /reset-password below, which does the actual reset.
    """
    return send_from_directory(app.static_folder, "index.html")


@app.route("/signup")
def signup_page():
    """
    Serves the React app shell so an ambassador referral link
    (BASE_URL/signup?ref=...&via=... - see ambassador_dashboard()'s
    referral_link field) has somewhere to land. Without this route,
    GET /signup 404'd before the React app - and therefore the
    ?ref=... it's supposed to read - ever loaded at all. Mirrors
    GET /reset-password and GET /verify-email above. SignupScreen
    reads ref/via client-side and includes them in its eventual
    POST /signup body (that's the separate, already-existing route
    below, unaffected by this one).
    """
    return send_from_directory(app.static_folder, "index.html")


@app.route("/verify-email/confirm", methods=["POST"])
def verify_email_confirm():
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    if not token:
        return jsonify({"error": "Missing verification token"}), 400

    user = User.query.filter_by(verification_token=token).first()
    if not user:
        return jsonify({"error": "This link is invalid or has already been used"}), 400

    user.email_verified = True
    user.verification_token = None
    _sync_referral_progress(user)
    db.session.commit()

    # Auto-login: set the session the same way /login does, so the user
    # lands straight in the dashboard instead of having to log in again.
    session.permanent = True
    session["user_id"] = user.id
    session["_session_version"] = user.session_version

    return jsonify({
        "message": "Email verified successfully",
        "redirect": "/",
    })
@app.route("/resend-verification", methods=["POST"])
@limiter.limit("5 per hour")
def resend_verification():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "Email is required"}), 400
    user = User.query.filter_by(email=email).first()
    # Always return the same generic message whether or not the account
    # exists or is already verified - same privacy pattern as /forgot-password,
    # so this endpoint can't be used to check which emails are registered.
    generic_response = jsonify({
        "message": "If an unverified account with that email exists, a new verification link has been sent."
    })
    if not user or user.email_verified:
        return generic_response
    token = secrets.token_urlsafe(32)
    user.verification_token = token
    db.session.commit()
    try:
        send_verification_email(email, token)
    except Exception:
        pass
    return generic_response
@app.route("/forgot-password", methods=["POST"])
@limiter.limit("5 per hour")
def forgot_password():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "Email is required"}), 400

    user = User.query.filter_by(email=email).first()

    # Always return the same message whether or not the account exists -
    # this stops people from using this endpoint to check which emails are registered.
    generic_response = jsonify({
        "message": "If an account with that email exists, a reset link has been sent."
    })

    if not user:
        return generic_response

    token = secrets.token_urlsafe(32)
    user.reset_token = token
    user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
    db.session.commit()

    try:
        send_reset_email(email, token)
    except Exception:
        pass  # Don't reveal email-sending failures - keep the response generic either way

    return generic_response


@app.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    token = data.get("token") or ""
    new_password = data.get("new_password") or ""

    if not token:
        return jsonify({"error": "Missing reset token"}), 400
    if len(new_password) < 8:
        return jsonify({"error": "Password must be at least 8 characters long"}), 400
    strength_error = password_strength_error(new_password)
    if strength_error:
        return jsonify({"error": strength_error}), 400

    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.utcnow():
        return jsonify({"error": "Invalid or expired reset link"}), 400

    user.password_hash = generate_password_hash(new_password)
    user.reset_token = None
    user.reset_token_expiry = None
    user.session_version = (user.session_version or 0) + 1
    db.session.commit()

    return jsonify({"message": "Password reset successfully. You can now log in."})


@app.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = User.query.filter_by(email=email).first()

    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401

    # Keep account state generic at the login boundary. Verification and
    # suspension status must not become an account-enumeration oracle.
    if not user.email_verified or user.is_suspended:
        return jsonify({"error": "Invalid email or password"}), 401

    session.permanent = True
    session["user_id"] = user.id
    session["_session_version"] = user.session_version
    return jsonify({"message": "Logged in successfully", "user_id": user.id})


@app.route("/auth/google")
@limiter.limit("20 per minute")
def google_auth_start():
    """
    Redirects the browser to Google's consent screen. A random state
    token is stashed in the session and checked on callback to guard
    against CSRF - this is a full browser navigation, not a fetch()
    call, so the usual @require_csrf header check doesn't apply here.
    """
    if not GOOGLE_CLIENT_ID:
        return jsonify({"error": "Google Sign-In is not configured"}), 503

    state = secrets.token_urlsafe(24)
    session["google_oauth_state"] = state
    redirect_uri = f"{BASE_URL.rstrip('/')}/auth/google/callback"

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@app.route("/auth/google/callback")
def google_auth_callback():
    """
    Google redirects the user's browser back here with ?code=...&state=...
    (or ?error=... if they cancelled). Exchanges the code for tokens,
    fetches the Google profile, and logs the user in - creating a new
    account if this is their first time signing in with this email.

    New Google accounts get a random, never-shared password hash (so the
    NOT NULL password_hash column is satisfied) and no university_id /
    program_id yet - the frontend is expected to route them into a
    profile-completion step when GET /me shows university_id: null.
    """
    if request.args.get("error"):
        return redirect("/?auth_error=google_denied")

    state = request.args.get("state")
    expected_state = session.pop("google_oauth_state", None)
    if not state or not expected_state or state != expected_state:
        return redirect("/?auth_error=invalid_state")

    code = request.args.get("code")
    if not code:
        return redirect("/?auth_error=missing_code")

    redirect_uri = f"{BASE_URL.rstrip('/')}/auth/google/callback"
    try:
        token_resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            return redirect("/?auth_error=token_exchange_failed")

        userinfo_resp = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        userinfo_resp.raise_for_status()
        info = userinfo_resp.json()
    except requests.RequestException:
        return redirect("/?auth_error=google_unreachable")

    email = (info.get("email") or "").strip().lower()
    email_verified = info.get("email_verified", False)
    name = (info.get("name") or "").strip()

    if not email or not email_verified:
        return redirect("/?auth_error=unverified_google_email")

    user = User.query.filter_by(email=email).first()
    is_new = False
    if not user:
        is_new = True
        user = User(
            email=email,
            password_hash=generate_password_hash(secrets.token_urlsafe(32)),
            display_name=name[:50] or None,
            email_verified=True,
            created_at=datetime.utcnow(),
            signup_source="google_oauth",
        )
        db.session.add(user)
        db.session.commit()
    else:
        if user.is_suspended:
            return redirect("/?auth_error=account_suspended")
        if not user.email_verified:
            # A successful Google login on this exact email is strong enough
            # proof of ownership to satisfy our own verification requirement.
            user.email_verified = True
            db.session.commit()

    session.permanent = True
    session["user_id"] = user.id
    session["_session_version"] = user.session_version

    if is_new or user.university_id is None or user.program_id is None or user.year is None or user.semester is None:
        return redirect("/?complete_profile=1")
    return redirect("/")


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return jsonify({"message": "Logged out successfully"})


@app.route("/me")
def me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    user = db.session.get(User, user_id)

    if not user or user.is_suspended:
        session.pop("user_id", None)
        return jsonify({"error": "Not logged in"}), 401

    return jsonify({
        "id": user.id,
        "email": user.email,
        "year": user.year,
        "semester": user.semester,
        "display_name": user.display_name,
        "bio": user.bio,
        "phone_number": user.phone_number,
        "profile_visibility": user.profile_visibility,
        "who_can_message": user.who_can_message,
        "who_can_follow": user.who_can_follow,
        "read_receipts_enabled": bool(user.read_receipts_enabled),
        "email_verified": user.email_verified,
        "is_admin": user.is_admin,
        "university_id": user.university_id,
        "program_id": user.program_id,
        "csrf_token": session["csrf_token"],
    })
@app.route("/delete-account", methods=["DELETE"])
@require_csrf
def delete_account():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    user = db.session.get(User, user_id)
    if not user:
        session.pop("user_id", None)
        return jsonify({"error": "Account not found"}), 404
    # Preserve payment/financial records for accounting and any M-Pesa
    # dispute purposes - just disassociate them from the deleted user
    # instead of deleting the rows outright.
    Payment.query.filter_by(user_id=user.id).update({"user_id": None})
    db.session.delete(user)
    db.session.commit()
    session.pop("user_id", None)
    return jsonify({"message": "Account deleted successfully"})


@app.route("/profile", methods=["PATCH"])
@require_csrf
def update_profile():
    """
    Lets a logged-in student update their own year and semester -
    e.g. a real account that never had them set, or a student moving
    on to a new semester. Uses the same validation rules as /signup.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    year = data.get("year")
    semester = data.get("semester")

    if year is None or semester is None:
        return jsonify({"error": "year and semester are both required"}), 400

    if not isinstance(year, int) or year < 1 or year > 4:
        return jsonify({"error": "Year must be a number between 1 and 4"}), 400

    if not isinstance(semester, int) or semester not in (1, 2):
        return jsonify({"error": "Semester must be 1 or 2"}), 400

    display_name = data.get("display_name", None)
    bio = data.get("bio", None)
    phone_number = data.get("phone_number", None)
    if phone_number is not None:
        phone_number = phone_number.strip()
        if phone_number and not PHONE_NUMBER_REGEX.match(phone_number):
            return jsonify({"error": "Phone number must be a valid number (e.g. +254712345678)"}), 400

    profile_visibility = data.get("profile_visibility", None)
    if profile_visibility is not None and profile_visibility not in PROFILE_VISIBILITY_VALUES:
        return jsonify({"error": "profile_visibility must be one of: " + ", ".join(sorted(PROFILE_VISIBILITY_VALUES))}), 400
    who_can_message = data.get("who_can_message", None)
    if who_can_message is not None and who_can_message not in WHO_CAN_MESSAGE_VALUES:
        return jsonify({"error": "who_can_message must be one of: " + ", ".join(sorted(WHO_CAN_MESSAGE_VALUES))}), 400
    who_can_follow = data.get("who_can_follow", None)
    if who_can_follow is not None and who_can_follow not in WHO_CAN_FOLLOW_VALUES:
        return jsonify({"error": "who_can_follow must be one of: " + ", ".join(sorted(WHO_CAN_FOLLOW_VALUES))}), 400
    if display_name is not None:
        display_name = display_name.strip()
        if len(display_name) > 50:
            return jsonify({"error": "Display name must be 50 characters or fewer"}), 400
    if bio is not None:
        bio = bio.strip()
        if len(bio) > 160:
            return jsonify({"error": "Bio must be 160 characters or fewer"}), 400

    # Optional - lets a Google Sign-In account (which has no university/
    # program yet) complete its profile after the fact. Same validation
    # /signup uses: university_id must be real and active, program_id (if
    # given) must belong to that exact university.
    university_id = data.get("university_id", None)
    program_id = data.get("program_id", None)
    university = None
    if university_id is not None:
        if not isinstance(university_id, int):
            return jsonify({"error": "Invalid university"}), 400
        university = University.query.filter_by(id=university_id, is_active=True).first()
        if not university:
            return jsonify({"error": "Selected university was not found"}), 400
    if program_id is not None:
        if not isinstance(program_id, int):
            return jsonify({"error": "Invalid program"}), 400
        lookup_university_id = university_id if university_id is not None else (
            db.session.get(User, user_id).university_id
        )
        program = Program.query.filter_by(id=program_id, university_id=lookup_university_id, is_active=True).first()
        if not program:
            return jsonify({"error": "Selected course does not belong to the selected university"}), 400

    user = db.session.get(User, user_id)
    user.year = year
    user.semester = semester
    if display_name is not None:
        user.display_name = display_name or None
    if bio is not None:
        user.bio = bio or None
    if phone_number is not None:
        user.phone_number = phone_number or None
    if profile_visibility is not None:
        user.profile_visibility = profile_visibility
    if who_can_message is not None:
        user.who_can_message = who_can_message
    if who_can_follow is not None:
        user.who_can_follow = who_can_follow
    read_receipts_enabled = data.get("read_receipts_enabled", None)
    if read_receipts_enabled is not None and not isinstance(read_receipts_enabled, bool):
        return jsonify({"error": "read_receipts_enabled must be a boolean"}), 400
    if read_receipts_enabled is not None:
        user.read_receipts_enabled = read_receipts_enabled
    if university_id is not None:
        user.university_id = university_id
    if program_id is not None:
        user.program_id = program_id
    _sync_referral_progress(user)
    db.session.commit()

    return jsonify({
        "message": "Profile updated",
        "year": user.year,
        "semester": user.semester,
        "display_name": user.display_name,
        "bio": user.bio,
        "phone_number": user.phone_number,
        "profile_visibility": user.profile_visibility,
        "who_can_message": user.who_can_message,
        "who_can_follow": user.who_can_follow,
        "read_receipts_enabled": bool(user.read_receipts_enabled),
        "university_id": user.university_id,
        "program_id": user.program_id,
    })


@app.route("/change-password", methods=["POST"])
@limiter.limit(
    "5 per hour",
    key_func=lambda: f"change-password:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def change_password():
    """
    Lets a logged-in student change their own password from Settings,
    given their current password for confirmation. Uses the same
    strength rules as /signup and /reset-password
    (password_strength_error) so this can never disagree with what
    those endpoints accept.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""

    if not current_password:
        return jsonify({"error": "Current password is required"}), 400

    user = db.session.get(User, user_id)
    if not user or not check_password_hash(user.password_hash, current_password):
        return jsonify({"error": "Current password is incorrect"}), 401

    if len(new_password) < 8:
        return jsonify({"error": "Password must be at least 8 characters long"}), 400
    strength_error = password_strength_error(new_password)
    if strength_error:
        return jsonify({"error": strength_error}), 400
    if check_password_hash(user.password_hash, new_password):
        return jsonify({"error": "New password must be different from your current password"}), 400

    user.password_hash = generate_password_hash(new_password)
    user.session_version = (user.session_version or 0) + 1
    db.session.commit()

    return jsonify({"message": "Password changed successfully."})


@app.route("/change-email", methods=["POST"])
@limiter.limit(
    "5 per hour",
    key_func=lambda: f"change-email:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def change_email():
    """
    Lets a logged-in student change their own login email from
    Settings, given their current password for confirmation. The new
    email is applied immediately but the account is marked unverified
    (same fields /signup uses) until the student clicks the link in a
    fresh verification email sent to the new address - reusing
    login()'s existing unverified-account gate rather than adding new
    enforcement.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    password = data.get("password") or ""
    new_email = (data.get("new_email") or "").strip().lower()

    if not password:
        return jsonify({"error": "Your current password is required to change your email"}), 400

    user = db.session.get(User, user_id)
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Password is incorrect"}), 401

    if not new_email:
        return jsonify({"error": "New email is required"}), 400
    if not EMAIL_REGEX.match(new_email):
        return jsonify({"error": "Email format is invalid"}), 400
    if new_email == user.email:
        return jsonify({"error": "That's already your current email"}), 400

    existing = User.query.filter_by(email=new_email).first()
    if existing:
        return jsonify({"error": "An account with this email already exists"}), 409

    token = secrets.token_urlsafe(32)
    user.email = new_email
    user.email_verified = False
    user.verification_token = token
    db.session.commit()

    try:
        send_verification_email(new_email, token)
        email_status = "Verification email sent"
    except Exception as e:
        email_status = f"Email updated but verification email failed to send: {str(e)}"

    return jsonify({
        "message": "Email updated - please verify your new address before your next login.",
        "email": user.email,
        "email_verified": user.email_verified,
        "email_status": email_status,
    })


@app.route("/payment-history")
def payment_history():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    # Student billing is subscription-first. Individual content purchases are
    # legacy and must not appear as current student transactions. Keep the
    # endpoint ready for future usage/add-on payments without reviving content
    # ownership as a product model.
    payments = (
        Payment.query.filter(
            Payment.user_id == user_id,
            Payment.payment_type.in_(( "subscription", "addon" )),
        )
        .order_by(Payment.created_at.desc())
        .all()
    )

    result = []
    for p in payments:
        result.append({
            "id": p.id,
            "payment_type": p.payment_type,
            "content_title": None,
            "plan": p.plan,
            "amount": p.amount,
            "status": p.status,
            "provider": p.provider,
            "reference": p.reference,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    return jsonify({"payments": result})


# ---------- Document routes (student uploads) ----------

ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "jpg", "jpeg", "png", "webm", "ogg", "mp3", "m4a", "wav", "aac", "mp4"}
MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB - revisit once real usage data exists
CONTENT_HASH_REGEX = re.compile(r"^[a-f0-9]{64}$")


def get_document_extension(filename):
    """
    Extracts and validates a file extension from a client-supplied filename.
    Returns the lowercase extension (no dot) if allowed, otherwise None.
    This is only ever used to pick a storage suffix - it is not trusted as
    a statement of the file's real content type.
    """
    if not filename or "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[-1].strip().lower()
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        return None
    return ext


def create_signed_upload_url(bucket, path):
    """
    Requests a short-lived signed upload URL from Supabase Storage so the
    client can PUT the file bytes directly to Supabase - the file itself
    never passes through this Flask server. Returns None on failure.
    """
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not supabase_url or not service_key:
        print("WARNING: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set")
        return None

    sign_url = f"{supabase_url}/storage/v1/object/upload/sign/{bucket}/{path}"
    headers = {
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(sign_url, json={}, headers=headers)
        response.raise_for_status()
        signed_path = response.json().get("url")
        if not signed_path:
            return None
        return f"{supabase_url}/storage/v1{signed_path}"
    except Exception as e:
        print(f"ERROR generating signed upload URL for {bucket}/{path}: {e}")
        return None


def storage_object_exists(bucket, path):
    """
    Confirms an object actually landed in Supabase Storage. Used to verify
    a client's "upload finished" claim before trusting it server-side.
    """
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not supabase_url or not service_key:
        print("WARNING: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set")
        return False

    info_url = f"{supabase_url}/storage/v1/object/info/{bucket}/{path}"
    headers = {
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
    }

    try:
        response = requests.get(info_url, headers=headers)
        return response.status_code == 200
    except Exception as e:
        print(f"ERROR checking storage object {bucket}/{path}: {e}")
        return False


@app.route("/documents", methods=["POST"])
@limiter.limit("20 per hour")
@require_csrf
def create_document():
    """
    Registers a new personal document. If a DocumentContent row already
    exists for this exact content_hash (byte-identical file previously
    uploaded by anyone), this student is attached to that existing content
    immediately - no upload, no re-processing, no re-billing of AI cost.
    Otherwise a new DocumentContent is created and a signed direct-upload
    URL is returned so the client can PUT the file straight to Supabase
    Storage without the bytes passing through this server.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    title = (data.get("title") or "").strip()
    original_filename = (data.get("original_filename") or "").strip()
    file_size_bytes = data.get("file_size_bytes")
    content_hash = (data.get("content_hash") or "").strip().lower()

    if not title or len(title) > 200:
        return jsonify({"error": "Title is required and must be 200 characters or fewer"}), 400
    if not original_filename or len(original_filename) > 255:
        return jsonify({"error": "original_filename is required and must be 255 characters or fewer"}), 400
    ext = get_document_extension(original_filename)
    if not ext:
        return jsonify({"error": "Unsupported file type"}), 400
    if not isinstance(file_size_bytes, int) or isinstance(file_size_bytes, bool) or file_size_bytes <= 0:
        return jsonify({"error": "file_size_bytes must be a positive integer"}), 400
    if file_size_bytes > MAX_DOCUMENT_SIZE_BYTES:
        return jsonify({"error": f"File exceeds the {MAX_DOCUMENT_SIZE_BYTES // (1024 * 1024)} MB limit"}), 400
    if not CONTENT_HASH_REGEX.match(content_hash):
        return jsonify({"error": "content_hash must be a 64-character hex SHA-256 hash"}), 400

    existing_content = DocumentContent.query.filter_by(content_hash=content_hash).first()

    if existing_content:
        existing_user_document = Document.query.filter_by(
            user_id=user_id,
            document_content_id=existing_content.id,
            is_removed=False,
        ).order_by(Document.id.asc()).first()
        if existing_user_document:
            return jsonify({
                "document_id": existing_user_document.id,
                "status": existing_content.status,
                "duplicate": True,
                "already_in_studyhub": True,
            }), 200

        doc_status = "processing" if existing_content.status in ("pending", "processing") else existing_content.status
        new_document = Document(
            user_id=user_id,
            document_content_id=existing_content.id,
            title=title,
            original_filename=original_filename,
            status=doc_status,
        )
        db.session.add(new_document)
        db.session.commit()
        return jsonify({
            "document_id": new_document.id,
            "status": new_document.status,
            "duplicate": True,
        }), 201

    storage_path = f"{content_hash}.{ext}"
    new_content = DocumentContent(
        content_hash=content_hash,
        storage_path=storage_path,
        file_type=ext,
        file_size_bytes=file_size_bytes,
        status="pending",
    )
    db.session.add(new_content)
    db.session.flush()  # assign new_content.id before the Document row references it

    new_document = Document(
        user_id=user_id,
        document_content_id=new_content.id,
        title=title,
        original_filename=original_filename,
        status="uploading",
    )
    db.session.add(new_document)
    db.session.commit()

    upload_url = create_signed_upload_url("documents", storage_path)
    if not upload_url:
        return jsonify({"error": "Could not prepare upload - please try again shortly"}), 502

    return jsonify({
        "document_id": new_document.id,
        "status": "uploading",
        "duplicate": False,
        "upload_url": upload_url,
        "storage_path": storage_path,
    }), 201


@app.route("/documents/<int:document_id>/uploaded", methods=["POST"])
@require_csrf
def confirm_document_uploaded(document_id):
    """
    Called by the client once the direct-to-Supabase upload finishes.
    Verifies the object actually landed in storage before trusting the
    client's word for it, then advances both the Document and its shared
    DocumentContent into "processing". Actual extraction/AI generation is
    handled by a later pipeline chunk, not this endpoint.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    document = db.session.get(Document, document_id)
    if not document or document.user_id != user_id:
        return jsonify({"error": "Document not found"}), 404

    if document.status != "uploading":
        return jsonify({"error": f"Document is not awaiting upload (status: {document.status})"}), 400

    content = db.session.get(DocumentContent, document.document_content_id)
    if not content:
        return jsonify({"error": "Document content record missing"}), 500

    if not storage_object_exists("documents", content.storage_path):
        return jsonify({"error": "Upload not found in storage yet - please retry"}), 409

    document.status = "processing"
    should_process = content.status == "pending"
    if should_process:
        content.status = "processing"
    db.session.commit()

    if should_process:
        document_pipeline.start_processing(content.id, app)

    return jsonify({"status": "processing"})


@app.route("/documents")
def list_documents():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    documents = (
        Document.query.filter_by(user_id=user_id, is_removed=False)
        .order_by(Document.created_at.desc())
        .all()
    )

    result = []
    for d in documents:
        content = db.session.get(DocumentContent, d.document_content_id) if d.document_content_id else None
        # Once past "uploading", status tracks the shared DocumentContent
        # live - document_pipeline.py updates content.status in the
        # background, not this row, and several Document rows can share
        # one DocumentContent.
        effective_status = content.status if (content and d.status != "uploading") else d.status
        result.append({
            "id": d.id,
            "title": d.title,
            "status": effective_status,
            "file_type": content.file_type if content else None,
            "page_count": content.page_count if content else None,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        })

    return jsonify({"documents": result})


@app.route("/documents/<int:document_id>")
def get_document(document_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    document = db.session.get(Document, document_id)
    if not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404

    content = db.session.get(DocumentContent, document.document_content_id) if document.document_content_id else None

    # Once past "uploading", status tracks the shared DocumentContent live -
    # document_pipeline.py updates content.status in the background, not
    # this row.
    effective_status = content.status if (content and document.status != "uploading") else document.status

    view_url = None
    # Published readers use the native page renderer instead of receiving a
    # signed URL to the original private file. Owners retain the existing
    # signed view URL for backwards-compatible document access.
    if content and content.status == "ready" and document.user_id == user_id:
        view_url = get_signed_url(content.storage_path, bucket="documents")

    materials = []
    if content:
        material_query = GeneratedMaterial.query.filter_by(
            document_content_id=content.id,
            status="ready",
            generation_version="v2",
        )
        if document.user_id == user_id:
            # Never expose another student's private artifact just because
            # DocumentContent is deduplicated across identical uploads.
            material_query = material_query.filter(
                db.or_(
                    GeneratedMaterial.scope == "shared",
                    db.and_(
                        GeneratedMaterial.scope == "private",
                        GeneratedMaterial.owner_user_id == user_id,
                    ),
                )
            )
        else:
            material_query = material_query.filter(
                GeneratedMaterial.scope == "shared",
                GeneratedMaterial.owner_user_id.is_(None),
            )
        materials = [
            {
                "id": m.id,
                "type": m.material_type,
                "status": m.status,
                "parameters": m.generation_parameters or {},
            }
            for m in material_query.order_by(GeneratedMaterial.updated_at.desc()).all()
        ]

    return jsonify({
        "id": document.id,
        "title": document.title,
        "original_filename": document.original_filename,
        "status": effective_status,
        "file_type": content.file_type if content else None,
        "file_size_bytes": content.file_size_bytes if content else None,
        "content_hash": content.content_hash if content else None,
        "page_count": content.page_count if content else None,
        "error_message": content.error_message if (content and effective_status == "failed") else None,
        "view_url": view_url,
        "materials": materials,
        "created_at": document.created_at.isoformat() if document.created_at else None,
    })


@app.route("/documents/<int:document_id>/materials/<int:material_id>", methods=["GET"])
@login_required
def get_generated_material(document_id, material_id):
    """Return one exact ready artifact the current student is allowed to replay."""
    user_id = session.get("user_id")
    document = db.session.get(Document, document_id)
    if not user_id or not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404
    if not document.document_content_id:
        return jsonify({"error": "Document has no generated material"}), 404

    material = db.session.get(GeneratedMaterial, material_id)
    if not material or material.status != "ready" or not material.payload:
        return jsonify({"error": "Study material not found"}), 404
    if material.document_content_id != document.document_content_id:
        return jsonify({"error": "Study material not found"}), 404

    if material.scope == "private":
        if material.owner_user_id != user_id or document.user_id != user_id:
            return jsonify({"error": "Study material not found"}), 404
    elif material.scope == "shared":
        if material.owner_user_id is not None:
            return jsonify({"error": "Study material not found"}), 404
        if not _can_study_document(user_id, document):
            return jsonify({"error": "Study material not found"}), 404
    else:
        return jsonify({"error": "Study material not found"}), 404

    return jsonify({
        "material_id": material.id,
        "type": material.material_type,
        "status": material.status,
        "parameters": material.generation_parameters or {},
        "payload": json.loads(material.payload),
    }), 200


def _approved_library_publication(document):
    """Return the approved Library publication for a document, if public."""
    if not document or document.is_removed:
        return None
    return LibraryPublication.query.filter_by(
        document_id=document.id,
        status="approved",
    ).first()


def _can_study_document(user_id, document):
    if not document or document.is_removed:
        return False
    if document.user_id == user_id:
        return True
    return bool(_approved_library_publication(document))





def _can_publish_document(user_id, document):
    """Publishing is an ownership action, not merely a study permission."""
    return bool(
        document
        and not document.is_removed
        and document.user_id == user_id
    )

def _document_reader_watermark(user_id, document):
    """Resolve a reader watermark without leaking a student's email publicly.

    Private StudyHub documents retain the existing viewer-specific email
    watermark. Once a document has an approved Library publication, the
    public reader always uses Prepza attribution instead, including when the
    publisher is viewing their own published document.
    """
    if _approved_library_publication(document):
        return "SOURCED FROM PREPZA"

    viewer = db.session.get(User, user_id)
    return viewer.email if viewer and viewer.email else "Prepza"


def _get_studyable_document(user_id, document_id):
    document = db.session.get(Document, document_id)
    if not _can_study_document(user_id, document): return None
    content = db.session.get(DocumentContent, document.document_content_id) if document.document_content_id else None
    if not content or content.status != "ready": return None
    return document, content


@app.route("/documents/<int:document_id>/reading", methods=["GET"])
def get_document_reading(document_id):
    user_id = session.get("user_id")
    if not user_id: return jsonify({"error": "Not logged in"}), 401
    pair = _get_studyable_document(user_id, document_id)
    if not pair: return jsonify({"error": "Document not found"}), 404
    document, content = pair
    progress = DocumentReadingProgress.query.filter_by(user_id=user_id, document_id=document.id).first()
    page_num = progress.page_num if progress else 0
    max_page = max(0, (content.page_count or 1) - 1)
    return jsonify({"document_id": document.id, "page_num": min(max(0, page_num), max_page), "page_count": content.page_count})


@app.route("/documents/<int:document_id>/reading", methods=["POST"])
@require_csrf
def save_document_reading(document_id):
    user_id = session.get("user_id")
    if not user_id: return jsonify({"error": "Not logged in"}), 401
    pair = _get_studyable_document(user_id, document_id)
    if not pair: return jsonify({"error": "Document not found"}), 404
    document, content = pair
    data = request.get_json(silent=True) or {}
    page_num = data.get("page_num")
    if not isinstance(page_num, int) or isinstance(page_num, bool) or page_num < 0: return jsonify({"error": "page_num must be a non-negative integer"}), 400
    max_page = max(0, (content.page_count or 1) - 1)
    if page_num > max_page: return jsonify({"error": "page_num is outside the document"}), 400
    progress = DocumentReadingProgress.query.filter_by(user_id=user_id, document_id=document.id).first()
    if not progress: db.session.add(DocumentReadingProgress(user_id=user_id, document_id=document.id, page_num=page_num))
    else: progress.page_num = page_num
    db.session.commit()
    return jsonify({"ok": True, "page_num": page_num})


@app.route("/documents/<int:document_id>/reading/page/<int:page_num>")
def render_document_reading_page(document_id, page_num):
    user_id = session.get("user_id")
    if not user_id: return jsonify({"error": "Not logged in"}), 401
    pair = _get_studyable_document(user_id, document_id)
    if not pair: return jsonify({"error": "Document not found"}), 404
    document, content = pair
    if content.file_type != "pdf": return jsonify({"error": "Native reading currently supports PDF documents only"}), 415
    if page_num < 0 or content.page_count is None or page_num >= content.page_count: return jsonify({"error": "Page not found"}), 404
    file_bytes = fetch_private_file_bytes(content.storage_path, bucket="documents")
    if not file_bytes: return jsonify({"error": "Document file could not be loaded"}), 502
    watermark = _document_reader_watermark(user_id, document)
    try:
        image_bytes, _ = render_watermarked_page(file_bytes, page_num, watermark, zoom=1.6)
    except Exception:
        return jsonify({"error": "Document page could not be rendered"}), 500
    response = Response(image_bytes, mimetype="image/png")
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Content-Disposition"] = "inline"
    return response


@app.route("/documents/<int:document_id>", methods=["PATCH"])
@require_csrf
def rename_document(document_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    document = db.session.get(Document, document_id)
    if not document or document.user_id != user_id or document.is_removed:
        return jsonify({"error": "Document not found"}), 404

    data = request.get_json(silent=True)
    if not data or "title" not in data:
        return jsonify({"error": "title is required"}), 400

    title = (data.get("title") or "").strip()
    if not title or len(title) > 200:
        return jsonify({"error": "Title must be 1-200 characters"}), 400

    document.title = title
    db.session.commit()

    return jsonify({"id": document.id, "title": document.title})


@app.route("/documents/<int:document_id>", methods=["DELETE"])
@require_csrf
def delete_document(document_id):
    """
    Soft-deletes the student's personal Document row only. The underlying
    DocumentContent (its storage object and any generated materials) is
    left untouched, since other students' Document rows may point at the
    same deduplicated content. Real cleanup - deleting DocumentContent once
    zero Document rows reference it - belongs in a later chunk once that
    reference-counting can be done safely.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    document = db.session.get(Document, document_id)
    if not document or document.user_id != user_id:
        return jsonify({"error": "Document not found"}), 404

    document.is_removed = True
    db.session.commit()

    return jsonify({"message": "Document removed"})


@app.route("/documents/<int:document_id>/report", methods=["POST"])
@require_csrf
def report_document(document_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    document = db.session.get(Document, document_id)
    if not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    allowed_reasons = {
        "inaccurate_content", "plagiarised_material",
        "inappropriate_content", "copyright_violation", "other",
    }
    if reason not in allowed_reasons:
        return jsonify({"error": "Invalid report reason"}), 400

    document.reported_at = datetime.utcnow()
    document.report_reason = reason
    db.session.commit()

    return jsonify({"message": "Report submitted"})


def _published_ready_material_for_viewer(user_id, document, material_type, parameters):
    '''Return an approved document's READY shared artifact without generation.'''
    if not document or document.user_id == user_id:
        return None
    if not _can_study_document(user_id, document):
        return None
    if not document.document_content_id:
        return None
    content = db.session.get(DocumentContent, document.document_content_id)
    if not content or content.status != "ready":
        return None
    from ai_artifact_fingerprint import GENERATION_VERSION, build_generation_fingerprint
    from ai_reusable_generation import PROMPT_VERSIONS, SCHEMA_VERSIONS, normalize_parameters
    try:
        normalized = normalize_parameters(material_type, parameters)
        fingerprint = build_generation_fingerprint(
            content_hash=content.content_hash,
            material_type=material_type,
            parameters=normalized,
            prompt_version=PROMPT_VERSIONS[material_type],
            schema_version=SCHEMA_VERSIONS[material_type],
            scope="shared",
            owner_user_id=None,
        )
    except (KeyError, ValueError):
        return None
    material = GeneratedMaterial.query.filter_by(
        generation_fingerprint=fingerprint,
        document_content_id=content.id,
        material_type=material_type,
        status="ready",
        scope="shared",
        owner_user_id=None,
        generation_version=GENERATION_VERSION,
    ).first()
    if not material or not material.payload:
        return None
    return content, material

def _published_material_response(user_id, content, material):
    # Opening or replaying a generated material is not itself study time.
    # Actual study activity is recorded by the reading/review/audio flows.
    return {
        "material_id": material.id,
        "reused": True,
        "payload": json.loads(material.payload),
    }

def _requested_generated_material(user_id, document, material_id, material_type):
    """Resolve one exact ready artifact without falling back to another variant."""
    try:
        requested_id = int(material_id)
    except (TypeError, ValueError):
        return None
    material = db.session.get(GeneratedMaterial, requested_id)
    if not material or material.document_content_id != document.document_content_id:
        return None
    if material.material_type != material_type or material.status != "ready" or not material.payload:
        return None
    if document.user_id == user_id:
        if material.scope == "private" and material.owner_user_id != user_id:
            return None
        if material.scope not in ("private", "shared"):
            return None
    elif not (material.scope == "shared" and material.owner_user_id is None):
        return None
    return material


def _ai_generation_parameters_from_request():
    """Return an AI generation parameter object without coercing invalid JSON shapes."""
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("AI generation parameters must be an object")
    return data

@app.route("/documents/<int:document_id>/summarize", methods=["POST"])
@limiter.limit(
    "200 per hour",
    key_func=lambda: f"summarize:{session.get('user_id', get_remote_address())}",
)
@require_csrf


def summarize_document(document_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    document = db.session.get(Document, document_id)
    if not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404
    if not document.document_content_id:
        return jsonify({"error": "Document has no content to summarize"}), 400
    if document.user_id != user_id:
        shared = _published_ready_material_for_viewer(user_id, document, "summary", _ai_generation_parameters_from_request())
        if not shared:
            return jsonify({"error": "Published summary has not been generated yet"}), 404
        content, material = shared
        result = _published_material_response(user_id, content, material)
        return jsonify({"material_id": result["material_id"], "reused": True, "summary": result["payload"]}), 200

    content = db.session.get(DocumentContent, document.document_content_id)
    if not content or content.status != "ready":
        return jsonify({"error": "Document is still processing - try again shortly"}), 400
    requested_material_id = request.headers.get("X-Prepza-Material-ID")
    if requested_material_id:
        exact = _requested_generated_material(user_id, document, requested_material_id, "summary")
        if not exact:
            return jsonify({"error": "The selected study material is no longer available"}), 404
        return jsonify({"material_id": exact.id, "reused": True, "summary": json.loads(exact.payload)}), 200
    parameters = _ai_generation_parameters_from_request()
    if request.headers.get("X-Prepza-Resolve-Generation") == "1":
        result = _resolve_material_generation("summary", content, user_id, parameters)
        return jsonify({"material_id": result["material_id"], "reused": result["reused"], "summary": result["payload"]}), 200
    job_id = _start_async_material_generation(
        document_content_id=content.id, user_id=user_id, feature="summary", parameters=parameters
    )
    return jsonify({"job_id": job_id, "status": "processing", "progress_percent": 5}), 202


@app.route("/documents/<int:document_id>/quiz", methods=["POST"])
@limiter.limit(
    "200 per hour",
    key_func=lambda: f"quiz:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def quiz_document(document_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    document = db.session.get(Document, document_id)
    if not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404
    if not document.document_content_id:
        return jsonify({"error": "Document has no content to quiz"}), 400
    if document.user_id != user_id:
        shared = _published_ready_material_for_viewer(user_id, document, "quiz", _ai_generation_parameters_from_request())
        if not shared:
            return jsonify({"error": "Published quiz has not been generated yet"}), 404
        content, material = shared
        result = _published_material_response(user_id, content, material)
        return jsonify({"material_id": result["material_id"], "reused": True, "quiz": result["payload"]}), 200

    content = db.session.get(DocumentContent, document.document_content_id)
    if not content or content.status != "ready":
        return jsonify({"error": "Document is still processing - try again shortly"}), 400
    requested_material_id = request.headers.get("X-Prepza-Material-ID")
    if requested_material_id:
        exact = _requested_generated_material(user_id, document, requested_material_id, "quiz")
        if not exact:
            return jsonify({"error": "The selected study material is no longer available"}), 404
        return jsonify({"material_id": exact.id, "reused": True, "quiz": json.loads(exact.payload)}), 200
    parameters = _ai_generation_parameters_from_request()
    if request.headers.get("X-Prepza-Resolve-Generation") == "1":
        result = _resolve_material_generation("quiz", content, user_id, parameters)
        return jsonify({"material_id": result["material_id"], "reused": result["reused"], "quiz": result["payload"]}), 200
    job_id = _start_async_material_generation(
        document_content_id=content.id, user_id=user_id, feature="quiz", parameters=parameters
    )
    return jsonify({"job_id": job_id, "status": "processing", "progress_percent": 5}), 202


@app.route("/documents/<int:document_id>/quiz/<int:material_id>/complete", methods=["POST"])
@limiter.limit(
    "30 per hour",
    key_func=lambda: f"quiz-complete:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def complete_quiz(document_id, material_id):
    """
    Records that a student finished a generated quiz (with whatever
    score, per the frontend's "+20 XP for any score" copy) and awards
    XP for it. Separate from quiz generation above - generating a quiz
    material and actually completing it are different events, and only
    completion should count toward XP / the Quiz Master achievement.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    document = db.session.get(Document, document_id)
    if not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404
    if not document or not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404
    if not document.document_content_id:
        return jsonify({"error": "Document has no content"}), 400

    material = db.session.get(GeneratedMaterial, material_id)
    if (
        not material
        or material.document_content_id != document.document_content_id
        or material.material_type != "quiz"
        or material.status != "ready"
    ):
        return jsonify({"error": "Quiz material not found"}), 404
    if document.user_id != user_id and (material.scope != "shared" or material.owner_user_id is not None):
        return jsonify({"error": "Quiz material not found"}), 404

    data = request.get_json(silent=True) or {}
    score_percent = data.get("score_percent")
    if score_percent is not None:
        if not isinstance(score_percent, int) or isinstance(score_percent, bool) or not (0 <= score_percent <= 100):
            return jsonify({"error": "score_percent must be an integer between 0 and 100"}), 400

    attempt = QuizAttempt(
        user_id=user_id,
        generated_material_id=material.id,
        document_content_id=material.document_content_id,
        score_percent=score_percent,
    )
    db.session.add(attempt)
    db.session.flush()  # assign attempt.id, used as the XpEvent related_id below

    award_xp(user_id, "quiz_completed", XP_QUIZ_COMPLETED, related_id=attempt.id)
    record_study_activity(user_id, document_content_id=material.document_content_id)
    newly_unlocked = check_and_unlock_achievements(user_id)
    db.session.commit()

    return jsonify({
        "attempt_id": attempt.id,
        "xp_awarded": XP_QUIZ_COMPLETED,
        "newly_unlocked_achievements": newly_unlocked,
    }), 201


@app.route("/documents/<int:document_id>/flashcards", methods=["POST"])
@limiter.limit(
    "200 per hour",
    key_func=lambda: f"flashcards:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def flashcards_document(document_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    document = db.session.get(Document, document_id)
    if not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404
    if not document.document_content_id:
        return jsonify({"error": "Document has no content to generate flashcards from"}), 400
    if document.user_id != user_id:
        shared = _published_ready_material_for_viewer(user_id, document, "flashcards", _ai_generation_parameters_from_request())
        if not shared:
            return jsonify({"error": "Published flashcards has not been generated yet"}), 404
        content, material = shared
        result = _published_material_response(user_id, content, material)
        return jsonify({"material_id": result["material_id"], "reused": True, "flashcards": result["payload"]}), 200

    content = db.session.get(DocumentContent, document.document_content_id)
    if not content or content.status != "ready":
        return jsonify({"error": "Document is still processing - try again shortly"}), 400
    requested_material_id = request.headers.get("X-Prepza-Material-ID")
    if requested_material_id:
        exact = _requested_generated_material(user_id, document, requested_material_id, "flashcards")
        if not exact:
            return jsonify({"error": "The selected study material is no longer available"}), 404
        return jsonify({"material_id": exact.id, "reused": True, "flashcards": json.loads(exact.payload)}), 200
    parameters = _ai_generation_parameters_from_request()
    if request.headers.get("X-Prepza-Resolve-Generation") == "1":
        result = _resolve_material_generation("flashcards", content, user_id, parameters)
        return jsonify({"material_id": result["material_id"], "reused": result["reused"], "flashcards": result["payload"]}), 200
    job_id = _start_async_material_generation(
        document_content_id=content.id, user_id=user_id, feature="flashcards", parameters=parameters
    )
    return jsonify({"job_id": job_id, "status": "processing", "progress_percent": 5}), 202


@app.route("/documents/<int:document_id>/flashcards/<int:material_id>/complete", methods=["POST"])
@limiter.limit(
    "30 per hour",
    key_func=lambda: f"flashcards-complete:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def complete_flashcards(document_id, material_id):
    """Records a completed flashcard review session. Same shape as
    complete_quiz() above."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    document = db.session.get(Document, document_id)
    if not document or not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404
    if not document.document_content_id:
        return jsonify({"error": "Document has no content"}), 400

    material = db.session.get(GeneratedMaterial, material_id)
    if (
        not material
        or material.document_content_id != document.document_content_id
        or material.material_type != "flashcards"
        or material.status != "ready"
    ):
        return jsonify({"error": "Flashcard material not found"}), 404
    if document.user_id != user_id and (material.scope != "shared" or material.owner_user_id is not None):
        return jsonify({"error": "Flashcard material not found"}), 404

    data = request.get_json(silent=True) or {}
    cards_reviewed = data.get("cards_reviewed")
    if cards_reviewed is not None:
        if not isinstance(cards_reviewed, int) or isinstance(cards_reviewed, bool) or cards_reviewed < 0:
            return jsonify({"error": "cards_reviewed must be a non-negative integer"}), 400

    session_row = FlashcardSession(
        user_id=user_id,
        generated_material_id=material.id,
        document_content_id=material.document_content_id,
        cards_reviewed=cards_reviewed,
    )
    db.session.add(session_row)
    db.session.flush()

    award_xp(user_id, "flashcards_completed", XP_FLASHCARDS_COMPLETED, related_id=session_row.id)
    record_study_activity(user_id, document_content_id=material.document_content_id)
    newly_unlocked = check_and_unlock_achievements(user_id)
    db.session.commit()

    return jsonify({
        "session_id": session_row.id,
        "xp_awarded": XP_FLASHCARDS_COMPLETED,
        "newly_unlocked_achievements": newly_unlocked,
    }), 201


@app.route("/documents/<int:document_id>/mind-map", methods=["POST"])
@limiter.limit(
    "20 per hour",
    key_func=lambda: f"mind-map:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def mind_map_document(document_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    document = db.session.get(Document, document_id)
    if not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404
    if not document.document_content_id:
        return jsonify({"error": "Document has no content to generate a mind map from"}), 400
    if document.user_id != user_id:
        shared = _published_ready_material_for_viewer(user_id, document, "mind_map", _ai_generation_parameters_from_request())
        if not shared:
            return jsonify({"error": "Published mind map has not been generated yet"}), 404
        content, material = shared
        result = _published_material_response(user_id, content, material)
        return jsonify({"material_id": result["material_id"], "reused": True, "mind_map": result["payload"]}), 200
    content = db.session.get(DocumentContent, document.document_content_id)
    if not content or content.status != "ready":
        return jsonify({"error": "Document is still processing - try again shortly"}), 400
    requested_material_id = request.headers.get("X-Prepza-Material-ID")
    if requested_material_id:
        exact = _requested_generated_material(user_id, document, requested_material_id, "mind_map")
        if not exact:
            return jsonify({"error": "The selected study material is no longer available"}), 404
        return jsonify({"material_id": exact.id, "reused": True, "mind_map": json.loads(exact.payload)}), 200
    parameters = _ai_generation_parameters_from_request()
    if request.headers.get("X-Prepza-Resolve-Generation") == "1":
        result = _resolve_material_generation("mind_map", content, user_id, parameters)
        return jsonify({"material_id": result["material_id"], "reused": result["reused"], "mind_map": result["payload"]}), 200
    job_id = _start_async_material_generation(
        document_content_id=content.id, user_id=user_id, feature="mind_map", parameters=parameters
    )
    return jsonify({"job_id": job_id, "status": "processing", "progress_percent": 5}), 202


@app.route("/documents/<int:document_id>/generation-progress", methods=["GET"])
@login_required
def generation_progress(document_id):
    """Return the latest generation job progress for a document.

    This is deliberately a read-only polling endpoint. The frontend can
    keep the generation request itself running while polling this endpoint,
    so the student gets live stage/percentage updates instead of a blank
    screen.
    """
    user_id = session.get("user_id")
    document = db.session.get(Document, document_id)
    if not user_id or not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404

    feature = (request.args.get("feature") or "").strip().lower()
    allowed_features = {"summary", "quiz", "flashcards", "mind_map", "podcast", "podcast_audio"}
    if feature not in allowed_features:
        return jsonify({"error": "Unsupported generation feature"}), 400

    job = (
        AiJob.query
        .filter_by(document_content_id=document.document_content_id, feature=feature, user_id=user_id)
        .order_by(AiJob.id.desc())
        .first()
    )
    if not job:
        return jsonify({
            "found": False,
            "status": "idle",
            "progress_percent": 0,
            "progress_stage": "waiting",
        }), 200

    return jsonify({
        "found": True,
        "job_id": job.id,
        "status": job.status,
        "progress_percent": max(0, min(100, int(job.progress_percent or 0))),
        "progress_stage": job.progress_stage or "working",
        "error_message": job.error_message if job.status == "failed" else None,
        "material_id": job.material_id,
    }), 200


@app.route("/documents/<int:document_id>/podcast-script", methods=["POST"])
@limiter.limit(
    "200 per hour",
    key_func=lambda: f"podcast-script:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def podcast_script_document(document_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    document = db.session.get(Document, document_id)
    if not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404
    if not document.document_content_id:
        return jsonify({"error": "Document has no content to generate a podcast from"}), 400
    content = db.session.get(DocumentContent, document.document_content_id)
    if not content or content.status != "ready":
        return jsonify({"error": "Document is still processing - try again shortly"}), 400
    if document.user_id != user_id:
        material = GeneratedMaterial.query.filter_by(
            document_content_id=document.document_content_id, material_type="podcast",
            status="ready", scope="shared", owner_user_id=None
        ).first()
        if not material or not material.payload:
            return jsonify({"error": "Podcast has not been published yet"}), 404
        return jsonify({"material_id": material.id, "reused": True, "podcast": json.loads(material.payload)}), 200
    requested_material_id = request.headers.get("X-Prepza-Material-ID")
    if requested_material_id:
        exact = _requested_generated_material(user_id, document, requested_material_id, "podcast")
        if not exact:
            return jsonify({"error": "The selected study material is no longer available"}), 404
        return jsonify({"material_id": exact.id, "reused": True, "podcast": json.loads(exact.payload)}), 200
    parameters = _ai_generation_parameters_from_request()
    if request.headers.get("X-Prepza-Resolve-Generation") == "1":
        result = _resolve_material_generation("podcast", content, user_id, parameters)
        return jsonify({"material_id": result["material_id"], "reused": result["reused"], "podcast": result["payload"]}), 200
    job_id = _start_async_material_generation(
        document_content_id=content.id, user_id=user_id, feature="podcast", parameters=parameters
    )
    return jsonify({"job_id": job_id, "status": "processing", "progress_percent": 5}), 202


@app.route("/documents/<int:document_id>/podcast-audio", methods=["POST"])
@limiter.limit(
    "10 per hour",
    key_func=lambda: f"podcast-audio:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def trigger_podcast_audio(document_id):
    """
    Kicks off background audio synthesis for an already-generated
    podcast script (see podcast_script_document above - a script must
    exist first). Fire-and-forget: returns immediately with
    audio_status='processing'; the frontend polls
    GET /documents/<id>/podcast-audio for completion, same pattern as
    document upload processing.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    document = db.session.get(Document, document_id)
    if not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404

    if not document.document_content_id:
        return jsonify({"error": "Document has no content to generate a podcast from"}), 400

    requested_material_id = request.args.get("material_id")
    if requested_material_id:
        material = _requested_generated_material(user_id, document, requested_material_id, "podcast")
    elif document.user_id == user_id:
        material = get_generated_material_for_user(
            document.document_content_id, "podcast", session.get("user_id")
        )
    else:
        material = GeneratedMaterial.query.filter_by(
            document_content_id=document.document_content_id,
            material_type="podcast",
            status="ready",
            scope="shared",
            owner_user_id=None,
        ).first()
    requested_material_id = request.args.get("material_id")
    if requested_material_id:
        exact = _requested_generated_material(user_id, document, requested_material_id, "podcast")
        if not exact:
            return jsonify({"error": "The selected podcast is no longer available"}), 404
        material = exact

    if not material or material.status != "ready" or not material.payload:
        return jsonify({"error": "Generate the podcast script first"}), 400

    envelope = json.loads(material.payload)
    audio_status = envelope.get("audio_status")

    if audio_status == "ready":
        return jsonify({"audio_status": "ready", "material_id": material.id}), 200
    if audio_status == "processing":
        return jsonify({"audio_status": "processing", "material_id": material.id}), 202

    if document.user_id != user_id:
        return jsonify({"error": "Podcast audio is not ready yet"}), 409

    # Create a hidden pending notification now. It is marked read so it
    # does not appear in the student's feed while generation is running.
    # podcast_audio finalizes this same row when the background job completes.
    notification = Notification(
        user_id=user_id,
        type="podcast_pending",
        title="Preparing your podcast",
        body="We'll let you know when your study podcast is ready.",
        related_type="document",
        related_id=material.id,
        is_read=True,
    )
    db.session.add(notification)
    db.session.flush()

    envelope["audio_status"] = "processing"
    material.payload = json.dumps(envelope)
    db.session.commit()

    podcast_audio.start_podcast_audio_processing(material.id, app, notification.id)

    return jsonify({"audio_status": "processing", "material_id": material.id}), 202


@app.route("/documents/<int:document_id>/podcast-audio")
def get_podcast_audio(document_id):
    """
    Polling endpoint for podcast audio synthesis status. Returns a
    short-lived signed URL once audio_status is 'ready', same
    get_signed_url() helper used for content items elsewhere in this
    file.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    document = db.session.get(Document, document_id)
    if not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404

    if document.user_id == user_id:
        material = get_generated_material_for_user(
            document.document_content_id, "podcast", session.get("user_id")
        )
    else:
        material = GeneratedMaterial.query.filter_by(
            document_content_id=document.document_content_id,
            material_type="podcast",
            status="ready",
            scope="shared",
            owner_user_id=None,
        ).first()
    if not material or not material.payload:
        return jsonify({"error": "No podcast generated for this document yet"}), 404

    envelope = json.loads(material.payload)
    audio_status = envelope.get("audio_status", "pending")

    audio_url = None
    if audio_status == "ready" and envelope.get("audio_storage_path"):
        audio_url = get_signed_url(envelope["audio_storage_path"], bucket="podcast-audio")

    latest_job = AiJob.query.filter_by(
        document_content_id=document.document_content_id,
        feature="podcast_audio",
    ).order_by(AiJob.created_at.desc()).first()
    return jsonify({
        "audio_status": audio_status,
        "audio_url": audio_url,
        "duration_seconds": envelope.get("duration_seconds"),
        "requested_duration_seconds": envelope.get("requested_duration_seconds"),
        "duration_verified": envelope.get("duration_verified", False),
        "progress_percent": int((latest_job.progress_percent if latest_job else (100 if audio_status == "ready" else 0)) or 0),
        "progress_stage": latest_job.progress_stage if latest_job else ("ready" if audio_status == "ready" else "queued"),
    })

@app.route("/podcasts")
def list_podcasts():
    """
    Cross-document podcast library for the current user. Previously
    missing entirely - Home's Study Podcasts strip and PodcastLibraryScreen
    were both mock as a result, since there was no way to list a student's
    generated podcasts without already knowing a specific document_id.

    One row per Document the student owns that has a ready podcast
    GeneratedMaterial row attached to its content. Sourced from the same
    GeneratedMaterial rows the per-document podcast-script/podcast-audio
    endpoints already use, so it can never disagree with them.

    Deliberately does NOT include a signed audio_url - that stays a
    per-document concern via GET /documents/<id>/podcast-audio, called by
    PodcastPlayerScreen only when the student actually opens an episode.
    Keeps this list cheap to call even as a student's podcast count grows.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    rows = (
        db.session.query(Document, GeneratedMaterial)
        .join(DocumentContent, Document.document_content_id == DocumentContent.id)
        .join(GeneratedMaterial, GeneratedMaterial.document_content_id == DocumentContent.id)
        .filter(
            Document.user_id == user_id,
            Document.is_removed.is_(False),
            GeneratedMaterial.material_type == "podcast",
            GeneratedMaterial.status == "ready",
            GeneratedMaterial.generation_version == "v2",
            db.or_(
                GeneratedMaterial.scope == "shared",
                db.and_(
                    GeneratedMaterial.scope == "private",
                    GeneratedMaterial.owner_user_id == user_id,
                ),
            ),
        )
        .order_by(GeneratedMaterial.updated_at.desc())
        .all()
    )

    podcasts = []
    for document, material in rows:
        envelope = json.loads(material.payload) if material.payload else {}
        podcasts.append({
            "document_id": document.id,
            "title": document.title,
            "audio_status": envelope.get("audio_status", "pending"),
            "duration_seconds": envelope.get("duration_seconds"),
            "created_at": material.created_at.isoformat() if material.created_at else None,
        })

    return jsonify({"podcasts": podcasts})


@app.route("/documents/<int:document_id>/mindmap", methods=["POST"])
@limiter.limit(
    "200 per hour",
    key_func=lambda: f"mindmap:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def mindmap_document(document_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    document = db.session.get(Document, document_id)
    if not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404
    if not document.document_content_id:
        return jsonify({"error": "Document has no content to generate a mind map from"}), 400
        if document.user_id != user_id:
        shared = _published_ready_material_for_viewer(user_id, document, "mind_map", _ai_generation_parameters_from_request())
        if not shared:
            return jsonify({"error": "Published mindmap has not been generated yet"}), 404
        content, material = shared
        result = _published_material_response(user_id, content, material)
        return jsonify({"material_id": result["material_id"], "reused": True, "mindmap": result["payload"]}), 200

    content = db.session.get(DocumentContent, document.document_content_id)
    if not content or content.status != "ready":
        return jsonify({"error": "Document is still processing - try again shortly"}), 400
    parameters = _ai_generation_parameters_from_request()
    if request.headers.get("X-Prepza-Resolve-Generation") == "1":
        result = _resolve_material_generation(mind_map, content, user_id, parameters)
        return jsonify({"material_id": result["material_id"], "reused": result["reused"], "mindmap": result["payload"]}), 200
    job_id = _start_async_material_generation(
        document_content_id=content.id, user_id=user_id, feature="mind_map", parameters=parameters
    )
    return jsonify({"job_id": job_id, "status": "processing", "progress_percent": 5}), 202


@app.route("/documents/<int:document_id>/tutor")
def get_tutor_conversation(document_id):
    """
    Fetches (or reports empty) the persistent tutor conversation for
    this student+document pair. Returns conversation_id: null and
    messages: [] if no conversation has started yet - the first
    POST to /documents/<id>/tutor/messages creates it. Doesn't gate on
    document status - resuming/viewing history is harmless even if the
    document is still processing, unlike actually sending a new message.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    document = db.session.get(Document, document_id)
    if not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404

    if not document.document_content_id:
        return jsonify({"error": "Document has no content to tutor on"}), 400

    conversation = TutorConversation.query.filter_by(
        user_id=user_id, document_content_id=document.document_content_id
    ).first()

    if not conversation:
        return jsonify({"conversation_id": None, "messages": []})

    messages = (
        TutorMessage.query.filter_by(conversation_id=conversation.id)
        .order_by(TutorMessage.created_at.asc())
        .all()
    )

    return jsonify({
        "conversation_id": conversation.id,
        "messages": [_serialize_tutor_message(m) for m in messages],
    })


@app.route("/documents/<int:document_id>/tutor/messages", methods=["POST"])
@limiter.limit(
    "60 per hour",
    key_func=lambda: f"tutor-message:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def send_tutor_message(document_id):
    """
    Sends one message to Ada and returns her reply. Creates the
    TutorConversation on first message if it doesn't exist yet (get-
    or-create keyed on the same (user_id, document_content_id) pair
    the model's own unique constraint enforces).

    This route-level "60 per hour" throttle is deliberately SEPARATE
    from ai_service.check_daily_tutor_limit()'s daily cap - this one
    guards against rapid-fire spam within a short window, the daily
    cap guards total cost/day. Both apply independently, same layering
    other rate-limited AI routes in this file already use.

    ai_service.generate_tutor_reply() enforces the spend cap / daily
    rate limit / message persistence - this route just resolves the
    conversation and translates exceptions to HTTP responses, same
    shape as every other AI route in this file.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    document = db.session.get(Document, document_id)
    if not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404

    if not document.document_content_id:
        return jsonify({"error": "Document has no content to tutor on"}), 400

    content = db.session.get(DocumentContent, document.document_content_id)
    if not content or content.status != "ready":
        return jsonify({"error": "Document is still processing - try again shortly"}), 400

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    body = (data.get("body") or "").strip()
    if not body or len(body) > TUTOR_MESSAGE_MAX:
        return jsonify({"error": f"Message is required and must be {TUTOR_MESSAGE_MAX} characters or fewer"}), 400

    conversation = TutorConversation.query.filter_by(
        user_id=user_id, document_content_id=content.id
    ).first()
    if not conversation:
        conversation = TutorConversation(user_id=user_id, document_content_id=content.id)
        db.session.add(conversation)
        db.session.commit()

    try:
        result = ai_service.generate_tutor_reply(
            conversation_id=conversation.id,
            user_message_text=body,
            triggering_user_id=user_id,
            plan_tier=get_ai_plan_tier(user_id),
        )
    except ai_service.AIBudgetExceededError as e:
        return jsonify({"error": str(e)}), 503
    except ai_service.AIRateLimitExceededError as e:
        return jsonify({"error": str(e)}), 429
    except ai_service.AIProviderError as e:
        return jsonify({"error": str(e)}), 502

    record_document_studied(user_id, content.id)
    db.session.commit()

    return jsonify({
        "conversation_id": conversation.id,
        "reply": {
            "id": result["tutor_message_id"],
            "role": "assistant",
            "content": result["reply_text"],
        },
        "concept": result["concept"],
    }), 201


@app.route("/documents/<int:document_id>/tutor", methods=["DELETE"])
@require_csrf
def reset_tutor_conversation(document_id):
    """
    Hard-deletes the TutorConversation (cascades to TutorMessage via
    the FK's ondelete="CASCADE") - "start fresh" is a real recurring
    need for a study tool, unlike forum posts where soft-delete/audit
    trail matters, so this is a real delete rather than an is_removed
    flag.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    document = db.session.get(Document, document_id)
    if not _can_study_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404

    if not document.document_content_id:
        return jsonify({"error": "Document has no content"}), 400

    conversation = TutorConversation.query.filter_by(
        user_id=user_id, document_content_id=document.document_content_id
    ).first()
    if not conversation:
        return jsonify({"message": "No conversation to reset"}), 200

    db.session.delete(conversation)
    db.session.commit()

    return jsonify({"message": "Tutor conversation reset"})


# ---------- Library (publishing) ----------

LIBRARY_MATERIAL_TYPES = {"lecture_notes", "past_paper", "summary", "other"}
LIBRARY_TITLE_MAX = 200
LIBRARY_DESCRIPTION_MAX = 1000
LIBRARY_ACTIVE_STATUSES = ("pending", "approved")


def _document_content_has_flagged_material(document_content_id):
    """Used at publish time - blocks submitting a document to the Library
    if any of its AI-generated materials are currently flagged."""
    if not document_content_id:
        return False
    return GeneratedMaterial.query.filter_by(
        document_content_id=document_content_id, is_flagged=True
    ).first() is not None


def _flagged_document_ids():
    """
    Document ids whose underlying DocumentContent has at least one
    flagged GeneratedMaterial - computed as plain Python lists rather
    than a SQL subquery/join, same SQLAlchemy-version-safety reasoning
    as the moderation queue's Python-side priority sort elsewhere in
    this file. Used to keep already-published items out of Library
    browse/saved views without touching LibraryPublication's own status
    machine. Publication volume is small enough that this costs nothing.
    """
    flagged_content_ids = [
        row[0] for row in
        db.session.query(GeneratedMaterial.document_content_id)
        .filter(GeneratedMaterial.is_flagged.is_(True))
        .distinct()
        .all()
    ]
    if not flagged_content_ids:
        return []
    return [
        row[0] for row in
        db.session.query(Document.id)
        .filter(Document.document_content_id.in_(flagged_content_ids))
        .all()
    ]


@app.route("/library/publish", methods=["POST"])
@require_csrf
def publish_document():
    """
    Submits a student's own Document to the public Library for admin
    review. Only one active (pending or approved) publication is allowed
    per document - if a prior submission was rejected, this creates a
    fresh row rather than reviving the old one, keeping submission
    history intact.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    document_id = data.get("document_id")
    title = (data.get("title") or "").strip()
    description = data.get("description")
    material_type = (data.get("material_type") or "").strip()
    unit_id = data.get("unit_id")

    if not document_id:
        return jsonify({"error": "document_id is required"}), 400

    document = db.session.get(Document, document_id)
    if not _can_publish_document(user_id, document):
        return jsonify({"error": "Document not found"}), 404
    if document.status != "ready":
        return jsonify({"error": f"Document is not ready to publish (status: {document.status})"}), 400

    if not title or len(title) > LIBRARY_TITLE_MAX:
        return jsonify({"error": f"Title is required and must be {LIBRARY_TITLE_MAX} characters or fewer"}), 400

    if description is not None:
        if not isinstance(description, str):
            return jsonify({"error": "description must be a string"}), 400
        description = description.strip() or None
        if description and len(description) > LIBRARY_DESCRIPTION_MAX:
            return jsonify({"error": f"description must be {LIBRARY_DESCRIPTION_MAX} characters or fewer"}), 400

    if material_type not in LIBRARY_MATERIAL_TYPES:
        return jsonify({"error": "material_type must be one of: " + ", ".join(sorted(LIBRARY_MATERIAL_TYPES))}), 400

    if unit_id is not None:
        if not db.session.get(Unit, unit_id):
            return jsonify({"error": "Unit not found"}), 404

    if _document_content_has_flagged_material(document.document_content_id):
        return jsonify({
            "error": "This document can't be published right now - one of its AI-generated "
                     "materials has been flagged for review"
        }), 400

    # Library publishing is content-addressed, not name/document-row addressed.
    # Multiple student Document rows may point at the same DocumentContent, but
    # the same underlying bytes must never become multiple active library copies.
    existing_active = (
        LibraryPublication.query
        .join(Document, LibraryPublication.document_id == Document.id)
        .filter(
            Document.document_content_id == document.document_content_id,
            LibraryPublication.status.in_(LIBRARY_ACTIVE_STATUSES),
        )
        .first()
    )
    if existing_active:
        # The content is already represented in the Library. Do not create
        # another publication row or duplicate storage. A duplicate publish
        # attempt is a successful no-op from the student's perspective.
        return jsonify({
            "published": False,
            "duplicate": True,
            "message": "Thank you for publishing. This document is already in the Library.",
        }), 200

    publication = LibraryPublication(
        document_id=document_id,
        user_id=user_id,
        unit_id=unit_id,
        title=title,
        description=description,
        material_type=material_type,
        status="pending",
    )
    db.session.add(publication)
    db.session.commit()

    return jsonify({
        "publication_id": publication.id,
        "status": publication.status,
    }), 201


@app.route("/library/my-submissions")
def my_library_submissions():
    """
    Lists the logged-in student's own Library submissions, any status
    (pending/approved/rejected/removed) - powers the "review" tab on
    PublishLibraryScreen so a student can track where each one stands.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    publications = (
        LibraryPublication.query.filter_by(user_id=user_id)
        .order_by(LibraryPublication.created_at.desc())
        .all()
    )

    result = []
    for pub in publications:
        unit = db.session.get(Unit, pub.unit_id) if pub.unit_id else None
        result.append({
            "id": pub.id,
            "document_id": pub.document_id,
            "title": pub.title,
            "description": pub.description,
            "material_type": pub.material_type,
            "unit_id": pub.unit_id,
            "unit_code": unit.code if unit else None,
            "status": pub.status,
            "rejection_reason": pub.rejection_reason,
            "view_count": pub.view_count,
            "save_count": pub.save_count,
            "created_at": pub.created_at.isoformat() if pub.created_at else None,
            "updated_at": pub.updated_at.isoformat() if pub.updated_at else None,
        })

    return jsonify({"submissions": result})


@app.route("/library")
def browse_library():
    """
    Browse/search approved Library publications. Login required (same
    pattern as other content routes) but not tied to the viewer's own
    year/semester - any student can browse any unit's published material,
    matching the "any student, any university" product direction.

    Query params (all optional):
      q            - substring match against title
      unit_id      - filter to one unit
      university_id - filter to units belonging to one university
      material_type - lecture_notes | past_paper | summary | other
      page         - 1-indexed, 20 per page
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    query = LibraryPublication.query.filter_by(status="approved")
    flagged_document_ids = _flagged_document_ids()
    if flagged_document_ids:
        query = query.filter(~LibraryPublication.document_id.in_(flagged_document_ids))

    q = (request.args.get("q") or "").strip()
    if q:
        query = query.filter(LibraryPublication.title.ilike(f"%{q}%"))

    unit_id = request.args.get("unit_id", type=int)
    if unit_id:
        query = query.filter(LibraryPublication.unit_id == unit_id)

    university_id = request.args.get("university_id", type=int)
    if university_id:
        query = query.join(Unit, LibraryPublication.unit_id == Unit.id).filter(
            Unit.university_id == university_id
        )

    material_type = request.args.get("material_type")
    if material_type:
        if material_type not in LIBRARY_MATERIAL_TYPES:
            return jsonify({"error": "material_type must be one of: " + ", ".join(sorted(LIBRARY_MATERIAL_TYPES))}), 400
        query = query.filter(LibraryPublication.material_type == material_type)

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 20

    sort = request.args.get("sort")
    order_col = LibraryPublication.view_count.desc() if sort == "trending" else LibraryPublication.created_at.desc()

    publications = (
        query.order_by(order_col)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    result = []
    for pub in publications:
        unit = db.session.get(Unit, pub.unit_id) if pub.unit_id else None
        author = db.session.get(User, pub.user_id)
        result.append({
            "id": pub.id,
            "document_id": pub.document_id,
            "title": pub.title,
            "description": pub.description,
            "material_type": pub.material_type,
            "unit_id": pub.unit_id,
            "unit_code": unit.code if unit else None,
            "author": _display_name(author) if author else "Deleted user",
            "view_count": pub.view_count,
            "save_count": pub.save_count,
            "created_at": pub.created_at.isoformat() if pub.created_at else None,
        })

    return jsonify({"page": page, "publications": result})


def _ensure_studyhub_document_for_publication(user_id, publication):
    """Attach an approved Library publication to the student's StudyHub.

    The underlying DocumentContent remains shared/deduplicated. The student
    receives their own Document row, so title/delete/read-progress state is
    personal and cannot mutate the publisher's Document row.
    """
    source = db.session.get(Document, publication.document_id)
    if not source or source.is_removed or not source.document_content_id:
        return None

    content = db.session.get(DocumentContent, source.document_content_id)
    if not content or content.status != "ready":
        return None

    existing = Document.query.filter_by(
        user_id=user_id,
        document_content_id=content.id,
        is_removed=False,
    ).first()
    if existing:
        return existing

    removed = Document.query.filter_by(
        user_id=user_id,
        document_content_id=content.id,
        is_removed=True,
    ).first()
    if removed:
        removed.is_removed = False
        removed.title = publication.title
        removed.original_filename = source.original_filename
        removed.status = "ready"
        return removed

    return Document(
        user_id=user_id,
        document_content_id=content.id,
        title=publication.title,
        original_filename=source.original_filename,
        status="ready",
    )


@app.route("/library/<int:publication_id>/save", methods=["POST"])
@require_csrf
def save_library_item(publication_id):
    """Save an approved Library item and make it available in StudyHub.

    Saving is idempotent. The first save creates/reuses a personal Document
    row pointing at the same deduplicated DocumentContent; repeated saves do
    not create duplicate StudyHub rows or increment save_count again.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    publication = db.session.get(LibraryPublication, publication_id)
    if not publication or publication.status != "approved":
        return jsonify({"error": "Library item not found"}), 404

    source = db.session.get(Document, publication.document_id)
    if not source or source.is_removed or not source.document_content_id:
        return jsonify({"error": "Library document is not ready"}), 409
    if _document_content_has_flagged_material(source.document_content_id):
        return jsonify({"error": "Library item is currently unavailable"}), 404

    existing_studyhub_document = Document.query.filter_by(
        user_id=user_id,
        document_content_id=source.document_content_id,
        is_removed=False,
    ).order_by(Document.id.asc()).first()
    already_in_studyhub = existing_studyhub_document is not None

    studyhub_document = _ensure_studyhub_document_for_publication(user_id, publication)
    if not studyhub_document:
        return jsonify({"error": "Library document is not ready"}), 409

    existing = SavedLibraryMaterial.query.filter_by(
        user_id=user_id, library_publication_id=publication_id
    ).first()
    if not existing:
        # Free students may save up to 3 Library documents. Plus/Pro get the
        # premium Library entitlement. Enforce this server-side; never trust
        # the frontend's plan display for an access decision.
        subscription = get_user_subscription_status(user_id)
        if not subscription["is_active"]:
            saved_count = SavedLibraryMaterial.query.filter_by(user_id=user_id).count()
            if saved_count >= 3:
                return jsonify({
                    "error": "Free plan Library limit reached. Upgrade to Plus or Pro for premium Library access."
                }), 403
    if existing:
        # A legacy SavedLibraryMaterial row may predate the StudyHub-document
        # guarantee. In that case _ensure_studyhub_document_for_publication
        # returns a new, transient Document that must be persisted here.
        if studyhub_document.id is None:
            db.session.add(studyhub_document)
            db.session.flush()
        db.session.commit()
        return jsonify({
            "message": "This document is already in your Study Hub. No download was needed.",
            "document_id": studyhub_document.id,
            "in_studyhub": True,
            "already_in_studyhub": True,
            "save_count": publication.save_count,
        }), 200

    db.session.add(studyhub_document)
    db.session.flush()
    saved = SavedLibraryMaterial(user_id=user_id, library_publication_id=publication_id)
    db.session.add(saved)
    publication.save_count = (publication.save_count or 0) + 1
    try:
        db.session.commit()
    except IntegrityError:
        # A concurrent request may have won the SavedLibraryMaterial unique
        # constraint after both requests observed no existing save. Roll back
        # the losing transaction, then return the already-created StudyHub
        # document instead of surfacing a 500 or creating a second save count.
        db.session.rollback()
        saved_existing = SavedLibraryMaterial.query.filter_by(
            user_id=user_id, library_publication_id=publication_id
        ).first()
        if not saved_existing:
            raise
        winner_document = Document.query.filter_by(
            user_id=user_id,
            document_content_id=source.document_content_id,
            is_removed=False,
        ).order_by(Document.id.asc()).first()
        if not winner_document:
            return jsonify({"error": "Library save could not be completed"}), 409
        publication = db.session.get(LibraryPublication, publication_id)
        return jsonify({
            "message": "Already saved",
            "document_id": winner_document.id,
            "in_studyhub": True,
            "save_count": publication.save_count if publication else None,
        }), 200

    return jsonify({
        "message": (
            "This document is already in your Study Hub. No download was needed."
            if already_in_studyhub
            else "Saved to your Study Hub."
        ),
        "document_id": studyhub_document.id,
        "in_studyhub": True,
        "already_in_studyhub": already_in_studyhub,
        "save_count": publication.save_count,
    }), 200 if already_in_studyhub else 201

@app.route("/library/<int:publication_id>/save", methods=["DELETE"])
@require_csrf
def unsave_library_item(publication_id):
    """Removes the logged-in student's bookmark, if one exists."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    saved = SavedLibraryMaterial.query.filter_by(
        user_id=user_id, library_publication_id=publication_id
    ).first()
    if not saved:
        return jsonify({"message": "Not saved"}), 200

    publication = db.session.get(LibraryPublication, publication_id)
    db.session.delete(saved)
    if publication and publication.save_count > 0:
        publication.save_count -= 1
    db.session.commit()

    return jsonify({
        "message": "Removed",
        "save_count": publication.save_count if publication else None,
    })


@app.route("/library/saved")
def list_saved_library_items():
    """Lists the logged-in student's saved Library items (Saved tab)."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    saved_rows = (
        SavedLibraryMaterial.query.filter_by(user_id=user_id)
        .order_by(SavedLibraryMaterial.created_at.desc())
        .all()
    )
    flagged_document_ids = _flagged_document_ids()

    result = []
    for saved in saved_rows:
        pub = db.session.get(LibraryPublication, saved.library_publication_id)
        if not pub or pub.status != "approved":
            # Publication was later rejected/removed - skip rather than
            # error, so one bad row doesn't break the whole Saved tab.
            continue
        if pub.document_id in flagged_document_ids:
            # Underlying material was flagged after this was saved - hide
            # it the same way browse_library does, rather than error.
            continue
        unit = db.session.get(Unit, pub.unit_id) if pub.unit_id else None
        author = db.session.get(User, pub.user_id)
        result.append({
            "id": pub.id,
            "title": pub.title,
            "description": pub.description,
            "material_type": pub.material_type,
            "unit_id": pub.unit_id,
            "unit_code": unit.code if unit else None,
            "author": _display_name(author) if author else "Deleted user",
            "view_count": pub.view_count,
            "save_count": pub.save_count,
            "saved_at": saved.created_at.isoformat() if saved.created_at else None,
        })

    return jsonify({"saved": result})


LIBRARY_REPORT_REASONS = {
    "inaccurate_content", "plagiarised_material",
    "inappropriate_content", "copyright_violation", "other",
}
LIBRARY_REPORT_DETAILS_MAX = 500


@app.route("/library/<int:publication_id>/report", methods=["POST"])
@require_csrf
def report_library_item(publication_id):
    """
    Files a moderation report against a published Library item. No
    duplicate-report guard - a student can report the same item more
    than once (e.g. for a different reason); admins dedupe/dismiss on
    the review side rather than this endpoint silently dropping reports.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    publication = db.session.get(LibraryPublication, publication_id)
    if not publication or publication.status != "approved":
        return jsonify({"error": "Library item not found"}), 404

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if reason not in LIBRARY_REPORT_REASONS:
        return jsonify({"error": "Invalid report reason"}), 400

    details = data.get("details")
    if details is not None:
        details = details.strip()
        if len(details) > LIBRARY_REPORT_DETAILS_MAX:
            return jsonify({"error": f"details must be {LIBRARY_REPORT_DETAILS_MAX} characters or fewer"}), 400
        details = details or None

    report = LibraryReport(
        library_publication_id=publication_id,
        reporter_user_id=user_id,
        reason=reason,
        details=details,
        status="pending",
    )
    db.session.add(report)
    db.session.commit()

    return jsonify({"message": "Report submitted", "report_id": report.id}), 201


LIBRARY_XP_ON_APPROVAL = 50


@app.route("/admin/library/queue")
@require_admin
def admin_library_queue():
    """Lists pending Library publications for admin review, oldest first
    (first submitted, first reviewed)."""
    publications = (
        LibraryPublication.query.filter_by(status="pending")
        .order_by(LibraryPublication.created_at.asc())
        .all()
    )

    result = []
    for pub in publications:
        unit = db.session.get(Unit, pub.unit_id) if pub.unit_id else None
        author = db.session.get(User, pub.user_id)
        document = db.session.get(Document, pub.document_id)
        result.append({
            "id": pub.id,
            "document_id": pub.document_id,
            "title": pub.title,
            "description": pub.description,
            "material_type": pub.material_type,
            "unit_id": pub.unit_id,
            "unit_code": unit.code if unit else None,
            "author_email": author.email if author else None,
            "original_filename": document.original_filename if document else None,
            "created_at": pub.created_at.isoformat() if pub.created_at else None,
        })

    return jsonify({"queue": result})


@app.route("/admin/library/<int:publication_id>/approve", methods=["POST"])
@require_csrf
@require_admin
def admin_approve_library_item(publication_id):
    """
    Approves a pending publication and awards the submitter XP. XP award
    is idempotent via the XpEvent unique constraint on
    (user_id, event_type, related_id) - if this route is called twice for
    the same publication (retry, double-click), the second XpEvent insert
    is caught and skipped rather than double-awarding.
    """
    acting_admin_id = session.get("user_id")

    publication = db.session.get(LibraryPublication, publication_id)
    if not publication:
        return jsonify({"error": "Publication not found"}), 404
    if publication.status != "pending":
        return jsonify({"error": f"Publication is not pending (status: {publication.status})"}), 400

    publication.status = "approved"
    publication.reviewed_by = acting_admin_id
    publication.reviewed_at = datetime.utcnow()
    publication.rejection_reason = None

    xp_awarded_now = False
    if not publication.xp_awarded:
        xp_event = XpEvent(
            user_id=publication.user_id,
            event_type="library_publication_approved",
            xp_amount=LIBRARY_XP_ON_APPROVAL,
            related_id=publication.id,
        )
        db.session.add(xp_event)
        try:
            db.session.flush()
            publication.xp_awarded = True
            xp_awarded_now = True
        except IntegrityError:
            db.session.rollback()
            # Another request already awarded XP for this publication -
            # re-apply the approval fields (rolled back with the session)
            # and just skip the XP award this time.
            publication = db.session.get(LibraryPublication, publication_id)
            publication.status = "approved"
            publication.reviewed_by = acting_admin_id
            publication.reviewed_at = datetime.utcnow()
            publication.rejection_reason = None

    newly_unlocked = check_and_unlock_achievements(publication.user_id)
    db.session.commit()

    return jsonify({
        "id": publication.id,
        "status": publication.status,
        "xp_awarded_now": xp_awarded_now,
        "newly_unlocked_achievements": newly_unlocked,
    })


@app.route("/admin/library/<int:publication_id>/reject", methods=["POST"])
@require_csrf
@require_admin
def admin_reject_library_item(publication_id):
    """Rejects a pending publication with a required reason."""
    acting_admin_id = session.get("user_id")

    publication = db.session.get(LibraryPublication, publication_id)
    if not publication:
        return jsonify({"error": "Publication not found"}), 404
    if publication.status != "pending":
        return jsonify({"error": f"Publication is not pending (status: {publication.status})"}), 400

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason or len(reason) > 500:
        return jsonify({"error": "reason is required and must be 500 characters or fewer"}), 400

    publication.status = "rejected"
    publication.rejection_reason = reason
    publication.reviewed_by = acting_admin_id
    publication.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"id": publication.id, "status": publication.status})


@app.route("/admin/library/<int:publication_id>/remove", methods=["POST"])
@require_csrf
@require_admin
def admin_remove_library_item(publication_id):
    """
    Takedown for an already-approved publication (e.g. a reported item
    an admin has decided to act on) - the counterpart to reject, which
    only covers not-yet-approved submissions. Requires a reason, stored
    in the same rejection_reason column reject uses (kept generic
    rather than adding a parallel column for what is functionally the
    same "why did an admin act on this" note - same pattern as
    admin_remove_opportunity).
    """
    acting_admin_id = session.get("user_id")

    publication = db.session.get(LibraryPublication, publication_id)
    if not publication:
        return jsonify({"error": "Publication not found"}), 404
    if publication.status != "approved":
        return jsonify({"error": f"Can only remove an approved publication (status: {publication.status})"}), 400

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason or len(reason) > 500:
        return jsonify({"error": "reason is required and must be 500 characters or fewer"}), 400

    publication.status = "removed"
    publication.rejection_reason = reason
    publication.reviewed_by = acting_admin_id
    publication.reviewed_at = datetime.utcnow()
    log_admin_action(acting_admin_id, "library_publication_removed", target_type="library_publication", target_id=publication.id, details={"reason": reason})
    db.session.commit()

    return jsonify({"id": publication.id, "status": publication.status})


LIBRARY_REPORT_RESOLUTIONS = {"dismissed", "actioned"}
LIBRARY_REPORT_ADMIN_NOTES_MAX = 500


@app.route("/admin/library/reports")
@require_admin
def admin_list_library_reports():
    """
    Lists Library reports for the moderation queue. Defaults to pending
    only; pass status=all to see dismissed/actioned ones too.
    """
    status_filter = request.args.get("status", "pending")

    query = LibraryReport.query
    if status_filter != "all":
        query = query.filter_by(status=status_filter)

    reports = query.order_by(LibraryReport.created_at.asc()).all()

    result = []
    for report in reports:
        publication = db.session.get(LibraryPublication, report.library_publication_id)
        reporter = db.session.get(User, report.reporter_user_id)
        result.append({
            "id": report.id,
            "library_publication_id": report.library_publication_id,
            "publication_title": publication.title if publication else None,
            "publication_status": publication.status if publication else None,
            "reporter_email": reporter.email if reporter else None,
            "reason": report.reason,
            "details": report.details,
            "status": report.status,
            "admin_notes": report.admin_notes,
            "created_at": report.created_at.isoformat() if report.created_at else None,
        })

    return jsonify({"reports": result})


@app.route("/admin/library/reports/<int:report_id>/resolve", methods=["POST"])
@require_csrf
@require_admin
def admin_resolve_library_report(report_id):
    """
    Marks a report dismissed or actioned. Deliberately does NOT touch the
    underlying LibraryPublication's status - taking a publication down is
    a separate, explicit admin decision (existing reject/removal paths),
    not an automatic side effect of closing a report.
    """
    acting_admin_id = session.get("user_id")

    report = db.session.get(LibraryReport, report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    if report.status != "pending":
        return jsonify({"error": f"Report is not pending (status: {report.status})"}), 400

    data = request.get_json(silent=True) or {}
    resolution = (data.get("status") or "").strip()
    if resolution not in LIBRARY_REPORT_RESOLUTIONS:
        return jsonify({"error": "status must be one of: " + ", ".join(sorted(LIBRARY_REPORT_RESOLUTIONS))}), 400

    admin_notes = data.get("admin_notes")
    if admin_notes is not None:
        admin_notes = admin_notes.strip()
        if len(admin_notes) > LIBRARY_REPORT_ADMIN_NOTES_MAX:
            return jsonify({"error": f"admin_notes must be {LIBRARY_REPORT_ADMIN_NOTES_MAX} characters or fewer"}), 400
        admin_notes = admin_notes or None

    report.status = resolution
    report.admin_notes = admin_notes
    report.reviewed_by = acting_admin_id
    report.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"id": report.id, "status": report.status})


# ---------- Admin: content review (Chunk 10) ----------
# Flags an individual GeneratedMaterial row (not the Document, and not
# the LibraryPublication). A flagged material only affects the public
# Library - see _document_content_has_flagged_material() (blocks new
# publishes) and _flagged_document_ids() (hides already-published items)
# above. A student can still privately generate/study flagged material;
# this is a sharing gate, not an access gate.

CONTENT_MATERIAL_FLAG_REASON_MAX = 500


def _serialize_admin_content_material(material):
    content = db.session.get(DocumentContent, material.document_content_id)
    flagged_by_user = db.session.get(User, material.flagged_by) if material.flagged_by else None
    return {
        "id": material.id,
        "document_content_id": material.document_content_id,
        "material_type": material.material_type,
        "status": material.status,
        "file_type": content.file_type if content else None,
        "is_flagged": material.is_flagged,
        "flagged_reason": material.flagged_reason,
        "flagged_by_email": flagged_by_user.email if flagged_by_user else None,
        "flagged_at": material.flagged_at.isoformat() if material.flagged_at else None,
        "created_at": material.created_at.isoformat() if material.created_at else None,
    }


@app.route("/admin/content-materials")
@require_admin
def admin_list_content_materials():
    """
    Lists GeneratedMaterial rows for admin review. Defaults to flagged
    only; pass status=all to see everything. Newest first.
    """
    status_filter = request.args.get("status", "flagged")

    query = GeneratedMaterial.query
    if status_filter == "flagged":
        query = query.filter_by(is_flagged=True)
    elif status_filter != "all":
        return jsonify({"error": "status must be 'flagged' or 'all'"}), 400

    materials = query.order_by(GeneratedMaterial.created_at.desc()).limit(200).all()

    return jsonify({"materials": [_serialize_admin_content_material(m) for m in materials]})


@app.route("/admin/content-materials/<int:material_id>/flag", methods=["POST"])
@require_csrf
@require_admin
def admin_flag_content_material(material_id):
    """
    Flags a GeneratedMaterial row, requiring a reason. Idempotent -
    re-flagging an already-flagged row just updates the reason/admin
    rather than erroring, so an admin can amend a flag without an
    unflag/reflag round trip.
    """
    acting_admin_id = session.get("user_id")

    material = db.session.get(GeneratedMaterial, material_id)
    if not material:
        return jsonify({"error": "Material not found"}), 404

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason or len(reason) > CONTENT_MATERIAL_FLAG_REASON_MAX:
        return jsonify({
            "error": f"reason is required and must be {CONTENT_MATERIAL_FLAG_REASON_MAX} characters or fewer"
        }), 400

    material.is_flagged = True
    material.flagged_reason = reason
    material.flagged_by = acting_admin_id
    material.flagged_at = datetime.utcnow()
    log_admin_action(acting_admin_id, "content_material_flagged", target_type="generated_material", target_id=material.id, details={"reason": reason})
    db.session.commit()

    return jsonify(_serialize_admin_content_material(material))


@app.route("/admin/content-materials/<int:material_id>/unflag", methods=["POST"])
@require_csrf
@require_admin
def admin_unflag_content_material(material_id):
    material = db.session.get(GeneratedMaterial, material_id)
    if not material:
        return jsonify({"error": "Material not found"}), 404

    if not material.is_flagged:
        return jsonify({"message": "Not flagged"}), 200

    material.is_flagged = False
    material.flagged_reason = None
    material.flagged_by = None
    material.flagged_at = None
    log_admin_action(session.get("user_id"), "content_material_unflagged", target_type="generated_material", target_id=material.id)
    db.session.commit()

    return jsonify(_serialize_admin_content_material(material))


# ---------- XP / Achievements / Streaks (Chunk 7) ----------
#
# Fixed-value MVP: XP amounts and the achievement catalog are hardcoded
# constants below rather than admin-editable SystemSetting rows (unlike
# content prices) - that's a Phase 17 (Platform Controls) concern, not
# this chunk's. All awarding funnels through award_xp()/unlock_achievement(),
# which are idempotent the same way admin_approve_library_item already is:
# insert into a uniquely-constrained table, and treat IntegrityError as
# "already awarded" rather than an error.

XP_DOCUMENT_STUDIED = 15
XP_QUIZ_COMPLETED = 20
XP_FLASHCARDS_COMPLETED = 10
XP_COMMUNITY_HELPFUL_REPLY = 5
XP_LIBRARY_PUBLICATION_APPROVED = LIBRARY_XP_ON_APPROVAL  # defined earlier, kept as one source of truth
XP_STREAK_MILESTONES = {7: 50, 14: 100, 21: 150, 30: 200}

# Cumulative XP required to REACH a level: cumulative(L) = 75 * L * (L-1).
# Chosen so the curve lands on whole numbers and gives a natural ramp
# (Level 4 starts at 900 XP, Level 5 at 1500 XP, etc).
LEVEL_TITLES = {
    1: "Fresher", 2: "Learner", 3: "Achiever", 4: "Scholar", 5: "Sage",
    6: "Master", 7: "Luminary", 8: "Legend",
}
LEVEL_TITLE_FALLBACK = "Legend"


def _level_cumulative_xp(level):
    return 75 * level * (level - 1)


def get_level_info(xp_total):
    """
    Returns (level, title, xp_into_level, xp_needed_for_level_gap,
    next_level_xp_total) for a given lifetime XP total. The gap and
    "into level" figures are what the frontend's progress ring needs
    (xpTotal / xpNext in XPProgressScreen).
    """
    level = 1
    while _level_cumulative_xp(level + 1) <= xp_total:
        level += 1
    level_start = _level_cumulative_xp(level)
    next_level_xp = _level_cumulative_xp(level + 1)
    title = LEVEL_TITLES.get(level, LEVEL_TITLE_FALLBACK)
    return {
        "level": level,
        "title": title,
        "xp_total": xp_total,
        "xp_into_level": xp_total - level_start,
        "xp_for_level_gap": next_level_xp - level_start,
        "next_level_xp": next_level_xp,
    }


ACHIEVEMENT_DEFINITIONS = [
    {
        "code": "first_document", "icon": "📄", "name": "First Document",
        "desc": "Upload your first document",
        "check": lambda uid: min(1, Document.query.filter_by(user_id=uid, is_removed=False).count()),
        "total": 1,
    },
    {
        "code": "quiz_starter", "icon": "❓", "name": "Quiz Starter",
        "desc": "Complete your first quiz",
        "check": lambda uid: min(1, QuizAttempt.query.filter_by(user_id=uid).count()),
        "total": 1,
    },
    {
        "code": "streak_7", "icon": "🔥", "name": "7-Day Scholar",
        "desc": "Maintain a 7-day study streak",
        "check": lambda uid: min(7, _get_or_create_streak(uid).longest_streak),
        "total": 7,
    },
    {
        "code": "library_contributor", "icon": "📚", "name": "Library Contributor",
        "desc": "Get a material approved in the library",
        "check": lambda uid: min(1, LibraryPublication.query.filter_by(user_id=uid, status="approved").count()),
        "total": 1,
    },
    {
        "code": "quiz_master", "icon": "🧠", "name": "Quiz Master",
        "desc": "Complete 25 quizzes",
        "check": lambda uid: min(25, QuizAttempt.query.filter_by(user_id=uid).count()),
        "total": 25,
    },
    {
        "code": "flashcard_champ", "icon": "🃏", "name": "Flashcard Champ",
        "desc": "Complete 50 flashcard sessions",
        "check": lambda uid: min(50, FlashcardSession.query.filter_by(user_id=uid).count()),
        "total": 50,
    },
    {
        "code": "community_helper", "icon": "💬", "name": "Community Helper",
        "desc": "Receive 10 helpful votes on replies",
        "check": lambda uid: min(10, XpEvent.query.filter_by(user_id=uid, event_type="community_helpful_reply").count()),
        "total": 10,
    },
    {
        "code": "streak_30", "icon": "🔥", "name": "30-Day Master",
        "desc": "Maintain a 30-day study streak",
        "check": lambda uid: min(30, _get_or_create_streak(uid).longest_streak),
        "total": 30,
    },
]


def award_xp(user_id, event_type, xp_amount, related_id):
    """
    Idempotently awards XP. Returns True if this call actually granted
    XP, False if an XpEvent with this (user, event_type, related_id)
    already existed. Caller is responsible for choosing a related_id
    that's unique per legitimate award (e.g. a freshly-inserted row's
    own id for uncapped per-attempt events, or a shared sentinel for
    "once ever" events like streak milestones).
    """
    event = XpEvent(user_id=user_id, event_type=event_type, xp_amount=xp_amount, related_id=related_id)
    db.session.add(event)
    try:
        db.session.flush()
        return True
    except IntegrityError:
        db.session.rollback()
        return False


def _get_or_create_streak(user_id):
    streak = StudyStreak.query.filter_by(user_id=user_id).first()
    if not streak:
        streak = StudyStreak(user_id=user_id, current_streak=0, longest_streak=0, last_study_date=None)
        db.session.add(streak)
        db.session.flush()
    return streak


def record_study_activity(user_id, document_content_id=None):
    """
    Marks today as a study day for this user (and optionally this
    document), updates the running streak, and awards any newly-crossed
    streak milestone. Safe to call multiple times per day - the
    StudyActivityLog unique constraint no-ops repeats for the same
    (user, document, day), and the streak/milestone logic only advances
    on the FIRST qualifying activity of a new calendar day.
    Returns True if this was the first study activity logged today.
    """
    today = datetime.utcnow().date()

    log_row = StudyActivityLog(user_id=user_id, document_content_id=document_content_id, activity_date=today)
    db.session.add(log_row)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return False  # already logged this exact (user, document, day)

    # Was ANY activity already logged today (possibly for a different
    # document, or with document_content_id=None)? If so, the streak
    # itself was already advanced today - only the per-document XP cap
    # above needed the fresh row.
    already_active_today = StudyActivityLog.query.filter(
        StudyActivityLog.user_id == user_id,
        StudyActivityLog.activity_date == today,
        StudyActivityLog.id != log_row.id,
    ).first() is not None
    if already_active_today:
        return True

    streak = _get_or_create_streak(user_id)
    yesterday = today - timedelta(days=1)
    if streak.last_study_date == yesterday:
        streak.current_streak += 1
    elif streak.last_study_date == today:
        pass
    else:
        streak.current_streak = 1
    streak.longest_streak = max(streak.longest_streak, streak.current_streak)
    streak.last_study_date = today

    milestone_xp = XP_STREAK_MILESTONES.get(streak.current_streak)
    if milestone_xp:
        award_xp(user_id, "streak_milestone", milestone_xp, related_id=streak.current_streak)

    return True


def record_document_studied(user_id, document_content_id):
    """
    Rewards a document-study action only when the student has already
    accumulated meaningful study time on that document today. Generation
    itself is not enough to create or renew a streak.
    """
    today = datetime.utcnow().date()
    activity = StudyActivityLog.query.filter_by(
        user_id=user_id, document_content_id=document_content_id, activity_date=today,
    ).first()
    if not activity:
        return False

    event_related_id = activity.id
    award_xp(user_id, "document_studied", XP_DOCUMENT_STUDIED, related_id=event_related_id)
    check_and_unlock_achievements(user_id)
    return True

def _document_study_event_id(user_id, document_content_id):
    """
    XpEvent's uniqueness is (user, event_type, related_id) with no date
    column, so "once per document per day" can't be expressed with
    document_content_id alone (that would mean once per document EVER).
    We instead key off today's StudyActivityLog row for this exact
    (user, document, day), which is itself uniquely constrained -
    giving each new day its own related_id "for free".
    """
    today = datetime.utcnow().date()
    row = StudyActivityLog.query.filter_by(
        user_id=user_id, document_content_id=document_content_id, activity_date=today,
    ).first()
    return row.id if row else None


MAX_HEARTBEAT_INTERVAL_SECONDS = 30
MAX_STUDY_TIME_SECONDS_PER_DAY = 8 * 60 * 60  # anti-gaming ceiling, 8h/day


def record_study_time_heartbeat(user_id, feature="reading"):
    """
    Credits up to MAX_HEARTBEAT_INTERVAL_SECONDS for the gap since
    this user's last heartbeat today for this FEATURE, onto that
    feature's StudyTimeLog row for today (created on first heartbeat
    of the day for that feature). The very first heartbeat of a
    feature/day only sets the baseline timestamp and credits nothing,
    since there's no prior heartbeat to measure from.

    The 8h/day anti-gaming ceiling applies across ALL of this user's
    features combined for today, not per-feature - otherwise 8h
    reading + 8h quiz + 8h podcast would all separately be allowed in
    one day. Returns this user's total study time across all
    features today, in seconds.
    """
    today = datetime.utcnow().date()
    now = datetime.utcnow()

    row = StudyTimeLog.query.filter_by(user_id=user_id, activity_date=today, feature=feature).first()
    if not row:
        row = StudyTimeLog(user_id=user_id, activity_date=today, feature=feature, study_time_seconds=0)
        db.session.add(row)
        db.session.flush()

    if row.last_heartbeat_at is not None:
        elapsed = (now - row.last_heartbeat_at).total_seconds()
        credited = max(0, min(elapsed, MAX_HEARTBEAT_INTERVAL_SECONDS))
        total_today = db.session.query(
            db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0)
        ).filter(
            StudyTimeLog.user_id == user_id,
            StudyTimeLog.activity_date == today,
        ).scalar()
        room = max(0, MAX_STUDY_TIME_SECONDS_PER_DAY - total_today)
        row.study_time_seconds += int(min(credited, room))

    row.last_heartbeat_at = now

    return db.session.query(
        db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0)
    ).filter(
        StudyTimeLog.user_id == user_id,
        StudyTimeLog.activity_date == today,
    ).scalar()


def check_and_unlock_achievements(user_id):
    """
    Evaluates every achievement definition and unlocks any newly-earned
    ones. Cheap enough to call after every XP-earning action for MVP
    scale (each check is a single indexed COUNT query); revisit with
    caching/denormalized counters if this shows up in slow-query logs.
    Returns the list of achievement_codes newly unlocked this call.
    """
    already_unlocked = {
        row.achievement_code
        for row in UserAchievement.query.filter_by(user_id=user_id).all()
    }
    newly_unlocked = []
    for achievement in ACHIEVEMENT_DEFINITIONS:
        code = achievement["code"]
        if code in already_unlocked:
            continue
        progress = achievement["check"](user_id)
        if progress >= achievement["total"]:
            row = UserAchievement(user_id=user_id, achievement_code=code)
            db.session.add(row)
            try:
                db.session.flush()
                newly_unlocked.append(code)
            except IntegrityError:
                db.session.rollback()
    return newly_unlocked


XP_HISTORY_LABELS = {
    "document_studied": ("📄", "Studied a document"),
    "quiz_completed": ("❓", "Completed a quiz"),
    "flashcards_completed": ("🧠", "Completed flashcard set"),
    "streak_milestone": ("🔥", "Study streak milestone"),
    "library_publication_approved": ("📚", "Material approved in Library"),
    "community_helpful_reply": ("💬", "Helpful community reply"),
}

HOW_TO_EARN_XP = [
    {"label": "Study a document", "xp": f"+{XP_DOCUMENT_STUDIED} XP"},
    {"label": "Complete a quiz (any score)", "xp": f"+{XP_QUIZ_COMPLETED} XP"},
    {"label": "Complete flashcard set", "xp": f"+{XP_FLASHCARDS_COMPLETED} XP"},
    {"label": "Maintain 7-day streak", "xp": f"+{XP_STREAK_MILESTONES[7]} XP"},
    {"label": "Library material approved", "xp": f"+{XP_LIBRARY_PUBLICATION_APPROVED} XP"},
    {"label": "Helpful community reply", "xp": f"+{XP_COMMUNITY_HELPFUL_REPLY} XP"},
]


@app.route("/gamification/summary")
def gamification_summary():
    """
    Lightweight combined payload for surfaces that show XP/streak as
    small stat pills rather than the full detail screens - the Home
    streak banner and the Profile stat row (Streak / XP / Docs /
    Followers) in the current frontend.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    xp_total = db.session.query(func.coalesce(func.sum(XpEvent.xp_amount), 0)).filter(
        XpEvent.user_id == user_id
    ).scalar()
    level_info = get_level_info(xp_total)
    streak = _get_or_create_streak(user_id)
    db.session.commit()  # persist a lazily-created StudyStreak row, if any

    documents_count = Document.query.filter_by(user_id=user_id, is_removed=False).count()
    followers_count = Follow.query.filter_by(followed_id=user_id).count()

    return jsonify({
        "xp_total": xp_total,
        "level": level_info["level"],
        "level_title": level_info["title"],
        "current_streak": streak.current_streak,
        "longest_streak": streak.longest_streak,
        "documents_count": documents_count,
        "followers_count": followers_count,
    })


@app.route("/xp/progress")
def xp_progress():
    """Powers XPProgressScreen: the level ring, and a paginated feed of
    recent XP-earning events."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    xp_total = db.session.query(func.coalesce(func.sum(XpEvent.xp_amount), 0)).filter(
        XpEvent.user_id == user_id
    ).scalar()
    level_info = get_level_info(xp_total)

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 20

    events = (
        XpEvent.query.filter_by(user_id=user_id)
        .order_by(XpEvent.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    history = []
    for e in events:
        icon, label = XP_HISTORY_LABELS.get(e.event_type, ("⭐", e.event_type.replace("_", " ").title()))
        history.append({
            "icon": icon,
            "label": label,
            "xp": e.xp_amount,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })

    return jsonify({
        "level": level_info["level"],
        "level_title": level_info["title"],
        "xp_total": xp_total,
        "xp_into_level": level_info["xp_into_level"],
        "xp_for_level_gap": level_info["xp_for_level_gap"],
        "next_level_xp": level_info["next_level_xp"],
        "page": page,
        "history": history,
        "how_to_earn": HOW_TO_EARN_XP,
    })


STREAK_MILESTONE_LABELS = {7: "7-Day Scholar", 14: "14-Day Achiever", 21: "21-Day Legend", 30: "30-Day Master"}


@app.route("/profile/posts")
def profile_posts():
    """Return the authenticated student's real profile posts.
    The social-post composer is not enabled yet, so an empty result is
    preferable to fabricated demo content in a production profile."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    return jsonify({"posts": [], "composer_enabled": False})


@app.route("/streak")
def streak_detail():
    """Powers StudyStreakScreen: current/longest streak, a
    month-by-month activity calendar (GitHub-contributions style,
    navigable via ?month=YYYY-MM), and milestone progress."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    streak = _get_or_create_streak(user_id)
    db.session.commit()

    today = datetime.utcnow().date()

    month_param = request.args.get("month")
    view_first_day = None
    if month_param:
        try:
            y_str, m_str = month_param.split("-")
            view_first_day = datetime(int(y_str), int(m_str), 1).date()
        except (ValueError, TypeError):
            view_first_day = None
    if view_first_day is None:
        view_first_day = today.replace(day=1)

    if view_first_day.month == 12:
        next_month_first_day = view_first_day.replace(year=view_first_day.year + 1, month=1)
    else:
        next_month_first_day = view_first_day.replace(month=view_first_day.month + 1)
    view_last_day = next_month_first_day - timedelta(days=1)

    active_dates = {
        row.activity_date
        for row in StudyActivityLog.query.filter(
            StudyActivityLog.user_id == user_id,
            StudyActivityLog.activity_date >= view_first_day,
            StudyActivityLog.activity_date <= view_last_day,
        ).all()
    }

    # Per-day study duration (summed across all StudyTimeLog features)
    # for the viewed month, so the frontend can shade each calendar
    # tile by how long the student studied that day - GitHub-style
    # contribution intensity - rather than a flat studied/not-studied
    # boolean.
    study_seconds_by_date = dict(
        db.session.query(
            StudyTimeLog.activity_date,
            db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0),
        )
        .filter(
            StudyTimeLog.user_id == user_id,
            StudyTimeLog.activity_date >= view_first_day,
            StudyTimeLog.activity_date <= view_last_day,
        )
        .group_by(StudyTimeLog.activity_date)
        .all()
    )

    calendar = []
    num_days_in_month = (view_last_day - view_first_day).days + 1
    for i in range(num_days_in_month):
        day = view_first_day + timedelta(days=i)
        calendar.append({
            "date": day.isoformat(),
            "studied": day in active_dates,
            "is_future": day > today,
            "study_seconds": int(study_seconds_by_date.get(day, 0)),
        })

    # Bound backward navigation by account creation, not first study
    # activity - a brand-new account whose only activity is this month
    # would otherwise have earliest_month == calendar_month and
    # permanently disable the prev button on load. Matches GitHub's
    # own contribution calendar, which scrolls back through empty
    # months to account creation, not just to first contribution.
    user = db.session.get(User, user_id)
    account_created = user.created_at.date() if (user and user.created_at) else today
    earliest_month = account_created.strftime("%Y-%m")

    milestones = [
        {
            "days": days,
            "label": STREAK_MILESTONE_LABELS[days],
            "xp": f"+{xp} XP",
            "done": streak.longest_streak >= days,
        }
        for days, xp in sorted(XP_STREAK_MILESTONES.items())
    ]

    return jsonify({
        "current_streak": streak.current_streak,
        "longest_streak": streak.longest_streak,
        "calendar_month": view_first_day.strftime("%Y-%m"),
        "calendar_start_weekday": (view_first_day.weekday() + 1) % 7,  # 0=Sun..6=Sat to match S M T W T F S header
        "earliest_month": earliest_month,
        "calendar": calendar,
        "milestones": milestones,
    })


@app.route("/study-time/heartbeat", methods=["POST"])
@limiter.limit(
    "200 per hour",
    key_func=lambda: f"study-heartbeat:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def study_time_heartbeat():
    """
    Called by the client every ~20s while a document/summary is open
    and the tab is visible. Also marks today as a study day (streak)
    via record_study_activity() - reading is a legitimate study
    action - but awards no XP itself; only record_document_studied()
    (called from the generation routes) does that.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True) or {}
    feature = data.get("feature", "reading")
    if feature not in STUDY_TIME_FEATURES:
        return jsonify({"error": f"feature must be one of {sorted(STUDY_TIME_FEATURES)}"}), 400

    document_content_id = None
    document_id = data.get("document_id")
    if document_id is not None:
        if not isinstance(document_id, int) or isinstance(document_id, bool): return jsonify({"error": "document_id must be an integer"}), 400
        pair = _get_studyable_document(user_id, document_id)
        if not pair: return jsonify({"error": "Document not found"}), 404
        document_content_id = pair[1].id

    before_feature_seconds = int(db.session.query(
        db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0)
    ).filter(
        StudyTimeLog.user_id == user_id,
        StudyTimeLog.activity_date == datetime.utcnow().date(),
        StudyTimeLog.feature == feature,
    ).scalar() or 0)

    seconds_today = record_study_time_heartbeat(user_id, feature=feature)

    after_feature_seconds = int(db.session.query(
        db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0)
    ).filter(
        StudyTimeLog.user_id == user_id,
        StudyTimeLog.activity_date == datetime.utcnow().date(),
        StudyTimeLog.feature == feature,
    ).scalar() or 0)

    credited_this_heartbeat = max(0, after_feature_seconds - before_feature_seconds)
    # A visible session must accumulate at least one minute before it can
    # create/renew a study day. This prevents opening the app/document from
    # immediately starting a streak.
    if credited_this_heartbeat > 0 and document_content_id is not None:
        today = datetime.utcnow().date()
        existing = StudyActivityLog.query.filter_by(
            user_id=user_id, document_content_id=document_content_id, activity_date=today,
        ).first()
        feature_session_seconds = after_feature_seconds
        if existing is None and feature_session_seconds >= 60:
            record_study_activity(user_id, document_content_id=document_content_id)

    db.session.commit()
    return jsonify({
        "study_time_seconds_today": seconds_today,
        "credited_this_heartbeat": credited_this_heartbeat,
        "study_day_active": bool(document_content_id is not None and feature_session_seconds >= 60) if 'feature_session_seconds' in locals() else False,
    })


@app.route("/study-time")
def study_time_summary():
    """
    Powers TimeStudiedScreen. by_feature is not yet implemented -
    StudyTimeLog only tracks a daily total today, not a per-feature
    breakdown - so it's returned as an empty object rather than
    fabricated. See the patch script that added this route for why.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    period = request.args.get("period", "week")
    today = datetime.utcnow().date()
    if period == "day":
        start_date = today
    elif period == "month":
        start_date = today.replace(day=1)
    else:
        period = "week"
        start_date = today - timedelta(days=today.weekday())

    rows = db.session.query(
        StudyTimeLog.feature,
        db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0),
    ).filter(
        StudyTimeLog.user_id == user_id,
        StudyTimeLog.activity_date >= start_date,
        StudyTimeLog.activity_date <= today,
    ).group_by(StudyTimeLog.feature).all()

    by_feature = {feature: seconds for feature, seconds in rows}
    total_seconds = sum(by_feature.values())

    return jsonify({
        "period": period,
        "total_seconds": total_seconds,
        "by_feature": by_feature,
    })


@app.route("/achievements")
def list_achievements():
    """Powers AchievementsScreen: full catalog split into
    unlocked/in-progress, with progress counters for locked ones."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    unlocked_rows = {
        row.achievement_code: row.unlocked_at
        for row in UserAchievement.query.filter_by(user_id=user_id).all()
    }

    result = []
    for a in ACHIEVEMENT_DEFINITIONS:
        code = a["code"]
        is_done = code in unlocked_rows
        progress = a["total"] if is_done else a["check"](user_id)
        result.append({
            "code": code,
            "icon": a["icon"],
            "name": a["name"],
            "desc": a["desc"],
            "done": is_done,
            "unlocked_at": unlocked_rows[code].isoformat() if is_done else None,
            "progress": progress,
            "total": a["total"],
        })

    return jsonify({
        "unlocked_count": len(unlocked_rows),
        "total_count": len(ACHIEVEMENT_DEFINITIONS),
        "achievements": result,
    })


# ---------- Groups ----------

GROUP_NAME_MAX = 150
GROUP_DESCRIPTION_MAX = 1000
GROUP_PRIVACY_VALUES = {"public", "private", "course_only"}


def _serialize_group(group, membership=None):
    unit = db.session.get(Unit, group.unit_id) if group.unit_id else None
    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "privacy": group.privacy,
        "university_id": group.university_id,
        "program_id": group.program_id,
        "unit_id": group.unit_id,
        "unit_code": unit.code if unit else None,
        "year": group.year,
        "member_count": group.member_count,
        "created_by": group.created_by,
        "created_at": group.created_at.isoformat() if group.created_at else None,
        "is_active": group.is_active,
        "is_member": membership is not None,
        "role": membership.role if membership else None,
    }


@app.route("/groups", methods=["POST"])
@require_csrf
def create_group():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    name = (data.get("name") or "").strip()
    if not name or len(name) > GROUP_NAME_MAX:
        return jsonify({"error": f"name is required and must be {GROUP_NAME_MAX} characters or fewer"}), 400

    description = data.get("description")
    if description is not None:
        if not isinstance(description, str):
            return jsonify({"error": "description must be a string"}), 400
        description = description.strip() or None
        if description and len(description) > GROUP_DESCRIPTION_MAX:
            return jsonify({"error": f"description must be {GROUP_DESCRIPTION_MAX} characters or fewer"}), 400

    privacy = (data.get("privacy") or "public").strip().lower()
    if privacy not in GROUP_PRIVACY_VALUES:
        return jsonify({"error": "privacy must be one of: " + ", ".join(sorted(GROUP_PRIVACY_VALUES))}), 400

    university_id = data.get("university_id")
    if university_id is not None:
        if not isinstance(university_id, int) or not db.session.get(University, university_id):
            return jsonify({"error": "Invalid university_id"}), 400

    program_id = data.get("program_id")
    if program_id is not None:
        if not isinstance(program_id, int) or not db.session.get(Program, program_id):
            return jsonify({"error": "Invalid program_id"}), 400

    unit_id = data.get("unit_id")
    if unit_id is not None:
        if not isinstance(unit_id, int) or not db.session.get(Unit, unit_id):
            return jsonify({"error": "Invalid unit_id"}), 400

    year = data.get("year")
    if year is not None:
        if not isinstance(year, int) or isinstance(year, bool) or year < 1 or year > 5:
            return jsonify({"error": "year must be a number between 1 and 5, or omitted for 'Mixed'"}), 400

    member_user_ids = data.get("member_user_ids")
    if member_user_ids is not None:
        if not isinstance(member_user_ids, list) or len(member_user_ids) > 50:
            return jsonify({"error": "member_user_ids must be a list of at most 50 user ids"}), 400
        if not all(isinstance(uid, int) and not isinstance(uid, bool) for uid in member_user_ids):
            return jsonify({"error": "member_user_ids must all be integers"}), 400
        member_user_ids = sorted({uid for uid in member_user_ids if uid != user_id})
    else:
        member_user_ids = []

    group = Group(
        name=name,
        description=description,
        privacy=privacy,
        university_id=university_id,
        program_id=program_id,
        unit_id=unit_id,
        year=year,
        created_by=user_id,
        member_count=1,
    )
    db.session.add(group)
    db.session.flush()  # assign group.id before the membership row references it

    membership = GroupMember(group_id=group.id, user_id=user_id, role="admin")
    db.session.add(membership)

    added_members = 0
    for member_id in member_user_ids:
        # Silently skip unknown ids rather than failing the whole create -
        # a stale/typo'd id in the initial member list shouldn't block
        # group creation.
        if db.session.get(User, member_id):
            db.session.add(GroupMember(group_id=group.id, user_id=member_id, role="member"))
            added_members += 1
    group.member_count = 1 + added_members

    db.session.commit()

    return jsonify(_serialize_group(group, membership)), 201


@app.route("/groups")
def browse_groups():
    """
    Browse/discover groups. Private groups are excluded entirely - no
    invite/request flow exists yet, so surfacing them would just be a
    dead end. Course-only groups ARE listed (not yet restricted to
    matching students - that's a later refinement, not a security
    boundary, since course_only groups still require an explicit join).
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    query = Group.query.filter(Group.privacy != "private", Group.is_active.is_(True))

    q = (request.args.get("q") or "").strip()
    if q:
        query = query.filter(Group.name.ilike(f"%{q}%"))

    unit_id = request.args.get("unit_id", type=int)
    if unit_id:
        query = query.filter(Group.unit_id == unit_id)

    university_id = request.args.get("university_id", type=int)
    if university_id:
        query = query.filter(Group.university_id == university_id)

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 20

    groups = (
        query.order_by(Group.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    group_ids = [g.id for g in groups]
    memberships = {
        m.group_id: m
        for m in GroupMember.query.filter(
            GroupMember.user_id == user_id, GroupMember.group_id.in_(group_ids)
        ).all()
    } if group_ids else {}

    return jsonify({
        "page": page,
        "groups": [_serialize_group(g, memberships.get(g.id)) for g in groups],
    })


@app.route("/groups/mine")
def my_groups():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    memberships = (
        GroupMember.query.filter_by(user_id=user_id)
        .order_by(GroupMember.joined_at.desc())
        .all()
    )

    result = []
    for m in memberships:
        group = db.session.get(Group, m.group_id)
        if not group:
            continue
        result.append(_serialize_group(group, m))

    return jsonify({"groups": result})


@app.route("/groups/<int:group_id>")
def get_group(group_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()

    if group.privacy == "private" and not membership:
        # Hide existence of private groups from non-members rather than
        # a 403 that would confirm the group exists.
        return jsonify({"error": "Group not found"}), 404

    return jsonify(_serialize_group(group, membership))


@app.route("/groups/<int:group_id>/join", methods=["POST"])
@require_csrf
def join_group(group_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    existing = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
    if existing:
        return jsonify({"message": "Already a member", "role": existing.role}), 200

    if not group.is_active:
        return jsonify({"error": "This group has been deactivated"}), 403

    if group.privacy == "private":
        # No invite/request flow yet.
        return jsonify({"error": "This group is invite-only"}), 403

    membership = GroupMember(group_id=group_id, user_id=user_id, role="member")
    db.session.add(membership)
    group.member_count = (group.member_count or 0) + 1
    db.session.commit()

    return jsonify({
        "message": "Joined",
        "role": membership.role,
        "member_count": group.member_count,
    }), 201


@app.route("/groups/<int:group_id>/leave", methods=["POST"])
@require_csrf
def leave_group(group_id):
    """
    A sole admin can't leave while other members remain - there's no
    promote-another-admin endpoint yet, so this would strand the group.
    If they're the last member overall, leaving is allowed (the group
    is simply left empty for now - cleanup/deletion is a later item).
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
    if not membership:
        return jsonify({"message": "Not a member"}), 200

    if membership.role == "admin":
        other_admins = GroupMember.query.filter(
            GroupMember.group_id == group_id,
            GroupMember.role == "admin",
            GroupMember.user_id != user_id,
        ).count()
        other_members = GroupMember.query.filter(
            GroupMember.group_id == group_id,
            GroupMember.user_id != user_id,
        ).count()
        if other_admins == 0 and other_members > 0:
            return jsonify({
                "error": "You're the only admin - promote another member to admin before leaving"
            }), 400

    db.session.delete(membership)
    group.member_count = max(0, (group.member_count or 1) - 1)
    db.session.commit()

    return jsonify({"message": "Left group", "member_count": group.member_count})


def _get_group_visible(group_id, user_id):
    """
    Returns (group, membership) if the group exists and is visible to
    user_id - public/course_only groups are visible to anyone, private
    groups only to members. Returns (None, None) otherwise, so callers
    can 404 without distinguishing "doesn't exist" from "private and
    you're not in it".
    """
    group = db.session.get(Group, group_id)
    if not group:
        return None, None
    membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
    if group.privacy == "private" and not membership:
        return None, None
    return group, membership


GROUP_POST_TYPES = {"post", "question"}
GROUP_POST_BODY_MAX = 3000
GROUP_POST_COMMENT_MAX = 2000


def _serialize_group_post(post, user_id):
    author = db.session.get(User, post.user_id)
    like_count = None
    vote_count = None
    viewer_liked = False
    viewer_voted = False
    if post.post_type == "post":
        like_count = GroupPostLike.query.filter_by(group_post_id=post.id).count()
        viewer_liked = GroupPostLike.query.filter_by(group_post_id=post.id, user_id=user_id).first() is not None
    else:
        vote_count = GroupQuestionVote.query.filter_by(group_post_id=post.id).count()
        viewer_voted = GroupQuestionVote.query.filter_by(group_post_id=post.id, user_id=user_id).first() is not None
    comment_count = GroupPostComment.query.filter_by(group_post_id=post.id).count()
    return {
        "id": post.id,
        "group_id": post.group_id,
        "post_type": post.post_type,
        "body": post.body if not post.is_removed else None,
        "is_removed": post.is_removed,
        "author": _display_name(author) if author else "Deleted user",
        "author_id": post.user_id,
        "like_count": like_count,
        "viewer_liked": viewer_liked,
        "vote_count": vote_count,
        "viewer_voted": viewer_voted,
        "comment_count": comment_count,
        "created_at": post.created_at.isoformat() if post.created_at else None,
    }


def _serialize_group_post_comment(comment):
    author = db.session.get(User, comment.user_id)
    return {
        "id": comment.id,
        "group_post_id": comment.group_post_id,
        "body": comment.body if not comment.is_removed else None,
        "is_removed": comment.is_removed,
        "author": _display_name(author) if author else "Deleted user",
        "author_id": comment.user_id,
        "marked_helpful": comment.marked_helpful,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


@app.route("/groups/<int:group_id>/posts", methods=["POST"])
@require_csrf
def create_group_post(group_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    if not membership:
        return jsonify({"error": "You must join this group first"}), 403
    if not group.is_active:
        return jsonify({"error": "This group has been deactivated"}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    post_type = (data.get("post_type") or "post").strip().lower()
    if post_type not in GROUP_POST_TYPES:
        return jsonify({"error": "post_type must be 'post' or 'question'"}), 400

    body = (data.get("body") or "").strip()
    if not body or len(body) > GROUP_POST_BODY_MAX:
        return jsonify({"error": f"body is required and must be {GROUP_POST_BODY_MAX} characters or fewer"}), 400

    post = GroupPost(group_id=group_id, user_id=user_id, post_type=post_type, body=body)
    db.session.add(post)
    db.session.commit()

    return jsonify(_serialize_group_post(post, user_id)), 201


@app.route("/groups/<int:group_id>/posts")
def list_group_posts(group_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    post_type = (request.args.get("type") or "post").strip().lower()
    if post_type not in GROUP_POST_TYPES:
        return jsonify({"error": "type must be 'post' or 'question'"}), 400

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 20

    posts = (
        GroupPost.query.filter_by(group_id=group_id, post_type=post_type, is_removed=False)
        .order_by(GroupPost.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return jsonify({
        "page": page,
        "posts": [_serialize_group_post(p, user_id) for p in posts],
    })


@app.route("/groups/<int:group_id>/posts/<int:post_id>")
def get_group_post(group_id, post_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    post = db.session.get(GroupPost, post_id)
    if not post or post.group_id != group_id:
        return jsonify({"error": "Post not found"}), 404

    comments = (
        GroupPostComment.query.filter_by(group_post_id=post_id)
        .order_by(GroupPostComment.created_at.asc())
        .all()
    )

    result = _serialize_group_post(post, user_id)
    result["comments"] = [_serialize_group_post_comment(c) for c in comments]
    return jsonify(result)


@app.route("/groups/<int:group_id>/posts/<int:post_id>/comments", methods=["POST"])
@require_csrf
def create_group_post_comment(group_id, post_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    if not membership:
        return jsonify({"error": "You must join this group first"}), 403
    if not group.is_active:
        return jsonify({"error": "This group has been deactivated"}), 403

    post = db.session.get(GroupPost, post_id)
    if not post or post.group_id != group_id:
        return jsonify({"error": "Post not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    body = (data.get("body") or "").strip()
    if not body or len(body) > GROUP_POST_COMMENT_MAX:
        return jsonify({"error": f"body is required and must be {GROUP_POST_COMMENT_MAX} characters or fewer"}), 400

    comment = GroupPostComment(group_post_id=post_id, user_id=user_id, body=body)
    db.session.add(comment)

    if post.user_id != user_id and should_notify(post.user_id, "community"):
        commenter = db.session.get(User, user_id)
        group = db.session.get(Group, group_id)
        db.session.add(Notification(
            user_id=post.user_id,
            type="group_comment",
            title="New comment" if post.post_type == "post" else "New reply",
            body=f"{_display_name(commenter)} commented on your {post.post_type} in {group.name if group else 'a group'}",
            related_type="group_post",
            related_id=post.id,
        ))
        send_push_notification(
            post.user_id,
            "New comment" if post.post_type == "post" else "New reply",
            f"{_display_name(commenter)} commented on your {post.post_type} in {group.name if group else 'a group'}",
        )

    db.session.commit()

    return jsonify(_serialize_group_post_comment(comment)), 201


@app.route("/groups/<int:group_id>/posts/<int:post_id>/comments/<int:comment_id>/helpful", methods=["POST"])
@require_csrf
def mark_comment_helpful(group_id, post_id, comment_id):
    """
    Lets the ORIGINAL POST author mark a reply as helpful, once, awarding
    the replier community_helpful_reply XP (Chunk 7). Restricted to the
    post author (not any group member) so this can't be used to farm XP
    for friends, and restricted to Questions-tab posts since "helpful"
    only makes sense as an answer-quality signal there.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    post = db.session.get(GroupPost, post_id)
    if not post or post.group_id != group_id:
        return jsonify({"error": "Post not found"}), 404
    if post.post_type != "question":
        return jsonify({"error": "Only replies on Questions-tab posts can be marked helpful"}), 400
    if post.user_id != user_id:
        return jsonify({"error": "Only the person who asked the question can mark a reply helpful"}), 403

    comment = db.session.get(GroupPostComment, comment_id)
    if not comment or comment.group_post_id != post_id:
        return jsonify({"error": "Comment not found"}), 404
    if comment.user_id == user_id:
        return jsonify({"error": "You can't mark your own reply helpful"}), 400
    if comment.marked_helpful:
        return jsonify({"message": "Already marked helpful"}), 200

    comment.marked_helpful = True
    xp_awarded = award_xp(
        comment.user_id, "community_helpful_reply", XP_COMMUNITY_HELPFUL_REPLY, related_id=comment.id,
    )
    newly_unlocked = check_and_unlock_achievements(comment.user_id) if xp_awarded else []
    db.session.commit()

    return jsonify({
        "message": "Marked helpful",
        "xp_awarded": XP_COMMUNITY_HELPFUL_REPLY if xp_awarded else 0,
        "newly_unlocked_achievements": newly_unlocked,
    })


@app.route("/groups/<int:group_id>/posts/<int:post_id>/like", methods=["POST"])
@require_csrf
def like_group_post(group_id, post_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    if not membership:
        return jsonify({"error": "You must join this group first"}), 403

    post = db.session.get(GroupPost, post_id)
    if not post or post.group_id != group_id:
        return jsonify({"error": "Post not found"}), 404
    if post.post_type != "post":
        return jsonify({"error": "Only Posts-tab posts can be liked - use vote for questions"}), 400

    existing = GroupPostLike.query.filter_by(group_post_id=post_id, user_id=user_id).first()
    if not existing:
        db.session.add(GroupPostLike(group_post_id=post_id, user_id=user_id))
        if post.user_id != user_id and should_notify(post.user_id, "community"):
            liker = db.session.get(User, user_id)
            db.session.add(Notification(
                user_id=post.user_id,
                type="group_like",
                title="New like",
                body=f"{_display_name(liker)} liked your post",
                related_type="group_post",
                related_id=post.id,
            ))
            send_push_notification(
                post.user_id,
                "New like",
                f"{_display_name(liker)} liked your post",
                data={"screen": "notifications", "related_type": "group_post", "related_id": post.id},
            )
        db.session.commit()

    return jsonify({
        "message": "Already liked" if existing else "Liked",
        "like_count": GroupPostLike.query.filter_by(group_post_id=post_id).count(),
    }), (200 if existing else 201)


@app.route("/groups/<int:group_id>/posts/<int:post_id>/like", methods=["DELETE"])
@require_csrf
def unlike_group_post(group_id, post_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    existing = GroupPostLike.query.filter_by(group_post_id=post_id, user_id=user_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()

    return jsonify({
        "message": "Unliked" if existing else "Not liked",
        "like_count": GroupPostLike.query.filter_by(group_post_id=post_id).count(),
    })


@app.route("/groups/<int:group_id>/posts/<int:post_id>/vote", methods=["POST"])
@require_csrf
def vote_group_post(group_id, post_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    if not membership:
        return jsonify({"error": "You must join this group first"}), 403

    post = db.session.get(GroupPost, post_id)
    if not post or post.group_id != group_id:
        return jsonify({"error": "Post not found"}), 404
    if post.post_type != "question":
        return jsonify({"error": "Only Questions-tab posts can be voted on - use like for posts"}), 400

    existing = GroupQuestionVote.query.filter_by(group_post_id=post_id, user_id=user_id).first()
    if not existing:
        db.session.add(GroupQuestionVote(group_post_id=post_id, user_id=user_id))
        if post.user_id != user_id and should_notify(post.user_id, "community"):
            voter = db.session.get(User, user_id)
            db.session.add(Notification(
                user_id=post.user_id,
                type="group_vote",
                title="New vote",
                body=f"{_display_name(voter)} voted on your question",
                related_type="group_post",
                related_id=post.id,
            ))
            send_push_notification(
                post.user_id,
                "New vote",
                f"{_display_name(voter)} voted on your question",
                data={"screen": "notifications", "related_type": "group_post", "related_id": post.id},
            )
        db.session.commit()

    return jsonify({
        "message": "Already voted" if existing else "Voted",
        "vote_count": GroupQuestionVote.query.filter_by(group_post_id=post_id).count(),
    }), (200 if existing else 201)


@app.route("/groups/<int:group_id>/posts/<int:post_id>/vote", methods=["DELETE"])
@require_csrf
def unvote_group_post(group_id, post_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    existing = GroupQuestionVote.query.filter_by(group_post_id=post_id, user_id=user_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()

    return jsonify({
        "message": "Unvoted" if existing else "Not voted",
        "vote_count": GroupQuestionVote.query.filter_by(group_post_id=post_id).count(),
    })


# ---------- Group members ----------

def _serialize_group_member(membership):
    user = db.session.get(User, membership.user_id)
    return {
        "user_id": membership.user_id,
        "display_name": _display_name(user) if user else "Deleted user",
        "role": membership.role,
        "joined_at": membership.joined_at.isoformat() if membership.joined_at else None,
    }


@app.route("/groups/<int:group_id>/members")
def list_group_members(group_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    members = GroupMember.query.filter_by(group_id=group_id).all()
    members.sort(key=lambda m: (0 if m.role == "admin" else 1, m.joined_at or datetime.min))

    return jsonify({"members": [_serialize_group_member(m) for m in members]})


@app.route("/groups/<int:group_id>/members/<int:target_user_id>", methods=["PATCH"])
@require_csrf
def update_group_member_role(group_id, target_user_id):
    """
    Promote a member to admin, or demote an admin to member. Admin-only.
    Refuses to demote the last remaining admin - they'd need to promote
    someone else first (this is also how a sole admin unblocks
    themselves from the leave_group restriction).
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    requester = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
    if not requester or requester.role != "admin":
        return jsonify({"error": "Only group admins can change member roles"}), 403

    target = GroupMember.query.filter_by(group_id=group_id, user_id=target_user_id).first()
    if not target:
        return jsonify({"error": "Member not found"}), 404

    data = request.get_json(silent=True) or {}
    role = (data.get("role") or "").strip().lower()
    if role not in ("admin", "member"):
        return jsonify({"error": "role must be 'admin' or 'member'"}), 400

    if role == "member" and target.role == "admin":
        other_admins = GroupMember.query.filter(
            GroupMember.group_id == group_id,
            GroupMember.role == "admin",
            GroupMember.user_id != target_user_id,
        ).count()
        if other_admins == 0:
            return jsonify({"error": "Can't demote the only admin - promote someone else first"}), 400

    was_admin = target.role == "admin"
    target.role = role

    if role == "admin" and not was_admin and should_notify(target_user_id, "community"):
        group = db.session.get(Group, group_id)
        db.session.add(Notification(
            user_id=target_user_id,
            type="group_promoted",
            title="You're now an admin",
            body=f"You were made an admin of {group.name if group else 'a group'}",
            related_type="group",
            related_id=group_id,
        ))
        send_push_notification(
            target_user_id,
            "You're now an admin",
            f"You were made an admin of {group.name if group else 'a group'}",
        )

    db.session.commit()

    return jsonify(_serialize_group_member(target))


@app.route("/groups/<int:group_id>/members/<int:target_user_id>", methods=["DELETE"])
@require_csrf
def remove_group_member(group_id, target_user_id):
    """
    Admin-only kick. Self-removal is deliberately rejected here - use
    POST /groups/<id>/leave instead, which has its own sole-admin
    protection. An admin target must be demoted first (kicking an
    admin outright would bypass that protection entirely).
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if target_user_id == user_id:
        return jsonify({"error": "Use POST /groups/<id>/leave to remove yourself"}), 400

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    requester = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
    if not requester or requester.role != "admin":
        return jsonify({"error": "Only group admins can remove members"}), 403

    target = GroupMember.query.filter_by(group_id=group_id, user_id=target_user_id).first()
    if not target:
        return jsonify({"error": "Member not found"}), 404

    if target.role == "admin":
        return jsonify({"error": "Demote this admin before removing them"}), 400

    db.session.delete(target)
    group.member_count = max(0, (group.member_count or 1) - 1)
    db.session.commit()

    return jsonify({"message": "Member removed", "member_count": group.member_count})


# ---------- Group files ----------

def _serialize_group_file(group_file):
    document = db.session.get(Document, group_file.document_id)
    content = (
        db.session.get(DocumentContent, document.document_content_id)
        if document and document.document_content_id else None
    )
    sharer = db.session.get(User, group_file.shared_by_user_id)
    view_url = None
    if content and content.status == "ready":
        view_url = get_signed_url(content.storage_path, bucket="documents")
    return {
        "id": group_file.id,
        "group_id": group_file.group_id,
        "document_id": group_file.document_id,
        "title": document.title if document else None,
        "file_type": content.file_type if content else None,
        "file_size_bytes": content.file_size_bytes if content else None,
        "page_count": content.page_count if content else None,
        "view_url": view_url,
        "shared_by": _display_name(sharer) if sharer else "Deleted user",
        "shared_by_user_id": group_file.shared_by_user_id,
        "created_at": group_file.created_at.isoformat() if group_file.created_at else None,
    }


@app.route("/groups/<int:group_id>/files", methods=["POST"])
@require_csrf
def share_group_file(group_id):
    """
    Shares one of the caller's OWN ready Documents into the group's
    Files tab. Does not touch storage - just links the existing
    Document row, same dedup-friendly pattern as the rest of the app.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    if not membership:
        return jsonify({"error": "You must join this group first"}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    document_id = data.get("document_id")
    if not isinstance(document_id, int) or isinstance(document_id, bool):
        return jsonify({"error": "document_id is required"}), 400

    document = db.session.get(Document, document_id)
    if not document or document.user_id != user_id or document.is_removed:
        return jsonify({"error": "Document not found"}), 404

    content = (
        db.session.get(DocumentContent, document.document_content_id)
        if document.document_content_id else None
    )
    effective_status = content.status if (content and document.status != "uploading") else document.status
    if effective_status != "ready":
        return jsonify({"error": f"Document is not ready to share (status: {effective_status})"}), 400

    existing = GroupFile.query.filter_by(group_id=group_id, document_id=document_id).first()
    if existing:
        return jsonify(_serialize_group_file(existing)), 200

    group_file = GroupFile(group_id=group_id, document_id=document_id, shared_by_user_id=user_id)
    db.session.add(group_file)
    db.session.commit()

    return jsonify(_serialize_group_file(group_file)), 201


@app.route("/groups/<int:group_id>/files")
def list_group_files(group_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    files = (
        GroupFile.query.filter_by(group_id=group_id)
        .order_by(GroupFile.created_at.desc())
        .all()
    )

    return jsonify({"files": [_serialize_group_file(f) for f in files]})


@app.route("/groups/<int:group_id>/files/<int:file_id>", methods=["DELETE"])
@require_csrf
def remove_group_file(group_id, file_id):
    """Removable by whoever shared it, or by any group admin."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    group_file = db.session.get(GroupFile, file_id)
    if not group_file or group_file.group_id != group_id:
        return jsonify({"error": "File not found"}), 404

    membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
    is_admin = bool(membership and membership.role == "admin")

    if group_file.shared_by_user_id != user_id and not is_admin:
        return jsonify({"error": "Only the person who shared this file or a group admin can remove it"}), 403

    db.session.delete(group_file)
    db.session.commit()

    return jsonify({"message": "File removed"})


# ---------- Content reports (Chunk 10 moderation) ----------

CONTENT_REPORT_DETAILS_MAX = 500


def _content_report_target_exists(target_type, target_id):
    """Returns the target row if it exists (and isn't already removed
    for the content types that support removal), else None."""
    if target_type == "group_post":
        return GroupPost.query.filter_by(id=target_id, is_removed=False).first()
    if target_type == "group_post_comment":
        return GroupPostComment.query.filter_by(id=target_id, is_removed=False).first()
    if target_type == "user":
        return User.query.filter_by(id=target_id, is_suspended=False).first()
    return None


@app.route("/content-reports", methods=["POST"])
@require_csrf
def create_content_report():
    """
    Files a report against a forum post/reply, group post/comment, or
    a user directly. No duplicate-report guard, same reasoning as
    report_library_item() - admins dedupe on the review side.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    target_type = (data.get("target_type") or "").strip().lower()
    target_id = data.get("target_id")
    reason = (data.get("reason") or "").strip().lower()
    details = data.get("details")

    if target_type not in CONTENT_REPORT_TARGET_TYPES:
        return jsonify({"error": "target_type must be one of: " + ", ".join(CONTENT_REPORT_TARGET_TYPES)}), 400
    if not isinstance(target_id, int) or isinstance(target_id, bool):
        return jsonify({"error": "target_id is required"}), 400
    if reason not in CONTENT_REPORT_REASONS:
        return jsonify({"error": "reason must be one of: " + ", ".join(CONTENT_REPORT_REASONS)}), 400
    if target_type == "user" and target_id == user_id:
        return jsonify({"error": "You can't report yourself"}), 400

    if details is not None:
        details = details.strip()
        if len(details) > CONTENT_REPORT_DETAILS_MAX:
            return jsonify({"error": f"details must be {CONTENT_REPORT_DETAILS_MAX} characters or fewer"}), 400
        details = details or None

    if not _content_report_target_exists(target_type, target_id):
        return jsonify({"error": "Reported content was not found"}), 404

    report = ContentReport(
        target_type=target_type,
        target_id=target_id,
        reporter_user_id=user_id,
        reason=reason,
        details=details,
        priority=CONTENT_REPORT_REASONS[reason],
        status="pending",
    )
    db.session.add(report)
    db.session.commit()

    return jsonify({"id": report.id, "status": report.status, "priority": report.priority}), 201


# ---------- Follows ----------

def _serialize_follow_user(user, viewer_user_id):
    return {
        "user_id": user.id,
        "display_name": _display_name(user),
        "is_following": Follow.query.filter_by(
            follower_id=viewer_user_id, followed_id=user.id
        ).first() is not None,
    }


@app.route("/users/<int:target_user_id>/follow", methods=["POST"])
@require_csrf
def follow_user(target_user_id):
    """
    Follows a user immediately, UNLESS the target has
    who_can_follow='approval_required' - in that case this creates
    (or reuses/reopens) a pending FollowRequest and notifies the
    target instead of creating a Follow row directly. The frontend
    should treat a 202 response as "requested, not yet following".
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if target_user_id == user_id:
        return jsonify({"error": "You can't follow yourself"}), 400

    target = db.session.get(User, target_user_id)
    if not target or target.is_suspended:
        return jsonify({"error": "User not found"}), 404

    existing = Follow.query.filter_by(follower_id=user_id, followed_id=target_user_id).first()
    if existing:
        return jsonify({
            "message": "Already following",
            "followers_count": Follow.query.filter_by(followed_id=target_user_id).count(),
        }), 200

    if target.who_can_follow == "approval_required":
        pending = FollowRequest.query.filter_by(requester_id=user_id, target_id=target_user_id).first()
        if pending and pending.status == "pending":
            return jsonify({"message": "Follow request already sent", "status": "pending"}), 200
        if pending:
            pending.status = "pending"
            pending.responded_at = None
        else:
            pending = FollowRequest(requester_id=user_id, target_id=target_user_id, status="pending")
            db.session.add(pending)
        requester = db.session.get(User, user_id)
        if should_notify(target_user_id, "community"):
            db.session.add(Notification(
                user_id=target_user_id,
                type="follow_request",
                title="New follow request",
                body=f"{_display_name(requester)} wants to follow you",
                related_type="user",
                related_id=user_id,
            ))
            send_push_notification(
                target_user_id,
                "New follow request",
                f"{_display_name(requester)} wants to follow you",
            )
        db.session.commit()
        return jsonify({"message": "Follow request sent", "status": "pending"}), 202

    db.session.add(Follow(follower_id=user_id, followed_id=target_user_id))
    follower = db.session.get(User, user_id)
    if should_notify(target_user_id, "community"):
        db.session.add(Notification(
            user_id=target_user_id,
            type="new_follower",
            title="New follower",
            body=f"{_display_name(follower)} started following you",
            related_type="user",
            related_id=user_id,
        ))
        send_push_notification(
            target_user_id,
            "New follower",
            f"{_display_name(follower)} started following you",
        )
    db.session.commit()

    return jsonify({
        "message": "Followed",
        "followers_count": Follow.query.filter_by(followed_id=target_user_id).count(),
    }), 201


@app.route("/follow-requests")
def list_follow_requests():
    """Pending follow requests directed AT the logged-in user."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    requests = (
        FollowRequest.query.filter_by(target_id=user_id, status="pending")
        .order_by(FollowRequest.created_at.desc())
        .all()
    )

    result = []
    for r in requests:
        requester = db.session.get(User, r.requester_id)
        result.append({
            "id": r.id,
            "requester_id": r.requester_id,
            "requester_display_name": _display_name(requester) if requester else "Deleted user",
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return jsonify({"requests": result})


@app.route("/follow-requests/<int:request_id>/accept", methods=["POST"])
@require_csrf
def accept_follow_request(request_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    req = db.session.get(FollowRequest, request_id)
    if not req or req.target_id != user_id:
        return jsonify({"error": "Follow request not found"}), 404
    if req.status != "pending":
        return jsonify({"error": f"Request is not pending (status: {req.status})"}), 400

    req.status = "accepted"
    req.responded_at = datetime.utcnow()

    existing_follow = Follow.query.filter_by(follower_id=req.requester_id, followed_id=user_id).first()
    if not existing_follow:
        db.session.add(Follow(follower_id=req.requester_id, followed_id=user_id))
        target = db.session.get(User, user_id)
        if should_notify(req.requester_id, "community"):
            db.session.add(Notification(
                user_id=req.requester_id,
                type="new_follower",
                title="Follow request accepted",
                body=f"{_display_name(target)} accepted your follow request",
                related_type="user",
                related_id=user_id,
            ))
            send_push_notification(
                req.requester_id,
                "Follow request accepted",
                f"{_display_name(target)} accepted your follow request",
            )

    db.session.commit()

    return jsonify({
        "message": "Accepted",
        "followers_count": Follow.query.filter_by(followed_id=user_id).count(),
    })


@app.route("/follow-requests/<int:request_id>/decline", methods=["POST"])
@require_csrf
def decline_follow_request(request_id):
    """
    Declines a pending follow request. Deliberately does NOT notify
    the requester - same silent-decline convention private accounts
    elsewhere use, so declining doesn't feel like a public rejection.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    req = db.session.get(FollowRequest, request_id)
    if not req or req.target_id != user_id:
        return jsonify({"error": "Follow request not found"}), 404
    if req.status != "pending":
        return jsonify({"error": f"Request is not pending (status: {req.status})"}), 400

    req.status = "declined"
    req.responded_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"message": "Declined"})


@app.route("/users/<int:target_user_id>/follow", methods=["DELETE"])
@require_csrf
def unfollow_user(target_user_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    existing = Follow.query.filter_by(follower_id=user_id, followed_id=target_user_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()

    return jsonify({
        "message": "Unfollowed" if existing else "Not following",
        "followers_count": Follow.query.filter_by(followed_id=target_user_id).count(),
    })


@app.route("/users/<int:target_user_id>/followers")
def list_followers(target_user_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    target = db.session.get(User, target_user_id)
    if not target:
        return jsonify({"error": "User not found"}), 404

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 20

    rows = (
        Follow.query.filter_by(followed_id=target_user_id)
        .order_by(Follow.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    followers = [db.session.get(User, r.follower_id) for r in rows]

    return jsonify({
        "page": page,
        "followers": [_serialize_follow_user(u, user_id) for u in followers if u],
    })


@app.route("/users/<int:target_user_id>/following")
def list_following(target_user_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    target = db.session.get(User, target_user_id)
    if not target:
        return jsonify({"error": "User not found"}), 404

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 20

    rows = (
        Follow.query.filter_by(follower_id=target_user_id)
        .order_by(Follow.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    following = [db.session.get(User, r.followed_id) for r in rows]

    return jsonify({
        "page": page,
        "following": [_serialize_follow_user(u, user_id) for u in following if u],
    })


@app.route("/users/<int:target_user_id>/follow-summary")
def follow_summary(target_user_id):
    """Counts + relationship flags for a profile header."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    target = db.session.get(User, target_user_id)
    if not target:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "user_id": target_user_id,
        "followers_count": Follow.query.filter_by(followed_id=target_user_id).count(),
        "following_count": Follow.query.filter_by(follower_id=target_user_id).count(),
        "is_following": Follow.query.filter_by(
            follower_id=user_id, followed_id=target_user_id
        ).first() is not None,
        "is_followed_by": Follow.query.filter_by(
            follower_id=target_user_id, followed_id=user_id
        ).first() is not None,
    })


@app.route("/users/<int:target_user_id>/public-profile")
def get_public_profile(target_user_id):
    """
    Lightweight public profile fields for VIEWING another student -
    distinct from /me (your own full profile, includes email) and from
    follow_summary above (just counts/relationship flags). Deliberately
    excludes email and any other contact/sensitive fields - only what a
    student's profile card needs to render for someone who isn't them.
    Suspended users 404 the same way follow_summary treats a missing
    user, so this can't be used to confirm a suspended account exists.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    target = db.session.get(User, target_user_id)
    if not target or target.is_suspended:
        return jsonify({"error": "User not found"}), 404

    if target.profile_visibility == "private" and target.id != user_id:
        return jsonify({
            "user_id": target.id,
            "display_name": _display_name(target),
            "is_private": True,
        })

    university = db.session.get(University, target.university_id) if target.university_id else None
    program = db.session.get(Program, target.program_id) if target.program_id else None

    documents_count = Document.query.filter_by(user_id=target_user_id, is_removed=False).count()
    xp_total = db.session.query(func.coalesce(func.sum(XpEvent.xp_amount), 0)).filter(
        XpEvent.user_id == target_user_id
    ).scalar()

    today = datetime.utcnow().date()
    week_start = today - timedelta(days=today.weekday())
    weekly_study_seconds = db.session.query(
        db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0)
    ).filter(
        StudyTimeLog.user_id == target_user_id,
        StudyTimeLog.activity_date >= week_start,
        StudyTimeLog.activity_date <= today,
    ).scalar()

    return jsonify({
        "user_id": target.id,
        "display_name": _display_name(target),
        "bio": target.bio,
        "year": target.year,
        "university_name": university.name if university else None,
        "program_name": program.name if program else None,
        "documents_count": documents_count,
        "xp_total": int(xp_total),
        "weekly_study_seconds": int(weekly_study_seconds or 0),
        "is_private": False,
    })


# ---------- Notifications ----------

def _serialize_notification(notification):
    return {
        "id": notification.id,
        "type": notification.type,
        "title": notification.title,
        "body": notification.body,
        "related_type": notification.related_type,
        "related_id": notification.related_id,
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
    }


@app.route("/notifications")
def list_notifications():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 20

    # Announcements less than 24h old are pinned to the top of the feed,
    # newest-first among themselves, ahead of everything else - after 24h
    # an announcement just falls back into normal chronological order.
    # A plain boolean SQL expression (not case()) keeps this portable
    # across SQLAlchemy versions, same reasoning as the case()-avoidance
    # elsewhere in this file.
    pin_cutoff = datetime.utcnow() - timedelta(hours=24)
    is_pinned_announcement = and_(
        Notification.type == "announcement",
        Notification.created_at >= pin_cutoff,
    )

    notifications = (
        Notification.query.filter_by(user_id=user_id)
        .order_by(is_pinned_announcement.desc(), Notification.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return jsonify({
        "page": page,
        "notifications": [_serialize_notification(n) for n in notifications],
    })


@app.route("/notifications/unread-count")
def notifications_unread_count():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    return jsonify({"unread_count": count})


@app.route("/notifications/<int:notification_id>/read", methods=["POST"])
@require_csrf
def mark_notification_read(notification_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    notification = db.session.get(Notification, notification_id)
    if not notification or notification.user_id != user_id:
        return jsonify({"error": "Notification not found"}), 404

    if not notification.is_read:
        notification.is_read = True
        db.session.commit()

    return jsonify(_serialize_notification(notification))


@app.route("/notifications/read-all", methods=["POST"])
@require_csrf
def mark_all_notifications_read():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    updated_count = (
        Notification.query.filter_by(user_id=user_id, is_read=False)
        .update({"is_read": True})
    )
    db.session.commit()

    return jsonify({"message": "Marked all as read", "updated_count": updated_count})


@app.route("/notifications/<int:notification_id>", methods=["DELETE"])
@require_csrf
def delete_notification(notification_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    notification = db.session.get(Notification, notification_id)
    if not notification or notification.user_id != user_id:
        return jsonify({"error": "Notification not found"}), 404

    db.session.delete(notification)
    db.session.commit()

    return jsonify({"message": "Notification deleted"})


def get_or_create_notification_prefs(user_id):
    prefs = NotificationPreference.query.filter_by(user_id=user_id).first()
    if not prefs:
        prefs = NotificationPreference(user_id=user_id)
        db.session.add(prefs)
        db.session.flush()
    return prefs


def should_notify(user_id, category):
    """category: 'community' or 'messages'. Anything else (moderation
    warnings, announcements) is not gated here and always sends."""
    prefs = NotificationPreference.query.filter_by(user_id=user_id).first()
    if not prefs:
        return True
    return getattr(prefs, f"{category}_enabled", True)


@app.route("/notification-preferences")
def get_notification_preferences():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    prefs = get_or_create_notification_prefs(user_id)
    db.session.commit()

    return jsonify({
        "community_enabled": prefs.community_enabled,
        "messages_enabled": prefs.messages_enabled,
    })


@app.route("/notification-preferences", methods=["PATCH"])
@require_csrf
def update_notification_preferences():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True) or {}
    prefs = get_or_create_notification_prefs(user_id)

    if "community_enabled" in data:
        if not isinstance(data["community_enabled"], bool):
            return jsonify({"error": "community_enabled must be a boolean"}), 400
        prefs.community_enabled = data["community_enabled"]

    if "messages_enabled" in data:
        if not isinstance(data["messages_enabled"], bool):
            return jsonify({"error": "messages_enabled must be a boolean"}), 400
        prefs.messages_enabled = data["messages_enabled"]

    db.session.commit()

    return jsonify({
        "community_enabled": prefs.community_enabled,
        "messages_enabled": prefs.messages_enabled,
    })


@app.route("/push/vapid-public-key")
def get_vapid_public_key():
    """
    Public, unauthenticated - the frontend needs this before a push
    subscription can be created, same reasoning as /universities being
    public before a session exists.
    """
    public_key = os.environ.get("VAPID_PUBLIC_KEY")
    if not public_key:
        return jsonify({"error": "Push notifications are not configured"}), 503
    return jsonify({"public_key": public_key})


@app.route("/push/subscribe", methods=["POST"])
@require_csrf
def push_subscribe():
    """
    Upserts a push subscription for the logged-in user, keyed on endpoint
    (not user_id) - a device re-subscribing gets a fresh endpoint from the
    browser, so the same physical device never creates duplicate rows, but
    a user can have many rows across devices.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    endpoint = (data.get("endpoint") or "").strip()
    keys = data.get("keys") or {}
    p256dh_key = (keys.get("p256dh") or "").strip()
    auth_key = (keys.get("auth") or "").strip()

    if not endpoint or not p256dh_key or not auth_key:
        return jsonify({"error": "endpoint and keys.p256dh and keys.auth are required"}), 400

    existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if existing:
        existing.user_id = user_id
        existing.p256dh_key = p256dh_key
        existing.auth_key = auth_key
    else:
        db.session.add(PushSubscription(
            user_id=user_id, endpoint=endpoint,
            p256dh_key=p256dh_key, auth_key=auth_key,
        ))
    db.session.commit()

    return jsonify({"message": "Subscribed"}), 201


@app.route("/push/subscribe", methods=["DELETE"])
@require_csrf
def push_unsubscribe():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True) or {}
    endpoint = (data.get("endpoint") or "").strip()
    if not endpoint:
        return jsonify({"error": "endpoint is required"}), 400

    sub = PushSubscription.query.filter_by(endpoint=endpoint, user_id=user_id).first()
    if sub:
        db.session.delete(sub)
        db.session.commit()

    return jsonify({"message": "Unsubscribed"})


# ---------- E2EE key management (Chats only - Study Groups/Forum unaffected) ----------

USER_KEY_PUBLIC_KEY_MAX_LEN = 2000
# Generous ceiling for a base64url-exported raw EC public key (P-256 raw
# point is ~91 chars base64) - this just guards against garbage/abuse,
# not a tight format check, since the server never inspects key contents.


@app.route("/keys/register", methods=["POST"])
@require_csrf
def register_user_key():
    """
    Upserts the logged-in user's Chats identity public key. Called
    once by the client after it generates (or loads from IndexedDB) an
    identity keypair - see frontend/src/crypto/keys.ts. Idempotent:
    re-registering the same or a rotated public key just overwrites
    the existing row for this user (UserKey.user_id is unique).

    The server stores only the PUBLIC key here - it has no way to
    decrypt any conversation this key is later used to wrap, and never
    receives the private key in this endpoint.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    public_key = (data.get("public_key") or "").strip()
    if not public_key:
        return jsonify({"error": "public_key is required"}), 400
    if len(public_key) > USER_KEY_PUBLIC_KEY_MAX_LEN:
        return jsonify({"error": f"public_key must be {USER_KEY_PUBLIC_KEY_MAX_LEN} characters or fewer"}), 400

    existing = UserKey.query.filter_by(user_id=user_id).first()
    if existing:
        existing.public_key = public_key
    else:
        db.session.add(UserKey(user_id=user_id, public_key=public_key))
    db.session.commit()

    return jsonify({"message": "Key registered"}), 200


@app.route("/keys/<int:user_id>")
def get_user_public_key(user_id):
    """
    Returns another user's Chats identity public key, so the caller's
    client can wrap a new conversation key to them (starts being used
    in the 1:1/group chat encryption chunk - harmless and login-gated
    like every other content route in this file, so exposing it now
    doesn't require waiting for that chunk).
    """
    requester_id = session.get("user_id")
    if not requester_id:
        return jsonify({"error": "Not logged in"}), 401

    key = UserKey.query.filter_by(user_id=user_id).first()
    if not key:
        return jsonify({"error": "This user has not set up secure chat yet"}), 404

    return jsonify({"user_id": user_id, "public_key": key.public_key})


USER_KEY_BACKUP_BLOB_MAX_LEN = 8000
# Generous ceiling for a base64-encoded, AES-GCM-wrapped exported JWK
# private key (typically well under 1000 chars) - guards against
# abuse/garbage, not a format check, since the server can't and
# shouldn't inspect what's inside this ciphertext.
USER_KEY_KDF_SALT_MAX_LEN = 128


@app.route("/keys/backup", methods=["POST"])
@require_csrf
def upload_key_backup():
    """
    Uploads the passphrase-wrapped private key blob for the logged-in
    user's existing UserKey row (see frontend/src/crypto/backup.ts for
    how the blob is produced - PBKDF2-derived AES-GCM wrap, entirely
    client-side). Requires that /keys/register has already been called
    for this user - a backup wraps an identity keypair that must
    already be registered, not a substitute for registering one.

    The passphrase itself and the raw private key never appear in this
    request - only the resulting ciphertext blob and the salt used to
    derive the wrapping key from the passphrase.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    encrypted_private_key = (data.get("encrypted_private_key") or "").strip()
    kdf_salt = (data.get("kdf_salt") or "").strip()

    if not encrypted_private_key:
        return jsonify({"error": "encrypted_private_key is required"}), 400
    if not kdf_salt:
        return jsonify({"error": "kdf_salt is required"}), 400
    if len(encrypted_private_key) > USER_KEY_BACKUP_BLOB_MAX_LEN:
        return jsonify({"error": f"encrypted_private_key must be {USER_KEY_BACKUP_BLOB_MAX_LEN} characters or fewer"}), 400
    if len(kdf_salt) > USER_KEY_KDF_SALT_MAX_LEN:
        return jsonify({"error": f"kdf_salt must be {USER_KEY_KDF_SALT_MAX_LEN} characters or fewer"}), 400

    key = UserKey.query.filter_by(user_id=user_id).first()
    if not key:
        return jsonify({"error": "Register a public key via /keys/register before uploading a backup"}), 404

    key.encrypted_private_key = encrypted_private_key
    key.kdf_salt = kdf_salt
    db.session.commit()

    return jsonify({"message": "Backup saved"}), 200


@app.route("/keys/backup")
def get_key_backup():
    """
    Returns the logged-in user's OWN passphrase-wrapped private key
    blob, for a new device to download and decrypt locally with the
    user's passphrase (see frontend/src/crypto/backup.ts). Scoped to
    session["user_id"] only - there is no way to fetch anyone else's
    backup blob through this route.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    key = UserKey.query.filter_by(user_id=user_id).first()
    if not key or not key.encrypted_private_key:
        return jsonify({"error": "No backup found for this account"}), 404

    return jsonify({
        "encrypted_private_key": key.encrypted_private_key,
        "kdf_salt": key.kdf_salt,
    })


# ---------- Content routes (student-facing) ----------

# ---------- Shared display-name helper ----------
# Not forum-specific despite living in this spot historically - used by
# Groups, Follow, Chats, and Library serializers throughout this file.

def _display_name(user):
    """Forum identity is username-based, not full real-name reveal.
    display_name is optional on signup, so fall back to a stable
    per-account label rather than ever exposing email."""
    return user.display_name or f"Student{user.id}"


@app.route("/library/my-purchases")
def my_library():
    # Legacy endpoint retained for compatibility with old clients only.
    # Current Library access is subscription/plan based and does not create
    # per-content ownership records.
    return jsonify({
        "error": "Individual content purchases are no longer part of Prepza."
    }), 410

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    # Only fulfilled order-ledger purchases are eligible for the paid
    # library. Do not build the entitlement set from Payment rows alone.
    fulfilled_orders = db.session.execute(
        text("""
            SELECT item_id, MAX(COALESCE(fulfilled_at, paid_at, created_at)) AS unlocked_at
            FROM student_order
            WHERE user_id = :user_id
              AND order_type = 'content'
              AND status = 'fulfilled'
              AND quantity = 1
              AND item_id IS NOT NULL
            GROUP BY item_id
        """),
        {"user_id": user_id},
    ).mappings().all()
    unlocked_at = {row["item_id"]: row["unlocked_at"] for row in fulfilled_orders}

    items = ContentItem.query.all()
    grouped = {"past_paper": [], "notes": [], "qna": []}
    for item in items:
        if not has_access(user_id, item):
            continue
        unit = db.session.get(Unit, item.unit_id)
        item_unlocked_at = unlocked_at.get(item.id)
        grouped[item.content_type].append({
            "id": item.id,
            "title": item.title,
            "paper_year": item.paper_year,
            "unit_id": item.unit_id,
            "unit_code": unit.code if unit else None,
            "file_url": (
                get_signed_url(get_fulfilled_content_file_path(user_id, item.id))
                if item.is_downloadable else None
            ),
            "unlocked_at": item_unlocked_at.isoformat() if item_unlocked_at else None,
        })

    for content_type in grouped:
        grouped[content_type].sort(key=lambda x: x["unlocked_at"] or "", reverse=True)

    return jsonify({"content": grouped})


@app.route("/content/<int:content_id>/view/info")
def content_view_info(content_id):
    """
    For view-only Q&A content: confirms the logged-in user has paid access,
    then returns basic info (page count) so the frontend viewer knows how
    many pages to request. Does NOT return any file URL - the raw file is
    never sent to the browser for this content type.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    content_item = db.session.get(ContentItem, content_id)
    if not content_item:
        return jsonify({"error": "Content not found"}), 404

    if content_item.content_type != "qna":
        return jsonify({"error": "This endpoint is only for view-only Q&A content"}), 400

    if not has_access(user_id, content_item):
        return jsonify({"error": "You don't have access to this content"}), 403

    purchased_file_path = get_fulfilled_content_file_path(user_id, content_item.id)
    if not purchased_file_path:
        return jsonify({"error": "Purchased file is unavailable"}), 404

    pdf_bytes = fetch_private_file_bytes(purchased_file_path)
    if pdf_bytes is None:
        return jsonify({"error": "Content file could not be loaded"}), 500

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = doc.page_count
        doc.close()
    except Exception as e:
        return jsonify({"error": f"Could not read content file: {e}"}), 500

    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    progress = ViewProgress.query.filter_by(
        user_id=user_id, content_item_id=content_item.id
    ).first()
    last_page = progress.page_num if progress else 0

    return jsonify({
        "content_id": content_item.id,
        "title": content_item.title,
        "page_count": page_count,
        "last_page": last_page,
        "csrf_token": session["csrf_token"],
    })


@app.route("/content/<int:content_id>/view/page/<int:page_num>")
def content_view_page(content_id, page_num):
    """
    Returns ONE watermarked page of view-only Q&A content, rendered as a
    PNG image. Rechecks access on every single page request - never trust
    that a prior /view/info call means this call is still authorized.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    content_item = db.session.get(ContentItem, content_id)
    if not content_item:
        return jsonify({"error": "Content not found"}), 404

    if content_item.content_type != "qna":
        return jsonify({"error": "This endpoint is only for view-only Q&A content"}), 400

    if not has_access(user_id, content_item):
        return jsonify({"error": "You don't have access to this content"}), 403

    user = db.session.get(User, user_id)
    watermark_text = user.email

    purchased_file_path = get_fulfilled_content_file_path(user_id, content_item.id)
    if not purchased_file_path:
        return jsonify({"error": "Purchased file is unavailable"}), 404

    pdf_bytes = fetch_private_file_bytes(purchased_file_path)
    if pdf_bytes is None:
        return jsonify({"error": "Content file could not be loaded"}), 500

    try:
        png_bytes, page_count = render_watermarked_page(pdf_bytes, page_num, watermark_text)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Could not render page: {e}"}), 500

    response = Response(png_bytes, mimetype="image/png")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    return response


@app.route("/content/<int:content_id>/view/progress", methods=["POST"])
@require_csrf
def content_view_progress(content_id):
    """
    Saves the last-viewed page number for a Q&A content item so the
    viewer can resume there next time. Upserts a ViewProgress row.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    content_item = db.session.get(ContentItem, content_id)
    if not content_item:
        return jsonify({"error": "Content not found"}), 404

    if content_item.content_type != "qna":
        return jsonify({"error": "This endpoint is only for view-only Q&A content"}), 400

    if not has_access(user_id, content_item):
        return jsonify({"error": "You don't have access to this content"}), 403

    data = request.get_json(silent=True) or {}
    page_num = data.get("page_num")
    if not isinstance(page_num, int) or page_num < 0:
        return jsonify({"error": "page_num must be a non-negative integer"}), 400

    progress = ViewProgress.query.filter_by(
        user_id=user_id, content_item_id=content_item.id
    ).first()
    if progress:
        progress.page_num = page_num
    else:
        progress = ViewProgress(
            user_id=user_id, content_item_id=content_item.id, page_num=page_num
        )
        db.session.add(progress)
    db.session.commit()

    return jsonify({"ok": True})


@app.route("/content/<int:content_id>/pay", methods=["POST"])
@limiter.limit(
    "1 per 20 seconds",
    key_func=lambda: f"pay:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def pay_for_content(content_id):
    # Kept as an explicit tombstone so stale clients cannot accidentally
    # create individual content purchases. Content remains Library/learning
    # infrastructure; student monetization is subscriptions plus future
    # usage/add-on credits.
    return jsonify({
        "error": "Individual content purchases are no longer available. Choose a Prepza subscription."
    }), 410

@app.route("/payment/paystack/callback")
def paystack_callback():
    """
    Browser redirect target after the user finishes on Paystack's hosted
    checkout page. Unlike the old Pesapal callback (which rendered a
    standalone HTML page outside the app), this redirects back INTO the
    SPA with a query param, so PaymentSuccessScreen/PaymentFailureScreen
    become reachable. This is a best-effort, user-is-waiting sync - the
    webhook below is the authoritative source of truth and will also
    resolve the payment even if the user closes the tab here.
    """
    reference = request.args.get("reference") or request.args.get("trxref")
    status = "error"
    if reference:
        try:
            payment = sync_paystack_payment_status(reference)
            status = payment.status if payment else "error"
        except Exception as e:
            print("Paystack callback sync error:", str(e))

    return redirect(f"/?payment_status={status}")


@app.route("/payment/paystack/webhook", methods=["POST"])
def paystack_webhook():
    """
    Server-to-server webhook - the authoritative confirmation, per
    Paystack's own docs ("do not rely on the callback URL alone").
    Verifies the request actually came from Paystack via HMAC-SHA512 over
    the raw request body, keyed with the secret key, compared against the
    X-Paystack-Signature header (constant-time compare) - anyone who
    doesn't have the secret key cannot forge this.
    """
    if not PAYSTACK_SECRET_KEY:
        return jsonify({"error": "Paystack is not configured"}), 503

    raw_body = request.get_data()
    signature = request.headers.get("X-Paystack-Signature", "")
    expected_signature = hmac.new(
        PAYSTACK_SECRET_KEY.encode("utf-8"), raw_body, hashlib.sha512
    ).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected_signature):
        return jsonify({"error": "Invalid signature"}), 401

    payload = request.get_json(silent=True) or {}
    event = payload.get("event")
    reference = (payload.get("data") or {}).get("reference")

    if event == "charge.success" and reference:
        try:
            payment = sync_paystack_payment_status(reference)
            if payment is None:
                _student_subscription_billing["recurring_charge"](db, payload)
        except Exception as e:
            print("Paystack webhook sync error:", str(e))
            return jsonify({"status": "error"}), 500
    elif event == "subscription.create":
        try:
            _student_subscription_billing["subscription_created"](db, payload)
        except Exception as e:
            print("Paystack subscription.create webhook error:", str(e))
            return jsonify({"status": "error"}), 500
    elif event in ("subscription.not_renew", "subscription.disable", "invoice.payment_failed"):
        try:
            _student_subscription_billing["subscription_webhook"](db, event, payload)
        except Exception as e:
            print("Paystack subscription webhook error:", str(e))
            return jsonify({"status": "error"}), 500
    elif event in ("refund.pending", "refund.processing", "refund.needs-attention", "refund.processed", "refund.failed"):
        try:
            _student_subscription_billing["refund_webhook"](db, event, payload)
        except Exception as e:
            print("Paystack refund webhook error:", str(e))
            return jsonify({"status": "error"}), 500
    elif event in ("transfer.success", "transfer.failed", "transfer.reversed") and reference:
        # Ambassador payout confirmation - shares this route with checkout
        # events since Paystack only supports one webhook URL per account.
        transfer_status = event.split(".", 1)[1]  # "success" | "failed" | "reversed"
        payout = AmbassadorPayout.query.filter_by(paystack_transfer_code=reference).first()
        if payout:
            try:
                _apply_paystack_transfer_result(payout, transfer_status)
            except Exception as e:
                print("Paystack transfer webhook sync error:", str(e))
                return jsonify({"status": "error"}), 500
        else:
            print(f"WARNING: Paystack transfer webhook for unknown reference {reference}")
    # Other event types (charge.failed, etc.) don't need action here -
    # a payment stays "pending" until a successful charge resolves it,
    # and pending payments simply never unlock access.

    return jsonify({"status": "ok"}), 200


# ---------- Subscriptions (Chunk 8) ----------

@app.route("/subscription/plans")
def subscription_plans():
    prices = get_plan_prices()
    return jsonify({
        "plans": [
            {"id": "free", "name": "Free", "price": 0, "period": None},
            {"id": "plus", "name": "Plus", "price": prices["plus"], "period": "month"},
            {"id": "pro", "name": "Pro", "price": prices["pro"], "period": "month"},
        ]
    })


@app.route("/subscription/status")
def subscription_status():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    return jsonify(get_user_subscription_status(user_id))


@app.route("/subscription/upgrade", methods=["POST"])
@limiter.limit(
    "1 per 20 seconds",
    key_func=lambda: f"sub_upgrade:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def subscription_upgrade():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True) or {}
    plan = data.get("plan")
    if plan not in ("plus", "pro"):
        return jsonify({"error": "plan must be 'plus' or 'pro'"}), 400

    price = get_plan_prices()[plan]
    if price <= 0:
        return jsonify({"error": "This plan is not currently available"}), 400

    paystack_plan_code = os.environ.get(
        "PAYSTACK_PLUS_PLAN_CODE" if plan == "plus" else "PAYSTACK_PRO_PLAN_CODE"
    )
    if not paystack_plan_code:
        return jsonify({
            "error": "Recurring billing is not configured for this plan yet. "
                     "Admin must add the matching Paystack plan code."
        }), 503

    pending = _student_order_helpers["find_pending_checkout"](user_id, plan=plan)
    if pending and pending.get("checkout_url"):
        return jsonify({
            "redirect_url": pending["checkout_url"],
            "reference": pending["reference"],
            "order_number": pending["order_number"],
            "recovered": True,
        })

    user = db.session.get(User, user_id)
    reference = f"PZA-sub-{plan}-{secrets.token_hex(6)}"

    plan_name = "Plus" if plan == "plus" else "Pro"
    try:
        provider_reference, authorization_url = create_paystack_transaction(
            reference, price, f"Prepza {plan_name} Plan", user,
            paystack_plan_code=paystack_plan_code,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    payment = Payment(
        user_id=user_id,
        content_item_id=None,
        phone_number=data.get("phone_number"),
        amount=price,
        provider="paystack",
        reference=reference,
        provider_reference=provider_reference,
        payment_type="subscription",
        plan=plan,
        status="pending",
    )
    db.session.add(payment)
    db.session.flush()
    _student_order_helpers["create"](payment, item_title=("Plus Plan" if plan == "plus" else "Pro Plan"), checkout_url=authorization_url, requested_payload={
        "payment_type": "subscription",
        "plan": plan,
        "plan_name": "Plus" if plan == "plus" else "Pro",
        "quantity": 1,
    })
    db.session.commit()

    return jsonify({
        # Same alias reasoning as pay_for_content() above.
        "redirect_url": authorization_url,
        "reference": reference,
    })


# ---------- Ambassador / Referral program (Chunk 9) ----------

AMBASSADOR_PAYOUT_DESTINATION_REGEX = re.compile(r"^\+?\d{9,15}$")


def _serialize_ambassador_referral(referral):
    return {
        "id": referral.id,
        "status": referral.status,
        "channel": referral.channel,
        "verified_at": referral.verified_at.isoformat() if referral.verified_at else None,
        "activated_at": referral.activated_at.isoformat() if referral.activated_at else None,
        "converted": referral.first_payment_id is not None,
        "first_payment_at": referral.first_payment_at.isoformat() if referral.first_payment_at else None,
        "commission_rate_applied": referral.commission_rate_applied,
        "commission_amount": referral.commission_amount,
        "unlock_at": referral.unlock_at.isoformat() if referral.unlock_at else None,
        "voided": referral.voided_at is not None,
        "payout_id": referral.payout_id,
        "created_at": referral.created_at.isoformat() if referral.created_at else None,
    }


def _generate_unique_referral_code(display_name):
    for _ in range(10):
        code = generate_referral_code(display_name)
        if not Ambassador.query.filter_by(referral_code=code).first():
            return code
    raise RuntimeError("Could not generate a unique referral code after 10 attempts")


@app.route("/ambassador/apply", methods=["POST"])
@limiter.limit("5 per hour")
@require_csrf
def ambassador_apply():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    settings = get_ambassador_settings()
    if not settings["enabled"]:
        return jsonify({"error": "The ambassador program is not currently accepting applications"}), 503

    user = db.session.get(User, user_id)
    existing = Ambassador.query.filter_by(user_id=user_id).first()

    if existing:
        if existing.status in ("pending", "active"):
            return jsonify({"error": f"You already have a {existing.status} ambassador application"}), 409
        if existing.status == "suspended":
            return jsonify({"error": "Your ambassador account is suspended - contact support to be reinstated"}), 403
        # rejected -> reset back to pending rather than creating a duplicate
        # row, keeping the referral_code stable if it was ever shared.
        existing.status = "pending"
        existing.applied_at = datetime.utcnow()
        existing.rejection_reason = None
        existing.reviewed_by = None
        existing.reviewed_at = None
        db.session.commit()
        return jsonify({
            "id": existing.id, "status": existing.status, "referral_code": existing.referral_code,
        }), 200

    referral_code = _generate_unique_referral_code(user.display_name)
    ambassador = Ambassador(user_id=user_id, referral_code=referral_code, status="pending")
    db.session.add(ambassador)
    db.session.commit()

    return jsonify({
        "id": ambassador.id, "status": ambassador.status, "referral_code": ambassador.referral_code,
    }), 201


@app.route("/ambassador/status")
def ambassador_status():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    ambassador = Ambassador.query.filter_by(user_id=user_id).first()
    if not ambassador:
        return jsonify({"enrolled": False})

    return jsonify({
        "enrolled": True,
        "status": ambassador.status,
        "referral_code": ambassador.referral_code,
        "applied_at": ambassador.applied_at.isoformat() if ambassador.applied_at else None,
        "rejection_reason": ambassador.rejection_reason if ambassador.status == "rejected" else None,
    })


@app.route("/ambassador/dashboard")
def ambassador_dashboard():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    ambassador = Ambassador.query.filter_by(user_id=user_id).first()
    if not ambassador or ambassador.status not in ("active", "suspended"):
        return jsonify({"error": "You are not an active ambassador"}), 403

    referrals = Referral.query.filter_by(ambassador_id=ambassador.id).all()
    referred_count = len(referrals)
    verified_count = sum(1 for r in referrals if r.status in ("verified", "activated"))
    activated_count = sum(1 for r in referrals if r.status == "activated")
    converted = [r for r in referrals if r.first_payment_id and not r.voided_at]
    paying_count = len(converted)
    conversion_rate = round((paying_count / referred_count) * 100, 1) if referred_count else 0.0

    now = datetime.utcnow()
    pending_amount = sum(
        (r.commission_amount or 0) for r in converted
        if r.payout_id is None and r.unlock_at and r.unlock_at > now
    )
    available_amount = sum(
        (r.commission_amount or 0) for r in converted
        if r.payout_id is None and r.unlock_at and r.unlock_at <= now
    )
    paid_amount = db.session.query(func.coalesce(func.sum(AmbassadorPayout.amount), 0)).filter(
        AmbassadorPayout.ambassador_id == ambassador.id, AmbassadorPayout.status == "paid",
    ).scalar()

    settings = get_ambassador_settings()
    current_tier, current_pct = compute_ambassador_tier(paying_count, settings)
    next_threshold = (
        settings["tier2_threshold"] if current_tier == 1
        else settings["tier3_threshold"] if current_tier == 2
        else None
    )

    return jsonify({
        "referral_code": ambassador.referral_code,
        "referral_link": f"{BASE_URL}/signup?ref={ambassador.referral_code}",
        "status": ambassador.status,
        "tier": current_tier,
        "commission_pct": current_pct,
        "next_tier_at": next_threshold,
        "funnel": {
            "referred": referred_count,
            "verified": verified_count,
            "activated": activated_count,
            "paying": paying_count,
            "conversion_rate": conversion_rate,
        },
        "earnings": {
            "pending_kes": pending_amount,
            "available_kes": available_amount,
            "paid_kes": paid_amount,
        },
        "min_payout_kes": settings["min_payout_kes"],
        "payout_hold_days": settings["payout_hold_days"],
    })


@app.route("/ambassador/referral-qr")
def ambassador_referral_qr():
    """Return the logged-in active ambassador's referral link as a self-contained SVG QR."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    ambassador = Ambassador.query.filter_by(user_id=user_id).first()
    if not ambassador or ambassador.status not in ("active", "suspended"):
        return jsonify({"error": "You are not an active ambassador"}), 403

    referral_link = f"{BASE_URL}/signup?ref={ambassador.referral_code}&via=qr"
    import qrcode
    from qrcode.image.svg import SvgPathImage
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
    qr.add_data(referral_link)
    qr.make(fit=True)
    image = qr.make_image(image_factory=SvgPathImage)
    svg = image.to_string()
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "private, max-age=300"})


@app.route("/ambassador/referrals")
def ambassador_referrals():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    ambassador = Ambassador.query.filter_by(user_id=user_id).first()
    if not ambassador:
        return jsonify({"error": "You are not enrolled in the ambassador program"}), 403

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 20

    referrals = (
        Referral.query.filter_by(ambassador_id=ambassador.id)
        .order_by(Referral.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return jsonify({"page": page, "referrals": [_serialize_ambassador_referral(r) for r in referrals]})


@app.route("/ambassador/payouts")
def ambassador_payouts():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    ambassador = Ambassador.query.filter_by(user_id=user_id).first()
    if not ambassador:
        return jsonify({"error": "You are not enrolled in the ambassador program"}), 403

    payouts = (
        AmbassadorPayout.query.filter_by(ambassador_id=ambassador.id)
        .order_by(AmbassadorPayout.requested_at.desc())
        .all()
    )

    return jsonify({"payouts": [
        {
            "id": p.id,
            "amount": p.amount,
            "status": p.status,
            "payout_destination": p.payout_destination,
            "requested_at": p.requested_at.isoformat() if p.requested_at else None,
            "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
            "rejection_reason": p.rejection_reason,
            "paid_at": p.paid_at.isoformat() if p.paid_at else None,
        }
        for p in payouts
    ]})


@app.route("/ambassador/payouts/request", methods=["POST"])
@limiter.limit("5 per hour")
@require_csrf
def ambassador_request_payout():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    ambassador = Ambassador.query.filter_by(user_id=user_id).first()
    if not ambassador or ambassador.status != "active":
        return jsonify({"error": "You are not an active ambassador"}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    payout_destination = (data.get("payout_destination") or "").strip()
    if not AMBASSADOR_PAYOUT_DESTINATION_REGEX.match(payout_destination):
        return jsonify({"error": "payout_destination must be a valid phone number"}), 400

    recipient_first_name = (data.get("recipient_first_name") or "").strip()
    recipient_last_name = (data.get("recipient_last_name") or "").strip()
    if not recipient_first_name or len(recipient_first_name) > 100:
        return jsonify({"error": "recipient_first_name is required and must be 100 characters or fewer"}), 400
    if not recipient_last_name or len(recipient_last_name) > 100:
        return jsonify({"error": "recipient_last_name is required and must be 100 characters or fewer"}), 400

    # An existing pending/approved request already in flight - don't let
    # a student stack multiple requests before the last one is resolved.
    in_flight = AmbassadorPayout.query.filter(
        AmbassadorPayout.ambassador_id == ambassador.id,
        AmbassadorPayout.status.in_(("pending", "approved")),
    ).first()
    if in_flight:
        return jsonify({"error": f"You already have a payout request {in_flight.status}"}), 409

    now = datetime.utcnow()
    eligible = Referral.query.filter(
        Referral.ambassador_id == ambassador.id,
        Referral.first_payment_id.isnot(None),
        Referral.voided_at.is_(None),
        Referral.payout_id.is_(None),
        Referral.unlock_at.isnot(None),
        Referral.unlock_at <= now,
    ).all()

    total = sum((r.commission_amount or 0) for r in eligible)
    settings = get_ambassador_settings()
    if total < settings["min_payout_kes"]:
        return jsonify({
            "error": f"Available balance (KES {total}) is below the minimum payout of KES {settings['min_payout_kes']}"
        }), 400

    payout = AmbassadorPayout(
        ambassador_id=ambassador.id,
        amount=total,
        payout_destination=payout_destination,
        recipient_first_name=recipient_first_name,
        recipient_last_name=recipient_last_name,
        status="pending",
    )
    db.session.add(payout)
    db.session.flush()  # assign payout.id before referrals reference it

    for referral in eligible:
        referral.payout_id = payout.id

    db.session.commit()

    return jsonify({"id": payout.id, "amount": payout.amount, "status": payout.status}), 201


# ---------- Paystack Transfers (Chunk 9, migrated from Kasapay) ----------
# Ambassador commission payouts via Paystack's Transfers API. Two-step,
# unlike Kasapay's single-call B2C: a transfer recipient must exist
# before a transfer can be initiated (POST /transferrecipient once per
# payout, then cached and reused on retries), then POST /transfer moves
# the money. The result is confirmed via the SAME unified webhook route
# used for checkout (/payment/paystack/webhook below), branching on the
# event field - Paystack only supports one webhook URL per account, so
# there's no separate /payment/paystack/payout-webhook route.
# Docs: paystack.com/docs/transfers

PAYSTACK_MOBILE_MONEY_BANK_CODE = os.environ.get("PAYSTACK_MOBILE_MONEY_BANK_CODE", "MPESA")
# "MPESA" is Paystack's Kenya mobile-money bank_code for M-Pesa
# recipients - confirmed via Paystack's Kenya docs. account_reference is
# only needed for Paybill/Till transfers, not personal M-Pesa numbers,
# so it's correctly omitted from the recipient payload below.


def _ensure_paystack_transfer_recipient(payout):
    """
    Creates (and caches) a Paystack transfer recipient for this payout's
    destination phone number. Idempotent - if payout.paystack_recipient_code
    is already set, reuses it rather than creating a duplicate recipient
    on a retried approval.
    """
    if payout.paystack_recipient_code:
        return payout.paystack_recipient_code

    recipient_name = f"{payout.recipient_first_name} {payout.recipient_last_name}"
    payload = {
        "type": "mobile_money",
        "name": recipient_name,
        "account_number": payout.payout_destination,
        "bank_code": PAYSTACK_MOBILE_MONEY_BANK_CODE,
        "currency": "KES",
    }
    data = paystack_request("POST", "/transferrecipient", json=payload)
    recipient_code = (data.get("data") or {}).get("recipient_code")
    if not recipient_code:
        raise RuntimeError(f"Paystack recipient creation failed: {data}")

    payout.paystack_recipient_code = recipient_code
    db.session.commit()
    return recipient_code


def initiate_paystack_transfer(payout):
    """
    Submits a Paystack transfer for one approved AmbassadorPayout,
    creating a transfer recipient first if needed. Returns
    (transfer_reference, transfer_status) - transfer_reference is OUR
    reference, stored on payout.paystack_transfer_code for later
    lookups (webhook + manual sync). transfer_status is Paystack's own
    status string - in sandbox this is already "success" by the time
    this returns, since test-mode transfers auto-succeed with no OTP
    step at all; once live keys are in use it will typically come back
    "pending" until OTP confirmation is disabled under Settings ->
    Preferences, or via the Transfer Control API's /transfer/disable_otp.
    """
    recipient_code = _ensure_paystack_transfer_recipient(payout)
    reference = f"PZA-amb-{payout.id}-{secrets.token_hex(4)}"

    payload = {
        "source": "balance",
        "amount": payout.amount * 100,
        "recipient": recipient_code,
        "reason": "Prepza ambassador commission payout",
        "reference": reference,
    }
    data = paystack_request("POST", "/transfer", json=payload)
    tx = data.get("data") or {}
    if not tx.get("transfer_code"):
        raise RuntimeError(f"Paystack transfer initiation failed: {data}")
    return reference, tx.get("status")


def _apply_paystack_transfer_result(payout, transfer_status):
    """
    Shared by the webhook and the manual status-poll route. Idempotent -
    no-ops if the payout is already resolved to 'paid', so a retried
    webhook or a repeated manual poll can never double-apply a result.
    """
    if payout.status == "paid":
        return payout

    if transfer_status == "success":
        payout.status = "paid"
        payout.paid_at = datetime.utcnow()
    elif transfer_status in ("failed", "reversed"):
        # Release the bundled referrals so the ambassador's commissions
        # become requestable again, same pattern as admin_reject_ambassador_payout.
        payout.status = "rejected"
        payout.rejection_reason = f"Payout {transfer_status} at Paystack"
        Referral.query.filter_by(payout_id=payout.id).update({"payout_id": None})
    # else: still pending/otp/processing on Paystack's side - leave the
    # payout as 'approved' and check again later (webhook retry or manual sync).

    db.session.commit()
    return payout


def sync_paystack_transfer_status(payout):
    """Polls Paystack's verify-transfer endpoint directly - a manual
    fallback since webhooks can occasionally be missed."""
    if not payout.paystack_transfer_code or payout.status == "paid":
        return payout
    data = paystack_request("GET", f"/transfer/verify/{payout.paystack_transfer_code}")
    tx = data.get("data") or {}
    return _apply_paystack_transfer_result(payout, tx.get("status"))


# ---------- Admin: ambassador management (Chunk 9) ----------

@app.route("/admin/ambassadors")
@require_admin
def admin_list_ambassadors():
    """Lists ambassadors, optionally filtered by ?status= (pending |
    active | suspended | rejected). Newest applications first."""
    status_filter = request.args.get("status")

    query = Ambassador.query
    if status_filter:
        query = query.filter_by(status=status_filter)

    ambassadors = query.order_by(Ambassador.applied_at.desc()).all()

    result = []
    for a in ambassadors:
        user = db.session.get(User, a.user_id)
        result.append({
            "id": a.id,
            "user_id": a.user_id,
            "email": user.email if user else None,
            "display_name": _display_name(user) if user else None,
            "referral_code": a.referral_code,
            "status": a.status,
            "applied_at": a.applied_at.isoformat() if a.applied_at else None,
            "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
            "rejection_reason": a.rejection_reason,
        })

    return jsonify({"ambassadors": result})


@app.route("/admin/ambassadors/<int:ambassador_id>")
@require_admin
def admin_get_ambassador(ambassador_id):
    """
    Full detail view for one ambassador - their referral list with
    per-referral commission/void state, meant for the fraud-review
    pass before approving a payout (self-referral patterns, unusually
    fast conversions, etc. are all visible here per-referral).
    """
    ambassador = db.session.get(Ambassador, ambassador_id)
    if not ambassador:
        return jsonify({"error": "Ambassador not found"}), 404

    user = db.session.get(User, ambassador.user_id)
    referrals = (
        Referral.query.filter_by(ambassador_id=ambassador.id)
        .order_by(Referral.created_at.desc())
        .all()
    )

    referral_rows = []
    for r in referrals:
        referred_user = db.session.get(User, r.referred_user_id)
        referral_rows.append({
            "id": r.id,
            "referred_email": referred_user.email if referred_user else None,
            "status": r.status,
            "channel": r.channel,
            "converted": r.first_payment_id is not None,
            "commission_amount": r.commission_amount,
            "unlock_at": r.unlock_at.isoformat() if r.unlock_at else None,
            "voided": r.voided_at is not None,
            "void_reason": r.void_reason,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    converted = [r for r in referrals if r.first_payment_id and not r.voided_at]
    total_commission_awarded = sum((r.commission_amount or 0) for r in converted)
    total_paid = db.session.query(func.coalesce(func.sum(AmbassadorPayout.amount), 0)).filter(
        AmbassadorPayout.ambassador_id == ambassador.id, AmbassadorPayout.status == "paid",
    ).scalar()

    return jsonify({
        "id": ambassador.id,
        "user_id": ambassador.user_id,
        "email": user.email if user else None,
        "display_name": _display_name(user) if user else None,
        "referral_code": ambassador.referral_code,
        "status": ambassador.status,
        "applied_at": ambassador.applied_at.isoformat() if ambassador.applied_at else None,
        "reviewed_by": ambassador.reviewed_by,
        "reviewed_at": ambassador.reviewed_at.isoformat() if ambassador.reviewed_at else None,
        "rejection_reason": ambassador.rejection_reason,
        "referred_count": len(referrals),
        "paying_count": len(converted),
        "total_commission_awarded_kes": total_commission_awarded,
        "total_paid_kes": total_paid,
        "referrals": referral_rows,
    })


@app.route("/admin/ambassadors/<int:ambassador_id>/approve", methods=["POST"])
@require_csrf
@require_admin
def admin_approve_ambassador(ambassador_id):
    acting_admin_id = session.get("user_id")

    ambassador = db.session.get(Ambassador, ambassador_id)
    if not ambassador:
        return jsonify({"error": "Ambassador not found"}), 404
    if ambassador.status != "pending":
        return jsonify({"error": f"Ambassador is not pending (status: {ambassador.status})"}), 400

    ambassador.status = "active"
    ambassador.reviewed_by = acting_admin_id
    ambassador.reviewed_at = datetime.utcnow()
    ambassador.rejection_reason = None
    db.session.commit()

    return jsonify({"id": ambassador.id, "status": ambassador.status})


@app.route("/admin/ambassadors/<int:ambassador_id>/reject", methods=["POST"])
@require_csrf
@require_admin
def admin_reject_ambassador(ambassador_id):
    acting_admin_id = session.get("user_id")

    ambassador = db.session.get(Ambassador, ambassador_id)
    if not ambassador:
        return jsonify({"error": "Ambassador not found"}), 404
    if ambassador.status != "pending":
        return jsonify({"error": f"Ambassador is not pending (status: {ambassador.status})"}), 400

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason or len(reason) > 500:
        return jsonify({"error": "reason is required and must be 500 characters or fewer"}), 400

    ambassador.status = "rejected"
    ambassador.rejection_reason = reason
    ambassador.reviewed_by = acting_admin_id
    ambassador.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"id": ambassador.id, "status": ambassador.status})


@app.route("/admin/ambassadors/<int:ambassador_id>/suspend", methods=["POST"])
@require_csrf
@require_admin
def admin_suspend_ambassador(ambassador_id):
    """
    Suspending does NOT touch existing Referral/commission rows or
    in-flight payouts - it only blocks new applications-worth of
    trust (dashboard access, new payout requests). Any pending payout
    still goes through the normal admin approve/reject flow.
    """
    acting_admin_id = session.get("user_id")

    ambassador = db.session.get(Ambassador, ambassador_id)
    if not ambassador:
        return jsonify({"error": "Ambassador not found"}), 404
    if ambassador.status != "active":
        return jsonify({"error": f"Only active ambassadors can be suspended (status: {ambassador.status})"}), 400

    ambassador.status = "suspended"
    ambassador.reviewed_by = acting_admin_id
    ambassador.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"id": ambassador.id, "status": ambassador.status})


@app.route("/admin/ambassadors/<int:ambassador_id>/reinstate", methods=["POST"])
@require_csrf
@require_admin
def admin_reinstate_ambassador(ambassador_id):
    acting_admin_id = session.get("user_id")

    ambassador = db.session.get(Ambassador, ambassador_id)
    if not ambassador:
        return jsonify({"error": "Ambassador not found"}), 404
    if ambassador.status != "suspended":
        return jsonify({"error": f"Only suspended ambassadors can be reinstated (status: {ambassador.status})"}), 400

    ambassador.status = "active"
    ambassador.reviewed_by = acting_admin_id
    ambassador.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"id": ambassador.id, "status": ambassador.status})


# ---------- Admin: ambassador payouts (Chunk 9) ----------

@app.route("/admin/payouts")
@require_admin
def admin_list_ambassador_payouts():
    """Lists ambassador payout requests, optionally filtered by
    ?status= (pending | approved | rejected | paid)."""
    status_filter = request.args.get("status")

    query = AmbassadorPayout.query
    if status_filter:
        query = query.filter_by(status=status_filter)

    payouts = query.order_by(AmbassadorPayout.requested_at.desc()).all()

    result = []
    for p in payouts:
        ambassador = db.session.get(Ambassador, p.ambassador_id)
        user = db.session.get(User, ambassador.user_id) if ambassador else None
        result.append({
            "id": p.id,
            "ambassador_id": p.ambassador_id,
            "email": user.email if user else None,
            "amount": p.amount,
            "status": p.status,
            "payout_destination": p.payout_destination,
            "paystack_transfer_code": p.paystack_transfer_code,
            "requested_at": p.requested_at.isoformat() if p.requested_at else None,
            "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
            "rejection_reason": p.rejection_reason,
            "paid_at": p.paid_at.isoformat() if p.paid_at else None,
        })

    return jsonify({"payouts": result})


@app.route("/admin/payouts/<int:payout_id>/approve", methods=["POST"])
@require_csrf
@require_admin
def admin_approve_ambassador_payout(payout_id):
    """
    Greenlights a payout request AND fires the actual Paystack transfer
    in the same action - approving IS sending, which is the fraud
    checkpoint you get instead of a separate "send" button. If the
    Paystack request fails, nothing is marked approved and the payout
    stays 'pending', so the admin can fix whatever's wrong (balance,
    recipient details) and retry the same click.

    In sandbox, test-mode transfers always auto-succeed - the payout may
    already be 'paid' by the time this returns. Once switching to live
    keys, a successful call here only means Paystack ACCEPTED the
    transfer for processing - the real outcome arrives later via
    /payment/paystack/webhook, or can be checked manually via
    /admin/payouts/<id>/sync-status.
    """
    acting_admin_id = session.get("user_id")

    payout = db.session.get(AmbassadorPayout, payout_id)
    if not payout:
        return jsonify({"error": "Payout not found"}), 404
    if payout.status != "pending":
        return jsonify({"error": f"Payout is not pending (status: {payout.status})"}), 400

    try:
        transfer_reference, transfer_status = initiate_paystack_transfer(payout)
    except Exception as e:
        return jsonify({"error": f"Paystack transfer request failed: {e}"}), 502

    payout.status = "approved"
    payout.paystack_transfer_code = transfer_reference
    payout.reviewed_by = acting_admin_id
    payout.reviewed_at = datetime.utcnow()
    db.session.commit()

    if transfer_status:
        _apply_paystack_transfer_result(payout, transfer_status)

    return jsonify({
        "id": payout.id, "status": payout.status, "paystack_transfer_code": payout.paystack_transfer_code,
    })


@app.route("/admin/payouts/<int:payout_id>/reject", methods=["POST"])
@require_csrf
@require_admin
def admin_reject_ambassador_payout(payout_id):
    """
    Rejects a payout request and releases every Referral that had been
    bundled into it (payout_id back to NULL), so the ambassador can
    request again later - e.g. once a flagged referral is resolved -
    without losing the rest of their already-unlocked commissions.
    """
    acting_admin_id = session.get("user_id")

    payout = db.session.get(AmbassadorPayout, payout_id)
    if not payout:
        return jsonify({"error": "Payout not found"}), 404
    if payout.status != "pending":
        return jsonify({"error": f"Payout is not pending (status: {payout.status})"}), 400

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason or len(reason) > 500:
        return jsonify({"error": "reason is required and must be 500 characters or fewer"}), 400

    payout.status = "rejected"
    payout.rejection_reason = reason
    payout.reviewed_by = acting_admin_id
    payout.reviewed_at = datetime.utcnow()

    Referral.query.filter_by(payout_id=payout.id).update({"payout_id": None})

    db.session.commit()

    return jsonify({"id": payout.id, "status": payout.status})


@app.route("/admin/payouts/<int:payout_id>/sync-status", methods=["POST"])
@require_csrf
@require_admin
def admin_sync_ambassador_payout_status(payout_id):
    """
    Manually re-checks a payout's status directly against Paystack's
    verify-transfer endpoint - useful if a webhook was missed. Safe to
    call any time after a payout has a paystack_transfer_code (i.e.
    after it's been approved/sent).
    """
    payout = db.session.get(AmbassadorPayout, payout_id)
    if not payout:
        return jsonify({"error": "Payout not found"}), 404
    if not payout.paystack_transfer_code:
        return jsonify({"error": "This payout has not been sent to Paystack yet"}), 400

    try:
        sync_paystack_transfer_status(payout)
    except Exception as e:
        return jsonify({"error": f"Paystack status check failed: {e}"}), 502

    return jsonify({
        "id": payout.id,
        "status": payout.status,
        "rejection_reason": payout.rejection_reason,
        "paid_at": payout.paid_at.isoformat() if payout.paid_at else None,
    })


# ---------- Chat routes (Chunk 6) ----------

CHAT_MESSAGE_MAX = 3000
# Retained as the reference plaintext-length limit surfaced in the
# frontend UI (e.g. a character counter) - no longer what the
# server itself validates against, since body is ciphertext.
CHAT_MESSAGE_CIPHERTEXT_MAX = 20000
# What send_message() actually checks. Generous ceiling accounting
# for AES-GCM overhead (16-byte tag) + base64 encoding (~4/3
# expansion) + worst-case 4-byte-per-character UTF-8 plaintext at
# the CHAT_MESSAGE_MAX length - guards against abuse/garbage, not a
# tight format check.
CHAT_GROUP_NAME_MAX = 100
CHAT_MESSAGE_PAGE_SIZE = 50
CHAT_MESSAGE_SEARCH_LIMIT = 50


def _active_participant(conversation_id, user_id):
    """Returns the caller's ConversationParticipant row if they are a
    current (non-left) member of the conversation, else None."""
    return ConversationParticipant.query.filter_by(
        conversation_id=conversation_id, user_id=user_id, left_at=None,
    ).first()


def _conversation_display_name(conversation, viewer_id):
    """Group conversations use their own name. 1:1 conversations are
    named after the other participant, so the viewer never has to name
    their own DMs."""
    if conversation.is_group:
        return conversation.name or "Study Group"

    other = (
        ConversationParticipant.query
        .filter(
            ConversationParticipant.conversation_id == conversation.id,
            ConversationParticipant.user_id != viewer_id,
        )
        .first()
    )
    if not other:
        return "Conversation"
    other_user = db.session.get(User, other.user_id)
    return _display_name(other_user) if other_user else "Deleted user"


def _serialize_message(message, attachment=None):
    """
    attachment is an optional pre-fetched MessageAttachment - callers
    that serialize many messages at once (list_messages, search_messages)
    batch-fetch attachments up front and pass the matching one in here,
    rather than this function querying per-message (would be an N+1 on
    a 50-row page).
    """
    attachment_data = None
    if attachment and not message.is_deleted:
        attachment_data = {
            "id": attachment.id,
            "file_type": attachment.file_type,
            "original_filename": attachment.original_filename,
            "file_size_bytes": attachment.file_size_bytes,
            "view_url": get_cached_chat_attachment_url(attachment),
        }
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_id": message.sender_id,
        "body": message.body if not message.is_deleted else None,
        "nonce": message.nonce if not message.is_deleted else None,
        "key_epoch": message.e2ee_key_epoch if not message.is_deleted else None,
        "is_deleted": message.is_deleted,
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "edited_at": message.edited_at.isoformat() if message.edited_at else None,
        "attachment": attachment_data,
    }


def _serialize_conversation_detail(conversation, viewer_id):
    """
    Full detail payload for GET /chats/<id> - the display name (reusing
    the same logic /chats uses), the active (non-left) participant list
    with display names, and who created it. Exists so the frontend can
    label group-chat message senders and show a real member count/
    creator in chat-options, without a message-by-message name lookup.
    """
    participant_rows = (
        ConversationParticipant.query
        .filter_by(conversation_id=conversation.id, left_at=None)
        .all()
    )
    participants = []
    for p in participant_rows:
        member = db.session.get(User, p.user_id)
        participants.append({
            "user_id": p.user_id,
            "display_name": _display_name(member) if member else "Deleted user",
            "role": p.role,
        })
    creator = db.session.get(User, conversation.created_by)
    viewer_participant = next((p for p in participant_rows if p.user_id == viewer_id), None)
    return {
        "id": conversation.id,
        "is_group": conversation.is_group,
        "name": _conversation_display_name(conversation, viewer_id),
        "created_by": conversation.created_by,
        "created_by_name": _display_name(creator) if creator else "Deleted user",
        "member_count": len(participant_rows),
        "participants": participants,
        "viewer_muted": bool(viewer_participant.muted) if viewer_participant else False,
    }


@app.route("/chats")
def list_chats():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    participations = (
        ConversationParticipant.query
        .filter_by(user_id=user_id, left_at=None)
        .all()
    )

    result = []
    for p in participations:
        conversation = db.session.get(Conversation, p.conversation_id)
        if not conversation:
            continue

        last_message = (
            Message.query
            .filter_by(conversation_id=conversation.id, is_deleted=False)
            .order_by(Message.created_at.desc())
            .first()
        )

        unread_query = Message.query.filter(
            Message.conversation_id == conversation.id,
            Message.sender_id != user_id,
        )
        if p.last_read_at:
            unread_query = unread_query.filter(Message.created_at > p.last_read_at)
        unread_count = unread_query.count()

        # A pending request directed AT me (I didn't create it) stays
        # out of the normal chat list until I accept it via
        # /message-requests - the requester still sees it in theirs.
        if conversation.status == "pending" and conversation.created_by != user_id:
            continue

        last_attachment = None
        if last_message:
            last_attachment = (
                MessageAttachment.query
                .filter_by(message_id=last_message.id, status="ready")
                .first()
            )

        peer_user_id = None
        peer_display_name = None
        if not conversation.is_group:
            peer = (
                ConversationParticipant.query
                .filter(
                    ConversationParticipant.conversation_id == conversation.id,
                    ConversationParticipant.user_id != user_id,
                    ConversationParticipant.left_at.is_(None),
                )
                .first()
            )
            if peer:
                peer_user_id = peer.user_id
                peer_user = db.session.get(User, peer.user_id)
                peer_display_name = _display_name(peer_user) if peer_user else None

        result.append({
            "id": conversation.id,
            "is_group": conversation.is_group,
            "name": _conversation_display_name(conversation, user_id),
            "peer_user_id": peer_user_id,
            "last_message": last_message.body if last_message else None,
            "last_message_at": last_message.created_at.isoformat() if last_message else None,
            "last_message_sender_name": (
                _display_name(db.session.get(User, last_message.sender_id))
                if last_message and last_message.sender_id
                else None
            ),
            "last_message_sender_id": last_message.sender_id if last_message else None,
            "last_message_read_by_all": (
                bool(last_message)
                and last_message.sender_id == user_id
                and all(
                    participant.last_read_at is not None
                    and participant.last_read_at >= last_message.created_at
                    for participant in ConversationParticipant.query.filter(
                        ConversationParticipant.conversation_id == conversation.id,
                        ConversationParticipant.user_id != user_id,
                        ConversationParticipant.left_at.is_(None),
                    ).all()
                )
            ) if last_message else False,
            "last_message_file_type": last_attachment.file_type if last_attachment else None,
            "last_message_filename": last_attachment.original_filename if last_attachment else None,
            "unread_count": unread_count,
            "status": conversation.status,
        })

    result.sort(key=lambda c: c["last_message_at"] or "", reverse=True)
    return jsonify({"chats": result})


@app.route("/chats", methods=["POST"])
@limiter.limit("30 per hour")
@require_csrf
def create_chat():
    """
    Starts a conversation. For a non-group chat between exactly 2
    users, reuses an existing conversation between the same pair
    instead of creating a duplicate every time someone taps "message"
    on the same classmate.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    is_group = bool(data.get("is_group"))
    participant_ids = data.get("participant_ids")
    name = (data.get("name") or "").strip()

    if not isinstance(participant_ids, list) or not participant_ids:
        return jsonify({"error": "participant_ids must be a non-empty list"}), 400
    try:
        participant_ids = {int(pid) for pid in participant_ids}
    except (TypeError, ValueError):
        return jsonify({"error": "participant_ids must be integers"}), 400
    participant_ids.discard(user_id)
    if not participant_ids:
        return jsonify({"error": "Cannot start a conversation with only yourself"}), 400

    valid_users = User.query.filter(User.id.in_(participant_ids)).count()
    if valid_users != len(participant_ids):
        return jsonify({"error": "One or more participants were not found"}), 404

    if is_group:
        if not name or len(name) > CHAT_GROUP_NAME_MAX:
            return jsonify({"error": f"Group name is required and must be {CHAT_GROUP_NAME_MAX} characters or fewer"}), 400
    else:
        if len(participant_ids) != 1:
            return jsonify({"error": "Direct chats must have exactly one other participant"}), 400
        other_id = next(iter(participant_ids))

        # Reused regardless of status - a second attempt by the same
        # sender while a request is still pending just returns the
        # same pending conversation instead of creating a duplicate.
        existing = (
            db.session.query(Conversation.id)
            .join(ConversationParticipant, ConversationParticipant.conversation_id == Conversation.id)
            .filter(Conversation.is_group.is_(False))
            .filter(ConversationParticipant.user_id.in_([user_id, other_id]))
            .group_by(Conversation.id)
            .having(func.count(ConversationParticipant.user_id.distinct()) == 2)
            .first()
        )
        if existing:
            return jsonify({"id": existing.id, "reused": True}), 200

    # A conversation with exactly one OTHER participant functions like a
    # direct message regardless of is_group, so who_can_message="followers"
    # has to be enforced here too - otherwise it could be dodged just by
    # setting is_group=true and giving it a name. Groups with 2+ other
    # participants (3+ total members) are a different, legitimate case
    # (a real study group someone was added to) and are left alone.
    # Instagram-style message requests: rather than hard-blocking with
    # a 403, a non-follower's message just creates the conversation as
    # "pending" - see the Conversation.status column and
    # GET /message-requests / accept-request / decline-request below.
    conversation_status = "accepted"
    if len(participant_ids) == 1:
        only_other_id = next(iter(participant_ids))
        only_other_user = db.session.get(User, only_other_id)
        if only_other_user and only_other_user.who_can_message == "followers":
            sender_is_follower = Follow.query.filter_by(
                follower_id=user_id, followed_id=only_other_id
            ).first() is not None
            if not sender_is_follower:
                conversation_status = "pending"

    conversation = Conversation(
        is_group=is_group,
        name=name if is_group else None,
        created_by=user_id,
        status=conversation_status,
    )
    db.session.add(conversation)
    db.session.flush()

    all_member_ids = participant_ids | {user_id}
    for member_id in all_member_ids:
        db.session.add(ConversationParticipant(
            conversation_id=conversation.id,
            user_id=member_id,
            role="admin" if (is_group and member_id == user_id) else "member",
        ))

    db.session.commit()
    return jsonify({"id": conversation.id, "reused": False, "status": conversation_status}), 201


@app.route("/message-requests")
def list_message_requests():
    """
    Pending 1:1 conversations directed AT the logged-in user - the
    who_can_message="followers" equivalent of /follow-requests. The
    requester already sees these in their normal /chats list; only
    the receiver's view is gated until they accept or decline.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    participations = (
        ConversationParticipant.query
        .filter_by(user_id=user_id, left_at=None)
        .all()
    )

    result = []
    for p in participations:
        conversation = db.session.get(Conversation, p.conversation_id)
        if not conversation or conversation.is_group or conversation.status != "pending":
            continue
        if conversation.created_by == user_id:
            continue

        requester = db.session.get(User, conversation.created_by)
        # Message bodies are E2EE ciphertext - the server can't preview
        # content, same reasoning as the push-notification fallback
        # elsewhere in this file.
        has_message = Message.query.filter_by(conversation_id=conversation.id, is_deleted=False).first() is not None
        result.append({
            "conversation_id": conversation.id,
            "requester_id": conversation.created_by,
            "requester_display_name": _display_name(requester) if requester else "Deleted user",
            "has_message": has_message,
            "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
        })

    result.sort(key=lambda r: r["created_at"] or "", reverse=True)
    return jsonify({"requests": result})


@app.route("/chats/<int:conversation_id>/accept-request", methods=["POST"])
@require_csrf
def accept_message_request(conversation_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    conversation = db.session.get(Conversation, conversation_id)
    if not conversation or conversation.is_group or conversation.status != "pending" or conversation.created_by == user_id:
        return jsonify({"error": "Message request not found"}), 404
    if not _active_participant(conversation_id, user_id):
        return jsonify({"error": "Message request not found"}), 404

    conversation.status = "accepted"
    db.session.commit()

    requester_id = conversation.created_by
    accepter = db.session.get(User, user_id)
    if should_notify(requester_id, "community"):
        db.session.add(Notification(
            user_id=requester_id,
            type="message_request_accepted",
            title="Message request accepted",
            body=f"{_display_name(accepter)} accepted your message request",
            related_type="conversation",
            related_id=conversation.id,
        ))
        db.session.commit()
        send_push_notification(
            requester_id,
            "Message request accepted",
            f"{_display_name(accepter)} accepted your message request",
        )

    return jsonify({"message": "Accepted", "id": conversation.id})


@app.route("/chats/<int:conversation_id>/decline-request", methods=["POST"])
@require_csrf
def decline_message_request(conversation_id):
    """
    Declining deletes the pending conversation outright (cascades to
    its participants/messages) rather than leaving a "declined"
    marker - same silent-dismiss convention as follow-request
    declines, and lets the same sender try again later with a clean
    conversation instead of being permanently blocked.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    conversation = db.session.get(Conversation, conversation_id)
    if not conversation or conversation.is_group or conversation.status != "pending" or conversation.created_by == user_id:
        return jsonify({"error": "Message request not found"}), 404
    if not _active_participant(conversation_id, user_id):
        return jsonify({"error": "Message request not found"}), 404

    db.session.delete(conversation)
    db.session.commit()

    return jsonify({"message": "Declined"})


@app.route("/chats/<int:conversation_id>")
def get_chat_detail(conversation_id):
    """
    Single-conversation detail: display name, participant list (with
    names), member count, and creator - powers the chat-detail header,
    group-message sender labels, and chat-options screen on the
    frontend. 404s (not 403) for a non-participant, same "don't confirm
    existence" pattern as other conversation routes.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if not _active_participant(conversation_id, user_id):
        return jsonify({"error": "Conversation not found"}), 404

    conversation = db.session.get(Conversation, conversation_id)
    if not conversation:
        return jsonify({"error": "Conversation not found"}), 404

    return jsonify(_serialize_conversation_detail(conversation, user_id))


@app.route("/chats/<int:conversation_id>/messages")
def list_messages(conversation_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if not _active_participant(conversation_id, user_id):
        return jsonify({"error": "Conversation not found"}), 404

    before_id = request.args.get("before_id", type=int)
    preview_only = request.args.get("preview") == "1"
    query = Message.query.filter_by(conversation_id=conversation_id)
    if before_id:
        query = query.filter(Message.id < before_id)

    messages = (
        query.order_by(Message.created_at.desc())
        .limit(1 if preview_only else CHAT_MESSAGE_PAGE_SIZE)
        .all()
    )
    messages.reverse()  # oldest-first for the client's scroll-down feed

    message_ids = [m.id for m in messages]
    attachments_by_message = {
        a.message_id: a
        for a in MessageAttachment.query.filter(
            MessageAttachment.message_id.in_(message_ids),
            MessageAttachment.status == "ready",
        ).all()
    } if message_ids else {}

    return jsonify({
        "messages": [_serialize_message(m, attachments_by_message.get(m.id)) for m in messages]
    })


@app.route("/chats/<int:conversation_id>/messages/search")
def search_messages(conversation_id):
    """
    Substring search of this conversation's own message history. Scoped
    to one conversation only (no cross-chat search) - same membership
    gate as every other /chats/<id> route. Returns newest-first, capped
    at CHAT_MESSAGE_SEARCH_LIMIT - this is a search result, not a feed,
    so no before_id pagination like list_messages() has.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if not _active_participant(conversation_id, user_id):
        return jsonify({"error": "Conversation not found"}), 404

    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"messages": []})

    messages = (
        Message.query.filter(
            Message.conversation_id == conversation_id,
            Message.is_deleted.is_(False),
            Message.body.ilike(f"%{q}%"),
        )
        .order_by(Message.created_at.desc())
        .limit(CHAT_MESSAGE_SEARCH_LIMIT)
        .all()
    )

    message_ids = [m.id for m in messages]
    attachments_by_message = {
        a.message_id: a
        for a in MessageAttachment.query.filter(
            MessageAttachment.message_id.in_(message_ids),
            MessageAttachment.status == "ready",
        ).all()
    } if message_ids else {}

    return jsonify({
        "messages": [_serialize_message(m, attachments_by_message.get(m.id)) for m in messages]
    })


@app.route("/chats/<int:conversation_id>/messages", methods=["POST"])
@limiter.limit("120 per hour")
@require_csrf
def send_message(conversation_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if not _active_participant(conversation_id, user_id):
        return jsonify({"error": "Conversation not found"}), 404

    pending_check = db.session.get(Conversation, conversation_id)
    if pending_check and pending_check.status == "pending" and pending_check.created_by != user_id:
        return jsonify({"error": "Accept this message request before replying"}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    client_message_id = (data.get("client_message_id") or "").strip() or None
    if client_message_id is not None:
        if len(client_message_id) > 128 or not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", client_message_id):
            return jsonify({"error": "client_message_id is invalid"}), 400
        if _ensure_chat_idempotency_schema():
            existing_message_id = db.session.execute(
                text("""
                    SELECT message_id
                    FROM chat_message_idempotency
                    WHERE conversation_id = :conversation_id
                      AND sender_id = :sender_id
                      AND client_message_id = :client_message_id
                """),
                {
                    "conversation_id": conversation_id,
                    "sender_id": user_id,
                    "client_message_id": client_message_id,
                },
            ).scalar_one_or_none()
            if existing_message_id:
                existing_message = db.session.get(Message, int(existing_message_id))
                if existing_message:
                    existing_attachment = MessageAttachment.query.filter_by(
                        message_id=existing_message.id,
                        status="ready",
                    ).first()
                    return jsonify(_serialize_message(existing_message, existing_attachment)), 200
                db.session.execute(
                    text("""
                        DELETE FROM chat_message_idempotency
                        WHERE conversation_id = :conversation_id
                          AND sender_id = :sender_id
                          AND client_message_id = :client_message_id
                    """),
                    {
                        "conversation_id": conversation_id,
                        "sender_id": user_id,
                        "client_message_id": client_message_id,
                    },
                )
                db.session.commit()

    body = (data.get("body") or "").strip() or None
    nonce = (data.get("nonce") or "").strip() or None
    conversation = db.session.get(Conversation, conversation_id)
    e2ee_mode = getattr(conversation, "e2ee_mode", "legacy") if conversation else "legacy"
    requested_key_epoch = data.get("key_epoch")
    if requested_key_epoch is not None and (not isinstance(requested_key_epoch, int) or isinstance(requested_key_epoch, bool) or requested_key_epoch < 1):
        return jsonify({"error": "key_epoch must be a positive integer"}), 400
    if e2ee_mode == "group_v1":
        current_epoch = db.session.execute(text("SELECT key_epoch FROM conversation WHERE id = :conversation_id"), {"conversation_id": conversation_id}).scalar_one_or_none()
        current_epoch = int(current_epoch or 0)
        if not body or not nonce:
            return jsonify({"error": "Encrypted group messages require body and nonce"}), 400
        if requested_key_epoch != current_epoch:
            return jsonify({"error": "Encrypted group message key epoch is stale; retry with the current group key", "key_epoch": current_epoch}), 409
    if body and len(body) > CHAT_MESSAGE_CIPHERTEXT_MAX:
        return jsonify({"error": f"Message must be {CHAT_MESSAGE_CIPHERTEXT_MAX} characters or fewer"}), 400
    if body and not nonce:
        return jsonify({"error": "nonce is required alongside an encrypted body"}), 400

    attachment_id = data.get("attachment_id")
    attachment = None
    if attachment_id is not None:
        if not isinstance(attachment_id, int) or isinstance(attachment_id, bool):
            return jsonify({"error": "attachment_id must be an integer"}), 400
        attachment = db.session.get(MessageAttachment, attachment_id)
        if (
            not attachment
            or attachment.conversation_id != conversation_id
            or attachment.uploaded_by_user_id != user_id
            or attachment.status != "ready"
            or attachment.message_id is not None
        ):
            return jsonify({"error": "Attachment not found or already sent"}), 404

    if not body and not attachment:
        return jsonify({"error": "Message must include text or an attachment"}), 400

    message = Message(conversation_id=conversation_id, sender_id=user_id, body=body, nonce=nonce, e2ee_key_epoch=requested_key_epoch if e2ee_mode == "group_v1" else 0)
    db.session.add(message)
    db.session.flush()  # assign message.id before linking the attachment

    if attachment:
        attachment.message_id = message.id

    if client_message_id and _ensure_chat_idempotency_schema():
        db.session.execute(
            text("""
                INSERT INTO chat_message_idempotency
                    (conversation_id, sender_id, client_message_id, message_id)
                VALUES
                    (:conversation_id, :sender_id, :client_message_id, :message_id)
                ON CONFLICT (conversation_id, sender_id, client_message_id) DO NOTHING
            """),
            {
                "conversation_id": conversation_id,
                "sender_id": user_id,
                "client_message_id": client_message_id,
                "message_id": message.id,
            },
        )
        mapped_message_id = db.session.execute(
            text("""
                SELECT message_id
                FROM chat_message_idempotency
                WHERE conversation_id = :conversation_id
                  AND sender_id = :sender_id
                  AND client_message_id = :client_message_id
            """),
            {
                "conversation_id": conversation_id,
                "sender_id": user_id,
                "client_message_id": client_message_id,
            },
        ).scalar_one_or_none()
        if mapped_message_id and int(mapped_message_id) != message.id:
            db.session.rollback()
            existing_message = db.session.get(Message, int(mapped_message_id))
            if existing_message:
                existing_attachment = MessageAttachment.query.filter_by(
                    message_id=existing_message.id,
                    status="ready",
                ).first()
                return jsonify(_serialize_message(existing_message, existing_attachment)), 200
            return jsonify({"error": "Message idempotency conflict; retry"}), 409

    if conversation:
        conversation.updated_at = datetime.utcnow()

    db.session.commit()

    # Chat push follows a DM pattern (like Instagram) rather than the
    # in-app Notification feed - push only, no Notification row, and
    # suppressed for any recipient whose last_read_at is very recent
    # (a cheap proxy for "still looking at this conversation right now",
    # since this app is polling-based with no real presence/websockets).
    sender = db.session.get(User, user_id)
    sender_name = _display_name(sender) if sender else "Someone"
    # E2EE (Chats only): body is ciphertext as of the 1:1 chat
    # encryption chunk, so the server can no longer build a content
    # preview here - generic preview instead, same reasoning as the
    # design doc's WhatsApp-style push fallback. Pulled forward into
    # this chunk since it's the same function already being edited.
    push_preview = "New message" if body else "Sent an attachment"
    recently_active_cutoff = datetime.utcnow() - timedelta(seconds=15)
    other_participants = ConversationParticipant.query.filter(
        ConversationParticipant.conversation_id == conversation_id,
        ConversationParticipant.user_id != user_id,
        ConversationParticipant.left_at.is_(None),
    ).all()
    for participant in other_participants:
        if participant.last_read_at and participant.last_read_at >= recently_active_cutoff:
            continue
        if not should_notify(participant.user_id, "messages"):
            continue
        send_push_notification(participant.user_id, sender_name, push_preview)

    return jsonify(_serialize_message(message, attachment)), 201


CHAT_EDIT_WINDOW = timedelta(minutes=15)
CHAT_DELETE_WINDOW = timedelta(days=2)


@app.route("/chats/<int:conversation_id>/messages/<int:message_id>", methods=["PATCH"])
@require_csrf
def edit_message(conversation_id, message_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if not _active_participant(conversation_id, user_id):
        return jsonify({"error": "Conversation not found"}), 404

    message = Message.query.filter_by(id=message_id, conversation_id=conversation_id).first()
    if not message or message.is_deleted:
        return jsonify({"error": "Message not found"}), 404
    if message.sender_id != user_id:
        return jsonify({"error": "You can only edit your own messages"}), 403
    if message.created_at and datetime.utcnow() - message.created_at > CHAT_EDIT_WINDOW:
        return jsonify({"error": "Messages can only be edited within 15 minutes"}), 409
    if MessageAttachment.query.filter_by(message_id=message.id).first():
        return jsonify({"error": "Attachments cannot be edited"}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be valid JSON"}), 400
    body = (data.get("body") or "").strip()
    nonce = (data.get("nonce") or "").strip()
    if not body:
        return jsonify({"error": "Edited message body is required"}), 400
    if len(body) > CHAT_MESSAGE_CIPHERTEXT_MAX:
        return jsonify({"error": f"Message must be {CHAT_MESSAGE_CIPHERTEXT_MAX} characters or fewer"}), 400
    conversation = db.session.get(Conversation, conversation_id)
    e2ee_mode = getattr(conversation, "e2ee_mode", "legacy") if conversation else "legacy"
    requested_key_epoch = data.get("key_epoch")
    if requested_key_epoch is not None and (not isinstance(requested_key_epoch, int) or isinstance(requested_key_epoch, bool) or requested_key_epoch < 1):
        return jsonify({"error": "key_epoch must be a positive integer"}), 400
    if e2ee_mode == "group_v1":
        current_epoch = db.session.execute(text("SELECT key_epoch FROM conversation WHERE id = :conversation_id"), {"conversation_id": conversation_id}).scalar_one_or_none()
        current_epoch = int(current_epoch or 0)
        if not nonce or requested_key_epoch != current_epoch:
            return jsonify({"error": "Encrypted group edit key epoch is stale or missing; retry with the current group key", "key_epoch": current_epoch}), 409

    message.body = body
    message.e2ee_key_epoch = requested_key_epoch if e2ee_mode == "group_v1" else 0
    message.nonce = nonce or None
    message.edited_at = datetime.utcnow()
    db.session.commit()
    return jsonify(_serialize_message(message))


@app.route("/chats/<int:conversation_id>/messages/<int:message_id>", methods=["DELETE"])
@require_csrf
def delete_message(conversation_id, message_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if not _active_participant(conversation_id, user_id):
        return jsonify({"error": "Conversation not found"}), 404

    message = Message.query.filter_by(id=message_id, conversation_id=conversation_id).first()
    if not message or message.is_deleted:
        return jsonify({"error": "Message not found"}), 404
    if message.sender_id != user_id:
        return jsonify({"error": "You can only delete your own messages"}), 403
    if message.created_at and datetime.utcnow() - message.created_at > CHAT_DELETE_WINDOW:
        return jsonify({"error": "Messages can only be deleted within 2 days"}), 409

    message.is_deleted = True
    message.body = None
    message.nonce = None
    message.edited_at = None
    db.session.commit()
    return jsonify(_serialize_message(message))


CHAT_ATTACHMENT_MAX_SIZE_BYTES = 20 * 1024 * 1024
# 20 MB - deliberately smaller than document uploads (50 MB); chat
# attachments don't get AI processing or text extraction, so there's no
# reason to allow document-sized files here.


@app.route("/chats/<int:conversation_id>/attachments", methods=["POST"])
@limiter.limit("30 per hour")
@require_csrf
def init_chat_attachment(conversation_id):
    """
    Step 1 of sending a chat attachment: registers a pending
    MessageAttachment (status='uploading', message_id=None) and returns
    a signed direct-upload URL - same two-phase pattern as POST
    /documents. Reuses the existing "documents" Supabase bucket under a
    chat-attachments/ prefix rather than provisioning a separate bucket.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if not _active_participant(conversation_id, user_id):
        return jsonify({"error": "Conversation not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    original_filename = (data.get("original_filename") or "").strip()
    file_size_bytes = data.get("file_size_bytes")

    if not original_filename or len(original_filename) > 255:
        return jsonify({"error": "original_filename is required and must be 255 characters or fewer"}), 400
    ext = get_document_extension(original_filename)
    if not ext:
        return jsonify({"error": "Unsupported file type"}), 400
    if not isinstance(file_size_bytes, int) or isinstance(file_size_bytes, bool) or file_size_bytes <= 0:
        return jsonify({"error": "file_size_bytes must be a positive integer"}), 400
    if file_size_bytes > CHAT_ATTACHMENT_MAX_SIZE_BYTES:
        return jsonify({
            "error": f"File exceeds the {CHAT_ATTACHMENT_MAX_SIZE_BYTES // (1024 * 1024)} MB limit"
        }), 400

    storage_path = f"chat-attachments/{conversation_id}/{secrets.token_hex(16)}.{ext}"
    attachment = MessageAttachment(
        conversation_id=conversation_id,
        uploaded_by_user_id=user_id,
        storage_path=storage_path,
        file_type=ext,
        original_filename=original_filename,
        file_size_bytes=file_size_bytes,
        status="uploading",
    )
    db.session.add(attachment)
    db.session.commit()

    upload_url = create_signed_upload_url("documents", storage_path)
    if not upload_url:
        return jsonify({"error": "Could not prepare upload - please try again shortly"}), 502

    return jsonify({
        "attachment_id": attachment.id,
        "upload_url": upload_url,
        "storage_path": storage_path,
    }), 201


@app.route("/chats/<int:conversation_id>/attachments/<int:attachment_id>/uploaded", methods=["POST"])
@require_csrf
def confirm_chat_attachment_uploaded(conversation_id, attachment_id):
    """Step 2: confirms the direct upload landed in storage before
    trusting the client's word for it - same verification as
    POST /documents/<id>/uploaded."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if not _active_participant(conversation_id, user_id):
        return jsonify({"error": "Conversation not found"}), 404

    attachment = db.session.get(MessageAttachment, attachment_id)
    if (
        not attachment
        or attachment.conversation_id != conversation_id
        or attachment.uploaded_by_user_id != user_id
    ):
        return jsonify({"error": "Attachment not found"}), 404

    if attachment.status != "uploading":
        return jsonify({"error": f"Attachment is not awaiting upload (status: {attachment.status})"}), 400

    if not storage_object_exists("documents", attachment.storage_path):
        return jsonify({"error": "Upload not found in storage yet - please retry"}), 409

    attachment.status = "ready"
    db.session.commit()

    return jsonify({"attachment_id": attachment.id, "status": "ready"})


@app.route("/chats/<int:conversation_id>/attachments")
def list_chat_attachments(conversation_id):
    """
    Powers the Shared Media tab: every ready attachment sent in this
    conversation (excluding ones on soft-deleted messages), newest
    first. Only attachments actually attached to a sent message
    (message_id set) are eligible - an initiated-but-abandoned upload
    never shows up here.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if not _active_participant(conversation_id, user_id):
        return jsonify({"error": "Conversation not found"}), 404

    rows = (
        db.session.query(MessageAttachment, Message)
        .join(Message, MessageAttachment.message_id == Message.id)
        .filter(
            MessageAttachment.conversation_id == conversation_id,
            MessageAttachment.status == "ready",
            Message.is_deleted.is_(False),
        )
        .order_by(MessageAttachment.created_at.desc())
        .limit(100)
        .all()
    )

    result = []
    for attachment, message in rows:
        uploader = db.session.get(User, attachment.uploaded_by_user_id)
        result.append({
            "id": attachment.id,
            "message_id": attachment.message_id,
            "file_type": attachment.file_type,
            "original_filename": attachment.original_filename,
            "file_size_bytes": attachment.file_size_bytes,
            "view_url": get_cached_chat_attachment_url(attachment),
            "uploaded_by_user_id": attachment.uploaded_by_user_id,
            "uploaded_by_name": _display_name(uploader) if uploader else "Deleted user",
            "created_at": attachment.created_at.isoformat() if attachment.created_at else None,
        })

    return jsonify({"attachments": result})


@app.route("/chats/<int:conversation_id>/read", methods=["POST"])
@require_csrf
def mark_chat_read(conversation_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    participant = _active_participant(conversation_id, user_id)
    if not participant:
        return jsonify({"error": "Conversation not found"}), 404

    user = db.session.get(User, user_id)
    if user is not None and not bool(user.read_receipts_enabled):
        return jsonify({"message": "Read receipts disabled", "marked": False})

    participant.last_read_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Marked as read"})


@app.route("/chats/<int:conversation_id>/mute", methods=["POST"])
@require_csrf
def toggle_chat_mute(conversation_id):
    """
    Sets (or toggles) the CALLER's own mute flag for this conversation -
    purely a per-participant notification preference, not a moderation
    action, so no admin/role check beyond being an active participant.
    Body is optional: {"muted": true|false} sets it explicitly; an empty
    body toggles the current value.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    participant = _active_participant(conversation_id, user_id)
    if not participant:
        return jsonify({"error": "Conversation not found"}), 404

    data = request.get_json(silent=True) or {}
    if "muted" in data:
        if not isinstance(data["muted"], bool):
            return jsonify({"error": "muted must be true or false"}), 400
        participant.muted = data["muted"]
    else:
        participant.muted = not participant.muted

    db.session.commit()
    return jsonify({"muted": participant.muted})


@app.route("/chats/<int:conversation_id>", methods=["PATCH"])
@require_csrf
def rename_chat(conversation_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if not _active_participant(conversation_id, user_id):
        return jsonify({"error": "Conversation not found"}), 404

    conversation = db.session.get(Conversation, conversation_id)
    if not conversation or not conversation.is_group:
        return jsonify({"error": "Only group conversations can be renamed"}), 400

    data = request.get_json(silent=True)
    if not data or "name" not in data:
        return jsonify({"error": "name is required"}), 400

    name = (data.get("name") or "").strip()
    if not name or len(name) > CHAT_GROUP_NAME_MAX:
        return jsonify({"error": f"Group name must be 1-{CHAT_GROUP_NAME_MAX} characters"}), 400

    conversation.name = name
    db.session.commit()
    return jsonify({"id": conversation.id, "name": conversation.name})


@app.route("/chats/<int:conversation_id>/leave", methods=["POST"])
@require_csrf
def leave_chat(conversation_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    conversation = db.session.get(Conversation, conversation_id)
    if not conversation or not conversation.is_group:
        return jsonify({"error": "Only group conversations can be left"}), 400

    participant = _active_participant(conversation_id, user_id)
    if not participant:
        return jsonify({"error": "Conversation not found"}), 404

    participant.left_at = datetime.utcnow()
    if getattr(conversation, "e2ee_mode", "legacy") == "group_v1":
        current_epoch = db.session.execute(
            text("SELECT key_epoch FROM conversation WHERE id = :conversation_id"),
            {"conversation_id": conversation_id},
        ).scalar_one_or_none()
        current_epoch = int(current_epoch or 0)
        db.session.execute(
            text("UPDATE conversation SET key_epoch = :new_epoch WHERE id = :conversation_id AND key_epoch = :old_epoch"),
            {"conversation_id": conversation_id, "old_epoch": current_epoch, "new_epoch": current_epoch + 1},
        )
    db.session.commit()
    return jsonify({"message": "Left group"})


@app.route("/students")
def browse_students():
    """
    Browse students for the Explore > Students tab. Unlike /users/search
    (a narrow contact-picker for chat), this is a real directory: ranked
    by lifetime XP, filterable by university/program, with follow state
    for the viewer. Excludes email and any other sensitive fields, and
    - same rule as get_public_profile - hides program_name/year/xp_total
    for a private-profile user the viewer doesn't follow.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    q = (request.args.get("q") or "").strip()
    university_id = request.args.get("university_id", type=int)
    program_id = request.args.get("program_id", type=int)
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 20

    xp_subq = (
        db.session.query(
            XpEvent.user_id.label("user_id"),
            func.sum(XpEvent.xp_amount).label("xp_total"),
        )
        .group_by(XpEvent.user_id)
        .subquery()
    )

    xp_col = func.coalesce(xp_subq.c.xp_total, 0)
    query = (
        db.session.query(User, xp_col.label("xp_total"))
        .outerjoin(xp_subq, xp_subq.c.user_id == User.id)
        .filter(User.is_suspended.is_(False))
        .filter(User.id != user_id)
    )
    if q:
        query = query.filter(User.display_name.ilike(f"%{q}%"))
    if university_id:
        query = query.filter(User.university_id == university_id)
    if program_id:
        query = query.filter(User.program_id == program_id)

    rows = (
        query.order_by(xp_col.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    page_user_ids = [u.id for u, _ in rows]
    followed_ids = set()
    if page_user_ids:
        followed_ids = {
            f.followed_id for f in Follow.query.filter(
                Follow.follower_id == user_id,
                Follow.followed_id.in_(page_user_ids),
            ).all()
        }

    result = []
    for u, xp_total in rows:
        is_following = u.id in followed_ids
        is_private = u.profile_visibility == "private" and not is_following
        program = db.session.get(Program, u.program_id) if u.program_id else None
        result.append({
            "user_id": u.id,
            "display_name": _display_name(u),
            "program_name": None if is_private else (program.name if program else None),
            "year": None if is_private else u.year,
            "xp_total": None if is_private else int(xp_total),
            "is_following": is_following,
            "is_private": is_private,
        })

    return jsonify({"page": page, "students": result})


@app.route("/users/search")
def search_users():
    """Backs the "New Chat"/"New Group" contact picker. Deliberately
    narrow: only display_name matches, capped results, no email
    exposure - this is a people-picker, not a directory lookup."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"users": []})

    matches = (
        User.query
        .filter(User.id != user_id)
        .filter(User.is_suspended.is_(False))
        .filter(User.display_name.ilike(f"%{q}%"))
        .limit(20)
        .all()
    )

    return jsonify({"users": [
        {"id": u.id, "display_name": _display_name(u), "year": u.year, "semester": u.semester}
        for u in matches
    ]})


# ---------- Admin routes (protected) ----------

ANNOUNCEMENT_TITLE_MAX = 200
ANNOUNCEMENT_BODY_MAX = 500


@app.route("/admin/announcements", methods=["POST"])
@require_csrf
@require_admin
def admin_send_announcement():
    """
    Broadcasts an announcement to every non-suspended user as a
    Notification(type="announcement"), and logs the send in
    Announcement for the Communications history table. Reach is
    computed and stored at send time.
    """
    acting_admin_id = session.get("user_id")

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()

    if not title or len(title) > ANNOUNCEMENT_TITLE_MAX:
        return jsonify({"error": f"title is required and must be {ANNOUNCEMENT_TITLE_MAX} characters or fewer"}), 400
    if not body or len(body) > ANNOUNCEMENT_BODY_MAX:
        return jsonify({"error": f"body is required and must be {ANNOUNCEMENT_BODY_MAX} characters or fewer"}), 400

    university_id = data.get("university_id")
    program_id = data.get("program_id")
    year = data.get("year")
    semester = data.get("semester")
    group_id = data.get("group_id")

    audience_query = User.query.filter(User.is_suspended.is_(False))

    if university_id is not None:
        if not isinstance(university_id, int) or isinstance(university_id, bool):
            return jsonify({"error": "university_id must be an integer"}), 400
        audience_query = audience_query.filter(User.university_id == university_id)

    if program_id is not None:
        if not isinstance(program_id, int) or isinstance(program_id, bool):
            return jsonify({"error": "program_id must be an integer"}), 400
        audience_query = audience_query.filter(User.program_id == program_id)

    if year is not None:
        if not isinstance(year, int) or isinstance(year, bool):
            return jsonify({"error": "year must be an integer"}), 400
        audience_query = audience_query.filter(User.year == year)

    if semester is not None:
        if not isinstance(semester, int) or isinstance(semester, bool):
            return jsonify({"error": "semester must be an integer"}), 400
        audience_query = audience_query.filter(User.semester == semester)

    if group_id is not None:
        if not isinstance(group_id, int) or isinstance(group_id, bool):
            return jsonify({"error": "group_id must be an integer"}), 400
        if not db.session.get(Group, group_id):
            return jsonify({"error": "Group not found"}), 404
        member_ids = [
            row[0] for row in
            db.session.query(GroupMember.user_id).filter(GroupMember.group_id == group_id).all()
        ]
        audience_query = audience_query.filter(User.id.in_(member_ids))

    recipient_ids = [row.id for row in audience_query.with_entities(User.id).all()]

    announcement = Announcement(title=title, body=body, sent_by=acting_admin_id, reach=len(recipient_ids))
    db.session.add(announcement)
    db.session.flush()  # assign announcement.id before Notification.related_id references it

    for recipient_id in recipient_ids:
        db.session.add(Notification(
            user_id=recipient_id,
            type="announcement",
            title=title,
            body=body,
            related_type="announcement",
            related_id=announcement.id,
        ))

    db.session.commit()

    # Best-effort push fan-out to the same audience - never blocks or fails
    # the announcement itself if push sending has issues (see
    # send_push_notification()'s own internal error handling).
    for recipient_id in recipient_ids:
        send_push_notification(recipient_id, title, body)

    return jsonify({
        "id": announcement.id,
        "title": announcement.title,
        "body": announcement.body,
        "reach": announcement.reach,
        "created_at": announcement.created_at.isoformat(),
    }), 201


@app.route("/admin/announcements")
@require_admin
def admin_list_announcements():
    """History for the Communications tab, newest first."""
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).limit(50).all()
    return jsonify([
        {
            "id": a.id,
            "title": a.title,
            "body": a.body,
            "reach": a.reach,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in announcements
    ])


# ---------- Admin: moderation (Chunk 10) ----------

def _content_report_preview(report):
    """
    Best-effort preview of the reported content for the admin queue -
    a short text snippet plus who authored it. Returns None fields if
    the target was hard-deleted out from under the report (shouldn't
    normally happen since content is soft-removed, but don't 500 if it
    does).
    """
    author_id = None
    snippet = None

    if report.target_type == "group_post":
        row = db.session.get(GroupPost, report.target_id)
        if row:
            author_id = row.user_id
            snippet = row.body
    elif report.target_type == "group_post_comment":
        row = db.session.get(GroupPostComment, report.target_id)
        if row:
            author_id = row.user_id
            snippet = row.body
    elif report.target_type == "user":
        author_id = report.target_id

    author = db.session.get(User, author_id) if author_id else None
    return {
        "author_id": author_id,
        "author_email": author.email if author else None,
        "snippet": (snippet[:200] if snippet else None),
    }


def _serialize_content_report(report):
    reporter = db.session.get(User, report.reporter_user_id) if report.reporter_user_id else None
    entry = {
        "id": report.id,
        "target_type": report.target_type,
        "target_id": report.target_id,
        "reporter_email": reporter.email if reporter else "System",
        "reason": report.reason,
        "details": report.details,
        "priority": report.priority,
        "status": report.status,
        "action_taken": report.action_taken,
        "admin_notes": report.admin_notes,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }
    entry.update(_content_report_preview(report))
    return entry


@app.route("/admin/content-reports")
@require_admin
def admin_list_content_reports():
    """
    Moderation queue. Defaults to pending only, ordered highest
    priority first (then oldest first within a priority tier) so the
    most urgent reports surface at the top; pass status=all to see
    dismissed/actioned ones too.

    Sorted in Python rather than via a SQL CASE expression - same
    pattern as admin_list_users() below, which avoids depending on
    SQLAlchemy version-specific case() syntax (the tuple-positional
    form needs 1.4+; older installs need the list/`whens=` form).
    Report volume is small enough that this costs nothing.
    """
    status_filter = request.args.get("status", "pending")
    if status_filter != "all" and status_filter not in CONTENT_REPORT_STATUSES:
        return jsonify({"error": "status must be 'all' or one of: " + ", ".join(CONTENT_REPORT_STATUSES)}), 400

    query = ContentReport.query
    if status_filter != "all":
        query = query.filter_by(status=status_filter)

    reports = query.order_by(ContentReport.created_at.asc()).all()
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    reports.sort(key=lambda r: priority_rank.get(r.priority, 3))

    return jsonify({"reports": [_serialize_content_report(r) for r in reports]})


@app.route("/admin/content-reports/summary")
@require_admin
def admin_content_reports_summary():
    """KPI row for the Moderation tab header."""
    open_reports = ContentReport.query.filter_by(status="pending").count()
    today = datetime.utcnow().date()
    resolved_today = ContentReport.query.filter(
        ContentReport.status != "pending",
        func.date(ContentReport.reviewed_at) == today,
    ).count()
    suspended_users = User.query.filter_by(is_suspended=True).count()
    warnings_issued = UserWarning.query.count()

    return jsonify({
        "open_reports": open_reports,
        "resolved_today": resolved_today,
        "suspended_users": suspended_users,
        "warnings_issued": warnings_issued,
    })


def _load_pending_report(report_id):
    report = db.session.get(ContentReport, report_id)
    if not report:
        return None, (jsonify({"error": "Report not found"}), 404)
    if report.status != "pending":
        return None, (jsonify({"error": f"Report is not pending (status: {report.status})"}), 400)
    return report, None


@app.route("/admin/content-reports/<int:report_id>/dismiss", methods=["POST"])
@require_csrf
@require_admin
def admin_dismiss_content_report(report_id):
    acting_admin_id = session.get("user_id")
    report, error = _load_pending_report(report_id)
    if error:
        return error

    data = request.get_json(silent=True) or {}
    admin_notes = data.get("admin_notes")
    if admin_notes is not None:
        admin_notes = admin_notes.strip()
        if len(admin_notes) > CONTENT_REPORT_DETAILS_MAX:
            return jsonify({"error": f"admin_notes must be {CONTENT_REPORT_DETAILS_MAX} characters or fewer"}), 400
        admin_notes = admin_notes or None

    report.status = "dismissed"
    report.action_taken = "dismissed"
    report.admin_notes = admin_notes
    report.reviewed_by = acting_admin_id
    report.reviewed_at = datetime.utcnow()
    log_admin_action(acting_admin_id, "content_report_dismissed", target_type="content_report", target_id=report.id, details={"admin_notes": admin_notes} if admin_notes else None)
    db.session.commit()

    return jsonify(_serialize_content_report(report))


@app.route("/admin/content-reports/<int:report_id>/remove", methods=["POST"])
@require_csrf
@require_admin
def admin_remove_reported_content(report_id):
    """
    Hides the reported content (soft-remove, same is_removed pattern
    used everywhere else) and marks the report actioned. Not valid for
    target_type='user' - there's no "content" to remove for a user
    report; use /warn or the existing /admin/users suspend toggle
    instead.
    """
    acting_admin_id = session.get("user_id")
    report, error = _load_pending_report(report_id)
    if error:
        return error

    if report.target_type == "user":
        return jsonify({
            "error": "Can't 'remove' a user report - use /admin/content-reports/<id>/warn, "
                     "or suspend the user via PATCH /admin/users/<id>"
        }), 400

    model_by_type = {
        "group_post": GroupPost,
        "group_post_comment": GroupPostComment,
    }
    model = model_by_type[report.target_type]
    target = db.session.get(model, report.target_id)
    if not target:
        return jsonify({"error": "Reported content no longer exists"}), 404

    target.is_removed = True

    data = request.get_json(silent=True) or {}
    admin_notes = data.get("admin_notes")
    if admin_notes is not None:
        admin_notes = admin_notes.strip()
        if len(admin_notes) > CONTENT_REPORT_DETAILS_MAX:
            return jsonify({"error": f"admin_notes must be {CONTENT_REPORT_DETAILS_MAX} characters or fewer"}), 400
        admin_notes = admin_notes or None

    report.status = "actioned"
    report.action_taken = "removed"
    report.admin_notes = admin_notes
    report.reviewed_by = acting_admin_id
    report.reviewed_at = datetime.utcnow()
    log_admin_action(acting_admin_id, "content_report_content_removed", target_type="content_report", target_id=report.id, details={"target_type": report.target_type, "target_id": report.target_id})
    db.session.commit()

    return jsonify(_serialize_content_report(report))


@app.route("/admin/content-reports/<int:report_id>/warn", methods=["POST"])
@require_csrf
@require_admin
def admin_warn_from_content_report(report_id):
    """
    Issues a UserWarning to the content's author (or the reported user
    directly, for target_type='user'), tied back to this report. The
    warning ALWAYS reaches the student as a Notification - message
    states what they did wrong, consequence states what happens as a
    result. Both are admin-authored per warning, not templated, since
    the punishment should fit the specific violation. Optionally also
    removes the content in the same call (remove_content=true).
    """
    acting_admin_id = session.get("user_id")
    report, error = _load_pending_report(report_id)
    if error:
        return error

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    consequence = (data.get("consequence") or "").strip()
    remove_content = bool(data.get("remove_content"))

    if not message or len(message) > CONTENT_REPORT_DETAILS_MAX:
        return jsonify({"error": f"message is required and must be {CONTENT_REPORT_DETAILS_MAX} characters or fewer"}), 400
    if not consequence or len(consequence) > CONTENT_REPORT_DETAILS_MAX:
        return jsonify({"error": f"consequence is required and must be {CONTENT_REPORT_DETAILS_MAX} characters or fewer"}), 400

    if report.target_type == "user":
        warned_user_id = report.target_id
    else:
        preview = _content_report_preview(report)
        warned_user_id = preview["author_id"]
        if not warned_user_id:
            return jsonify({"error": "Could not determine the content's author to warn"}), 404

        if remove_content:
            model_by_type = {
                "group_post": GroupPost,
                "group_post_comment": GroupPostComment,
            }
            target = db.session.get(model_by_type[report.target_type], report.target_id)
            if target:
                target.is_removed = True

    warning = UserWarning(
        user_id=warned_user_id,
        issued_by=acting_admin_id,
        content_report_id=report.id,
        reason=report.reason,
        message=message,
        consequence=consequence,
    )
    db.session.add(warning)
    db.session.flush()  # assign warning.id before Notification.related_id references it

    db.session.add(Notification(
        user_id=warned_user_id,
        type="moderation_warning",
        title="You've received a warning",
        body=f"{message} {consequence}",
        related_type="user_warning",
        related_id=warning.id,
    ))
    send_push_notification(warned_user_id, "You've received a warning", f"{message} {consequence}")

    report.status = "actioned"
    report.action_taken = "warned"
    report.reviewed_by = acting_admin_id
    report.reviewed_at = datetime.utcnow()
    log_admin_action(acting_admin_id, "content_report_warning_issued", target_type="user_warning", target_id=warning.id, details={"warned_user_id": warned_user_id, "reason": report.reason})
    db.session.commit()

    return jsonify({
        "report": _serialize_content_report(report),
        "warning_id": warning.id,
        "content_removed": remove_content and report.target_type != "user",
    })


@app.route("/warnings")
def list_my_warnings():
    """Lets a student see their own warning history - what they did
    wrong and the consequence, in their own words from the admin."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    warnings = (
        UserWarning.query.filter_by(user_id=user_id)
        .order_by(UserWarning.created_at.desc())
        .all()
    )
    return jsonify({"warnings": [
        {
            "id": w.id,
            "reason": w.reason,
            "message": w.message,
            "consequence": w.consequence,
            "created_at": w.created_at.isoformat() if w.created_at else None,
        }
        for w in warnings
    ]})


@app.route("/admin/ai-usage")
@require_admin
def admin_ai_usage():
    """
    Rollup of AI usage/cost for the admin AI & Usage dashboard, sourced
    from AiUsageLog (populated by ai_service.py on every AI call - both
    document actions and forum Q&A share this table via request_type).

    NOTE on gaps this endpoint deliberately does NOT paper over:
      - AiUsageLog has no success/failure column, so a request-level
        error rate can't be computed from it. failed_jobs/completed_jobs
        below come from AiJob instead, which only covers the document
        pipeline (text_extraction/summary/quiz/flashcards/podcast) -
        forum Q&A failures aren't persisted anywhere today (ai_service
        raises an exception, the route translates it to an HTTP error,
        nothing is logged). Treat failed_jobs as a partial signal, not
        a true platform-wide error rate.
      - Average response time isn't tracked anywhere in the schema, so
        it's omitted entirely rather than estimated.
    """
    try:
        days = int(request.args.get("days", 30))
    except ValueError:
        days = 30
    days = max(1, min(days, 365))
    window_start = datetime.utcnow() - timedelta(days=days)

    base = AiUsageLog.query.filter(AiUsageLog.created_at >= window_start)

    total_requests = base.count()
    totals_row = db.session.query(
        func.coalesce(func.sum(AiUsageLog.cost_usd), 0),
        func.coalesce(func.sum(AiUsageLog.input_tokens), 0),
        func.coalesce(func.sum(AiUsageLog.output_tokens), 0),
        func.coalesce(func.sum(AiUsageLog.cache_read_tokens), 0),
        func.coalesce(func.sum(AiUsageLog.cache_creation_tokens), 0),
    ).filter(AiUsageLog.created_at >= window_start).first()
    total_cost_usd, total_input_tokens, total_output_tokens, total_cache_read, total_cache_creation = totals_row

    by_feature_raw = (
        db.session.query(
            AiUsageLog.request_type,
            func.count(AiUsageLog.id),
            func.coalesce(func.sum(AiUsageLog.cost_usd), 0),
        )
        .filter(AiUsageLog.created_at >= window_start)
        .group_by(AiUsageLog.request_type)
        .order_by(func.count(AiUsageLog.id).desc())
        .all()
    )
    by_feature = [
        {"request_type": request_type, "requests": count, "cost_usd": float(cost)}
        for request_type, count, cost in by_feature_raw
    ]

    daily_raw = (
        db.session.query(
            func.date(AiUsageLog.created_at).label("day"),
            func.count(AiUsageLog.id),
            func.coalesce(func.sum(AiUsageLog.cost_usd), 0),
        )
        .filter(AiUsageLog.created_at >= window_start)
        .group_by(func.date(AiUsageLog.created_at))
        .order_by(func.date(AiUsageLog.created_at))
        .all()
    )
    daily_trend = [
        {"date": day.isoformat(), "requests": count, "cost_usd": float(cost)}
        for day, count, cost in daily_raw
    ]

    today = datetime.utcnow().date()
    requests_today = AiUsageLog.query.filter(func.date(AiUsageLog.created_at) == today).count()

    failed_jobs = AiJob.query.filter(
        AiJob.status == "failed", AiJob.created_at >= window_start,
    ).count()
    completed_jobs = AiJob.query.filter(
        AiJob.status == "completed", AiJob.created_at >= window_start,
    ).count()

    return jsonify({
        "period_days": days,
        "total_requests": total_requests,
        "requests_today": requests_today,
        "total_cost_usd": float(total_cost_usd),
        "total_tokens": int(total_input_tokens) + int(total_output_tokens),
        "input_tokens": int(total_input_tokens),
        "output_tokens": int(total_output_tokens),
        "cache_read_tokens": int(total_cache_read),
        "cache_creation_tokens": int(total_cache_creation),
        "by_feature": by_feature,
        "daily_trend": daily_trend,
        "document_pipeline_jobs": {
            "completed": completed_jobs,
            "failed": failed_jobs,
            "note": "Covers text_extraction/summary/quiz/flashcards/podcast jobs only - forum Q&A failures aren't logged.",
        },
    })


@app.route("/admin/ai-jobs")
@require_admin
def admin_list_ai_jobs():
    """
    Lists recent AiJob rows for admin visibility, optionally filtered
    by status (?status=failed). Newest first.
    """
    status_filter = request.args.get("status")

    query = AiJob.query
    if status_filter:
        query = query.filter_by(status=status_filter)

    jobs = query.order_by(AiJob.created_at.desc()).limit(100).all()

    return jsonify([
        {
            "id": j.id,
            "document_content_id": j.document_content_id,
            "feature": j.feature,
            "status": j.status,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            "error_message": j.error_message,
            "retry_count": j.retry_count,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ])


@app.route("/admin/ai-jobs/<int:job_id>/retry", methods=["POST"])
@require_csrf
@require_admin
def admin_retry_ai_job(job_id):
    """
    Re-runs a failed job synchronously (not backgrounded - admin is
    waiting on the response) and increments retry_count regardless of
    outcome, so repeated failures are visible in the job list.
    """
    job = db.session.get(AiJob, job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job.status not in ("failed", "completed"):
        return jsonify({"error": f"Job is currently '{job.status}' - wait for it to finish before retrying"}), 400

    job.retry_count = (job.retry_count or 0) + 1
    db.session.commit()

    try:
        if job.feature == "text_extraction":
            document_pipeline.process_document(job.document_content_id)
        else:
            return jsonify({"error": f"No retry handler for feature '{job.feature}' yet"}), 400
    except Exception as e:
        return jsonify({"error": f"Retry failed: {e}"}), 502

    return jsonify({"message": "Retry completed", "job_id": job.id})


@app.route("/admin/content", methods=["GET"])
@require_admin
def admin_list_content():
    unit_id = request.args.get("unit_id", type=int)

    query = ContentItem.query
    if unit_id:
        query = query.filter_by(unit_id=unit_id)

    items = query.order_by(ContentItem.id.desc()).all()

    result = []
    for item in items:
        unit = db.session.get(Unit, item.unit_id)
        result.append({
            "id": item.id,
            "unit_id": item.unit_id,
            "unit_code": unit.code if unit else None,
            "content_type": item.content_type,
            "title": item.title,
            "file_url": item.file_url,
            "paper_year": item.paper_year,
            "is_downloadable": item.is_downloadable,
            "price": get_price_for_type(item.content_type),
        })

    return jsonify({"content": result})


@app.route("/admin/content", methods=["POST"])
@require_csrf
@require_admin
def admin_add_content():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    unit_id = data.get("unit_id")
    content_type = data.get("content_type")
    title = data.get("title")
    file_url = data.get("file_url")
    paper_year = data.get("paper_year")

    if not unit_id or not content_type or not title:
        return jsonify({"error": "unit_id, content_type, and title are required"}), 400

    if content_type not in ("past_paper", "notes", "qna"):
        return jsonify({"error": "content_type must be past_paper, notes, or qna"}), 400

    unit = db.session.get(Unit, unit_id)
    if not unit:
        return jsonify({"error": "Unit not found"}), 404

    is_downloadable = False if content_type == "qna" else True

    item = ContentItem(
        unit_id=unit_id,
        content_type=content_type,
        title=title,
        file_url=file_url,
        paper_year=paper_year,
        is_downloadable=is_downloadable,
    )
    db.session.add(item)
    db.session.commit()

    return jsonify({"message": "Content added", "content_id": item.id}), 201


@app.route("/admin/content/<int:content_id>", methods=["PATCH"])
@require_csrf
@require_admin
def admin_update_content(content_id):
    item = db.session.get(ContentItem, content_id)
    if not item:
        return jsonify({"error": "Content not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    if "title" in data:
        item.title = data["title"]
    if "file_url" in data:
        item.file_url = data["file_url"]
    if "paper_year" in data:
        item.paper_year = data["paper_year"]

    db.session.commit()

    return jsonify({
        "message": "Content updated",
        "content_id": item.id,
        "price": get_price_for_type(item.content_type),
        "title": item.title,
    })


@app.route("/admin/payments", methods=["GET"])
@require_admin
def admin_list_payments():
    status_filter = request.args.get("status")

    query = Payment.query
    if status_filter:
        query = query.filter_by(status=status_filter)

    payments = query.order_by(Payment.created_at.desc()).all()

    result = []
    for p in payments:
        content_item = db.session.get(ContentItem, p.content_item_id) if p.content_item_id else None
        user = db.session.get(User, p.user_id) if p.user_id else None
        result.append({
            "id": p.id,
            "user_id": p.user_id,
            "user_email": user.email if user else None,
            "user_display_name": user.display_name if user else None,
            "payment_type": p.payment_type,
            "content_title": content_item.title if content_item else None,
            "plan": p.plan,
            "phone_number": p.phone_number,
            "amount": p.amount,
            "status": p.status,
            "provider": p.provider,
            "reference": p.reference,
            "subscription_expires_at": p.subscription_expires_at.isoformat() if p.subscription_expires_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    return jsonify({"payments": result})


@app.route("/admin/analytics")
@require_admin
def admin_analytics():
    total_revenue = db.session.query(
        func.coalesce(func.sum(Payment.amount), 0)
    ).filter(Payment.status == "success").scalar()

    total_users = db.session.query(func.count(User.id)).scalar()

    # "Active today" = any authenticated request today (login, browsing,
    # chatting, studying - see track_last_active()), not just specific
    # study actions.
    today = datetime.utcnow().date()
    active_today = db.session.query(
        func.count(User.id)
    ).filter(func.date(User.last_active_at) == today).scalar()

    # Storage is summed off DocumentContent, not Document - DocumentContent
    # is the deduplicated, one-row-per-unique-file table, so a document
    # shared by many students' Document rows is only counted once.
    storage_used_bytes = db.session.query(
        func.coalesce(func.sum(DocumentContent.file_size_bytes), 0)
    ).scalar()

    total_units = db.session.query(func.count(Unit.id)).scalar()
    total_content = db.session.query(func.count(ContentItem.id)).scalar()

    content_by_type = dict(
        db.session.query(ContentItem.content_type, func.count(ContentItem.id))
        .group_by(ContentItem.content_type)
        .all()
    )

    payments_by_status = dict(
        db.session.query(Payment.status, func.count(Payment.id))
        .group_by(Payment.status)
        .all()
    )

    revenue_30d = db.session.query(
        func.coalesce(func.sum(Payment.amount), 0)
    ).filter(
        Payment.status == "success",
        Payment.created_at >= datetime.utcnow() - timedelta(days=30),
    ).scalar()

    trend_start = datetime.utcnow() - timedelta(days=30)

    signups_raw = (
        db.session.query(
            func.date(User.created_at).label("day"),
            func.count(User.id),
        )
        .filter(User.created_at >= trend_start)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
        .all()
    )
    signups_per_day = [
        {"date": day.isoformat(), "count": count}
        for day, count in signups_raw
    ]

    revenue_raw = (
        db.session.query(
            func.date(Payment.created_at).label("day"),
            func.coalesce(func.sum(Payment.amount), 0),
        )
        .filter(
            Payment.status == "success",
            Payment.created_at >= trend_start,
        )
        .group_by(func.date(Payment.created_at))
        .order_by(func.date(Payment.created_at))
        .all()
    )
    revenue_per_day = [
        {"date": day.isoformat(), "amount": amount}
        for day, amount in revenue_raw
    ]

    return jsonify({
        "total_revenue": total_revenue,
        "revenue_last_30d": revenue_30d,
        "total_users": total_users,
        "active_today": active_today,
        "storage_used_bytes": int(storage_used_bytes),
        "total_units": total_units,
        "total_content_items": total_content,
        "content_by_type": content_by_type,
        "payments_by_status": payments_by_status,
        "signups_per_day": signups_per_day,
        "revenue_per_day": revenue_per_day,
    })


@app.route("/admin/analytics/universities")
@require_admin
def admin_analytics_universities():
    """
    Per-university engagement rollup for the admin Analytics tab.
    Only includes universities with at least one signed-up student.
    Engagement tier is a relative ranking (top/bottom quartile of a
    combined documents+AI-requests score) among the universities
    returned here, not an absolute scale - same reasoning as the
    percentile-based work used elsewhere (e.g. XP leaderboards): with
    a handful of universities, fixed thresholds like ">10000 requests
    = Very High" would be meaningless noise, whereas relative ranking
    stays useful regardless of platform size.

    "Premium users" reuses the same latest-successful-subscription
    dedup logic as GET /admin/users, just grouped by university
    instead of returned per-user.
    """
    student_counts = dict(
        db.session.query(User.university_id, func.count(User.id))
        .filter(User.university_id.isnot(None))
        .group_by(User.university_id)
        .all()
    )
    if not student_counts:
        return jsonify({"universities": []})

    uni_ids = list(student_counts.keys())
    universities = {u.id: u.name for u in University.query.filter(University.id.in_(uni_ids)).all()}

    doc_counts = dict(
        db.session.query(User.university_id, func.count(Document.id))
        .select_from(Document)
        .join(User, Document.user_id == User.id)
        .filter(Document.is_removed.is_(False), User.university_id.in_(uni_ids))
        .group_by(User.university_id)
        .all()
    )

    ai_counts = dict(
        db.session.query(User.university_id, func.count(AiUsageLog.id))
        .select_from(AiUsageLog)
        .join(User, AiUsageLog.user_id == User.id)
        .filter(User.university_id.in_(uni_ids))
        .group_by(User.university_id)
        .all()
    )

    # Same active-subscription dedup as GET /admin/users, then grouped
    # by university instead of returned per-user.
    sub_rows = (
        db.session.query(Payment.user_id, Payment.subscription_expires_at)
        .join(User, Payment.user_id == User.id)
        .filter(
            User.university_id.in_(uni_ids),
            Payment.payment_type == "subscription",
            Payment.status == "success",
            Payment.subscription_expires_at.isnot(None),
        )
        .all()
    )
    latest_expiry = {}
    for uid, expires_at in sub_rows:
        if uid not in latest_expiry or expires_at > latest_expiry[uid]:
            latest_expiry[uid] = expires_at
    now = datetime.utcnow()
    active_user_ids = [uid for uid, expires_at in latest_expiry.items() if expires_at > now]
    premium_counts = dict(
        db.session.query(User.university_id, func.count(User.id))
        .filter(User.id.in_(active_user_ids), User.university_id.in_(uni_ids))
        .group_by(User.university_id)
        .all()
    ) if active_user_ids else {}

    rows = []
    for uid in uni_ids:
        docs = doc_counts.get(uid, 0)
        ai_reqs = ai_counts.get(uid, 0)
        rows.append({
            "university_id": uid,
            "university_name": universities.get(uid, "Unknown"),
            "students": student_counts.get(uid, 0),
            "documents": docs,
            "ai_requests": ai_reqs,
            "premium_users": premium_counts.get(uid, 0),
            "_score": docs + ai_reqs,
        })

    rows.sort(key=lambda r: r["_score"], reverse=True)
    n = len(rows)
    for i, r in enumerate(rows):
        percentile = i / n
        if percentile < 0.25:
            r["engagement"] = "Very High"
        elif percentile < 0.5:
            r["engagement"] = "High"
        elif percentile < 0.75:
            r["engagement"] = "Medium"
        else:
            r["engagement"] = "Low"
        del r["_score"]

    return jsonify({"universities": rows})


# Plan tiers a bootstrapped single-operator app can pick between on the
# System tab - approximate published Supabase limits per tier. Not
# fetched from a Supabase API (that would need a separate integration);
# the admin just clicks which tier they're currently on, and it's
# persisted in SystemSetting like other admin-editable values (see
# admin_get_settings / admin_update_settings above for the same
# pattern). Add a new key here if Supabase adds/changes a tier.
SUPABASE_TIER_LIMITS = {
    "free": {"db_size_bytes": 500 * 1024 * 1024, "storage_bytes": 1 * 1024 * 1024 * 1024, "connections": 60},
    "pro": {"db_size_bytes": 8 * 1024 * 1024 * 1024, "storage_bytes": 100 * 1024 * 1024 * 1024, "connections": 200},
    "team": {"db_size_bytes": 8 * 1024 * 1024 * 1024, "storage_bytes": 200 * 1024 * 1024 * 1024, "connections": 400},
}
SUPABASE_DEFAULT_TIER = "free"


def _get_supabase_tier():
    setting = SystemSetting.query.filter_by(key="supabase_tier").first()
    tier = setting.value if setting and setting.value in SUPABASE_TIER_LIMITS else SUPABASE_DEFAULT_TIER
    return tier


@app.route("/admin/system/capacity")
@require_admin
def admin_system_capacity():
    """
    Capacity/budget tracking for a bootstrapped, single-operator app -
    answers "am I about to outgrow my plan" and "what's my AI burn
    rate," not "is SendGrid up right now" (that would need a real
    health-check system with historical uptime storage, out of scope
    here). Plan limits come from SUPABASE_TIER_LIMITS keyed by whichever
    tier is currently selected in SystemSetting - see
    /admin/system/capacity/tier to change it.
    """
    tier = _get_supabase_tier()
    limits = SUPABASE_TIER_LIMITS[tier]

    db_size_bytes = db.session.execute(
        db.text("SELECT pg_database_size(current_database())")
    ).scalar()

    storage_used_bytes = db.session.query(
        func.coalesce(func.sum(DocumentContent.file_size_bytes), 0)
    ).scalar()

    active_connections = db.session.execute(
        db.text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
    ).scalar()

    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    ai_spend_mtd = db.session.query(
        func.coalesce(func.sum(AiUsageLog.cost_usd), 0)
    ).filter(AiUsageLog.created_at >= month_start).scalar()

    days_elapsed = max((now - month_start).days + 1, 1)
    if now.month == 12:
        next_month_start = datetime(now.year + 1, 1, 1)
    else:
        next_month_start = datetime(now.year, now.month + 1, 1)
    days_in_month = (next_month_start - month_start).days
    ai_spend_projected = float(ai_spend_mtd) / days_elapsed * days_in_month

    return jsonify({
        "tier": tier,
        "available_tiers": list(SUPABASE_TIER_LIMITS.keys()),
        "db_size_bytes": int(db_size_bytes),
        "db_size_limit_bytes": limits["db_size_bytes"],
        "storage_used_bytes": int(storage_used_bytes),
        "storage_limit_bytes": limits["storage_bytes"],
        "active_connections": int(active_connections),
        "connection_limit": limits["connections"],
        "ai_spend_mtd_usd": float(ai_spend_mtd),
        "ai_spend_projected_month_end_usd": round(ai_spend_projected, 2),
        "days_elapsed_this_month": days_elapsed,
        "days_in_month": days_in_month,
    })


@app.route("/admin/system/capacity/tier", methods=["POST"])
@require_csrf
@require_admin
def admin_set_supabase_tier():
    """Switches which Supabase plan tier the capacity bars are measured against."""
    data = request.get_json(silent=True) or {}
    tier = data.get("tier")
    if tier not in SUPABASE_TIER_LIMITS:
        return jsonify({"error": "tier must be one of: " + ", ".join(SUPABASE_TIER_LIMITS.keys())}), 400

    setting = SystemSetting.query.filter_by(key="supabase_tier").first()
    if not setting:
        setting = SystemSetting(key="supabase_tier", value=tier)
        db.session.add(setting)
    else:
        setting.value = tier
    db.session.commit()

    return jsonify({"tier": tier})


@app.route("/admin/payments/<int:payment_id>/refund", methods=["POST"])
@require_csrf
@require_admin
def admin_refund_payment(payment_id):
    # Legacy refund endpoint deliberately disabled. It used to mutate the
    # local Payment row without contacting Paystack and without checking
    # entitlement consumption. Money-changing refunds must now go through
    # /admin/subscription-refunds/<refund_id>/execute so the policy quote,
    # audit record, Paystack refund, and webhook confirmation stay aligned.
    return jsonify({
        "error": "Legacy refund endpoint disabled",
        "use": "/admin/subscription-refunds",
        "payment_id": payment_id,
    }), 410


# ---------- Admin: user management ----------

ADMIN_USER_STATUS_VALUES = ("active", "suspended")
ADMIN_USER_SUB_VALUES = ("free", "premium")


@app.route("/admin/users")
@require_admin
def admin_list_users():
    """
    Lists users for the admin dashboard, optionally filtered by an
    email/display_name substring, suspension status, and subscription
    tier. Newest signups first; users with no created_at (pre-migration
    accounts) sort last rather than first.

    Each row is enriched with document count, AI request count, and
    current subscription plan - all computed via grouped aggregate
    queries up front (one query per metric) rather than per-user
    lookups, so this stays cheap regardless of user count.
    """
    search = (request.args.get("search") or "").strip().lower()
    status_filter = (request.args.get("status") or "").strip().lower()
    sub_filter = (request.args.get("sub") or "").strip().lower()

    if status_filter and status_filter not in ADMIN_USER_STATUS_VALUES:
        return jsonify({"error": "status must be one of: " + ", ".join(ADMIN_USER_STATUS_VALUES)}), 400
    if sub_filter and sub_filter not in ADMIN_USER_SUB_VALUES:
        return jsonify({"error": "sub must be one of: " + ", ".join(ADMIN_USER_SUB_VALUES)}), 400

    query = User.query
    if search:
        query = query.filter(
            or_(
                User.email.ilike(f"%{search}%"),
                User.display_name.ilike(f"%{search}%"),
            )
        )
    if status_filter == "active":
        query = query.filter(User.is_suspended.is_(False))
    elif status_filter == "suspended":
        query = query.filter(User.is_suspended.is_(True))

    users = query.all()
    users.sort(key=lambda u: u.created_at or datetime.min, reverse=True)
    user_ids = [u.id for u in users]

    doc_counts = dict(
        db.session.query(Document.user_id, func.count(Document.id))
        .filter(Document.user_id.in_(user_ids), Document.is_removed.is_(False))
        .group_by(Document.user_id)
        .all()
    ) if user_ids else {}

    ai_counts = dict(
        db.session.query(AiUsageLog.user_id, func.count(AiUsageLog.id))
        .filter(AiUsageLog.user_id.in_(user_ids))
        .group_by(AiUsageLog.user_id)
        .all()
    ) if user_ids else {}

    # Latest successful subscription payment per user, so plan can be
    # derived the same way get_user_subscription_status() does for a
    # single user - done here as one grouped query instead of N calls.
    sub_rows = (
        db.session.query(Payment.user_id, Payment.plan, Payment.subscription_expires_at)
        .filter(
            Payment.user_id.in_(user_ids),
            Payment.payment_type == "subscription",
            Payment.status == "success",
            Payment.subscription_expires_at.isnot(None),
        )
        .all()
    ) if user_ids else []
    latest_sub = {}
    for uid, plan, expires_at in sub_rows:
        existing = latest_sub.get(uid)
        if existing is None or expires_at > existing[1]:
            latest_sub[uid] = (plan, expires_at)

    now = datetime.utcnow()
    result = []
    for u in users:
        sub_entry = latest_sub.get(u.id)
        is_sub_active = bool(sub_entry and sub_entry[1] > now)
        plan = sub_entry[0] if (sub_entry and is_sub_active) else "free"

        if sub_filter == "premium" and plan == "free":
            continue
        if sub_filter == "free" and plan != "free":
            continue

        university = db.session.get(University, u.university_id) if u.university_id else None
        program = db.session.get(Program, u.program_id) if u.program_id else None

        result.append({
            "id": u.id,
            "email": u.email,
            "year": u.year,
            "semester": u.semester,
            "display_name": u.display_name,
            "email_verified": u.email_verified,
            "is_admin": u.is_admin,
            "is_suspended": u.is_suspended,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "signup_source": u.signup_source,
            "university_name": university.name if university else None,
            "program_name": program.name if program else None,
            "documents_count": doc_counts.get(u.id, 0),
            "ai_requests_count": ai_counts.get(u.id, 0),
            "subscription_plan": plan,
            "subscription_active": is_sub_active,
        })

    return jsonify(result)


@app.route("/admin/users/<int:user_id>", methods=["PATCH"])
@require_csrf
@require_admin
def admin_update_user(user_id):
    """
    Lets an admin edit a student's year/semester, or toggle their
    is_admin / is_suspended flags. Self-protection: the acting admin
    cannot remove their own is_admin flag or suspend themselves here -
    that would risk locking the only admin out with no recovery path
    short of a direct DB edit.
    """
    acting_admin_id = session.get("user_id")

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    target_user = db.session.get(User, user_id)
    if not target_user:
        return jsonify({"error": "User not found"}), 404

    if "year" in data:
        year = data["year"]
        if year is not None:
            if not isinstance(year, int) or year < 1 or year > 4:
                return jsonify({"error": "Year must be a number between 1 and 4"}), 400
        target_user.year = year

    if "semester" in data:
        semester = data["semester"]
        if semester is not None:
            if not isinstance(semester, int) or semester not in (1, 2):
                return jsonify({"error": "Semester must be 1 or 2"}), 400
        target_user.semester = semester

    if "is_admin" in data:
        is_admin = data["is_admin"]
        if not isinstance(is_admin, bool):
            return jsonify({"error": "is_admin must be true or false"}), 400
        if user_id == acting_admin_id and is_admin is False:
            return jsonify({"error": "You can't remove your own admin access"}), 400
        target_user.is_admin = is_admin

    if "is_suspended" in data:
        is_suspended = data["is_suspended"]
        if not isinstance(is_suspended, bool):
            return jsonify({"error": "is_suspended must be true or false"}), 400
        if user_id == acting_admin_id and is_suspended is True:
            return jsonify({"error": "You can't suspend your own account"}), 400
        target_user.is_suspended = is_suspended

    _audit_details = {}
    if "is_admin" in data:
        _audit_details["is_admin"] = target_user.is_admin
    if "is_suspended" in data:
        _audit_details["is_suspended"] = target_user.is_suspended
    if _audit_details:
        log_admin_action(acting_admin_id, "user_updated", target_type="user", target_id=target_user.id, details=_audit_details)
    db.session.commit()

    return jsonify({
        "id": target_user.id,
        "email": target_user.email,
        "year": target_user.year,
        "semester": target_user.semester,
        "is_admin": target_user.is_admin,
        "is_suspended": target_user.is_suspended,
    })


# ---------- Admin: universities & programs (Chunk 10) ----------

UNIVERSITY_NAME_MAX = 150
UNIVERSITY_SHORT_CODE_MAX = 20
UNIVERSITY_COUNTRY_MAX = 80


def _serialize_admin_university(university):
    return {
        "id": university.id,
        "name": university.name,
        "short_code": university.short_code,
        "country": university.country,
        "is_active": university.is_active,
        "created_at": university.created_at.isoformat() if university.created_at else None,
    }


@app.route("/admin/universities", methods=["GET"])
@require_admin
def admin_list_universities():
    """Lists ALL universities (active and inactive) for admin management -
    unlike the public GET /universities, which only returns active ones."""
    universities = University.query.order_by(University.name).all()
    return jsonify({"universities": [_serialize_admin_university(u) for u in universities]})


@app.route("/admin/universities", methods=["POST"])
@require_csrf
@require_admin
def admin_create_university():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    name = (data.get("name") or "").strip()
    short_code = (data.get("short_code") or "").strip().upper()
    country = data.get("country")

    if not name or len(name) > UNIVERSITY_NAME_MAX:
        return jsonify({"error": f"name is required and must be {UNIVERSITY_NAME_MAX} characters or fewer"}), 400
    if not short_code or len(short_code) > UNIVERSITY_SHORT_CODE_MAX:
        return jsonify({
            "error": f"short_code is required and must be {UNIVERSITY_SHORT_CODE_MAX} characters or fewer"
        }), 400
    if University.query.filter_by(short_code=short_code).first():
        return jsonify({"error": "A university with this short_code already exists"}), 409

    if country is not None:
        if not isinstance(country, str):
            return jsonify({"error": "country must be a string"}), 400
        country = country.strip() or None
        if country and len(country) > UNIVERSITY_COUNTRY_MAX:
            return jsonify({"error": f"country must be {UNIVERSITY_COUNTRY_MAX} characters or fewer"}), 400

    university = University(name=name, short_code=short_code, country=country)
    db.session.add(university)
    db.session.commit()

    return jsonify(_serialize_admin_university(university)), 201


@app.route("/admin/universities/<int:university_id>", methods=["PATCH"])
@require_csrf
@require_admin
def admin_update_university(university_id):
    """
    Edits a university's fields and/or toggles is_active. Deactivating
    hides it from the public /universities and
    /universities/<id>/programs routes (and therefore from new student
    signups) without deleting anything - same reactive kill-switch
    pattern used throughout this file (Organisation.is_active,
    Group.is_active, etc).
    """
    university = db.session.get(University, university_id)
    if not university:
        return jsonify({"error": "University not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name or len(name) > UNIVERSITY_NAME_MAX:
            return jsonify({"error": f"name must be 1-{UNIVERSITY_NAME_MAX} characters"}), 400
        university.name = name

    if "short_code" in data:
        short_code = (data.get("short_code") or "").strip().upper()
        if not short_code or len(short_code) > UNIVERSITY_SHORT_CODE_MAX:
            return jsonify({"error": f"short_code must be 1-{UNIVERSITY_SHORT_CODE_MAX} characters"}), 400
        existing = University.query.filter_by(short_code=short_code).first()
        if existing and existing.id != university.id:
            return jsonify({"error": "A university with this short_code already exists"}), 409
        university.short_code = short_code

    if "country" in data:
        country = data.get("country")
        if country is not None:
            if not isinstance(country, str):
                return jsonify({"error": "country must be a string"}), 400
            country = country.strip() or None
            if country and len(country) > UNIVERSITY_COUNTRY_MAX:
                return jsonify({"error": f"country must be {UNIVERSITY_COUNTRY_MAX} characters or fewer"}), 400
        university.country = country

    if "is_active" in data:
        is_active = data["is_active"]
        if not isinstance(is_active, bool):
            return jsonify({"error": "is_active must be true or false"}), 400
        university.is_active = is_active

    db.session.commit()

    return jsonify(_serialize_admin_university(university))


PROGRAM_NAME_MAX = 150
PROGRAM_DEGREE_LEVEL_MAX = 50
PROGRAM_DISCIPLINE_CATEGORY_MAX = 80


def _serialize_admin_program(program):
    university = db.session.get(University, program.university_id)
    return {
        "id": program.id,
        "university_id": program.university_id,
        "university_name": university.name if university else None,
        "name": program.name,
        "degree_level": program.degree_level,
        "discipline_category": program.discipline_category,
        "is_active": program.is_active,
        "created_at": program.created_at.isoformat() if program.created_at else None,
    }


@app.route("/admin/programs", methods=["GET"])
@require_admin
def admin_list_programs():
    """Lists ALL programs (active and inactive), optionally filtered by
    ?university_id= - for admin management, unlike the public
    per-university GET /universities/<id>/programs, which only returns
    active ones."""
    query = Program.query
    university_id = request.args.get("university_id", type=int)
    if university_id:
        query = query.filter_by(university_id=university_id)
    programs = query.order_by(Program.name).all()
    return jsonify({"programs": [_serialize_admin_program(p) for p in programs]})


@app.route("/admin/programs", methods=["POST"])
@require_csrf
@require_admin
def admin_create_program():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    university_id = data.get("university_id")
    if not isinstance(university_id, int) or isinstance(university_id, bool):
        return jsonify({"error": "university_id is required"}), 400
    if not db.session.get(University, university_id):
        return jsonify({"error": "University not found"}), 404

    name = (data.get("name") or "").strip()
    if not name or len(name) > PROGRAM_NAME_MAX:
        return jsonify({"error": f"name is required and must be {PROGRAM_NAME_MAX} characters or fewer"}), 400

    degree_level = data.get("degree_level")
    if degree_level is not None:
        if not isinstance(degree_level, str):
            return jsonify({"error": "degree_level must be a string"}), 400
        degree_level = degree_level.strip() or None
        if degree_level and len(degree_level) > PROGRAM_DEGREE_LEVEL_MAX:
            return jsonify({"error": f"degree_level must be {PROGRAM_DEGREE_LEVEL_MAX} characters or fewer"}), 400

    discipline_category = data.get("discipline_category")
    if discipline_category is not None:
        if not isinstance(discipline_category, str):
            return jsonify({"error": "discipline_category must be a string"}), 400
        discipline_category = discipline_category.strip() or None
        if discipline_category and len(discipline_category) > PROGRAM_DISCIPLINE_CATEGORY_MAX:
            return jsonify({
                "error": f"discipline_category must be {PROGRAM_DISCIPLINE_CATEGORY_MAX} characters or fewer"
            }), 400

    program = Program(
        university_id=university_id, name=name,
        degree_level=degree_level, discipline_category=discipline_category,
    )
    db.session.add(program)
    db.session.commit()

    return jsonify(_serialize_admin_program(program)), 201


@app.route("/admin/programs/<int:program_id>", methods=["PATCH"])
@require_csrf
@require_admin
def admin_update_program(program_id):
    """
    Edits a program's fields and/or toggles is_active. Deactivating
    hides it from the public /universities/<id>/programs route (and
    therefore from new student signups picking a course), without
    deleting anything.
    """
    program = db.session.get(Program, program_id)
    if not program:
        return jsonify({"error": "Program not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name or len(name) > PROGRAM_NAME_MAX:
            return jsonify({"error": f"name must be 1-{PROGRAM_NAME_MAX} characters"}), 400
        program.name = name

    if "degree_level" in data:
        degree_level = data.get("degree_level")
        if degree_level is not None:
            if not isinstance(degree_level, str):
                return jsonify({"error": "degree_level must be a string"}), 400
            degree_level = degree_level.strip() or None
            if degree_level and len(degree_level) > PROGRAM_DEGREE_LEVEL_MAX:
                return jsonify({"error": f"degree_level must be {PROGRAM_DEGREE_LEVEL_MAX} characters or fewer"}), 400
        program.degree_level = degree_level

    if "discipline_category" in data:
        discipline_category = data.get("discipline_category")
        if discipline_category is not None:
            if not isinstance(discipline_category, str):
                return jsonify({"error": "discipline_category must be a string"}), 400
            discipline_category = discipline_category.strip() or None
            if discipline_category and len(discipline_category) > PROGRAM_DISCIPLINE_CATEGORY_MAX:
                return jsonify({
                    "error": f"discipline_category must be {PROGRAM_DISCIPLINE_CATEGORY_MAX} characters or fewer"
                }), 400
        program.discipline_category = discipline_category

    if "is_active" in data:
        is_active = data["is_active"]
        if not isinstance(is_active, bool):
            return jsonify({"error": "is_active must be true or false"}), 400
        program.is_active = is_active

    db.session.commit()

    return jsonify(_serialize_admin_program(program))


# ---------- Admin: groups (Chunk 10) ----------

@app.route("/admin/groups")
@require_admin
def admin_list_groups():
    """
    Lists groups for the admin dashboard, optionally filtered by
    ?search= (name substring) and ?status=active|inactive. Newest first.
    """
    search = (request.args.get("search") or "").strip()
    status_filter = (request.args.get("status") or "").strip().lower()
    if status_filter and status_filter not in ("active", "inactive"):
        return jsonify({"error": "status must be 'active' or 'inactive'"}), 400

    query = Group.query
    if search:
        query = query.filter(Group.name.ilike(f"%{search}%"))
    if status_filter == "active":
        query = query.filter(Group.is_active.is_(True))
    elif status_filter == "inactive":
        query = query.filter(Group.is_active.is_(False))

    groups = query.order_by(Group.created_at.desc()).all()

    return jsonify({"groups": [_serialize_group(g) for g in groups]})


@app.route("/admin/groups/<int:group_id>", methods=["PATCH"])
@require_csrf
@require_admin
def admin_update_group(group_id):
    """
    Admin kill-switch: activate/deactivate a group. Deactivating hides it
    from browse/join and blocks new posts/comments/joins for existing
    members too (see the is_active checks in join_group /
    create_group_post / create_group_post_comment) - stricter than the
    Organisation.is_active pattern, which only hides new opportunities
    rather than blocking ongoing member activity.
    """
    group = db.session.get(Group, group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    if "is_active" in data:
        is_active = data["is_active"]
        if not isinstance(is_active, bool):
            return jsonify({"error": "is_active must be true or false"}), 400
        group.is_active = is_active

    db.session.commit()

    return jsonify(_serialize_group(group))


@app.route("/admin/settings", methods=["GET"])
@require_admin
def admin_get_settings():
    settings = {s.key: s.value for s in SystemSetting.query.all()}

    def price(key):
        try:
            return int(settings.get(key, "0") or "0")
        except (TypeError, ValueError):
            return 0

    def daily_limit(key, default):
        raw = settings.get(key)
        if raw is None or raw == "":
            return default
        if raw.strip().lower() == "unlimited":
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    def money(key, default_str):
        try:
            return float(settings.get(key, default_str) or default_str)
        except (TypeError, ValueError):
            return float(default_str)

    return jsonify({
        "maintenance_mode": settings.get("maintenance_mode", "false") == "true",
        "maintenance_message": settings.get("maintenance_message", ""),
        "prepza_control_enabled": settings.get("prepza_control_enabled", "false") == "true",
        "price_notes": price("price_notes"),
        "price_past_paper": price("price_past_paper"),
        "price_qna": price("price_qna"),
        "price_plan_semester": price("price_plan_semester") or 599,
        "price_plan_annual": price("price_plan_annual") or 999,
        "price_promotion_standard": price("price_promotion_standard"),
        "price_promotion_featured": price("price_promotion_featured") or 300,
        "price_promotion_sponsored": price("price_promotion_sponsored") or 800,
        "ai_daily_limit_free": daily_limit("ai_daily_limit_free", 5),
        "ai_daily_limit_plus": daily_limit("ai_daily_limit_plus", 15),
        "ai_daily_limit_premium": daily_limit("ai_daily_limit_premium", None),
        "ai_daily_tutor_limit_free": daily_limit("ai_daily_tutor_limit_free", 5),
        "ai_daily_tutor_limit_plus": daily_limit("ai_daily_tutor_limit_plus", 20),
        "ai_daily_tutor_limit_premium": daily_limit("ai_daily_tutor_limit_premium", 50),
        "ai_monthly_budget_usd": money("ai_monthly_budget_usd", "300.00"),
    })


@app.route("/admin/settings", methods=["PATCH"])
@require_csrf
@require_admin
def admin_update_settings():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    if "maintenance_mode" in data:
        value = data["maintenance_mode"]
        if not isinstance(value, bool):
            return jsonify({"error": "maintenance_mode must be true or false"}), 400
        setting = SystemSetting.query.filter_by(key="maintenance_mode").first()
        if not setting:
            setting = SystemSetting(key="maintenance_mode", value="false")
            db.session.add(setting)
        setting.value = "true" if value else "false"

    if "maintenance_message" in data:
        message = data["maintenance_message"]
        if not isinstance(message, str):
            return jsonify({"error": "maintenance_message must be a string"}), 400
        if len(message) > 500:
            return jsonify({"error": "maintenance_message must be 500 characters or fewer"}), 400
        setting = SystemSetting.query.filter_by(key="maintenance_message").first()
        if not setting:
            setting = SystemSetting(key="maintenance_message", value="")
            db.session.add(setting)
        setting.value = message

    if "prepza_control_enabled" in data:
        value = data["prepza_control_enabled"]
        if not isinstance(value, bool):
            return jsonify({"error": "prepza_control_enabled must be true or false"}), 400
        setting = SystemSetting.query.filter_by(key="prepza_control_enabled").first()
        if not setting:
            setting = SystemSetting(key="prepza_control_enabled", value="false")
            db.session.add(setting)
        setting.value = "true" if value else "false"
        log_admin_action(
            session.get("user_id"),
            "control_api_enabled" if value else "control_api_disabled",
            target_type="control_api",
            details={"enabled": value},
        )

    for price_key in ("price_notes", "price_past_paper", "price_qna", "price_plan_semester", "price_plan_annual", "price_promotion_standard", "price_promotion_featured", "price_promotion_sponsored"):
        if price_key in data:
            value = data[price_key]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return jsonify({"error": f"{price_key} must be a non-negative integer"}), 400
            setting = SystemSetting.query.filter_by(key=price_key).first()
            if not setting:
                setting = SystemSetting(key=price_key, value="0")
                db.session.add(setting)
            setting.value = str(value)

    for tier_key in (
        "ai_daily_limit_free", "ai_daily_limit_plus", "ai_daily_limit_premium",
        "ai_daily_tutor_limit_free", "ai_daily_tutor_limit_plus", "ai_daily_tutor_limit_premium",
    ):
        if tier_key in data:
            value = data[tier_key]
            if value is None:
                stored = "unlimited"
            elif not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return jsonify({"error": f"{tier_key} must be a non-negative integer, or null for unlimited"}), 400
            else:
                stored = str(value)
            setting = SystemSetting.query.filter_by(key=tier_key).first()
            if not setting:
                setting = SystemSetting(key=tier_key, value=stored)
                db.session.add(setting)
            else:
                setting.value = stored

    if "ai_monthly_budget_usd" in data:
        value = data["ai_monthly_budget_usd"]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            return jsonify({"error": "ai_monthly_budget_usd must be a positive number"}), 400
        setting = SystemSetting.query.filter_by(key="ai_monthly_budget_usd").first()
        if not setting:
            setting = SystemSetting(key="ai_monthly_budget_usd", value=str(value))
            db.session.add(setting)
        else:
            setting.value = str(value)

    db.session.commit()
    _invalidate_maintenance_cache()

    mode_setting = SystemSetting.query.filter_by(key="maintenance_mode").first()
    message_setting = SystemSetting.query.filter_by(key="maintenance_message").first()
    control_setting = SystemSetting.query.filter_by(key="prepza_control_enabled").first()
    return jsonify({
        "maintenance_mode": bool(mode_setting and mode_setting.value == "true"),
        "maintenance_message": message_setting.value if message_setting else "",
        "prepza_control_enabled": bool(control_setting and control_setting.value == "true"),
    })


# ---------- Organisations (Opportunities + Organisation portal) ----------

ORGANISATION_NAME_MAX = 150
ORGANISATION_DESCRIPTION_MAX = 1000
ORGANISATION_WEBSITE_MAX = 500
ORGANISATION_LOGO_URL_MAX = 500
ORGANISATION_CONTACT_PHONE_MAX = 20


def _serialize_organisation(org, membership=None):
    return {
        "id": org.id,
        "name": org.name,
        "description": org.description,
        "website": org.website,
        "logo_url": org.logo_url,
        "contact_email": org.contact_email,
        "contact_phone": org.contact_phone,
        "verification_status": org.verification_status,
        "verification_notes": org.verification_notes,
        "is_active": org.is_active,
        "created_by": org.created_by,
        "created_at": org.created_at.isoformat() if org.created_at else None,
        "updated_at": org.updated_at.isoformat() if org.updated_at else None,
        "is_member": membership is not None,
        "role": membership.role if membership else None,
    }


def _validate_organisation_fields(data, partial=False):
    """
    Shared validation for create + update. Returns (fields, error_response)
    - fields is a dict of validated values to apply, error_response is
    (jsonify(...), status) or None. In partial mode, a field is only
    validated/included if present in data (PATCH semantics); in
    non-partial mode name/contact_email are always required (POST semantics).
    """
    fields = {}

    if not partial or "name" in data:
        name = (data.get("name") or "").strip()
        if not name or len(name) > ORGANISATION_NAME_MAX:
            return None, (jsonify({
                "error": f"name is required and must be {ORGANISATION_NAME_MAX} characters or fewer"
            }), 400)
        fields["name"] = name

    if not partial or "contact_email" in data:
        contact_email = (data.get("contact_email") or "").strip().lower()
        if not contact_email or not EMAIL_REGEX.match(contact_email):
            return None, (jsonify({"error": "A valid contact_email is required"}), 400)
        fields["contact_email"] = contact_email

    if "description" in data:
        description = data.get("description")
        if description is not None:
            if not isinstance(description, str):
                return None, (jsonify({"error": "description must be a string"}), 400)
            description = description.strip() or None
            if description and len(description) > ORGANISATION_DESCRIPTION_MAX:
                return None, (jsonify({
                    "error": f"description must be {ORGANISATION_DESCRIPTION_MAX} characters or fewer"
                }), 400)
        fields["description"] = description

    if "website" in data:
        website = data.get("website")
        if website is not None:
            if not isinstance(website, str):
                return None, (jsonify({"error": "website must be a string"}), 400)
            website = website.strip() or None
            if website and len(website) > ORGANISATION_WEBSITE_MAX:
                return None, (jsonify({
                    "error": f"website must be {ORGANISATION_WEBSITE_MAX} characters or fewer"
                }), 400)
        fields["website"] = website

    if "logo_url" in data:
        logo_url = data.get("logo_url")
        if logo_url is not None:
            if not isinstance(logo_url, str):
                return None, (jsonify({"error": "logo_url must be a string"}), 400)
            logo_url = logo_url.strip() or None
            if logo_url and len(logo_url) > ORGANISATION_LOGO_URL_MAX:
                return None, (jsonify({
                    "error": f"logo_url must be {ORGANISATION_LOGO_URL_MAX} characters or fewer"
                }), 400)
        fields["logo_url"] = logo_url

    if "contact_phone" in data:
        contact_phone = data.get("contact_phone")
        if contact_phone is not None:
            if not isinstance(contact_phone, str):
                return None, (jsonify({"error": "contact_phone must be a string"}), 400)
            contact_phone = contact_phone.strip() or None
            if contact_phone and len(contact_phone) > ORGANISATION_CONTACT_PHONE_MAX:
                return None, (jsonify({
                    "error": f"contact_phone must be {ORGANISATION_CONTACT_PHONE_MAX} characters or fewer"
                }), 400)
        fields["contact_phone"] = contact_phone

    return fields, None


@app.route("/organisations", methods=["POST"])
@require_csrf
def create_organisation():
    """
    Registers a new Organisation and makes the creator its 'owner'.
    New organisations start unverified (verification_status='pending') -
    they can be staffed and edited immediately, but their opportunities
    cannot be published until an admin verifies them (enforced in the
    opportunities routes patch).
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    fields, error = _validate_organisation_fields(data, partial=False)
    if error:
        return error

    org = Organisation(created_by=user_id, **fields)
    db.session.add(org)
    db.session.flush()  # assign org.id before the membership row references it

    membership = OrganisationMember(organisation_id=org.id, user_id=user_id, role="owner")
    db.session.add(membership)
    db.session.commit()

    return jsonify(_serialize_organisation(org, membership)), 201


@app.route("/organisations/mine")
def my_organisations():
    """Lists every Organisation the caller is a member of, any role."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    memberships = OrganisationMember.query.filter_by(user_id=user_id).all()
    result = []
    for m in memberships:
        org = db.session.get(Organisation, m.organisation_id)
        if not org:
            continue
        result.append(_serialize_organisation(org, m))

    return jsonify({"organisations": result})


@app.route("/organisations/<int:organisation_id>")
def get_organisation(organisation_id):
    """
    Full org profile - members and admins only. Non-members get a 404
    (not a 403) so this can't be used to enumerate which organisations
    exist or probe their contact details.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    membership = OrganisationMember.query.filter_by(
        organisation_id=organisation_id, user_id=user_id
    ).first()

    viewer = db.session.get(User, user_id)
    is_admin = bool(viewer and viewer.is_admin)

    if not membership and not is_admin:
        return jsonify({"error": "Organisation not found"}), 404

    return jsonify(_serialize_organisation(org, membership))


@app.route("/organisations/<int:organisation_id>", methods=["PATCH"])
@require_csrf
def update_organisation(organisation_id):
    """
    Edits an org's own profile. Owner-only - per OrganisationMember's
    role split, 'manager' can submit/edit opportunities but does not
    manage the organisation account itself.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    membership = OrganisationMember.query.filter_by(
        organisation_id=organisation_id, user_id=user_id
    ).first()
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404
    if membership.role != "owner":
        return jsonify({"error": "Only the organisation owner can edit its profile"}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    fields, error = _validate_organisation_fields(data, partial=True)
    if error:
        return error

    for key, value in fields.items():
        setattr(org, key, value)
    db.session.commit()

    return jsonify(_serialize_organisation(org, membership))


@app.route("/admin/organisations")
@require_admin
def admin_list_organisations():
    """
    Lists organisations for the admin dashboard, optionally filtered by
    verification_status. Oldest-first, same "review queue" ordering as
    admin_library_queue - whether or not a status filter is applied.
    """
    status_filter = request.args.get("verification_status")
    query = Organisation.query
    if status_filter:
        if status_filter not in ORGANISATION_VERIFICATION_STATUSES:
            return jsonify({
                "error": "verification_status must be one of: " + ", ".join(ORGANISATION_VERIFICATION_STATUSES)
            }), 400
        query = query.filter_by(verification_status=status_filter)

    orgs = query.order_by(Organisation.created_at.asc()).all()

    result = []
    for org in orgs:
        owner_membership = OrganisationMember.query.filter_by(
            organisation_id=org.id, role="owner"
        ).first()
        owner_user = db.session.get(User, owner_membership.user_id) if owner_membership else None
        entry = _serialize_organisation(org)
        entry["owner_email"] = owner_user.email if owner_user else None
        result.append(entry)

    return jsonify({"organisations": result})


@app.route("/admin/organisations/<int:organisation_id>/verify", methods=["POST"])
@require_csrf
@require_admin
def admin_verify_organisation(organisation_id):
    """Verifies a pending or previously-rejected organisation."""
    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404
    if org.verification_status == "verified":
        return jsonify({"error": "Organisation is already verified"}), 400

    org.verification_status = "verified"
    org.verification_notes = None
    db.session.commit()

    return jsonify(_serialize_organisation(org))


@app.route("/admin/organisations/<int:organisation_id>/reject", methods=["POST"])
@require_csrf
@require_admin
def admin_reject_organisation(organisation_id):
    """
    Rejects a pending organisation with a required reason. Refuses to
    reject an already-verified org - revoking a verified org's standing
    is a separate action (the is_active kill-switch below), not a
    verification-flow rejection.
    """
    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404
    if org.verification_status == "verified":
        return jsonify({
            "error": "Cannot reject an already-verified organisation - deactivate it instead"
        }), 400

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason or len(reason) > 500:
        return jsonify({"error": "reason is required and must be 500 characters or fewer"}), 400

    org.verification_status = "rejected"
    org.verification_notes = reason
    db.session.commit()

    return jsonify(_serialize_organisation(org))


@app.route("/admin/organisations/<int:organisation_id>", methods=["PATCH"])
@require_csrf
@require_admin
def admin_update_organisation(organisation_id):
    """Admin kill-switch: activate/deactivate an organisation. Deactivating
    hides its opportunities without deleting anything (enforced in the
    opportunities routes patch)."""
    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    if "is_active" in data:
        is_active = data["is_active"]
        if not isinstance(is_active, bool):
            return jsonify({"error": "is_active must be true or false"}), 400
        org.is_active = is_active

    db.session.commit()

    return jsonify(_serialize_organisation(org))


# ---------- Organisation staff management ----------
# Lets an org 'owner' invite/remove 'manager' staff. Deliberately does NOT
# support transferring ownership or promoting a manager to owner - every
# Organisation has exactly one owner (the creator, set at POST
# /organisations time) and that never changes here, same "no speculative
# building" tradeoff as elsewhere in this file. A manager can submit/edit
# opportunities (per the existing OrganisationMember role split) but has
# no say over org staffing itself.

def _serialize_org_member(membership):
    user = db.session.get(User, membership.user_id)
    return {
        "user_id": membership.user_id,
        "email": user.email if user else None,
        "display_name": _display_name(user) if user else "Deleted user",
        "role": membership.role,
        "joined_at": membership.joined_at.isoformat() if membership.joined_at else None,
    }


@app.route("/organisations/<int:organisation_id>/members")
def list_organisation_members(organisation_id):
    """Any member (owner or manager) can view the staff list. Non-members
    get a 404, same "don't confirm existence" pattern as get_organisation()."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    members = (
        OrganisationMember.query.filter_by(organisation_id=organisation_id)
        .order_by(OrganisationMember.joined_at.asc())
        .all()
    )
    members.sort(key=lambda m: 0 if m.role == "owner" else 1)

    return jsonify({"members": [_serialize_org_member(m) for m in members]})


@app.route("/organisations/<int:organisation_id>/members", methods=["POST"])
@require_csrf
def add_organisation_member(organisation_id):
    """
    Owner-only: invites an existing Prepza user as a 'manager'. Takes a
    user_id (not an email) - same "search then add" pattern as group
    creation's member_user_ids, resolved client-side via the existing
    GET /users/search picker rather than an email-invite flow, since
    every staffer must already have a Prepza account to sign in as.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    membership = _get_org_membership(organisation_id, user_id)
    if not membership or membership.role != "owner":
        return jsonify({"error": "Only the organisation owner can add staff"}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    target_user_id = data.get("user_id")
    if not isinstance(target_user_id, int) or isinstance(target_user_id, bool):
        return jsonify({"error": "user_id is required"}), 400
    if target_user_id == user_id:
        return jsonify({"error": "You're already the owner of this organisation"}), 400

    target_user = db.session.get(User, target_user_id)
    if not target_user or target_user.is_suspended:
        return jsonify({"error": "User not found"}), 404

    existing = OrganisationMember.query.filter_by(
        organisation_id=organisation_id, user_id=target_user_id
    ).first()
    if existing:
        return jsonify({"message": "Already staff", "member": _serialize_org_member(existing)}), 200

    new_member = OrganisationMember(organisation_id=organisation_id, user_id=target_user_id, role="manager")
    db.session.add(new_member)
    db.session.commit()

    return jsonify(_serialize_org_member(new_member)), 201


@app.route("/organisations/<int:organisation_id>/members/<int:target_user_id>", methods=["DELETE"])
@require_csrf
def remove_organisation_member(organisation_id, target_user_id):
    """
    Owner-only removal of a manager. Refuses to remove the owner (there's
    no ownership-transfer flow, so removing the owner would strand the
    org with no one able to manage staff or edit its profile) and refuses
    self-removal for the same reason.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    membership = _get_org_membership(organisation_id, user_id)
    if not membership or membership.role != "owner":
        return jsonify({"error": "Only the organisation owner can remove staff"}), 403

    if target_user_id == user_id:
        return jsonify({"error": "The owner can't remove themselves"}), 400

    target = OrganisationMember.query.filter_by(
        organisation_id=organisation_id, user_id=target_user_id
    ).first()
    if not target:
        return jsonify({"error": "Staff member not found"}), 404
    if target.role == "owner":
        return jsonify({"error": "Can't remove the organisation owner"}), 400

    db.session.delete(target)
    db.session.commit()

    return jsonify({"message": "Staff member removed"})


# ---------- Opportunities (organisation-side CRUD) ----------

from datetime import timezone

OPPORTUNITY_TITLE_MAX = 200
OPPORTUNITY_DESCRIPTION_MAX = 5000
OPPORTUNITY_LOCATION_MAX = 200
OPPORTUNITY_APPLICATION_URL_MAX = 500
OPPORTUNITY_INSTRUCTIONS_MAX = 3000
OPPORTUNITY_EDITABLE_STATUSES = ("draft", "rejected")


def _get_org_membership(organisation_id, user_id):
    return OrganisationMember.query.filter_by(
        organisation_id=organisation_id, user_id=user_id
    ).first()


def _parse_iso_datetime(value):
    """
    Parses an ISO-8601 string into a naive UTC datetime (matching the
    naive datetime.utcnow() convention used throughout this file).
    Returns None if value is missing/invalid rather than raising -
    callers turn that into a 400.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _serialize_opportunity(opp):
    return {
        "id": opp.id,
        "organisation_id": opp.organisation_id,
        "created_by": opp.created_by,
        "title": opp.title,
        "description": opp.description,
        "opportunity_type": opp.opportunity_type,
        "location": opp.location,
        "is_remote": opp.is_remote,
        "application_url": opp.application_url,
        "application_instructions": opp.application_instructions,
        "application_deadline": opp.application_deadline.isoformat() if opp.application_deadline else None,
        "expiry_date": opp.expiry_date.isoformat() if opp.expiry_date else None,
        "status": opp.status,
        "rejection_reason": opp.rejection_reason,
        "submitted_at": opp.submitted_at.isoformat() if opp.submitted_at else None,
        "reviewed_at": opp.reviewed_at.isoformat() if opp.reviewed_at else None,
        "published_at": opp.published_at.isoformat() if opp.published_at else None,
        "view_count": opp.view_count,
        "created_at": opp.created_at.isoformat() if opp.created_at else None,
        "updated_at": opp.updated_at.isoformat() if opp.updated_at else None,
    }


def _validate_opportunity_fields(data, partial=False):
    """
    Shared validation for create + update. Returns (fields, error_response).
    Does NOT validate the deadline/expiry cross-field ordering - callers
    do that themselves once they know the row's effective final values
    (needed because PATCH may only change one of the two dates).
    """
    fields = {}

    if not partial or "title" in data:
        title = (data.get("title") or "").strip()
        if not title or len(title) > OPPORTUNITY_TITLE_MAX:
            return None, (jsonify({
                "error": f"title is required and must be {OPPORTUNITY_TITLE_MAX} characters or fewer"
            }), 400)
        fields["title"] = title

    if not partial or "description" in data:
        description = (data.get("description") or "").strip()
        if not description or len(description) > OPPORTUNITY_DESCRIPTION_MAX:
            return None, (jsonify({
                "error": f"description is required and must be {OPPORTUNITY_DESCRIPTION_MAX} characters or fewer"
            }), 400)
        fields["description"] = description

    if not partial or "opportunity_type" in data:
        opportunity_type = (data.get("opportunity_type") or "").strip().lower()
        if opportunity_type not in OPPORTUNITY_TYPES:
            return None, (jsonify({
                "error": "opportunity_type must be one of: " + ", ".join(OPPORTUNITY_TYPES)
            }), 400)
        fields["opportunity_type"] = opportunity_type

    if "location" in data:
        location = data.get("location")
        if location is not None:
            if not isinstance(location, str):
                return None, (jsonify({"error": "location must be a string"}), 400)
            location = location.strip() or None
            if location and len(location) > OPPORTUNITY_LOCATION_MAX:
                return None, (jsonify({
                    "error": f"location must be {OPPORTUNITY_LOCATION_MAX} characters or fewer"
                }), 400)
        fields["location"] = location

    if "is_remote" in data:
        is_remote = data.get("is_remote")
        if not isinstance(is_remote, bool):
            return None, (jsonify({"error": "is_remote must be true or false"}), 400)
        fields["is_remote"] = is_remote

    if "application_url" in data:
        application_url = data.get("application_url")
        if application_url is not None:
            if not isinstance(application_url, str):
                return None, (jsonify({"error": "application_url must be a string"}), 400)
            application_url = application_url.strip() or None
            if application_url and len(application_url) > OPPORTUNITY_APPLICATION_URL_MAX:
                return None, (jsonify({
                    "error": f"application_url must be {OPPORTUNITY_APPLICATION_URL_MAX} characters or fewer"
                }), 400)
        fields["application_url"] = application_url

    if "application_instructions" in data:
        instructions = data.get("application_instructions")
        if instructions is not None:
            if not isinstance(instructions, str):
                return None, (jsonify({"error": "application_instructions must be a string"}), 400)
            instructions = instructions.strip() or None
            if instructions and len(instructions) > OPPORTUNITY_INSTRUCTIONS_MAX:
                return None, (jsonify({
                    "error": f"application_instructions must be {OPPORTUNITY_INSTRUCTIONS_MAX} characters or fewer"
                }), 400)
        fields["application_instructions"] = instructions

    if not partial or "application_deadline" in data:
        deadline = _parse_iso_datetime(data.get("application_deadline"))
        if not deadline:
            return None, (jsonify({
                "error": "application_deadline is required and must be a valid ISO datetime"
            }), 400)
        fields["application_deadline"] = deadline

    if not partial or "expiry_date" in data:
        expiry = _parse_iso_datetime(data.get("expiry_date"))
        if not expiry:
            return None, (jsonify({
                "error": "expiry_date is required and must be a valid ISO datetime"
            }), 400)
        fields["expiry_date"] = expiry

    return fields, None


@app.route("/organisations/<int:organisation_id>/opportunities", methods=["POST"])
@require_csrf
def create_opportunity(organisation_id):
    """
    Creates a new Opportunity in status='draft'. Allowed even if the
    organisation isn't verified yet - verification is only required to
    submit for review (see submit_opportunity below), not to draft one.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    fields, error = _validate_opportunity_fields(data, partial=False)
    if error:
        return error

    if fields["expiry_date"] <= fields["application_deadline"]:
        return jsonify({"error": "expiry_date must be after application_deadline"}), 400
    if fields["application_deadline"] <= datetime.utcnow():
        return jsonify({"error": "application_deadline must be in the future"}), 400

    opp = Opportunity(
        organisation_id=organisation_id, created_by=user_id, status="draft", **fields
    )
    db.session.add(opp)
    db.session.commit()

    return jsonify(_serialize_opportunity(opp)), 201


@app.route("/organisations/<int:organisation_id>/opportunities")
def list_org_opportunities(organisation_id):
    """Lists this org's own opportunities, any status. ?status= filters
    to one status (management view - not the public browse endpoint)."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    query = Opportunity.query.filter_by(organisation_id=organisation_id)

    status_filter = request.args.get("status")
    if status_filter:
        if status_filter not in OPPORTUNITY_STATUSES:
            return jsonify({
                "error": "status must be one of: " + ", ".join(OPPORTUNITY_STATUSES)
            }), 400
        query = query.filter_by(status=status_filter)

    opportunities = query.order_by(Opportunity.created_at.desc()).all()
    return jsonify({"opportunities": [_serialize_opportunity(o) for o in opportunities]})


@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>")
def get_org_opportunity(organisation_id, opportunity_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp or opp.organisation_id != organisation_id:
        return jsonify({"error": "Opportunity not found"}), 404

    return jsonify(_serialize_opportunity(opp))


@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>", methods=["PATCH"])
@require_csrf
def update_opportunity(organisation_id, opportunity_id):
    """
    Edits an opportunity. Only allowed while status is 'draft' or
    'rejected' - once it's in the review/published pipeline, the org
    can't silently change it out from under an approval; they'd need to
    withdraw and recreate, or (for rejected ones) fix it up here and
    resubmit via /submit.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp or opp.organisation_id != organisation_id:
        return jsonify({"error": "Opportunity not found"}), 404

    if opp.status not in OPPORTUNITY_EDITABLE_STATUSES:
        return jsonify({
            "error": f"Cannot edit an opportunity with status '{opp.status}' - "
                     f"only draft or rejected opportunities can be edited"
        }), 400

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    fields, error = _validate_opportunity_fields(data, partial=True)
    if error:
        return error

    effective_deadline = fields.get("application_deadline", opp.application_deadline)
    effective_expiry = fields.get("expiry_date", opp.expiry_date)
    if effective_expiry <= effective_deadline:
        return jsonify({"error": "expiry_date must be after application_deadline"}), 400

    for key, value in fields.items():
        setattr(opp, key, value)
    db.session.commit()

    return jsonify(_serialize_opportunity(opp))


@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>/submit", methods=["POST"])
@require_csrf
def submit_opportunity(organisation_id, opportunity_id):
    """
    Moves draft/rejected -> pending_review. Requires the organisation to
    be verified AND active (an unverified or deactivated org's postings
    never enter the admin review queue), and requires the opportunity's
    own dates to not already be in the past.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    if org.verification_status != "verified" or not org.is_active:
        return jsonify({
            "error": "Organisation must be verified and active before submitting opportunities for review"
        }), 400

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp or opp.organisation_id != organisation_id:
        return jsonify({"error": "Opportunity not found"}), 404

    if opp.status not in OPPORTUNITY_EDITABLE_STATUSES:
        return jsonify({
            "error": f"Cannot submit an opportunity with status '{opp.status}'"
        }), 400

    now = datetime.utcnow()
    if opp.application_deadline <= now or opp.expiry_date <= now:
        return jsonify({
            "error": "Cannot submit - application_deadline or expiry_date has already passed. "
                     "Update the dates first."
        }), 400

    opp.status = "pending_review"
    opp.submitted_at = now
    opp.rejection_reason = None
    db.session.commit()

    return jsonify(_serialize_opportunity(opp))


@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>/archive", methods=["POST"])
@require_csrf
def archive_opportunity(organisation_id, opportunity_id):
    """Org self-service archive - lets them retire a published or
    already-expired posting without waiting on an admin."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp or opp.organisation_id != organisation_id:
        return jsonify({"error": "Opportunity not found"}), 404

    if opp.status not in ("published", "expired"):
        return jsonify({
            "error": f"Cannot archive an opportunity with status '{opp.status}'"
        }), 400

    opp.status = "archived"
    db.session.commit()

    return jsonify(_serialize_opportunity(opp))


@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>", methods=["DELETE"])
@require_csrf
def withdraw_opportunity(organisation_id, opportunity_id):
    """Org withdraws its own opportunity at any point in its lifecycle
    (except if already removed). Soft-delete via status='removed', same
    pattern as Document.is_removed elsewhere in this file."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp or opp.organisation_id != organisation_id:
        return jsonify({"error": "Opportunity not found"}), 404

    if opp.status == "removed":
        return jsonify({"message": "Already removed"}), 200

    opp.status = "removed"
    db.session.commit()

    return jsonify({"message": "Opportunity withdrawn"})


# ---------- Admin: Opportunity review ----------

def _serialize_opportunity_admin(opp):
    """Same shape as _serialize_opportunity() plus the organisation's
    name/verification state, so the admin queue doesn't need a second
    round trip per row."""
    org = db.session.get(Organisation, opp.organisation_id)
    entry = _serialize_opportunity(opp)
    entry["organisation_name"] = org.name if org else None
    entry["organisation_verification_status"] = org.verification_status if org else None
    entry["organisation_is_active"] = org.is_active if org else None
    return entry


@app.route("/admin/opportunities")
@require_admin
def admin_list_opportunities():
    """Review queue. Defaults to pending_review only (the actual queue);
    pass status=all to see every opportunity regardless of status, or
    a specific status to filter to just that one."""
    status_filter = request.args.get("status", "pending_review")

    query = Opportunity.query
    if status_filter != "all":
        if status_filter not in OPPORTUNITY_STATUSES:
            return jsonify({
                "error": "status must be 'all' or one of: " + ", ".join(OPPORTUNITY_STATUSES)
            }), 400
        query = query.filter_by(status=status_filter)

    opportunities = query.order_by(Opportunity.submitted_at.asc().nullslast(), Opportunity.created_at.asc()).all()
    return jsonify({"opportunities": [_serialize_opportunity_admin(o) for o in opportunities]})


@app.route("/admin/opportunities/<int:opportunity_id>/approve", methods=["POST"])
@require_csrf
@require_admin
def admin_approve_opportunity(opportunity_id):
    """
    Approves a pending_review opportunity. Does NOT publish it - Publish
    is a separate, deliberate action (see admin_publish_opportunity)
    so an admin can approve now and schedule the actual go-live
    separately. Re-checks the organisation is still verified and active,
    since its standing could have changed since submission.
    """
    acting_admin_id = session.get("user_id")

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp:
        return jsonify({"error": "Opportunity not found"}), 404
    if opp.status != "pending_review":
        return jsonify({"error": f"Opportunity is not pending review (status: {opp.status})"}), 400

    org = db.session.get(Organisation, opp.organisation_id)
    if not org or org.verification_status != "verified" or not org.is_active:
        return jsonify({
            "error": "The submitting organisation is no longer verified and active - "
                     "resolve that before approving"
        }), 400

    opp.status = "approved"
    opp.rejection_reason = None
    opp.reviewed_by = acting_admin_id
    opp.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_serialize_opportunity_admin(opp))


@app.route("/admin/opportunities/<int:opportunity_id>/reject", methods=["POST"])
@require_csrf
@require_admin
def admin_reject_opportunity(opportunity_id):
    """Rejects a pending_review opportunity with a required reason. The
    org can edit and resubmit via its own PATCH + /submit routes."""
    acting_admin_id = session.get("user_id")

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp:
        return jsonify({"error": "Opportunity not found"}), 404
    if opp.status != "pending_review":
        return jsonify({"error": f"Opportunity is not pending review (status: {opp.status})"}), 400

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason or len(reason) > 500:
        return jsonify({"error": "reason is required and must be 500 characters or fewer"}), 400

    opp.status = "rejected"
    opp.rejection_reason = reason
    opp.reviewed_by = acting_admin_id
    opp.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_serialize_opportunity_admin(opp))


@app.route("/admin/opportunities/<int:opportunity_id>/publish", methods=["POST"])
@require_csrf
@require_admin
def admin_publish_opportunity(opportunity_id):
    """
    Makes an approved opportunity live (visible to students - see the
    browse routes patch). Re-checks the organisation's standing and the
    opportunity's own dates one more time, since time may have passed
    since approval.
    """
    opp = db.session.get(Opportunity, opportunity_id)
    if not opp:
        return jsonify({"error": "Opportunity not found"}), 404
    if opp.status != "approved":
        return jsonify({"error": f"Opportunity is not approved (status: {opp.status})"}), 400

    org = db.session.get(Organisation, opp.organisation_id)
    if not org or org.verification_status != "verified" or not org.is_active:
        return jsonify({
            "error": "The submitting organisation is no longer verified and active - "
                     "resolve that before publishing"
        }), 400

    now = datetime.utcnow()
    if opp.application_deadline <= now or opp.expiry_date <= now:
        return jsonify({
            "error": "Cannot publish - application_deadline or expiry_date has already passed"
        }), 400

    opp.status = "published"
    opp.published_at = now
    db.session.commit()

    return jsonify(_serialize_opportunity_admin(opp))


@app.route("/admin/opportunities/<int:opportunity_id>/archive", methods=["POST"])
@require_csrf
@require_admin
def admin_archive_opportunity(opportunity_id):
    """Admin-side archive - broader than the org's own self-service
    archive route (which only allows published/expired); admins can
    also archive an approved-but-not-yet-published listing."""
    opp = db.session.get(Opportunity, opportunity_id)
    if not opp:
        return jsonify({"error": "Opportunity not found"}), 404
    if opp.status not in ("approved", "published", "expired"):
        return jsonify({
            "error": f"Cannot archive an opportunity with status '{opp.status}'"
        }), 400

    opp.status = "archived"
    db.session.commit()

    return jsonify(_serialize_opportunity_admin(opp))


@app.route("/admin/opportunities/<int:opportunity_id>/remove", methods=["POST"])
@require_csrf
@require_admin
def admin_remove_opportunity(opportunity_id):
    """
    Admin takedown for a policy violation or similar, from any
    non-removed state - broader than either self-service route. An
    optional reason is stored in the same rejection_reason column used
    by the reject flow (kept generic rather than adding a parallel
    column for what is, functionally, the same "why did an admin act
    on this" note).
    """
    acting_admin_id = session.get("user_id")

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp:
        return jsonify({"error": "Opportunity not found"}), 404
    if opp.status == "removed":
        return jsonify({"message": "Already removed"}), 200

    data = request.get_json(silent=True) or {}
    reason = data.get("reason")
    if reason is not None:
        reason = reason.strip()
        if len(reason) > 500:
            return jsonify({"error": "reason must be 500 characters or fewer"}), 400
        reason = reason or None

    opp.status = "removed"
    opp.rejection_reason = reason
    opp.reviewed_by = acting_admin_id
    opp.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_serialize_opportunity_admin(opp))


# ---------- Opportunity Promotions (Step 5b) ----------

OPPORTUNITY_PROMOTION_EDITABLE_OPPORTUNITY_STATUSES = ("pending_review", "approved", "published")


def get_promotion_prices():
    """
    Returns a dict of promotion_type -> price (KES), sourced from
    SystemSetting rows (price_promotion_standard, price_promotion_featured,
    price_promotion_sponsored) - same pattern as get_plan_prices() /
    get_content_prices(). Missing or invalid settings fall back to the
    defaults below.
    """
    keys = ("price_promotion_standard", "price_promotion_featured", "price_promotion_sponsored")
    settings = {
        s.key: s.value
        for s in SystemSetting.query.filter(SystemSetting.key.in_(keys)).all()
    }

    def parse(key, default):
        try:
            return int(settings.get(key) or default)
        except (TypeError, ValueError):
            return default

    return {
        "standard": parse("price_promotion_standard", 0),
        "featured": parse("price_promotion_featured", 300),
        "sponsored": parse("price_promotion_sponsored", 800),
    }


def _serialize_opportunity_promotion(promo, include_context=False):
    result = {
        "id": promo.id,
        "opportunity_id": promo.opportunity_id,
        "organisation_id": promo.organisation_id,
        "promotion_type": promo.promotion_type,
        "start_date": promo.start_date.isoformat() if promo.start_date else None,
        "end_date": promo.end_date.isoformat() if promo.end_date else None,
        "price": promo.price,
        "payment_status": promo.payment_status,
        "payment_required": promo.price > 0,
        "approval_status": promo.approval_status,
        "reviewed_at": promo.reviewed_at.isoformat() if promo.reviewed_at else None,
        "created_at": promo.created_at.isoformat() if promo.created_at else None,
        "updated_at": promo.updated_at.isoformat() if promo.updated_at else None,
    }
    if include_context:
        opp = db.session.get(Opportunity, promo.opportunity_id)
        org = db.session.get(Organisation, promo.organisation_id)
        result["opportunity_title"] = opp.title if opp else None
        result["organisation_name"] = org.name if org else None
    return result


@app.route("/organisations/promotion-prices")
def organisation_promotion_prices():
    """Returns the current admin-configured promotion price catalogue.
    Prices are informational; every promotion still snapshots its server-side
    price when requested, so the client can never choose the charge amount."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    prices = get_promotion_prices()
    return jsonify({
        "currency": "KES",
        "prices": prices,
        "billing_flow": "request -> server price snapshot -> Paystack checkout -> payment verification -> admin approval",
    })


@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>/promotions", methods=["POST"])
@require_csrf
def request_opportunity_promotion(organisation_id, opportunity_id):
    """
    Requests a promotion campaign for one of the org's own opportunities.
    price is snapshotted at request time from admin-configurable
    SystemSetting pricing (see get_promotion_prices()) - same reasoning
    as Payment.amount. Deliberately does NOT touch payment_status here;
    actual payment collection/webhook wiring belongs to the Payments
    chunk, which hasn't wired into this yet - payment_status stays at
    its 'unpaid' default until that lands.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp or opp.organisation_id != organisation_id:
        return jsonify({"error": "Opportunity not found"}), 404

    if opp.status not in OPPORTUNITY_PROMOTION_EDITABLE_OPPORTUNITY_STATUSES:
        return jsonify({
            "error": f"Cannot promote an opportunity with status '{opp.status}'"
        }), 400

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    promotion_type = (data.get("promotion_type") or "").strip().lower()
    if promotion_type not in OPPORTUNITY_PROMOTION_TYPES:
        return jsonify({
            "error": "promotion_type must be one of: " + ", ".join(OPPORTUNITY_PROMOTION_TYPES)
        }), 400

    start_date = _parse_iso_datetime(data.get("start_date"))
    if not start_date:
        return jsonify({"error": "start_date is required and must be a valid ISO datetime"}), 400

    end_date = _parse_iso_datetime(data.get("end_date"))
    if not end_date:
        return jsonify({"error": "end_date is required and must be a valid ISO datetime"}), 400

    now = datetime.utcnow()
    if start_date < now:
        return jsonify({"error": "start_date cannot be in the past"}), 400
    if end_date <= start_date:
        return jsonify({"error": "end_date must be after start_date"}), 400
    if end_date > opp.expiry_date:
        return jsonify({"error": "end_date cannot be after the opportunity's own expiry_date"}), 400

    price = get_promotion_prices().get(promotion_type, 0)

    promo = OpportunityPromotion(
        opportunity_id=opportunity_id,
        organisation_id=organisation_id,
        promotion_type=promotion_type,
        start_date=start_date,
        end_date=end_date,
        price=price,
        payment_status="not_required" if price <= 0 else "unpaid",
        approval_status="pending",
    )
    db.session.add(promo)
    db.session.commit()

    return jsonify(_serialize_opportunity_promotion(promo)), 201


@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>/promotions")
def list_opportunity_promotions(organisation_id, opportunity_id):
    """Lists the org's own promotion requests for one opportunity, any
    approval_status, newest first."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp or opp.organisation_id != organisation_id:
        return jsonify({"error": "Opportunity not found"}), 404

    promotions = (
        OpportunityPromotion.query.filter_by(
            opportunity_id=opportunity_id, organisation_id=organisation_id
        )
        .order_by(OpportunityPromotion.created_at.desc())
        .all()
    )

    return jsonify({"promotions": [_serialize_opportunity_promotion(p) for p in promotions]})


@app.route("/admin/opportunity-promotions")
@require_admin
def admin_list_opportunity_promotions():
    """
    Admin queue for promotion requests. Defaults to pending only; pass
    approval_status=all to see approved/rejected ones too. Each row
    includes opportunity_title/organisation_name for admin readability.
    """
    status_filter = request.args.get("approval_status", "pending")
    if status_filter != "all" and status_filter not in OPPORTUNITY_PROMOTION_APPROVAL_STATUSES:
        return jsonify({
            "error": "approval_status must be 'all' or one of: " + ", ".join(OPPORTUNITY_PROMOTION_APPROVAL_STATUSES)
        }), 400

    query = OpportunityPromotion.query
    if status_filter != "all":
        query = query.filter_by(approval_status=status_filter)

    promotions = query.order_by(OpportunityPromotion.created_at.asc()).all()

    return jsonify({
        "promotions": [_serialize_opportunity_promotion(p, include_context=True) for p in promotions]
    })


@app.route("/organisations/<int:organisation_id>/opportunity-promotions/<int:promotion_id>/pay", methods=["POST"])
@limiter.limit("1 per 20 seconds", key_func=lambda: f"org-promo-pay:{session.get('user_id', get_remote_address())}")
@require_csrf
def pay_for_opportunity_promotion(organisation_id, promotion_id):
    """Create the one-time Paystack checkout for a paid promotion.

    Billing is owner-only. Managers can create and manage opportunity content,
    but cannot spend organisation funds. The promotion price is already a
    server-side snapshot, so the client cannot choose its amount.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404
    if membership.role != "owner":
        return jsonify({"error": "Only the organisation owner can pay for promotions"}), 403

    promo = db.session.get(OpportunityPromotion, promotion_id)
    if not promo or promo.organisation_id != organisation_id:
        return jsonify({"error": "Promotion request not found"}), 404
    if promo.approval_status == "rejected":
        return jsonify({"error": "This promotion request was rejected"}), 400
    if promo.price <= 0:
        promo.payment_status = "not_required"
        db.session.commit()
        return jsonify({"payment_required": False, "promotion": _serialize_opportunity_promotion(promo)})
    if promo.payment_status == "success":
        return jsonify({"payment_required": False, "promotion": _serialize_opportunity_promotion(promo)})

    existing = Payment.query.filter_by(
        opportunity_promotion_id=promo.id, status="pending"
    ).order_by(Payment.created_at.desc()).first()
    if existing:
        try:
            synced = sync_paystack_payment_status(existing.reference)
            if synced and synced.status == "success":
                return jsonify({"payment_required": False, "promotion": _serialize_opportunity_promotion(promo)})
        except Exception:
            pass

    reference = f"PZA-promo-{promo.id}-{secrets.token_hex(6)}"
    user = db.session.get(User, user_id)
    try:
        provider_reference, authorization_url = create_paystack_transaction(
            reference, promo.price, f"Prepza promotion - {promo.promotion_type}", user
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    payment = Payment(
        user_id=user_id,
        organisation_id=organisation_id,
        opportunity_promotion_id=promo.id,
        amount=promo.price,
        provider="paystack",
        reference=reference,
        provider_reference=provider_reference,
        payment_type="promotion",
        status="pending",
    )
    db.session.add(payment)
    promo.payment_status = "pending"
    db.session.commit()
    return jsonify({
        "payment_required": True,
        "redirect_url": authorization_url,
        "reference": reference,
        "promotion": _serialize_opportunity_promotion(promo),
    })


@app.route("/admin/opportunity-promotions/<int:promotion_id>/approve", methods=["POST"])
@require_csrf
@require_admin
def admin_approve_opportunity_promotion(promotion_id):
    """
    Approves a pending promotion request. Deliberately does NOT check or
    change payment_status - real payment collection/webhook wiring
    belongs to the Payments chunk, which hasn't wired into this yet.
    Approval here means "this promotion is allowed to run", not "it has
    been paid for" - don't assume the two are the same thing.
    """
    acting_admin_id = session.get("user_id")

    promo = db.session.get(OpportunityPromotion, promotion_id)
    if not promo:
        return jsonify({"error": "Promotion request not found"}), 404
    if promo.approval_status != "pending":
        return jsonify({
            "error": f"Promotion request is not pending (approval_status: {promo.approval_status})"
        }), 400
    if promo.price > 0 and promo.payment_status != "success":
        return jsonify({"error": "Promotion must be paid before it can be approved"}), 402

    promo.approval_status = "approved"
    promo.reviewed_by = acting_admin_id
    promo.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_serialize_opportunity_promotion(promo))


@app.route("/admin/opportunity-promotions/<int:promotion_id>/reject", methods=["POST"])
@require_csrf
@require_admin
def admin_reject_opportunity_promotion(promotion_id):
    """Rejects a pending promotion request. Reason is optional (unlike
    Opportunity rejection) since promotions are a lower-stakes add-on,
    not a content moderation decision."""
    acting_admin_id = session.get("user_id")

    promo = db.session.get(OpportunityPromotion, promotion_id)
    if not promo:
        return jsonify({"error": "Promotion request not found"}), 404
    if promo.approval_status != "pending":
        return jsonify({
            "error": f"Promotion request is not pending (approval_status: {promo.approval_status})"
        }), 400

    promo.approval_status = "rejected"
    promo.reviewed_by = acting_admin_id
    promo.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_serialize_opportunity_promotion(promo))



# ---------- Opportunities (student-facing browse) (Step 6) ----------

class SavedOpportunity(db.Model):
    """A student bookmarking an Opportunity - same shape/reasoning as
    SavedLibraryMaterial."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("opportunity.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("user_id", "opportunity_id", name="uq_saved_opportunity_user_opp"),
    )


OPPORTUNITY_BROWSE_PAGE_SIZE = 20

# sponsored > featured > standard - lower rank number surfaces first.
_PROMOTION_TYPE_RANK = {"sponsored": 0, "featured": 1, "standard": 2}


def _serialize_organisation_public(org):
    """
    Public-safe organisation fields only. Deliberately excludes
    contact_email/contact_phone, which are org-management-only per the
    existing _serialize_organisation() - students browsing Opportunities
    must never see an org's contact details through this surface.
    """
    return {
        "id": org.id,
        "name": org.name,
        "logo_url": org.logo_url,
        "website": org.website,
    }


def _opportunity_publicly_visible_query():
    """
    Base query for opportunities a student is allowed to see: published,
    not yet expired, AND the owning organisation is still verified and
    active. The org re-check matters because an org can be deactivated
    or have its verification revoked AFTER an opportunity was already
    published - this keeps that opportunity from staying visible.
    """
    now = datetime.utcnow()
    return (
        Opportunity.query
        .join(Organisation, Opportunity.organisation_id == Organisation.id)
        .filter(
            Opportunity.status == "published",
            Opportunity.expiry_date > now,
            Organisation.verification_status == "verified",
            Organisation.is_active.is_(True),
        )
    )


def _get_active_promotions_map(opportunity_ids):
    """
    Returns {opportunity_id: promotion_type} for the highest-ranked
    currently-active, APPROVED promotion per opportunity (sponsored >
    featured > standard). Computed in Python against the already-small,
    already-filtered result set - same SQLAlchemy-version-safety
    reasoning as the admin moderation queue's priority sort elsewhere in
    this file, rather than a fragile SQL CASE/join. Read-only: never
    mutates Opportunity itself - OpportunityPromotion stays the single
    source of truth for promotion state, per the MVP spec.
    """
    if not opportunity_ids:
        return {}
    now = datetime.utcnow()
    rows = OpportunityPromotion.query.filter(
        OpportunityPromotion.opportunity_id.in_(opportunity_ids),
        OpportunityPromotion.approval_status == "approved",
        or_(OpportunityPromotion.price == 0, OpportunityPromotion.payment_status == "success"),
        OpportunityPromotion.start_date <= now,
        OpportunityPromotion.end_date >= now,
    ).all()
    best = {}
    for r in rows:
        rank = _PROMOTION_TYPE_RANK.get(r.promotion_type, 99)
        current = best.get(r.opportunity_id)
        if current is None or rank < current[0]:
            best[r.opportunity_id] = (rank, r.promotion_type)
    return {oid: promo_type for oid, (rank, promo_type) in best.items()}


def _serialize_opportunity_public(opp, promotion_type=None, viewer_saved=None):
    org = db.session.get(Organisation, opp.organisation_id)
    result = {
        "id": opp.id,
        "title": opp.title,
        "description": opp.description,
        "opportunity_type": opp.opportunity_type,
        "location": opp.location,
        "is_remote": opp.is_remote,
        "application_url": opp.application_url,
        "application_instructions": opp.application_instructions,
        "application_deadline": opp.application_deadline.isoformat() if opp.application_deadline else None,
        "expiry_date": opp.expiry_date.isoformat() if opp.expiry_date else None,
        "published_at": opp.published_at.isoformat() if opp.published_at else None,
        "view_count": opp.view_count,
        "organisation": _serialize_organisation_public(org) if org else None,
        "promotion_type": promotion_type,
    }
    if viewer_saved is not None:
        result["saved"] = viewer_saved
    return result


@app.route("/opportunities")
def browse_opportunities():
    """
    Browse/search publicly visible opportunities. Login required, same
    convention as /library and /groups (session-gated, not tied to the
    viewer's own year/semester - any student can browse any opportunity).

    Query params (all optional):
      q               - substring match against title
      opportunity_type - job | internship | scholarship | competition |
                          volunteering | event | other
      is_remote       - "true" or "false"
      page            - 1-indexed, 20 per page

    Currently-active promotions (sponsored > featured > standard) sort
    to the top; newest-first within each tier and among unpromoted
    listings.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    query = _opportunity_publicly_visible_query()

    q = (request.args.get("q") or "").strip()
    if q:
        query = query.filter(Opportunity.title.ilike(f"%{q}%"))

    opportunity_type = request.args.get("opportunity_type")
    if opportunity_type:
        if opportunity_type not in OPPORTUNITY_TYPES:
            return jsonify({
                "error": "opportunity_type must be one of: " + ", ".join(OPPORTUNITY_TYPES)
            }), 400
        query = query.filter(Opportunity.opportunity_type == opportunity_type)

    is_remote_param = request.args.get("is_remote")
    if is_remote_param is not None:
        query = query.filter(Opportunity.is_remote.is_(is_remote_param.strip().lower() == "true"))

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = OPPORTUNITY_BROWSE_PAGE_SIZE

    # Promotion-aware ordering needs the full matching set sorted before
    # pagination, so this is done in Python rather than SQL OFFSET/LIMIT -
    # same tradeoff as the admin content-reports priority sort. Volume
    # here is bounded by "currently published, unexpired opportunities",
    # not the whole table, so this stays cheap.
    all_matching = query.order_by(Opportunity.created_at.desc()).all()
    opportunity_ids = [o.id for o in all_matching]
    promo_map = _get_active_promotions_map(opportunity_ids)
    all_matching.sort(key=lambda o: _PROMOTION_TYPE_RANK.get(promo_map.get(o.id), 99))

    page_items = all_matching[(page - 1) * per_page: page * per_page]

    saved_ids = set()
    if page_items:
        saved_rows = SavedOpportunity.query.filter(
            SavedOpportunity.user_id == user_id,
            SavedOpportunity.opportunity_id.in_([o.id for o in page_items]),
        ).all()
        saved_ids = {r.opportunity_id for r in saved_rows}

    return jsonify({
        "page": page,
        "opportunities": [
            _serialize_opportunity_public(
                o, promotion_type=promo_map.get(o.id), viewer_saved=(o.id in saved_ids)
            )
            for o in page_items
        ],
    })


@app.route("/podcast-opportunities")
def podcast_opportunities():
    """Small, low-cost opportunity feed for the podcast player.
    Uses the same verified/published/expiry rules as the main opportunities
    feed, with active paid promotions ranked first. This is placement, not
    a separate opportunity database.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    query = _opportunity_publicly_visible_query()
    all_matching = query.order_by(Opportunity.created_at.desc()).all()
    promo_map = _get_active_promotions_map([o.id for o in all_matching])
    all_matching.sort(key=lambda o: (
        _PROMOTION_TYPE_RANK.get(promo_map.get(o.id), 99),
        -(o.published_at.timestamp() if o.published_at else 0),
    ))

    items = all_matching[:3]
    saved_ids = set()
    if items:
        saved_ids = {
            row.opportunity_id
            for row in SavedOpportunity.query.filter(
                SavedOpportunity.user_id == user_id,
                SavedOpportunity.opportunity_id.in_([o.id for o in items]),
            ).all()
        }

    return jsonify({
        "opportunities": [
            _serialize_opportunity_public(
                o,
                promotion_type=promo_map.get(o.id),
                viewer_saved=o.id in saved_ids,
            )
            for o in items
        ]
    })


@app.route("/opportunities/<int:opportunity_id>")
def get_opportunity_public(opportunity_id):
    """
    Single opportunity detail. 404s (not 403) if the opportunity isn't
    currently publicly visible, hiding existence - same pattern as
    get_group()/get_organisation(). Increments view_count unconditionally
    on every hit, matching the existing LibraryPublication.view_count
    convention elsewhere in this file (a display/analytics counter, not
    a security- or payout-sensitive one, so no per-user cap is needed).
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    opp = _opportunity_publicly_visible_query().filter(Opportunity.id == opportunity_id).first()
    if not opp:
        return jsonify({"error": "Opportunity not found"}), 404

    opp.view_count = (opp.view_count or 0) + 1
    db.session.commit()

    promo_map = _get_active_promotions_map([opp.id])
    saved = SavedOpportunity.query.filter_by(user_id=user_id, opportunity_id=opp.id).first() is not None

    return jsonify(_serialize_opportunity_public(
        opp, promotion_type=promo_map.get(opp.id), viewer_saved=saved
    ))


@app.route("/opportunities/<int:opportunity_id>/save", methods=["POST"])
@require_csrf
def save_opportunity(opportunity_id):
    """
    Bookmarks a publicly visible opportunity. Idempotent from the
    caller's perspective - saving an already-saved item just returns
    success, same pattern as save_library_item(). Only allows saving
    currently-visible opportunities (published/unexpired/org in good
    standing) - same gate as the detail route.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    opp = _opportunity_publicly_visible_query().filter(Opportunity.id == opportunity_id).first()
    if not opp:
        return jsonify({"error": "Opportunity not found"}), 404

    existing = SavedOpportunity.query.filter_by(user_id=user_id, opportunity_id=opportunity_id).first()
    if existing:
        return jsonify({"message": "Already saved"}), 200

    db.session.add(SavedOpportunity(user_id=user_id, opportunity_id=opportunity_id))
    db.session.commit()

    return jsonify({"message": "Saved"}), 201


@app.route("/opportunities/<int:opportunity_id>/save", methods=["DELETE"])
@require_csrf
def unsave_opportunity(opportunity_id):
    """
    Removes a bookmark. Deliberately NOT gated on current visibility -
    a student must always be able to remove their own bookmark, even for
    an opportunity that has since expired/been withdrawn/had its org
    deactivated, same reasoning as unsave_library_item().
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    existing = SavedOpportunity.query.filter_by(user_id=user_id, opportunity_id=opportunity_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()

    return jsonify({"message": "Removed" if existing else "Not saved"})


@app.route("/opportunities/saved")
def list_saved_opportunities():
    """
    Lists the logged-in student's saved opportunities. Skips any saved
    row whose opportunity is no longer publicly visible (expired,
    withdrawn, org deactivated) rather than erroring - same pattern as
    list_saved_library_items().
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    saved_rows = (
        SavedOpportunity.query.filter_by(user_id=user_id)
        .order_by(SavedOpportunity.created_at.desc())
        .all()
    )

    now = datetime.utcnow()
    result = []
    opportunity_ids = [r.opportunity_id for r in saved_rows]
    promo_map = _get_active_promotions_map(opportunity_ids)
    for row in saved_rows:
        opp = db.session.get(Opportunity, row.opportunity_id)
        if not opp or opp.status != "published" or opp.expiry_date <= now:
            continue
        org = db.session.get(Organisation, opp.organisation_id)
        if not org or org.verification_status != "verified" or not org.is_active:
            continue
        result.append(_serialize_opportunity_public(
            opp, promotion_type=promo_map.get(opp.id), viewer_saved=True
        ))

    return jsonify({"saved": result})



# ---------- Opportunity auto-expiry (Step 7) ----------

def sweep_expired_opportunities():
    """
    Flips any Opportunity still marked 'published' whose expiry_date has
    passed into 'expired'. Never trusts a frontend clock for this - per
    the MVP spec, expiry is always computed server-side. Bulk UPDATE (no
    per-row SELECT/commit loop) so this stays cheap even when called on
    every health-check tick. Returns the number of rows updated.

    Deliberately scoped to status='published' only - opportunities still
    stuck in pending_review/approved past their own expiry_date never
    went live, so 'expired' is the wrong terminal state for them; those
    are left for an admin to handle manually via the existing
    reject/remove routes rather than silently auto-expired here.
    """
    now = datetime.utcnow()
    updated = Opportunity.query.filter(
        Opportunity.status == "published",
        Opportunity.expiry_date <= now,
    ).update({"status": "expired"}, synchronize_session=False)
    db.session.commit()
    return updated


def _sweep_expired_opportunities_safe():
    """
    Wraps sweep_expired_opportunities() for use inside /health - a sweep
    failure must NEVER turn /health into a false-negative for the
    GitHub Actions keep-alive ping, whose only job is preventing
    Render's free tier from spinning down and Supabase's free tier from
    auto-pausing. Swallows and logs, never raises or affects the
    response.
    """
    try:
        count = sweep_expired_opportunities()
        if count:
            print(f"INFO: swept {count} expired opportunity(ies) to status='expired'")
    except Exception as e:
        db.session.rollback()
        print(f"WARNING: expired-opportunity sweep failed during health check: {e}")


@app.route("/admin/opportunities/sweep-expired", methods=["POST"])
@require_csrf
@require_admin
def admin_sweep_expired_opportunities():
    """
    Manual trigger for the expiry sweep - lets an admin force it on
    demand (e.g. right after changing an expiry_date, or for testing)
    rather than waiting for the next /health ping, which piggybacks the
    same sweep on roughly a 10-minute cadence via the existing GitHub
    Actions keep-alive workflow.
    """
    count = sweep_expired_opportunities()
    return jsonify({"swept_count": count})



# ---------- Audit Logging ----------
# "Admin changes must be recorded in audit logs." / "Moderation actions
# must be auditable." per the MVP spec's Admin Platform and Moderation
# phases, and "Audit logs work" is a listed acceptance criterion.

class AuditLog(db.Model):
    """
    Records administrative and moderation actions for accountability.
    Append-only by convention - no UPDATE/DELETE route is exposed for
    this table anywhere; a log that can be edited after the fact isn't
    an audit trail.
    """
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    # nullable to leave room for a future system-initiated entry (e.g.
    # an automated sweep) without forcing a fake actor.
    action = db.Column(db.String(60), nullable=False)
    # short verb-based code, e.g. "user_updated", "content_report_dismissed"
    target_type = db.Column(db.String(40), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    # optional JSON-serialized context (best-effort; falls back to str()
    # for anything that isn't directly JSON-serializable)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PushSubscription(db.Model):
    """
    A single browser/device Web Push subscription for a user. One user can
    have multiple rows (multiple devices/browsers) - no uniqueness on
    user_id alone, only on endpoint (a device re-subscribing gets a fresh
    endpoint from the browser, so upsert is keyed on endpoint, not user_id).
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    endpoint = db.Column(db.String(500), unique=True, nullable=False)
    p256dh_key = db.Column(db.String(255), nullable=False)
    auth_key = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class UserKey(db.Model):
    """
    End-to-end encryption key material for a user's Chats identity
    (Chats/Conversation/Message only - Study Groups and Forum are not
    encrypted and never touch this table). public_key is shared with
    other participants so they can wrap a per-conversation symmetric
    key to this user (see ConversationKey, added in a later E2EE
    chunk). encrypted_private_key + kdf_salt are reserved for the
    passphrase-wrapped multi-device backup blob (Chunk 2) - both stay
    NULL until that chunk lands; this chunk only registers the public
    key. The server never has access to the passphrase or the raw
    private key, only this ciphertext blob once Chunk 2 adds it.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    public_key = db.Column(db.Text, nullable=False)
    encrypted_private_key = db.Column(db.Text, nullable=True)
    kdf_salt = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def send_push_notification(user_id, title, body, data=None):
    """
    Sends a Web Push notification to every subscribed device for a user.
    Best-effort: never raises - a push failure must not break the calling
    route (e.g. an admin announcement send). Auto-prunes subscriptions the
    push service reports as gone (404/410 - expired or unsubscribed).
    """
    vapid_private_key = os.environ.get("VAPID_PRIVATE_KEY")
    vapid_claims_email = os.environ.get("VAPID_CLAIMS_EMAIL")
    if not vapid_private_key or not vapid_claims_email:
        print("WARNING: VAPID keys not configured - skipping push send")
        return

    subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh_key, "auth": sub.auth_key},
                },
                data=json.dumps({"title": title, "body": body, "data": data or {}}),
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": vapid_claims_email},
            )
        except WebPushException as e:
            status_code = e.response.status_code if e.response is not None else None
            if status_code in (404, 410):
                db.session.delete(sub)
                db.session.commit()
            else:
                print(f"WARNING: push send failed for user {user_id}: {e}")
        except Exception as e:
            print(f"WARNING: push send failed for user {user_id}: {e}")

def log_admin_action(actor_id, action, target_type=None, target_id=None, details=None):
    """
    Stages one audit log row on the current session. Deliberately does
    NOT call db.session.commit() itself - callers invoke this right
    before their own existing commit, so the audit row lands atomically
    together with the change it's describing, same transaction. If
    details isn't JSON-serializable, falls back to str() rather than
    raising - an audit-logging quirk must never break the admin action
    it's describing.
    """
    payload = None
    if details is not None:
        try:
            payload = json.dumps(details)
        except (TypeError, ValueError):
            payload = str(details)
    db.session.add(AuditLog(
        actor_id=actor_id, action=action, target_type=target_type,
        target_id=target_id, details=payload,
    ))


@app.route("/admin/audit-logs")
@require_admin
def admin_list_audit_logs():
    """
    Lists audit log entries, newest first. Optional filters:
    actor_id (exact match), action (substring match), target_type
    (exact match), days (window, default 30, same convention as
    /admin/ai-usage), page (1-indexed, 50 per page).
    """
    try:
        days = int(request.args.get("days", 30))
    except ValueError:
        days = 30
    days = max(1, min(days, 365))
    window_start = datetime.utcnow() - timedelta(days=days)

    query = AuditLog.query.filter(AuditLog.created_at >= window_start)

    actor_id = request.args.get("actor_id", type=int)
    if actor_id:
        query = query.filter(AuditLog.actor_id == actor_id)

    action_filter = (request.args.get("action") or "").strip()
    if action_filter:
        query = query.filter(AuditLog.action.ilike(f"%{action_filter}%"))

    target_type = (request.args.get("target_type") or "").strip()
    if target_type:
        query = query.filter(AuditLog.target_type == target_type)

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 50

    entries = (
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    result = []
    for e in entries:
        actor = db.session.get(User, e.actor_id) if e.actor_id else None
        parsed_details = None
        if e.details:
            try:
                parsed_details = json.loads(e.details)
            except (TypeError, ValueError):
                parsed_details = e.details
        result.append({
            "id": e.id,
            "actor_id": e.actor_id,
            "actor_email": actor.email if actor else None,
            "action": e.action,
            "target_type": e.target_type,
            "target_id": e.target_id,
            "details": parsed_details,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })

    return jsonify({"page": page, "logs": result})



import chat_interactions

from prepza_control import register_control_routes

register_control_routes(
    app,
    db,
    SystemSetting,
    User,
    Document,
    DocumentContent,
    GeneratedMaterial,
    log_admin_action,
    limiter,
)

from infrastructure_monitoring import register_infrastructure_monitoring

register_infrastructure_monitoring(
    app, db, require_admin, SystemSetting, User, DocumentContent,
    AiUsageLog, Payment, StudyActivityLog, StudyTimeLog,
)

from student_subscription_billing import register_student_subscription_billing

_student_subscription_billing = register_student_subscription_billing(
    app, db, Payment, User, require_csrf, require_admin, paystack_request,
)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)