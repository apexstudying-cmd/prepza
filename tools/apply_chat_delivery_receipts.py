from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'chat_interactions.py'
REALTIME = ROOT / 'realtime_server.py'
FRONT = ROOT / 'frontend' / 'src' / 'crypto' / 'chatRealtime.ts'
CHAT = ROOT / 'frontend' / 'src' / 'crypto' / 'WhatsAppChatExperience.tsx'

MARK = 'PREPZA_CHAT_DELIVERY_RECEIPTS'

# ---------------------------------------------------------------------------
# Server: persistent delivery metadata. Message bodies remain opaque.
# ---------------------------------------------------------------------------
s = BACKEND.read_text(encoding='utf-8')
if MARK not in s:
    schema_anchor = '''                db.session.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_chat_message_meta_conversation_kind
                    ON chat_message_meta (conversation_id, kind)
                """))'''
    schema_insert = schema_anchor + '''
                db.session.execute(text("""
                    CREATE TABLE IF NOT EXISTS chat_message_receipt (
                        message_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        delivered_at TIMESTAMP NULL,
                        read_at TIMESTAMP NULL,
                        PRIMARY KEY (message_id, user_id)
                    )
                """))
                db.session.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_chat_message_receipt_user_delivery
                    ON chat_message_receipt (user_id, delivered_at)
                """))'''
    if schema_anchor not in s:
        raise SystemExit('chat delivery: schema anchor missing')
    s = s.replace(schema_anchor, schema_insert, 1)

    decorate_anchor = '''    other_participants = [p for p in participants if p.user_id != user_id]

    decorated = []'''
    decorate_insert = '''    other_participants = [p for p in participants if p.user_id != user_id]
    message_ids = [m.get("id") for m in messages if isinstance(m, dict) and isinstance(m.get("id"), int)]
    delivered_counts = {}
    if message_ids:
        placeholders = ",".join(f":delivery_id_{i}" for i in range(len(message_ids)))
        delivery_params = {f"delivery_id_{i}": message_id for i, message_id in enumerate(message_ids)}
        delivery_rows = db.session.execute(text(f"""
            SELECT message_id, COUNT(*)
            FROM chat_message_receipt
            WHERE message_id IN ({placeholders}) AND delivered_at IS NOT NULL
            GROUP BY message_id
        """), delivery_params).fetchall()
        delivered_counts = {int(row[0]): int(row[1] or 0) for row in delivery_rows}

    decorated = []'''
    if decorate_anchor not in s:
        raise SystemExit('chat delivery: decorate anchor missing')
    s = s.replace(decorate_anchor, decorate_insert, 1)

    status_anchor = '''        next_item["kind"] = kind
        if isinstance(message_id, int) and item.get("sender_id") == user_id and other_participants:'''
    status_insert = '''        next_item["kind"] = kind
        if isinstance(message_id, int):
            delivered_by_count = delivered_counts.get(message_id, 0)
            next_item["delivered_by_count"] = delivered_by_count
            next_item["delivered_by_all"] = delivered_by_count >= len(other_participants) if other_participants else False
        if isinstance(message_id, int) and item.get("sender_id") == user_id and other_participants:'''
    if status_anchor not in s:
        raise SystemExit('chat delivery: status anchor missing')
    s = s.replace(status_anchor, status_insert, 1)
    BACKEND.write_text(s, encoding='utf-8')

# ---------------------------------------------------------------------------
# Socket.IO: recipient devices acknowledge persisted delivery.
# ---------------------------------------------------------------------------
s = REALTIME.read_text(encoding='utf-8')
if MARK not in s:
    read_marker = '''@socketio.on("chat:read")
def handle_read(data):'''
    delivery = '''@socketio.on("chat:delivered")
def handle_delivered(data):
    user_id = authenticated_user_id()
    if user_id is None or not isinstance(data, dict):
        return
    try:
        conversation_id = int(data.get("conversation_id"))
        message_id = int(data.get("message_id"))
    except (TypeError, ValueError):
        return
    if conversation_id <= 0 or message_id <= 0 or not is_active_participant(user_id, conversation_id):
        return
    row = db.session.execute(text(
        "SELECT sender_id FROM message WHERE id = :message_id AND conversation_id = :conversation_id LIMIT 1"
    ), {"message_id": message_id, "conversation_id": conversation_id}).first()
    if row is None or int(row[0]) == user_id:
        return
    try:
        db.session.execute(text("""
            INSERT INTO chat_message_receipt (message_id, user_id, delivered_at)
            VALUES (:message_id, :user_id, CURRENT_TIMESTAMP)
            ON CONFLICT(message_id, user_id) DO UPDATE SET
                delivered_at = COALESCE(chat_message_receipt.delivered_at, excluded.delivered_at)
        """), {"message_id": message_id, "user_id": user_id})
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Could not persist chat delivery receipt")
        return
    emit("chat:delivered", {"conversation_id": conversation_id, "message_id": message_id, "user_id": user_id}, to=room_for(conversation_id), include_self=False)


''' + read_marker
    if read_marker not in s:
        raise SystemExit('chat delivery: realtime read anchor missing')
    s = s.replace(read_marker, delivery, 1)
    s = s.replace('"""Socket.IO entrypoint for Prepza realtime study chat."""', '"""Socket.IO entrypoint for Prepza realtime study chat."""\n# PREPZA_CHAT_DELIVERY_RECEIPTS', 1)
    REALTIME.write_text(s, encoding='utf-8')

