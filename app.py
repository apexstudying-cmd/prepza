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
    subscription_starts_at = db.Column(db.DateTime, nullable=True)  # subscription entitlement period start
    subscription_expires_at = db.Column(db.DateTime, nullable=True)  # subscription only
    # Immutable feature allowance snapshot for refund/accounting calculations.
    subscription_allowance_snapshot = db.Column(db.JSON, nullable=True)
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


def _start_async_material_generation(document_content_id, user_id, feature, parameters):
    """Create a user-visible job and run the exact requested generation off-request."""
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
    Return the paid subscription period that contains *now*.

    A payment may be paid today but represent a future stacked period (for
    example, buying Pro while an existing Plus period still has 20 days
    remaining). Future paid periods must not grant their plan early.
    """
    now = datetime.utcnow()
    latest = (
        Payment.query
        .filter(
            Payment.user_id == user_id,
            Payment.payment_type == "subscription",
            Payment.status == "success",
            Payment.subscription_starts_at.isnot(None),
            Payment.subscription_expires_at.isnot(None),
            Payment.subscription_starts_at <= now,
            Payment.subscription_expires_at > now,
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
        .order_by(Payment.subscription_starts_at.desc(), Payment.id.desc())
        .first()
    )
    if not latest:
        return {
            "plan": "free", "is_active": False, "expires_at": None,
            "starts_at": None, "cancel_at_period_end": False, "recurring": False,
        }

    recurring = db.session.execute(text("""
        SELECT cancel_at_period_end
        FROM student_subscription
        WHERE user_id=:uid AND plan=:plan
        ORDER BY id DESC LIMIT 1
    """), {"uid": user_id, "plan": latest.plan}).scalar_one_or_none()
    return {
        "plan": latest.plan,
        "is_active": True,
        "starts_at": latest.subscription_starts_at.isoformat(),
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


def compute_new_subscription_period(user_id, plan):
    """
    Return the independent 30-day/calendar-month entitlement period created
    by THIS subscription payment.

    Subscription purchases overlap. Example:
      Plus paid Sep 10 -> Oct 10
      Pro paid Sep 20 -> Oct 20

    Pro therefore becomes the active plan immediately on Sep 20, while the
    original Plus entitlement remains valid until Oct 10. From Sep 20-Oct 10
    both purchased entitlements exist; after Oct 10 only Pro remains.

    This is intentionally NOT Paystack's billing schedule. It is Prepza's
    internal entitlement contract.
    """
    now = datetime.utcnow()
    if plan not in SUBSCRIPTION_PLAN_DURATIONS_MONTHS:
        return now, now
    return now, _add_subscription_month(now)


def compute_new_subscription_expiry(user_id, plan):
    """Compatibility wrapper returning only the new period's end."""
    return compute_new_subscription_period(user_id, plan)[1]


def recompute_subscription_expiries(user_id):
    """
    Rebuild each successful subscription payment as its own independent
    entitlement period. Refunds must not extend or shorten another payment's
    entitlement: overlapping purchases are separate periods.
    """
    remaining = (
        Payment.query.filter(
            Payment.user_id == user_id,
            Payment.payment_type == "subscription",
            Payment.status == "success",
        )
        .order_by(Payment.created_at.asc(), Payment.id.asc())
        .all()
    )

    for p in remaining:
        if p.plan not in SUBSCRIPTION_PLAN_DURATIONS_MONTHS:
            continue
        base = p.created_at or datetime.utcnow()
        p.subscription_starts_at = base
        p.subscription_expires_at = _add_subscription_month(base)


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
                    starts_at, expires_at = compute_new_subscription_period(
                        payment.user_id, payment.plan
                    )
                    payment.subscription_starts_at = starts_at
                    payment.subscription_expires_at = expires_at

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


