from pathlib import Path

p = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'crypto' / 'CallExperience.tsx'
s = p.read_text()

# Keep the active call in a ref as well as React state. Socket listeners are
# intentionally installed once per userId, so they must not close over stale
# call state while an incoming/outgoing call is being established.
if 'const callRef = useRef<ActiveCall | null>(null)' not in s:
    s = s.replace("  const [cameraOff, setCameraOff] = useState(false)\n", "  const [cameraOff, setCameraOff] = useState(false)\n  const callRef = useRef<ActiveCall | null>(null)\n", 1)
if "useEffect(() => { callRef.current = call }, [call])" not in s:
    s = s.replace("  useEffect(() => {\n    if (!userId) return\n", "  useEffect(() => { callRef.current = call }, [call])\n\n  useEffect(() => {\n    if (!userId) return\n", 1)

# The caller must create its offer only after the callee accepts. The previous
# patch only wired this when callRef was absent, which made the transformation
# silently skip the offer function on already-patched files.
if 'async function createCallerOffer(' not in s:
    needle = "  async function acceptOffer(event: CallSignal) {"
    offer_fn = """  async function createCallerOffer(active: ActiveCall) {
    if (!peer.current) return
    const offer = await peer.current.createOffer()
    await peer.current.setLocalDescription(offer)
    emitCall('call:offer', { call_id: active.callId, conversation_id: active.conversationId, to_user_id: active.peerId, payload: offer })
  }\n\n"""
    s = s.replace(needle, offer_fn + needle, 1)

# Never let the socket callback depend on stale React state.
s = s.replace(
    "if (event.type === 'call:accepted' && call) setCall({ ...call, connected: true })",
    "if (event.type === 'call:accepted' && callRef.current) void createCallerOffer(callRef.current)",
)
s = s.replace(
    "if (!peer.current || !call) return",
    "if (!peer.current || !callRef.current) return",
)
s = s.replace("const current = call\n", "const current = callRef.current\n")

# Keep the ref synchronized immediately when a call becomes active, rather
# than waiting for the next React effect turn.
s = s.replace("setCall(active)\n      emitCall('call:invite'", "setCall(active); callRef.current = active\n      emitCall('call:invite'", 1)
s = s.replace("setCall(active); setIncoming(null)\n      emitCall('call:accept'", "setCall(active); callRef.current = active; setIncoming(null)\n      emitCall('call:accept'", 1)
s = s.replace("setCall(null); setIncoming(null);", "callRef.current = null; setCall(null); setIncoming(null);")

# Socket.IO unsubscribe returns a boolean; React effect cleanup must return
# void. Make this transformation idempotent for already-fixed files.
s = s.replace("    return onCallSignal(event => {", "    const unsubscribe = onCallSignal(event => {", 1)
if "return () => { unsubscribe() }\n  }, [userId])" not in s:
    s = s.replace("    })\n  }, [userId])", "    })\n    return () => { unsubscribe() }\n  }, [userId])", 1)

# Calls require a live network and are deliberately not queued offline.
if "Calls require an internet connection." not in s:
    s = s.replace(
        "  async function startCall(conversationId: number, peerId: number, peerName: string, kind: 'voice' | 'video') {\n    if (call || !userId) return\n",
        "  async function startCall(conversationId: number, peerId: number, peerName: string, kind: 'voice' | 'video') {\n    if (call || !userId) return\n    if (!navigator.onLine) { window.dispatchEvent(new CustomEvent('prepza-call-error', { detail: 'Calls require an internet connection.' })); return }\n",
        1,
    )
    s = s.replace(
        "  async function acceptIncoming() {\n    if (!incoming || !userId) return\n",
        "  async function acceptIncoming() {\n    if (!incoming || !userId) return\n    if (!navigator.onLine) { window.dispatchEvent(new CustomEvent('prepza-call-error', { detail: 'Calls require an internet connection.' })); return }\n",
        1,
    )

p.write_text(s)
print('CALLING_RUNTIME_FIXED')
