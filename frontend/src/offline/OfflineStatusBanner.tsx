import { useEffect, useState } from 'react'
import { getOfflineStudySnapshot } from './studyActivity'

type State = 'online' | 'offline' | 'reconnecting' | 'caught-up'

export default function OfflineStatusBanner() {
  const [state, setState] = useState<State>(() => (typeof navigator !== 'undefined' && navigator.onLine ? 'online' : 'offline'))
  const [studySeconds, setStudySeconds] = useState(0)

  useEffect(() => {
    let reconnectTimer: number | undefined
    const refresh = () => {
      try { setStudySeconds(getOfflineStudySnapshot().todaySeconds) } catch (_) {}
    }
    const onOffline = () => { window.clearTimeout(reconnectTimer); setState('offline'); refresh() }
    const onOnline = () => {
      setState('reconnecting')
      window.clearTimeout(reconnectTimer)
      reconnectTimer = window.setTimeout(() => setState('caught-up'), 1200)
      refresh()
    }
    const onActivity = () => refresh()
    window.addEventListener('offline', onOffline)
    window.addEventListener('online', onOnline)
    window.addEventListener('prepza:offline-study-activity-changed', onActivity)
    refresh()
    return () => {
      window.clearTimeout(reconnectTimer)
      window.removeEventListener('offline', onOffline)
      window.removeEventListener('online', onOnline)
      window.removeEventListener('prepza:offline-study-activity-changed', onActivity)
    }
  }, [])

  if (state === 'online') return null

  const label = state === 'offline' ? 'Offline — saved study materials remain available' : state === 'reconnecting' ? 'Reconnecting — syncing your study activity…' : 'All caught up'
  const minutes = Math.floor(studySeconds / 60)
  const seconds = studySeconds % 60

  return (
    <div style={{ position: 'fixed', left: 12, right: 12, bottom: 12, zIndex: 10000, borderRadius: 14, padding: '10px 13px', background: state === 'offline' ? '#172033' : '#10261d', border: '1px solid rgba(255,255,255,0.12)', color: '#fff', boxShadow: '0 8px 30px rgba(0,0,0,0.25)', fontSize: 12, fontWeight: 700 }} role="status" aria-live="polite">
      <div>{label}</div>
      {state === 'offline' && studySeconds > 0 && <div style={{ marginTop: 3, opacity: 0.72, fontWeight: 500 }}>Offline study today: {minutes}m {String(seconds).padStart(2, '0')}s</div>}
    </div>
  )
}
