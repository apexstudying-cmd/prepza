from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / 'frontend' / 'src' / 'offline' / 'bootstrap.ts'
text = BOOTSTRAP.read_text(encoding='utf-8')

if 'prepza-offline-last-auth-user' not in text:
    anchor = "  const reconcile = async () => {\n"
    if anchor not in text:
        raise SystemExit('Offline account isolation: reconcile anchor missing')

    helper = """  const isolateAccount = async (userId: number) => {
    try {
      const previous = Number(localStorage.getItem('prepza-offline-last-auth-user') || 0)
      if (previous > 0 && previous !== userId) {
        try { indexedDB.deleteDatabase('prepza-offline-v2') } catch (_) {}
        try { indexedDB.deleteDatabase('prepza-offline-v1') } catch (_) {}
        try { await caches.delete('prepza-study-assets-v1') } catch (_) {}
        try { await caches.delete('prepza-generated-audio-v1') } catch (_) {}
        try { localStorage.removeItem('prepza-offline-user-id') } catch (_) {}
      }
      localStorage.setItem('prepza-offline-last-auth-user', String(userId))
    } catch (_) {}
  }

"""
    text = text.replace(anchor, helper + anchor, 1)
    needle = "      setOfflineUserId(userId)\n      setOfflineStudyUserId(userId)\n"
    replacement = "      await isolateAccount(userId)\n      setOfflineUserId(userId)\n      setOfflineStudyUserId(userId)\n"
    if needle not in text:
        raise SystemExit('Offline account isolation: user binding anchor missing')
    text = text.replace(needle, replacement, 1)
else:
    old = "try { indexedDB.deleteDatabase('prepza-offline-v2') } catch (_) {}"
    if "indexedDB.deleteDatabase('prepza-offline-v1')" not in text:
        new = old + "\n        try { indexedDB.deleteDatabase('prepza-offline-v1') } catch (_) {}"
        if old not in text:
            raise SystemExit('Offline account isolation: existing DB cleanup anchor missing')
        text = text.replace(old, new, 1)
    if "caches.delete('prepza-generated-audio-v1')" not in text:
        cache_anchor = "        try { await caches.delete('prepza-study-assets-v1') } catch (_) {}\n"
        if cache_anchor not in text:
            raise SystemExit('Offline account isolation: study asset cache cleanup anchor missing')
        text = text.replace(cache_anchor, cache_anchor + "        try { await caches.delete('prepza-generated-audio-v1') } catch (_) {}\n", 1)

required = [
    'prepza-offline-last-auth-user',
    "indexedDB.deleteDatabase('prepza-offline-v2')",
    "indexedDB.deleteDatabase('prepza-offline-v1')",
    "caches.delete('prepza-study-assets-v1')",
    "caches.delete('prepza-generated-audio-v1')",
]
missing = [x for x in required if x not in text]
if missing:
    raise SystemExit('Offline account isolation verification failed: ' + ', '.join(missing))
BOOTSTRAP.write_text(text, encoding='utf-8')
print('Offline account isolation applied and verified.')
