import { useState } from 'react'

import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'

export default function LoginScreen({ setScreen, oauthError = '' }: { setScreen: (s: 'home' | 'forgot-password' | 'signup') => void; oauthError?: string }) {
  const { tokens: T } = useTheme()
  // Keep the auth entry point keyboard/mobile friendly: native form semantics
  // allow password managers and Enter-to-submit without adding another auth path.
  const [email, setEmail] = useState('')
  const [pass, setPass] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [error, setError] = useState(oauthError)
  const [submitting, setSubmitting] = useState(false)
  const [resendingVerification, setResendingVerification] = useState(false)
  const [resendMessage, setResendMessage] = useState('')

  const handleLogin = async () => {
    setError('')
    setResendMessage('')
    if (!email || !pass) { setError('Please enter both your email and password.'); return }
    setSubmitting(true)
    try {
      await api('/login', { method: 'POST', body: JSON.stringify({ email, password: pass }) })
      setScreen('home')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
      setResendMessage('If this account still needs email verification, you can request a new link below.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: `linear-gradient(170deg, ${N.navy} 0%, ${N.navy2} 55%, ${N.bg} 100%)` }} className="scrollbar-hide">
      <div style={{ padding: '20px 28px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 40 }}>
        <img src="/icon-192.png" alt="Prepza" style={{ width: 72, height: 72, borderRadius: 20, marginBottom: 16, boxShadow: '0 8px 32px rgba(201,168,76,0.25)' }} />
        <div style={{ fontWeight: 800, fontSize: 26, color: '#fff', letterSpacing: '-0.5px' }}>Welcome back</div>
        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginTop: 4, marginBottom: 36 }}>Sign in to continue studying</div>

        <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Email</div>
            <input type="email" name="email" autoComplete="email" inputMode="email" aria-label="Email address" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" style={{ width: '100%', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 16px', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', boxSizing: 'border-box' }} />
          </div>
          <div>
            <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Password</div>
            <div style={{ position: 'relative' }}>
              <input type={showPass ? 'text' : 'password'} name="password" autoComplete="current-password" aria-label="Password" value={pass} onChange={e => setPass(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleLogin()} placeholder="••••••••" style={{ width: '100%', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 44px 13px 16px', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', boxSizing: 'border-box' }} />
              <button type="button" aria-label={showPass ? 'Hide password' : 'Show password'} title={showPass ? 'Hide password' : 'Show password'} onClick={() => setShowPass(v => !v)} style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.4)' }}>{Ic.eye()}</button>
            </div>
          </div>
          <div style={{ textAlign: 'right' }}><span onClick={() => setScreen('forgot-password')} style={{ color: N.gold, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>Forgot password?</span></div>

          {error && (
            <div style={{ background: 'rgba(140,29,43,0.25)', border: '1px solid rgba(140,29,43,0.5)', borderRadius: 12, padding: '10px 14px', color: '#ffb4bd', fontSize: 13 }}>{error}</div>
          )}

          {resendMessage && email && (
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)', lineHeight: 1.5 }}>
              {resendMessage} <button type="button" disabled={resendingVerification} onClick={async () => {
                setResendingVerification(true)
                try {
                  const res = await api<{ message: string }>('/resend-verification', { method: 'POST', body: JSON.stringify({ email }) })
                  setResendMessage(res.message)
                } catch { setResendMessage('Could not request a new verification link. Please try again.') }
                finally { setResendingVerification(false) }
              }} style={{ background: 'none', border: 'none', padding: 0, color: N.gold, fontWeight: 700, cursor: resendingVerification ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', fontSize: 12 }}>{resendingVerification ? 'Sending…' : 'Resend verification email'}</button>
            </div>
          )}

          <button disabled={submitting} onClick={handleLogin} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: submitting ? 'default' : 'pointer', opacity: submitting ? 0.7 : 1, fontFamily: 'Plus Jakarta Sans', boxShadow: '0 6px 24px rgba(201,168,76,0.4)', marginTop: 4 }}>{submitting ? 'Signing in...' : 'Sign In'}</button>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 8 }}>
            <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.1)' }} />
            <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: 12 }}>or continue with</span>
            <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.1)' }} />
          </div>

          <button type="button" aria-label="Continue with Google" onClick={() => { window.location.href = '/auth/google' }} style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 14, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M21.35 12.2c0-.68-.06-1.33-.18-1.95H12v3.69h5.24a4.48 4.48 0 0 1-1.94 2.94v2.44h3.14c1.84-1.69 2.91-4.18 2.91-7.12Z" fill="#4285F4"/><path d="M12 21.5c2.64 0 4.85-.87 6.47-2.35l-3.14-2.44c-.87.58-1.98.92-3.33.92-2.56 0-4.73-1.73-5.5-4.06H3.25v2.52A9.77 9.77 0 0 0 12 21.5Z" fill="#34A853"/><path d="M6.5 13.57a5.87 5.87 0 0 1 0-3.74V7.31H3.25a9.5 9.5 0 0 0 0 8.78l3.25-2.52Z" fill="#FBBC05"/><path d="M12 5.77c1.44 0 2.73.5 3.75 1.48l2.81-2.81C16.85 2.85 14.64 2 12 2a9.77 9.77 0 0 0-8.75 5.31L6.5 9.83C7.27 7.5 9.44 5.77 12 5.77Z" fill="#EA4335"/></svg> Continue with Google
          </button>
        </div>

        <div style={{ marginTop: 28, color: 'rgba(255,255,255,0.5)', fontSize: 13, textAlign: 'center' }}>
          Don't have an account? <span onClick={() => setScreen('signup')} style={{ color: N.gold, fontWeight: 700, cursor: 'pointer' }}>Sign Up</span>
        </div>
      </div>
    </div>
  )
}
