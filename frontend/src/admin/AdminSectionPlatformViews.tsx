import { N } from '../theme/theme'
import { AdminBadge, AdminTable, AdminCard } from './AdminShared'
import type { AdminSectionController } from './useAdminSectionController'

type AdminSystemSectionProps = Pick<AdminSectionController, 'mode' | 'T' | 'infrastructure' | 'infrastructureLoading' | 'infrastructureError' | 'otpAdmin' | 'setOtpAdmin' | 'otpAdminLoading' | 'otpAdminSaving' | 'otpAdminError' | 'systemCapacity' | 'storageCapacity' | 'storageCapacityLoading' | 'storageCapacityError' | 'systemCapacityLoading' | 'systemCapacityError' | 'tierSwitching' | 'tierSwitchError' | 'adminAccounts' | 'adminAccountsLoading' | 'adminAccountsError' | 'adminAccountActionError' | 'auditLogs' | 'auditLogsLoading' | 'auditLogsError' | 'auditActionFilter' | 'setAuditActionFilter' | 'auditTargetTypeFilter' | 'setAuditTargetTypeFilter' | 'auditDays' | 'setAuditDays' | 'auditPage' | 'loadAuditLogs' | 'saveOtpAdmin' | 'switchSupabaseTier' | 'setAdminAccountRole'>

