from pathlib import Path
TARGET = Path(__file__).resolve().parents[1] / "frontend/src/crypto/CallExperience.tsx"

def main():
    text = TARGET.read_text(encoding="utf-8")

    marker = """if (event.type === 'call:incoming') {"""
    history = """if (event.type === 'call:incoming') {
        window.dispatchEvent(new CustomEvent('prepza-call-history', { detail: { id: event.call_id, peerId: event.from_user_id, peerName: event.from_name || 'Student', kind: event.kind, direction: 'missed', at: new Date().toISOString(), conversationId: event.conversation_id } }))"""
    if "direction: 'missed'" not in text:
        if marker not in text:
            raise SystemExit("CALL_HISTORY_FAILED: incoming handler missing")
        text = text.replace(marker, history, 1)

    old2 = """setIncoming(null)
      if (incomingTimeoutRef.current)"""
    new2 = """window.dispatchEvent(new CustomEvent('prepza-call-history', { detail: { id: event.call_id, peerId: event.from_user_id, peerName: event.from_name || 'Student', kind: event.kind, direction: 'incoming', at: new Date().toISOString(), conversationId: event.conversation_id } }))
      setIncoming(null)
      if (incomingTimeoutRef.current)"""
    if "direction: 'incoming'" not in text:
        if old2 not in text:
            raise SystemExit("CALL_HISTORY_FAILED: accept handler anchor missing")
        text = text.replace(old2, new2, 1)

    TARGET.write_text(text, encoding="utf-8")
    print("CALL_HISTORY_APPLIED")

if __name__ == "__main__":
    main()
