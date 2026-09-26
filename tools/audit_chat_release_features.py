"""Fail the production build if chat voice/calling release wiring is absent."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAT = ROOT / "frontend" / "src" / "crypto" / "WhatsAppChatExperience.tsx"
SERVER = ROOT / "realtime_server.py"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"Chat release audit: missing {label}: {needle}")


chat = CHAT.read_text(encoding="utf-8")
server = SERVER.read_text(encoding="utf-8")

for needle, label in [
    ("function isAudio(", "audio attachment detection"),
    ("recordingVoice", "voice recording state"),
    ("startVoiceRecording", "voice recording handler"),
    ('aria-label=\"Record voice note\"', "voice-note button"),
    ("recordingVoice ? <span", "recording UI") if "recordingVoice ? <span" in chat or "recordingVoice ?<span" in chat or "recordingVoice &&" in chat else ("__missing_recording_ui__", "recording UI"),
    ('<audio controls', "voice-note playback"),
    ("Voice message" if "Voice message" in chat else "<audio controls", "voice-message chat preview"),
    ("CallExperience from './CallExperience'", "call experience import"),
    ('className=\"prepza-call-actions\"', "call action container"),
    ('aria-label=\"Start voice call\"', "voice-call button"),
    ('aria-label=\"Start video call\"', "video-call button"),
    ('<CallExperience userId={meId} />', "call experience mount"),
]:
    require(chat, needle, label)

for needle, label in [
    ('@socketio.on("call:invite")', "call invite signaling"),
    ('@socketio.on("call:accept")', "call accept signaling"),
    ('@socketio.on("call:offer")', "call offer signaling"),
    ('@socketio.on("call:answer")', "call answer signaling"),
    ('@socketio.on("call:ice")', "call ICE signaling"),
    ('@socketio.on("call:end")', "call end signaling"),
]:
    require(server, needle, label)

print("Chat release feature audit: OK")
