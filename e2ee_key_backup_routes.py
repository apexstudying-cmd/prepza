"""Session-scoped E2EE private-key backup route registration.

The browser wraps the private key before upload. The server stores only the
opaque ciphertext and its KDF salt for the currently authenticated account.
"""
from __future__ import annotations

from typing import Any, Callable

from flask import jsonify, request, session


USER_KEY_BACKUP_BLOB_MAX_LEN = 8000
# Generous ceiling for a base64-encoded, AES-GCM-wrapped exported JWK
# private key (typically well under 1000 chars) - guards against
# abuse/garbage, not a format check, since the server can't and
# shouldn't inspect what's inside this ciphertext.
USER_KEY_KDF_SALT_MAX_LEN = 128


def register_e2ee_key_backup_routes(
    app: Any,
    db: Any,
    UserKey: Any,
    require_csrf: Callable[[Callable[..., Any]], Callable[..., Any]],
) -> None:
    """Register the existing upload/download routes at their original app position."""

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
