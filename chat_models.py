"""Chat conversation, membership, message and attachment ORM models."""
from datetime import datetime

from extensions import db


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
    # Non-null only for a Study Hub source-document share. Generated AI
    # artifacts never use this field and therefore cannot be shared through
    # the Study Hub chat flow.
    source_document_content_id = db.Column(db.Integer, db.ForeignKey("document_content.id"), nullable=True)
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
