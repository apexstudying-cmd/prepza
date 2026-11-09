import { N } from '../theme/theme'
import { AdminBadge, AdminBarChart, AdminLineChart, AdminKPI, AdminTable, AdminCard } from './AdminShared'
import { materialTypeLabel } from '../lib/library'
import type { AdminSectionController } from './useAdminSectionController'

type AdminDashboardSectionProps = Pick<AdminSectionController, 'T' | 'dashAnalytics' | 'dashAnalyticsLoading' | 'dashAiUsage' | 'dashPayments' | 'dashPaymentsLoading' | 'dashModSummary' | 'dashLibraryQueueCount' | 'dashRecentUsers' | 'dashError' | 'setSection'>

export function AdminDashboardSection({ controller }: { controller: AdminDashboardSectionProps }) {
  const { T, dashAnalytics, dashAnalyticsLoading, dashAiUsage, dashPayments, dashPaymentsLoading, dashModSummary, dashLibraryQueueCount, dashRecentUsers, dashError, setSection } = controller
  const ActivityDot = ({ color }: { color: string }) => <div style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0, marginTop: 3 }} />

  const fmtBytesDash = (n: number) => {
      if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`
      if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`
      if (n >= 1e3) return `${(n / 1e3).toFixed(1)} KB`
      return `${n} B`
    }
    const nowDash = new Date()
    const dashSuccess = dashPayments.filter(p => p.status === 'success')
    const dashFailedThisMonth = dashPayments.filter(p => p.status === 'failed' && p.created_at && new Date(p.created_at).getMonth() === nowDash.getMonth() && new Date(p.created_at).getFullYear() === nowDash.getFullYear()).length
    const dashLatestSub = new Map<number, AdminPayment>()
    for (const p of dashPayments) {
      if (p.payment_type !== 'subscription' || p.status !== 'success' || !p.subscription_expires_at || p.user_id == null) continue
      const existing = dashLatestSub.get(p.user_id)
      if (!existing || new Date(p.subscription_expires_at) > new Date(existing.subscription_expires_at as string)) dashLatestSub.set(p.user_id, p)
    }
    const dashActiveSubs = [...dashLatestSub.values()].filter(p => new Date(p.subscription_expires_at as string) > nowDash).length

    return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {dashError && <div style={{ color: '#DC2626', fontSize: 12 }}>{dashError}</div>}

      {/* KPI grid */}
      {dashAnalyticsLoading ? (
        <div style={{ padding: '24px 0', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading dashboard…</div>
      ) : dashAnalytics && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14 }}>
            <AdminKPI label="Total Students" value={dashAnalytics.total_users.toLocaleString()} sub="All time" color={T.text} chartData={dashAnalytics.signups_per_day.map(d => d.count)} />
            <AdminKPI label="Active Today" value={dashAnalytics.active_today.toLocaleString()} sub={`${dashAnalytics.total_users > 0 ? Math.round((dashAnalytics.active_today / dashAnalytics.total_users) * 100) : 0}% of total`} color="#4C7BC9" />
            <AdminKPI label="Revenue (30d)" value={`KES ${dashAnalytics.revenue_last_30d.toLocaleString()}`} sub={`All time: KES ${dashAnalytics.total_revenue.toLocaleString()}`} color="#16A34A" chartData={dashAnalytics.revenue_per_day.map(d => d.amount)} />
            <AdminKPI label="Active Subscriptions" value={dashPaymentsLoading ? '—' : dashActiveSubs.toLocaleString()} color={N.gold} />
            <AdminKPI label="AI Requests Today" value={(dashAiUsage?.requests_today ?? '—').toString()} sub={dashAiUsage ? `${dashAiUsage.total_requests.toLocaleString()} in 30d` : ''} color="#7C3AED" chartData={dashAiUsage?.daily_trend.map(d => d.requests)} />
            <AdminKPI label="AI Cost (30d)" value={dashAiUsage ? `$${dashAiUsage.total_cost_usd.toFixed(2)}` : '—'} color="#DC2626" />
            <AdminKPI label="Content Items" value={dashAnalytics.total_content_items.toLocaleString()} sub={`${dashAnalytics.total_units.toLocaleString()} units`} color={T.text} />
            <AdminKPI label="Storage Used" value={fmtBytesDash(dashAnalytics.storage_used_bytes)} color="#6B7280" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: 14 }}>
            <AdminCard title="Revenue — Last 30 Days">
              <div style={{ padding: '16px 18px' }}>
                {dashAnalytics.revenue_per_day.length === 0 ? (
                  <div style={{ fontSize: 13, color: T.textMuted }}>No revenue in this period.</div>
                ) : (
                  <AdminBarChart data={dashAnalytics.revenue_per_day.map(d => d.amount)} height={100} color={N.gold} />
                )}
              </div>
            </AdminCard>
            <AdminCard title="AI Requests — Last 30 Days">
              <div style={{ padding: '16px 18px' }}>
                {dashAiUsage && dashAiUsage.daily_trend.length > 0 ? (
                  <AdminBarChart data={dashAiUsage.daily_trend.map(d => d.requests)} height={100} color="#7C3AED" />
                ) : (
                  <div style={{ fontSize: 13, color: T.textMuted }}>No AI requests in this period.</div>
                )}
              </div>
            </AdminCard>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <AdminCard title="Student Growth — Last 30 Days">
              <div style={{ padding: '16px 18px' }}>
                <div style={{ fontSize: 28, fontWeight: 800, color: T.text, marginBottom: 4 }}>{dashAnalytics.total_users.toLocaleString()} <span style={{ fontSize: 13, color: T.textMuted, fontWeight: 500 }}>total</span></div>
                {dashAnalytics.signups_per_day.length > 0 && <AdminLineChart data={dashAnalytics.signups_per_day.map(d => d.count)} color={T.text} height={60} />}
              </div>
            </AdminCard>

            <AdminCard title="Recent Signups">
              <div style={{ padding: '0 18px' }}>
                {dashRecentUsers.length === 0 ? (
                  <div style={{ padding: '18px 0', fontSize: 13, color: T.textMuted }}>No signups yet.</div>
                ) : dashRecentUsers.map((u, i) => (
                  <div key={u.id} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', padding: '10px 0', borderBottom: i < dashRecentUsers.length - 1 ? `1px solid ${T.border}` : 'none' }}>
                    <ActivityDot color="#4CC97B" />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, color: T.text, lineHeight: 1.4 }}>{u.display_name || u.email} registered{u.university_name ? ` · ${u.university_name}` : ''}</div>
                      <div style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>{u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</div>
                    </div>
                  </div>
                ))}
              </div>
            </AdminCard>
          </div>

          {/* Alerts */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12 }}>
            {[
              { icon: '🛡️', label: 'Pending Reports', value: (dashModSummary?.open_reports ?? '—').toString(), color: '#FEF3C7', fg: '#D97706', action: () => setSection('moderation') },
              { icon: '📄', label: 'Content Awaiting Review', value: (dashLibraryQueueCount ?? '—').toString(), color: '#DBEAFE', fg: '#2563EB', action: () => setSection('content') },
              { icon: '💳', label: 'Failed Payments (30d)', value: dashPaymentsLoading ? '—' : dashFailedThisMonth.toString(), color: '#FEE2E2', fg: '#DC2626', action: () => setSection('payments') },
            ].map(a => (
              <button key={a.label} onClick={a.action} style={{ background: a.color, border: 'none', borderRadius: 14, padding: '14px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', display: 'flex', gap: 12, alignItems: 'center', textAlign: 'left' }}>
                <span style={{ fontSize: 22 }}>{a.icon}</span>
                <div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: a.fg }}>{a.value}</div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: a.fg, opacity: 0.8 }}>{a.label}</div>
                </div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
    )
}

