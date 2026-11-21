import { useEffect, useState, type ComponentType } from 'react'
import { api, ApiError } from '../../lib/appApi'
import { PAYMENT_STATUS_META } from '../../lib/paymentStatus'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Pill from '../../ui/Pill'
import type { Screen } from '../../types/navigation'
import type { PaymentHistoryItem, SubscriptionPlan, SubscriptionStatus } from '../../types/billing'

type ScreenNavigationProps = { setScreen: (screen: Screen) => void }
type EmptyStateComponent = ComponentType<{ icon: string; title: string; sub: string; action?: string; onAction?: () => void }>
type ErrorStateComponent = ComponentType<{ onRetry?: () => void }>

type SubscriptionScreenProps = ScreenNavigationProps & {
  selectedPlan: string
  setSelectedPlan: (plan: string) => void
  ErrorState: ErrorStateComponent
}
type PaymentScreenProps = ScreenNavigationProps & { selectedPlan: string }
type PaymentHistoryScreenProps = ScreenNavigationProps & {
  EmptyState: EmptyStateComponent
  ErrorState: ErrorStateComponent
}

// ─── SUBSCRIPTION ─────────────────────────────────────────────────────────────
// Static display metadata (badges/colors/feature bullets) keyed by plan id -
// the backend only knows price/period, not marketing copy, so this stays
// client-side and is merged onto whatever plans GET /subscription/plans
// actually returns.
const SUBSCRIPTION_PLAN_META: Record<string, { badge?: string; badgeColor?: string; color: string }> = {
  free: { color: '#6B7280' },
  plus: { badge: 'Plus', badgeColor: N.gold, color: N.gold },
  pro: { badge: 'Pro', badgeColor: '#4CC97B', color: '#4C7BC9' },
}

function subscriptionFeatures(plan: SubscriptionPlan): string[] {
  const features = [
    'Morio — personalized AI study support',
    `${Number(plan.podcast_minutes || 0).toLocaleString()} podcast minutes`,
    `${Number(plan.summary_pages || 0).toLocaleString()} summary pages`,
    `${Number(plan.questions || 0).toLocaleString()} questions`,
    `${Number(plan.mind_map_nodes || 0).toLocaleString()} mind-map nodes`,
    `${Number(plan.flashcards || 0).toLocaleString()} flashcards`,
  ]
  if (plan.offline_study) features.push('Offline study')
  if (plan.premium_library) features.push('Premium library')
  if (plan.study_hub_uploads) features.push('Unlimited StudyHub uploads')
  return features
}

