import { setOfflineUserId, clearOfflineUserId } from './generatedMaterials'
import { installOfflineChatQueue } from './chatOfflineQueue'
import { setOfflineStudyUserId, syncOfflineStudyActivity } from './studyActivity'

let started = false

/**
 * Small, failure-isolated offline bootstrap. It never blocks React startup.
 * Once the authenticated account is known, local offline state is scoped to
 * that account and pending study-time is reconciled whenever connectivity is
 * available again.
 */
export function installOfflineBootstrap(): void {
  if (started || typeof window === 'undefined') return
  started = true
  // Chat queue has its own retry/locking guard and is safe to start here.
  // This makes the persisted outgoing queue active after a cold restart.
  installOfflineChatQueue()

  const isolateAccount = async (userId: number) => {
    try {
      const previous = Number(localStorage.getItem('prepza-offline-last-auth-user') || 0)
      if (previous > 0 && previous !== userId) {
        try { indexedDB.deleteDatabase('prepza-offline-v2') } catch (_) {}
        try { indexedDB.deleteDatabase('prepza-offline-v1') } catch (_) {}
        try { indexedDB.deleteDatabase('prepza-offline-study-v1') } catch (_) {}
        try { indexedDB.deleteDatabase('prepza-offline-chat-v1') } catch (_) {}
        try { await caches.delete('prepza-study-assets-v1') } catch (_) {}
        try { await caches.delete('prepza-generated-audio-v1') } catch (_) {}
        try { localStorage.removeItem('prepza-offline-user-id') } catch (_) {}
      }
      localStorage.setItem('prepza-offline-last-auth-user', String(userId))
    } catch (_) {}
  }

  const reconcile = async () => {
    if (!navigator.onLine) return
    try {
      const response = await fetch('/me', { credentials: 'include', cache: 'no-store' })
      if (!response.ok) {
        // A confirmed unauthenticated session must never keep exposing the
        // previous account's offline namespace. The actual cached bytes stay
        // intact but become inaccessible until a new authenticated /me sets
        // a fresh account id.
        if (response.status === 401 || response.status === 403) clearOfflineUserId()
        return
      }
      const me = await response.json()
      const userId = Number(me?.id)
      if (!Number.isInteger(userId) || userId <= 0) return
      await isolateAccount(userId)
      setOfflineUserId(userId)
      setOfflineStudyUserId(userId)
      await syncOfflineStudyActivity(me?.csrf_token)
    } catch (_) {}
  }

  window.addEventListener('online', () => { void reconcile() })
  window.addEventListener('focus', () => { void reconcile() })
  void reconcile()
}
