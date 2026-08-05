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
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

sentry_dsn = os.environ.get("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=0,  # Error monitoring only, no performance tracing
        send_default_pii=False,  # Skip sending user IPs/headers by default
    )

app = Flask(__name__)
import logging
app.logger.setLevel(logging.INFO)
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
    if not re.search(r"[A-Za-z]", password):
        return "Password must include at least one letter."
    if not re.search(r"\d", password):
        return "Password must include at least one number."
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
    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(64), nullable=True)
    reset_token = db.Column(db.String(64), nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)


class Unit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    semester = db.Column(db.Integer, nullable=False)


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


class ViewProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    content_item_id = db.Column(db.Integer, db.ForeignKey("content_item.id"), nullable=False)
    page_num = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("user_id", "content_item_id", name="uq_view_progress_user_item"),
    )


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
        provided_secret = request.headers.get("X-Admin-Secret")
        real_secret = os.environ.get("ADMIN_SECRET")
        if not provided_secret or not real_secret or not hmac.compare_digest(provided_secret, real_secret):
            return jsonify({"error": "Unauthorized"}), 401
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


def has_access(user_id, content_item):
    if content_item.price == 0:
        return True

    successful_payment = Payment.query.filter_by(
        user_id=user_id,
        content_item_id=content_item.id,
        status="success",
    ).first()

    return successful_payment is not None


def get_signed_url(bucket_path, expires_in=60):
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

    sign_url = f"{supabase_url}/storage/v1/object/sign/content/{bucket_path}"
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


def fetch_private_file_bytes(bucket_path):
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

    download_url = f"{supabase_url}/storage/v1/object/content/{bucket_path}"
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

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({"error": "An account with this email already exists"}), 409

    token = secrets.token_urlsafe(32)

    new_user = User(
        email=email,
        password_hash=generate_password_hash(password),
        year=year,
        semester=semester,
        email_verified=False,
        verification_token=token,
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

    session.permanent = True
    session["user_id"] = user.id
    return jsonify({"message": "Logged in successfully", "user_id": user.id})


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return jsonify({"message": "Logged out successfully"})


@app.route("/me")
def me():
    app.logger.info(
        "[/me DEBUG] raw Cookie header: %r", request.headers.get("Cookie")
    )
    app.logger.info(
        "[/me DEBUG] session contents: %r", dict(session)
    )
    user_id = session.get("user_id")
    app.logger.info("[/me DEBUG] user_id from session: %r", user_id)
    if not user_id:
        app.logger.info("[/me DEBUG] -> returning 401 Not logged in")
        return jsonify({"error": "Not logged in"}), 401

    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    user = db.session.get(User, user_id)
    return jsonify({
        "id": user.id,
        "email": user.email,
        "year": user.year,
        "semester": user.semester,
        "email_verified": user.email_verified,
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

    user = db.session.get(User, user_id)
    user.year = year
    user.semester = semester
    db.session.commit()

    return jsonify({
        "message": "Profile updated",
        "year": user.year,
        "semester": user.semester,
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
            "price": item.price,
            "unlocked": unlocked,
            "file_url": get_signed_url(item.file_url) if (unlocked and item.is_downloadable) else None,
        })

    return jsonify({"unit": unit.code, "content": grouped})


@app.route("/library")
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

    progress = ViewProgress.query.filter_by(
        user_id=user_id, content_item_id=content_item.id
    ).first()
    last_page = progress.page_num if progress else 0

    return jsonify({
        "content_id": content_item.id,
        "title": content_item.title,
        "page_count": page_count,
        "last_page": last_page,
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

    if content_item.price == 0:
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
            "Amount": content_item.price,
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
                amount=content_item.price,
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


# ---------- Admin routes (protected) ----------

@app.route("/admin/units", methods=["POST"])
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
            "price": item.price,
        })

    return jsonify({"content": result})


@app.route("/admin/content", methods=["POST"])
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
    price = data.get("price", 0)

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
        price=price,
    )
    db.session.add(item)
    db.session.commit()

    return jsonify({"message": "Content added", "content_id": item.id}), 201


@app.route("/admin/content/<int:content_id>", methods=["PATCH"])
@require_admin
def admin_update_content(content_id):
    item = db.session.get(ContentItem, content_id)
    if not item:
        return jsonify({"error": "Content not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    if "price" in data:
        item.price = data["price"]
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
        "price": item.price,
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


@app.route("/admin/payments/<int:payment_id>/refund", methods=["POST"])
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
