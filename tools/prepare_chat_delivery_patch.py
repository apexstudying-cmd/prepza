from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CHAT = ROOT / 'frontend' / 'src' / 'crypto' / 'WhatsAppChatExperience.tsx'
s = CHAT.read_text(encoding='utf-8')

# apply_chat_voice_notes.py rewrites loadList before the delivery patch runs.
# Normalize only that temporary rewrite back to the stable original anchor so
# apply_chat_delivery_receipts.py can install the complete receipt-aware list.
if 'const baseChats = Array.isArray(result.chats)' in s and 'PREPZA_CHAT_DELIVERY_RECEIPTS' not in s:
    pattern = re.compile(r"  const loadList = async \(\) => \{.*?\n  useEffect\(\(\) => \{ if \(!visible\) return; void loadList\(\);", re.S)
    match = pattern.search(s)
    if not match:
        raise SystemExit('chat delivery order: voice loadList rewrite not found')
    original = "  const loadList = async () => { setListError(''); try { const result = await api<{ chats: ChatSummary[] }>('/chats'); setChats(Array.isArray(result.chats) ? result.chats : []) } catch (value) { setListError(friendlyError(value, 'Could not load your conversations.')) } }\n  useEffect(() => { if (!visible) return; void loadList();"
    s = s[:match.start()] + original + s[match.end():]
    CHAT.write_text(s, encoding='utf-8')
    print('CHAT_DELIVERY_PATCH_ORDER_PREPARED')
else:
    print('CHAT_DELIVERY_PATCH_ORDER_NOT_NEEDED')