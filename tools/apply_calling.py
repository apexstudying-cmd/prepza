from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / 'frontend' / 'src' / 'crypto'

chat = FRONT / 'WhatsAppChatExperience.tsx'
s = chat.read_text(encoding='utf-8')

if "import CallExperience from './CallExperience'" not in s:
    anchor = "import { provisionInitialGroupKey } from './groupProvisioning'"
    if anchor not in s:
        raise SystemExit('Calling patch: chat import anchor missing')
    s = s.replace(anchor, anchor + "\nimport CallExperience from './CallExperience'", 1)

# Put the two call controls at the end of the real chat header. This keeps
# them visible on narrow screens instead of relying on flex ordering.
if 'className="prepza-call-actions"' not in s:
    header_start = '<header className="prepza-wa-head">'
    header_end = '</header>'
    start = s.find(header_start)
    end = s.find(header_end, start + len(header_start)) if start >= 0 else -1
    if start < 0 or end < 0:
        raise SystemExit('Calling patch: chat header anchors missing')
    injection = """{view === 'detail' && detail && !detail.is_group && (() => { const peer = detail.participants.find(item => item.user_id !== meId); return peer ? <div className=\"prepza-call-actions\" style={{ marginLeft:7,display:'flex',gap:7,flexShrink:0 }}><button type=\"button\" className=\"prepza-start-call\" aria-label=\"Start voice call\" title=\"Voice call\" onClick={() => window.dispatchEvent(new CustomEvent('prepza-start-call',{detail:{conversationId:detail.id,peerId:peer.user_id,peerName:peer.display_name,kind:'voice'}}))} style={{width:34,height:34,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer',fontSize:16}}>☎</button><button type=\"button\" className=\"prepza-start-call\" aria-label=\"Start video call\" title=\"Video call\" onClick={() => window.dispatchEvent(new CustomEvent('prepza-start-call',{detail:{conversationId:detail.id,peerId:peer.user_id,peerName:peer.display_name,kind:'video'}}))} style={{width:34,height:34,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer',fontSize:16}}>▣</button></div> : null })()}"""
    s = s[:end] + injection + s[end:]

# Mount the call overlay inside the chat shell immediately before the final
# component close. Do not depend on exact indentation or other child markup.
if '<CallExperience userId={meId} />' not in s:
    final_component_close = s.rfind('\n}')
    if final_component_close < 0:
        raise SystemExit('Calling patch: component close missing')
    root_close = s.rfind('\n  </div>', 0, final_component_close)
    if root_close < 0:
        raise SystemExit('Calling patch: root shell close missing')
    s = s[:root_close] + '\n    <CallExperience userId={meId} />' + s[root_close:]

chat.write_text(s, encoding='utf-8')

# Backend: authenticated, membership-checked WebRTC signaling. Media never
# passes through this server; only offer/answer/ICE metadata does.
server = ROOT / 'realtime_server.py'
s = server.read_text(encoding='utf-8')
if '_active_calls = {}' not in s:
    s = s.replace('_socket_state_lock = Lock()', '_socket_state_lock = Lock()\n_active_calls = {}\n_active_calls_lock = Lock()', 1)
    s = s.replace('from app import app, db, Conversation, ConversationParticipant', 'from app import app, db, Conversation, ConversationParticipant, User', 1)
    helper = r'''

def emit_to_user(user_id, event, payload):
    with _socket_state_lock:
        targets = [sid for sid, uid in _socket_users.items() if uid == user_id]
    for sid in targets:
        socketio.emit(event, payload, to=sid)


def call_participants(conversation_id):
    rows = db.session.execute(text(
        "SELECT user_id FROM conversation_participant "
        "WHERE conversation_id = :conversation_id AND left_at IS NULL"
    ), {"conversation_id": conversation_id}).scalars().all()
    return [int(value) for value in rows]


def validate_call_event(data):
    user_id = authenticated_user_id()
    if user_id is None or not isinstance(data, dict):
        return None
    call_id = data.get("call_id")
    target_id = data.get("to_user_id")
    try:
        target_id = int(target_id)
    except (TypeError, ValueError):
        return None
    if not isinstance(call_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", call_id):
        return None
    return user_id, target_id, call_id


@socketio.on("call:invite")
def handle_call_invite(data):
    validated = validate_call_event(data)
    if not validated:
        return {"ok": False}
    caller_id, target_id, call_id = validated
    try:
        conversation_id = int(data.get("conversation_id"))
    except (TypeError, ValueError):
        return {"ok": False}
    kind = data.get("kind")
    if kind not in {"voice", "video"} or target_id == caller_id:
        return {"ok": False}
    participants = call_participants(conversation_id)
    if len(participants) != 2 or set(participants) != {caller_id, target_id}:
        return {"ok": False}
    with _active_calls_lock:
        if call_id in _active_calls or any(c["caller_id"] == caller_id or c["callee_id"] == caller_id for c in _active_calls.values()):
            return {"ok": False, "error": "Another call is already active"}
        _active_calls[call_id] = {"caller_id": caller_id, "callee_id": target_id, "conversation_id": conversation_id, "kind": kind}
    user = db.session.get(User, caller_id)
    emit_to_user(target_id, "call:incoming", {"call_id": call_id, "conversation_id": conversation_id, "from_user_id": caller_id, "from_name": getattr(user, "display_name", None), "to_user_id": target_id, "kind": kind})
    return {"ok": True}


def _route_call_signal(event_name, data, final=False):
    validated = validate_call_event(data)
    if not validated:
        return {"ok": False}
    sender_id, target_id, call_id = validated
    with _active_calls_lock:
        call = _active_calls.get(call_id)
    if not call or sender_id not in {call["caller_id"], call["callee_id"]} or target_id != (call["callee_id"] if sender_id == call["caller_id"] else call["caller_id"]):
        return {"ok": False}
    payload = {"call_id": call_id, "conversation_id": call["conversation_id"], "from_user_id": sender_id, "to_user_id": target_id, "kind": call["kind"]}
    if "payload" in data:
        payload["payload"] = data.get("payload")
    emit_to_user(target_id, event_name, payload)
    if final:
        with _active_calls_lock:
            _active_calls.pop(call_id, None)
    return {"ok": True}


@socketio.on("call:accept")
def handle_call_accept(data):
    return _route_call_signal("call:accepted", data)


@socketio.on("call:reject")
def handle_call_reject(data):
    return _route_call_signal("call:rejected", data, final=True)


@socketio.on("call:end")
def handle_call_end(data):
    return _route_call_signal("call:ended", data, final=True)


@socketio.on("call:offer")
def handle_call_offer(data):
    return _route_call_signal("call:offer", data)


@socketio.on("call:answer")
def handle_call_answer(data):
    return _route_call_signal("call:answer", data)


@socketio.on("call:ice")
def handle_call_ice(data):
    return _route_call_signal("call:ice", data)
'''
    anchor = '\n@socketio.on("disconnect")'
    if anchor not in s:
        raise SystemExit('Calling patch: disconnect anchor missing')
    s = s.replace(anchor, helper + '\n\n@socketio.on("disconnect")', 1)
    server.write_text(s, encoding='utf-8')

print('CALLING_PATCH_APPLIED')
