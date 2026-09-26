"""Prepza email OTP authentication and Amazon SES delivery.

The service is deliberately provider-aware but provider-agnostic at the auth
boundary: the student verifies a short-lived email OTP, while SES is the
launch transactional-email provider. SMS can be added later without changing
the OTP verification contract.
"""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from flask import jsonify, request, session
from sqlalchemy import func


DEFAULTS = {
    "otp_enabled": "true",
    "otp_length": "6",
    "otp_expiry_minutes": "10",
    "otp_max_attempts": "5",
    "otp_resend_cooldown_seconds": "60",
    "otp_max_sends_per_target_hour": "5",
    "otp_max_sends_per_ip_hour": "20",
}


def register_email_otp(app, db, User, SystemSetting, require_admin, require_csrf, limiter):
    class AuthOtp(db.Model):
        __tablename__ = "auth_otp"
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
        purpose = db.Column(db.String(30), nullable=False, index=True)
        target = db.Column(db.String(320), nullable=False, index=True)
        code_hash = db.Column(db.String(64), nullable=False)
        attempts = db.Column(db.Integer, nullable=False, default=0)
        request_ip = db.Column(db.String(64), nullable=True, index=True)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
        expires_at = db.Column(db.DateTime, nullable=False)
        consumed_at = db.Column(db.DateTime, nullable=True)

        __table_args__ = (
            db.Index("ix_auth_otp_target_created", "target", "created_at"),
            db.Index("ix_auth_otp_ip_created", "request_ip", "created_at"),
        )

    def setting(name):
        row = SystemSetting.query.filter_by(key=name).first()
        return row.value if row and row.value != "" else DEFAULTS[name]

    def setting_int(name, minimum, maximum):
        try:
            value = int(setting(name))
        except (TypeError, ValueError):
            value = int(DEFAULTS[name])
        return max(minimum, min(maximum, value))

    def enabled():
        return str(setting("otp_enabled")).strip().lower() in {"1", "true", "yes", "on"}

    def otp_length():
        return setting_int("otp_length", 6, 8)

    def otp_expiry_minutes():
        return setting_int("otp_expiry_minutes", 2, 30)

    def max_attempts():
        return setting_int("otp_max_attempts", 3, 10)

    def resend_cooldown():
        return setting_int("otp_resend_cooldown_seconds", 30, 600)

    def max_target_sends_hour():
        return setting_int("otp_max_sends_per_target_hour", 1, 20)

    def max_ip_sends_hour():
        return setting_int("otp_max_sends_per_ip_hour", 5, 100)

    def _secret():
        secret = (app.config.get("SECRET_KEY") or os.environ.get("SECRET_KEY") or "").encode()
        if not secret:
            raise RuntimeError("SECRET_KEY is required for OTP hashing")
        return secret

    def _hash(code):
        return hmac.new(_secret(), code.encode("utf-8"), hashlib.sha256).hexdigest()

    def _generate_code():
        upper = 10 ** otp_length()
        return f"{secrets.randbelow(upper):0{otp_length()}d}"

    def _ses_client():
        region = (
            os.environ.get("AWS_SES_REGION")
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
        )
        if not region:
            raise RuntimeError("AWS_SES_REGION (or AWS_REGION/AWS_DEFAULT_REGION) is required")
        return boto3.client("sesv2", region_name=region)

    def _from_address():
        return (
            os.environ.get("SES_FROM_EMAIL")
            or os.environ.get("AWS_SES_FROM_EMAIL")
            or os.environ.get("AWS_FROM_EMAIL")
            or ""
        ).strip()

    def ses_configured():
        return bool(_from_address() and (
            os.environ.get("AWS_ACCESS_KEY_ID")
            and os.environ.get("AWS_SECRET_ACCESS_KEY")
        ))

    def send_email(to_email, subject, text_body, html_body, purpose):
        sender = _from_address()
        if not sender:
            raise RuntimeError("SES_FROM_EMAIL is not configured")
        response = _ses_client().send_email(
            FromEmailAddress=sender,
            Destination={"ToAddresses": [to_email]},
            Content={
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": text_body, "Charset": "UTF-8"},
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                    },
                }
            },
        )
        return response.get("MessageId")

    def _record_send(user, purpose, target, request_ip):
        now = datetime.utcnow()
        target_count = AuthOtp.query.filter(
            AuthOtp.target == target,
            AuthOtp.purpose == purpose,
            AuthOtp.created_at >= now - timedelta(hours=1),
        ).count()
        if target_count >= max_target_sends_hour():
            raise ValueError("Too many verification emails requested. Please try again later.")

        ip_count = AuthOtp.query.filter(
            AuthOtp.request_ip == request_ip,
            AuthOtp.purpose == purpose,
            AuthOtp.created_at >= now - timedelta(hours=1),
        ).count()
        if request_ip and ip_count >= max_ip_sends_hour():
            raise ValueError("Too many verification requests from this connection. Please try again later.")

        latest = (
            AuthOtp.query
            .filter(AuthOtp.target == target, AuthOtp.purpose == purpose)
            .order_by(AuthOtp.created_at.desc())
            .first()
        )
        if latest and latest.created_at > now - timedelta(seconds=resend_cooldown()):
            remaining = int((latest.created_at + timedelta(seconds=resend_cooldown()) - now).total_seconds())
            raise ValueError(f"Please wait {max(1, remaining)} seconds before requesting another code.")

        # A new code invalidates all previous active codes for this target.
        AuthOtp.query.filter(
            AuthOtp.target == target,
            AuthOtp.purpose == purpose,
            AuthOtp.consumed_at.is_(None),
            AuthOtp.expires_at > now,
        ).update({"consumed_at": now}, synchronize_session=False)

        code = _generate_code()
        row = AuthOtp(
            user_id=user.id,
            purpose=purpose,
            target=target,
            code_hash=_hash(code),
            request_ip=request_ip,
            expires_at=now + timedelta(minutes=otp_expiry_minutes()),
        )
        db.session.add(row)
        db.session.flush()
        return row, code

    def issue(user, purpose, request_ip):
        if not enabled():
            raise RuntimeError("Email OTP verification is disabled")
        if purpose not in {"signup_verify", "password_reset"}:
            raise ValueError("Unsupported OTP purpose")

        target = user.email.lower()
        row, code = _record_send(user, purpose, target, request_ip)

        if purpose == "signup_verify":
            subject = "Your Prepza verification code"
            text_body = (
                f"Your Prepza verification code is {code}. "
                f"It expires in {otp_expiry_minutes()} minutes. "
                "If you did not create this account, you can ignore this email."
            )
            html_body = (
                "<p>Welcome to Prepza.</p>"
                f"<p style='font-size:28px;font-weight:700;letter-spacing:6px'>{code}</p>"
                f"<p>This code expires in {otp_expiry_minutes()} minutes.</p>"
                "<p>If you did not create this account, you can ignore this email.</p>"
            )
        else:
            subject = "Your Prepza password reset code"
            text_body = (
                f"Your Prepza password reset code is {code}. "
                f"It expires in {otp_expiry_minutes()} minutes. "
                "If you did not request this, you can ignore this email."
            )
            html_body = (
                "<p>We received a password reset request for Prepza.</p>"
                f"<p style='font-size:28px;font-weight:700;letter-spacing:6px'>{code}</p>"
                f"<p>This code expires in {otp_expiry_minutes()} minutes.</p>"
                "<p>If you did not request this, you can ignore this email.</p>"
            )

        try:
            message_id = send_email(target, subject, text_body, html_body, purpose)
            db.session.commit()
            return {"expires_in_seconds": otp_expiry_minutes() * 60, "message_id": message_id}
        except Exception:
            db.session.rollback()
            raise

    def verify(user, purpose, code):
        if not isinstance(code, str):
            return False, "Invalid or expired verification code."
        code = code.strip()
        if len(code) != otp_length() or not code.isdigit():
            return False, "Invalid or expired verification code."

        now = datetime.utcnow()
        row = (
            AuthOtp.query
            .filter(
                AuthOtp.user_id == user.id,
                AuthOtp.purpose == purpose,
                AuthOtp.consumed_at.is_(None),
            )
            .order_by(AuthOtp.created_at.desc())
            .first()
        )
        if not row or row.expires_at <= now:
            return False, "Invalid or expired verification code."
        if row.attempts >= max_attempts():
            return False, "Too many incorrect attempts. Request a new code."

        row.attempts += 1
        if not hmac.compare_digest(row.code_hash, _hash(code)):
            db.session.commit()
            return False, "Invalid or expired verification code."

        row.consumed_at = now
        db.session.commit()
        return True, None

    @app.route("/verify-otp", methods=["POST"])
    @limiter.limit("30 per minute")
    def verify_otp_route():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        code = data.get("code") or ""
        if not email:
            return jsonify({"error": "Email is required"}), 400
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({"error": "Invalid or expired verification code."}), 400
        ok, error = verify(user, "signup_verify", code)
        if not ok:
            return jsonify({"error": error}), 400
        if user.email_verified:
            return jsonify({"message": "Email already verified", "redirect": "/"}), 200
        user.email_verified = True
        _sync_referral_progress = app.view_functions.get("_sync_referral_progress")
        if _sync_referral_progress:
            try:
                _sync_referral_progress(user)
            except Exception:
                app.logger.exception("Referral sync failed during OTP verification")
        db.session.commit()
        session.permanent = True
        session["user_id"] = user.id
        session["_session_version"] = user.session_version
        return jsonify({"message": "Email verified successfully", "redirect": "/"}), 200

    @app.route("/resend-verification", methods=["POST"])
    @limiter.limit("20 per hour")
    def resend_verification():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        generic = {"message": "If an unverified account with that email exists, a new verification code has been sent."}
        if not email or not User.query.filter_by(email=email).first():
            return jsonify(generic), 200
        user = User.query.filter_by(email=email).first()
        if user.email_verified:
            return jsonify(generic), 200
        try:
            result = issue(user, "signup_verify", request.remote_addr or "")
            return jsonify({**generic, "expires_in_seconds": result["expires_in_seconds"]}), 200
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 429
        except Exception:
            app.logger.exception("SES verification email failed")
            return jsonify({"error": "We could not send a verification code right now. Please try again later."}), 503

    @app.route("/forgot-password", methods=["POST"])
    @limiter.limit("20 per hour")
    def forgot_password():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        if not email:
            return jsonify({"error": "Email is required"}), 400
        generic = {"message": "If an account with that email exists, a password reset code has been sent."}
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify(generic), 200
        try:
            result = issue(user, "password_reset", request.remote_addr or "")
            return jsonify({**generic, "expires_in_seconds": result["expires_in_seconds"]}), 200
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 429
        except Exception:
            app.logger.exception("SES password reset email failed")
            return jsonify({"error": "We could not send a reset code right now. Please try again later."}), 503

    @app.route("/reset-password", methods=["POST"])
    @limiter.limit("20 per hour")
    def reset_password():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        code = data.get("code") or ""
        new_password = data.get("new_password") or ""
        if not email or not code:
            return jsonify({"error": "Email and verification code are required"}), 400
        if len(new_password) < 8:
            return jsonify({"error": "Password must be at least 8 characters long"}), 400
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({"error": "Invalid or expired verification code."}), 400
        ok, error = verify(user, "password_reset", code)
        if not ok:
            return jsonify({"error": error}), 400
        user.password_hash = generate_password_hash(new_password)
        user.session_version = (user.session_version or 0) + 1
        db.session.commit()
        return jsonify({"message": "Password reset successfully. You can now log in."}), 200

    @app.route("/admin/auth/otp", methods=["GET"])
    @require_admin
    def admin_otp_config():
        region = os.environ.get("AWS_SES_REGION") or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
        telemetry = {"configured": ses_configured(), "region": region, "status": "not_configured"}
        if ses_configured() and region:
            try:
                account = _ses_client().get_account()
                quota = account.get("SendQuota") or {}
                telemetry.update({
                    "status": "ok" if account.get("SendingEnabled", True) else "sending_disabled",
                    "sending_enabled": bool(account.get("SendingEnabled", True)),
                    "max_24_hour_send": quota.get("Max24HourSend"),
                    "max_send_rate": quota.get("MaxSendRate"),
                    "sent_last_24_hours": quota.get("SentLast24Hours"),
                    "enforcement_status": account.get("EnforcementStatus"),
                })
            except (ClientError, BotoCoreError, Exception) as exc:
                telemetry.update({"status": "error", "error": str(exc)[:240]})

        return jsonify({
            "settings": {key: setting(key) for key in DEFAULTS},
            "ses": telemetry,
        })

    @app.route("/admin/auth/otp", methods=["PATCH"])
    @require_csrf
    @require_admin
    def update_admin_otp_config():
        data = request.get_json(silent=True) or {}
        allowed = set(DEFAULTS)
        for key, value in data.items():
            if key not in allowed:
                return jsonify({"error": f"Unsupported OTP setting: {key}"}), 400
            row = SystemSetting.query.filter_by(key=key).first()
            if not row:
                row = SystemSetting(key=key, value="")
                db.session.add(row)
            if key == "otp_enabled":
                normalized = "true" if bool(value) else "false"
            else:
                try:
                    normalized = str(int(value))
                except (TypeError, ValueError):
                    return jsonify({"error": f"{key} must be an integer"}), 400
            row.value = normalized
        db.session.commit()
        return admin_otp_config()

    app.extensions["prepza_auth_otp"] = {
        "AuthOtp": AuthOtp,
        "issue": issue,
        "verify": verify,
        "ses_configured": ses_configured,
    }
    return AuthOtp
