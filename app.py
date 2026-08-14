import os
import re
import base64
import secrets
import hmac
import requests
import sentry_sdk
import fitz  # PyMuPDF - used to rasterize + watermark view-only Q&A pages
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, session, Response, send_from_directory, redirect
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import ai_service
import document_pipeline

load_dotenv()

sentry_dsn = os.environ.get("SENTRY_DSN")
anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=0,  # Error monitoring only, no performance tracing
        send_default_pii=False,  # Skip sending user IPs/headers by default
    )

app = Flask(__name__)
limiter = Limiter(get_remote_address, app=app, default_limits=[])
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

db = SQLAlchemy(app)

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
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
    if request.path.startswith(("/static/images/", "/static/css/", "/static/js/")):
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
    email_verified = db.Column(db.Boolean, default=False)
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
    phone_number = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    checkout_request_id = db.Column(db.String(100), unique=True, nullable=True)
    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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
    __table_args__ = (
        db.UniqueConstraint("document_content_id", "material_type", name="uq_material_content_type"),
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
    feature = db.Column(db.String(30), nullable=False)
    # text_extraction | summary | quiz | flashcards | podcast | mind_map
    status = db.Column(db.String(20), nullable=False, default="pending")
    # pending -> processing -> completed | failed
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.String(500), nullable=True)
    retry_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    batch_id = db.Column(db.String(100), nullable=True)
    # Anthropic Message Batch id, when this job's AI call(s) went through
    # the Batch API instead of a synchronous call - lets an admin look up
    # the batch directly in the Anthropic Console if a job seems stuck.


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


class ForumPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey("unit.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
class AiAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey("unit.id"), nullable=True)
    question_text = db.Column(db.Text, nullable=False)
    answer_text = db.Column(db.Text, nullable=False)
    model_used = db.Column(db.String(50), nullable=True)
    input_tokens = db.Column(db.Integer, default=0)
    output_tokens = db.Column(db.Integer, default=0)
    cache_read_tokens = db.Column(db.Integer, default=0)
    cache_creation_tokens = db.Column(db.Integer, default=0)
    cost_usd = db.Column(db.Numeric(10, 6), default=0)
    reuse_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
