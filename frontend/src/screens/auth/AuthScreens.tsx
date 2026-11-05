import { useEffect, useRef, useState } from 'react'

import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import type { UniversityOption, ProgramOption } from '../../types/academic'

export function ForgotPasswordScreen({ setScreen }: { setScreen: (s: 'login') => void }) {
  const { tokens: T } = useTheme()
  const [email, setEmail] = useState('')
  const [otpLength, setOtpLength] = useState(6)
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [sent, setSent] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [resendSeconds, setResendSeconds] = useState(0)

  useEffect(() => {
    if (resendSeconds <= 0) return
    const id = window.setInterval(() => setResendSeconds(s => Math.max(0, s - 1)), 1000)
    return () => window.clearInterval(id)
  }, [resendSeconds])

  const passwordValid = newPassword.length >= 8 &&
    /[a-z]/.test(newPassword) &&
    /[A-Z]/.test(newPassword) &&
    /\d/.test(newPassword) &&
    /[^A-Za-z0-9]/.test(newPassword)

  const requestCode = async () => {
    setError('')
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError('Please enter a valid email address.')
      return
    }
    setSubmitting(true)
    try {
      const response = await api<{ otp_length?: number }>('/forgot-password', { method: 'POST', body: JSON.stringify({ email }) })
      if (response.otp_length) setOtpLength(response.otp_length)
      setSent(true)
      setResendSeconds(60)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const resend = async () => {
    if (resendSeconds > 0 || submitting) return
    setSubmitting(true)
    setError('')
    try {
      const response = await api<{ otp_length?: number }>('/forgot-password', { method: 'POST', body: JSON.stringify({ email }) })
      if (response.otp_length) setOtpLength(response.otp_length)
      setResendSeconds(60)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not send a new reset code.')
    } finally {
      setSubmitting(false)
    }
  }

  const resetPassword = async () => {
    setError('')
    if (!new RegExp('^\\d{' + otpLength + '}$').test(code)) { setError('Enter the ' + otpLength + '-digit code from your email.'); return }
    if (!passwordValid) { setError('Choose a password with at least 8 characters, including upper/lowercase letters, a number and a symbol.'); return }
    if (newPassword !== confirmPassword) { setError('The passwords do not match.'); return }
    setSubmitting(true)
    try {
      await api('/reset-password', {
        method: 'POST',
        body: JSON.stringify({ email, code, new_password: newPassword }),
      })
      setDone(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'That code could not be verified. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: `linear-gradient(170deg,${N.navy} 0%,${N.navy2} 60%,${N.bg} 100%)` }} className="scrollbar-hide">
      <div style={{ padding: '20px 28px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <button onClick={() => setScreen('login')} style={{ alignSelf: 'flex-start', background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, padding: '8px 12px', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 32, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 12 }}>{Ic.back('w-4 h-4')} Back</button>
        <img src="/icon-192.png" alt="Prepza" style={{ width: 64, height: 64, borderRadius: 18, marginBottom: 20 }} />
        {!sent ? (
          <>
            <div style={{ fontWeight: 800, fontSize: 24, color: '#fff', textAlign: 'center' }}>Reset Password</div>
            <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginTop: 6, marginBottom: 32, textAlign: 'center' }}>Enter your email and we'll send a verification code.</div>
            <div style={{ width: '100%' }}>
              <input value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" placeholder="your@email.com" style={{ width: '100%', boxSizing: 'border-box', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 16px', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', marginBottom: 16 }} />
              {error && <div style={{ background: 'rgba(140,29,43,0.25)', border: '1px solid rgba(140,29,43,0.5)', borderRadius: 12, padding: '10px 14px', color: '#ffb4bd', fontSize: 13, marginBottom: 16 }}>{error}</div>}
              <button disabled={submitting} onClick={requestCode} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: submitting ? 0.6 : 1 }}>{submitting ? 'Sending…' : 'Send Reset Code'}</button>
            </div>
          </>
        ) : done ? (
          <>
            <div style={{ width: 72, height: 72, borderRadius: '50%', background: 'rgba(76,201,123,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 24, color: '#4CC97B' }}>
              <svg aria-hidden="true" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
            </div>
            <div style={{ fontWeight: 800, fontSize: 22, color: '#fff', textAlign: 'center', marginBottom: 10 }}>Password reset</div>
            <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 13, textAlign: 'center', lineHeight: 1.7, marginBottom: 32 }}>Your password has been changed. Sign in with the new password.</div>
            <button onClick={() => setScreen('login')} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Back to Login</button>
          </>
        ) : (
          <>
            <div style={{ fontWeight: 800, fontSize: 24, color: '#fff', textAlign: 'center' }}>Enter your reset code</div>
            <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginTop: 6, marginBottom: 20, textAlign: 'center' }}>We sent a {otpLength}-digit code to <strong style={{ color: N.gold }}>{email}</strong>.</div>
            {error && <div style={{ width: '100%', background: 'rgba(140,29,43,0.25)', border: '1px solid rgba(140,29,43,0.5)', borderRadius: 12, padding: '10px 14px', color: '#ffb4bd', fontSize: 13, marginBottom: 14, boxSizing: 'border-box' }}>{error}</div>}
            <input value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" maxLength={otpLength} placeholder={'0'.repeat(otpLength)} style={{ width: '100%', boxSizing: 'border-box', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 16, padding: '15px', color: '#fff', fontSize: 25, letterSpacing: 9, textAlign: 'center', fontFamily: 'Plus Jakarta Sans', outline: 'none', marginBottom: 14 }} />
            <input value={newPassword} onChange={e => setNewPassword(e.target.value)} type="password" autoComplete="new-password" placeholder="New password" style={{ width: '100%', boxSizing: 'border-box', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 16px', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', marginBottom: 10 }} />
            <input value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} type="password" autoComplete="new-password" placeholder="Confirm new password" style={{ width: '100%', boxSizing: 'border-box', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 16px', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', marginBottom: 14 }} />
            <button disabled={submitting} onClick={resetPassword} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: submitting ? 0.6 : 1 }}>{submitting ? 'Saving…' : 'Reset Password'}</button>
            <button type="button" onClick={resend} disabled={resendSeconds > 0 || submitting} style={{ marginTop: 16, background: 'none', border: 'none', color: N.gold, fontWeight: 700, fontSize: 13, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: resendSeconds > 0 ? 0.55 : 1 }}>{resendSeconds > 0 ? `Resend code in ${resendSeconds}s` : 'Resend code'}</button>
          </>
        )}
      </div>
    </div>
  )
}

