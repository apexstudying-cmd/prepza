from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "frontend/src/crypto/WhatsAppChatExperience.tsx"
ADA_TARGET = ROOT / "frontend/src/crypto/inChatAdaEnhancer.tsx"

def once(text, old, new, label):
    if old not in text:
        raise SystemExit("CHAT_NAV_FAILED: missing " + label)
    return text.replace(old, new, 1)

def main():
    text = TARGET.read_text(encoding="utf-8")
    text = once(text, "import { provisionInitialGroupKey } from './groupProvisioning'",
                 "import { provisionInitialGroupKey } from './groupProvisioning'\nimport CommunicationsNavigation from './CommunicationsNavigation'",
                 "navigation import")

    text = once(text,
        "if (!visible || view !== 'detail' || selectedId == null || !csrfToken) return",
        "if (!visible || view !== 'detail' || selectedId == null || !csrfToken || localStorage.getItem('prepza-chat-read-receipts') === 'off') return",
        "read receipt setting")

    anchor = '<div title="End-to-end encrypted" style={{ fontSize:10,opacity:.65 }}>E2EE</div>'
    controls = """<div title="End-to-end encrypted" style={{ fontSize:10,opacity:.65 }}>E2EE</div>{!isGroup && detail && (() => { const peer = detail.participants.find(item => item.user_id !== meId); return peer ? <><button type="button" onClick={() => { window.dispatchEvent(new CustomEvent('prepza-call-history', { detail:{ id:String(Date.now()),peerId:peer.user_id,peerName:peer.display_name,kind:'voice',direction:'outgoing',at:new Date().toISOString(),conversationId:detail.id } })); window.dispatchEvent(new CustomEvent('prepza-start-call',{detail:{conversationId:detail.id,peerId:peer.user_id,peerName:peer.display_name,kind:'voice'}})) }} aria-label="Start voice call" style={{ width:34,height:34,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer' }}>C</button><button type="button" onClick={() => { window.dispatchEvent(new CustomEvent('prepza-call-history', { detail:{ id:String(Date.now()),peerId:peer.user_id,peerName:peer.display_name,kind:'video',direction:'outgoing',at:new Date().toISOString(),conversationId:detail.id } })); window.dispatchEvent(new CustomEvent('prepza-start-call',{detail:{conversationId:detail.id,peerId:peer.user_id,peerName:peer.display_name,kind:'video'}})) }} aria-label="Start video call" style={{ width:34,height:34,border:0,borderRadius:10,background:'rgba(255,255,255,.1)',color:'#fff',cursor:'pointer' }}>V</button></> : null })()}"""
    text = once(text, anchor, controls, "E2EE header anchor")

    text = once(text,
        '<button type="button" onClick={() => setMessageSearchOpen(v => !v)} aria-label="Search messages"',
        '<button type="button" onClick={() => window.dispatchEvent(new CustomEvent("prepza-open-chat-info"))} aria-label="Chat info" style={{ width:34,height:34,border:0,borderRadius:10,background:"rgba(255,255,255,.1)",color:"#fff",cursor:"pointer" }}>i</button><button type="button" onClick={() => setMessageSearchOpen(v => !v)} aria-label="Search messages"',
        "chat info button")

    text = once(text,
        '<div style={{ flex:1,fontWeight:850,fontSize:18 }}>Chats</div>',
        '<div style={{ flex:1,fontWeight:850,fontSize:18 }}>Chats</div><button type="button" onClick={() => window.dispatchEvent(new CustomEvent("prepza-open-calls"))} aria-label="Calls" style={{ border:0,borderRadius:10,padding:"7px 9px",background:"rgba(255,255,255,.1)",color:"#fff",fontWeight:800 }}>Calls</button><button type="button" onClick={() => window.dispatchEvent(new CustomEvent("prepza-open-chat-settings"))} aria-label="Chat settings" style={{ border:0,borderRadius:10,padding:"7px 9px",background:"rgba(255,255,255,.1)",color:"#fff",fontWeight:800 }}>Settings</button>',
        "sidebar navigation buttons")

    text = once(text,
        '<aside className="prepza-wa-list">',
        '<CommunicationsNavigation conversationId={selectedId} detail={detail} messages={messages} onOpenChat={chooseChat} /><aside className="prepza-wa-list">',
        "navigation mount")

    text = once(text,
        "{message.attachment.view_url && isImage(message.attachment.file_type) ? <img",
        "{localStorage.getItem('prepza-chat-media-visibility') !== 'off' && message.attachment.view_url && isImage(message.attachment.file_type) ? <img",
        "media visibility")

    text = once(text,
        'placeholder="Message…" disabled={sending || uploading} rows={1}',
        'placeholder="Message…" data-prepza-chat-composer="true" disabled={sending || uploading} rows={1}',
        "composer marker")

    TARGET.write_text(text, encoding="utf-8")
    ada = ADA_TARGET.read_text(encoding="utf-8")
    ada = ada.replace("document.querySelector('input[placeholder=\"Message…\"]') as HTMLInputElement | null",
                      "document.querySelector('[data-prepza-chat-composer=\"true\"]') as HTMLTextAreaElement | null")
    ADA_TARGET.write_text(ada, encoding="utf-8")
    print("CHAT_NAVIGATION_APPLIED")
    print("CALLS_SECTION_READY")
    print("CHAT_SETTINGS_READY")
    print("MEDIA_AND_GROUP_INFO_READY")
    print("ADA_MENTION_ONLY_READY")

if __name__ == "__main__":
    main()
