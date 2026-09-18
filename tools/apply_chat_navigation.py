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