export function ResetPasswordScreen({ setScreen }: { setScreen: (s: 'login') => void }) {
  const { tokens: T } = useTheme()
  const token = new URLSearchParams(window.location.search).get('token') || ''
  const [password, setPassword] = useState('')
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const COMMON_WEAK_PASSWORDS = new Set([
    'password', 'password1', 'password12', 'password123',
    '12345678', '123456789', '1234567890', 'qwerty123', 'qwertyuiop',
    'letmein123', 'iloveyou1', 'iloveyou123', 'admin1234', 'welcome123',
    'abc123456', '11111111', '00000000', 'changeme1', 'monkey123',
    'football1', 'sunshine1', 'princess1', 'dragon123',
  ])
  // Mirrors app.py's password_strength_error() branch-for-branch, same as
  // the signup checklist, so this never disagrees with what POST
  // /reset-password will actually accept.
  const passwordChecks = (pw: string) => [
    { label: 'At least 8 characters', met: pw.length >= 8 },
    { label: 'One lowercase letter', met: /[a-z]/.test(pw) },
    { label: 'One uppercase letter', met: /[A-Z]/.test(pw) },
    { label: 'One number', met: /\d/.test(pw) },
    { label: 'One symbol (e.g. ! @ # $ %)', met: /[^A-Za-z0-9]/.test(pw) },
    { label: 'Not a commonly used password', met: pw.length > 0 && !COMMON_WEAK_PASSWORDS.has(pw.toLowerCase()) },
  ]
  const stepValid = passwordChecks(password).every(c => c.met)

  const handleSubmit = async () => {
    setError('')
    if (!token) { setError('This reset link is missing its token - please use the link from your email directly.'); return }
    if (!stepValid) { setError('Please meet all password requirements below.'); return }
    setSubmitting(true)
    try {
      await api('/reset-password', { method: 'POST', body: JSON.stringify({ token, new_password: password }) })
      setDone(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: `linear-gradient(170deg,${N.navy} 0%,${N.navy2} 60%,${N.bg} 100%)` }} className="scrollbar-hide">
      <div style={{ padding: '20px 28px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <img src="/icon-192.png" alt="Prepza" style={{ width: 64, height: 64, borderRadius: 18, marginTop: 20, marginBottom: 20 }} />
        {!done ? (
          <>
            <div style={{ fontWeight: 800, fontSize: 24, color: '#fff', letterSpacing: '-0.5px', textAlign: 'center' }}>Set a new password</div>
            <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginTop: 6, marginBottom: 24, textAlign: 'center' }}>Choose a strong password for your account</div>
            {!token && (
              <div style={{ width: '100%', background: 'rgba(140,29,43,0.25)', border: '1px solid rgba(140,29,43,0.5)', borderRadius: 12, padding: '10px 14px', color: '#ffb4bd', fontSize: 13, marginBottom: 16, boxSizing: 'border-box' }}>
                This link is missing its reset token. Please open the link from your email directly, or request a new one.
              </div>
            )}
            {error && (
              <div style={{ width: '100%', background: 'rgba(140,29,43,0.25)', border: '1px solid rgba(140,29,43,0.5)', borderRadius: 12, padding: '10px 14px', color: '#ffb4bd', fontSize: 13, marginBottom: 16, boxSizing: 'border-box' }}>{error}</div>
            )}
            <div style={{ width: '100%' }}>
              <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12, fontWeight: 600, marginBottom: 6 }}>New Password</div>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" style={{ width: '100%', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 16px', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', boxSizing: 'border-box', marginBottom: 12 }} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 20 }}>
                {passwordChecks(password).map(c => (
                  <div key={c.label} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: c.met ? '#4CC97B' : 'rgba(255,255,255,0.4)', fontFamily: 'Plus Jakarta Sans' }}>
                    <span>{c.met ? '✓' : '○'}</span>{c.label}
                  </div>
                ))}
              </div>
              <button disabled={submitting || !stepValid} onClick={handleSubmit} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: (submitting || !stepValid) ? 'default' : 'pointer', opacity: (submitting || !stepValid) ? 0.45 : 1, fontFamily: 'Plus Jakarta Sans' }}>{submitting ? 'Saving…' : 'Reset Password'}</button>
            </div>
          </>
        ) : (
          <>
            <div style={{ fontSize: 56, marginBottom: 16 }}>✅</div>
            <div style={{ fontWeight: 800, fontSize: 22, color: '#fff', textAlign: 'center', marginBottom: 10 }}>Password reset</div>
            <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 13, textAlign: 'center', lineHeight: 1.7, marginBottom: 32 }}>You can now log in with your new password.</div>
            <button onClick={() => setScreen('login')} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Back to Login</button>
          </>
        )}
      </div>
    </div>
  )
}

