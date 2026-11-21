"""Security, push subscription and administrative audit models."""
from datetime import datetime

from extensions import db


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
