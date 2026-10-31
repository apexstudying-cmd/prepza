import { useEffect, useState } from 'react'
import { api } from '../../lib/appApi'
import { useTheme } from '../../theme/theme'

const AMB_COLORS = { navy: '#0B1437', navy3: '#1A2A5E', gold: '#C9A84C', goldLight: '#E8C97E', bg: '#F8F9FC', green: '#16A34A', red: '#C94C4C', gray: '#9CA3AF' }

interface AmbassadorStatusResp {
  enrolled: boolean
  status?: 'pending' | 'active' | 'suspended' | 'rejected'
  referral_code?: string
  applied_at?: string
  rejection_reason?: string | null
}
interface AmbassadorDashboardResp {
  referral_code: string
  referral_link: string
  status: 'active' | 'suspended'
  tier: number
  commission_pct: number
  next_tier_at: number | null
  funnel: { referred: number; verified: number; activated: number; paying: number; conversion_rate: number }
  earnings: { pending_kes: number; available_kes: number; paid_kes: number }
  min_payout_kes: number
  payout_hold_days: number
}
interface AmbassadorReferral {
  id: number
  status: 'signed_up' | 'verified' | 'activated'
  channel: string | null
  converted: boolean
  commission_amount: number | null
  voided: boolean
  created_at: string
}
interface AmbassadorPayout {
  id: number
  amount: number
  status: 'pending' | 'approved' | 'rejected' | 'paid'
  payout_destination: string
  requested_at: string
  rejection_reason: string | null
}

const AMB_STATUS_META: Record<string, { label: string; color: string }> = {
  signed_up: { label: 'Signed up', color: AMB_COLORS.gray },
  verified: { label: 'Verified', color: '#4C7BC9' },
  activated: { label: 'Activated', color: AMB_COLORS.green },
}
const AMB_PAYOUT_META: Record<string, { label: string; color: string }> = {
  pending: { label: 'Pending', color: AMB_COLORS.gold },
  approved: { label: 'Approved', color: '#4C7BC9' },
  paid: { label: 'Paid', color: AMB_COLORS.green },
  rejected: { label: 'Rejected', color: AMB_COLORS.red },
}
function amPill(text: string, color: string) {
  return <span style={{ display: 'inline-block', fontSize: 10, fontWeight: 700, color, background: color + '20', border: `1px solid ${color}55`, borderRadius: 99, padding: '2px 9px' }}>{text}</span>
}
function fmtKes(n: number) {
  return 'KES ' + Math.round(n).toLocaleString('en-KE')
}