export function VerifyConfirmScreen({ setScreen }: { setScreen: (s: 'home' | 'login') => void }) {
  const { tokens: T } = useTheme()
  const [status, setStatus] = useState<'confirming' | 'success' | 'error'>('confirming')
  const [error, setError] = useState('')
  const [resendEmail, setResendEmail] = useState('')
  const [resendState, setResendState] = useState<'idle' | 'sending' | 'sent'>('idle')

  // GET /verify-email itself just serves this SPA shell (scanner-safe - a
  // link-preview bot fetching the URL doesn't run JS and so can't silently
  // consume the token). The actual confirmation happens here, via this
  // JS-triggered POST, matching the old static/verify-confirm.html design.
  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token') || ''
    if (!token) {
      setStatus('error')
      setError('This verification link is missing its token.')
      return
    }
    api('/verify-email/confirm', { method: 'POST', body: JSON.stringify({ token }) })
      .then(() => setStatus('success'))
      .catch((e) => {
        setStatus('error')
        setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
      })
  }, [])

  // Backend always returns the same generic message whether or not the
  // account/verification state matches (same privacy pattern as
  // /forgot-password) - nothing to branch on beyond request success.
  const handleResend = async () => {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(resendEmail)) return
    setResendState('sending')
    try {
      await api('/resend-verification', { method: 'POST', body: JSON.stringify({ email: resendEmail }) })
    } catch { /* generic response either way - nothing to surface */ }
    setResendState('sent')
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 32px', background: `linear-gradient(170deg,${N.navy} 0%,${N.navy2} 60%,${N.bg} 100%)`, textAlign: 'center' }}>
      {status === 'confirming' && (
        <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 14 }}>Confirming your email…</div>
      )}
      {status === 'success' && (
        <>
          <div style={{ width: 72, height: 72, borderRadius: '50%', background: 'rgba(76,201,123,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 24 }}>
            <span style={{ fontSize: 32 }}>✅</span>
          </div>
          <div style={{ fontWeight: 800, fontSize: 22, color: '#fff', marginBottom: 10 }}>Email verified</div>
          <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 14, lineHeight: 1.6, marginBottom: 32 }}>Your account is confirmed and you're already signed in.</div>
          <button onClick={() => setScreen('home')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 32px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Continue to Prepza</button>
        </>
      )}
      {status === 'error' && (
        <>
          <div style={{ width: 72, height: 72, borderRadius: '50%', background: 'rgba(140,29,43,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 24 }}>
            <span style={{ fontSize: 32 }}>⚠️</span>
          </div>
          <div style={{ fontWeight: 800, fontSize: 22, color: '#fff', marginBottom: 10 }}>Verification failed</div>
          <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 14, lineHeight: 1.6, marginBottom: 24 }}>{error}</div>

          {resendState === 'sent' ? (
            <div style={{ color: '#4CC97B', fontSize: 13, marginBottom: 24 }}>If that email needs verifying, a new link is on its way.</div>
          ) : (
            <div style={{ width: '100%', maxWidth: 320, marginBottom: 24 }}>
              <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 12, marginBottom: 10 }}>Get a new verification link:</div>
              <input value={resendEmail} onChange={e => setResendEmail(e.target.value)} placeholder="your@email.com" style={{ width: '100%', boxSizing: 'border-box', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 16px', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', marginBottom: 10 }} />
              <button
                disabled={resendState === 'sending' || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(resendEmail)}
                onClick={handleResend}
                style={{ width: '100%', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.18)', borderRadius: 14, padding: '12px 0', color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: resendState === 'sending' ? 0.6 : 1 }}
              >{resendState === 'sending' ? 'Sending…' : 'Resend verification email'}</button>
            </div>
          )}

          <button onClick={() => setScreen('login')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 32px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Back to Sign In</button>
        </>
      )}
    </div>
  )
}

