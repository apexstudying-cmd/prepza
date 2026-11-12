import * as React from 'react'
import { N, useTheme } from '../theme/theme'

export type AdminLibraryQueueItem = {
  id: number
  document_id: number
  title: string
  description: string | null
  material_type: string
  unit_id: number | null
  unit_code: string | null
  author_email: string | null
  original_filename: string | null
  created_at: string | null
}

export type AdminLibraryReportItem = {
  id: number
  library_publication_id: number
  publication_title: string | null
  publication_status: string | null
  reporter_email: string | null
  reason: string
  details: string | null
  status: string
  admin_notes: string | null
  created_at: string | null
}

export type AdminInfrastructure = {
  generated_at: string
  active_users: { today: number; last_7d: number; last_30d: number }
  study: { students_today: number; study_seconds_today: number; study_minutes_today: number }
  database: { used_bytes: number; limit_bytes: number; percent: number; status: string }
  storage: { used_bytes: number; limit_bytes: number; percent: number; status: string }
  supabase_limits: { egress_gb: number; realtime_messages: number; realtime_peak_connections: number }
  ai: { requests_mtd: number; input_tokens_mtd: number; output_tokens_mtd: number; spend_mtd_usd: number; projected_month_end_usd: number; budget_usd: number | null; budget_percent: number | null; status: string; by_feature: { feature: string; requests: number; cost_usd: number }[] }
  payments: { revenue_mtd_kes: number; estimated_paystack_fees_mtd_kes: number; estimated_net_after_paystack_kes: number; note: string }
  ses: { configured: boolean; region: string | null; status: string; max_24_hour_send: number | null; max_send_rate: number | null; sent_last_24_hours: number | null; sending_enabled: boolean | null; enforcement_status: string | null; application_sends_last_24_hours: number; verification_sends_last_24_hours: number; password_reset_sends_last_24_hours: number; error?: string }
  known_limits: { render_hobby_build_minutes: number; render_hobby_bandwidth_gb: number; render_runtime_metrics: string; ses_free_tier: string; ses_sandbox_daily_send: number; ses_sandbox_send_rate: number; supabase_free_egress_gb: number; supabase_free_cached_egress_gb: number; supabase_free_realtime_messages: number; supabase_free_realtime_peak_connections: number }
  upgrade_policy: { automatic_billing: boolean; message: string }
}

export type AdminStorageCapacity = {
  supabase: { configured:boolean; object_bytes:number|null; object_bytes_error?:string }
  r2: { enabled:boolean; objects:number; bytes:number; by_bucket:Record<string,number>; error?:string }
}

export type AdminSystemCapacity = {
  tier: string
  available_tiers: string[]
  db_size_bytes: number
  db_size_limit_bytes: number
  storage_used_bytes: number
  storage_limit_bytes: number
  active_connections: number
  connection_limit: number
  ai_spend_mtd_usd: number
  ai_spend_projected_month_end_usd: number
  days_elapsed_this_month: number
  days_in_month: number
}

export type AdminUniversityEngagement = {
  university_id: number
  university_name: string
  students: number
  documents: number
  ai_requests: number
  premium_users: number
  engagement: string
}

export type AdminAnalytics = {
  total_revenue: number
  revenue_last_30d: number
  total_users: number
  active_today: number
  storage_used_bytes: number
  total_units: number
  total_content_items: number
  content_by_type: Record<string, number>
  payments_by_status: Record<string, number>
  signups_per_day: { date: string; count: number }[]
  revenue_per_day: { date: string; amount: number }[]
}

export type AdminContentReport = {
  id: number
  target_type: string
  target_id: number
  reporter_email: string
  reason: string
  details: string | null
  priority: string
  status: string
  action_taken: string | null
  admin_notes: string | null
  created_at: string | null
  author_id: number | null
  author_email: string | null
  snippet: string | null
}

export type AdminModerationSummary = {
  open_reports: number
  resolved_today: number
  suspended_users: number
  warnings_issued: number
}