def _refresh_streak_from_study_time(user_id, today=None):
    """Rebuild the streak from the real 10-minute daily study threshold."""
    today = today or datetime.utcnow().date()
    rows = db.session.query(
        StudyTimeLog.activity_date,
        db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0),
    ).filter(
        StudyTimeLog.user_id == user_id,
        StudyTimeLog.activity_date <= today,
    ).group_by(StudyTimeLog.activity_date).all()

    qualifying_dates = {
        activity_date for activity_date, seconds in rows
        if int(seconds or 0) >= MIN_QUALIFYING_STUDY_SECONDS
    }

    streak = _get_or_create_streak(user_id)
    current = 0
    cursor = today
    while cursor in qualifying_dates:
        current += 1
        cursor -= timedelta(days=1)

    longest = 0
    run = 0
    previous = None
    for activity_date in sorted(qualifying_dates):
        if previous is not None and activity_date == previous + timedelta(days=1):
            run += 1
        else:
            run = 1
        longest = max(longest, run)
        previous = activity_date

    old_current = streak.current_streak
    streak.current_streak = current
    streak.longest_streak = max(streak.longest_streak, longest)
    streak.last_study_date = max(qualifying_dates) if qualifying_dates else None

    # Milestones are awarded only when a newly-qualified streak reaches the
    # milestone. The XP ledger remains idempotent through its unique key.
    if current != old_current:
        milestone_xp = XP_STREAK_MILESTONES.get(current)
        if milestone_xp:
            award_xp(user_id, "streak_milestone", milestone_xp, related_id=current)

    return streak


def record_study_activity(user_id, document_content_id=None):
    """
    Records document activity only after the student has accumulated the
    minimum 10 active study minutes today. Generation/completion alone can
    never create a streak day.
    """
    today = datetime.utcnow().date()
    total_seconds = db.session.query(
        db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0)
    ).filter(
        StudyTimeLog.user_id == user_id,
        StudyTimeLog.activity_date == today,
    ).scalar() or 0
    if int(total_seconds) < MIN_QUALIFYING_STUDY_SECONDS:
        _refresh_streak_from_study_time(user_id, today)
        return False

    log_row = StudyActivityLog(
        user_id=user_id,
        document_content_id=document_content_id,
        activity_date=today,
    )
    db.session.add(log_row)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return False

    _refresh_streak_from_study_time(user_id, today)
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
MIN_QUALIFYING_STUDY_SECONDS = 10 * 60  # 10 cumulative active minutes/day


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
    streak = _refresh_streak_from_study_time(user_id)
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

    today = datetime.utcnow().date()
    streak = _refresh_streak_from_study_time(user_id, today)
    db.session.commit()

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
    # A study day requires 10 cumulative active minutes across all study
    # features. Opening a document or completing a generation is not enough.
    feature_session_seconds = after_feature_seconds
    today = datetime.utcnow().date()
    total_today = int(db.session.query(
        db.func.coalesce(db.func.sum(StudyTimeLog.study_time_seconds), 0)
    ).filter(
        StudyTimeLog.user_id == user_id,
        StudyTimeLog.activity_date == today,
    ).scalar() or 0)
    study_day_active = total_today >= MIN_QUALIFYING_STUDY_SECONDS

    if credited_this_heartbeat > 0 and document_content_id is not None and study_day_active:
        existing = StudyActivityLog.query.filter_by(
            user_id=user_id, document_content_id=document_content_id, activity_date=today,
        ).first()
        if existing is None:
            record_study_activity(user_id, document_content_id=document_content_id)
    else:
        # Also clears a stale streak immediately after a missed day once the
        # student next interacts with the study-time system.
        _refresh_streak_from_study_time(user_id, today)

    db.session.commit()
    return jsonify({
        "study_time_seconds_today": total_today,
        "credited_this_heartbeat": credited_this_heartbeat,
        "qualifying_study_seconds": MIN_QUALIFYING_STUDY_SECONDS,
        "study_day_active": study_day_active,
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