export function SignupScreen({ setScreen, referralCode, referralChannel }: { setScreen: (s: 'check-email') => void; referralCode?: string | null; referralChannel?: string | null }) {
  const { tokens: T } = useTheme()
  const steps = ['Name', 'Email', 'Password', 'University', 'Course', 'Year', 'Semester']
  const [step, setStep] = useState(0)
  const [data, setData] = useState({
    display_name: '', email: '', password: '',
    university_id: null as number | null, university_name: '',
    program_id: null as number | null, program_name: '',
    year: null as number | null, semester: null as number | null,
  })

  const [universities, setUniversities] = useState<UniversityOption[]>([])
  const [loadingUniversities, setLoadingUniversities] = useState(true)
  const [uniSearch, setUniSearch] = useState('')

  const [programs, setPrograms] = useState<ProgramOption[]>([])
  const [loadingPrograms, setLoadingPrograms] = useState(false)
  const [courseSearch, setCourseSearch] = useState('')

  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  // True once the user has been bounced back to fix a field after a failed
  // submit - lets Continue skip straight back to resubmitting instead of
  // forcing them to re-click through every already-answered step again.
  const [recovering, setRecovering] = useState(false)

  useEffect(() => {
    api<UniversityOption[]>('/universities')
      .then(setUniversities)
      .catch(() => setError('Could not load the university list. Check your connection and try again.'))
      .finally(() => setLoadingUniversities(false))
  }, [])

  useEffect(() => {
    if (data.university_id == null) { setPrograms([]); return }
    setLoadingPrograms(true)
    api<ProgramOption[]>(`/universities/${data.university_id}/programs`)
      .then(setPrograms)
      .catch(() => setError('Could not load courses for that university.'))
      .finally(() => setLoadingPrograms(false))
  }, [data.university_id])

  const goBack = () => { setError(''); setStep(s => Math.max(0, s - 1)) }
  const advance = () => { setError(''); setStep(s => s + 1) }

  // Mirrors app.py's password_strength_error() exactly, so weak passwords
  // get caught here instead of only failing after the full wizard is done.
  const COMMON_WEAK_PASSWORDS = new Set([
    'password', 'password1', 'password12', 'password123',
    '12345678', '123456789', '1234567890', 'qwerty123', 'qwertyuiop',
    'letmein123', 'iloveyou1', 'iloveyou123', 'admin1234', 'welcome123',
    'abc123456', '11111111', '00000000', 'changeme1', 'monkey123',
    'football1', 'sunshine1', 'princess1', 'dragon123',
  ])
  // Each check mirrors one branch of app.py's password_strength_error()
  // in the same order, so this checklist never disagrees with what the
  // backend will actually accept.
  const passwordChecks = (pw: string) => [
    { label: 'At least 8 characters', met: pw.length >= 8 },
    { label: 'One lowercase letter', met: /[a-z]/.test(pw) },
    { label: 'One uppercase letter', met: /[A-Z]/.test(pw) },
    { label: 'One number', met: /\d/.test(pw) },
    { label: 'One symbol (e.g. ! @ # $ %)', met: /[^A-Za-z0-9]/.test(pw) },
    { label: 'Not a commonly used password', met: pw.length > 0 && !COMMON_WEAK_PASSWORDS.has(pw.toLowerCase()) },
  ]
  const passwordError = (pw: string): string | null => {
    const failed = passwordChecks(pw).find(c => !c.met)
    return failed ? `Password needs: ${failed.label.toLowerCase()}.` : null
  }

  // After steps 0-2 (Name/Email/Password), decide whether to continue
  // forward normally or - if this is a correction after a failed submit
  // and everything else is already filled in - jump straight back to
  // resubmitting instead of re-walking University/Course/Year/Semester.
  const continueFromEarlyStep = () => {
    if (recovering && data.university_id != null && data.program_id != null && data.year != null && data.semester != null) {
      setRecovering(false)
      setError('')
      handleSubmit()
    } else {
      advance()
    }
  }

  const handleSubmit = async (overrides: Partial<typeof data> = {}) => {
    const payload = { ...data, ...overrides }
    setSubmitting(true)
    setError('')
    try {
      const signupResponse = await api<{ otp_length?: number }>('/signup', {
        method: 'POST',
        body: JSON.stringify({
          display_name: payload.display_name,
          email: payload.email,
          password: payload.password,
          university_id: payload.university_id,
          program_id: payload.program_id,
          year: payload.year,
          semester: payload.semester,
          ref: referralCode || undefined,
          via: referralChannel || undefined,
        }),
      })
      sessionStorage.setItem('prepza_verification_email', payload.email)
      sessionStorage.setItem('prepza_verification_otp_length', String(signupResponse.otp_length || 6))
      setScreen('check-email')
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Something went wrong. Please try again.'
      setError(msg)
      setRecovering(true)
      const lower = msg.toLowerCase()
      if (lower.includes('display name')) setStep(0)
      else if (lower.includes('email')) setStep(1)
      else if (lower.includes('password')) setStep(2)
      else if (lower.includes('university')) setStep(3)
      else if (lower.includes('course') || lower.includes('program')) setStep(4)
      else if (lower.includes('year')) setStep(5)
      else if (lower.includes('semester')) setStep(6)
    } finally {
      setSubmitting(false)
    }
  }

  const filteredUniversities = universities.filter(u => u.name.toLowerCase().includes(uniSearch.toLowerCase()))
  const filteredPrograms = programs.filter(p => p.name.toLowerCase().includes(courseSearch.toLowerCase()))

  const titles = ["What's your name?", 'Your email address', 'Create a password', 'Your university', 'Your course', 'What year are you?', 'Which semester?']
  const subtitles: Record<number, string> = { 6: "Almost done - we'll personalise your experience" }

  const inputStyle = { width: '100%', boxSizing: 'border-box' as const, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 16px', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', marginBottom: 12 }
  const optionStyle = (selected: boolean) => ({ background: selected ? 'rgba(201,168,76,0.2)' : 'rgba(255,255,255,0.08)', border: `1px solid ${selected ? N.gold + '55' : 'rgba(255,255,255,0.1)'}`, borderRadius: 14, padding: '14px 18px', color: '#fff', fontWeight: 600, fontSize: 14, cursor: 'pointer', textAlign: 'left' as const, fontFamily: 'Plus Jakarta Sans' })
  const primaryBtn = { background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', marginTop: 'auto' }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: `linear-gradient(170deg,${N.navy} 0%,${N.navy2} 60%,${N.bg} 100%)` }}>
      <div style={{ padding: '20px 24px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          {step > 0 && <button onClick={goBack} style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, padding: '8px 10px', color: '#fff', cursor: 'pointer' }}>{Ic.back('w-4 h-4')}</button>}
          <div style={{ flex: 1, background: 'rgba(255,255,255,0.12)', borderRadius: 99, height: 4 }}>
            <div style={{ width: `${((step + 1) / steps.length) * 100}%`, height: '100%', background: N.gold, borderRadius: 99, transition: 'width 0.3s' }} />
          </div>
          <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12, fontWeight: 600 }}>{step + 1}/{steps.length}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 20 }}>
          <img src="/icon-192.png" alt="Prepza" style={{ width: 56, height: 56, borderRadius: 16 }} />
        </div>
      </div>
      <div style={{ flex: 1, padding: '0 24px 32px', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div style={{ fontWeight: 800, fontSize: 26, color: '#fff', marginBottom: 6 }}>{titles[step]}</div>
        <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 13, marginBottom: 20 }}>{subtitles[step] ?? 'Help us personalise your Prepza experience'}</div>

        {error && (
          <div style={{ background: 'rgba(140,29,43,0.25)', border: '1px solid rgba(140,29,43,0.5)', borderRadius: 12, padding: '10px 14px', color: '#ffb4bd', fontSize: 13, marginBottom: 16 }}>{error}</div>
        )}

        {step === 0 && (
          <input name="name" autoComplete="name" aria-label="Full name" value={data.display_name} onChange={e => setData(d => ({ ...d, display_name: e.target.value }))} placeholder="e.g. Arnold Gichuru" maxLength={50} style={inputStyle} />
        )}
        {step === 1 && (
          <input type="email" name="email" autoComplete="email" inputMode="email" aria-label="Email address" value={data.email} onChange={e => setData(d => ({ ...d, email: e.target.value }))} placeholder="arnold@students.ku.ac.ke" style={inputStyle} />
        )}
        {step === 2 && (
          <>
            <input type="password" name="password" autoComplete="new-password" aria-label="Create password" value={data.password} onChange={e => setData(d => ({ ...d, password: e.target.value }))} placeholder="••••••••" style={inputStyle} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
              {passwordChecks(data.password).map(c => (
                <div key={c.label} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: c.met ? '#4CC97B' : 'rgba(255,255,255,0.4)', fontFamily: 'Plus Jakarta Sans' }}>
                  <span>{c.met ? '✓' : '○'}</span>{c.label}
                </div>
              ))}
            </div>
          </>
        )}

        {step === 3 && (
          <>
            <input type="search" aria-label="Search universities" value={uniSearch} onChange={e => setUniSearch(e.target.value)} placeholder="Type to search your university..." style={inputStyle} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1, overflowY: 'auto', minHeight: 0 }} className="scrollbar-hide">
              {loadingUniversities ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>Loading universities...</div>
              ) : filteredUniversities.length === 0 ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>University not found. Prepza doesn't have your university yet - try a different search, or check back soon.</div>
              ) : filteredUniversities.map(u => (
                <button key={u.id} onClick={() => { setData(d => ({ ...d, university_id: u.id, university_name: u.name, program_id: null, program_name: '' })); setCourseSearch(''); advance() }}
                  style={optionStyle(data.university_id === u.id)}>{u.name}</button>
              ))}
            </div>
          </>
        )}

        {step === 4 && (
          <>
            <input type="search" aria-label="Search courses" value={courseSearch} onChange={e => setCourseSearch(e.target.value)} placeholder="Type to search your course..." style={inputStyle} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1, overflowY: 'auto', minHeight: 0 }} className="scrollbar-hide">
              {loadingPrograms ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>Loading courses...</div>
              ) : programs.length === 0 ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>No courses listed yet for {data.university_name}. Check back soon - we're adding more universities regularly.</div>
              ) : filteredPrograms.length === 0 ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>Course not found for {data.university_name}. Try a different search.</div>
              ) : filteredPrograms.map(p => (
                <button key={p.id} onClick={() => { setData(d => ({ ...d, program_id: p.id, program_name: p.name })); advance() }}
                  style={optionStyle(data.program_id === p.id)}>{p.name}</button>
              ))}
            </div>
          </>
        )}

        {step === 5 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[1, 2, 3, 4, 5].map(y => (
              <button key={y} onClick={() => { setData(d => ({ ...d, year: y })); advance() }} style={optionStyle(data.year === y)}>Year {y}</button>
            ))}
          </div>
        )}

        {step === 6 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[1, 2, 3].map(s => (
              <button key={s} disabled={submitting} onClick={() => { setData(d => ({ ...d, semester: s })); handleSubmit({ semester: s }) }} style={optionStyle(data.semester === s)}>Semester {s}</button>
            ))}
            {submitting && <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginTop: 8 }}>Creating your account...</div>}
          </div>
        )}

        {step <= 2 && (() => {
          const stepValid =
            step === 0 ? data.display_name.trim().length > 0 :
            step === 1 ? /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email) :
            passwordError(data.password) === null
          return (
            <button
              disabled={!stepValid}
              onClick={() => {
                if (step === 0 && !data.display_name.trim()) { setError('Please enter your name.'); return }
                if (step === 1 && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) { setError('Please enter a valid email address.'); return }
                if (step === 2) {
                  const pwErr = passwordError(data.password)
                  if (pwErr) { setError(pwErr); return }
                }
                continueFromEarlyStep()
              }}
              style={{ ...primaryBtn, opacity: stepValid ? 1 : 0.45, cursor: stepValid ? 'pointer' : 'not-allowed' }}>Continue →</button>
          )
        })()}
      </div>
    </div>
  )
}

