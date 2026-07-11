import os
import re
import base64
import secrets
import requests
import sentry_sdk
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
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
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

db = SQLAlchemy(app)

EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
BASE_URL = os.environ.get("BASE_URL", "https://prepza-sf60.onrender.com")


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
        provided_secret = request.headers.get("X-Admin-Secret")
        real_secret = os.environ.get("ADMIN_SECRET")
        if not provided_secret or provided_secret != real_secret:
            return jsonify({"error": "Unauthorized"}), 401
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


@app.route("/")
def home():
    return "Prepza is alive!"


@app.route("/db-check")
def db_check():
    try:
        count = User.query.count()
        return f"Database connected! Current user count: {count}"
    except Exception as e:
        return f"Database connection failed: {str(e)}"


# ---------- Auth routes ----------

@app.route("/signup", methods=["POST"])
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
    token = request.args.get("token")
    if not token:
        return jsonify({"error": "Missing verification token"}), 400

    user = User.query.filter_by(verification_token=token).first()
    if not user:
        return jsonify({"error": "Invalid or expired verification link"}), 400

    user.email_verified = True
    user.verification_token = None
    db.session.commit()

    return jsonify({"message": "Email verified successfully! You can now log in."})


@app.route("/forgot-password", methods=["POST"])
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

    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.utcnow():
        return jsonify({"error": "Invalid or expired reset link"}), 400

    user.password_hash = generate_password_hash(new_password)
    user.reset_token = None
    user.reset_token_expiry = None
    db.session.commit()

    return jsonify({"message": "Password reset successfully. You can now log in."})


@app.route("/login", methods=["POST"])
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
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    user = User.query.get(user_id)
    return jsonify({
        "id": user.id,
        "email": user.email,
        "year": user.year,
        "semester": user.semester,
        "email_verified": user.email_verified,
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
        content_item = ContentItem.query.get(p.content_item_id)
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

    user = User.query.get(user_id)
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

    unit = Unit.query.get(unit_id)
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
            "file_url": item.file_url if (unlocked and item.is_downloadable) else None,
        })

    return jsonify({"unit": unit.code, "content": grouped})


@app.route("/content/<int:content_id>/pay", methods=["POST"])
def pay_for_content(content_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    content_item = ContentItem.query.get(content_id)
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

        print("DEBUG CallBackURL being sent:", repr(payload["CallBackURL"]))

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
    if not expected_token or callback_token != expected_token:
        # Don't reveal *why* it failed - just look like a normal 404 to anyone probing the URL
        return jsonify({"error": "Not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ResultCode": 1, "ResultDesc": "Invalid payload"}), 400

    print("MPESA CALLBACK RECEIVED:", data)

    try:
        stk_callback = data["Body"]["stkCallback"]
        checkout_request_id = stk_callback["CheckoutRequestID"]
        result_code = stk_callback["ResultCode"]

        payment = Payment.query.filter_by(
            checkout_request_id=checkout_request_id
        ).first()

        if payment and payment.status == "pending":
            payment.status = "success" if result_code == 0 else "failed"
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

    unit = Unit.query.get(unit_id)
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
    item = ContentItem.query.get(content_id)
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
        content_item = ContentItem.query.get(p.content_item_id)
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
    payment = Payment.query.get(payment_id)
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