export function AdminSystemSection({ controller }: { controller: AdminSystemSectionProps }) {
  const { mode, T, infrastructure, infrastructureLoading, infrastructureError, otpAdmin, setOtpAdmin, otpAdminLoading, otpAdminSaving, otpAdminError, systemCapacity, storageCapacity, storageCapacityLoading, storageCapacityError, systemCapacityLoading, systemCapacityError, tierSwitching, tierSwitchError, adminAccounts, adminAccountsLoading, adminAccountsError, adminAccountActionError, auditLogs, auditLogsLoading, auditLogsError, auditActionFilter, setAuditActionFilter, auditTargetTypeFilter, setAuditTargetTypeFilter, auditDays, setAuditDays, auditPage, loadAuditLogs, saveOtpAdmin, switchSupabaseTier, setAdminAccountRole } = controller
  const fmtBytesSys = (n: number) => {
      if (n >= 1e9) return `${(n / 1e9).toFixed(2)} GB`
      if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`
      if (n >= 1e3) return `${(n / 1e3).toFixed(1)} KB`
      return `${n} B`
    }
    const barColor = (pct: number) => pct >= 90 ? '#DC2626' : pct >= 70 ? '#D97706' : '#16A34A'
    return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.5 }}>
        Tracks whether the current infrastructure can handle real usage, and what it's costing — not third-party uptime (that would need a separate monitoring integration, not built yet).
      </div>

      {infrastructureLoading ? (
        <AdminCard title="Pay-as-you-grow infrastructure"><div style={{ padding: '18px', color: T.textMuted, fontSize: 12 }}>Loading live usage…</div></AdminCard>
      ) : infrastructureError ? (
        <AdminCard title="Pay-as-you-grow infrastructure"><div style={{ padding: '18px', color: '#DC2626', fontSize: 12 }}>{infrastructureError}</div></AdminCard>
      ) : infrastructure && (
        <AdminCard title="Pay-as-you-grow infrastructure">
          <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 10 }}>
              {[[ 'Active today', String(infrastructure.active_users.today) ], [ 'Active 7d', String(infrastructure.active_users.last_7d) ], [ 'Studying today', String(infrastructure.study.students_today) ]].map(([label, value]) => (
                <div key={label} style={{ background: mode === 'dark' ? 'rgba(255,255,255,.04)' : '#F9FAFB', borderRadius: 10, padding: '11px 12px' }}><div style={{ fontSize: 10, color: T.textMuted }}>{label}</div><div style={{ fontSize: 20, fontWeight: 800, color: T.text, marginTop: 4 }}>{value}</div></div>
              ))}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {[{ label: 'Database', used: infrastructure.database.used_bytes, limit: infrastructure.database.limit_bytes, pct: infrastructure.database.percent }, { label: 'File storage', used: infrastructure.storage.used_bytes, limit: infrastructure.storage.limit_bytes, pct: infrastructure.storage.percent }].map(item => (
                <div key={item.label}><div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}><span style={{ fontSize: 12, fontWeight: 700, color: T.text }}>{item.label}</span><span style={{ fontSize: 11, color: item.pct >= 90 ? '#DC2626' : T.textMuted }}>{fmtBytesSys(item.used)} / {fmtBytesSys(item.limit)}</span></div><div style={{ height: 7, borderRadius: 99, background: mode === 'dark' ? 'rgba(255,255,255,.08)' : '#F0F1F4' }}><div style={{ height: 7, width: Math.min(item.pct, 100) + '%', borderRadius: 99, background: barColor(item.pct) }} /></div><div style={{ fontSize: 10, color: T.textMuted, marginTop: 4 }}>{Math.round(item.pct)}% used · {item.pct >= 90 ? 'action soon' : item.pct >= 75 ? 'watch' : 'comfortable'}</div></div>
              ))}
            </div>
            <div style={{ background: mode === 'dark' ? 'rgba(255,255,255,.04)' : '#F9FAFB', borderRadius: 10, padding: 12 }}>
              <div style={{ fontSize: 10, color: T.textMuted }}>Podcast GPU & autoscaler</div>
              <div style={{ fontSize: 17, fontWeight: 800, color: T.text, marginTop: 4 }}>{(infrastructure as any).gpu?.gpu || 'RTX A2000'}</div>
              <div style={{ fontSize: 10, color: T.textMuted, marginTop: 4 }}>
                {(infrastructure as any).gpu_scaling?.current_workers ?? 0} / {(infrastructure as any).gpu_scaling?.max_workers ?? 1} workers · {(infrastructure as any).gpu_scaling?.pending_jobs ?? 0} pending · {(infrastructure as any).gpu_scaling?.processing_jobs ?? 0} processing
              </div>
              <div style={{ fontSize: 10, color: T.textMuted, marginTop: 4 }}>
                Oldest pending: {(infrastructure as any).gpu_scaling?.oldest_pending_age_seconds == null ? 'none' : (infrastructure as any).gpu_scaling.oldest_pending_age_seconds + 's'} · limit {(infrastructure as any).gpu_scaling?.max_pending_jobs_per_worker ?? 3} jobs/worker
              </div>
              <div style={{ fontSize: 10, color: T.text, marginTop: 5, lineHeight: 1.4 }}>
                <strong>{(infrastructure as any).gpu_scaling?.latest_decision?.action || 'hold'}</strong>{' — '}{(infrastructure as any).gpu_scaling?.latest_decision?.reason_text || 'No scaling decision recorded yet.'}
              </div>
              <div style={{ fontSize: 10, color: T.textMuted, marginTop: 4 }}>
                {(infrastructure as any).gpu_scaling?.dry_run ? 'DRY RUN: GPU rental/destruction is blocked.' : 'Automatic scaling policy active.'}
                <div style={{ marginTop: 8, display: 'grid', gap: 6 }}>
                  <div style={{ fontSize: 10, fontWeight: 800, color: T.text }}>Recent scaling decisions</div>
                  {((infrastructure as any).gpu_scaling?.recent_decisions || []).slice(0, 8).map((d: any, i: number) => (
                    <div key={i} style={{ borderTop: i === 0 ? '0' : '1px solid rgba(127,127,127,.16)', paddingTop: i === 0 ? 0 : 6 }}>
                      <div style={{ fontSize: 10, fontWeight: 800, color: T.text }}>{d.action} · {d.reason_code}</div>
                      <div style={{ fontSize: 10, color: T.textMuted, lineHeight: 1.35, marginTop: 2 }}>{d.reason_text}</div>
                      <div style={{ fontSize: 9, color: T.textMuted, marginTop: 2 }}>
                        Queue {d.queue_depth} · workers {d.current_workers}→{d.target_workers} ·
                        {d.gpu_name ? ' ' + d.gpu_name + ' ' + (d.gpu_vram_gb ?? '—') + 'GB VRAM' : ''} ·
                        {d.projected_hourly_spend_usd == null ? ' spend n/a' : ' projected $' + Number(d.projected_hourly_spend_usd).toFixed(4) + '/h'} ·
                        {d.dry_run ? ' dry-run' : ' enforced'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div style={{ background: mode === 'dark' ? 'rgba(255,255,255,.04)' : '#F9FAFB', borderRadius: 10, padding: 12 }}><div style={{ fontSize: 10, color: T.textMuted }}>AI spend this month</div><div style={{ fontSize: 21, fontWeight: 800, color: T.text, marginTop: 4 }}>${infrastructure.ai.spend_mtd_usd.toFixed(2)}</div><div style={{ fontSize: 10, color: T.textMuted, marginTop: 3 }}>Projected ${infrastructure.ai.projected_month_end_usd.toFixed(2)} · {infrastructure.ai.requests_mtd} requests</div></div>
              <div style={{ background: mode === 'dark' ? 'rgba(255,255,255,.04)' : '#F9FAFB', borderRadius: 10, padding: 12 }}><div style={{ fontSize: 10, color: T.textMuted }}>Revenue this month</div><div style={{ fontSize: 21, fontWeight: 800, color: N.gold, marginTop: 4 }}>KES {infrastructure.payments.revenue_mtd_kes.toLocaleString()}</div><div style={{ fontSize: 10, color: T.textMuted, marginTop: 3 }}>Est. Paystack fees KES {infrastructure.payments.estimated_paystack_fees_mtd_kes.toLocaleString()}</div></div>
            </div>
            <div style={{ background: 'rgba(201,168,76,.08)', border: '1px solid rgba(201,168,76,.2)', borderRadius: 11, padding: '10px 12px', fontSize: 11, color: T.text, lineHeight: 1.55 }}><strong>Upgrade rule:</strong> Prepza does not upgrade provider plans automatically. SES below is live account telemetry, not a hardcoded free-tier estimate.</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 10, color: T.textMuted }}><div>Render Hobby: {infrastructure.known_limits.render_hobby_build_minutes} build min · {infrastructure.known_limits.render_hobby_bandwidth_gb} GB bandwidth</div><div>Supabase Free: {infrastructure.known_limits.supabase_free_egress_gb} GB egress · 2M realtime</div><div>SES: {infrastructure.ses.status} · {infrastructure.ses.sent_last_24_hours == null ? 'quota unavailable' : infrastructure.ses.sent_last_24_hours + ' sent / ' + (infrastructure.ses.max_24_hour_send ?? '—') + ' 24h'}</div><div>Podcast TTS: generated once per artifact; no per-play generation cost</div></div>
            <div style={{ background: mode === 'dark' ? 'rgba(255,255,255,.04)' : '#F9FAFB', borderRadius: 10, padding: 12 }}>
              <div style={{ fontSize: 10, color: T.textMuted }}>Transactional email — last 24h</div>
              <div style={{ fontSize: 18, fontWeight: 800, color: T.text, marginTop: 4 }}>{infrastructure.ses.application_sends_last_24_hours.toLocaleString()}</div>
              <div style={{ fontSize: 10, color: T.textMuted, marginTop: 3 }}>Verification {infrastructure.ses.verification_sends_last_24_hours.toLocaleString()} · password reset {infrastructure.ses.password_reset_sends_last_24_hours.toLocaleString()}</div>
            </div>
          </div>
        </AdminCard>
      )}
      {otpAdminLoading ? (
        <AdminCard title="Email authentication">
          <div style={{ padding: 18, color: T.textMuted, fontSize: 12 }}>Loading OTP settings…</div>
        </AdminCard>
      ) : otpAdminError ? (
        <AdminCard title="Email authentication">
          <div style={{ padding: 18, color: '#DC2626', fontSize: 12 }}>{otpAdminError}</div>
        </AdminCard>
      ) : otpAdmin && (
        <AdminCard title="Email authentication — SES OTP">
          <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {[
                ['Provider', otpAdmin.ses.status],
                ['Region', otpAdmin.ses.region || 'Not configured'],
                ['24h quota', otpAdmin.ses.max_24_hour_send == null ? '—' : otpAdmin.ses.max_24_hour_send.toLocaleString()],
                ['Send rate', otpAdmin.ses.max_send_rate == null ? '—' : otpAdmin.ses.max_send_rate + '/sec'],
              ].map(([label, value]) => <div key={label} style={{ background: mode === 'dark' ? 'rgba(255,255,255,.04)' : '#F9FAFB', borderRadius: 10, padding: 11 }}><div style={{ fontSize: 10, color: T.textMuted }}>{label}</div><div style={{ fontSize: 14, fontWeight: 800, color: T.text, marginTop: 4 }}>{value}</div></div>)}
            </div>
            <div style={{ fontSize: 11, color: T.textMuted, lineHeight: 1.5 }}>
              Configure the safe operational policy here. Provider credentials remain Render environment variables and are never shown.
            </div>
            <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, fontSize: 12, color: T.text }}>
              <span>OTP verification enabled</span>
              <button type="button" disabled={otpAdminSaving} onClick={() => saveOtpAdmin({ otp_enabled: otpAdmin.settings.otp_enabled !== 'true' })} style={{ border: 'none', borderRadius: 999, padding: '7px 12px', background: otpAdmin.settings.otp_enabled === 'true' ? '#DCFCE7' : '#F3F4F6', color: otpAdmin.settings.otp_enabled === 'true' ? '#16A34A' : '#6B7280', fontWeight: 800, cursor: 'pointer' }}>{otpAdmin.settings.otp_enabled === 'true' ? 'Enabled' : 'Disabled'}</button>
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 8 }}>
              {[
                ['OTP length', 'otp_length'],
                ['Expiry (min)', 'otp_expiry_minutes'],
                ['Max attempts', 'otp_max_attempts'],
                ['Resend cooldown (sec)', 'otp_resend_cooldown_seconds'],
                ['Target sends/hour', 'otp_max_sends_per_target_hour'],
                ['IP sends/hour', 'otp_max_sends_per_ip_hour'],
              ].map(([label, key]) => (
                <label key={key} style={{ fontSize: 10, color: T.textMuted }}>{label}
                  <input value={otpAdmin.settings[key] || ''} onChange={e => setOtpAdmin(v => v ? ({ ...v, settings: { ...v.settings, [key]: e.target.value } }) : v)} onBlur={e => saveOtpAdmin({ [key]: Number(e.target.value) })} inputMode="numeric" style={{ width: '100%', boxSizing: 'border-box', marginTop: 5, padding: '8px 9px', borderRadius: 9, border: '1px solid rgba(128,128,128,.2)', background: T.card, color: T.text }} />
                </label>
              ))}
            </div>
          </div>
        </AdminCard>
      )}
      {storageCapacityLoading ? (
        <div style={{padding:'24px 0',textAlign:'center',color:T.textMuted,fontSize:13}}>Loading storage capacity…</div>
      ) : storageCapacityError ? (
        <div style={{padding:'24px 0',textAlign:'center',color:'#DC2626',fontSize:13}}>{storageCapacityError}</div>
      ) : storageCapacity && (
        <AdminCard title="Object storage — Supabase vs Cloudflare R2">
          <div style={{padding:'16px 18px',display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(220px,1fr))',gap:12}}>
            <div style={{border:'1px solid #E5E7EB',borderRadius:12,padding:14}}>
              <div style={{fontWeight:800,color:T.text}}>Supabase Storage</div>
              <div style={{fontSize:22,fontWeight:800,marginTop:6}}>{storageCapacity.supabase.object_bytes == null ? '—' : (storageCapacity.supabase.object_bytes/1024/1024/1024).toFixed(2)+' GB'}</div>
              <div style={{fontSize:11,color:T.textMuted,marginTop:4}}>{storageCapacity.supabase.configured ? 'Configured' : 'Not configured'} · database-backed telemetry</div>
            </div>
            <div style={{border:'1px solid #E5E7EB',borderRadius:12,padding:14}}>
              <div style={{fontWeight:800,color:T.text}}>Cloudflare R2</div>
              <div style={{fontSize:22,fontWeight:800,marginTop:6}}>{storageCapacity.r2.enabled ? (storageCapacity.r2.bytes/1024/1024/1024).toFixed(2)+' GB' : 'Not enabled'}</div>
              <div style={{fontSize:11,color:T.textMuted,marginTop:4}}>{storageCapacity.r2.enabled ? `${storageCapacity.r2.objects.toLocaleString()} objects · cached 5 min` : 'Configure R2 credentials on Render'}</div>
            </div>
          </div>
        </AdminCard>
      )}
      {systemCapacityLoading ? (
        <div style={{ padding: '24px 0', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading capacity data…</div>
      ) : systemCapacityError ? (
        <div style={{ padding: '24px 0', textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{systemCapacityError}</div>
      ) : systemCapacity && (() => {
        const dbPct = (systemCapacity.db_size_bytes / systemCapacity.db_size_limit_bytes) * 100
        const storagePct = (systemCapacity.storage_used_bytes / systemCapacity.storage_limit_bytes) * 100
        const connPct = (systemCapacity.active_connections / systemCapacity.connection_limit) * 100
        return (
          <>
            <AdminCard title={`Supabase ${systemCapacity.tier.charAt(0).toUpperCase()}${systemCapacity.tier.slice(1)} Tier — Capacity`}>
              <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 11, color: T.textMuted, fontWeight: 600 }}>Plan:</span>
                  {systemCapacity.available_tiers.map(t => (
                    <button
                      key={t}
                      onClick={() => switchSupabaseTier(t)}
                      disabled={tierSwitching || t === systemCapacity.tier}
                      style={{
                        padding: '6px 14px',
                        borderRadius: 8,
                        background: t === systemCapacity.tier ? N.navy : (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'),
                        color: t === systemCapacity.tier ? '#fff' : '#6B7280',
                        border: 'none',
                        cursor: (tierSwitching || t === systemCapacity.tier) ? 'default' : 'pointer',
                        opacity: tierSwitching && t !== systemCapacity.tier ? 0.5 : 1,
                        fontSize: 12,
                        fontWeight: 600,
                        fontFamily: 'Plus Jakarta Sans',
                        textTransform: 'capitalize',
                      }}
                    >{t}</button>
                  ))}
                  {tierSwitching && <span style={{ fontSize: 11, color: T.textMuted }}>Switching…</span>}
                </div>
                {tierSwitchError && <div style={{ color: '#DC2626', fontSize: 12 }}>{tierSwitchError}</div>}
                {[
                  { label: 'Database Size', used: fmtBytesSys(systemCapacity.db_size_bytes), total: fmtBytesSys(systemCapacity.db_size_limit_bytes), pct: dbPct },
                  { label: 'File Storage', used: fmtBytesSys(systemCapacity.storage_used_bytes), total: fmtBytesSys(systemCapacity.storage_limit_bytes), pct: storagePct },
                  { label: 'DB Connections (live)', used: systemCapacity.active_connections.toString(), total: systemCapacity.connection_limit.toString(), pct: connPct },
                ].map(r => (
                  <div key={r.label}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{r.label}</span>
                      <span style={{ fontSize: 12, color: r.pct >= 90 ? '#DC2626' : '#9CA3AF', fontWeight: r.pct >= 90 ? 700 : 400 }}>{r.used} / {r.total} ({Math.round(r.pct)}%)</span>
                    </div>
                    <div style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), borderRadius: 99, height: 8 }}>
                      <div style={{ background: barColor(r.pct), borderRadius: 99, height: 8, width: `${Math.min(r.pct, 100)}%`, transition: 'width 0.5s' }} />
                    </div>
                  </div>
                ))}
                {(dbPct >= 80 || storagePct >= 80) && (
                  <div style={{ background: '#FEF3C7', borderRadius: 10, padding: '10px 14px', fontSize: 12, color: '#92400E', fontWeight: 600 }}>
                    ⚠️ You're approaching the Supabase free tier limit — worth planning the Pro tier upgrade (~$25/mo) soon.
                  </div>
                )}
              </div>
            </AdminCard>

            <AdminCard title="AI (Anthropic) Spend">
              <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.04)' : '#F9FAFB'), borderRadius: 10, padding: '12px 14px' }}>
                    <div style={{ fontSize: 11, color: T.textMuted }}>Spent this month ({systemCapacity.days_elapsed_this_month}/{systemCapacity.days_in_month} days)</div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: T.text }}>${systemCapacity.ai_spend_mtd_usd.toFixed(2)}</div>
                  </div>
                  <div style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.04)' : '#F9FAFB'), borderRadius: 10, padding: '12px 14px' }}>
                    <div style={{ fontSize: 11, color: T.textMuted }}>Projected month-end (at current pace)</div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: N.gold }}>${systemCapacity.ai_spend_projected_month_end_usd.toFixed(2)}</div>
                  </div>
                </div>
                <div style={{ fontSize: 11, color: T.textMuted }}>No fixed budget cap set — this is a raw spend tracker so you can decide what to budget as usage grows.</div>
              </div>
            </AdminCard>
          </>
        )
      })()}

      {adminAccountActionError && <div style={{ color: '#DC2626', fontSize: 12 }}>{adminAccountActionError}</div>}
      <AdminCard title="Admin Accounts">
        {adminAccountsLoading ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading admin accounts…</div>
        ) : adminAccountsError ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{adminAccountsError}</div>
        ) : adminAccounts.length === 0 ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No admin accounts found.</div>
        ) : (
          <AdminTable
            cols={['Name', 'Email', 'Joined', 'Status']}
            rows={adminAccounts.map(a => [
              a.display_name || '(no name)',
              a.email,
              a.created_at ? new Date(a.created_at).toLocaleDateString() : '—',
              <AdminBadge text={a.is_suspended ? 'Suspended' : 'Active'} color={a.is_suspended ? 'red' : 'green'} />,
            ])}
            actions={i => (
              <button
                onClick={() => setAdminAccountRole(adminAccounts[i].id, false)}
                style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}
              >Revoke Admin</button>
            )}
          />
        )}
      </AdminCard>

      <AdminCard title="Audit Log">
        <div style={{ padding: '12px 18px', borderBottom: `1px solid ${T.border}`, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <input value={auditActionFilter} onChange={e => setAuditActionFilter(e.target.value)} placeholder="Filter by action…" style={{ minWidth: 160, border: `1px solid ${T.border}`, borderRadius: 8, padding: '7px 10px', fontSize: 12, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card }} />
          <input value={auditTargetTypeFilter} onChange={e => setAuditTargetTypeFilter(e.target.value)} placeholder="Target type…" style={{ minWidth: 140, border: `1px solid ${T.border}`, borderRadius: 8, padding: '7px 10px', fontSize: 12, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card }} />
          <select value={auditDays} onChange={e => setAuditDays(Number(e.target.value))} style={{ border: `1px solid ${T.border}`, borderRadius: 8, padding: '7px 10px', fontSize: 12, fontFamily: 'Plus Jakarta Sans', color: T.text, background: T.card }}>
            {[7, 30, 90, 365].map(d => <option key={d} value={d}>Last {d}d</option>)}
          </select>
        </div>
        {auditLogsLoading ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading audit log…</div>
        ) : auditLogsError ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{auditLogsError}</div>
        ) : auditLogs.length === 0 ? (
          <div style={{ padding: '24px 18px', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No audit log entries in this window.</div>
        ) : (
          <>
            <AdminTable
              cols={['When', 'Actor', 'Action', 'Target']}
              rows={auditLogs.map(l => [
                l.created_at ? new Date(l.created_at).toLocaleString() : '—',
                l.actor_email || (l.actor_id ? `#${l.actor_id}` : 'System'),
                l.action,
                l.target_type ? `${l.target_type}${l.target_id != null ? ` #${l.target_id}` : ''}` : '—',
              ])}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 18px' }}>
              <button disabled={auditPage <= 1} onClick={() => loadAuditLogs(auditPage - 1)} style={{ background: 'none', border: 'none', color: auditPage <= 1 ? T.textMuted : N.gold, cursor: auditPage <= 1 ? 'default' : 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>← Previous</button>
              <span style={{ fontSize: 11, color: T.textMuted }}>Page {auditPage}</span>
              <button disabled={auditLogs.length < 50} onClick={() => loadAuditLogs(auditPage + 1)} style={{ background: 'none', border: 'none', color: auditLogs.length < 50 ? T.textMuted : N.gold, cursor: auditLogs.length < 50 ? 'default' : 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Next →</button>
            </div>
          </>
        )}
      </AdminCard>
    </div>
    )
}

