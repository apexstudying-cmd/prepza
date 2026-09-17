from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
chat = (ROOT / 'frontend/src/crypto/WhatsAppChatExperience.tsx').read_text()
call = (ROOT / 'frontend/src/crypto/CallExperience.tsx').read_text()
signal = (ROOT / 'frontend/src/crypto/callRealtime.ts').read_text()
server = (ROOT / 'realtime_server.py').read_text()
package = (ROOT / 'frontend/package.json').read_text()

required = {
    'chat imports call overlay': "import CallExperience from './CallExperience'" in chat,
    'chat exposes voice button': 'prepza-start-call' in chat and 'Start voice call' in chat,
    'chat exposes video button': 'Start video call' in chat,
    'chat mounts call overlay': '<CallExperience userId={meId}' in chat,
    'frontend invite signaling': "emitCall('call:invite'" in call,
    'frontend offer signaling': "emitCall('call:offer'" in call,
    'frontend answer signaling': "emitCall('call:answer'" in call,
    'frontend ICE signaling': "emitCall('call:ice'" in call,
    'frontend receives incoming': "call:incoming" in signal,
    'frontend receives offer': "call:offer" in signal,
    'backend invite handler': '@socketio.on("call:invite")' in server,
    'backend accept handler': '@socketio.on("call:accept")' in server,
    'backend offer handler': '@socketio.on("call:offer")' in server,
    'backend answer handler': '@socketio.on("call:answer")' in server,
    'backend ICE handler': '@socketio.on("call:ice")' in server,
    'backend membership authorization': 'call_participants(conversation_id)' in server and 'set(participants) != {caller_id, target_id}' in server,
    'backend active-call state': '_active_calls = {}' in server,
    'offline call guard': 'Calls require an internet connection.' in call,
    'calling build patch': 'apply_calling.py' in package and 'fix_calling_runtime.py' in package,
}
failed = [name for name, ok in required.items() if not ok]
if failed:
    raise SystemExit('Calling architecture audit failed: ' + ', '.join(failed))
print('Calling architecture regression audit passed.')
