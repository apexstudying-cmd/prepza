import { useEffect, useState } from 'react'

export default function OfflineStatusBanner() {
  const [online, setOnline] = useState(() => typeof navigator === 'undefined' ? true : navigator.onLine)
  const [reconnecting, setReconnecting] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const onOffline = () => { setOnline(false); setReconnecting(false); setSyncing(false); setVisible(true) }
    const onOnline = () => { setOnline(true); setReconnecting(true); setSyncing(false); setVisible(true) }
    const onSyncing = () => { setOnline(true); setReconnecting(false); setSyncing(true); setVisible(true) }
    const onSynced = () => { setOnline(true); setReconnecting(false); setSyncing(false); setVisible(true); window.setTimeout(() => setVisible(false), 1200) }
    window.addEventListener('offline', onOffline)
    window.addEventListener('online', onOnline)
    window.addEventListener('prepza:offline-queue-syncing', onSyncing as EventListener)
    window.addEventListener('prepza:offline-queue-synced', onSynced as EventListener)
    return () => {
      window.removeEventListener('offline', onOffline)
      window.removeEventListener('online', onOnline)
      window.removeEventListener('prepza:offline-queue-syncing', onSyncing as EventListener)
      window.removeEventListener('prepza:offline-queue-synced', onSynced as EventListener)
    }
  }, [])

  if (!visible) return null

  const label = !online
    ? 'Offline — saved study materials remain available'
    : reconnecting
      ? 'Connection restored — reconnecting…'
      : syncing
        ? 'Syncing your study activity…'
        : 'All caught up'

  return (
    <div role="status" aria-live="polite" style={{ position: 'fixed', top: 10, left: '50%', transform: 'translateX(-50%)', zIndex: 1000, maxWidth: 'calc(100% - 28px)', pointerEvents: 'none' }}>
      <div style={{ background: !online ? '#18212B' : '#20352A', color: '#fff', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 999, padding: '8px 13px', fontSize: 11, fontWeight: 700, boxShadow: '0 6px 24px rgba(0,0,0,0.18)', whiteSpace: 'nowrap' }}>
        {label}
      </div>
    </div>
  )
}