# ---------------------------------------------------------------------------
# Client realtime: acknowledge messages as delivered and surface receipts.
# ---------------------------------------------------------------------------
s = FRONT.read_text(encoding='utf-8')
if MARK not in s:
    message_anchor = '''  socket.on('chat:message', (message: RealtimeMessageEvent) => { if (message && typeof message.conversation_id === 'number' && typeof message.id === 'number') window.dispatchEvent(new CustomEvent('prepza-realtime-message', { detail: message })) })'''
    message_replacement = '''  socket.on('chat:message', (message: RealtimeMessageEvent) => {
    if (message && typeof message.conversation_id === 'number' && typeof message.id === 'number') {
      socket?.emit('chat:delivered', { conversation_id: message.conversation_id, message_id: message.id })
      window.dispatchEvent(new CustomEvent('prepza-realtime-message', { detail: message }))
    }
  })'''
    if message_anchor not in s:
        raise SystemExit('chat delivery: realtime message anchor missing')
    s = s.replace(message_anchor, message_replacement, 1)
    read_anchor = "  socket.on('chat:read', detail => window.dispatchEvent(new CustomEvent('prepza-realtime-read', { detail })))"
    read_replacement = read_anchor + "\n  socket.on('chat:delivered', detail => window.dispatchEvent(new CustomEvent('prepza-realtime-delivered', { detail })))"
    if read_anchor not in s:
        raise SystemExit('chat delivery: realtime read anchor missing')
    s = s.replace(read_anchor, read_replacement, 1)
    FRONT.write_text(s, encoding='utf-8')

