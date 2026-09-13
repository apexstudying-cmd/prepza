"""SQLAlchemy model for opaque group-chat E2EE key envelopes."""


def create_e2ee_models(db):
    """Return the canonical envelope model, creating it once if necessary."""
    for mapper in db.Model.registry.mappers:
        if mapper.local_table.name == "conversation_key_envelope":
            return mapper.class_

    class ConversationKeyEnvelope(db.Model):
        __tablename__ = "conversation_key_envelope"

        id = db.Column(db.Integer, primary_key=True)
        conversation_id = db.Column(
            db.Integer,
            db.ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=False,
        )
        recipient_user_id = db.Column(
            db.Integer,
            db.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        )
        sender_user_id = db.Column(
            db.Integer,
            db.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        )
        key_epoch = db.Column(db.Integer, nullable=False, default=0)
        version = db.Column(db.Integer, nullable=False, default=1)
        nonce = db.Column(db.String(64), nullable=False)
        ciphertext = db.Column(db.Text, nullable=False)
        created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

        __table_args__ = (
            db.UniqueConstraint(
                "conversation_id",
                "recipient_user_id",
                "key_epoch",
                name="uq_conversation_key_envelope_recipient_epoch",
            ),
            db.CheckConstraint("key_epoch >= 0", name="ck_conversation_key_envelope_epoch_nonnegative"),
            db.CheckConstraint("version > 0", name="ck_conversation_key_envelope_version_positive"),
        )

    return ConversationKeyEnvelope