export type AdminPlatformSettings = {
  maintenance_mode: boolean
  maintenance_message: string
  prepza_control_enabled: boolean
  price_notes: number
  price_past_paper: number
  price_qna: number
  price_promotion_standard: number
  price_promotion_featured: number
  price_promotion_sponsored: number
  ai_daily_limit_free: number | null
  ai_daily_limit_plus: number | null
  ai_daily_limit_premium: number | null
  ai_daily_tutor_limit_free: number | null
  ai_daily_tutor_limit_plus: number | null
  ai_daily_tutor_limit_premium: number | null
  ai_monthly_budget_usd: number
}

export type AdminAuditLogEntry = {
  id: number
  actor_id: number | null
  actor_email: string | null
  action: string
  target_type: string | null
  target_id: number | null
  details: unknown
  created_at: string | null
}

export type AdminContentMaterial = {
  id: number
  document_content_id: number
  material_type: string
  status: string
  file_type: string | null
  is_flagged: boolean
  flagged_reason: string | null
  flagged_by_email: string | null
  flagged_at: string | null
  created_at: string | null
}

export type AdminAiUsage = {
  period_days: number
  total_requests: number
  requests_today: number
  total_cost_usd: number
  total_tokens: number
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_creation_tokens: number
  by_feature: { request_type: string; requests: number; cost_usd: number }[]
  daily_trend: { date: string; requests: number; cost_usd: number }[]
  document_pipeline_jobs: { completed: number; failed: number; note: string }
}

export type AdminAiJob = {
  id: number
  document_content_id: number
  feature: string
  status: string
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  retry_count: number
  created_at: string | null
}

export type AdminPayment = {
  id: number
  user_id: number | null
  user_email: string | null
  user_display_name: string | null
  payment_type: string
  content_title: string | null
  plan: string | null
  phone_number: string | null
  amount: number
  status: string
  provider: string
  reference: string | null
  subscription_expires_at: string | null
  created_at: string | null
}

export type AdminUserRow = {
  id: number
  email: string
  display_name: string | null
  year: number | null
  semester: number | null
  is_admin: boolean
  is_suspended: boolean
  created_at: string | null
  university_name: string | null
  program_name: string | null
  documents_count: number
  ai_requests_count: number
  subscription_plan: string
  subscription_active: boolean
}

export function AdminBadge({ text, color }: { text: string; color: string }) {
  const bg = color === 'green' ? '#DCFCE7' : color === 'amber' ? '#FEF3C7' : color === 'red' ? '#FEE2E2' : color === 'blue' ? '#DBEAFE' : '#F3F4F6'
  const fg = color === 'green' ? '#16A34A' : color === 'amber' ? '#D97706' : color === 'red' ? '#DC2626' : color === 'blue' ? '#2563EB' : '#6B7280'
  return <span style={{ background: bg, color: fg, fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 99, fontFamily: 'Plus Jakarta Sans', whiteSpace: 'nowrap' }}>{text}</span>
}

export function AdminBarChart({ data, labels, height = 80, color = N.gold }: { data: number[]; labels?: string[]; height?: number; color?: string }) {
  const { tokens: T } = useTheme()
  const max = Math.max(...data) || 1
  const w = data.length * 28
  return (
    <svg width="100%" height={height + (labels ? 18 : 0)} viewBox={`0 0 ${w} ${height + (labels ? 18 : 0)}`} preserveAspectRatio="none">
      {data.map((v, i) => {
        const bh = Math.max(2, (v / max) * (height - 4))
        return (
          <g key={i}>
            <rect x={i * 28 + 2} y={height - bh} width={24} height={bh} rx={4} fill={color} opacity={0.75 + (i === data.length - 1 ? 0.25 : 0)} />
            {labels && <text x={i * 28 + 14} y={height + 14} textAnchor="middle" fontSize="9" fill={T.textMuted} fontFamily="Plus Jakarta Sans">{labels[i]}</text>}
          </g>
        )
      })}
    </svg>
  )
}

