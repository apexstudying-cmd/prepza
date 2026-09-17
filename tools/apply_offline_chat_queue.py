from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'frontend' / 'src' / 'crypto' / 'WhatsAppChatExperience.tsx'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'Offline chat queue patch anchor missing: {label}')
    if text.count(old) != 1:
        raise SystemExit(f'Offline chat queue patch anchor not unique: {label}')
    return text.replace(old, new, 1)


def main() -> None:
    text = TARGET.read_text(encoding='utf-8')
    text = replace_once(
        text,
        "import { provisionInitialGroupKey } from './groupProvisioning'\n",
        "import { provisionInitialGroupKey } from './groupProvisioning'\nimport { enqueueOfflineChatMessage, installOfflineChatQueue } from '../offline/chatOfflineQueue'\n",
        'imports',
    )

    text = replace_once(
        text,
        "installConversationObserver()\n",
        "installConversationObserver()\ninstallOfflineChatQueue()\n",
        'queue startup',
    )

    old_send = """    try { const token = await getCsrfToken(); await api(`/chats/${selectedId}/messages`, { method: 'POST', headers: { 'X-CSRF-Token': token }, body: JSON.stringify({ body: JSON.stringify(envelope), kind: 'text' }) }); setInput(''); setReplyingTo(null); const result = await api<{ messages: Message[] }>(`/chats/${selectedId}/messages`); setMessages(result.messages || []); void loadList() } catch (value) { setError(friendlyError(value, 'Could not send this message.')) } finally { setSending(false) }"""
    new_send = """    try {
      const token = await getCsrfToken()
      const body = JSON.stringify({ body: JSON.stringify(envelope), kind: 'text' })
      if (!navigator.onLine) {
        const queued = await enqueueOfflineChatMessage(`/chats/${selectedId}/messages`, body, token)
        if (!queued) throw new Error('Could not save this message for offline delivery.')
        setInput(''); setReplyingTo(null)
        setMessages(current => [...current, { id: -Date.now(), conversation_id: selectedId, sender_id: meIdRef.current || 0, body: JSON.stringify(envelope), nonce: null, is_deleted: false, created_at: new Date().toISOString(), edited_at: null, attachment: null, kind: 'text' }])
        setError('Message saved. It will send when your connection returns.')
      } else {
        await api(`/chats/${selectedId}/messages`, { method: 'POST', headers: { 'X-CSRF-Token': token }, body })
        setInput(''); setReplyingTo(null)
        const result = await api<{ messages: Message[] }>(`/chats/${selectedId}/messages`)
        setMessages(result.messages || []); void loadList()
      }
    } catch (value) { setError(friendlyError(value, 'Could not send this message.')) } finally { setSending(false) }"""
    text = replace_once(text, old_send, new_send, 'text send')

    # Reconcile queued messages as soon as the account reconnects while the chat is open.
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
    if 'prepza:offline-chat-synced' not in text:
        anchor = "  useEffect(() => { if (!visible || view !== 'detail' || selectedId == null) return\n"
        if anchor not in text:
            raise SystemExit('Offline chat queue: reconnect effect anchor missing')
        text = text.replace(anchor, reconnect_effect + anchor, 1)

    required = [
        "../offline/chatOfflineQueue",
        'installOfflineChatQueue()',
        'enqueueOfflineChatMessage',
        'Message saved. It will send when your connection returns.',
        'prepza:offline-chat-synced',
    ]
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise SystemExit('Offline chat queue verification failed: ' + ', '.join(missing))
    TARGET.write_text(text, encoding='utf-8')
    print('Offline chat text-message queue applied and verified.')


if __name__ == '__main__':
    main()