export default function AmbassadorScreen({ setScreen }: { setScreen: (s: 'profile') => void }) {
  const { tokens: T } = useTheme()
  const [csrfToken, setCsrfToken] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [statusData, setStatusData] = useState<AmbassadorStatusResp | null>(null)
  const [dashboard, setDashboard] = useState<AmbassadorDashboardResp | null>(null)
  const [referrals, setReferrals] = useState<AmbassadorReferral[]>([])
  const [payouts, setPayouts] = useState<AmbassadorPayout[]>([])
  const [tab, setTab] = useState<'overview' | 'referrals' | 'payouts'>('overview')
  const [applying, setApplying] = useState(false)
  const [copied, setCopied] = useState(false)
  const [showSheet, setShowSheet] = useState(false)
  const [payoutPhone, setPayoutPhone] = useState('')
  const [payoutError, setPayoutError] = useState('')
  const [submittingPayout, setSubmittingPayout] = useState(false)

  const loadAll = () => {
    setLoadError('')
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
    api<AmbassadorStatusResp>('/ambassador/status')
      .then(async status => {
        setStatusData(status)
        if (status.enrolled && (status.status === 'active' || status.status === 'suspended')) {
          const [d, r, p] = await Promise.all([
            api<AmbassadorDashboardResp>('/ambassador/dashboard'),
            api<{ referrals: AmbassadorReferral[] }>('/ambassador/referrals?page=1'),
            api<{ payouts: AmbassadorPayout[] }>('/ambassador/payouts'),
          ])
          setDashboard(d)
          setReferrals(r.referrals)
          setPayouts(p.payouts)
        }
      })
      .catch((e: any) => setLoadError(e?.message || 'Could not load the Ambassador program right now.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadAll() }, [])

  const handleApply = async () => {
    setApplying(true)
    try {
      await api('/ambassador/apply', { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      setLoading(true)
      loadAll()
    } catch (e: any) {
      alert(e?.message || 'Could not submit application.')
    } finally {
      setApplying(false)
    }
  }

  const copyLink = () => {
    if (!dashboard) return
    navigator.clipboard?.writeText(dashboard.referral_link).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    })
  }

  const shareLink = async () => {
    if (!dashboard) return
    const text = `Study smarter with Prepza - sign up with my link: ${dashboard.referral_link}`
    if ((navigator as any).share) {
      try { await (navigator as any).share({ text, url: dashboard.referral_link }) } catch {}
    } else {
      copyLink()
    }
  }

  const requestPayout = async () => {
    if (!/^\+?\d{9,15}$/.test(payoutPhone.trim())) {
      setPayoutError('Enter a valid phone number (e.g. +254712345678).')
      return
    }
    setSubmittingPayout(true)
    setPayoutError('')
    try {
      await api('/ambassador/payouts/request', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ payout_destination: payoutPhone.trim() }),
      })
      setShowSheet(false)
      loadAll()
    } catch (e: any) {
      setPayoutError(e?.message || 'Could not submit the payout request.')
    } finally {
      setSubmittingPayout(false)
    }
  }

  const Header = ({ title }: { title: string }) => (
    <div style={{ background: AMB_COLORS.navy, padding: '0 18px 16px', flexShrink: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', color: '#fff' }}>‹</button>
        <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>{title}</div>
      </div>
    </div>
  )

  if (loading) return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: AMB_COLORS.bg }}>
      <Header title="Ambassador Program" />
      <div style={{ padding: 40, textAlign: 'center', color: AMB_COLORS.gray, fontSize: 13 }}>Loading…</div>
    </div>
  )

  if (loadError && !statusData) return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: AMB_COLORS.bg }}>
      <Header title="Ambassador Program" />
      <div style={{ padding: 40, textAlign: 'center' }}>
        <div style={{ fontSize: 13, color: AMB_COLORS.gray, marginBottom: 14 }}>{loadError}</div>
        <button onClick={() => { setLoading(true); loadAll() }} style={{ background: AMB_COLORS.gold, color: AMB_COLORS.navy, border: 'none', borderRadius: 12, padding: '12px 24px', fontWeight: 800, fontSize: 13, cursor: 'pointer' }}>Retry</button>
      </div>
    </div>
  )

  const enrolled = statusData?.enrolled ?? false
  const appStatus = statusData?.status

  if (!enrolled || appStatus === 'rejected') return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: AMB_COLORS.bg }}>
      <Header title="Ambassador Program" />
      <div style={{ flex: 1, overflowY: 'auto', padding: 18 }}>
        <div style={{ background: `linear-gradient(135deg,${AMB_COLORS.navy},${AMB_COLORS.navy3})`, borderRadius: 20, padding: 22, marginBottom: 16, textAlign: 'center' }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>🤝</div>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff', marginBottom: 6 }}>Earn by sharing Prepza</div>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)', lineHeight: 1.6 }}>Get a personal referral link. Earn a one-time commission on every friend's first payment.</div>
        </div>
        {appStatus === 'rejected' && (
          <div style={{ background: '#FEE2E2', border: '1px solid #FCA5A5', borderRadius: 14, padding: 14, marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 12, color: '#B91C1C', marginBottom: 4 }}>Previous application declined</div>
            {!!statusData?.rejection_reason && <div style={{ fontSize: 12, color: '#991B1B' }}>{statusData.rejection_reason}</div>}
          </div>
        )}
        <div style={{ fontWeight: 700, fontSize: 13, color: AMB_COLORS.navy, marginBottom: 10 }}>Commission tiers</div>
        <div style={{ background: T.card, borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', marginBottom: 20 }}>
          {[[1, 10, '0–4 paying referrals'], [2, 15, '5–19 paying referrals'], [3, 20, '20+ paying referrals']].map(([t, pct, range], i) => (
            <div key={t as number} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px', borderBottom: i < 2 ? '1px solid #F3F4F6' : 'none' }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: AMB_COLORS.gold + '18', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, color: AMB_COLORS.gold }}>T{t}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: AMB_COLORS.navy }}>{pct}% commission</div>
                <div style={{ fontSize: 11, color: AMB_COLORS.gray }}>{range}</div>
              </div>
            </div>
          ))}
        </div>
        <button onClick={handleApply} disabled={applying} style={{ width: '100%', padding: '15px 0', fontSize: 14, background: AMB_COLORS.gold, color: AMB_COLORS.navy, border: 'none', borderRadius: 14, fontWeight: 800, cursor: applying ? 'default' : 'pointer', opacity: applying ? 0.7 : 1 }}>
          {applying ? 'Submitting…' : (appStatus === 'rejected' ? 'Reapply' : 'Apply to become an ambassador')}
        </button>
      </div>
    </div>
  )

  if (appStatus === 'pending') return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: AMB_COLORS.bg }}>
      <Header title="Ambassador Program" />
      <div style={{ padding: 18 }}>
        <div style={{ background: T.card, borderRadius: 18, padding: 26, textAlign: 'center', boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
          <div style={{ fontSize: 32, marginBottom: 10 }}>⏳</div>
          <div style={{ fontWeight: 800, fontSize: 16, color: AMB_COLORS.navy, marginBottom: 6 }}>Application under review</div>
          <div style={{ fontSize: 12, color: AMB_COLORS.gray, lineHeight: 1.6 }}>We're reviewing your application - usually within 1-2 days.</div>
        </div>
      </div>
    </div>
  )

  if (!dashboard) return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: AMB_COLORS.bg }}>
      <Header title="Ambassador Program" />
      <div style={{ padding: 40, textAlign: 'center', color: AMB_COLORS.gray, fontSize: 13 }}>Loading dashboard…</div>
    </div>
  )

  const canRequestPayout = dashboard.status === 'active' && dashboard.earnings.available_kes >= dashboard.min_payout_kes
  const tierPct = dashboard.next_tier_at ? Math.min(100, (dashboard.funnel.paying / dashboard.next_tier_at) * 100) : 100

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: AMB_COLORS.bg }}>
      <Header title="Ambassador Program" />
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {dashboard.status === 'suspended' && (
          <div style={{ margin: '14px 18px', background: '#FEF3C7', border: '1px solid #FDE68A', borderRadius: 14, padding: '12px 14px' }}>
            <div style={{ fontWeight: 700, fontSize: 12, color: '#92400E', marginBottom: 2 }}>Account suspended</div>
            <div style={{ fontSize: 11, color: '#92400E' }}>Existing commissions are safe, but new payout requests are disabled.</div>
          </div>
        )}
        <div style={{ margin: '14px 18px', background: `linear-gradient(135deg,${AMB_COLORS.navy},${AMB_COLORS.navy3})`, borderRadius: 18, padding: 18 }}>
          <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginBottom: 6 }}>Your referral link</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 12, padding: '10px 12px', marginBottom: 10 }}>
            <div style={{ flex: 1, fontSize: 12, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{dashboard.referral_link}</div>
            <button onClick={copyLink} style={{ color: AMB_COLORS.gold, background: 'none', border: 'none', cursor: 'pointer', fontSize: 11, fontWeight: 700 }}>{copied ? 'Copied ✓' : 'Copy'}</button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '112px 1fr', gap: 12, alignItems: 'center', marginBottom: 10 }}>
            <div style={{ background:'#fff', borderRadius:14, padding:7, display:'flex', alignItems:'center', justifyContent:'center' }}>
              <img src="/ambassador/referral-qr" alt="Your Prepza ambassador QR code" style={{ width:98, height:98, display:'block' }} />
            </div>
            <div>
              <div style={{ fontSize:11, color:'rgba(255,255,255,.62)', lineHeight:1.5 }}>Print this QR code or place it on posters. Every scan opens your referral link.</div>
              <a href="/ambassador/referral-qr" download={`prepza-ambassador-${dashboard.referral_code}.svg`} style={{ display:'inline-block', marginTop:9, color:AMB_COLORS.gold, fontSize:11, fontWeight:800, textDecoration:'none' }}>Save QR code</a>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={shareLink} style={{ flex: 1, background: `linear-gradient(135deg,${AMB_COLORS.gold},${AMB_COLORS.goldLight})`, color: AMB_COLORS.navy, border: 'none', borderRadius: 12, padding: '11px 0', fontWeight: 800, fontSize: 12, cursor: 'pointer' }}>Share link</button>
            <div style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 12, padding: '11px 14px', display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)' }}>Code</span>
              <span style={{ fontSize: 12, fontWeight: 800, color: AMB_COLORS.gold }}>{dashboard.referral_code}</span>
            </div>
          </div>
        </div>
        <div style={{ margin: '0 18px 14px', background: T.card, borderRadius: 16, padding: 16, boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <div>
              <div style={{ fontWeight: 800, fontSize: 15, color: AMB_COLORS.navy }}>Tier {dashboard.tier} · {dashboard.commission_pct}% commission</div>
              <div style={{ fontSize: 11, color: AMB_COLORS.gray }}>{dashboard.next_tier_at ? `${Math.max(0, dashboard.next_tier_at - dashboard.funnel.paying)} more paying referrals to Tier ${dashboard.tier + 1}` : 'Top tier reached'}</div>
            </div>
            {amPill(`${dashboard.funnel.paying} paying`, AMB_COLORS.gold)}
          </div>
          {!!dashboard.next_tier_at && (
            <div style={{ background: '#F3F4F6', borderRadius: 99, height: 7, overflow: 'hidden' }}>
              <div style={{ background: `linear-gradient(90deg,${AMB_COLORS.gold},${AMB_COLORS.goldLight})`, height: 7, width: `${tierPct}%`, borderRadius: 99 }} />
            </div>
          )}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8, margin: '0 18px 14px' }}>
          {[['Pending', dashboard.earnings.pending_kes, AMB_COLORS.gray], ['Available', dashboard.earnings.available_kes, AMB_COLORS.green], ['Paid out', dashboard.earnings.paid_kes, AMB_COLORS.navy]].map(([label, val, color]) => (
            <div key={label as string} style={{ background: T.card, borderRadius: 14, padding: '12px 6px', textAlign: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
              <div style={{ fontWeight: 800, fontSize: 13, color: color as string }}>{fmtKes(val as number)}</div>
              <div style={{ fontSize: 10, color: AMB_COLORS.gray, fontWeight: 600, marginTop: 2 }}>{label as string}</div>
            </div>
          ))}
        </div>
        <div style={{ margin: '0 18px 16px' }}>
          <button onClick={() => canRequestPayout && setShowSheet(true)} disabled={!canRequestPayout} style={{ width: '100%', padding: '13px 0', fontSize: 13, background: AMB_COLORS.gold, color: AMB_COLORS.navy, border: 'none', borderRadius: 14, fontWeight: 800, opacity: canRequestPayout ? 1 : 0.5, cursor: canRequestPayout ? 'pointer' : 'not-allowed' }}>
            {canRequestPayout ? `Request payout — ${fmtKes(dashboard.earnings.available_kes)}` : dashboard.status === 'suspended' ? 'Payouts disabled while suspended' : `Min. payout is ${fmtKes(dashboard.min_payout_kes)}`}
          </button>
          <div style={{ fontSize: 10, color: T.textMuted, textAlign: 'center', marginTop: 8 }}>Commissions unlock {dashboard.payout_hold_days} days after the qualifying payment</div>
        </div>
        <div style={{ margin: '0 18px', background: T.card, borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
          <div style={{ display: 'flex', borderBottom: '1px solid rgba(0,0,0,0.06)' }}>
            {(['overview', 'referrals', 'payouts'] as const).map(t => (
              <button key={t} onClick={() => setTab(t)} style={{ flex: 1, padding: '11px 0', background: 'none', border: 'none', fontWeight: tab === t ? 800 : 500, fontSize: 11, color: tab === t ? AMB_COLORS.navy : AMB_COLORS.gray, cursor: 'pointer', borderBottom: tab === t ? `2px solid ${AMB_COLORS.gold}` : '2px solid transparent' }}>
                {t === 'overview' ? 'Funnel' : t === 'referrals' ? 'Referrals' : 'Payouts'}
              </button>
            ))}
          </div>
          <div style={{ padding: 14 }}>
            {tab === 'overview' && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 10 }}>
                {[['Referred', dashboard.funnel.referred], ['Verified', dashboard.funnel.verified], ['Activated', dashboard.funnel.activated], ['Paying', dashboard.funnel.paying]].map(([label, val]) => (
                  <div key={label as string} style={{ background: AMB_COLORS.bg, borderRadius: 12, padding: 12 }}>
                    <div style={{ fontWeight: 800, fontSize: 18, color: AMB_COLORS.navy }}>{val as number}</div>
                    <div style={{ fontSize: 10, color: AMB_COLORS.gray, fontWeight: 600 }}>{label as string}</div>
                  </div>
                ))}
                <div style={{ gridColumn: '1 / -1', background: AMB_COLORS.gold + '12', borderRadius: 12, padding: 12, textAlign: 'center' }}>
                  <span style={{ fontSize: 11, color: T.textMuted }}>Signup → paying conversion: </span>
                  <span style={{ fontWeight: 800, fontSize: 12, color: AMB_COLORS.gold }}>{dashboard.funnel.conversion_rate}%</span>
                </div>
              </div>
            )}
            {tab === 'referrals' && (
              <div>
                {referrals.length === 0 && <div style={{ fontSize: 12, color: AMB_COLORS.gray, textAlign: 'center', padding: '20px 0' }}>No referrals yet - share your link to get started.</div>}
                {referrals.map((r, i) => {
                  const meta = AMB_STATUS_META[r.status]
                  return (
                    <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 0', borderBottom: i < referrals.length - 1 ? '1px solid #F3F4F6' : 'none' }}>
                      <div style={{ width: 34, height: 34, borderRadius: 10, background: meta.color + '18', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15 }}>{r.channel === 'whatsapp' ? '💬' : r.channel === 'instagram' ? '📸' : r.channel === 'tiktok' ? '🎵' : '🔗'}</div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: AMB_COLORS.navy }}>Referral #{r.id}{r.channel ? ` · via ${r.channel}` : ''}</div>
                        <div style={{ fontSize: 10, color: AMB_COLORS.gray }}>{r.created_at}{r.voided ? ' · voided (refunded)' : ''}</div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        {r.converted && !r.voided ? <div style={{ fontWeight: 800, fontSize: 12, color: '#16A34A', marginBottom: 3 }}>+{fmtKes(r.commission_amount || 0)}</div> : <div style={{ height: 15 }} />}
                        {amPill(r.voided ? 'Voided' : meta.label, r.voided ? AMB_COLORS.red : meta.color)}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
            {tab === 'payouts' && (
              <div>
                {payouts.length === 0 && <div style={{ fontSize: 12, color: AMB_COLORS.gray, textAlign: 'center', padding: '20px 0' }}>No payout requests yet.</div>}
                {payouts.map((p, i) => {
                  const meta = AMB_PAYOUT_META[p.status]
                  return (
                    <div key={p.id} style={{ padding: '10px 0', borderBottom: i < payouts.length - 1 ? '1px solid #F3F4F6' : 'none' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 3 }}>
                        <span style={{ fontWeight: 800, fontSize: 13, color: AMB_COLORS.navy }}>{fmtKes(p.amount)}</span>
                        {amPill(meta.label, meta.color)}
                      </div>
                      <div style={{ fontSize: 10, color: AMB_COLORS.gray }}>{p.payout_destination} · requested {p.requested_at}</div>
                      {p.status === 'rejected' && !!p.rejection_reason && <div style={{ fontSize: 10, color: AMB_COLORS.red, marginTop: 3 }}>{p.rejection_reason}</div>}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
        <div style={{ height: 24 }} />
      </div>
      {showSheet && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'flex-end', zIndex: 99 }}>
          <div style={{ background: T.card, borderRadius: '24px 24px 0 0', padding: '24px 20px 36px', width: '100%' }}>
            <div style={{ width: 40, height: 4, background: '#E5E7EB', borderRadius: 99, margin: '0 auto 20px' }} />
            <div style={{ fontWeight: 800, fontSize: 16, color: AMB_COLORS.navy, marginBottom: 4 }}>Request payout</div>
            <div style={{ fontSize: 12, color: AMB_COLORS.gray, marginBottom: 18 }}>Available balance: {fmtKes(dashboard.earnings.available_kes)}</div>
            <div style={{ fontSize: 11, fontWeight: 700, color: T.textMuted, marginBottom: 6 }}>M-Pesa number</div>
            <input value={payoutPhone} onChange={e => setPayoutPhone(e.target.value)} placeholder="+254712345678" style={{ width: '100%', boxSizing: 'border-box', background: AMB_COLORS.bg, border: '1px solid #E5E7EB', borderRadius: 12, padding: '13px 14px', fontSize: 13, color: AMB_COLORS.navy, marginBottom: 8 }} />
            {!!payoutError && <div style={{ fontSize: 11, color: AMB_COLORS.red, marginBottom: 10 }}>{payoutError}</div>}
            <button onClick={requestPayout} disabled={submittingPayout} style={{ width: '100%', padding: '14px 0', fontSize: 14, background: AMB_COLORS.gold, color: AMB_COLORS.navy, border: 'none', borderRadius: 14, fontWeight: 800, cursor: 'pointer', opacity: submittingPayout ? 0.7 : 1 }}>
              {submittingPayout ? 'Submitting…' : 'Confirm request'}
            </button>
            <button onClick={() => setShowSheet(false)} style={{ width: '100%', background: 'none', border: 'none', padding: '12px 0', marginTop: 4, cursor: 'pointer', fontWeight: 700, fontSize: 13, color: AMB_COLORS.gray }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}
