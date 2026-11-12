import { useEffect, useState } from 'react'
import { api, ApiError } from '../../lib/appApi'
import { N } from '../../theme/theme'

export default function SplashScreen({ setScreen, brandline }: { setScreen: (s: 'home' | 'complete-profile' | 'login') => void; brandline: string }) {
  // Restores an existing backend session (cookie lasts 7 days) instead of
  // always dropping the user back to the login screen on every app open.
  // Keeps the branded 2.2s splash beat either way.
  //
  // IMPORTANT: only a confirmed 401 from /me means "not logged in". Any
  // other failure (network blip, the service worker's offline fallback,
  // a timeout while the connection re-establishes - all common right
  // after a PWA refresh on mobile) does NOT mean the session is gone;
  // treating it as a logout was sending people back to the login screen
  // while their cookie was still perfectly valid. So: retry once on a
  // non-401 failure, and if it still fails, offer a manual retry instead
  // of silently signing the user out.
  const [state, setState] = useState<'checking' | 'retry'>('checking')

  const checkSession = async (attempt = 0): Promise<void> => {
    setState('checking')
    try {
      const me = await api<{ university_id: number | null; program_id: number | null; year: number | null; semester: number | null }>('/me')
      setScreen(me.university_id && me.program_id && me.year && me.semester ? 'home' : 'complete-profile')
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setScreen('login')
        return
      }
      if (attempt === 0) {
        setTimeout(() => checkSession(1), 1200)
      } else {
        setState('retry')
      }
    }
  }

  useEffect(() => {
    let cancelled = false
    const t = setTimeout(() => { if (!cancelled) checkSession(0) }, 2200)
    return () => { cancelled = true; clearTimeout(t) }
  }, [])

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: `linear-gradient(160deg, ${N.navy} 0%, ${N.navy2} 60%, ${N.navy3} 100%)` }}>
      <div style={{ position: 'absolute', top: '18%', width: 220, height: 220, background: 'rgba(201,168,76,0.06)', borderRadius: '50%', filter: 'blur(50px)' }} />
      <img src="/icon-192.png" alt="Prepza" width={192} height={192} style={{ width: 192, height: 192, borderRadius: 42, marginBottom: 24, boxShadow: '0 18px 60px rgba(201,168,76,0.3)' }} />
      <div style={{ fontWeight: 800, fontSize: 30, color: '#fff', letterSpacing: '-1px' }}>{brandline}</div>
      <div style={{ color: 'rgba(255,255,255,0.52)', fontSize: 11, fontWeight: 600, letterSpacing: .2, marginTop: 9 }}>Our vision</div>
      {state === 'checking' ? (
        <div style={{ marginTop: 60, display: 'flex', gap: 6 }}>
          {[0,1,2].map(i => <div key={i} style={{ width: i === 0 ? 20 : 6, height: 6, background: i === 0 ? N.gold : 'rgba(255,255,255,0.2)', borderRadius: 99, transition: 'all 0.3s' }} />)}
        </div>
      ) : (
        <div style={{ marginTop: 48, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
          <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 13, textAlign: 'center', padding: '0 32px' }}>Couldn't reach Prepza. Check your connection.</div>
          <button onClick={() => checkSession(0)} style={{ background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.18)', borderRadius: 12, padding: '10px 22px', color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Retry</button>
        </div>
      )}
    </div>
  )
}
