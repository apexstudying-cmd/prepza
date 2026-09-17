from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CHAT = ROOT / 'frontend' / 'src' / 'crypto' / 'WhatsAppChatExperience.tsx'
MARK = 'PREPZA_GROUP_CREATION_READINESS'

s = CHAT.read_text(encoding='utf-8')
if MARK in s:
    print(f'{MARK}_ALREADY_PRESENT')
else:
    pattern = re.compile(r"      const memberIds = \[creatorId, \.\.\.groupSelected\.map\(user => user\.id\)\]\n      const memberKeys = await Promise\.all\(memberIds\.map\(async id => \(\{ userId: id, publicKey: await fetchUserPublicKey\(id\) \}\)\)\)")
    replacement = '''      const memberIds = [creatorId, ...groupSelected.map(user => user.id)]
      const keyResults = await Promise.all(memberIds.map(async id => {
        try {
          return { id, publicKey: await fetchUserPublicKey(id) }
        } catch {
          return { id, publicKey: null as string | null }
        }
      }))
      const missing = keyResults.filter(item => !item.publicKey).map(item => groupSelected.find(user => user.id === item.id)?.display_name || 'A selected student')
      if (missing.length) {
        throw new Error(`Secure chat setup is incomplete for: ${missing.join(', ')}. Each selected student must open Chats once before joining an encrypted group.`)
      }
      const memberKeys = keyResults.map(item => ({ userId: item.id, publicKey: item.publicKey as string }))'''
    if not pattern.search(s):
        raise SystemExit('group creation readiness: member key anchor missing')
    s = pattern.sub(replacement, s, count=1)
    s = s.replace('type ChatSummary = {', f'// {MARK}\ntype ChatSummary = {{', 1)
    CHAT.write_text(s, encoding='utf-8')
    print(f'{MARK}_APPLIED')
