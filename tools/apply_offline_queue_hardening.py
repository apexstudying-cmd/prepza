from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'
text = APP.read_text(encoding='utf-8')

MARKER = "const PREPZA_OFFLINE_QUEUE_STORE = 'syncQueue'"
if MARKER not in text:
    raise SystemExit('Offline queue hardening: queue foundation is missing.')

old_type = """type PrepzaOfflineQueueItem = {\n  id?: number\n  path: string\n  method: string\n  headers: Record<string, string>\n  body: string | null\n  createdAt: number\n  attempts: number\n  nextAttemptAt: number\n  lastError: string | null\n}"""
new_type = """type PrepzaOfflineQueueItem = {\n  id?: number\n  userId: number | null\n  dedupeKey: string\n  path: string\n  method: string\n  headers: Record<string, string>\n  body: string | null\n  createdAt: number\n  attempts: number\n  nextAttemptAt: number\n  lastError: string | null\n}"""
if old_type in text:
    text = text.replace(old_type, new_type, 1)
elif 'userId: number | null' not in text:
    raise SystemExit('Offline queue hardening: queue item type anchor missing.')

helper_anchor = "function prepzaOfflineQueueChanged(): void {"
helper = """function prepzaOfflineQueueUserId(): number | null {\n  try {\n    const raw = Number(localStorage.getItem('prepza-offline-user-id') || 0)\n    return Number.isInteger(raw) && raw > 0 ? raw : null\n  } catch { return null }\n}\n\nfunction prepzaOfflineQueueDedupeKey(userId: number | null, method: string, path: string, body: string | null): string {\n  return `${userId ?? 'unknown'}:${method}:${path}:${body ?? ''}`\n}\n\n"""
if 'function prepzaOfflineQueueUserId()' not in text:
    if helper_anchor not in text:
        raise SystemExit('Offline queue hardening: queue change helper anchor missing.')
    text = text.replace(helper_anchor, helper + helper_anchor, 1)

old_add = """    const id = await new Promise<number | null>((resolve) => {\n      const tx = db.transaction(PREPZA_OFFLINE_QUEUE_STORE, 'readwrite')\n      const request = tx.objectStore(PREPZA_OFFLINE_QUEUE_STORE).add({\n        path,\n        method,\n        headers,\n        body,\n        createdAt: Date.now(),\n        attempts: 0,\n        nextAttemptAt: Date.now(),\n        lastError: null,\n      } satisfies PrepzaOfflineQueueItem)\n      request.onsuccess = () => resolve(Number(request.result))\n      request.onerror = () => resolve(null)\n      tx.onerror = () => resolve(null)\n      tx.onabort = () => resolve(null)\n    })"""
new_add = """    const userId = prepzaOfflineQueueUserId()\n    const dedupeKey = prepzaOfflineQueueDedupeKey(userId, method, path, body)\n    const id = await new Promise<number | null>((resolve) => {\n      const tx = db.transaction(PREPZA_OFFLINE_QUEUE_STORE, 'readwrite')\n      const store = tx.objectStore(PREPZA_OFFLINE_QUEUE_STORE)\n      const all = store.getAll()\n      all.onsuccess = () => {\n        const existing = (all.result || []).find((row: PrepzaOfflineQueueItem) => row.dedupeKey === dedupeKey && row.userId === userId) as PrepzaOfflineQueueItem | undefined\n        const record: PrepzaOfflineQueueItem = {\n          ...(existing || {}),\n          userId,\n          dedupeKey,\n          path,\n          method,\n          headers,\n          body,\n          createdAt: existing?.createdAt || Date.now(),\n          attempts: existing?.attempts || 0,\n          nextAttemptAt: Date.now(),\n          lastError: null,\n        }\n        const request = existing?.id != null ? store.put(record) : store.add(record)\n        request.onsuccess = () => resolve(Number(request.result ?? existing?.id))\n        request.onerror = () => resolve(null)\n      }\n      all.onerror = () => resolve(null)\n      tx.onerror = () => resolve(null)\n      tx.onabort = () => resolve(null)\n    })"""
if old_add in text:
    text = text.replace(old_add, new_add, 1)
elif 'prepzaOfflineQueueDedupeKey(userId' not in text:
    raise SystemExit('Offline queue hardening: enqueue anchor missing.')

old_loop = """      for (const item of items) {\n        if (!navigator.onLine) break\n        const headers = { ...item.headers }\n        const res = await fetch(item.path, {"""
new_loop = """      let currentUserId: number | null = prepzaOfflineQueueUserId()\n      let freshCsrf = ''\n      try {\n        const meRes = await fetch('/me', { credentials: 'include', cache: 'no-store' })\n        if (meRes.ok) {\n          const me = await meRes.json()\n          const resolved = Number(me?.id)\n          currentUserId = Number.isInteger(resolved) && resolved > 0 ? resolved : currentUserId\n          freshCsrf = String(me?.csrf_token || '')\n        }\n      } catch {}\n\n      for (const item of items) {\n        if (!navigator.onLine) break\n        // Never replay one account's durable mutation into another account.\n        if (item.userId != null && currentUserId != null && item.userId !== currentUserId) {\n          await deletePrepzaOfflineQueueItem(item.id as number)\n          continue\n        }\n        const headers = { ...item.headers }\n        if (freshCsrf && Object.keys(headers).some(key => key.toLowerCase() === 'x-csrf-token')) {\n          const csrfHeader = Object.keys(headers).find(key => key.toLowerCase() === 'x-csrf-token') as string\n          headers[csrfHeader] = freshCsrf\n        }\n        const res = await fetch(item.path, {"""
if old_loop in text:
    text = text.replace(old_loop, new_loop, 1)
elif 'freshCsrf' not in text:
    raise SystemExit('Offline queue hardening: replay loop anchor missing.')

flush_start = """  prepzaOfflineQueueFlushPromise = (async () => {\n    try {"""
flush_replacement = """  prepzaOfflineQueueFlushPromise = (async () => {\n    try {\n      try { window.dispatchEvent(new CustomEvent('prepza:offline-queue-syncing')) } catch {}"""
if flush_start in text and 'prepza:offline-queue-syncing' not in text:
    text = text.replace(flush_start, flush_replacement, 1)

flush_end = """    } finally {\n      prepzaOfflineQueueFlushPromise = null\n    }\n  })()"""
flush_end_replacement = """    } finally {\n      try { window.dispatchEvent(new CustomEvent('prepza:offline-queue-synced')) } catch {}\n      prepzaOfflineQueueFlushPromise = null\n    }\n  })()"""
if flush_end in text and 'prepza:offline-queue-synced' not in text:
    text = text.replace(flush_end, flush_end_replacement, 1)

required = ['userId: number | null', 'dedupeKey: string', 'prepzaOfflineQueueDedupeKey', 'freshCsrf', 'Never replay one account', 'prepza:offline-queue-syncing', 'prepza:offline-queue-synced']
missing = [x for x in required if x not in text]
if missing:
    raise SystemExit('Offline queue hardening verification failed: ' + ', '.join(missing))
APP.write_text(text, encoding='utf-8')
print('Offline mutation queue hardening and sync lifecycle applied and verified.')