type AdminUsersSectionProps = Pick<AdminSectionController, 'mode' | 'T' | 'search' | 'setSearch' | 'userFilter' | 'setUserFilter' | 'selectedUser' | 'setSelectedUser' | 'confirmAction' | 'setConfirmAction' | 'adminUsersLoading' | 'adminUsersError' | 'userActionError' | 'setUserSuspended' | 'filteredUsers'>

export function AdminUsersSection({ controller }: { controller: AdminUsersSectionProps }) {
  const { mode, T, search, setSearch, userFilter, setUserFilter, selectedUser, setSelectedUser, confirmAction, setConfirmAction, adminUsersLoading, adminUsersError, userActionError, setUserSuspended, filteredUsers } = controller
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* User detail panel */}
      {selectedUser && (
        <div style={{ background: T.card, borderRadius: 14, padding: 20, boxShadow: '0 1px 4px rgba(0,0,0,0.06)', border: `1px solid ${T.border}` }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
            <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
              <div style={{ width: 52, height: 52, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 18, color: N.navy }}>{(selectedUser.display_name || selectedUser.email).split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}</div>
              <div>
                <div style={{ fontWeight: 800, fontSize: 17, color: T.text }}>{selectedUser.display_name || '(no name)'}</div>
                <div style={{ fontSize: 12, color: T.textMuted, marginTop: 2 }}>{selectedUser.email}</div>
                <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                  <AdminBadge text={selectedUser.is_suspended ? 'Suspended' : 'Active'} color={selectedUser.is_suspended ? 'red' : 'green'} />
                  <AdminBadge text={selectedUser.subscription_plan === 'free' ? 'Free' : selectedUser.subscription_plan} color={selectedUser.subscription_plan === 'free' ? 'gray' : 'amber'} />
                  {selectedUser.is_admin && <AdminBadge text="Admin" color="blue" />}
                </div>
              </div>
            </div>
            <button onClick={() => setSelectedUser(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.textMuted, fontSize: 20 }}>×</button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, marginBottom: 16 }}>
            {[
              ['University', selectedUser.university_name || '—'],
              ['Program', selectedUser.program_name || '—'],
              ['Year', selectedUser.year != null ? String(selectedUser.year) : '—'],
              ['Joined', selectedUser.created_at ? new Date(selectedUser.created_at).toLocaleDateString() : '—'],
              ['Documents', selectedUser.documents_count.toString()],
              ['AI Requests', selectedUser.ai_requests_count.toString()],
              ['User ID', selectedUser.id.toString()],
              ['Subscription', selectedUser.subscription_plan],
            ].map(([k, v]) => (
              <div key={k} style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.04)' : '#F9FAFB'), borderRadius: 10, padding: '10px 12px' }}>
                <div style={{ fontSize: 10, color: T.textMuted, fontWeight: 600, marginBottom: 3 }}>{k}</div>
                <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{v}</div>
              </div>
            ))}
          </div>
          {userActionError && <div style={{ color: '#DC2626', fontSize: 12, marginBottom: 10 }}>{userActionError}</div>}
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => setConfirmAction({ type: selectedUser.is_suspended ? 'Reactivate' : 'Suspend', target: selectedUser.display_name || selectedUser.email, userId: selectedUser.id, nextSuspended: !selectedUser.is_suspended })}
              style={{ background: selectedUser.is_suspended ? '#F0FDF4' : '#FEF3C7', color: selectedUser.is_suspended ? '#16A34A' : '#D97706', border: 'none', borderRadius: 10, padding: '8px 14px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 12 }}
            >{selectedUser.is_suspended ? 'Reactivate' : 'Suspend'}</button>
          </div>
        </div>
      )}

      {/* Confirm modal */}
      {confirmAction && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setConfirmAction(null)}>
          <div style={{ background: T.card, borderRadius: 16, padding: 24, maxWidth: 380, width: '90%', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }} onClick={e => e.stopPropagation()}>
            <div style={{ fontWeight: 800, fontSize: 17, color: T.text, marginBottom: 8 }}>Confirm: {confirmAction.type}</div>
            <div style={{ fontSize: 13, color: T.textMuted, marginBottom: 20, lineHeight: 1.6 }}>Are you sure you want to <strong>{confirmAction.type.toLowerCase()}</strong> for <strong>{confirmAction.target}</strong>? This action will be logged.</div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => setConfirmAction(null)} style={{ flex: 1, background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: T.text, border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 13 }}>Cancel</button>
              <button
                onClick={() => { if (confirmAction.userId != null && confirmAction.nextSuspended != null) { setUserSuspended(confirmAction.userId, confirmAction.nextSuspended) } else { setConfirmAction(null) } }}
                style={{ flex: 1, background: '#DC2626', color: '#fff', border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13 }}
              >Confirm</button>
            </div>
          </div>
        </div>
      )}

      <AdminCard title={`Users — ${filteredUsers.length}${adminUsersLoading ? '' : ' loaded'}`}>
        <div style={{ padding: '12px 18px', borderBottom: `1px solid ${T.border}`, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8, background: (mode === 'dark' ? 'rgba(255,255,255,0.04)' : '#F9FAFB'), border: `1px solid ${T.border}`, borderRadius: 10, padding: '8px 12px', minWidth: 200 }}>
            <span style={{ color: T.textMuted, fontSize: 14 }}>🔍</span>
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name, email, university…" style={{ flex: 1, border: 'none', background: 'none', outline: 'none', fontSize: 13, fontFamily: 'Plus Jakarta Sans', color: T.text }} />
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {['All','Active','Suspended','Premium','Free'].map(f => (
              <button key={f} onClick={() => setUserFilter(f)} style={{ padding: '7px 14px', borderRadius: 8, background: userFilter === f ? N.navy : (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: userFilter === f ? '#fff' : '#6B7280', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>{f}</button>
            ))}
          </div>
        </div>
        {adminUsersLoading ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading users…</div>
        ) : adminUsersError ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{adminUsersError}</div>
        ) : filteredUsers.length === 0 ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No users match this filter.</div>
        ) : (
          <AdminTable
            cols={['User', 'University', 'Plan', 'Docs', 'AI Reqs', 'Status', 'Joined']}
            rows={filteredUsers.map(u => [
              <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <div style={{ width: 32, height: 32, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 11, color: N.navy, flexShrink: 0 }}>{(u.display_name || u.email).split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}</div>
                <div><div style={{ fontWeight: 600, color: T.text }}>{u.display_name || '(no name)'}</div><div style={{ fontSize: 11, color: T.textMuted }}>{u.email}</div></div>
              </div>,
              u.university_name || '—',
              u.subscription_plan === 'free' ? 'Free' : u.subscription_plan,
              u.documents_count.toString(),
              u.ai_requests_count.toString(),
              <AdminBadge text={u.is_suspended ? 'Suspended' : 'Active'} color={u.is_suspended ? 'red' : 'green'} />,
              u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'
            ])}
            actions={i => (
              <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                <button onClick={() => setSelectedUser(filteredUsers[i])} style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), border: 'none', borderRadius: 7, padding: '5px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, color: T.text, fontFamily: 'Plus Jakarta Sans' }}>View</button>
                <button
                  onClick={() => setConfirmAction({ type: filteredUsers[i].is_suspended ? 'Reactivate' : 'Suspend', target: filteredUsers[i].display_name || filteredUsers[i].email, userId: filteredUsers[i].id, nextSuspended: !filteredUsers[i].is_suspended })}
                  style={{ background: filteredUsers[i].is_suspended ? '#F0FDF4' : '#FEF3C7', border: 'none', borderRadius: 7, padding: '5px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, color: filteredUsers[i].is_suspended ? '#16A34A' : '#D97706', fontFamily: 'Plus Jakarta Sans' }}
                >{filteredUsers[i].is_suspended ? 'Reactivate' : 'Suspend'}</button>
              </div>
            )}
          />
        )}
      </AdminCard>
    </div>
  )
}

