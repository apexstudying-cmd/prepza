import * as React from 'react'
import { useEffect, useState, useRef, type ChangeEvent } from 'react'
import { api, ApiError } from '../lib/appApi'
import { N, useTheme, currentThemeMode, DARK_THEME } from '../theme/theme'
import { Ic } from '../ui/icons'
import Pill from '../ui/Pill'
import { AdminBadge, AdminBarChart, AdminLineChart, AdminKPI, AdminTable, AdminCard } from './AdminShared'
import type { AdminLibraryQueueItem, AdminLibraryReportItem, AdminInfrastructure, AdminStorageCapacity, AdminSystemCapacity, AdminUniversityEngagement, AdminAnalytics, AdminContentReport, AdminModerationSummary, AdminPlatformSettings, AdminAuditLogEntry, AdminContentMaterial, AdminAiUsage, AdminAiJob, AdminPayment, AdminUserRow, AdminAnnouncementItem } from './AdminShared'

interface AdminAmbassadorRow {
  id: number
  user_id: number
  email: string | null
  display_name: string | null
  referral_code: string
  status: 'pending' | 'active' | 'suspended' | 'rejected'
  applied_at: string | null
  reviewed_at: string | null
  rejection_reason: string | null
}

interface AdminAmbassadorReferralRow {
  id: number
  referred_email: string | null
  status: string
  channel: string | null
  converted: boolean
  commission_amount: number | null
  unlock_at: string | null
  voided: boolean
  void_reason: string | null
  created_at: string | null
}

interface AdminAmbassadorDetail extends AdminAmbassadorRow {
  reviewed_by: number | null
  referred_count: number
  paying_count: number
  total_commission_awarded_kes: number
  total_paid_kes: number
  referrals: AdminAmbassadorReferralRow[]
}

interface AdminPayoutRow {
  id: number
  ambassador_id: number
  email: string | null
  amount: number
  status: 'pending' | 'approved' | 'rejected' | 'paid'
  payout_destination: string
  paystack_transfer_code: string | null
  requested_at: string | null
  reviewed_at: string | null
  rejection_reason: string | null
  paid_at: string | null
}

const ADMIN_AMB_STATUS_COLOR: Record<string, string> = {
  pending: 'amber', active: 'green', suspended: 'red', rejected: 'gray',
  approved: 'blue', paid: 'green',
}

