from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / 'frontend' / 'src' / 'crypto'

# Wire the call overlay into the existing authenticated chat experience.
chat = FRONT / 'WhatsAppChatExperience.tsx'
s = chat.read_text()
if "./CallExperience" not in s:
    s = s.replace("import { provisionInitialGroupKey } from './groupProvisioning'", "import { provisionInitialGroupKey } from './groupProvisioning'\nimport CallExperience from './CallExperience'")
marker = '<div className="prepza-wa-head">'
if marker in s and 'prepza-call-actions' not in s:
    injection = """<div className=\"prepza-call-actions\" style={{ marginLeft:'auto',display:'flex',gap:7 }}>
      {view === 'detail' && detail && !detail.is_group && (() => { const peer = detail.participants.find(item => item.user_id !== meId); return peer ? <><button type=\"button\" aria-label=\"Start voice call\" title=\"Voice call\" onClick={() => window.dispatchEvent(new CustomEvent('prepza-start-call',{detail:{conversationId:detail.id,peerId:peer.user_id,peerName:peer.display_name,kind:'voice'}}))} style={{width:36,height:36,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer'}}>☎</button><button type=\"button\" aria-label=\"Start video call\" title=\"Video call\" onClick={() => window.dispatchEvent(new CustomEvent('prepza-start-call',{detail:{conversationId:detail.id,peerId:peer.user_id,peerName:peer.display_name,kind:'video'}}))} style={{width:36,height:36,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer'}}>▣</button></> : null })()}
    </div>"""
    s = s.replace(marker, marker + injection, 1)
# Render the overlay after the main chat shell so it can cover the whole viewport.
if '<CallExperience userId={meId}' not in s:
    s = s.replace('</div>\n  </div>\n}', '</div>\n    <CallExperience userId={meId} />\n  </div>\n}', 1)
chat.write_text(s)

# Add authenticated, membership-checked signaling to the existing Socket.IO server.
server = ROOT / 'realtime_server.py'
s = server.read_text()
if '_active_calls = {}' not in s:
    s = s.replace('_socket_state_lock = Lock()', '_socket_state_lock = Lock()\n_active_calls = {}\n_active_calls_lock = Lock()')
    s = s.replace('from app import app, db, Conversation, ConversationParticipant', 'from app import app, db, Conversation, ConversationParticipant, User')
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
    s = s.replace('\n@socketio.on("disconnect")', helper + '\n\n@socketio.on("disconnect")')
server.write_text(s)

print('CALLING_PATCH_APPLIED')