type AdminContentSectionProps = Pick<AdminSectionController, 'mode' | 'T' | 'contentTab' | 'setContentTab' | 'libraryQueue' | 'libraryQueueLoading' | 'libraryQueueError' | 'libraryReports' | 'libraryReportsLoading' | 'libraryReportsError' | 'contentActionError' | 'rejectPromptId' | 'setRejectPromptId' | 'rejectReason' | 'setRejectReason' | 'removePromptTarget' | 'setRemovePromptTarget' | 'removeReason' | 'setRemoveReason' | 'approveLibraryItem' | 'rejectLibraryItem' | 'removeLibraryItem' | 'resolveLibraryReport'>

export function AdminContentSection({ controller }: { controller: AdminContentSectionProps }) {
  const { mode, T, contentTab, setContentTab, libraryQueue, libraryQueueLoading, libraryQueueError, libraryReports, libraryReportsLoading, libraryReportsError, contentActionError, rejectPromptId, setRejectPromptId, rejectReason, setRejectReason, removePromptTarget, setRemovePromptTarget, removeReason, setRemoveReason, approveLibraryItem, rejectLibraryItem, removeLibraryItem, resolveLibraryReport } = controller
  const CONTENT_TABS = ['Pending Review', 'Reported']
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Reject prompt */}
        {rejectPromptId != null && (
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => { setRejectPromptId(null); setRejectReason('') }}>
            <div style={{ background: T.card, borderRadius: 16, padding: 24, maxWidth: 380, width: '90%', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }} onClick={e => e.stopPropagation()}>
              <div style={{ fontWeight: 800, fontSize: 17, color: T.text, marginBottom: 8 }}>Reject submission</div>
              <textarea value={rejectReason} onChange={e => setRejectReason(e.target.value)} placeholder="Reason (required, shown to the student)" rows={3} style={{ width: '100%', border: `1px solid ${T.border}`, borderRadius: 10, padding: 10, fontSize: 13, fontFamily: 'Plus Jakarta Sans', marginBottom: 16, resize: 'vertical' }} />
              <div style={{ display: 'flex', gap: 10 }}>
                <button onClick={() => { setRejectPromptId(null); setRejectReason('') }} style={{ flex: 1, background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: T.text, border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 13 }}>Cancel</button>
                <button onClick={() => rejectLibraryItem(rejectPromptId, rejectReason.trim())} disabled={!rejectReason.trim()} style={{ flex: 1, background: rejectReason.trim() ? '#DC2626' : '#FCA5A5', color: '#fff', border: 'none', borderRadius: 10, padding: '10px 0', cursor: rejectReason.trim() ? 'pointer' : 'not-allowed', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13 }}>Reject</button>
              </div>
            </div>
          </div>
        )}

        {/* Remove (takedown) prompt */}
        {removePromptTarget != null && (
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => { setRemovePromptTarget(null); setRemoveReason('') }}>
            <div style={{ background: T.card, borderRadius: 16, padding: 24, maxWidth: 380, width: '90%', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }} onClick={e => e.stopPropagation()}>
              <div style={{ fontWeight: 800, fontSize: 17, color: T.text, marginBottom: 8 }}>Remove published item</div>
              <div style={{ fontSize: 13, color: T.textMuted, marginBottom: 12, lineHeight: 1.5 }}>This takes the item down from the public Library. The report will be marked actioned.</div>
              <textarea value={removeReason} onChange={e => setRemoveReason(e.target.value)} placeholder="Reason (required)" rows={3} style={{ width: '100%', border: `1px solid ${T.border}`, borderRadius: 10, padding: 10, fontSize: 13, fontFamily: 'Plus Jakarta Sans', marginBottom: 16, resize: 'vertical' }} />
              <div style={{ display: 'flex', gap: 10 }}>
                <button onClick={() => { setRemovePromptTarget(null); setRemoveReason('') }} style={{ flex: 1, background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: T.text, border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 13 }}>Cancel</button>
                <button onClick={() => removePromptTarget && removeLibraryItem(removePromptTarget.publicationId, removePromptTarget.reportId, removeReason.trim())} disabled={!removeReason.trim()} style={{ flex: 1, background: removeReason.trim() ? '#DC2626' : '#FCA5A5', color: '#fff', border: 'none', borderRadius: 10, padding: '10px 0', cursor: removeReason.trim() ? 'pointer' : 'not-allowed', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13 }}>Remove</button>
              </div>
            </div>
          </div>
        )}

        <AdminCard title="Content Management">
          <div style={{ padding: '12px 18px', borderBottom: `1px solid ${T.border}`, display: 'flex', gap: 6 }}>
            {CONTENT_TABS.map(t => (
              <button key={t} onClick={() => setContentTab(t)} style={{ padding: '7px 16px', borderRadius: 8, background: contentTab === t ? N.navy : (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: contentTab === t ? '#fff' : '#6B7280', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>
                {t}{t === 'Pending Review' && libraryQueue.length > 0 ? ` (${libraryQueue.length})` : ''}
                {t === 'Reported' && libraryReports.length > 0 ? ` (${libraryReports.length})` : ''}
              </button>
            ))}
          </div>

          {contentActionError && <div style={{ padding: '10px 18px', color: '#DC2626', fontSize: 12 }}>{contentActionError}</div>}

          {contentTab === 'Pending Review' && (
            libraryQueueLoading ? (
              <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading queue…</div>
            ) : libraryQueueError ? (
              <div style={{ padding: '24px 18px', textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{libraryQueueError}</div>
            ) : libraryQueue.length === 0 ? (
              <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Nothing pending review.</div>
            ) : (
              <AdminTable
                cols={['Title', 'Author', 'Type', 'Unit', 'Submitted', '']}
                rows={libraryQueue.map(item => [
                  item.title,
                  item.author_email || '—',
                  materialTypeLabel(item.material_type),
                  item.unit_code || '—',
                  item.created_at ? new Date(item.created_at).toLocaleDateString() : '—',
                  '',
                ])}
                actions={i => (
                  <div style={{ display: 'flex', gap: 5 }}>
                    <button onClick={() => approveLibraryItem(libraryQueue[i].id)} style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Approve</button>
                    <button onClick={() => setRejectPromptId(libraryQueue[i].id)} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Reject</button>
                  </div>
                )}
              />
            )
          )}

          {contentTab === 'Reported' && (
            libraryReportsLoading ? (
              <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading reports…</div>
            ) : libraryReportsError ? (
              <div style={{ padding: '24px 18px', textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{libraryReportsError}</div>
            ) : libraryReports.length === 0 ? (
              <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No open reports.</div>
            ) : (
              <AdminTable
                cols={['Item', 'Reported By', 'Reason', 'Item Status', 'Received', '']}
                rows={libraryReports.map(r => [
                  r.publication_title || '(item removed)',
                  r.reporter_email || 'Anonymous',
                  r.reason,
                  r.publication_status || '—',
                  r.created_at ? new Date(r.created_at).toLocaleDateString() : '—',
                  '',
                ])}
                actions={i => (
                  <div style={{ display: 'flex', gap: 5 }}>
                    <button onClick={() => resolveLibraryReport(libraryReports[i].id, 'dismissed')} style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: T.text, border: 'none', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Dismiss</button>
                    {libraryReports[i].publication_status === 'approved' && (
                      <button onClick={() => setRemovePromptTarget({ publicationId: libraryReports[i].library_publication_id, reportId: libraryReports[i].id })} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Remove</button>
                    )}
                  </div>
                )}
              />
            )
          )}
        </AdminCard>
      </div>
    )
}

type AdminAiUsageSectionProps = Pick<AdminSectionController, 'mode' | 'T' | 'aiUsage' | 'aiUsageLoading' | 'aiUsageError' | 'aiUsageDays' | 'setAiUsageDays' | 'aiJobs' | 'aiJobsLoading' | 'aiJobsError' | 'aiJobsFilter' | 'setAiJobsFilter' | 'aiJobActionError' | 'retryAiJob'>

export function AdminAiUsageSection({ controller }: { controller: AdminAiUsageSectionProps }) {
  const { mode, T, aiUsage, aiUsageLoading, aiUsageError, aiUsageDays, setAiUsageDays, aiJobs, aiJobsLoading, aiJobsError, aiJobsFilter, setAiJobsFilter, aiJobActionError, retryAiJob } = controller
  const fmtDuration = (started: string | null, completed: string | null) => {
      if (!started || !completed) return '—'
      const ms = new Date(completed).getTime() - new Date(started).getTime()
      return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
    }
    return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: T.textMuted, fontWeight: 600 }}>Period:</span>
        {[7, 30, 90].map(d => (
          <button key={d} onClick={() => setAiUsageDays(d)} style={{ padding: '6px 14px', borderRadius: 8, background: aiUsageDays === d ? N.navy : (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: aiUsageDays === d ? '#fff' : '#6B7280', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>{d}d</button>
        ))}
      </div>

      {aiUsageLoading ? (
        <div style={{ padding: '24px 0', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading AI usage…</div>
      ) : aiUsageError ? (
        <div style={{ padding: '24px 0', textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{aiUsageError}</div>
      ) : aiUsage && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
            <AdminKPI label="AI Requests Today" value={aiUsage.requests_today.toLocaleString()} sub={`${aiUsage.total_requests.toLocaleString()} in last ${aiUsage.period_days}d`} color="#7C3AED" />
            <AdminKPI label="Doc Pipeline Jobs" value={aiUsage.document_pipeline_jobs.completed.toLocaleString()} sub={`${aiUsage.document_pipeline_jobs.failed} failed`} color={aiUsage.document_pipeline_jobs.failed > 0 ? '#DC2626' : '#16A34A'} />
            <AdminKPI label="Tokens Used" value={aiUsage.total_tokens >= 1000000 ? `${(aiUsage.total_tokens / 1000000).toFixed(1)}M` : aiUsage.total_tokens.toLocaleString()} sub={`In: ${aiUsage.input_tokens.toLocaleString()} · Out: ${aiUsage.output_tokens.toLocaleString()}`} color={N.gold} />
            <AdminKPI label="Total Cost" value={`$${aiUsage.total_cost_usd.toFixed(2)}`} sub={`Last ${aiUsage.period_days} days`} color="#16A34A" />
          </div>
          <div style={{ fontSize: 11, color: T.textMuted, lineHeight: 1.5 }}>{aiUsage.document_pipeline_jobs.note}</div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <AdminCard title="AI Requests by Feature">
              <div style={{ padding: '16px 18px' }}>
                {aiUsage.by_feature.length === 0 ? (
                  <div style={{ fontSize: 13, color: T.textMuted }}>No AI requests in this period.</div>
                ) : (() => {
                  const maxReq = Math.max(...aiUsage.by_feature.map(f => f.requests))
                  const colors = [N.navy, N.gold, '#7C3AED', '#4C7BC9', '#4CC97B', '#DC2626']
                  return aiUsage.by_feature.map((f, i) => (
                    <div key={f.request_type} style={{ marginBottom: 12 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                        <span style={{ fontSize: 12, color: T.text, fontWeight: 500, textTransform: 'capitalize' }}>{f.request_type.replace(/_/g, ' ')}</span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: T.text }}>{f.requests.toLocaleString()}</span>
                      </div>
                      <div style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), borderRadius: 99, height: 6 }}>
                        <div style={{ background: colors[i % colors.length], borderRadius: 99, height: 6, width: `${maxReq > 0 ? (f.requests / maxReq) * 100 : 0}%`, transition: 'width 0.5s' }} />
                      </div>
                    </div>
                  ))
                })()}
              </div>
            </AdminCard>
            <AdminCard title={`Requests — Last ${aiUsage.period_days} Days`}>
              <div style={{ padding: '16px 18px' }}>
                {aiUsage.daily_trend.length === 0 ? (
                  <div style={{ fontSize: 13, color: T.textMuted }}>No data yet.</div>
                ) : (
                  <AdminBarChart data={aiUsage.daily_trend.map(d => d.requests)} labels={aiUsage.daily_trend.map(d => new Date(d.date).toLocaleDateString('default', { month: 'short', day: 'numeric' }))} height={120} color="#7C3AED" />
                )}
              </div>
            </AdminCard>
          </div>
        </>
      )}

      {aiJobActionError && <div style={{ color: '#DC2626', fontSize: 12 }}>{aiJobActionError}</div>}
      <AdminCard title="Recent AI Jobs">
        <div style={{ padding: '12px 18px', borderBottom: `1px solid ${T.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <div style={{ display: 'flex', gap: 6 }}>
            {(['all', 'failed', 'completed'] as const).map(f => (
              <button key={f} onClick={() => setAiJobsFilter(f)} style={{ padding: '7px 14px', borderRadius: 8, background: aiJobsFilter === f ? N.navy : (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: aiJobsFilter === f ? '#fff' : '#6B7280', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans', textTransform: 'capitalize' }}>{f}</button>
            ))}
          </div>
          {(() => {
            const withDuration = aiJobs.filter(j => j.started_at && j.completed_at)
            if (withDuration.length === 0) return null
            const avgMs = withDuration.reduce((sum, j) => sum + (new Date(j.completed_at as string).getTime() - new Date(j.started_at as string).getTime()), 0) / withDuration.length
            const avgLabel = avgMs < 1000 ? `${Math.round(avgMs)}ms` : `${(avgMs / 1000).toFixed(1)}s`
            return <span style={{ fontSize: 11, color: T.textMuted }}>Avg duration (this list, {withDuration.length} jobs): <strong style={{ color: T.text }}>{avgLabel}</strong></span>
          })()}
        </div>
        {aiJobsLoading ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading jobs…</div>
        ) : aiJobsError ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{aiJobsError}</div>
        ) : aiJobs.length === 0 ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No jobs match this filter.</div>
        ) : (
          <AdminTable
            cols={['Job ID', 'Feature', 'Status', 'Retries', 'Duration', 'Error', 'Created']}
            rows={aiJobs.map(j => [
              `#${j.id}`,
              j.feature.replace(/_/g, ' '),
              <AdminBadge text={j.status} color={j.status === 'completed' ? 'green' : j.status === 'failed' ? 'red' : j.status === 'processing' ? 'blue' : 'gray'} />,
              j.retry_count.toString(),
              fmtDuration(j.started_at, j.completed_at),
              j.error_message || '—',
              j.created_at ? new Date(j.created_at).toLocaleString() : '—',
            ])}
            actions={i => (aiJobs[i].status === 'failed' && aiJobs[i].feature === 'text_extraction') ? (
              <button onClick={() => retryAiJob(aiJobs[i].id)} style={{ background: '#DBEAFE', color: '#2563EB', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Retry</button>
            ) : null}
          />
        )}
      </AdminCard>
    </div>
    )
}

type AdminPaymentsSectionProps = Pick<AdminSectionController, 'mode' | 'T' | 'adminPayments' | 'adminPaymentsLoading' | 'adminPaymentsError' | 'paymentActionError' | 'refundPayment'>

export function AdminPaymentsSection({ controller }: { controller: AdminPaymentsSectionProps }) {
  const { mode, T, adminPayments, adminPaymentsLoading, adminPaymentsError, paymentActionError, refundPayment } = controller
  const now = new Date()
    const isThisMonth = (iso: string | null) => {
      if (!iso) return false
      const d = new Date(iso)
      return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth()
    }
    const successPayments = adminPayments.filter(p => p.status === 'success')
    const revenueMtd = successPayments.filter(p => isThisMonth(p.created_at)).reduce((sum, p) => sum + p.amount, 0)
    const failedThisMonth = adminPayments.filter(p => p.status === 'failed' && isThisMonth(p.created_at)).length
    const subPaymentsThisMonth = successPayments.filter(p => p.payment_type === 'subscription' && isThisMonth(p.created_at))
    const avgPlanValue = subPaymentsThisMonth.length > 0 ? Math.round(subPaymentsThisMonth.reduce((s, p) => s + p.amount, 0) / subPaymentsThisMonth.length) : 0

    // Active subscribers: latest subscription payment per user, only if still unexpired -
    // same dedup logic as the real /admin/users endpoint uses.
    const latestSubByUser = new Map<number, AdminPayment>()
    for (const p of adminPayments) {
      if (p.payment_type !== 'subscription' || p.status !== 'success' || !p.subscription_expires_at || p.user_id == null) continue
      const existing = latestSubByUser.get(p.user_id)
      if (!existing || new Date(p.subscription_expires_at) > new Date(existing.subscription_expires_at as string)) {
        latestSubByUser.set(p.user_id, p)
      }
    }
    const activeSubs = [...latestSubByUser.values()].filter(p => new Date(p.subscription_expires_at as string) > now)
    const activeByPlan: Record<string, number> = {}
    for (const p of activeSubs) { const plan = p.plan || 'other'; activeByPlan[plan] = (activeByPlan[plan] || 0) + 1 }
    const totalActive = activeSubs.length

    return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
        <AdminKPI label="Revenue (MTD)" value={`KES ${revenueMtd.toLocaleString()}`} sub={now.toLocaleString('default', { month: 'long', year: 'numeric' })} color="#16A34A" />
        <AdminKPI label="Active Subscriptions" value={totalActive.toLocaleString()} sub={Object.entries(activeByPlan).map(([plan, count]) => `${plan}: ${count}`).join(' · ') || 'None yet'} color={N.gold} />
        <AdminKPI label="Failed Payments" value={failedThisMonth.toString()} sub="This month" color="#DC2626" />
        <AdminKPI label="Avg. Plan Value" value={`KES ${avgPlanValue.toLocaleString()}`} sub="This month, subscriptions" color={T.text} />
      </div>
      <AdminCard title="Subscription Breakdown">
        <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          {Object.keys(activeByPlan).length === 0 ? (
            <div style={{ fontSize: 13, color: T.textMuted }}>No active paid subscriptions yet.</div>
          ) : Object.entries(activeByPlan).map(([plan, count]) => (
            <div key={plan}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: T.text, textTransform: 'capitalize' }}>{plan}</span>
                <span style={{ fontSize: 12, color: T.textMuted }}>{count}</span>
              </div>
              <div style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), borderRadius: 99, height: 8 }}>
                <div style={{ background: N.gold, borderRadius: 99, height: 8, width: `${totalActive > 0 ? (count / totalActive) * 100 : 0}%` }} />
              </div>
            </div>
          ))}
        </div>
      </AdminCard>
      {paymentActionError && <div style={{ color: '#DC2626', fontSize: 12 }}>{paymentActionError}</div>}
      <AdminCard title={`Transactions${adminPaymentsLoading ? '' : ` — ${adminPayments.length}`}`}>
        {adminPaymentsLoading ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading transactions…</div>
        ) : adminPaymentsError ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{adminPaymentsError}</div>
        ) : adminPayments.length === 0 ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No transactions yet.</div>
        ) : (
          <AdminTable
            cols={['Reference', 'Student', 'Plan / Item', 'Amount', 'Method', 'Status', 'Date']}
            rows={adminPayments.map(p => [
              p.reference || '—',
              p.user_display_name || p.user_email || '—',
              p.payment_type === 'subscription' ? (p.plan || '—') : (p.content_title || 'One-off purchase'),
              `KES ${p.amount.toLocaleString()}`,
              p.provider,
              <AdminBadge text={p.status} color={p.status === 'success' ? 'green' : p.status === 'refunded' ? 'amber' : p.status === 'failed' ? 'red' : 'gray'} />,
              p.created_at ? new Date(p.created_at).toLocaleDateString() : '—',
            ])}
            actions={i => adminPayments[i].status === 'success' ? (
              <button onClick={() => refundPayment(adminPayments[i].id)} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Refund</button>
            ) : null}
          />
        )}
      </AdminCard>
    </div>
    )
}

