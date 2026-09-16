from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / 'frontend' / 'src' / 'offline' / 'bootstrap.ts'
text = BOOTSTRAP.read_text(encoding='utf-8')

if 'prepza-offline-last-auth-user' in text:
    print('Offline account isolation already applied.')
    raise SystemExit(0)

anchor = "  const reconcile = async () => {\n"
if anchor not in text:
    raise SystemExit('Offline account isolation: reconcile anchor missing')

helper = """  const isolateAccount = async (userId: number) => {
    try {
      const previous = Number(localStorage.getItem('prepza-offline-last-auth-user') || 0)
      if (previous > 0 && previous !== userId) {
        // A browser profile can be reused by another Prepza account. Remove the
        // previous account's local study DB and cached assets before binding the
        // new account, preventing cross-account offline data exposure.
        try { indexedDB.deleteDatabase('prepza-offline-v2') } catch (_) {}
        try { await caches.delete('prepza-study-assets-v1') } catch (_) {}
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
BOOTSTRAP.write_text(text, encoding='utf-8')
print('Offline account isolation applied and verified.')