export function CheckEmailScreen({ setScreen }: { setScreen: (s: 'home' | 'login') => void }) {
  const { tokens: T } = useTheme()
  const inputRef = useRef<HTMLInputElement>(null)
  const [email, setEmail] = useState('')
  const [otpLength, setOtpLength] = useState(6)
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [resendSeconds, setResendSeconds] = useState(0)
  const [resending, setResending] = useState(false)

  useEffect(() => {
    const stored = sessionStorage.getItem('prepza_verification_email') || ''
    setEmail(stored)
    const storedLength = Number(sessionStorage.getItem('prepza_verification_otp_length') || '6')
    setOtpLength(storedLength >= 6 && storedLength <= 8 ? storedLength : 6)
    window.setTimeout(() => inputRef.current?.focus(), 50)
  }, [])

  useEffect(() => {
    if (resendSeconds <= 0) return
    const id = window.setInterval(() => setResendSeconds(s => Math.max(0, s - 1)), 1000)
    return () => window.clearInterval(id)
  }, [resendSeconds])

  const verify = async (value: string) => {
    const clean = value.replace(/\D/g, '').slice(0, otpLength)
    if (clean.length !== otpLength || verifying || !email) return
    setCode(clean)
    setError('')
    setVerifying(true)
    try {
      await api('/verify-otp', {
        method: 'POST',
        body: JSON.stringify({ email, code: clean }),
      })
      sessionStorage.removeItem('prepza_verification_email')
      setScreen('home')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'That code could not be verified. Please try again.')
      setCode('')
      window.setTimeout(() => inputRef.current?.focus(), 20)
    } finally {
      setVerifying(false)
    }
  }

  const handleCodeChange = (value: string) => {
    const clean = value.replace(/\D/g, '').slice(0, otpLength)
    setCode(clean)
    setError('')
    if (clean.length === otpLength) void verify(clean)
  }

  const resend = async () => {
    if (!email || resending || resendSeconds > 0) return
    setResending(true)
    setError('')
    try {
      const response = await api<{ message: string; expires_in_seconds?: number; otp_length?: number }>('/resend-verification', {
        method: 'POST',
        body: JSON.stringify({ email }),
      })
      setResendSeconds(60)
      if (response.otp_length) setOtpLength(response.otp_length)
      if (response.message) setError('')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not send a new code right now.')
    } finally {
      setResending(false)
      window.setTimeout(() => inputRef.current?.focus(), 20)
    }
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 28px', background: `linear-gradient(170deg,${N.navy} 0%,${N.navy2} 60%,${N.bg} 100%)`, textAlign: 'center' }}>
      <div style={{ width: 72, height: 72, borderRadius: '50%', background: 'rgba(201,168,76,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 24, color: N.gold }}>
        <svg aria-hidden="true" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <path d="m4 7 8 6 8-6" />
        </svg>
      </div>
      <div style={{ fontWeight: 800, fontSize: 22, color: '#fff', marginBottom: 10 }}>Verify your email</div>
      <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 14, lineHeight: 1.6, marginBottom: 24, maxWidth: 340 }}>
        Enter the {otpLength}-digit code we sent to <strong style={{ color: N.gold }}>{email || 'your email'}</strong>.
      </div>

      <div style={{ width: '100%', maxWidth: 340 }}>
        <input
          ref={inputRef}
          value={code}
          onChange={e => handleCodeChange(e.target.value)}
          onPaste={e => {
            const pasted = e.clipboardData.getData('text').trim().replace(/\D/g, '')
            if (pasted.length === otpLength) {
              e.preventDefault()
              handleCodeChange(pasted)
            }
          }}

          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]*"
          maxLength={otpLength}
          aria-label={otpLength + '-digit verification code'}
          placeholder={"0".repeat(otpLength)}
          disabled={verifying}
          style={{ width: '100%', boxSizing: 'border-box', background: 'rgba(255,255,255,0.08)', border: `1px solid ${error ? 'rgba(255,120,130,0.6)' : 'rgba(255,255,255,0.15)'}`, borderRadius: 16, padding: '16px', color: '#fff', fontSize: 26, letterSpacing: 10, textAlign: 'center', fontFamily: 'Plus Jakarta Sans', outline: 'none' }}
        />

        {verifying && <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12, marginTop: 10 }}>Verifying…</div>}
        {error && <div style={{ color: '#ffb4bd', fontSize: 13, lineHeight: 1.5, marginTop: 12 }}>{error}</div>}


        {verifying && <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12, marginTop: 10 }}>Verifying…</div>}
        {error && <div style={{ color: '#ffb4bd', fontSize: 13, lineHeight: 1.5, marginTop: 12 }}>{error}</div>}
        <button
          type="button"
          onClick={resend}
          disabled={resending || resendSeconds > 0}
          style={{ marginTop: 20, background: 'none', border: 'none', color: N.gold, fontWeight: 700, fontSize: 13, cursor: resendSeconds > 0 || resending ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: resendSeconds > 0 || resending ? 0.55 : 1 }}
        >
          {resending ? 'Sending…' : resendSeconds > 0 ? `Resend code in ${resendSeconds}s` : 'Resend code'}
        </button>

        <button
          type="button"
          onClick={() => { sessionStorage.removeItem('prepza_verification_email'); setScreen('login') }}
          style={{ width: '100%', marginTop: 18, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.14)', borderRadius: 16, padding: '13px 0', color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}
        >
          Back to Sign In
        </button>
      </div>
    </div>
  )
}