type AdminModerationSectionProps = Pick<AdminSectionController, 'mode' | 'T' | 'modReports' | 'modReportsLoading' | 'modReportsError' | 'modSummary' | 'modActionError' | 'warnPromptId' | 'setWarnPromptId' | 'warnMessage' | 'setWarnMessage' | 'warnConsequence' | 'setWarnConsequence' | 'warnRemoveContent' | 'setWarnRemoveContent' | 'flaggedMaterials' | 'flaggedMaterialsLoading' | 'flaggedMaterialsError' | 'materialActionError' | 'flagMaterialId' | 'setFlagMaterialId' | 'flagMaterialReason' | 'setFlagMaterialReason' | 'flagMaterialBusy' | 'unflagMaterial' | 'submitFlagMaterial' | 'dismissModReport' | 'removeModReportContent' | 'warnFromModReport'>

export function AdminModerationSection({ controller }: { controller: AdminModerationSectionProps }) {
  const { mode, T, modReports, modReportsLoading, modReportsError, modSummary, modActionError, warnPromptId, setWarnPromptId, warnMessage, setWarnMessage, warnConsequence, setWarnConsequence, warnRemoveContent, setWarnRemoveContent, flaggedMaterials, flaggedMaterialsLoading, flaggedMaterialsError, materialActionError, flagMaterialId, setFlagMaterialId, flagMaterialReason, setFlagMaterialReason, flagMaterialBusy, unflagMaterial, submitFlagMaterial, dismissModReport, removeModReportContent, warnFromModReport } = controller
  const targetTypeLabel: Record<string, string> = {
      forum_post: 'Forum Post',
      forum_reply: 'Forum Reply',
      group_post: 'Group Post',
      group_post_comment: 'Group Comment',
      user: 'User',
    }
    return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Warn prompt */}
      {warnPromptId != null && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setWarnPromptId(null)}>
          <div style={{ background: T.card, borderRadius: 16, padding: 24, maxWidth: 420, width: '90%', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }} onClick={e => e.stopPropagation()}>
            <div style={{ fontWeight: 800, fontSize: 17, color: T.text, marginBottom: 12 }}>Issue a warning</div>
            <div style={{ fontSize: 11, color: T.textMuted, fontWeight: 600, marginBottom: 4 }}>WHAT THEY DID WRONG</div>
            <textarea value={warnMessage} onChange={e => setWarnMessage(e.target.value)} placeholder="e.g. Your post violated our academic integrity policy." rows={2} style={{ width: '100%', border: `1px solid ${T.border}`, borderRadius: 10, padding: 10, fontSize: 13, fontFamily: 'Plus Jakarta Sans', marginBottom: 10, resize: 'vertical' }} />
            <div style={{ fontSize: 11, color: T.textMuted, fontWeight: 600, marginBottom: 4 }}>CONSEQUENCE</div>
            <textarea value={warnConsequence} onChange={e => setWarnConsequence(e.target.value)} placeholder="e.g. Further violations may result in suspension." rows={2} style={{ width: '100%', border: `1px solid ${T.border}`, borderRadius: 10, padding: 10, fontSize: 13, fontFamily: 'Plus Jakarta Sans', marginBottom: 10, resize: 'vertical' }} />
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: T.text, marginBottom: 16, cursor: 'pointer' }}>
              <input type="checkbox" checked={warnRemoveContent} onChange={e => setWarnRemoveContent(e.target.checked)} />
              Also remove the reported content
            </label>
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => setWarnPromptId(null)} style={{ flex: 1, background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: T.text, border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 13 }}>Cancel</button>
              <button
                onClick={() => warnFromModReport(warnPromptId, warnMessage.trim(), warnConsequence.trim(), warnRemoveContent)}
                disabled={!warnMessage.trim() || !warnConsequence.trim()}
                style={{ flex: 1, background: (warnMessage.trim() && warnConsequence.trim()) ? '#D97706' : '#FDE68A', color: '#fff', border: 'none', borderRadius: 10, padding: '10px 0', cursor: (warnMessage.trim() && warnConsequence.trim()) ? 'pointer' : 'not-allowed', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13 }}
              >Send Warning</button>
            </div>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
        <AdminKPI label="Open Reports" value={(modSummary?.open_reports ?? '—').toString()} color="#DC2626" />
        <AdminKPI label="Resolved Today" value={(modSummary?.resolved_today ?? '—').toString()} color="#16A34A" />
        <AdminKPI label="Warnings Issued" value={(modSummary?.warnings_issued ?? '—').toString()} sub="All time" color="#D97706" />
        <AdminKPI label="Suspended Users" value={(modSummary?.suspended_users ?? '—').toString()} color={T.text} />
      </div>

      {modActionError && <div style={{ color: '#DC2626', fontSize: 12 }}>{modActionError}</div>}
      <AdminCard title={`Report Queue${modReportsLoading ? '' : ` — ${modReports.length} Open`}`}>
        {modReportsLoading ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading reports…</div>
        ) : modReportsError ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{modReportsError}</div>
        ) : modReports.length === 0 ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No open reports.</div>
        ) : (
          <AdminTable
            cols={['#', 'Type', 'Content', 'Reported By', 'Reason', 'Priority', 'Received']}
            rows={modReports.map(r => [
              `#${r.id}`,
              targetTypeLabel[r.target_type] || r.target_type,
              r.snippet ? `"${r.snippet.slice(0, 60)}${r.snippet.length > 60 ? '…' : ''}"` : (r.target_type === 'user' ? (r.author_email || '—') : '(content removed)'),
              r.reporter_email,
              r.reason,
              <AdminBadge text={r.priority} color={r.priority === 'high' ? 'red' : r.priority === 'medium' ? 'amber' : 'gray'} />,
              r.created_at ? new Date(r.created_at).toLocaleString() : '—',
            ])}
            actions={i => (
              <div style={{ display: 'flex', gap: 5 }}>
                <button onClick={() => dismissModReport(modReports[i].id)} style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Dismiss</button>
                {modReports[i].target_type !== 'user' && (
                  <button onClick={() => removeModReportContent(modReports[i].id)} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Remove</button>
                )}
                <button onClick={() => setWarnPromptId(modReports[i].id)} style={{ background: '#FEF3C7', color: '#D97706', border: 'none', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Warn</button>
              </div>
            )}
          />
        )}
      </AdminCard>

      {materialActionError && <div style={{ color: '#DC2626', fontSize: 12 }}>{materialActionError}</div>}
      <AdminCard title={`Flagged Content${flaggedMaterialsLoading ? '' : ` — ${flaggedMaterials.length}`}`}>
        <div style={{ padding: '12px 18px', borderBottom: `1px solid ${T.border}`, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <input value={flagMaterialId} onChange={e => setFlagMaterialId(e.target.value.replace(/\D/g, ''))} placeholder="Material ID" style={{ width: 110, border: `1px solid ${T.border}`, borderRadius: 8, padding: '7px 10px', fontSize: 12, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card }} />
          <input value={flagMaterialReason} onChange={e => setFlagMaterialReason(e.target.value)} placeholder="Reason for flagging…" style={{ flex: 1, minWidth: 200, border: `1px solid ${T.border}`, borderRadius: 8, padding: '7px 10px', fontSize: 12, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card }} />
          <button disabled={flagMaterialBusy || !flagMaterialId.trim() || !flagMaterialReason.trim()} onClick={submitFlagMaterial} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 8, padding: '7px 14px', cursor: 'pointer', fontSize: 12, fontWeight: 700, fontFamily: 'Plus Jakarta Sans', opacity: (flagMaterialBusy || !flagMaterialId.trim() || !flagMaterialReason.trim()) ? 0.6 : 1 }}>Flag</button>
        </div>
        {flaggedMaterialsLoading ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading flagged content…</div>
        ) : flaggedMaterialsError ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{flaggedMaterialsError}</div>
        ) : flaggedMaterials.length === 0 ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No flagged content.</div>
        ) : (
          <AdminTable
            cols={['#', 'Type', 'File', 'Reason', 'Flagged By', 'Flagged At']}
            rows={flaggedMaterials.map(m => [
              `#${m.id}`,
              m.material_type,
              m.file_type || '—',
              m.flagged_reason || '—',
              m.flagged_by_email || '—',
              m.flagged_at ? new Date(m.flagged_at).toLocaleString() : '—',
            ])}
            actions={i => (
              <button onClick={() => unflagMaterial(flaggedMaterials[i].id)} style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Unflag</button>
            )}
          />
        )}
      </AdminCard>
    </div>
    )
}

