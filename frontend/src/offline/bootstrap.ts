import { setOfflineUserId } from './generatedMaterials'
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

  const reconcile = async () => {
    if (!navigator.onLine) return
    try {
      const response = await fetch('/me', { credentials: 'include', cache: 'no-store' })
      if (!response.ok) return
      const me = await response.json()
      const userId = Number(me?.id)
      if (!Number.isInteger(userId) || userId <= 0) return
      setOfflineUserId(userId)
      setOfflineStudyUserId(userId)
      await syncOfflineStudyActivity(me?.csrf_token)
    } catch (_) {}
  }

  window.addEventListener('online', () => { void reconcile() })
  window.addEventListener('focus', () => { void reconcile() })
  void reconcile()
}