# ---------------------------------------------------------------------------
# Client chat list: decrypt the latest message locally and show receipt state.
# The existing E2EE fetch bridge decrypts message bodies on the client.
# ---------------------------------------------------------------------------
s = CHAT.read_text(encoding='utf-8')
if MARK not in s:
    s = s.replace("type ChatSummary = { id: number; is_group: boolean; name: string; last_message: string | null; last_message_at: string | null; unread_count: number; status?: string }", "type ChatSummary = { id: number; is_group: boolean; name: string; last_message: string | null; last_message_at: string | null; unread_count: number; status?: 'sent' | 'delivered' | 'read' | string }")
    s = s.replace("type Message = { id: number; conversation_id: number; sender_id: number; body: string | null; nonce?: string | null; is_deleted: boolean; created_at: string | null; edited_at: string | null; attachment: Attachment | null; kind?: 'text' | 'reaction'; read_by_count?: number; read_by_all?: boolean }", "type Message = { id: number; conversation_id: number; sender_id: number; body: string | null; nonce?: string | null; is_deleted: boolean; created_at: string | null; edited_at: string | null; attachment: Attachment | null; kind?: 'text' | 'reaction'; delivered_by_count?: number; delivered_by_all?: boolean; read_by_count?: number; read_by_all?: boolean }")
    old = '''  const loadList = async () => { setListError(''); try { const result = await api<{ chats: ChatSummary[] }>('/chats'); setChats(Array.isArray(result.chats) ? result.chats : []) } catch (value) { setListError(friendlyError(value, 'Could not load your conversations.')) } }'''
    new = '''  const loadList = async () => {
    setListError('')
    try {
      const result = await api<{ chats: ChatSummary[] }>('/chats')
      const base = Array.isArray(result.chats) ? result.chats : []
      // Keep every conversation subscribed while the chat experience is open.
      // This lets a recipient acknowledge delivery even before opening the chat.
      base.forEach(chat => joinRealtimeChat(chat.id))
      const enriched = await Promise.all(base.map(async chat => {
        if (!chat.last_message_at) return chat
        try {
          const latest = await api<{ messages: Message[] }>(`/chats/${chat.id}/messages`)
          const candidates = (latest.messages || []).filter(message => message.kind !== 'reaction')
          const message = candidates[candidates.length - 1]
          if (!message) return chat
          let preview = displayText(message)
          if (message.attachment && !preview) preview = /^(audio|audio\\/)/i.test(message.attachment.file_type) ? 'Voice message' : message.attachment.original_filename
          if (!preview) preview = message.is_deleted ? 'This message was deleted' : 'Encrypted message'
          const next = { ...chat, last_message: preview, last_message_at: message.created_at || chat.last_message_at }
          if (message.sender_id === meIdRef.current) {
            next.status = message.read_by_all ? 'read' : message.delivered_by_count ? 'delivered' : 'sent'
          }
          return next
        } catch {
          return chat
        }
      }))
      setChats(enriched)
    } catch (value) { setListError(friendlyError(value, 'Could not load your conversations.')) }
  }'''
    if old not in s:
        raise SystemExit('chat delivery: loadList anchor missing')
    s = s.replace(old, new, 1)

    event_anchor = '''    const onRead = (event: Event) => { const data = (event as CustomEvent<{ conversation_id?: number; user_id?: number }>).detail; if (data?.conversation_id === selectedId && data.user_id) setMessages(current => current.map(m => m.sender_id === meIdRef.current ? { ...m, read_by_count: Math.max(m.read_by_count || 0, 1) } : m)) }'''
    event_replacement = event_anchor + '''
    const onDelivered = (event: Event) => { const data = (event as CustomEvent<{ conversation_id?: number; message_id?: number; user_id?: number }>).detail; if (data?.conversation_id === selectedId && data.message_id && data.user_id) setMessages(current => current.map(m => m.id === data.message_id ? { ...m, delivered_by_count: Math.max(m.delivered_by_count || 0, 1) } : m)); void loadList() }'''
    if event_anchor not in s:
        raise SystemExit('chat delivery: onRead anchor missing')
    s = s.replace(event_anchor, event_replacement, 1)
    listener_anchor = "    window.addEventListener('prepza-realtime-message', onMessage); window.addEventListener('prepza-realtime-read', onRead); window.addEventListener('prepza-realtime-typing', onTyping);"
    listener_replacement = "    window.addEventListener('prepza-realtime-message', onMessage); window.addEventListener('prepza-realtime-read', onRead); window.addEventListener('prepza-realtime-delivered', onDelivered); window.addEventListener('prepza-realtime-typing', onTyping);"
    if listener_anchor in s:
        s = s.replace(listener_anchor, listener_replacement, 1)
    elif "prepza-realtime-delivered" not in s:
        marker = "window.addEventListener('prepza-realtime-read', onRead);"
        if marker not in s:
            raise SystemExit('chat delivery: listener anchor missing')
        s = s.replace(marker, marker + " window.addEventListener('prepza-realtime-delivered', onDelivered);", 1)
    cleanup_anchor = "    return () => { window.removeEventListener('prepza-realtime-message', onMessage); window.removeEventListener('prepza-realtime-read', onRead); window.removeEventListener('prepza-realtime-typing', onTyping);"
    cleanup_replacement = "    return () => { window.removeEventListener('prepza-realtime-message', onMessage); window.removeEventListener('prepza-realtime-read', onRead); window.removeEventListener('prepza-realtime-delivered', onDelivered); window.removeEventListener('prepza-realtime-typing', onTyping);"
    if cleanup_anchor in s:
        s = s.replace(cleanup_anchor, cleanup_replacement, 1)
    elif "prepza-realtime-delivered'" in s:
        pass
    else:
        marker = "window.removeEventListener('prepza-realtime-read', onRead);"
        if marker not in s:
            raise SystemExit('chat delivery: cleanup anchor missing')
        s = s.replace(marker, marker + " window.removeEventListener('prepza-realtime-delivered', onDelivered);", 1)

    status_anchor = "{chat.last_message || 'No messages yet'}</div></div>{chat.unread_count > 0"
    status_replacement = "{chat.status && chat.status !== 'sent' && <span style={{ fontSize:10,color:'#8c929c',marginRight:4 }}>{chat.status === 'read' ? '✓✓' : '✓'}</span>}{chat.last_message || 'No messages yet'}</div></div>{chat.unread_count > 0"
    if status_anchor in s:
        s = s.replace(status_anchor, status_replacement, 1)

    bubble_anchor = "{timeLabel(message.created_at)} {mine && <span title={message.read_by_all ? 'Read by everyone' : message.read_by_count ? `Read by ${message.read_by_count}` : 'Sent'}>{message.read_by_count ? '✓✓' : '✓'}</span>}"
    bubble_replacement = "{timeLabel(message.created_at)} {mine && <span title={message.read_by_all ? 'Read by everyone' : message.delivered_by_count ? (message.delivered_by_all ? 'Delivered to everyone' : `Delivered to ${message.delivered_by_count}`) : 'Sent'}>{message.read_by_all ? '✓✓' : message.delivered_by_count ? '✓✓' : '✓'}</span>}"
    if bubble_anchor in s:
        s = s.replace(bubble_anchor, bubble_replacement, 1)

    s = s.replace("type ChatSummary = {", "// PREPZA_CHAT_DELIVERY_RECEIPTS\ntype ChatSummary = {", 1)
    CHAT.write_text(s, encoding='utf-8')

print(f'{MARK}_APPLIED')