type AdminCommunicationsSectionProps = Pick<AdminSectionController, 'T' | 'search' | 'annTitle' | 'setAnnTitle' | 'annBody' | 'setAnnBody' | 'annUniversityId' | 'setAnnUniversityId' | 'annProgramId' | 'setAnnProgramId' | 'annYear' | 'setAnnYear' | 'annSemester' | 'setAnnSemester' | 'annGroupId' | 'setAnnGroupId' | 'annGroupName' | 'setAnnGroupName' | 'annGroupSearch' | 'setAnnGroupSearch' | 'annGroupResults' | 'setAnnGroupResults' | 'annUniversities' | 'annPrograms' | 'annSending' | 'annError' | 'annSent' | 'announcements' | 'announcementsLoading' | 'sendAnnouncement'>

export function AdminCommunicationsSection({ controller }: { controller: AdminCommunicationsSectionProps }) {
  const { T, search, annTitle, setAnnTitle, annBody, setAnnBody, annUniversityId, setAnnUniversityId, annProgramId, setAnnProgramId, annYear, setAnnYear, annSemester, setAnnSemester, annGroupId, setAnnGroupId, annGroupName, setAnnGroupName, annGroupSearch, setAnnGroupSearch, annGroupResults, setAnnGroupResults, annUniversities, annPrograms, annSending, annError, annSent, announcements, announcementsLoading, sendAnnouncement } = controller
  return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <AdminCard title="Send Announcement">
          <div style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <input value={annTitle} onChange={e => setAnnTitle(e.target.value)} placeholder="Announcement title…" maxLength={200} style={{ border: `1.5px solid ${T.border}`, borderRadius: 10, padding: '10px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text }} />
            <textarea value={annBody} onChange={e => setAnnBody(e.target.value)} placeholder="Write your message…" rows={4} maxLength={500} style={{ border: `1.5px solid ${T.border}`, borderRadius: 10, padding: '10px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, resize: 'none', lineHeight: 1.6 }} />

            <div style={{ fontSize: 11, fontWeight: 700, color: T.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 4 }}>Audience (leave blank for everyone)</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 10 }}>
              <select value={annUniversityId ?? ''} onChange={e => setAnnUniversityId(e.target.value ? Number(e.target.value) : null)} style={{ border: `1.5px solid ${T.border}`, borderRadius: 10, padding: '9px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', color: T.text, background: T.card }}>
                <option value="">All universities</option>
                {annUniversities.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
              </select>
              <select value={annProgramId ?? ''} onChange={e => setAnnProgramId(e.target.value ? Number(e.target.value) : null)} disabled={!annUniversityId} style={{ border: `1.5px solid ${T.border}`, borderRadius: 10, padding: '9px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', color: T.text, background: T.card, opacity: annUniversityId ? 1 : 0.5 }}>
                <option value="">All courses</option>
                {annPrograms.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <select value={annYear ?? ''} onChange={e => setAnnYear(e.target.value ? Number(e.target.value) : null)} style={{ border: `1.5px solid ${T.border}`, borderRadius: 10, padding: '9px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', color: T.text, background: T.card }}>
                <option value="">All years</option>
                {[1,2,3,4].map(y => <option key={y} value={y}>Year {y}</option>)}
              </select>
              <select value={annSemester ?? ''} onChange={e => setAnnSemester(e.target.value ? Number(e.target.value) : null)} style={{ border: `1.5px solid ${T.border}`, borderRadius: 10, padding: '9px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', color: T.text, background: T.card }}>
                <option value="">All semesters</option>
                {[1,2].map(s => <option key={s} value={s}>Semester {s}</option>)}
              </select>
            </div>

            <div>
              {annGroupId ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: `${N.gold}15`, border: `1px solid ${N.gold}40`, borderRadius: 10, padding: '8px 12px' }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: T.text, flex: 1 }}>Group: {annGroupName}</span>
                  <button onClick={() => { setAnnGroupId(null); setAnnGroupName('') }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.textMuted, fontSize: 14 }}>×</button>
                </div>
              ) : (
                <div style={{ position: 'relative' }}>
                  <input value={annGroupSearch} onChange={e => setAnnGroupSearch(e.target.value)} placeholder="Or search a specific group…" style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 10, padding: '9px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, boxSizing: 'border-box' }} />
                  {annGroupResults.length > 0 && (
                    <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, marginTop: 4, boxShadow: '0 4px 16px rgba(0,0,0,0.08)', zIndex: 10, maxHeight: 180, overflowY: 'auto' }}>
                      {annGroupResults.map(g => (
                        <button key={g.id} onClick={() => { setAnnGroupId(g.id); setAnnGroupName(g.name); setAnnGroupSearch(''); setAnnGroupResults([]) }} style={{ display: 'block', width: '100%', padding: '10px 12px', background: 'none', border: 'none', textAlign: 'left', cursor: 'pointer', fontSize: 13, fontFamily: 'Plus Jakarta Sans', color: T.text }}>{g.name}</button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {annError && <div style={{ color: '#DC2626', fontSize: 12, fontWeight: 600 }}>{annError}</div>}
            {annSent && <div style={{ color: '#16A34A', fontSize: 12, fontWeight: 600 }}>Announcement sent.</div>}

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={sendAnnouncement} disabled={annSending || !annTitle.trim() || !annBody.trim()} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, border: 'none', borderRadius: 10, padding: '8px 20px', cursor: annSending ? 'wait' : 'pointer', fontWeight: 800, fontSize: 13, fontFamily: 'Plus Jakarta Sans', opacity: (!annTitle.trim() || !annBody.trim()) ? 0.5 : 1 }}>{annSending ? 'Sending…' : 'Send Now'}</button>
            </div>
          </div>
          <div style={{ borderTop: `1px solid ${T.border}` }}>
            {announcementsLoading ? (
              <div style={{ padding: '18px 20px', fontSize: 12, color: T.textMuted }}>Loading…</div>
            ) : announcements.length === 0 ? (
              <div style={{ padding: '18px 20px', fontSize: 12, color: T.textMuted }}>No announcements sent yet.</div>
            ) : announcements.map((a, i) => (
              <div key={a.id} style={{ padding: '14px 20px', borderBottom: i < announcements.length - 1 ? `1px solid ${T.border}` : 'none', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13, color: T.text }}>{a.title}</div>
                  <div style={{ fontSize: 12, color: T.textMuted, marginTop: 2 }}>{a.body}</div>
                  <div style={{ fontSize: 11, color: T.textMuted, marginTop: 4 }}>{a.created_at ? new Date(a.created_at).toLocaleString() : ''} · Reached {a.reach} students</div>
                </div>
                <AdminBadge text="Sent" color="green" />
              </div>
            ))}
          </div>
        </AdminCard>
      </div>
    )
}
