from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'frontend' / 'src' / 'crypto' / 'WhatsAppChatExperience.tsx'


def main() -> None:
    text = TARGET.read_text(encoding='utf-8')

    # The chat source has evolved from the original one-line send() implementation.
    # Validate and complete the current implementation instead of requiring the old anchor.
    if "enqueueOfflineChatMessage" not in text:
        raise SystemExit('Offline chat queue: current text-send implementation is missing enqueueOfflineChatMessage')

    if "import { enqueueOfflineChatMessage } from '../offline/chatOfflineQueue'" in text:
        text = text.replace(
            "import { enqueueOfflineChatMessage } from '../offline/chatOfflineQueue'",
            "import { enqueueOfflineChatMessage, installOfflineChatQueue } from '../offline/chatOfflineQueue'",
            1,
        )
    elif "import { enqueueOfflineChatMessage, installOfflineChatQueue } from '../offline/chatOfflineQueue'" not in text:
        anchor = "import { provisionInitialGroupKey } from './groupProvisioning'\n"
        if anchor not in text:
            raise SystemExit('Offline chat queue: imports anchor missing')
        text = text.replace(
            anchor,
            anchor + "import { enqueueOfflineChatMessage, installOfflineChatQueue } from '../offline/chatOfflineQueue'\n",
            1,
        )

    if "installOfflineChatQueue()" not in text:
        anchor = "installConversationObserver()\n"
        if anchor not in text:
            raise SystemExit('Offline chat queue: observer startup anchor missing')
        text = text.replace(anchor, anchor + "installOfflineChatQueue()\n", 1)

    if 'prepza:offline-chat-synced' not in text:
        anchor = "  useEffect(() => { const onStatus = (event: Event) => setRealtimeConnected(Boolean((event as CustomEvent<{ connected?: boolean }>).detail?.connected)); window.addEventListener('prepza-realtime-status', onStatus); return () => window.removeEventListener('prepza-realtime-status', onStatus) }, [])\n"
        if anchor not in text:
            raise SystemExit('Offline chat queue: reconnect effect anchor missing')
        reconnect_effect = """  useEffect(() => {
    const onSynced = () => {
      if (!navigator.onLine || selectedId == null) return
      void api<{ messages: Message[] }>(`/chats/${selectedId}/messages`).then(result => setMessages(result.messages || [])).catch(() => {})
      void loadList()
    }
    window.addEventListener('prepza:offline-chat-synced', onSynced)
    return () => window.removeEventListener('prepza:offline-chat-synced', onSynced)
  }, [selectedId])

"""
        text = text.replace(anchor, anchor + reconnect_effect, 1)

    required = [
        "../offline/chatOfflineQueue",
        'installOfflineChatQueue()',
        'enqueueOfflineChatMessage',
        'prepza:offline-chat-synced',
    ]
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise SystemExit('Offline chat queue verification failed: ' + ', '.join(missing))

    TARGET.write_text(text, encoding='utf-8')
    print('Offline chat text-message queue applied and verified.')


if __name__ == '__main__':
    main()