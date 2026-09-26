from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REALTIME = ROOT / 'realtime_server.py'
MARK = 'PREPZA_CHAT_READ_RECEIPTS'

s = REALTIME.read_text(encoding='utf-8')
if MARK not in s:
    anchor = '''    emit("chat:read", {"conversation_id": conversation_id, "user_id": user_id, "read_at": read_at}, to=room_for(conversation_id), include_self=False)'''
    replacement = '''    try:
        db.session.execute(text("""
            INSERT INTO chat_message_receipt (message_id, user_id, delivered_at, read_at)
            SELECT m.id, :user_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM message AS m
            WHERE m.conversation_id = :conversation_id
              AND m.sender_id != :user_id
              AND m.created_at <= CURRENT_TIMESTAMP
            ON CONFLICT(message_id, user_id) DO UPDATE SET
                delivered_at = COALESCE(chat_message_receipt.delivered_at, excluded.delivered_at),
                read_at = COALESCE(excluded.read_at, chat_message_receipt.read_at)
        """), {"conversation_id": conversation_id, "user_id": user_id})
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Could not persist chat read receipts")
    emit("chat:read", {"conversation_id": conversation_id, "user_id": user_id, "read_at": read_at}, to=room_for(conversation_id), include_self=False)'''
    if anchor in s:
        s = s.replace(anchor, replacement, 1)
        REALTIME.write_text(s, encoding='utf-8')
        print('CHAT_READ_RECEIPTS_APPLIED')
    else:
        print('CHAT_READ_RECEIPTS_ALREADY_SOURCE_OWNED')
else:
    print('CHAT_READ_RECEIPTS_ALREADY_PRESENT')