type AdminAnalyticsSectionProps = Pick<AdminSectionController, 'mode' | 'T' | 'analytics' | 'analyticsLoading' | 'analyticsError' | 'universityEngagement' | 'universityEngagementLoading' | 'universityEngagementError'>

export function AdminAnalyticsSection({ controller }: { controller: AdminAnalyticsSectionProps }) {
  const { mode, T, analytics, analyticsLoading, analyticsError, universityEngagement, universityEngagementLoading, universityEngagementError } = controller
  const fmtBytes = (n: number) => {
      if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`
      if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`
      if (n >= 1e3) return `${(n / 1e3).toFixed(1)} KB`
      return `${n} B`
    }
    return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {analyticsLoading ? (
        <div style={{ padding: '24px 0', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading analytics…</div>
      ) : analyticsError ? (
        <div style={{ padding: '24px 0', textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{analyticsError}</div>
      ) : analytics && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
            <AdminKPI label="Total Users" value={analytics.total_users.toLocaleString()} sub={`${analytics.active_today.toLocaleString()} active today`} color={T.text} />
            <AdminKPI label="Total Revenue" value={`KES ${analytics.total_revenue.toLocaleString()}`} sub={`KES ${analytics.revenue_last_30d.toLocaleString()} last 30d`} color="#16A34A" />
            <AdminKPI label="Content Items" value={analytics.total_content_items.toLocaleString()} sub={`${analytics.total_units.toLocaleString()} units`} color={N.gold} />
            <AdminKPI label="Storage Used" value={fmtBytes(analytics.storage_used_bytes)} sub="Deduplicated files" color="#4C7BC9" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <AdminCard title="New Signups — Last 30 Days">
              <div style={{ padding: '16px 18px' }}>
                {analytics.signups_per_day.length === 0 ? (
                  <div style={{ fontSize: 13, color: T.textMuted }}>No signups in this period.</div>
                ) : (
                  <>
                    <div style={{ fontSize: 28, fontWeight: 800, color: T.text, marginBottom: 4 }}>
                      {analytics.signups_per_day.reduce((s, d) => s + d.count, 0).toLocaleString()} <span style={{ fontSize: 13, color: T.textMuted, fontWeight: 500 }}>new users, 30 days</span>
                    </div>
                    <AdminLineChart data={analytics.signups_per_day.map(d => d.count)} color={T.text} height={80} />
                  </>
                )}
              </div>
            </AdminCard>
            <AdminCard title="Revenue — Last 30 Days">
              <div style={{ padding: '16px 18px' }}>
                {analytics.revenue_per_day.length === 0 ? (
                  <div style={{ fontSize: 13, color: T.textMuted }}>No revenue in this period.</div>
                ) : (
                  <>
                    <div style={{ fontSize: 28, fontWeight: 800, color: '#16A34A', marginBottom: 4 }}>
                      KES {analytics.revenue_per_day.reduce((s, d) => s + d.amount, 0).toLocaleString()} <span style={{ fontSize: 13, color: T.textMuted, fontWeight: 500 }}>30-day total</span>
                    </div>
                    <AdminLineChart data={analytics.revenue_per_day.map(d => d.amount)} color="#16A34A" height={80} />
                  </>
                )}
              </div>
            </AdminCard>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <AdminCard title="Content by Type">
              <div style={{ padding: '16px 18px' }}>
                {Object.keys(analytics.content_by_type).length === 0 ? (
                  <div style={{ fontSize: 13, color: T.textMuted }}>No content items yet.</div>
                ) : (() => {
                  const entries = Object.entries(analytics.content_by_type)
                  const max = Math.max(...entries.map(([, c]) => c))
                  return entries.map(([type, count]) => (
                    <div key={type} style={{ marginBottom: 10 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                        <span style={{ fontSize: 12, color: T.text, fontWeight: 500, textTransform: 'capitalize' }}>{type.replace(/_/g, ' ')}</span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: T.text }}>{count}</span>
                      </div>
                      <div style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), borderRadius: 99, height: 6 }}>
                        <div style={{ background: N.gold, borderRadius: 99, height: 6, width: `${max > 0 ? (count / max) * 100 : 0}%` }} />
                      </div>
                    </div>
                  ))
                })()}
              </div>
            </AdminCard>
            <AdminCard title="Payments by Status">
              <div style={{ padding: '16px 18px' }}>
                {Object.keys(analytics.payments_by_status).length === 0 ? (
                  <div style={{ fontSize: 13, color: T.textMuted }}>No payments yet.</div>
                ) : (() => {
                  const entries = Object.entries(analytics.payments_by_status)
                  const max = Math.max(...entries.map(([, c]) => c))
                  const colorFor = (s: string) => s === 'success' ? '#16A34A' : s === 'refunded' ? '#D97706' : s === 'failed' ? '#DC2626' : '#9CA3AF'
                  return entries.map(([status, count]) => (
                    <div key={status} style={{ marginBottom: 10 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                        <span style={{ fontSize: 12, color: T.text, fontWeight: 500, textTransform: 'capitalize' }}>{status}</span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: T.text }}>{count}</span>
                      </div>
                      <div style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), borderRadius: 99, height: 6 }}>
                        <div style={{ background: colorFor(status), borderRadius: 99, height: 6, width: `${max > 0 ? (count / max) * 100 : 0}%` }} />
                      </div>
                    </div>
                  ))
                })()}
              </div>
            </AdminCard>
          </div>

          <AdminCard title="Top Universities by Engagement">
            {universityEngagementLoading ? (
              <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading…</div>
            ) : universityEngagementError ? (
              <div style={{ padding: '24px 18px', textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{universityEngagementError}</div>
            ) : universityEngagement.length === 0 ? (
              <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No students with a university on file yet.</div>
            ) : (
              <AdminTable
                cols={['University', 'Students', 'Documents', 'AI Requests', 'Premium Users', 'Engagement']}
                rows={universityEngagement.map(u => [
                  u.university_name,
                  u.students.toLocaleString(),
                  u.documents.toLocaleString(),
                  u.ai_requests.toLocaleString(),
                  u.premium_users.toLocaleString(),
                  <AdminBadge text={u.engagement} color={u.engagement === 'Very High' || u.engagement === 'High' ? 'green' : u.engagement === 'Medium' ? 'amber' : 'gray'} />,
                ])}
              />
            )}
          </AdminCard>
        </>
      )}
    </div>
    )
}