export function AdminLineChart({ data, color = N.gold, height = 60 }: { data: number[]; color?: string; height?: number }) {
  const { tokens: T } = useTheme()
  const max = Math.max(...data) || 1
  const min = Math.min(...data)
  const range = max - min || 1
  const W = 300
  const pts = data.map((v, i) => [
    (i / (data.length - 1)) * W,
    height - 8 - ((v - min) / range) * (height - 16)
  ])
  const linePath = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')
  const areaPath = `${linePath} L${W},${height} L0,${height} Z`
  const gid = `ag${color.replace('#','')}`
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.18} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gid})`} />
      <path d={linePath} stroke={color} strokeWidth={2.5} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      {pts.map((p, i) => i === pts.length - 1 && <circle key={i} cx={p[0]} cy={p[1]} r={4} fill={color} stroke={T.card} strokeWidth={1.5} />)}
    </svg>
  )
}

export function AdminKPI({ label, value, sub, trend, color = N.navy, chartData }: { label: string; value: string; sub?: string; trend?: string; color?: string; chartData?: number[] }) {
  const { tokens: T } = useTheme()
  const isUp = trend?.startsWith('+')
  return (
    <div style={{ background: T.card, borderRadius: 14, padding: '16px 18px', boxShadow: '0 1px 4px rgba(0,0,0,0.06)', border: `1px solid ${T.border}`, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: T.textMuted, letterSpacing: 0.3 }}>{label}</div>
      <div style={{ fontWeight: 800, fontSize: 24, color, letterSpacing: '-0.5px', lineHeight: 1 }}>{value}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: 11, color: T.textMuted }}>{sub}</div>
        {trend && <span style={{ fontSize: 11, fontWeight: 700, color: isUp ? '#16A34A' : '#DC2626' }}>{trend}</span>}
      </div>
      {chartData && <div style={{ marginTop: 4 }}><AdminLineChart data={chartData} color={color === N.navy ? N.gold : color} height={40} /></div>}
    </div>
  )
}

export function AdminTable({ cols, rows, actions }: { cols: string[]; rows: (string | React.ReactNode)[][]; actions?: (i: number) => React.ReactNode }) {
  const { mode, tokens: T } = useTheme()
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, fontFamily: 'Plus Jakarta Sans' }}>
        <thead>
          <tr style={{ background: mode === 'dark' ? 'rgba(255,255,255,0.04)' : '#F9FAFB', borderBottom: `1px solid ${T.border}` }}>
            {cols.map(c => <th key={c} style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 700, color: T.textMuted, fontSize: 11, whiteSpace: 'nowrap' }}>{c}</th>)}
            {actions && <th style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 700, color: T.textMuted, fontSize: 11 }}>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ borderBottom: `1px solid ${T.border}`, transition: 'background 0.1s' }}>
              {row.map((cell, j) => <td key={j} style={{ padding: '12px 14px', color: j === 0 ? T.text : T.textMuted, fontWeight: j === 0 ? 600 : 400, verticalAlign: 'middle', whiteSpace: 'nowrap' }}>{cell}</td>)}
              {actions && <td style={{ padding: '12px 14px', textAlign: 'right' }}>{actions(i)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function AdminCard({ title, children, action, actionLabel }: { title: string; children: React.ReactNode; action?: () => void; actionLabel?: string }) {
  const { tokens: T } = useTheme()
  return (
    <div style={{ background: T.card, borderRadius: 14, boxShadow: '0 1px 4px rgba(0,0,0,0.06)', border: `1px solid ${T.border}`, overflow: 'hidden' }}>
      <div style={{ padding: '14px 18px', borderBottom: `1px solid ${T.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontWeight: 700, fontSize: 14, color: T.text }}>{title}</div>
        {action && <button onClick={action} style={{ fontSize: 12, fontWeight: 600, color: N.gold, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{actionLabel ?? 'View all'}</button>}
      </div>
      {children}
    </div>
  )
}

export type AdminAnnouncementItem = { id: number; title: string; body: string; reach: number; created_at: string | null }
