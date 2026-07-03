import os
import base64
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    year = db.Column(db.Integer, nullable=True)
    semester = db.Column(db.Integer, nullable=True)


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    checkout_request_id = db.Column(db.String(100), unique=True, nullable=True)
    status = db.Column(db.String(20), default="pending")  # pending, success, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------- M-Pesa helper functions ----------

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


# ---------- Routes ----------

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


@app.route("/mpesa/stk-push", methods=["POST"])
def stk_push():
    """
    Triggers an STK push prompt to a phone number.
    For sandbox testing, always use: 254708374149
    """
    data = request.get_json()
    phone_number = data.get("phone_number")
    amount = data.get("amount", 1)  # default to 1 KES for sandbox testing

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

        # Save a pending payment record so we can track it
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
    """
    Safaricom calls this URL automatically after the customer
    enters their PIN (or cancels/times out).
    """
    data = request.get_json()
    print("MPESA CALLBACK RECEIVED:", data)  # helpful for debugging in Render logs

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

    # Always respond 200 — Safaricom retries aggressively if you don't
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
