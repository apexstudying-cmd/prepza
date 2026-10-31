import { useEffect, useState, type ReactNode } from 'react'
import { api, ApiError } from '../../lib/appApi'
import { subscribeToPush, unsubscribeFromPush } from '../../lib/pushNotifications'
import { TERMS_TEXT, PRIVACY_TEXT } from '../../legalContent'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Pill from '../../ui/Pill'
import type { UniversityOption, ProgramOption } from '../../types/academic'

const PREPZA_VISION = 'Study smarter together.'
const PREPZA_MISSION = 'Bring personalized study tools, trusted academic resources, and students together in one place.'

export default function SettingsScreen({ setScreen, resetToAuth }: { setScreen: (s: 'edit-profile' | 'subscription' | 'payment-history') => void; resetToAuth: () => void }) {
  const [notifs, setNotifs] = useState({ push: true, messages: true, opportunities: false, community: true, reminders: true })
  const [priv, setPriv] = useState({ profilePublic: true, whoMessages: false, whoFollows: true, readReceipts: true })
  const [privacyBusy, setPrivacyBusy] = useState(false)
  const [opportunityDiscovery, setOpportunityDiscovery] = useState(false)
  const [showLogout, setShowLogout] = useState(false)
  const [showModal, setShowModal] = useState<string|null>(null)

  const [csrfToken, setCsrfToken] = useState('')
  const [email, setEmail] = useState('')
  const [uniName, setUniName] = useState<string | null>(null)
  const [programName, setProgramName] = useState<string | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [logoutError, setLogoutError] = useState('')

  const [emailPassword, setEmailPassword] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [emailChangeError, setEmailChangeError] = useState('')
  const [emailChangeSuccess, setEmailChangeSuccess] = useState(false)
  const [emailChangeBusy, setEmailChangeBusy] = useState(false)

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmNewPassword, setConfirmNewPassword] = useState('')
  const [passwordChangeError, setPasswordChangeError] = useState('')
  const [passwordChangeSuccess, setPasswordChangeSuccess] = useState(false)
  const [passwordChangeBusy, setPasswordChangeBusy] = useState(false)

  const submitChangeEmail = async () => {
    if (!emailPassword || !newEmail.trim() || emailChangeBusy) return
    setEmailChangeBusy(true)
    setEmailChangeError('')
    try {
      await api('/change-email', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ password: emailPassword, new_email: newEmail.trim() }),
      })
      setEmailChangeSuccess(true)
      setEmail(newEmail.trim())
    } catch (e) {
      setEmailChangeError(e instanceof ApiError ? e.message : 'Could not change your email. Please try again.')
    } finally {
      setEmailChangeBusy(false)
    }
  }

  const submitChangePassword = async () => {
    if (!currentPassword || !newPassword || passwordChangeBusy) return
    if (newPassword !== confirmNewPassword) {
      setPasswordChangeError('New passwords do not match.')
      return
    }
    setPasswordChangeBusy(true)
    setPasswordChangeError('')
    try {
      await api('/change-password', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      })
      setPasswordChangeSuccess(true)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmNewPassword('')
    } catch (e) {
      setPasswordChangeError(e instanceof ApiError ? e.message : 'Could not change your password. Please try again.')
    } finally {
      setPasswordChangeBusy(false)
    }
  }

  useEffect(() => {
    api<{ email: string; csrf_token: string; university_id: number | null; program_id: number | null; profile_visibility?: string; who_can_message?: string; who_can_follow?: string; read_receipts_enabled?: boolean; year?: number; semester?: number }>('/me')
      .then(me => {
        setCsrfToken(me.csrf_token)
        setEmail(me.email)
        setPriv({ profilePublic: me.profile_visibility !== 'private', whoMessages: me.who_can_message === 'everyone', whoFollows: me.who_can_follow === 'everyone', readReceipts: me.read_receipts_enabled !== false })
        if (me.university_id != null) {
          api<UniversityOption[]>('/universities')
            .then(list => setUniName(list.find(u => u.id === me.university_id)?.name ?? null))
            .catch(() => {})
        }
        if (me.university_id != null && me.program_id != null) {
          api<ProgramOption[]>(`/universities/${me.university_id}/programs`)
            .then(list => setProgramName(list.find(p => p.id === me.program_id)?.name ?? null))
            .catch(() => {})
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    api<{ discoverable: boolean }>('/api/opportunity-discovery')
      .then(value => setOpportunityDiscovery(!!value.discoverable))
      .catch(() => {})
  }, [])

  useEffect(() => {
    api<{ community_enabled: boolean; messages_enabled: boolean }>('/notification-preferences')
      .then(p => setNotifs(n => ({ ...n, community: p.community_enabled, messages: p.messages_enabled })))
      .catch(() => {})
  }, [])

  const handleDeleteAccount = async () => {
    setDeleting(true)
    setDeleteError('')
    try {
      await api('/delete-account', { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
      resetToAuth()
    } catch (e) {
      setDeleteError(e instanceof ApiError ? e.message : 'Could not delete your account. Please try again.')
      setDeleting(false)
    }
  }

  const handleLogout = async () => {
    setLogoutError('')
    try {
      await api('/logout', { method: 'POST' })
      resetToAuth()
    } catch (e) {
      setLogoutError(e instanceof ApiError ? e.message : 'Could not log you out. Please check your connection and try again.')
    }
  }

  const { tokens: T, mode: themeMode, toggleTheme } = useTheme()

  const Section = ({ title, children }: { title: string; children: ReactNode }) => (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontSize: 11, fontWeight: 800, color: T.textMuted, textTransform: 'uppercase', letterSpacing: 1, padding: '12px 18px 6px' }}>{title}</div>
      <div style={{ background: T.card, borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', margin: '0 16px' }}>{children}</div>
    </div>
  )
  const Row = ({ label, sub, onPress, right, danger }: { label: string; sub?: string; onPress?: () => void; right?: ReactNode; danger?: boolean }) => (
    <button onClick={onPress} style={{ display: 'flex', alignItems: 'center', width: '100%', gap: 14, padding: '14px 16px', background: 'none', border: 'none', borderBottom: `1px solid ${T.border}`, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', textAlign: 'left' }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600, fontSize: 13, color: danger ? '#C94C4C' : T.text }}>{label}</div>
        {sub && <div style={{ fontSize: 11, color: T.textMuted, marginTop: 1 }}>{sub}</div>}
      </div>
      {right ?? <div style={{ color: T.textMuted }}>{Ic.chevR()}</div>}
    </button>
  )
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => window.history.back()} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 18, color: '#fff' }}>Settings</span>
        </div>
      </div>

      <div style={{ paddingTop: 12, paddingBottom: 32 }}>
        <Section title="Account">
          <Row label="Edit Profile" sub="Name, photo, bio" onPress={() => setScreen('edit-profile')} />
          <Row label="Email" sub={email || 'Loading...'} onPress={() => { setNewEmail(''); setEmailPassword(''); setEmailChangeError(''); setEmailChangeSuccess(false); setShowModal('email') }} />
          <Row label="Phone" sub="+254 *** *** **89" onPress={() => setShowModal('phone')} />
          <Row label="University" sub={uniName || 'Not set'} onPress={() => setScreen('edit-profile')} />
          <Row label="Course" sub={programName || 'Not set'} onPress={() => setScreen('edit-profile')} />
        </Section>

        <Section title="Preferences">
          <Row label="Study Preferences" sub="Goals, daily target, subjects" onPress={() => setShowModal('study-prefs')} />
          <Row label="AI Preferences" sub="Language, explanation style" onPress={() => setShowModal('ai-prefs')} />
          <Row label="Language" sub="English" onPress={() => setShowModal('language')} />
          <Row label="Appearance" sub={themeMode === 'dark' ? 'Dark mode' : 'Light mode'} right={<div onClick={e => { e.stopPropagation(); toggleTheme() }}>{Ic.toggle(themeMode === 'dark')}</div>} />
        </Section>

        <Section title="Notifications">
          {([['push','Push Notifications'],['messages','Messages'],['community','Community']] as [keyof typeof notifs, string][]).map(([k, l]) => (
            <Row key={k} label={l} right={<div onClick={e => {
              e.stopPropagation()
              if (k === 'push') {
                const next = !notifs.push
                setNotifs(n => ({ ...n, push: next }))
                if (next) {
                  subscribeToPush(csrfToken).catch(() => setNotifs(n => ({ ...n, push: false })))
                } else {
                  unsubscribeFromPush(csrfToken).catch(() => {})
                }
              } else {
                const next = !notifs[k]
                setNotifs(n => ({ ...n, [k]: next }))
                api('/notification-preferences', { method: 'PATCH', headers: { 'X-CSRF-Token': csrfToken }, body: JSON.stringify({ [`${k}_enabled`]: next }) })
                  .catch(() => setNotifs(n => ({ ...n, [k]: !next })))
              }
            }}>{Ic.toggle(notifs[k])}</div>} />
          ))}
          <Row label="Opportunities" sub="Relevant opportunities and discovery" right={<Pill text="Ready" color={N.gold} />} />
          <Row label="Study Reminders" sub="Coming soon" right={<Pill text="Soon" color="#9CA3AF" />} />
        </Section>

        <Section title="Privacy">
          <Row label="Profile Visibility" right={<div onClick={async e => {
            e.stopPropagation()
            if (privacyBusy) return
            const next = !priv.profilePublic
            setPrivacyBusy(true)
            try {
              const me = await api<{ year: number; semester: number }>('/me')
              await api('/profile', { method: 'PATCH', headers: { 'X-CSRF-Token': csrfToken }, body: JSON.stringify({ year: me.year, semester: me.semester, profile_visibility: next ? 'public' : 'private' }) })
              setPriv(p => ({ ...p, profilePublic: next }))
            } catch { /* keep the previous value if saving fails */ }
            finally { setPrivacyBusy(false) }
          }} style={{ opacity: privacyBusy ? 0.6 : 1 }}>{Ic.toggle(priv.profilePublic)}</div>} sub={priv.profilePublic ? 'Public' : 'Private'} />
          <Row label="Who can message me" right={<div onClick={async e => {
            e.stopPropagation()
            if (privacyBusy) return
            const next = !priv.whoMessages
            setPrivacyBusy(true)
            try {
              const me = await api<{ year: number; semester: number }>('/me')
              await api('/profile', { method: 'PATCH', headers: { 'X-CSRF-Token': csrfToken }, body: JSON.stringify({ year: me.year, semester: me.semester, who_can_message: next ? 'everyone' : 'followers' }) })
              setPriv(p => ({ ...p, whoMessages: next }))
            } catch { /* keep previous value */ }
            finally { setPrivacyBusy(false) }
          }} style={{ opacity: privacyBusy ? 0.6 : 1 }}>{Ic.toggle(priv.whoMessages)}</div>} sub={priv.whoMessages ? 'Everyone' : 'Followers only'} />
          <Row label="Who can follow me" right={<div onClick={async e => {
            e.stopPropagation()
            if (privacyBusy) return
            const next = !priv.whoFollows
            setPrivacyBusy(true)
            try {
              const me = await api<{ year: number; semester: number }>('/me')
              await api('/profile', { method: 'PATCH', headers: { 'X-CSRF-Token': csrfToken }, body: JSON.stringify({ year: me.year, semester: me.semester, who_can_follow: next ? 'everyone' : 'approval_required' }) })
              setPriv(p => ({ ...p, whoFollows: next }))
            } catch { /* keep previous value */ }
            finally { setPrivacyBusy(false) }
          }} style={{ opacity: privacyBusy ? 0.6 : 1 }}>{Ic.toggle(priv.whoFollows)}</div>} sub={priv.whoFollows ? 'Everyone' : 'Approval required'} />
          <Row label="Read receipts" sub={priv.readReceipts ? 'Enabled' : 'Disabled'} right={<div onClick={async e => {
            e.stopPropagation()
            if (privacyBusy) return
            const next = !priv.readReceipts
            setPrivacyBusy(true)
            try {
              const me = await api<{ year: number; semester: number }>('/me')
              await api('/profile', { method: 'PATCH', headers: { 'X-CSRF-Token': csrfToken }, body: JSON.stringify({ year: me.year, semester: me.semester, read_receipts_enabled: next }) })
              setPriv(p => ({ ...p, readReceipts: next }))
            } catch { /* keep previous value */ }
            finally { setPrivacyBusy(false) }
          }} style={{ opacity: privacyBusy ? 0.6 : 1 }}>{Ic.toggle(priv.readReceipts)}</div>} />
          <Row label="Opportunity discovery" sub={opportunityDiscovery ? 'Opted in to relevant opportunities' : 'Not discoverable by organisations'} right={<div onClick={async e => {
            e.stopPropagation()
            if (privacyBusy) return
            const next = !opportunityDiscovery
            setPrivacyBusy(true)
            try {
              const res = await api<{ discoverable: boolean }>('/api/opportunity-discovery', { method: 'POST', headers: { 'X-CSRF-Token': csrfToken }, body: JSON.stringify({ discoverable: next }) })
              setOpportunityDiscovery(!!res.discoverable)
            } catch { /* keep previous value */ }
            finally { setPrivacyBusy(false) }
          }} style={{ opacity: privacyBusy ? 0.6 : 1 }}>{Ic.toggle(opportunityDiscovery)}</div>} />
        </Section>

        <Section title="Security">
          <Row label="Change Password" onPress={() => { setCurrentPassword(''); setNewPassword(''); setConfirmNewPassword(''); setPasswordChangeError(''); setPasswordChangeSuccess(false); setShowModal('change-password') }} />
          <Row label="Login Sessions" sub="1 active session" onPress={() => setShowModal('sessions')} />
          <Row label="Two-Factor Authentication" sub="Not enabled" onPress={() => setShowModal('2fa')} />
        </Section>

        <Section title="Subscription">
          <Row label="Subscription & Plan" sub="Free plan — Tap to upgrade" right={<Pill text="Upgrade" color={N.gold} />} onPress={() => setScreen('subscription')} />
          <Row label="Payment History" onPress={() => setScreen('payment-history')} />
        </Section>

        <Section title="Support">
          <Row label="Help Centre" onPress={() => setShowModal('help')} />
          <Row label="Contact Support" onPress={() => setShowModal('contact')} />
          <Row label="Report a Problem" onPress={() => setShowModal('report-problem')} />
        </Section>

        <Section title="About">
          <Row label="About Prepza" sub="v1.0.0 · Kenyatta University Launch" onPress={() => setShowModal('about')} />
          <Row label="Terms of Service" onPress={() => setShowModal('terms')} />
          <Row label="Privacy Policy" onPress={() => setShowModal('privacy-policy')} />
        </Section>

        <div style={{ margin: '8px 16px 0', background: T.card, borderRadius: 16, overflow: 'hidden' }}>
          <Row label="Log Out" danger onPress={() => setShowLogout(true)} right={<div style={{ color: '#C94C4C' }}>{Ic.logout()}</div>} />
        </div>
        <div style={{ margin: '10px 16px 0', background: T.card, borderRadius: 16, overflow: 'hidden' }}>
          <Row label="Delete Account" sub="Permanently delete your account and data" danger onPress={() => setShowDeleteConfirm(true)} />
        </div>
      </div>

      {/* Generic settings modal */}
      {showModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'flex-end', zIndex: 99 }}>
          <div style={{ background: T.card, borderRadius: '24px 24px 0 0', padding: '24px 20px 40px', width: '100%' }}>
            <div style={{ width: 40, height: 4, background: T.border, borderRadius: 99, margin: '0 auto 20px' }} />
            <div style={{ fontWeight: 800, fontSize: 17, color: N.navy, marginBottom: 8 }}>
              {showModal === 'email' ? 'Change Email' : showModal === 'phone' ? 'Change Phone' : showModal === 'university' ? 'Select University' : showModal === 'course' ? 'Select Course' : showModal === 'study-prefs' ? 'Study Preferences' : showModal === 'ai-prefs' ? 'AI Preferences' : showModal === 'language' ? 'Language' : showModal === 'appearance' ? 'Appearance' : showModal === 'change-password' ? 'Change Password' : showModal === 'sessions' ? 'Login Sessions' : showModal === '2fa' ? 'Two-Factor Authentication' : showModal === 'plan' ? 'Current Plan' : showModal === 'upgrade' ? 'Choose a plan' : showModal === 'billing' ? 'Billing' : showModal === 'help' ? 'Help Centre' : showModal === 'contact' ? 'Contact Support' : showModal === 'report-problem' ? 'Report a Problem' : showModal === 'about' ? 'About Prepza' : showModal === 'terms' ? 'Terms of Service' : 'Privacy Policy'}
            </div>
            {showModal === 'email' ? (
              emailChangeSuccess ? (
                <>
                  <div style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.65, marginBottom: 24 }}>We've sent a verification link to {newEmail.trim()}. Check your inbox to confirm the change.</div>
                  <button onClick={() => setShowModal(null)} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 14, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 14, color: N.navy }}>Got it</button>
                </>
              ) : (
                <>
                  <div style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.5, marginBottom: 16 }}>Enter your current password and your new email address.</div>
                  <input type="password" value={emailPassword} onChange={e => setEmailPassword(e.target.value)} placeholder="Current password" style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', marginBottom: 10, boxSizing: 'border-box', background: T.card, color: T.text }} />
                  <input type="email" value={newEmail} onChange={e => setNewEmail(e.target.value)} placeholder="New email address" style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', marginBottom: 12, boxSizing: 'border-box', background: T.card, color: T.text }} />
                  {emailChangeError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 12 }}>{emailChangeError}</div>}
                  <button onClick={submitChangeEmail} disabled={emailChangeBusy || !emailPassword || !newEmail.trim()} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 14, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 14, color: N.navy, marginBottom: 10, opacity: (emailChangeBusy || !emailPassword || !newEmail.trim()) ? 0.6 : 1 }}>{emailChangeBusy ? 'Saving…' : 'Save Email'}</button>
                  <button onClick={() => setShowModal(null)} style={{ width: '100%', background: themeMode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6', border: 'none', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 14, color: T.text }}>Cancel</button>
                </>
              )
            ) : showModal === 'change-password' ? (
              passwordChangeSuccess ? (
                <>
                  <div style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.65, marginBottom: 24 }}>Your password has been changed.</div>
                  <button onClick={() => setShowModal(null)} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 14, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 14, color: N.navy }}>Got it</button>
                </>
              ) : (
                <>
                  <input type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} placeholder="Current password" style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', marginBottom: 10, boxSizing: 'border-box', background: T.card, color: T.text }} />
                  <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="New password" style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', marginBottom: 10, boxSizing: 'border-box', background: T.card, color: T.text }} />
                  <input type="password" value={confirmNewPassword} onChange={e => setConfirmNewPassword(e.target.value)} placeholder="Confirm new password" style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', marginBottom: 12, boxSizing: 'border-box', background: T.card, color: T.text }} />
                  {passwordChangeError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 12 }}>{passwordChangeError}</div>}
                  <button onClick={submitChangePassword} disabled={passwordChangeBusy || !currentPassword || !newPassword} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 14, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 14, color: N.navy, marginBottom: 10, opacity: (passwordChangeBusy || !currentPassword || !newPassword) ? 0.6 : 1 }}>{passwordChangeBusy ? 'Saving…' : 'Save Password'}</button>
                  <button onClick={() => setShowModal(null)} style={{ width: '100%', background: themeMode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6', border: 'none', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 14, color: T.text }}>Cancel</button>
                </>
              )
            ) : (
              <>
                <div style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.65, marginBottom: 24 }}>
                  {showModal === 'terms' || showModal === 'privacy-policy' ? (
                    <div style={{ maxHeight: '50vh', overflowY: 'auto', whiteSpace: 'pre-wrap' }} className="scrollbar-hide">
                      {showModal === 'terms' ? TERMS_TEXT : PRIVACY_TEXT}
                    </div>
                  ) : showModal === 'upgrade' ? 'Paid plans provide larger study-generation allowances, offline study, and additional premium features. Your allowance is shown before you generate.' : showModal === 'about' ? `Prepza v1.0.0 — Kenyatta University Launch\n\nVision: ${PREPZA_VISION}\n\nMission: ${PREPZA_MISSION}` : showModal === 'help' ? 'Visit prepza.app/help or email support@prepza.app for assistance.' : 'This feature will be available in a future update. Stay tuned!'}
                </div>
                <button onClick={() => setShowModal(null)} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 14, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 14, color: N.navy }}>Got it</button>
              </>
            )}
          </div>
        </div>
      )}

      {/* Logout confirmation */}
      {showLogout && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 99 }}>
          <div style={{ background: T.card, borderRadius: 20, padding: 24, width: '100%' }}>
            <div style={{ fontSize: 32, textAlign: 'center', marginBottom: 12 }}>👋</div>
            <div style={{ fontWeight: 800, fontSize: 17, color: N.navy, textAlign: 'center', marginBottom: 8 }}>Log out of Prepza?</div>
            <div style={{ fontSize: 13, color: T.textMuted, textAlign: 'center', marginBottom: 24 }}>You'll need to sign in again to access your study materials.</div>
            <button onClick={() => { handleLogout() }} style={{ width: '100%', background: '#C94C4C', border: 'none', borderRadius: 14, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 14, color: '#fff', marginBottom: 10 }}>Log Out</button>
            <button onClick={() => setShowLogout(false)} style={{ width: '100%', background: themeMode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6', border: 'none', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 14, color: T.text }}>Cancel</button>
          </div>
        </div>
      )}

      {/* Delete account confirmation */}
      {showDeleteConfirm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 99 }}>
          <div style={{ background: T.card, borderRadius: 20, padding: 24, width: '100%' }}>
            <div style={{ fontSize: 32, textAlign: 'center', marginBottom: 12 }}>⚠️</div>
            <div style={{ fontWeight: 800, fontSize: 17, color: N.navy, textAlign: 'center', marginBottom: 8 }}>Delete your account?</div>
            <div style={{ fontSize: 13, color: T.textMuted, textAlign: 'center', marginBottom: 16 }}>This permanently deletes your account and cannot be undone. Your uploaded documents and study history will be lost.</div>
            {deleteError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, textAlign: 'center', marginBottom: 12 }}>{deleteError}</div>}
            <button onClick={handleDeleteAccount} disabled={deleting} style={{ width: '100%', background: '#C94C4C', border: 'none', borderRadius: 14, padding: '14px 0', cursor: deleting ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 14, color: '#fff', marginBottom: 10, opacity: deleting ? 0.7 : 1 }}>{deleting ? 'Deleting...' : 'Yes, Delete My Account'}</button>
            <button onClick={() => { setShowDeleteConfirm(false); setDeleteError('') }} disabled={deleting} style={{ width: '100%', background: themeMode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6', border: 'none', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 14, color: T.text }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