export function SubscriptionScreen({ setScreen, selectedPlan, setSelectedPlan, ErrorState }: SubscriptionScreenProps) {
  const { tokens: T } = useTheme()
  const [plans, setPlans] = useState<SubscriptionPlan[]>([])
  const [status, setStatus] = useState<SubscriptionStatus | null>(null)
  const [usage, setUsage] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true); setError('')
    Promise.all([
      api<{ plans: SubscriptionPlan[] }>('/subscription/plans'),
      api<SubscriptionStatus>('/subscription/status'),
      api('/api/usage/me'),
    ])
      .then(([plansRes, statusRes, usageRes]) => { setPlans(plansRes.plans); setStatus(statusRes); setUsage(usageRes) })
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load subscription plans - check your connection and try again.'))
      .finally(() => setLoading(false))
  }, [])

  const paidPlans = plans.filter(p => p.id !== 'free')
  const selected = paidPlans.find(p => p.id === selectedPlan) || paidPlans[0]

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => window.history.back()} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}><div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Prepza Plans</div><div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>Unlock all AI study tools</div></div>
        </div>
        <div style={{ marginTop: 16, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 14, padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 20 }}>🎓</span>
          <div style={{ flex: 1 }}>
            <div style={{ color: '#fff', fontWeight: 700, fontSize: 13 }}>
              {status ? `Current Plan: ${status.plan === 'plus' ? 'Plus' : status.plan === 'pro' ? 'Pro' : 'Free'}` : 'Loading plan…'}
            </div>
            <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11 }}>
              {status?.is_active && status.expires_at
                ? `Renews/expires ${new Date(status.expires_at).toLocaleDateString()}`
                : 'Upgrade to unlock everything'}
            </div>
          </div>
          {status && <Pill text={status.is_active ? 'Active' : status.plan === 'free' ? 'Free' : 'Expired'} color={status.is_active ? '#4CC97B' : T.textMuted} />}
        </div>
      </div>
      <div style={{ padding: '20px 18px' }}>
        {loading ? (
          <div style={{ fontSize: 13, color: T.textMuted, textAlign: 'center', padding: '30px 0' }}>Loading plans…</div>
        ) : error ? (
          <ErrorState />
        ) : (
          <>
            {plans.map(p => {
              const meta = SUBSCRIPTION_PLAN_META[p.id] || { color: T.textMuted }
              const isCurrent = status?.plan === p.id && status.is_active
              const isSelectable = p.id !== 'free'
              const isSelected = selected?.id === p.id
              return (
                <div key={p.id} onClick={() => isSelectable && setSelectedPlan(p.id)}
                  style={{ background: T.card, borderRadius: 18, padding: 18, marginBottom: 12, border: `2px solid ${isSelectable && isSelected ? meta.color : 'rgba(0,0,0,0.06)'}`, cursor: isSelectable ? 'pointer' : 'default', position: 'relative', boxShadow: isSelectable && isSelected ? `0 4px 20px ${meta.color}25` : '0 2px 8px rgba(0,0,0,0.05)', transition: 'all 0.2s' }}>
                  {meta.badge && <div style={{ position: 'absolute', top: -11, right: 16, background: meta.badgeColor, color: p.id === 'plus' ? N.navy : '#fff', fontSize: 10, fontWeight: 800, padding: '3px 10px', borderRadius: 99, fontFamily: 'Plus Jakarta Sans' }}>{meta.badge}</div>}
                  {isCurrent && <div style={{ position: 'absolute', top: -11, left: 16, background: '#E5E7EB', color: T.textMuted, fontSize: 10, fontWeight: 700, padding: '3px 10px', borderRadius: 99, fontFamily: 'Plus Jakarta Sans' }}>Current</div>}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                    <div>
                      <div style={{ fontWeight: 800, fontSize: 16, color: T.text }}>{p.name}</div>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 2, marginTop: 2 }}>
                        <span style={{ fontWeight: 800, fontSize: 22, color: meta.color }}>KES {p.price.toLocaleString()}</span>
                        <span style={{ fontSize: 11, color: T.textMuted }}>{p.period ? `/${p.period}` : ''}</span>
                      </div>
                    </div>
                    {isSelectable && (
                      <div style={{ width: 24, height: 24, borderRadius: '50%', border: `2px solid ${isSelected ? meta.color : T.textMuted}`, background: isSelected ? meta.color : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        {isSelected && <div style={{ color: p.id === 'plus' ? N.navy : '#fff' }}>{Ic.check('w-3 h-3')}</div>}
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                    {subscriptionFeatures(p).map((f, i) => (
                      <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <div style={{ width: 16, height: 16, borderRadius: '50%', background: `${meta.color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><div style={{ color: meta.color }}>{Ic.check('w-2.5 h-2.5')}</div></div>
                        <span style={{ fontSize: 12, color: '#4B5563' }}>{f}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
            <button onClick={() => selected && setScreen('payment')} disabled={!selected} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: selected ? 'pointer' : 'default', fontFamily: 'Plus Jakarta Sans', boxShadow: `0 6px 24px rgba(201,168,76,0.4)`, marginTop: 4, opacity: selected ? 1 : 0.6 }}>
              {selected ? `Upgrade — KES ${selected.price.toLocaleString()}` : 'Upgrade'}
            </button>
          </>
        )}
        {usage && (
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: 14, marginTop: 8 }}>
            <div style={{ fontWeight: 800, fontSize: 13, color: T.text, marginBottom: 10 }}>{usage.plan === 'free' ? 'Free allowance' : usage.plan === 'plus' ? 'Plus allowance' : 'Pro allowance'}</div>
            {(['summary', 'podcast', 'flashcards', 'quiz', 'mind_map'] as const).map(feature => {
              const labels: Record<string, string> = { summary: 'Summary', podcast: 'Podcast', flashcards: 'Flashcards', quiz: 'Questions', mind_map: 'Mind map' }
              const units: Record<string, string> = { summary: 'pages', podcast: 'min', flashcards: 'cards', quiz: 'questions', mind_map: 'nodes' }
              const item = usage.usage?.[feature]
              const used = Number(item?.units || 0)
              const remaining = Number(item?.remaining_units || 0)
              const max = Number(item?.unit_limit || 0)
              return <div key={feature} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 11, color: T.textMuted, marginTop: 7 }}>
                <span>{labels[feature]}</span>
                <span>{remaining}/{max} {units[feature]} remaining</span>
              </div>
            })}
          </div>
        )}

        <button onClick={() => setScreen('payment-history')} style={{ width: '100%', background: 'transparent', color: T.textMuted, fontSize: 12, fontWeight: 600, border: 'none', padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>View payment history</button>
        <div style={{ textAlign: 'center', fontSize: 11, color: T.textMuted, lineHeight: 1.6 }}>🔒 Secured payments via M-Pesa & card, powered by Paystack.</div>
      </div>
    </div>
  )
}

// ─── PAYMENT ──────────────────────────────────────────────────────────────────
// Paystack checkout: POST /subscription/upgrade returns a redirect_url
// to Paystack's hosted payment page. The current student purchase model is
// subscription-only; future one-off purchases are reserved for usage/add-on
// credits rather than ownership of individual Library content.
export function PaymentScreen({ setScreen, selectedPlan }: PaymentScreenProps) {
  const { tokens: T } = useTheme()
  const [phone, setPhone] = useState('')
  const [plan, setPlan] = useState<SubscriptionPlan | null>(null)
  const [loadingPlan, setLoadingPlan] = useState(true)
  const [redirecting, setRedirecting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api<{ plans: SubscriptionPlan[] }>('/subscription/plans')
      .then(res => setPlan(res.plans.find(p => p.id === selectedPlan) || null))
      .catch(() => setError('Could not load plan details.'))
      .finally(() => setLoadingPlan(false))
  }, [selectedPlan])

  const pay = async () => {
    if (redirecting) return
    setError('')
    setRedirecting(true)
    try {
      const me = await api<{ csrf_token: string }>('/me')
      const res = await api<{ redirect_url: string; order_tracking_id: string; merchant_reference: string }>('/subscription/upgrade', {
        method: 'POST',
        headers: { 'X-CSRF-Token': me.csrf_token },
        body: JSON.stringify({ plan: selectedPlan, phone_number: phone.trim() || undefined }),
      })
      window.location.href = res.redirect_url
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not start checkout - please try again.')
      setRedirecting(false)
    }
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 20px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <button onClick={() => setScreen('subscription')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Checkout</div>
        </div>
        <div style={{ background: 'rgba(255,255,255,0.08)', borderRadius: 14, padding: '14px 16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ color: 'rgba(255,255,255,0.7)', fontSize: 13 }}>{plan ? `Prepza ${plan.name} Plan` : 'Loading plan…'}</span>
            <span style={{ color: N.gold, fontWeight: 800 }}>{plan ? `KES ${plan.price.toLocaleString()}` : '—'}</span>
          </div>
          <div style={{ height: 1, background: 'rgba(255,255,255,0.1)', marginBottom: 8 }} />
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: '#fff', fontWeight: 700, fontSize: 14 }}>Total</span>
            <span style={{ color: '#fff', fontWeight: 800, fontSize: 16 }}>{plan ? `KES ${plan.price.toLocaleString()}` : '—'}</span>
          </div>
        </div>
      </div>
      {redirecting ? (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 20, padding: '0 32px', textAlign: 'center' }}>
          <div style={{ width: 72, height: 72, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 36, animation: 'pulse-gold 2s infinite' }}>🔒</div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 17, color: T.text, marginBottom: 8 }}>Taking you to secure checkout…</div>
            <div style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.65 }}>You'll complete payment on Paystack's secure page, then return to Prepza.</div>
          </div>
        </div>
      ) : (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
          {error && (
            <div style={{ background: 'rgba(201,68,68,0.08)', border: '1px solid rgba(201,68,68,0.25)', borderRadius: 12, padding: '12px 14px', color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 16 }}>{error}</div>
          )}
          <div style={{ background: T.card, borderRadius: 16, padding: 18, marginBottom: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
              <div style={{ width: 40, height: 40, background: '#4CC97B20', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>📱</div>
              <div><div style={{ fontWeight: 700, fontSize: 14, color: T.text }}>M-Pesa number</div><div style={{ fontSize: 11, color: T.textMuted }}>Optional - helps prefill checkout where supported</div></div>
            </div>
            <input value={phone} onChange={e => setPhone(e.target.value)} placeholder="07XX XXX XXX" style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 15, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, boxSizing: 'border-box', letterSpacing: 0.5 }} />
          </div>
          <button onClick={pay} disabled={loadingPlan || !plan} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: (loadingPlan || !plan) ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 6px 24px rgba(201,168,76,0.4)', opacity: (loadingPlan || !plan) ? 0.6 : 1 }}>
            {plan ? `Continue to Payment — KES ${plan.price.toLocaleString()}` : 'Loading…'}
          </button>
          <div style={{ textAlign: 'center', marginTop: 12, fontSize: 11, color: T.textMuted }}>🔒 Secured by Paystack (M-Pesa & card)</div>
        </div>
      )}
    </div>
  )
}

export function PaymentSuccessScreen({ setScreen }: ScreenNavigationProps) {
  const { tokens: T } = useTheme()
  const [payment, setPayment] = useState<PaymentHistoryItem | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    api<{ payments: PaymentHistoryItem[] }>('/payment-history')
      .then(res => setPayment(res.payments[0] || null))
      .catch(() => setLoadError('Could not load your payment details.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const t = setTimeout(() => setScreen('home'), 6000)
    return () => clearTimeout(t)
  }, [])

  const itemLabel = payment
    ? (payment.plan === 'plus' ? 'Plus Plan' : payment.plan === 'pro' ? 'Pro Plan' : 'Prepza Subscription')
    : null

  const detailRows: [string, string][] = payment
    ? [
        ['Item', itemLabel || '—'],
        ['Amount', `KES ${payment.amount.toLocaleString()}`],
        ['Status', payment.status.charAt(0).toUpperCase() + payment.status.slice(1)],
        ...(payment.reference ? ([['Reference', payment.reference]] as [string, string][]) : []),
      ]
    : []

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: T.pageBg, padding: '0 28px', textAlign: 'center', gap: 20 }}>
      <div style={{ width: 80, height: 80, background: 'rgba(76,201,123,0.12)', borderRadius: '50%', border: '3px solid #4CC97B', display: 'flex', alignItems: 'center', justifyContent: 'center', animation: 'fadeSlideUp 0.5s ease both' }}>
        <div style={{ color: '#4CC97B' }}>{Ic.check('w-10 h-10')}</div>
      </div>
      <div>
        <div style={{ fontWeight: 800, fontSize: 22, color: T.text, marginBottom: 8 }}>Payment Successful! 🎉</div>
        <div style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.7 }}>
          {itemLabel
            ? `Your ${itemLabel} payment has gone through — your plan entitlements are now active.`
            : 'Your payment has gone through. Welcome to Prepza.'}
        </div>
      </div>
      {loading ? (
        <div style={{ fontSize: 12, color: T.textMuted }}>Loading your payment details…</div>
      ) : loadError ? (
        <div style={{ fontSize: 12, color: T.textMuted }}>{loadError} You can check <span onClick={() => setScreen('payment-history')} style={{ color: N.gold, fontWeight: 700, cursor: 'pointer' }}>Payment History</span> for details.</div>
      ) : payment && (
        <div style={{ background: T.card, borderRadius: 16, padding: '16px 20px', width: '100%', boxShadow: '0 2px 8px rgba(0,0,0,0.06)', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {detailRows.map(([k, v]) => (
            <div key={k} style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 12, color: T.textMuted }}>{k}</span>
              <span style={{ fontSize: 12, fontWeight: 700, color: T.text, fontFamily: k === 'Reference' ? 'monospace' : 'Plus Jakarta Sans' }}>{v}</span>
            </div>
          ))}
        </div>
      )}
      <button onClick={() => setScreen('home')} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 6px 24px rgba(201,168,76,0.4)' }}>
        Start Studying
      </button>
      <div style={{ fontSize: 11, color: T.textMuted }}>Redirecting to home in a moment…</div>
    </div>
  )
}

export function PaymentFailureScreen({ setScreen }: ScreenNavigationProps) {
  const { tokens: T } = useTheme()
  const [payment, setPayment] = useState<PaymentHistoryItem | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api<{ payments: PaymentHistoryItem[] }>('/payment-history')
      .then(res => setPayment(res.payments[0] || null))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const isPending = payment?.status === 'pending'

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: T.pageBg, padding: '0 28px', textAlign: 'center', gap: 20 }}>
      <div style={{ width: 80, height: 80, background: isPending ? 'rgba(217,119,6,0.1)' : 'rgba(201,76,76,0.1)', borderRadius: '50%', border: `3px solid ${isPending ? '#D97706' : '#C94C4C'}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {isPending ? <span style={{ fontSize: 32 }}>⏳</span> : <div style={{ color: '#C94C4C' }}>{Ic.close('w-9 h-9')}</div>}
      </div>
      <div>
        <div style={{ fontWeight: 800, fontSize: 22, color: T.text, marginBottom: 8 }}>{isPending ? 'Payment Still Processing' : 'Payment Failed'}</div>
        <div style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.7 }}>
          {isPending
            ? "We haven't received final confirmation yet. This can take a minute — check Payment History shortly, or try again if it doesn't update."
            : 'Your payment was cancelled or could not be completed. Please try again or use a different payment method.'}
        </div>
      </div>
      {!loading && !isPending && (
        <div style={{ background: T.card, borderRadius: 16, padding: '14px 18px', width: '100%', border: '1px solid rgba(201,76,76,0.2)', textAlign: 'left' }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#C94C4C', marginBottom: 8 }}>Common reasons:</div>
          {['Insufficient M-Pesa balance or card funds', 'Incorrect PIN or OTP entered', 'Payment request timed out', 'Card declined by your bank'].map((r, i) => (
            <div key={i} style={{ fontSize: 12, color: T.textMuted, marginBottom: 4 }}>• {r}</div>
          ))}
        </div>
      )}
      <button onClick={() => setScreen('subscription')} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Try Again</button>
      <button onClick={() => setScreen('payment-history')} style={{ width: '100%', background: 'transparent', color: T.textMuted, fontWeight: 600, fontSize: 13, border: '1.5px solid rgba(0,0,0,0.1)', borderRadius: 16, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Check Payment History</button>
    </div>
  )
}

export function PaymentHistoryScreen({ setScreen, EmptyState, ErrorState }: PaymentHistoryScreenProps) {
  const { tokens: T } = useTheme()
  const [payments, setPayments] = useState<PaymentHistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api<{ payments: PaymentHistoryItem[] }>('/payment-history')
      .then(res => setPayments(res.payments))
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load payment history - check your connection and try again.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => window.history.back()} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Payment History</div>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 18px' }} className="scrollbar-hide">
        {loading ? (
          <div style={{ fontSize: 13, color: T.textMuted, textAlign: 'center', padding: '30px 0' }}>Loading…</div>
        ) : error ? (
          <ErrorState />
        ) : payments.length === 0 ? (
          <EmptyState icon="💳" title="No payments yet" sub="Your Prepza subscription payments will show up here." />
        ) : payments.map(p => {
          const meta = PAYMENT_STATUS_META[p.status] || { icon: '•', color: T.textMuted, label: p.status }
          const label = p.plan === 'plus' ? 'Plus Plan'
            : p.plan === 'pro' ? 'Pro Plan'
            : p.payment_type === 'addon' ? 'Usage add-on'
            : 'Prepza Subscription'
          return (
            <div key={p.id} style={{ background: T.card, borderRadius: 16, padding: '14px 16px', marginBottom: 10, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', display: 'flex', gap: 12, alignItems: 'center' }}>
              <div style={{ width: 44, height: 44, background: `${meta.color}18`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0 }}>{meta.icon}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: T.text }} className="line-clamp-1">{label}</div>
                <div style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>{p.created_at ? new Date(p.created_at).toLocaleDateString() : ''}{p.provider ? ` · ${p.provider.charAt(0).toUpperCase()}${p.provider.slice(1)}` : ''}</div>
                {p.reference && <div style={{ fontSize: 10, color: T.textMuted, fontFamily: 'monospace', marginTop: 2 }}>{p.reference}</div>}
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontWeight: 800, fontSize: 14, color: T.text, marginBottom: 4 }}>KES {p.amount.toLocaleString()}</div>
                <Pill text={meta.label} color={meta.color} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
