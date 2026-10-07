"""
Chunk 6 - Chat tables migration.

Creates the Conversation, ConversationParticipant, and Message tables
by importing app.py (so the DDL comes straight from the real
SQLAlchemy model definitions, not hand-written SQL that could drift)
and running create_all against just those three tables.

checkfirst=True (the default) means this is safe to re-run - it will
not touch or drop any existing table, and does nothing if the chat
tables already exist.

Run this AFTER patch_add_chat_backend.py has been applied - it imports
app.py directly, so the Conversation/ConversationParticipant/Message
models need to already be defined there.

Usage:
    python migrate_add_chat_tables.py
"""

import sys

try:
    import app as prepza_app
except Exception as e:
    print(f"Could not import app.py: {e}", file=sys.stderr)
    sys.exit(1)

REQUIRED_MODELS = ("Conversation", "ConversationParticipant", "Message")

for name in REQUIRED_MODELS:
    if not hasattr(prepza_app, name):
        print(
            f"app.py has no '{name}' model - run patch_add_chat_backend.py "
            "first, then re-run this migration.",
            file=sys.stderr,
        )
        sys.exit(1)

tables = [getattr(prepza_app, name).__table__ for name in REQUIRED_MODELS]

with prepza_app.app.app_context():
    prepza_app.db.metadata.create_all(
        bind=prepza_app.db.engine,
        tables=tables,
        checkfirst=True,
    )

print("Chat tables ready: conversation, conversation_participant, message")