export function AdminAmbassadorsPanel() {
  const { mode, tokens: T } = useTheme()
  const [tab, setTab] = useState<'applications' | 'payouts'>('applications')
  const [csrfToken, setCsrfToken] = useState('')

  const [appStatusFilter, setAppStatusFilter] = useState('pending')
  const [applications, setApplications] = useState<AdminAmbassadorRow[]>([])
  const [loadingApps, setLoadingApps] = useState(true)
  const [appsError, setAppsError] = useState('')

  const [selected, setSelected] = useState<AdminAmbassadorDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  const [payoutStatusFilter, setPayoutStatusFilter] = useState('pending')
  const [payouts, setPayouts] = useState<AdminPayoutRow[]>([])
  const [loadingPayouts, setLoadingPayouts] = useState(true)
  const [payoutsError, setPayoutsError] = useState('')

  const [actionBusy, setActionBusy] = useState(false)
  const [rejectTarget, setRejectTarget] = useState<{ kind: 'ambassador' | 'payout'; id: number } | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
  }, [])

  const loadApplications = (status: string) => {
    setLoadingApps(true)
    setAppsError('')
    api<{ ambassadors: AdminAmbassadorRow[] }>(`/admin/ambassadors${status === 'all' ? '' : `?status=${status}`}`)
      .then(res => setApplications(res.ambassadors))
      .catch(e => setAppsError(e instanceof ApiError ? e.message : 'Could not load ambassador applications.'))
      .finally(() => setLoadingApps(false))
  }

  const loadPayouts = (status: string) => {
    setLoadingPayouts(true)
    setPayoutsError('')
    api<{ payouts: AdminPayoutRow[] }>(`/admin/payouts${status === 'all' ? '' : `?status=${status}`}`)
      .then(res => setPayouts(res.payouts))
      .catch(e => setPayoutsError(e instanceof ApiError ? e.message : 'Could not load payout requests.'))
      .finally(() => setLoadingPayouts(false))
  }

  useEffect(() => { loadApplications(appStatusFilter) }, [appStatusFilter])
  useEffect(() => { loadPayouts(payoutStatusFilter) }, [payoutStatusFilter])

  const openDetail = (id: number) => {
    setLoadingDetail(true)
    api<AdminAmbassadorDetail>(`/admin/ambassadors/${id}`)
      .then(setSelected)
      .catch(e => alert(e instanceof ApiError ? e.message : 'Could not load ambassador detail.'))
      .finally(() => setLoadingDetail(false))
  }

  const runAmbassadorAction = async (id: number, action: 'approve' | 'suspend' | 'reinstate') => {
    setActionBusy(true)
    try {
      await api(`/admin/ambassadors/${id}/${action}`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
      })
      loadApplications(appStatusFilter)
      if (selected?.id === id) openDetail(id)
    } catch (e) {
      alert(e instanceof ApiError ? e.message : `Could not ${action} this ambassador.`)
    } finally {
      setActionBusy(false)
    }
  }

  const rejectAmbassador = async (id: number, reason: string) => {
    setActionBusy(true)
    try {
      await api(`/admin/ambassadors/${id}/reject`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ reason }),
      })
      loadApplications(appStatusFilter)
      setSelected(null)
      setRejectTarget(null)
      setRejectReason('')
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not reject this ambassador.')
    } finally {
      setActionBusy(false)
    }
  }

  const approvePayout = async (id: number) => {
    setActionBusy(true)
    try {
      await api(`/admin/payouts/${id}/approve`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
      })
      loadPayouts(payoutStatusFilter)
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not approve this payout.')
    } finally {
      setActionBusy(false)
    }
  }

  const rejectPayout = async (id: number, reason: string) => {
    setActionBusy(true)
    try {
      await api(`/admin/payouts/${id}/reject`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ reason }),
      })
      loadPayouts(payoutStatusFilter)
      setRejectTarget(null)
      setRejectReason('')
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not reject this payout.')
    } finally {
      setActionBusy(false)
    }
  }

  const syncPayoutStatus = async (id: number) => {
    setActionBusy(true)
    try {
      await api(`/admin/payouts/${id}/sync-status`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
      })
      loadPayouts(payoutStatusFilter)
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not sync this payout status with Paystack.')
    } finally {
      setActionBusy(false)
    }
  }

  const submitReject = () => {
    if (!rejectTarget || !rejectReason.trim()) return
    if (rejectTarget.kind === 'ambassador') rejectAmbassador(rejectTarget.id, rejectReason.trim())
    else rejectPayout(rejectTarget.id, rejectReason.trim())
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', gap: 6 }}>
        {(['applications', 'payouts'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{ padding: '8px 18px', borderRadius: 10, background: tab === t ? N.navy : (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: tab === t ? '#fff' : '#6B7280', border: 'none', cursor: 'pointer', fontWeight: 700, fontSize: 12, fontFamily: 'Plus Jakarta Sans' }}>
            {t === 'applications' ? 'Applications' : 'Payout Requests'}
          </button>
        ))}
      </div>

      {tab === 'applications' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {selected && (
            <div style={{ background: T.card, borderRadius: 14, padding: 20, boxShadow: '0 1px 4px rgba(0,0,0,0.06)', border: `1px solid ${T.border}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                <div>
                  <div style={{ fontWeight: 800, fontSize: 16, color: T.text }}>{selected.display_name || selected.email}</div>
                  <div style={{ fontSize: 12, color: T.textMuted, marginTop: 2 }}>{selected.email} · code {selected.referral_code}</div>
                  <div style={{ marginTop: 6 }}><AdminBadge text={selected.status} color={ADMIN_AMB_STATUS_COLOR[selected.status] || 'gray'} /></div>
                </div>
                <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.textMuted, fontSize: 20 }}>×</button>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, marginBottom: 16 }}>
                {[['Referred', selected.referred_count.toString()], ['Paying', selected.paying_count.toString()], ['Commission Awarded', 'KES ' + selected.total_commission_awarded_kes.toLocaleString()], ['Paid Out', 'KES ' + selected.total_paid_kes.toLocaleString()]].map(([k, v]) => (
                  <div key={k} style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.04)' : '#F9FAFB'), borderRadius: 10, padding: '10px 12px' }}>
                    <div style={{ fontSize: 10, color: T.textMuted, fontWeight: 600, marginBottom: 3 }}>{k}</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: T.text }}>{v}</div>
                  </div>
                ))}
              </div>
              {selected.status === 'pending' && (
                <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                  <button disabled={actionBusy} onClick={() => runAmbassadorAction(selected.id, 'approve')} style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 10, padding: '8px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 12 }}>Approve</button>
                  <button disabled={actionBusy} onClick={() => setRejectTarget({ kind: 'ambassador', id: selected.id })} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 10, padding: '8px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 12 }}>Reject</button>
                </div>
              )}
              {selected.status === 'active' && (
                <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                  <button disabled={actionBusy} onClick={() => runAmbassadorAction(selected.id, 'suspend')} style={{ background: '#FEF3C7', color: '#D97706', border: 'none', borderRadius: 10, padding: '8px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 12 }}>Suspend</button>
                </div>
              )}
              {selected.status === 'suspended' && (
                <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                  <button disabled={actionBusy} onClick={() => runAmbassadorAction(selected.id, 'reinstate')} style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 10, padding: '8px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 12 }}>Reinstate</button>
                </div>
              )}
              {selected.rejection_reason && (
                <div style={{ fontSize: 12, color: '#DC2626', marginBottom: 12 }}>Rejection reason: {selected.rejection_reason}</div>
              )}
              <div style={{ fontWeight: 700, fontSize: 12, color: T.text, marginBottom: 8 }}>Referrals ({selected.referrals.length})</div>
              {selected.referrals.length === 0 ? (
                <div style={{ fontSize: 12, color: T.textMuted }}>No referrals yet.</div>
              ) : (
                <AdminTable
                  cols={['Referred', 'Status', 'Commission', 'Voided']}
                  rows={selected.referrals.map(r => [
                    r.referred_email || `#${r.id}`,
                    r.status,
                    r.commission_amount != null ? 'KES ' + r.commission_amount.toLocaleString() : '—',
                    r.voided ? (r.void_reason || 'Yes') : 'No',
                  ])}
                />
              )}
            </div>
          )}

          <AdminCard title={`Ambassador Applications — ${applications.length}`}>
            <div style={{ padding: '12px 18px', borderBottom: `1px solid ${T.border}`, display: 'flex', gap: 6 }}>
              {['pending', 'active', 'suspended', 'rejected', 'all'].map(f => (
                <button key={f} onClick={() => setAppStatusFilter(f)} style={{ padding: '7px 14px', borderRadius: 8, background: appStatusFilter === f ? N.navy : (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: appStatusFilter === f ? '#fff' : '#6B7280', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans', textTransform: 'capitalize' }}>{f}</button>
              ))}
            </div>
            {loadingApps ? (
              <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading…</div>
            ) : appsError ? (
              <div style={{ padding: 24, textAlign: 'center', color: '#C94C4C', fontSize: 13 }}>{appsError}</div>
            ) : applications.length === 0 ? (
              <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No applications with this status.</div>
            ) : (
              <AdminTable
                cols={['Name', 'Email', 'Code', 'Applied', 'Status']}
                rows={applications.map(a => [
                  a.display_name || '—', a.email || '—', a.referral_code,
                  a.applied_at ? new Date(a.applied_at).toLocaleDateString() : '—',
                  <AdminBadge text={a.status} color={ADMIN_AMB_STATUS_COLOR[a.status] || 'gray'} />,
                ])}
                actions={i => (
                  <button onClick={() => openDetail(applications[i].id)} style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: T.text, border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>{loadingDetail ? '…' : 'Review'}</button>
                )}
              />
            )}
          </AdminCard>
        </div>
      )}

      {tab === 'payouts' && (
        <AdminCard title={`Payout Requests — ${payouts.length}`}>
          <div style={{ padding: '12px 18px', borderBottom: `1px solid ${T.border}`, display: 'flex', gap: 6 }}>
            {['pending', 'approved', 'paid', 'rejected', 'all'].map(f => (
              <button key={f} onClick={() => setPayoutStatusFilter(f)} style={{ padding: '7px 14px', borderRadius: 8, background: payoutStatusFilter === f ? N.navy : (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: payoutStatusFilter === f ? '#fff' : '#6B7280', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans', textTransform: 'capitalize' }}>{f}</button>
            ))}
          </div>
          {loadingPayouts ? (
            <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading…</div>
          ) : payoutsError ? (
            <div style={{ padding: 24, textAlign: 'center', color: '#C94C4C', fontSize: 13 }}>{payoutsError}</div>
          ) : payouts.length === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No payout requests with this status.</div>
          ) : (
            <AdminTable
              cols={['Email', 'Amount', 'Destination', 'Requested', 'Status']}
              rows={payouts.map(p => [
                p.email || `#${p.ambassador_id}`,
                'KES ' + p.amount.toLocaleString(),
                p.payout_destination,
                p.requested_at ? new Date(p.requested_at).toLocaleDateString() : '—',
                <AdminBadge text={p.status} color={ADMIN_AMB_STATUS_COLOR[p.status] || 'gray'} />,
              ])}
              actions={i => {
                const p = payouts[i]
                if (p.status === 'pending') return (
                  <div style={{ display: 'flex', gap: 5, justifyContent: 'flex-end' }}>
                    <button disabled={actionBusy} onClick={() => approvePayout(p.id)} style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Approve</button>
                    <button disabled={actionBusy} onClick={() => setRejectTarget({ kind: 'payout', id: p.id })} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Reject</button>
                  </div>
                )
                if (p.status === 'approved') return (
                  <div style={{ display: 'flex', gap: 5, justifyContent: 'flex-end' }}>
                    <button disabled={actionBusy} onClick={() => syncPayoutStatus(p.id)} style={{ background: '#DBEAFE', color: '#2563EB', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Sync Status</button>
                  </div>
                )
                return null
              }}
            />
          )}
        </AdminCard>
      )}

      {rejectTarget && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setRejectTarget(null)}>
          <div style={{ background: T.card, borderRadius: 16, padding: 24, maxWidth: 380, width: '90%' }} onClick={e => e.stopPropagation()}>
            <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 10 }}>Reason for rejection</div>
            <textarea value={rejectReason} onChange={e => setRejectReason(e.target.value)} rows={3} placeholder="Explain why this is being rejected…" style={{ width: '100%', boxSizing: 'border-box', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '10px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', resize: 'none', marginBottom: 14 }} />
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => { setRejectTarget(null); setRejectReason('') }} style={{ flex: 1, background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: T.text, border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 13 }}>Cancel</button>
              <button disabled={actionBusy || !rejectReason.trim()} onClick={submitReject} style={{ flex: 1, background: '#DC2626', color: '#fff', border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, opacity: (actionBusy || !rejectReason.trim()) ? 0.6 : 1 }}>Confirm Reject</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── ADMIN: OPPORTUNITIES REVIEW (Chunk 9 continued) ────────────────────────

interface AdminOpportunityRow {
  id: number
  organisation_id: number
  organisation_name: string | null
  organisation_verification_status: string | null
  organisation_is_active: boolean | null
  title: string
  opportunity_type: string
  location: string | null
  is_remote: boolean
  application_deadline: string | null
  expiry_date: string | null
  status: string
  rejection_reason: string | null
  submitted_at: string | null
  created_at: string | null
}

const ADMIN_OPP_STATUS_COLOR: Record<string, string> = {
  draft: 'gray', pending_review: 'amber', approved: 'blue', rejected: 'red',
  published: 'green', expired: 'gray', archived: 'gray', removed: 'red',
}

export function AdminOpportunitiesPanel() {
  const { mode, tokens: T } = useTheme()
  const [csrfToken, setCsrfToken] = useState('')
  const [statusFilter, setStatusFilter] = useState('pending_review')
  const [rows, setRows] = useState<AdminOpportunityRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionBusy, setActionBusy] = useState(false)
  const [reasonTarget, setReasonTarget] = useState<{ kind: 'reject' | 'remove'; id: number } | null>(null)
  const [reasonText, setReasonText] = useState('')

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
  }, [])

  const load = (status: string) => {
    setLoading(true)
    setError('')
    api<{ opportunities: AdminOpportunityRow[] }>(`/admin/opportunities?status=${status}`)
      .then(res => setRows(res.opportunities))
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load opportunities.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load(statusFilter) }, [statusFilter])

  const runAction = async (id: number, action: 'approve' | 'publish' | 'archive') => {
    setActionBusy(true)
    try {
      await api(`/admin/opportunities/${id}/${action}`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      load(statusFilter)
    } catch (e) {
      alert(e instanceof ApiError ? e.message : `Could not ${action} this opportunity.`)
    } finally {
      setActionBusy(false)
    }
  }

  const [sweepBusy, setSweepBusy] = useState(false)
  const sweepExpired = async () => {
    setSweepBusy(true)
    try {
      const res = await api<{ swept_count: number }>('/admin/opportunities/sweep-expired', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
      })
      alert(res.swept_count > 0 ? `Swept ${res.swept_count} expired opportunity(ies).` : 'No expired opportunities to sweep.')
      load(statusFilter)
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not run the expiry sweep.')
    } finally {
      setSweepBusy(false)
    }
  }

  const submitReason = async () => {
    if (!reasonTarget) return
    if (reasonTarget.kind === 'reject' && !reasonText.trim()) return
    setActionBusy(true)
    try {
      const path = reasonTarget.kind === 'reject'
        ? `/admin/opportunities/${reasonTarget.id}/reject`
        : `/admin/opportunities/${reasonTarget.id}/remove`
      await api(path, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ reason: reasonText.trim() || undefined }),
      })
      load(statusFilter)
      setReasonTarget(null)
      setReasonText('')
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not complete this action.')
    } finally {
      setActionBusy(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <AdminCard title={`Opportunities — ${rows.length}`} action={sweepExpired} actionLabel={sweepBusy ? 'Sweeping…' : 'Sweep Expired Now'}>
        <div style={{ padding: '12px 18px', borderBottom: `1px solid ${T.border}`, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {['pending_review', 'approved', 'published', 'rejected', 'expired', 'archived', 'removed', 'all'].map(f => (
            <button key={f} onClick={() => setStatusFilter(f)} style={{ padding: '7px 14px', borderRadius: 8, background: statusFilter === f ? N.navy : (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: statusFilter === f ? '#fff' : '#6B7280', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans', textTransform: 'capitalize' }}>{f.replace('_', ' ')}</button>
          ))}
        </div>
        {loading ? (
          <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading…</div>
        ) : error ? (
          <div style={{ padding: 24, textAlign: 'center', color: '#C94C4C', fontSize: 13 }}>{error}</div>
        ) : rows.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No opportunities with this status.</div>
        ) : (
          <AdminTable
            cols={['Title', 'Organisation', 'Type', 'Deadline', 'Status']}
            rows={rows.map(r => [
              r.title,
              r.organisation_name || `#${r.organisation_id}`,
              r.opportunity_type,
              r.application_deadline ? new Date(r.application_deadline).toLocaleDateString() : '—',
              <AdminBadge text={r.status.replace('_', ' ')} color={ADMIN_OPP_STATUS_COLOR[r.status] || 'gray'} />,
            ])}
            actions={i => {
              const r = rows[i]
              return (
                <div style={{ display: 'flex', gap: 5, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                  {r.status === 'pending_review' && (
                    <>
                      <button disabled={actionBusy} onClick={() => runAction(r.id, 'approve')} style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Approve</button>
                      <button disabled={actionBusy} onClick={() => setReasonTarget({ kind: 'reject', id: r.id })} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Reject</button>
                    </>
                  )}
                  {r.status === 'approved' && (
                    <button disabled={actionBusy} onClick={() => runAction(r.id, 'publish')} style={{ background: '#DBEAFE', color: '#2563EB', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Publish</button>
                  )}
                  {(r.status === 'approved' || r.status === 'published' || r.status === 'expired') && (
                    <button disabled={actionBusy} onClick={() => runAction(r.id, 'archive')} style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: T.textMuted, border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Archive</button>
                  )}
                  {r.status !== 'removed' && (
                    <button disabled={actionBusy} onClick={() => setReasonTarget({ kind: 'remove', id: r.id })} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Remove</button>
                  )}
                </div>
              )
            }}
          />
        )}
      </AdminCard>

      {reasonTarget && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setReasonTarget(null)}>
          <div style={{ background: T.card, borderRadius: 16, padding: 24, maxWidth: 380, width: '90%' }} onClick={e => e.stopPropagation()}>
            <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 10 }}>{reasonTarget.kind === 'reject' ? 'Reason for rejection' : 'Reason for removal (optional)'}</div>
            <textarea value={reasonText} onChange={e => setReasonText(e.target.value)} rows={3} placeholder="Explain why…" style={{ width: '100%', boxSizing: 'border-box', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '10px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', resize: 'none', marginBottom: 14 }} />
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => { setReasonTarget(null); setReasonText('') }} style={{ flex: 1, background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: T.text, border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 13 }}>Cancel</button>
              <button disabled={actionBusy || (reasonTarget.kind === 'reject' && !reasonText.trim())} onClick={submitReason} style={{ flex: 1, background: '#DC2626', color: '#fff', border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, opacity: (actionBusy || (reasonTarget.kind === 'reject' && !reasonText.trim())) ? 0.6 : 1 }}>Confirm</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── ADMIN: ORGANISATIONS VERIFICATION (Chunk 9 continued) ──────────────────