class ForumReply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("forum_post.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    is_ai = db.Column(db.Boolean, default=False)
    ai_answer_id = db.Column(db.Integer, db.ForeignKey("ai_answer.id"), nullable=True)
    triggered_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
class AiUsageLog(db.Model):
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
    __table_args__ = (
        db.UniqueConstraint("conversation_id", "user_id", name="uq_participant_conversation_user"),
    )


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.String(3000), nullable=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    edited_at = db.Column(db.DateTime, nullable=True)


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


class GroupPostComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_post_id = db.Column(db.Integer, db.ForeignKey("group_post.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Used for both Posts-tab comments and Questions-tab replies - the
    # frontend's shared CommentsScreen doesn't distinguish them either.


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


def get_mpesa_access_token():
    consumer_key = os.environ.get("MPESA_CONSUMER_KEY")
    consumer_secret = os.environ.get("MPESA_CONSUMER_SECRET")
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(url, auth=(consumer_key, consumer_secret))
    response.raise_for_status()
    return response.json()["access_token"]


def generate_stk_password():
    shortcode = os.environ.get("MPESA_SHORTCODE")
    passkey = os.environ.get("MPESA_PASSKEY")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    raw = shortcode + passkey + timestamp
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp


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
    reset_link = f"{BASE_URL}/static/reset-password.html?token={token}"

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


def has_access(user_id, content_item):
    if get_price_for_type(content_item.content_type) == 0:
        return True

    successful_payment = Payment.query.filter_by(
        user_id=user_id,
        content_item_id=content_item.id,
        status="success",
    ).first()

    return successful_payment is not None


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
    "/units",
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


@app.route("/")
def home():
    return send_from_directory(app.static_folder, "landing.html")


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

    if year is not None:
        if not isinstance(year, int) or year < 1 or year > 4:
            return jsonify({"error": "Year must be a number between 1 and 4"}), 400

    if semester is not None:
        if not isinstance(semester, int) or semester not in (1, 2):
            return jsonify({"error": "Semester must be 1 or 2"}), 400

    if not university_id or not isinstance(university_id, int):
        return jsonify({"error": "University is required"}), 400
    university = University.query.filter_by(id=university_id, is_active=True).first()
    if not university:
        return jsonify({"error": "Selected university was not found"}), 400

    if program_id is not None:
        if not isinstance(program_id, int):
            return jsonify({"error": "Invalid program"}), 400
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
    static/verify-confirm.html.
    """
    return send_from_directory(app.static_folder, "verify-confirm.html")


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
    db.session.commit()

    # Auto-login: set the session the same way /login does, so the user
    # lands straight in the dashboard instead of having to log in again.
    session.permanent = True
    session["user_id"] = user.id

    return jsonify({
        "message": "Email verified successfully",
        "redirect": "/static/dashboard.html?verified=1",
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

    if not user.email_verified:
        return jsonify({"error": "Please verify your email before logging in"}), 403

    if user.is_suspended:
        return jsonify({"error": "This account has been suspended"}), 403

    session.permanent = True
    session["user_id"] = user.id
    return jsonify({"message": "Logged in successfully", "user_id": user.id})


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
        "email_verified": user.email_verified,
        "is_admin": user.is_admin,
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
    if display_name is not None:
        display_name = display_name.strip()
        if len(display_name) > 50:
            return jsonify({"error": "Display name must be 50 characters or fewer"}), 400
    if bio is not None:
        bio = bio.strip()
        if len(bio) > 160:
            return jsonify({"error": "Bio must be 160 characters or fewer"}), 400

    user = db.session.get(User, user_id)
    user.year = year
    user.semester = semester
    if display_name is not None:
        user.display_name = display_name or None
    if bio is not None:
        user.bio = bio or None
    db.session.commit()

    return jsonify({
        "message": "Profile updated",
        "year": user.year,
        "semester": user.semester,
        "display_name": user.display_name,
        "bio": user.bio,
    })


@app.route("/payment-history")
def payment_history():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    payments = (
        Payment.query.filter_by(user_id=user_id)
        .order_by(Payment.created_at.desc())
        .all()
    )

    result = []
    for p in payments:
        content_item = db.session.get(ContentItem, p.content_item_id)
        result.append({
            "id": p.id,
            "content_title": content_item.title if content_item else None,
            "amount": p.amount,
            "status": p.status,
            "checkout_request_id": p.checkout_request_id,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    return jsonify({"payments": result})


# ---------- Document routes (student uploads) ----------

ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "jpg", "jpeg", "png"}
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
    if not document or document.user_id != user_id or document.is_removed:
        return jsonify({"error": "Document not found"}), 404

    content = db.session.get(DocumentContent, document.document_content_id) if document.document_content_id else None

    # Once past "uploading", status tracks the shared DocumentContent live -
    # document_pipeline.py updates content.status in the background, not
    # this row.
    effective_status = content.status if (content and document.status != "uploading") else document.status

    view_url = None
    if content and content.status == "ready":
        view_url = get_signed_url(content.storage_path, bucket="documents")

    materials = []
    if content:
        materials = [
            {"type": m.material_type, "status": m.status}
            for m in GeneratedMaterial.query.filter_by(document_content_id=content.id).all()
        ]

    return jsonify({
        "id": document.id,
        "title": document.title,
        "original_filename": document.original_filename,
        "status": effective_status,
        "file_type": content.file_type if content else None,
        "file_size_bytes": content.file_size_bytes if content else None,
        "page_count": content.page_count if content else None,
        "error_message": content.error_message if (content and effective_status == "failed") else None,
        "view_url": view_url,
        "materials": materials,
        "created_at": document.created_at.isoformat() if document.created_at else None,
    })


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
    if not document or document.user_id != user_id or document.is_removed:
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


@app.route("/documents/<int:document_id>/summarize", methods=["POST"])
@limiter.limit(
    "20 per hour",
    key_func=lambda: f"summarize:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def summarize_document(document_id):
    """
    Generates (or returns the cached) AI summary for a student's
    document. Mirrors /forum/posts/<id>/ask-ai's error-handling shape -
    ai_service enforces the spend cap / rate limit / cache-reuse logic,
    this route just translates its exceptions to HTTP responses.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    document = db.session.get(Document, document_id)
    if not document or document.user_id != user_id or document.is_removed:
        return jsonify({"error": "Document not found"}), 404

    if not document.document_content_id:
        return jsonify({"error": "Document has no content to summarize"}), 400

    content = db.session.get(DocumentContent, document.document_content_id)
    if not content or content.status != "ready":
        return jsonify({"error": "Document is still processing - try again shortly"}), 400

    try:
        result = ai_service.generate_document_summary(
            document_content_id=content.id,
            triggering_user_id=user_id,
        )
    except ai_service.AIBudgetExceededError as e:
        return jsonify({"error": str(e)}), 503
    except ai_service.AIRateLimitExceededError as e:
        return jsonify({"error": str(e)}), 429
    except ai_service.AIProviderError as e:
        return jsonify({"error": str(e)}), 502

    return jsonify({
        "material_id": result["material_id"],
        "reused": result["reused"],
        "summary": result["payload"],
    }), 200


@app.route("/documents/<int:document_id>/quiz", methods=["POST"])
@limiter.limit(
    "20 per hour",
    key_func=lambda: f"quiz:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def quiz_document(document_id):
    """
    Generates (or returns the cached) AI practice quiz for a student's
    document. Same shape as summarize_document() above - ai_service
    enforces the spend cap / rate limit / cache-reuse logic, this route
    just translates its exceptions to HTTP responses.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    document = db.session.get(Document, document_id)
    if not document or document.user_id != user_id or document.is_removed:
        return jsonify({"error": "Document not found"}), 404

    if not document.document_content_id:
        return jsonify({"error": "Document has no content to quiz"}), 400

    content = db.session.get(DocumentContent, document.document_content_id)
    if not content or content.status != "ready":
        return jsonify({"error": "Document is still processing - try again shortly"}), 400

    try:
        result = ai_service.generate_document_quiz(
            document_content_id=content.id,
            triggering_user_id=user_id,
        )
    except ai_service.AIBudgetExceededError as e:
        return jsonify({"error": str(e)}), 503
    except ai_service.AIRateLimitExceededError as e:
        return jsonify({"error": str(e)}), 429
    except ai_service.AIProviderError as e:
        return jsonify({"error": str(e)}), 502

    return jsonify({
        "material_id": result["material_id"],
        "reused": result["reused"],
        "quiz": result["payload"],
    }), 200


@app.route("/documents/<int:document_id>/flashcards", methods=["POST"])
@limiter.limit(
    "20 per hour",
    key_func=lambda: f"flashcards:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def flashcards_document(document_id):
    """
    Generates (or returns the cached) AI flashcard set for a student's
    document. Same shape as quiz_document()/summarize_document() above
    - ai_service enforces the spend cap / rate limit / cache-reuse
    logic, this route just translates its exceptions to HTTP
    responses.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    document = db.session.get(Document, document_id)
    if not document or document.user_id != user_id or document.is_removed:
        return jsonify({"error": "Document not found"}), 404

    if not document.document_content_id:
        return jsonify({"error": "Document has no content to generate flashcards from"}), 400

    content = db.session.get(DocumentContent, document.document_content_id)
    if not content or content.status != "ready":
        return jsonify({"error": "Document is still processing - try again shortly"}), 400

    try:
        result = ai_service.generate_document_flashcards(
            document_content_id=content.id,
            triggering_user_id=user_id,
        )
    except ai_service.AIBudgetExceededError as e:
        return jsonify({"error": str(e)}), 503
    except ai_service.AIRateLimitExceededError as e:
        return jsonify({"error": str(e)}), 429
    except ai_service.AIProviderError as e:
        return jsonify({"error": str(e)}), 502

    return jsonify({
        "material_id": result["material_id"],
        "reused": result["reused"],
        "flashcards": result["payload"],
    }), 200


@app.route("/documents/<int:document_id>/podcast-script", methods=["POST"])
@limiter.limit(
    "20 per hour",
    key_func=lambda: f"podcast-script:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def podcast_script_document(document_id):
    """
    Generates (or returns the cached) AI podcast SCRIPT for a student's
    document - Phase 1 only, text only, no audio yet (audio synthesis
    is a separate follow-up route once a TTS provider is wired up).
    Same shape as flashcards_document()/quiz_document()/
    summarize_document() above - ai_service enforces the spend cap /
    rate limit / cache-reuse logic, this route just translates its
    exceptions to HTTP responses.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    document = db.session.get(Document, document_id)
    if not document or document.user_id != user_id or document.is_removed:
        return jsonify({"error": "Document not found"}), 404

    if not document.document_content_id:
        return jsonify({"error": "Document has no content to generate a podcast from"}), 400

    content = db.session.get(DocumentContent, document.document_content_id)
    if not content or content.status != "ready":
        return jsonify({"error": "Document is still processing - try again shortly"}), 400

    try:
        result = ai_service.generate_document_podcast_script(
            document_content_id=content.id,
            triggering_user_id=user_id,
        )
    except ai_service.AIBudgetExceededError as e:
        return jsonify({"error": str(e)}), 503
    except ai_service.AIRateLimitExceededError as e:
        return jsonify({"error": str(e)}), 429
    except ai_service.AIProviderError as e:
        return jsonify({"error": str(e)}), 502

    return jsonify({
        "material_id": result["material_id"],
        "reused": result["reused"],
        "podcast": result["payload"],
    }), 200







# ---------- Library (publishing) ----------

LIBRARY_MATERIAL_TYPES = {"lecture_notes", "past_paper", "summary", "other"}
LIBRARY_TITLE_MAX = 200
LIBRARY_DESCRIPTION_MAX = 1000
LIBRARY_ACTIVE_STATUSES = ("pending", "approved")


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
    if not document or document.user_id != user_id or document.is_removed:
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

    existing_active = LibraryPublication.query.filter(
        LibraryPublication.document_id == document_id,
        LibraryPublication.status.in_(LIBRARY_ACTIVE_STATUSES),
    ).first()
    if existing_active:
        return jsonify({
            "error": f"This document already has an active library submission (status: {existing_active.status})"
        }), 409

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

    publications = (
        query.order_by(LibraryPublication.created_at.desc())
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


@app.route("/library/<int:publication_id>/save", methods=["POST"])
@require_csrf
def save_library_item(publication_id):
    """
    Bookmarks an approved Library publication for the logged-in student.
    Idempotent from the caller's perspective: saving an already-saved
    item just returns success rather than erroring, since the frontend
    doesn't need to track whether this is the first save.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    publication = db.session.get(LibraryPublication, publication_id)
    if not publication or publication.status != "approved":
        return jsonify({"error": "Library item not found"}), 404

    existing = SavedLibraryMaterial.query.filter_by(
        user_id=user_id, library_publication_id=publication_id
    ).first()
    if existing:
        return jsonify({"message": "Already saved"}), 200

    saved = SavedLibraryMaterial(user_id=user_id, library_publication_id=publication_id)
    db.session.add(saved)
    publication.save_count = (publication.save_count or 0) + 1
    db.session.commit()

    return jsonify({"message": "Saved", "save_count": publication.save_count}), 201


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

    result = []
    for saved in saved_rows:
        pub = db.session.get(LibraryPublication, saved.library_publication_id)
        if not pub or pub.status != "approved":
            # Publication was later rejected/removed - skip rather than
            # error, so one bad row doesn't break the whole Saved tab.
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

    db.session.commit()

    return jsonify({
        "id": publication.id,
        "status": publication.status,
        "xp_awarded_now": xp_awarded_now,
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
        if not isinstance(year, int) or year < 1 or year > 4:
            return jsonify({"error": "year must be a number between 1 and 4"}), 400

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

    query = Group.query.filter(Group.privacy != "private")

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
        "body": post.body,
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
        "body": comment.body,
        "author": _display_name(author) if author else "Deleted user",
        "author_id": comment.user_id,
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
        GroupPost.query.filter_by(group_id=group_id, post_type=post_type)
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
    db.session.commit()

    return jsonify(_serialize_group_post_comment(comment)), 201


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

    target.role = role
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
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if target_user_id == user_id:
        return jsonify({"error": "You can't follow yourself"}), 400

    target = db.session.get(User, target_user_id)
    if not target or target.is_suspended:
        return jsonify({"error": "User not found"}), 404

    existing = Follow.query.filter_by(follower_id=user_id, followed_id=target_user_id).first()
    if not existing:
        db.session.add(Follow(follower_id=user_id, followed_id=target_user_id))
        follower = db.session.get(User, user_id)
        db.session.add(Notification(
            user_id=target_user_id,
            type="new_follower",
            title="New follower",
            body=f"{_display_name(follower)} started following you",
            related_type="user",
            related_id=user_id,
        ))
        db.session.commit()

    return jsonify({
        "message": "Already following" if existing else "Followed",
        "followers_count": Follow.query.filter_by(followed_id=target_user_id).count(),
    }), (200 if existing else 201)


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


# ---------- Content routes (student-facing) ----------

@app.route("/units")
def list_units():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    user = db.session.get(User, user_id)
    units = Unit.query.filter_by(year=user.year, semester=user.semester).all()

    return jsonify([
        {"id": u.id, "code": u.code, "name": u.name}
        for u in units
    ])


@app.route("/units/<int:unit_id>/content")
def unit_content(unit_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    unit = db.session.get(Unit, unit_id)
    if not unit:
        return jsonify({"error": "Unit not found"}), 404

    items = ContentItem.query.filter_by(unit_id=unit_id).all()

    grouped = {"past_paper": [], "notes": [], "qna": []}
    for item in items:
        unlocked = has_access(user_id, item)
        grouped[item.content_type].append({
            "id": item.id,
            "title": item.title,
            "paper_year": item.paper_year,
            "price": get_price_for_type(item.content_type),
            "unlocked": unlocked,
            "file_url": get_signed_url(item.file_url) if (unlocked and item.is_downloadable) else None,
        })

    return jsonify({"unit": unit.code, "content": grouped})


# ---------- Forum + Prepza AI ----------

AI_MENTION_RE = re.compile(r"@prepza\s*ai", re.IGNORECASE)
FORUM_TITLE_MAX = 200
FORUM_BODY_MAX = 5000
FORUM_REPLY_MAX = 3000


def _display_name(user):
    """Forum identity is username-based, not full real-name reveal.
    display_name is optional on signup, so fall back to a stable
    per-account label rather than ever exposing email."""
    return user.display_name or f"Student{user.id}"


def _serialize_reply(reply):
    author = None
    if not reply.is_ai and reply.user_id:
        author_user = db.session.get(User, reply.user_id)
        author = _display_name(author_user) if author_user else "Deleted user"

    return {
        "id": reply.id,
        "body": reply.body,
        "is_ai": reply.is_ai,
        "author": "Prepza AI" if reply.is_ai else author,
        "ai_answer_id": reply.ai_answer_id,
        "created_at": reply.created_at.isoformat() if reply.created_at else None,
    }


def _trigger_ai_reply(post, question_text, triggering_user_id):
    """
    Shared by both the @Prepza AI mention path and the dedicated button.
    Returns (forum_reply_or_None, error_response_or_None). On any
    ai_service error, the human reply/post that triggered this should
    still have already been committed by the caller - AI failure must
    never lose a student's own post/reply.
    """
    unit = db.session.get(Unit, post.unit_id) if post.unit_id else None

    try:
        result = ai_service.answer_forum_question(
            question_text=question_text,
            unit=unit,
            triggering_user_id=triggering_user_id,
        )
    except ai_service.AIBudgetExceededError as e:
        return None, (jsonify({"error": str(e)}), 503)
    except ai_service.AIRateLimitExceededError as e:
        return None, (jsonify({"error": str(e)}), 429)
    except ai_service.AIProviderError:
        return None, (jsonify({
            "error": "Prepza AI is temporarily unavailable - please try again shortly."
        }), 502)

    ai_reply = ForumReply(
        post_id=post.id,
        user_id=None,
        is_ai=True,
        ai_answer_id=result["ai_answer_id"],
        triggered_by_user_id=triggering_user_id,
        body=result["answer_text"],
    )
    db.session.add(ai_reply)
    db.session.commit()
    return ai_reply, None


@app.route("/units/<int:unit_id>/forum")
def list_forum_posts(unit_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    unit = db.session.get(Unit, unit_id)
    if not unit:
        return jsonify({"error": "Unit not found"}), 404

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 20

    posts = (
        ForumPost.query.filter_by(unit_id=unit_id)
        .order_by(ForumPost.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    result = []
    for post in posts:
        author = db.session.get(User, post.user_id)
        reply_count = ForumReply.query.filter_by(post_id=post.id).count()
        result.append({
            "id": post.id,
            "title": post.title,
            "body": post.body,
            "author": _display_name(author) if author else "Deleted user",
            "reply_count": reply_count,
            "created_at": post.created_at.isoformat() if post.created_at else None,
        })

    return jsonify({"unit": unit.code, "page": page, "posts": result})


@app.route("/forum/posts", methods=["POST"])
@require_csrf
def create_forum_post():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    unit_id = data.get("unit_id")
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()

    if not unit_id or not db.session.get(Unit, unit_id):
        return jsonify({"error": "Valid unit_id is required"}), 400
    if not title or len(title) > FORUM_TITLE_MAX:
        return jsonify({"error": f"Title is required and must be {FORUM_TITLE_MAX} characters or fewer"}), 400
    if not body or len(body) > FORUM_BODY_MAX:
        return jsonify({"error": f"Body is required and must be {FORUM_BODY_MAX} characters or fewer"}), 400

    post = ForumPost(unit_id=unit_id, user_id=user_id, title=title, body=body)
    db.session.add(post)
    db.session.commit()

    return jsonify({
        "id": post.id,
        "title": post.title,
        "body": post.body,
        "unit_id": post.unit_id,
        "created_at": post.created_at.isoformat() if post.created_at else None,
    }), 201


@app.route("/forum/posts/<int:post_id>")
def get_forum_post(post_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    post = db.session.get(ForumPost, post_id)
    if not post:
        return jsonify({"error": "Post not found"}), 404

    author = db.session.get(User, post.user_id)
    replies = (
        ForumReply.query.filter_by(post_id=post_id)
        .order_by(ForumReply.created_at.asc())
        .all()
    )

    return jsonify({
        "id": post.id,
        "title": post.title,
        "body": post.body,
        "author": _display_name(author) if author else "Deleted user",
        "unit_id": post.unit_id,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "replies": [_serialize_reply(r) for r in replies],
    })


@app.route("/forum/posts/<int:post_id>/replies", methods=["POST"])
@require_csrf
def create_forum_reply(post_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    post = db.session.get(ForumPost, post_id)
    if not post:
        return jsonify({"error": "Post not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    body = (data.get("body") or "").strip()
    if not body or len(body) > FORUM_REPLY_MAX:
        return jsonify({"error": f"Body is required and must be {FORUM_REPLY_MAX} characters or fewer"}), 400

    reply = ForumReply(post_id=post_id, user_id=user_id, is_ai=False, body=body)
    db.session.add(reply)
    db.session.commit()

    response = {"reply": _serialize_reply(reply)}

    if AI_MENTION_RE.search(body):
        ai_reply, error = _trigger_ai_reply(post, question_text=body, triggering_user_id=user_id)
        if ai_reply:
            response["ai_reply"] = _serialize_reply(ai_reply)
        elif error:
            body_json, status = error
            response["ai_error"] = body_json.get_json()["error"]

    return jsonify(response), 201


@app.route("/forum/posts/<int:post_id>/ask-ai", methods=["POST"])
@limiter.limit(
    "20 per hour",
    key_func=lambda: f"ask-ai:{session.get('user_id', get_remote_address())}",
)
@require_csrf
def ask_prepza_ai(post_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    post = db.session.get(ForumPost, post_id)
    if not post:
        return jsonify({"error": "Post not found"}), 404

    question_text = f"{post.title}\n\n{post.body}"
    ai_reply, error = _trigger_ai_reply(post, question_text=question_text, triggering_user_id=user_id)
    if error:
        return error

    return jsonify({"reply": _serialize_reply(ai_reply)}), 201


@app.route("/library/my-purchases")
def my_library():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    payments = Payment.query.filter_by(user_id=user_id, status="success").all()
    unlocked_at = {}
    for p in payments:
        existing = unlocked_at.get(p.content_item_id)
        if existing is None or (p.created_at and p.created_at > existing):
            unlocked_at[p.content_item_id] = p.created_at

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
            "file_url": get_signed_url(item.file_url) if item.is_downloadable else None,
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

    pdf_bytes = fetch_private_file_bytes(content_item.file_url)
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

    pdf_bytes = fetch_private_file_bytes(content_item.file_url)
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
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    content_item = db.session.get(ContentItem, content_id)
    if not content_item:
        return jsonify({"error": "Content not found"}), 404

    price = get_price_for_type(content_item.content_type)
    if price == 0:
        return jsonify({"error": "This content is free, no payment needed"}), 400

    if has_access(user_id, content_item):
        return jsonify({"message": "You already have access to this content"}), 200

    data = request.get_json(silent=True) or {}
    phone_number = data.get("phone_number")
    if not phone_number:
        return jsonify({"error": "phone_number is required"}), 400

    try:
        access_token = get_mpesa_access_token()
        password, timestamp = generate_stk_password()

        url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {
            "BusinessShortCode": os.environ.get("MPESA_SHORTCODE"),
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": price,
            "PartyA": phone_number,
            "PartyB": os.environ.get("MPESA_SHORTCODE"),
            "PhoneNumber": phone_number,
            "CallBackURL": f"{os.environ.get('MPESA_CALLBACK_URL', '').strip()}/{os.environ.get('MPESA_CALLBACK_SECRET', '').strip()}",
            "AccountReference": "Prepza",
            "TransactionDesc": f"Prepza - {content_item.title}",
        }

        response = requests.post(url, json=payload, headers=headers)
        response_data = response.json()

        if "CheckoutRequestID" in response_data:
            payment = Payment(
                user_id=user_id,
                content_item_id=content_id,
                phone_number=phone_number,
                amount=price,
                checkout_request_id=response_data["CheckoutRequestID"],
                status="pending",
            )
            db.session.add(payment)
            db.session.commit()

        return jsonify(response_data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/mpesa/callback/<callback_token>", methods=["POST"])
def mpesa_callback(callback_token):
    expected_token = os.environ.get("MPESA_CALLBACK_SECRET", "").strip()
    if not expected_token or not hmac.compare_digest(callback_token, expected_token):
        # Don't reveal *why* it failed - just look like a normal 404 to anyone probing the URL
        return jsonify({"error": "Not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ResultCode": 1, "ResultDesc": "Invalid payload"}), 400

    try:
        stk_callback = data["Body"]["stkCallback"]
        checkout_request_id = stk_callback["CheckoutRequestID"]
        result_code = stk_callback["ResultCode"]

        payment = Payment.query.filter_by(
            checkout_request_id=checkout_request_id
        ).first()

        if payment and payment.status == "pending":
            if result_code == 0:
                callback_amount = next(
                    (item.get("Value") for item in
                     stk_callback.get("CallbackMetadata", {}).get("Item", [])
                     if item.get("Name") == "Amount"),
                    None,
                )
                if callback_amount is not None and int(callback_amount) != payment.amount:
                    # Amount mismatch - do NOT grant access, flag for manual review
                    print(f"MPESA amount mismatch on payment {payment.id}: "
                          f"expected {payment.amount}, callback said {callback_amount}")
                    payment.status = "failed"
                else:
                    payment.status = "success"
            else:
                payment.status = "failed"
            db.session.commit()

    except Exception as e:
        print("Callback processing error:", str(e))

    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})


# ---------- Chat routes (Chunk 6) ----------

CHAT_MESSAGE_MAX = 3000
CHAT_GROUP_NAME_MAX = 100
CHAT_MESSAGE_PAGE_SIZE = 50


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


def _serialize_message(message):
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_id": message.sender_id,
        "body": message.body if not message.is_deleted else None,
        "is_deleted": message.is_deleted,
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "edited_at": message.edited_at.isoformat() if message.edited_at else None,
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

        result.append({
            "id": conversation.id,
            "is_group": conversation.is_group,
            "name": _conversation_display_name(conversation, user_id),
            "last_message": last_message.body if last_message else None,
            "last_message_at": last_message.created_at.isoformat() if last_message else None,
            "unread_count": unread_count,
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

    conversation = Conversation(
        is_group=is_group,
        name=name if is_group else None,
        created_by=user_id,
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
    return jsonify({"id": conversation.id, "reused": False}), 201


@app.route("/chats/<int:conversation_id>/messages")
def list_messages(conversation_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if not _active_participant(conversation_id, user_id):
        return jsonify({"error": "Conversation not found"}), 404

    before_id = request.args.get("before_id", type=int)
    query = Message.query.filter_by(conversation_id=conversation_id)
    if before_id:
        query = query.filter(Message.id < before_id)

    messages = (
        query.order_by(Message.created_at.desc())
        .limit(CHAT_MESSAGE_PAGE_SIZE)
        .all()
    )
    messages.reverse()  # oldest-first for the client's scroll-down feed

    return jsonify({"messages": [_serialize_message(m) for m in messages]})


@app.route("/chats/<int:conversation_id>/messages", methods=["POST"])
@limiter.limit("120 per hour")
@require_csrf
def send_message(conversation_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    if not _active_participant(conversation_id, user_id):
        return jsonify({"error": "Conversation not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    body = (data.get("body") or "").strip()
    if not body or len(body) > CHAT_MESSAGE_MAX:
        return jsonify({"error": f"Message must be 1-{CHAT_MESSAGE_MAX} characters"}), 400

    message = Message(conversation_id=conversation_id, sender_id=user_id, body=body)
    db.session.add(message)

    conversation = db.session.get(Conversation, conversation_id)
    if conversation:
        conversation.updated_at = datetime.utcnow()

    db.session.commit()
    return jsonify(_serialize_message(message)), 201


@app.route("/chats/<int:conversation_id>/read", methods=["POST"])
@require_csrf
def mark_chat_read(conversation_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    participant = _active_participant(conversation_id, user_id)
    if not participant:
        return jsonify({"error": "Conversation not found"}), 404

    participant.last_read_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Marked as read"})


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
    db.session.commit()
    return jsonify({"message": "Left group"})


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


@app.route("/admin/units", methods=["POST"])
@require_csrf
@require_admin
def admin_add_unit():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    code = data.get("code")
    name = data.get("name")
    year = data.get("year")
    semester = data.get("semester")

    if not code or not name or year is None or semester is None:
        return jsonify({"error": "code, name, year, and semester are all required"}), 400

    unit = Unit(code=code, name=name, year=year, semester=semester)
    db.session.add(unit)
    db.session.commit()

    return jsonify({"message": "Unit added", "unit_id": unit.id}), 201


@app.route("/admin/units", methods=["GET"])
@require_admin
def admin_list_units():
    units = Unit.query.all()
    return jsonify([
        {"id": u.id, "code": u.code, "name": u.name, "year": u.year, "semester": u.semester}
        for u in units
    ])


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
        content_item = db.session.get(ContentItem, p.content_item_id)
        result.append({
            "id": p.id,
            "user_id": p.user_id,
            "content_title": content_item.title if content_item else None,
            "phone_number": p.phone_number,
            "amount": p.amount,
            "status": p.status,
            "checkout_request_id": p.checkout_request_id,
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

    top_content_raw = (
        db.session.query(
            ContentItem.id,
            ContentItem.title,
            ContentItem.content_type,
            func.coalesce(func.sum(Payment.amount), 0).label("revenue"),
            func.count(Payment.id).label("purchases"),
        )
        .join(Payment, Payment.content_item_id == ContentItem.id)
        .filter(Payment.status == "success")
        .group_by(ContentItem.id, ContentItem.title, ContentItem.content_type)
        .order_by(func.coalesce(func.sum(Payment.amount), 0).desc())
        .limit(10)
        .all()
    )
    top_performing_content = [
        {
            "id": cid,
            "title": title,
            "content_type": content_type,
            "revenue": revenue,
            "purchases": purchases,
        }
        for cid, title, content_type, revenue, purchases in top_content_raw
    ]

    return jsonify({
        "total_revenue": total_revenue,
        "revenue_last_30d": revenue_30d,
        "total_users": total_users,
        "total_units": total_units,
        "total_content_items": total_content,
        "content_by_type": content_by_type,
        "payments_by_status": payments_by_status,
        "signups_per_day": signups_per_day,
        "revenue_per_day": revenue_per_day,
        "top_performing_content": top_performing_content,
    })


@app.route("/admin/payments/<int:payment_id>/refund", methods=["POST"])
@require_csrf
@require_admin
def admin_refund_payment(payment_id):
    payment = db.session.get(Payment, payment_id)
    if not payment:
        return jsonify({"error": "Payment not found"}), 404

    if payment.status != "success":
        return jsonify({
            "error": f"Only successful payments can be refunded (current status: {payment.status})"
        }), 400

    payment.status = "refunded"
    db.session.commit()

    return jsonify({
        "message": "Payment marked as refunded. Access to this content has been revoked.",
        "payment_id": payment.id,
        "note": "This only updates records in Prepza. You must still send the actual M-Pesa refund manually.",
    })


# ---------- Admin: user management ----------

@app.route("/admin/users")
@require_admin
def admin_list_users():
    """
    Lists users for the admin dashboard, optionally filtered by an
    email substring. Newest signups first; users with no created_at
    (pre-migration accounts) sort last rather than first.
    """
    search = (request.args.get("search") or "").strip().lower()

    query = User.query
    if search:
        query = query.filter(User.email.ilike(f"%{search}%"))

    users = query.all()
    users.sort(key=lambda u: u.created_at or datetime.min, reverse=True)

    return jsonify([
        {
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
        }
        for u in users
    ])


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

    db.session.commit()

    return jsonify({
        "id": target_user.id,
        "email": target_user.email,
        "year": target_user.year,
        "semester": target_user.semester,
        "is_admin": target_user.is_admin,
        "is_suspended": target_user.is_suspended,
    })



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
        "price_notes": price("price_notes"),
        "price_past_paper": price("price_past_paper"),
        "price_qna": price("price_qna"),
        "ai_daily_limit_free": daily_limit("ai_daily_limit_free", 5),
        "ai_daily_limit_plus": daily_limit("ai_daily_limit_plus", 15),
        "ai_daily_limit_premium": daily_limit("ai_daily_limit_premium", None),
        "ai_monthly_budget_usd": money("ai_monthly_budget_usd", "20.00"),
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

    for price_key in ("price_notes", "price_past_paper", "price_qna"):
        if price_key in data:
            value = data[price_key]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return jsonify({"error": f"{price_key} must be a non-negative integer"}), 400
            setting = SystemSetting.query.filter_by(key=price_key).first()
            if not setting:
                setting = SystemSetting(key=price_key, value="0")
                db.session.add(setting)
            setting.value = str(value)

    for tier_key in ("ai_daily_limit_free", "ai_daily_limit_plus", "ai_daily_limit_premium"):
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
    return jsonify({
        "maintenance_mode": bool(mode_setting and mode_setting.value == "true"),
        "maintenance_message": message_setting.value if message_setting else "",
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
