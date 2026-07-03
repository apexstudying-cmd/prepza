import os
import re
import base64
import secrets
import requests
from datetime import datetime
from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")

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


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
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
    """
    Sends the verification email via Brevo's HTTP API instead of SMTP.
    We switched to this because Render (and most cloud hosts) block
    outbound SMTP ports as a common anti-spam measure - HTTPS is never
    blocked, so an API-based email service works reliably in production.
    """
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
    response.raise_for_status()  # raises an error if Brevo rejects the request


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


# ---------- M-Pesa routes ----------

@app.route("/mpesa/stk-push", methods=["POST"])
def stk_push():
    data = request.get_json()
    phone_number = data.get("phone_number")
    amount = data.get("amount", 1)

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
            "Amount": amount,
            "PartyA": phone_number,
            "PartyB": os.environ.get("MPESA_SHORTCODE"),
            "PhoneNumber": phone_number,
            "CallBackURL": os.environ.get("MPESA_CALLBACK_URL"),
            "AccountReference": "Prepza",
            "TransactionDesc": "Prepza content payment",
        }

        response = requests.post(url, json=payload, headers=headers)
        response_data = response.json()

        if "CheckoutRequestID" in response_data:
            payment = Payment(
                phone_number=phone_number,
                amount=amount,
                checkout_request_id=response_data["CheckoutRequestID"],
                status="pending",
            )
            db.session.add(payment)
            db.session.commit()

        return jsonify(response_data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.get_json()
    print("MPESA CALLBACK RECEIVED:", data)

    try:
        stk_callback = data["Body"]["stkCallback"]
        checkout_request_id = stk_callback["CheckoutRequestID"]
        result_code = stk_callback["ResultCode"]

        payment = Payment.query.filter_by(
            checkout_request_id=checkout_request_id
        ).first()

        if payment:
            payment.status = "success" if result_code == 0 else "failed"
            db.session.commit()

    except Exception as e:
        print("Callback processing error:", str(e))

    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
