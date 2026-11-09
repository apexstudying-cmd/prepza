import * as React from 'react'
import { useEffect, useState, useRef, type ChangeEvent } from 'react'

import { api, ApiError } from '../lib/appApi'
import { N, useTheme, currentThemeMode, DARK_THEME } from '../theme/theme'
import { Ic } from '../ui/icons'
import Pill from '../ui/Pill'
import { LIBRARY_MATERIAL_TYPES, materialTypeLabel } from '../lib/library'
import B2BFinanceAdmin from './B2BFinanceAdmin'
import AdminOperationsDashboard from './AdminOperationsDashboard'

export const PAYMENT_STATUS_META: Record<string, { icon: string; color: string; label: string }> = {
  success: { icon: '✅', color: '#4CC97B', label: 'Success' },
  pending: { icon: '⏳', color: '#D97706', label: 'Pending' },
  failed: { icon: '❌', color: '#C94C4C', label: 'Failed' },
  refunded: { icon: '↩️', color: '#6B7280', label: 'Refunded' },
}

const adminNavGroups = [
  { key:'dashboard', label:'Dashboard', icon:'dashboard', items:[{key:'dashboard',label:'Overview'}] },
  { key:'users', label:'Users', icon:'users', items:[{key:'users',label:'Students'},{key:'groups',label:'Groups'},{key:'moderation',label:'Moderation'}] },
  { key:'payments', label:'Payments', icon:'payments', items:[{key:'payments',label:'Student payments'},{key:'b2b-finance',label:'B2B finance'},{key:'ambassadors',label:'Ambassadors'}] },
  { key:'organisations', label:'Organizations', icon:'org', items:[{key:'organisations',label:'Organizations'},{key:'opportunities',label:'Opportunities'},{key:'promotions',label:'Promotions'}] },
  { key:'content', label:'Content', icon:'content', items:[{key:'content',label:'Library & review'},{key:'universities',label:'Universities'}] },
  { key:'communications', label:'Communications', icon:'communications', items:[{key:'communications',label:'Announcements'}] },
  { key:'system', label:'System', icon:'system', items:[{key:'operations',label:'Operations'},{key:'system',label:'Infrastructure'},{key:'ai-usage',label:'AI & usage'},{key:'analytics',label:'Analytics'},{key:'settings',label:'Settings'}] },
] as const

function AdminNavIcon({name}:{name:string}) {
  const common={viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:1.8,strokeLinecap:'round' as const,strokeLinejoin:'round' as const,"aria-hidden":true}
  if(name==='dashboard') return <svg width="18" height="18" {...common}><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
  if(name==='users') return <svg width="18" height="18" {...common}><circle cx="9" cy="8" r="3"/><path d="M3 20c0-3 2.7-5 6-5s6 2 6 5"/><path d="M16 6.5a2.5 2.5 0 0 1 0 4.8M18 15c1.9.7 3 2.1 3 4"/></svg>
  if(name==='payments') return <svg width="18" height="18" {...common}><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 9h18M7 14h4"/></svg>
  if(name==='org') return <svg width="18" height="18" {...common}><path d="M4 21V5l8-3 8 3v16M8 9h2M14 9h2M8 13h2M14 13h2M8 17h2M14 17h2"/></svg>
  if(name==='content') return <svg width="18" height="18" {...common}><path d="M5 3h10l4 4v14H5z"/><path d="M15 3v5h5M8 12h8M8 16h6"/></svg>
  if(name==='communications') return <svg width="18" height="18" {...common}><path d="M4 5h16v11H8l-4 4z"/><path d="M8 9h8M8 12h5"/></svg>
  return <svg width="18" height="18" {...common}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-1.8 1.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6V20h-2.6v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1-1.8-1.8.1-.1A1.7 1.7 0 0 0 8 15a1.7 1.7 0 0 0-1.6-1H6v-2.6h.4A1.7 1.7 0 0 0 8 10a1.7 1.7 0 0 0-.3-1.9l-.1-.1 1.8-1.8.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6V5H15v.1a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1 1.8 1.8-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.1v2.6H21a1.7 1.7 0 0 0-1.6 1z"/></svg>
}

type AdminLibraryQueueItem = {
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

type AdminLibraryReportItem = {
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

type AdminInfrastructure = {
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

type AdminStorageCapacity = {
  supabase: { configured:boolean; object_bytes:number|null; object_bytes_error?:string }
  r2: { enabled:boolean; objects:number; bytes:number; by_bucket:Record<string,number>; error?:string }
}

type AdminSystemCapacity = {
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

type AdminUniversityEngagement = {
  university_id: number
  university_name: string
  students: number
  documents: number
  ai_requests: number
  premium_users: number
  engagement: string
}

type AdminAnalytics = {
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

type AdminContentReport = {
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

type AdminModerationSummary = {
  open_reports: number
  resolved_today: number
  suspended_users: number
  warnings_issued: number
}

type AdminPlatformSettings = {
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

type AdminAuditLogEntry = {
  id: number
  actor_id: number | null
  actor_email: string | null
  action: string
  target_type: string | null
  target_id: number | null
  details: unknown
  created_at: string | null
}

type AdminContentMaterial = {
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

type AdminAiUsage = {
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

type AdminAiJob = {
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

type AdminPayment = {
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

type AdminUserRow = {
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

function AdminBadge({ text, color }: { text: string; color: string }) {
  const bg = color === 'green' ? '#DCFCE7' : color === 'amber' ? '#FEF3C7' : color === 'red' ? '#FEE2E2' : color === 'blue' ? '#DBEAFE' : '#F3F4F6'
  const fg = color === 'green' ? '#16A34A' : color === 'amber' ? '#D97706' : color === 'red' ? '#DC2626' : color === 'blue' ? '#2563EB' : '#6B7280'
  return <span style={{ background: bg, color: fg, fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 99, fontFamily: 'Plus Jakarta Sans', whiteSpace: 'nowrap' }}>{text}</span>
}

function AdminBarChart({ data, labels, height = 80, color = N.gold }: { data: number[]; labels?: string[]; height?: number; color?: string }) {
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

function AdminLineChart({ data, color = N.gold, height = 60 }: { data: number[]; color?: string; height?: number }) {
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

function AdminKPI({ label, value, sub, trend, color = N.navy, chartData }: { label: string; value: string; sub?: string; trend?: string; color?: string; chartData?: number[] }) {
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

function AdminTable({ cols, rows, actions }: { cols: string[]; rows: (string | React.ReactNode)[][]; actions?: (i: number) => React.ReactNode }) {
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

function AdminCard({ title, children, action, actionLabel }: { title: string; children: React.ReactNode; action?: () => void; actionLabel?: string }) {
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

type AdminAnnouncementItem = { id: number; title: string; body: string; reach: number; created_at: string | null }

function AdminSection({ section, setSection }: { section: string; setSection: (s: string) => void }) {
  const { mode, tokens: T } = useTheme()
  const [search, setSearch] = useState('')
  const [userFilter, setUserFilter] = useState('All')
  const [selectedUser, setSelectedUser] = useState<AdminUserRow | null>(null)
  const [confirmAction, setConfirmAction] = useState<{ type: string; target: string; userId?: number; nextSuspended?: boolean } | null>(null)
  const [contentTab, setContentTab] = useState('Pending Review')
  const [commTab, setCommTab] = useState('Announcements')
  const [adminExpanded, setAdminExpanded] = useState<Record<string, boolean>>({ dashboard:true, users:true, payments:false, organisations:false, content:false, communications:false, system:false })
  const [csrfToken, setCsrfToken] = useState('')
  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  const [annTitle, setAnnTitle] = useState('')
  const [annBody, setAnnBody] = useState('')
  const [annUniversityId, setAnnUniversityId] = useState<number | null>(null)
  const [annProgramId, setAnnProgramId] = useState<number | null>(null)
  const [annYear, setAnnYear] = useState<number | null>(null)
  const [annSemester, setAnnSemester] = useState<number | null>(null)
  const [annGroupId, setAnnGroupId] = useState<number | null>(null)
  const [annGroupName, setAnnGroupName] = useState('')
  const [annGroupSearch, setAnnGroupSearch] = useState('')
  const [annGroupResults, setAnnGroupResults] = useState<{ id: number; name: string }[]>([])
  const [annUniversities, setAnnUniversities] = useState<{ id: number; name: string }[]>([])
  const [annPrograms, setAnnPrograms] = useState<{ id: number; name: string }[]>([])
  const [annSending, setAnnSending] = useState(false)
  const [annError, setAnnError] = useState('')
  const [annSent, setAnnSent] = useState(false)

  const [announcements, setAnnouncements] = useState<AdminAnnouncementItem[]>([])
  const [announcementsLoading, setAnnouncementsLoading] = useState(true)

  const loadAnnouncements = () => {
    setAnnouncementsLoading(true)
    api<AdminAnnouncementItem[]>('/admin/announcements')
      .then(setAnnouncements)
      .catch(() => {})
      .finally(() => setAnnouncementsLoading(false))
  }

  useEffect(() => {
    if (section !== 'communications') return
    loadAnnouncements()
    api<{ id: number; name: string }[]>('/universities').then(setAnnUniversities).catch(() => {})
  }, [section])

  useEffect(() => {
    if (annUniversityId == null) { setAnnPrograms([]); setAnnProgramId(null); return }
    api<{ id: number; name: string }[]>(`/universities/${annUniversityId}/programs`).then(setAnnPrograms).catch(() => {})
  }, [annUniversityId])

  useEffect(() => {
    if (section !== 'communications') return
    const q = annGroupSearch.trim()
    if (!q) { setAnnGroupResults([]); return }
    const t = setTimeout(() => {
      api<{ page: number; groups: { id: number; name: string }[] }>(`/groups?q=${encodeURIComponent(q)}`)
        .then(res => setAnnGroupResults(res.groups))
        .catch(() => {})
    }, 300)
    return () => clearTimeout(t)
  }, [annGroupSearch, section])

  const sendAnnouncement = async () => {
    if (!annTitle.trim() || !annBody.trim() || annSending) return
    setAnnSending(true); setAnnError(''); setAnnSent(false)
    try {
      const payload: Record<string, number | string> = { title: annTitle.trim(), body: annBody.trim() }
      if (annUniversityId != null) payload.university_id = annUniversityId
      if (annProgramId != null) payload.program_id = annProgramId
      if (annYear != null) payload.year = annYear
      if (annSemester != null) payload.semester = annSemester
      if (annGroupId != null) payload.group_id = annGroupId
      await api('/admin/announcements', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify(payload),
      })
      setAnnTitle(''); setAnnBody('')
      setAnnUniversityId(null); setAnnProgramId(null); setAnnYear(null); setAnnSemester(null)
      setAnnGroupId(null); setAnnGroupName(''); setAnnGroupSearch(''); setAnnGroupResults([])
      setAnnSent(true)
      loadAnnouncements()
    } catch (e) {
      setAnnError(e instanceof ApiError ? e.message : 'Could not send announcement.')
    } finally {
      setAnnSending(false)
    }
  }

  const [adminUsers, setAdminUsers] = useState<AdminUserRow[]>([])
  const [adminUsersLoading, setAdminUsersLoading] = useState(true)
  const [adminUsersError, setAdminUsersError] = useState('')
  const [userActionError, setUserActionError] = useState('')

  const loadAdminUsers = () => {
    setAdminUsersLoading(true)
    setAdminUsersError('')
    const params = new URLSearchParams()
    if (search.trim()) params.set('search', search.trim())
    if (userFilter === 'Active') params.set('status', 'active')
    if (userFilter === 'Suspended') params.set('status', 'suspended')
    if (userFilter === 'Premium') params.set('sub', 'premium')
    if (userFilter === 'Free') params.set('sub', 'free')
    api<AdminUserRow[]>(`/admin/users?${params.toString()}`)
      .then(setAdminUsers)
      .catch(e => setAdminUsersError(e instanceof ApiError ? e.message : 'Could not load users.'))
      .finally(() => setAdminUsersLoading(false))
  }

  useEffect(() => {
    if (section !== 'users') return
    const t = setTimeout(() => { loadAdminUsers() }, search.trim() ? 350 : 0)
    return () => clearTimeout(t)
  }, [section, search, userFilter])

  const setUserSuspended = (userId: number, suspended: boolean) => {
    setUserActionError('')
    api(`/admin/users/${userId}`, {
      method: 'PATCH',
      headers: { 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({ is_suspended: suspended }),
    })
      .then(() => { loadAdminUsers(); setSelectedUser(null); setConfirmAction(null) })
      .catch(e => setUserActionError(e instanceof ApiError ? e.message : 'Could not update user.'))
  }

  const [libraryQueue, setLibraryQueue] = useState<AdminLibraryQueueItem[]>([])
  const [libraryQueueLoading, setLibraryQueueLoading] = useState(true)
  const [libraryQueueError, setLibraryQueueError] = useState('')
  const [libraryReports, setLibraryReports] = useState<AdminLibraryReportItem[]>([])
  const [libraryReportsLoading, setLibraryReportsLoading] = useState(true)
  const [libraryReportsError, setLibraryReportsError] = useState('')
  const [contentActionError, setContentActionError] = useState('')
  const [rejectPromptId, setRejectPromptId] = useState<number | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [removePromptTarget, setRemovePromptTarget] = useState<{ publicationId: number; reportId: number } | null>(null)
  const [removeReason, setRemoveReason] = useState('')

  const loadLibraryQueue = () => {
    setLibraryQueueLoading(true)
    setLibraryQueueError('')
    api<{ queue: AdminLibraryQueueItem[] }>('/admin/library/queue')
      .then(res => setLibraryQueue(res.queue))
      .catch(e => setLibraryQueueError(e instanceof ApiError ? e.message : 'Could not load the review queue.'))
      .finally(() => setLibraryQueueLoading(false))
  }

  const loadLibraryReports = () => {
    setLibraryReportsLoading(true)
    setLibraryReportsError('')
    api<{ reports: AdminLibraryReportItem[] }>('/admin/library/reports')
      .then(res => setLibraryReports(res.reports))
      .catch(e => setLibraryReportsError(e instanceof ApiError ? e.message : 'Could not load reports.'))
      .finally(() => setLibraryReportsLoading(false))
  }

  useEffect(() => {
    if (section !== 'content') return
    loadLibraryQueue()
    loadLibraryReports()
  }, [section])

  const approveLibraryItem = (publicationId: number) => {
    setContentActionError('')
    api(`/admin/library/${publicationId}/approve`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      .then(() => loadLibraryQueue())
      .catch(e => setContentActionError(e instanceof ApiError ? e.message : 'Could not approve this item.'))
  }

  const rejectLibraryItem = (publicationId: number, reason: string) => {
    setContentActionError('')
    api(`/admin/library/${publicationId}/reject`, {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({ reason }),
    })
      .then(() => { loadLibraryQueue(); setRejectPromptId(null); setRejectReason('') })
      .catch(e => setContentActionError(e instanceof ApiError ? e.message : 'Could not reject this item.'))
  }

  const removeLibraryItem = (publicationId: number, reportId: number, reason: string) => {
    setContentActionError('')
    api(`/admin/library/${publicationId}/remove`, {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({ reason }),
    })
      .then(() => api(`/admin/library/reports/${reportId}/resolve`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ status: 'actioned' }),
      }))
      .then(() => { loadLibraryReports(); setRemovePromptTarget(null); setRemoveReason('') })
      .catch(e => setContentActionError(e instanceof ApiError ? e.message : 'Could not remove this item.'))
  }

  const resolveLibraryReport = (reportId: number, status: 'dismissed' | 'actioned') => {
    setContentActionError('')
    api(`/admin/library/reports/${reportId}/resolve`, {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({ status }),
    })
      .then(() => loadLibraryReports())
      .catch(e => setContentActionError(e instanceof ApiError ? e.message : 'Could not resolve this report.'))
  }

  const [adminPayments, setAdminPayments] = useState<AdminPayment[]>([])
  const [adminPaymentsLoading, setAdminPaymentsLoading] = useState(true)
  const [adminPaymentsError, setAdminPaymentsError] = useState('')
  const [paymentActionError, setPaymentActionError] = useState('')

  const loadAdminPayments = () => {
    setAdminPaymentsLoading(true)
    setAdminPaymentsError('')
    api<{ payments: AdminPayment[] }>('/admin/payments')
      .then(res => setAdminPayments(res.payments))
      .catch(e => setAdminPaymentsError(e instanceof ApiError ? e.message : 'Could not load payments.'))
      .finally(() => setAdminPaymentsLoading(false))
  }

  useEffect(() => {
    if (section !== 'payments') return
    loadAdminPayments()
  }, [section])

  const refundPayment = (paymentId: number) => {
    setPaymentActionError('')
    api(`/admin/payments/${paymentId}/refund`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      .then(() => loadAdminPayments())
      .catch(e => setPaymentActionError(e instanceof ApiError ? e.message : 'Could not refund this payment.'))
  }

  const [aiUsage, setAiUsage] = useState<AdminAiUsage | null>(null)
  const [aiUsageLoading, setAiUsageLoading] = useState(true)
  const [aiUsageError, setAiUsageError] = useState('')
  const [aiUsageDays, setAiUsageDays] = useState(30)
  const [aiJobs, setAiJobs] = useState<AdminAiJob[]>([])
  const [aiJobsLoading, setAiJobsLoading] = useState(true)
  const [aiJobsError, setAiJobsError] = useState('')
  const [aiJobsFilter, setAiJobsFilter] = useState<'all' | 'failed' | 'completed'>('all')
  const [aiJobActionError, setAiJobActionError] = useState('')

  const loadAiUsage = () => {
    setAiUsageLoading(true)
    setAiUsageError('')
    api<AdminAiUsage>(`/admin/ai-usage?days=${aiUsageDays}`)
      .then(setAiUsage)
      .catch(e => setAiUsageError(e instanceof ApiError ? e.message : 'Could not load AI usage.'))
      .finally(() => setAiUsageLoading(false))
  }

  const loadAiJobs = () => {
    setAiJobsLoading(true)
    setAiJobsError('')
    const params = aiJobsFilter !== 'all' ? `?status=${aiJobsFilter}` : ''
    api<AdminAiJob[]>(`/admin/ai-jobs${params}`)
      .then(setAiJobs)
      .catch(e => setAiJobsError(e instanceof ApiError ? e.message : 'Could not load AI jobs.'))
      .finally(() => setAiJobsLoading(false))
  }

  useEffect(() => {
    if (section !== 'ai-usage') return
    loadAiUsage()
  }, [section, aiUsageDays])

  useEffect(() => {
    if (section !== 'ai-usage') return
    loadAiJobs()
  }, [section, aiJobsFilter])

  const retryAiJob = (jobId: number) => {
    setAiJobActionError('')
    api(`/admin/ai-jobs/${jobId}/retry`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      .then(() => loadAiJobs())
      .catch(e => setAiJobActionError(e instanceof ApiError ? e.message : 'Could not retry this job.'))
  }

  const [modReports, setModReports] = useState<AdminContentReport[]>([])
  const [modReportsLoading, setModReportsLoading] = useState(true)
  const [modReportsError, setModReportsError] = useState('')
  const [modSummary, setModSummary] = useState<AdminModerationSummary | null>(null)
  const [modActionError, setModActionError] = useState('')
  const [warnPromptId, setWarnPromptId] = useState<number | null>(null)
  const [warnMessage, setWarnMessage] = useState('')
  const [warnConsequence, setWarnConsequence] = useState('')
  const [warnRemoveContent, setWarnRemoveContent] = useState(false)

  const loadModReports = () => {
    setModReportsLoading(true)
    setModReportsError('')
    api<{ reports: AdminContentReport[] }>('/admin/content-reports')
      .then(res => setModReports(res.reports))
      .catch(e => setModReportsError(e instanceof ApiError ? e.message : 'Could not load reports.'))
      .finally(() => setModReportsLoading(false))
  }

  const loadModSummary = () => {
    api<AdminModerationSummary>('/admin/content-reports/summary')
      .then(setModSummary)
      .catch(() => {})
  }

  const [flaggedMaterials, setFlaggedMaterials] = useState<AdminContentMaterial[]>([])
  const [flaggedMaterialsLoading, setFlaggedMaterialsLoading] = useState(true)
  const [flaggedMaterialsError, setFlaggedMaterialsError] = useState('')
  const [materialActionError, setMaterialActionError] = useState('')
  const [flagMaterialId, setFlagMaterialId] = useState('')
  const [flagMaterialReason, setFlagMaterialReason] = useState('')
  const [flagMaterialBusy, setFlagMaterialBusy] = useState(false)

  const loadFlaggedMaterials = () => {
    setFlaggedMaterialsLoading(true)
    setFlaggedMaterialsError('')
    api<{ materials: AdminContentMaterial[] }>('/admin/content-materials?status=flagged')
      .then(res => setFlaggedMaterials(res.materials))
      .catch(e => setFlaggedMaterialsError(e instanceof ApiError ? e.message : 'Could not load flagged content.'))
      .finally(() => setFlaggedMaterialsLoading(false))
  }

  const unflagMaterial = (materialId: number) => {
    setMaterialActionError('')
    api(`/admin/content-materials/${materialId}/unflag`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      .then(() => loadFlaggedMaterials())
      .catch(e => setMaterialActionError(e instanceof ApiError ? e.message : 'Could not unflag this material.'))
  }

  const submitFlagMaterial = async () => {
    const id = parseInt(flagMaterialId, 10)
    if (!id || !flagMaterialReason.trim() || flagMaterialBusy) return
    setFlagMaterialBusy(true)
    setMaterialActionError('')
    try {
      await api(`/admin/content-materials/${id}/flag`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ reason: flagMaterialReason.trim() }),
      })
      setFlagMaterialId('')
      setFlagMaterialReason('')
      loadFlaggedMaterials()
    } catch (e) {
      setMaterialActionError(e instanceof ApiError ? e.message : 'Could not flag this material.')
    } finally {
      setFlagMaterialBusy(false)
    }
  }

  useEffect(() => {
    if (section !== 'moderation') return
    loadModReports()
    loadModSummary()
    loadFlaggedMaterials()
  }, [section])

  const dismissModReport = (reportId: number) => {
    setModActionError('')
    api(`/admin/content-reports/${reportId}/dismiss`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      .then(() => { loadModReports(); loadModSummary() })
      .catch(e => setModActionError(e instanceof ApiError ? e.message : 'Could not dismiss this report.'))
  }

  const removeModReportContent = (reportId: number) => {
    setModActionError('')
    api(`/admin/content-reports/${reportId}/remove`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      .then(() => { loadModReports(); loadModSummary() })
      .catch(e => setModActionError(e instanceof ApiError ? e.message : 'Could not remove this content.'))
  }

  const warnFromModReport = (reportId: number, message: string, consequence: string, removeContent: boolean) => {
    setModActionError('')
    api(`/admin/content-reports/${reportId}/warn`, {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({ message, consequence, remove_content: removeContent }),
    })
      .then(() => { loadModReports(); loadModSummary(); setWarnPromptId(null); setWarnMessage(''); setWarnConsequence(''); setWarnRemoveContent(false) })
      .catch(e => setModActionError(e instanceof ApiError ? e.message : 'Could not issue this warning.'))
  }

  const [analytics, setAnalytics] = useState<AdminAnalytics | null>(null)
  const [analyticsLoading, setAnalyticsLoading] = useState(true)
  const [analyticsError, setAnalyticsError] = useState('')

  useEffect(() => {
    if (section !== 'analytics') return
    setAnalyticsLoading(true)
    setAnalyticsError('')
    api<AdminAnalytics>('/admin/analytics')
      .then(setAnalytics)
      .catch(e => setAnalyticsError(e instanceof ApiError ? e.message : 'Could not load analytics.'))
      .finally(() => setAnalyticsLoading(false))
  }, [section])

  const [universityEngagement, setUniversityEngagement] = useState<AdminUniversityEngagement[]>([])
  const [universityEngagementLoading, setUniversityEngagementLoading] = useState(true)
  const [universityEngagementError, setUniversityEngagementError] = useState('')

  useEffect(() => {
    if (section !== 'analytics') return
    setUniversityEngagementLoading(true)
    setUniversityEngagementError('')
    api<{ universities: AdminUniversityEngagement[] }>('/admin/analytics/universities')
      .then(res => setUniversityEngagement(res.universities))
      .catch(e => setUniversityEngagementError(e instanceof ApiError ? e.message : 'Could not load university engagement.'))
      .finally(() => setUniversityEngagementLoading(false))
  }, [section])

  const filteredUsers = adminUsers

  const [dashAnalytics, setDashAnalytics] = useState<AdminAnalytics | null>(null)
  const [dashAnalyticsLoading, setDashAnalyticsLoading] = useState(true)
  const [dashAiUsage, setDashAiUsage] = useState<AdminAiUsage | null>(null)
  const [dashPayments, setDashPayments] = useState<AdminPayment[]>([])
  const [dashPaymentsLoading, setDashPaymentsLoading] = useState(true)
  const [dashModSummary, setDashModSummary] = useState<AdminModerationSummary | null>(null)
  const [dashLibraryQueueCount, setDashLibraryQueueCount] = useState<number | null>(null)
  const [dashRecentUsers, setDashRecentUsers] = useState<AdminUserRow[]>([])
  const [dashError, setDashError] = useState('')

  useEffect(() => {
    if (section !== 'dashboard') return
    setDashAnalyticsLoading(true)
    setDashPaymentsLoading(true)
    setDashError('')
    api<AdminAnalytics>('/admin/analytics').then(setDashAnalytics).catch(() => setDashError('Some dashboard data could not be loaded.')).finally(() => setDashAnalyticsLoading(false))
    api<AdminAiUsage>('/admin/ai-usage?days=30').then(setDashAiUsage).catch(() => {})
    api<{ payments: AdminPayment[] }>('/admin/payments').then(res => setDashPayments(res.payments)).catch(() => setDashError('Some dashboard data could not be loaded.')).finally(() => setDashPaymentsLoading(false))
    api<AdminModerationSummary>('/admin/content-reports/summary').then(setDashModSummary).catch(() => {})
    api<{ queue: AdminLibraryQueueItem[] }>('/admin/library/queue').then(res => setDashLibraryQueueCount(res.queue.length)).catch(() => {})
    api<AdminUserRow[]>('/admin/users').then(res => setDashRecentUsers(res.slice(0, 5))).catch(() => {})
  }, [section])

  const [infrastructure, setInfrastructure] = useState<AdminInfrastructure | null>(null)
  const [infrastructureLoading, setInfrastructureLoading] = useState(true)
  const [infrastructureError, setInfrastructureError] = useState('')
  const [otpAdmin, setOtpAdmin] = useState<{
    settings: Record<string, string>
    ses: { configured: boolean; region: string | null; status: string; max_24_hour_send?: number | null; max_send_rate?: number | null; sent_last_24_hours?: number | null; sending_enabled?: boolean | null; enforcement_status?: string | null; error?: string }
  } | null>(null)
  const [otpAdminLoading, setOtpAdminLoading] = useState(true)
  const [otpAdminSaving, setOtpAdminSaving] = useState(false)
  const [otpAdminError, setOtpAdminError] = useState('')


  const [systemCapacity, setSystemCapacity] = useState<AdminSystemCapacity | null>(null)
  const [storageCapacity, setStorageCapacity] = useState<AdminStorageCapacity | null>(null)
  const [storageCapacityLoading, setStorageCapacityLoading] = useState(true)
  const [storageCapacityError, setStorageCapacityError] = useState('')

  const [systemCapacityLoading, setSystemCapacityLoading] = useState(true)
  const [systemCapacityError, setSystemCapacityError] = useState('')
  const [tierSwitching, setTierSwitching] = useState(false)
  const [tierSwitchError, setTierSwitchError] = useState('')
  const [adminAccounts, setAdminAccounts] = useState<AdminUserRow[]>([])
  const [adminAccountsLoading, setAdminAccountsLoading] = useState(true)
  const [adminAccountsError, setAdminAccountsError] = useState('')
  const [adminAccountActionError, setAdminAccountActionError] = useState('')

  const [auditLogs, setAuditLogs] = useState<AdminAuditLogEntry[]>([])
  const [auditLogsLoading, setAuditLogsLoading] = useState(true)
  const [auditLogsError, setAuditLogsError] = useState('')
  const [auditActionFilter, setAuditActionFilter] = useState('')
  const [auditTargetTypeFilter, setAuditTargetTypeFilter] = useState('')
  const [auditDays, setAuditDays] = useState(30)
  const [auditPage, setAuditPage] = useState(1)

  const loadAuditLogs = (page: number) => {
    setAuditLogsLoading(true)
    setAuditLogsError('')
    const params = new URLSearchParams()
    params.set('days', String(auditDays))
    params.set('page', String(page))
    if (auditActionFilter.trim()) params.set('action', auditActionFilter.trim())
    if (auditTargetTypeFilter.trim()) params.set('target_type', auditTargetTypeFilter.trim())
    api<{ page: number; logs: AdminAuditLogEntry[] }>(`/admin/audit-logs?${params.toString()}`)
      .then(res => { setAuditLogs(res.logs); setAuditPage(res.page) })
      .catch(e => setAuditLogsError(e instanceof ApiError ? e.message : 'Could not load audit logs.'))
      .finally(() => setAuditLogsLoading(false))
  }

  useEffect(() => {
    if (section !== 'system') return
    loadAuditLogs(1)
  }, [section, auditDays, auditActionFilter, auditTargetTypeFilter])

  useEffect(() => {
    if (section !== 'system') return
    setOtpAdminLoading(true)
    setOtpAdminError('')
    api<typeof otpAdmin>('/admin/auth/otp')
      .then(setOtpAdmin)
      .catch(e => setOtpAdminError(e instanceof ApiError ? e.message : 'Could not load email authentication settings.'))
      .finally(() => setOtpAdminLoading(false))
  }, [section])

  const saveOtpAdmin = async (patch: Record<string, unknown>) => {
    if (otpAdminSaving) return
    setOtpAdminSaving(true)
    setOtpAdminError('')
    try {
      const next = await api<typeof otpAdmin>('/admin/auth/otp', {
        method: 'PATCH',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify(patch),
      })
      setOtpAdmin(next)
    } catch (e) {
      setOtpAdminError(e instanceof ApiError ? e.message : 'Could not save email authentication settings.')
    } finally {
      setOtpAdminSaving(false)
    }
  }

  useEffect(() => {
    if (section !== 'system') return
    setInfrastructureLoading(true)
    setInfrastructureError('')
    api<AdminInfrastructure>('/admin/infrastructure')
      .then(setInfrastructure)
      .catch(e => setInfrastructureError(e instanceof ApiError ? e.message : 'Could not load infrastructure telemetry.'))
      .finally(() => setInfrastructureLoading(false))
  }, [section])


  const loadStorageCapacity = () => {
    setStorageCapacityLoading(true); setStorageCapacityError('')
    api<AdminStorageCapacity>('/admin/system/storage')
      .then(setStorageCapacity)
      .catch(e => setStorageCapacityError(e instanceof ApiError ? e.message : 'Could not load storage capacity.'))
      .finally(() => setStorageCapacityLoading(false))
  }

  const loadSystemCapacity = () => {
    setSystemCapacityLoading(true)
    setSystemCapacityError('')
    api<AdminSystemCapacity>('/admin/system/capacity')
      .then(setSystemCapacity)
      .catch(e => setSystemCapacityError(e instanceof ApiError ? e.message : 'Could not load system capacity.'))
      .finally(() => setSystemCapacityLoading(false))
  }

  const switchSupabaseTier = (tier: string) => {
    setTierSwitching(true)
    setTierSwitchError('')
    api('/admin/system/capacity/tier', {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({ tier }),
    })
      .then(() => loadSystemCapacity())
      .catch(e => setTierSwitchError(e instanceof ApiError ? e.message : 'Could not switch tier.'))
      .finally(() => setTierSwitching(false))
  }

  const loadAdminAccounts = () => {
    setAdminAccountsLoading(true)
    setAdminAccountsError('')
    api<AdminUserRow[]>('/admin/users')
      .then(res => setAdminAccounts(res.filter(u => u.is_admin)))
      .catch(e => setAdminAccountsError(e instanceof ApiError ? e.message : 'Could not load admin accounts.'))
      .finally(() => setAdminAccountsLoading(false))
  }

  useEffect(() => {
    if (section !== 'system') return
    loadSystemCapacity()
    loadStorageCapacity()
    loadAdminAccounts()
  }, [section])

  const setAdminAccountRole = (userId: number, isAdmin: boolean) => {
    setAdminAccountActionError('')
    api(`/admin/users/${userId}`, {
      method: 'PATCH',
      headers: { 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({ is_admin: isAdmin }),
    })
      .then(() => loadAdminAccounts())
      .catch(e => setAdminAccountActionError(e instanceof ApiError ? e.message : 'Could not update this admin account.'))
  }

  const [platformSettings, setPlatformSettings] = useState<AdminPlatformSettings | null>(null)
  const [settingsDraft, setSettingsDraft] = useState<AdminPlatformSettings | null>(null)
  const [settingsLoading, setSettingsLoading] = useState(true)
  const [settingsError, setSettingsError] = useState('')
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [settingsSaveError, setSettingsSaveError] = useState('')
  const [settingsSaved, setSettingsSaved] = useState(false)

  const loadPlatformSettings = () => {
    setSettingsLoading(true)
    setSettingsError('')
    api<AdminPlatformSettings>('/admin/settings')
      .then(res => { setPlatformSettings(res); setSettingsDraft(res) })
      .catch(e => setSettingsError(e instanceof ApiError ? e.message : 'Could not load platform settings.'))
      .finally(() => setSettingsLoading(false))
  }

  useEffect(() => {
    if (section !== 'settings') return
    loadPlatformSettings()
  }, [section])

  const setPrepzaControlEnabled = async (enabled: boolean) => {
    if (!settingsDraft || settingsSaving) return
    if (!enabled && !window.confirm('Disable ChatGPT/Prepza control access now? This immediately blocks all control API requests.')) return
    setSettingsSaving(true)
    setSettingsSaveError('')
    try {
      await api('/admin/settings', {
        method: 'PATCH',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ prepza_control_enabled: enabled }),
      })
      await loadPlatformSettings()
      setSettingsSaved(true)
    } catch (e) {
      setSettingsSaveError(e instanceof ApiError ? e.message : 'Could not change control access.')
    } finally {
      setSettingsSaving(false)
    }
  }

  const savePlatformSettings = async () => {
    if (!settingsDraft || !platformSettings) return
    setSettingsSaving(true)
    setSettingsSaveError('')
    setSettingsSaved(false)
    const payload: Record<string, unknown> = {}
    ;(Object.keys(settingsDraft) as (keyof AdminPlatformSettings)[]).forEach(key => {
      if (settingsDraft[key] !== platformSettings[key]) payload[key] = settingsDraft[key]
    })
    if (Object.keys(payload).length === 0) { setSettingsSaving(false); return }
    try {
      await api('/admin/settings', {
        method: 'PATCH',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify(payload),
      })
      loadPlatformSettings()
      setSettingsSaved(true)
    } catch (e) {
      setSettingsSaveError(e instanceof ApiError ? e.message : 'Could not save platform settings.')
    } finally {
      setSettingsSaving(false)
    }
  }

  const ActivityDot = ({ color }: { color: string }) => <div style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0, marginTop: 3 }} />

  if (section === 'dashboard') {
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

  if (section === 'users') return (
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

  if (section === 'content') {
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

  if (section === 'ai-usage') {
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

  if (section === 'b2b-finance') {
    return <B2BFinanceAdmin tokens={T} />
  }

  if (section === 'payments') {
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

  if (section === 'moderation') {
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

  if (section === 'analytics') {
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

  if (section === 'operations') return <AdminOperationsDashboard />

  if (section === 'system') {
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

  if (section === 'settings') {
    const numField = (label: string, key: keyof AdminPlatformSettings, opts?: { allowNull?: boolean; prefix?: string }) => (
      <div key={key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '10px 0', borderBottom: `1px solid ${T.border}` }}>
        <span style={{ fontSize: 13, color: T.text, fontWeight: 600 }}>{label}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {opts?.prefix && <span style={{ fontSize: 12, color: T.textMuted }}>{opts.prefix}</span>}
          <input
            type="text"
            value={settingsDraft ? (settingsDraft[key] == null ? '' : String(settingsDraft[key])) : ''}
            placeholder={opts?.allowNull ? 'Unlimited' : ''}
            onChange={e => {
              if (!settingsDraft) return
              const raw = e.target.value.replace(/[^0-9.]/g, '')
              const num = raw === '' ? (opts?.allowNull ? null : 0) : Number(raw)
              setSettingsDraft({ ...settingsDraft, [key]: num as any })
            }}
            style={{ width: 100, textAlign: 'right', border: `1px solid ${T.border}`, borderRadius: 8, padding: '6px 10px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card }}
          />
        </div>
      </div>
    )
    return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {settingsLoading ? (
        <div style={{ padding: '24px 0', textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading settings…</div>
      ) : settingsError ? (
        <div style={{ padding: '24px 0', textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{settingsError}</div>
      ) : settingsDraft && (
        <>
          <AdminCard title="Maintenance Mode">
            <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                <input type="checkbox" checked={settingsDraft.maintenance_mode} onChange={e => setSettingsDraft({ ...settingsDraft, maintenance_mode: e.target.checked })} />
                <span style={{ fontSize: 13, fontWeight: 600, color: T.text }}>Put the app into maintenance mode</span>
              </label>
              <textarea
                value={settingsDraft.maintenance_message}
                onChange={e => setSettingsDraft({ ...settingsDraft, maintenance_message: e.target.value })}
                placeholder="Message shown to users while in maintenance mode…"
                rows={3}
                maxLength={500}
                style={{ border: `1px solid ${T.border}`, borderRadius: 10, padding: '10px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card, resize: 'vertical' }}
              />
            </div>
          </AdminCard>

          <AdminCard title="Prepza Control Access">
            <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.55 }}>
                Controls the private developer API used by trusted Prepza tooling. It is disabled by default and still requires a separate server-side token.
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: T.text }}>{settingsDraft.prepza_control_enabled ? 'Control access is ON' : 'Control access is OFF'}</div>
                  <div style={{ fontSize: 11, color: T.textMuted, marginTop: 3 }}>
                    {settingsDraft.prepza_control_enabled ? 'The API can be reached only with the server-side bearer token.' : 'All control API requests are rejected immediately.'}
                  </div>
                </div>
                <button
                  onClick={() => setPrepzaControlEnabled(!settingsDraft.prepza_control_enabled)}
                  disabled={settingsSaving}
                  style={{ background: settingsDraft.prepza_control_enabled ? '#DC2626' : '#16A34A', color: '#fff', border: 'none', borderRadius: 10, padding: '9px 16px', cursor: settingsSaving ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 12, opacity: settingsSaving ? 0.6 : 1 }}
                >{settingsSaving ? 'Updating…' : (settingsDraft.prepza_control_enabled ? 'Disable Control Access' : 'Enable Control Access')}</button>
              </div>
              <div style={{ fontSize: 11, color: '#92400E', background: '#FEF3C7', borderRadius: 8, padding: '8px 10px' }}>
                Keep this OFF unless you are actively using the trusted control connection.
              </div>
            </div>
          </AdminCard>

          <AdminCard title="Content Prices (KES)">
            <div style={{ padding: '4px 18px 8px' }}>
              {numField('Notes', 'price_notes', { prefix: 'KES' })}
              {numField('Past Paper', 'price_past_paper', { prefix: 'KES' })}
              {numField('Q&A', 'price_qna', { prefix: 'KES' })}
              {numField('Opportunity — Standard', 'price_promotion_standard', { prefix: 'KES' })}
              {numField('Opportunity — Featured', 'price_promotion_featured', { prefix: 'KES' })}
              {numField('Opportunity — Sponsored', 'price_promotion_sponsored', { prefix: 'KES' })}
            </div>
            <div style={{ padding: '0 18px 14px', fontSize: 11, color: T.textMuted }}>
              Promotion prices are snapshotted when an organisation submits a request. Changing these prices affects new requests, not existing campaigns.
            </div>
          </AdminCard>

          <AdminCard title="AI Daily Limits">
            <div style={{ padding: '4px 18px 8px' }}>
              {numField('Chat — Free tier', 'ai_daily_limit_free', { allowNull: true })}
              {numField('Chat — Plus tier', 'ai_daily_limit_plus', { allowNull: true })}
              {numField('Chat — Premium tier', 'ai_daily_limit_premium', { allowNull: true })}
              {numField('Tutor — Free tier', 'ai_daily_tutor_limit_free', { allowNull: true })}
              {numField('Tutor — Plus tier', 'ai_daily_tutor_limit_plus', { allowNull: true })}
              {numField('Tutor — Premium tier', 'ai_daily_tutor_limit_premium', { allowNull: true })}
            </div>
            <div style={{ padding: '0 18px 14px', fontSize: 11, color: T.textMuted }}>Leave blank for unlimited.</div>
          </AdminCard>

          <AdminCard title="AI Monthly Budget">
            <div style={{ padding: '4px 18px 8px' }}>
              {numField('Budget (USD)', 'ai_monthly_budget_usd', { prefix: '$' })}
            </div>
          </AdminCard>

          {settingsSaveError && <div style={{ color: '#DC2626', fontSize: 12 }}>{settingsSaveError}</div>}
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <button
              disabled={settingsSaving}
              onClick={savePlatformSettings}
              style={{ background: N.navy, color: '#fff', border: 'none', borderRadius: 10, padding: '10px 20px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, opacity: settingsSaving ? 0.6 : 1 }}
            >{settingsSaving ? 'Saving…' : 'Save Settings'}</button>
            {settingsSaved && !settingsSaving && <span style={{ fontSize: 12, color: '#16A34A', fontWeight: 600 }}>Saved.</span>}
          </div>
        </>
      )}
    </div>
    )
  }

  if (section === 'groups') return <AdminGroupsPanel />

  if (section === 'ambassadors') return <AdminAmbassadorsPanel />

  if (section === 'communications') {
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

  if (section === 'opportunities') return <AdminOpportunitiesPanel />

  if (section === 'promotions') return <AdminPromotionsPanel />

  if (section === 'organisations') return <AdminOrganisationsPanel />

  if (section === 'universities') return <AdminUniversitiesPanel />

  if (section === 'community') return <AdminCommunityPanel />

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, color: T.textMuted, fontSize: 14 }}>Select a section from the sidebar</div>
  )
}

// ─── ADMIN: AMBASSADORS (Chunk 9 admin review) ──────────────────────────────
// Self-contained admin panel: fetches from GET/POST /admin/ambassadors* and
// /admin/payouts* (see app.py). Owns all its own hooks so it can be dropped
// into a section branch without touching AdminSection's existing state.

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

function AdminAmbassadorsPanel() {
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

function AdminOpportunitiesPanel() {
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

interface AdminOrganisationRow {
  id: number
  name: string
  contact_email: string
  contact_phone: string | null
  website: string | null
  verification_status: 'pending' | 'verified' | 'rejected'
  verification_notes: string | null
  is_active: boolean
  owner_email: string | null
  created_at: string | null
}

const ADMIN_ORG_STATUS_COLOR: Record<string, string> = {
  pending: 'amber', verified: 'green', rejected: 'red',
}

interface AdminPromotionRow {
  id: number
  opportunity_id: number
  organisation_id: number
  promotion_type: string
  start_date: string | null
  end_date: string | null
  price: number
  payment_status: string
  approval_status: 'pending' | 'approved' | 'rejected'
  reviewed_at: string | null
  created_at: string | null
  opportunity_title?: string | null
  organisation_name?: string | null
}

const ADMIN_PROMO_STATUS_COLOR: Record<string, string> = { pending: 'amber', approved: 'green', rejected: 'red' }

function AdminPromotionsPanel() {
  const { mode, tokens: T } = useTheme()
  const [csrfToken, setCsrfToken] = useState('')
  const [statusFilter, setStatusFilter] = useState('pending')
  const [rows, setRows] = useState<AdminPromotionRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionBusy, setActionBusy] = useState(false)

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
  }, [])

  const load = (status: string) => {
    setLoading(true)
    setError('')
    api<{ promotions: AdminPromotionRow[] }>(`/admin/opportunity-promotions?approval_status=${status}`)
      .then(res => setRows(res.promotions))
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load promotion requests.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load(statusFilter) }, [statusFilter])

  const runAction = async (id: number, action: 'approve' | 'reject') => {
    setActionBusy(true)
    try {
      await api(`/admin/opportunity-promotions/${id}/${action}`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      load(statusFilter)
    } catch (e) {
      alert(e instanceof ApiError ? e.message : `Could not ${action} this promotion.`)
    } finally {
      setActionBusy(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <AdminCard title={`Promotion Requests — ${rows.length}`}>
        <div style={{ padding: '12px 18px', borderBottom: `1px solid ${T.border}`, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {['pending', 'approved', 'rejected', 'all'].map(f => (
            <button key={f} onClick={() => setStatusFilter(f)} style={{ padding: '7px 14px', borderRadius: 8, background: statusFilter === f ? N.navy : (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: statusFilter === f ? '#fff' : T.textMuted, border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans', textTransform: 'capitalize' }}>{f}</button>
          ))}
        </div>
        {loading ? (
          <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading…</div>
        ) : error ? (
          <div style={{ padding: 24, textAlign: 'center', color: '#C94C4C', fontSize: 13 }}>{error}</div>
        ) : rows.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No promotion requests with this status.</div>
        ) : (
          <AdminTable
            cols={['Opportunity', 'Organisation', 'Type', 'Window', 'Price', 'Payment', 'Status']}
            rows={rows.map(r => [
              r.opportunity_title || `#${r.opportunity_id}`,
              r.organisation_name || `#${r.organisation_id}`,
              r.promotion_type.charAt(0).toUpperCase() + r.promotion_type.slice(1),
              `${r.start_date ? new Date(r.start_date).toLocaleDateString() : '—'} – ${r.end_date ? new Date(r.end_date).toLocaleDateString() : '—'}`,
              r.price > 0 ? `KES ${r.price.toLocaleString()}` : 'Free',
              <AdminBadge text={r.price > 0 ? r.payment_status : 'not required'} color={r.price > 0 && r.payment_status !== 'success' ? 'amber' : 'green'} />,
              <AdminBadge text={r.approval_status} color={ADMIN_PROMO_STATUS_COLOR[r.approval_status] || 'gray'} />,
            ])}
            actions={i => rows[i].approval_status === 'pending' ? (
              <div style={{ display: 'flex', gap: 5, justifyContent: 'flex-end' }}>
                <button disabled={actionBusy || (rows[i].price > 0 && rows[i].payment_status !== 'success')} onClick={() => runAction(rows[i].id, 'approve')} title={rows[i].price > 0 && rows[i].payment_status !== 'success' ? 'Payment required before approval' : 'Approve'} style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: (actionBusy || (rows[i].price > 0 && rows[i].payment_status !== 'success')) ? 'not-allowed' : 'pointer', opacity: rows[i].price > 0 && rows[i].payment_status !== 'success' ? 0.45 : 1, fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Approve</button>
                <button disabled={actionBusy} onClick={() => runAction(rows[i].id, 'reject')} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Reject</button>
              </div>
            ) : null}
          />
        )}
      </AdminCard>
    </div>
  )
}

function AdminOrganisationsPanel() {
  const { mode, tokens: T } = useTheme()
  const [csrfToken, setCsrfToken] = useState('')
  const [statusFilter, setStatusFilter] = useState('pending')
  const [rows, setRows] = useState<AdminOrganisationRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionBusy, setActionBusy] = useState(false)
  const [rejectTarget, setRejectTarget] = useState<number | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
  }, [])

  const load = (status: string) => {
    setLoading(true)
    setError('')
    const qs = status === 'all' ? '' : `?verification_status=${status}`
    api<{ organisations: AdminOrganisationRow[] }>(`/admin/organisations${qs}`)
      .then(res => setRows(res.organisations))
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load organisations.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load(statusFilter) }, [statusFilter])

  const verify = async (id: number) => {
    setActionBusy(true)
    try {
      await api(`/admin/organisations/${id}/verify`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      load(statusFilter)
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not verify this organisation.')
    } finally {
      setActionBusy(false)
    }
  }

  const submitReject = async () => {
    if (rejectTarget == null || !rejectReason.trim()) return
    setActionBusy(true)
    try {
      await api(`/admin/organisations/${rejectTarget}/reject`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ reason: rejectReason.trim() }),
      })
      load(statusFilter)
      setRejectTarget(null)
      setRejectReason('')
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not reject this organisation.')
    } finally {
      setActionBusy(false)
    }
  }

  const toggleActive = async (id: number, nextActive: boolean) => {
    setActionBusy(true)
    try {
      await api(`/admin/organisations/${id}`, {
        method: 'PATCH',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ is_active: nextActive }),
      })
      load(statusFilter)
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not update this organisation.')
    } finally {
      setActionBusy(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <AdminCard title={`Organisations — ${rows.length}`}>
        <div style={{ padding: '12px 18px', borderBottom: `1px solid ${T.border}`, display: 'flex', gap: 6 }}>
          {['pending', 'verified', 'rejected', 'all'].map(f => (
            <button key={f} onClick={() => setStatusFilter(f)} style={{ padding: '7px 14px', borderRadius: 8, background: statusFilter === f ? N.navy : (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: statusFilter === f ? '#fff' : T.textMuted, border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans', textTransform: 'capitalize' }}>{f}</button>
          ))}
        </div>
        {loading ? (
          <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading…</div>
        ) : error ? (
          <div style={{ padding: 24, textAlign: 'center', color: '#C94C4C', fontSize: 13 }}>{error}</div>
        ) : rows.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No organisations with this status.</div>
        ) : (
          <AdminTable
            cols={['Name', 'Contact', 'Owner', 'Active', 'Status']}
            rows={rows.map(r => [
              r.name,
              r.contact_email,
              r.owner_email || '—',
              r.is_active ? 'Yes' : 'No',
              <AdminBadge text={r.verification_status} color={ADMIN_ORG_STATUS_COLOR[r.verification_status] || 'gray'} />,
            ])}
            actions={i => {
              const r = rows[i]
              return (
                <div style={{ display: 'flex', gap: 5, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                  {r.verification_status !== 'verified' && (
                    <button disabled={actionBusy} onClick={() => verify(r.id)} style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Verify</button>
                  )}
                  {r.verification_status === 'pending' && (
                    <button disabled={actionBusy} onClick={() => setRejectTarget(r.id)} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Reject</button>
                  )}
                  <button disabled={actionBusy} onClick={() => toggleActive(r.id, !r.is_active)} style={{ background: r.is_active ? '#FEF3C7' : '#DBEAFE', color: r.is_active ? '#D97706' : '#2563EB', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>{r.is_active ? 'Deactivate' : 'Activate'}</button>
                </div>
              )
            }}
          />
        )}
      </AdminCard>

      {rejectTarget != null && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setRejectTarget(null)}>
          <div style={{ background: T.card, borderRadius: 16, padding: 24, maxWidth: 380, width: '90%' }} onClick={e => e.stopPropagation()}>
            <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 10 }}>Reason for rejection</div>
            <textarea value={rejectReason} onChange={e => setRejectReason(e.target.value)} rows={3} placeholder="Explain why this organisation is being rejected…" style={{ width: '100%', boxSizing: 'border-box', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '10px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', resize: 'none', marginBottom: 14 }} />
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

type AdminGroupRow = {
  id: number
  name: string
  description: string | null
  privacy: string
  university_id: number | null
  program_id: number | null
  unit_id: number | null
  unit_code: string | null
  year: number | null
  member_count: number
  created_by: number | null
  created_at: string | null
  is_active: boolean
}

function AdminGroupsPanel() {
  const { mode, tokens: T } = useTheme()
  const [csrfToken, setCsrfToken] = useState('')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [rows, setRows] = useState<AdminGroupRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionBusy, setActionBusy] = useState(false)

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
  }, [])

  const load = () => {
    setLoading(true)
    setError('')
    const params = new URLSearchParams()
    if (search.trim()) params.set('search', search.trim())
    if (statusFilter !== 'all') params.set('status', statusFilter)
    api<{ groups: AdminGroupRow[] }>(`/admin/groups?${params.toString()}`)
      .then(res => setRows(res.groups))
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load groups.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    const t = setTimeout(load, 300)
    return () => clearTimeout(t)
  }, [search, statusFilter])

  const toggleActive = async (id: number, nextActive: boolean) => {
    setActionBusy(true)
    try {
      await api(`/admin/groups/${id}`, {
        method: 'PATCH',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ is_active: nextActive }),
      })
      load()
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Could not update this group.')
    } finally {
      setActionBusy(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <AdminCard title={`Groups — ${rows.length}`}>
        <div style={{ padding: '12px 18px', borderBottom: `1px solid ${T.border}`, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by name…" style={{ flex: 1, minWidth: 180, border: `1px solid ${T.border}`, borderRadius: 8, padding: '7px 10px', fontSize: 12, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card }} />
          {['all', 'active', 'inactive'].map(f => (
            <button key={f} onClick={() => setStatusFilter(f)} style={{ padding: '7px 14px', borderRadius: 8, background: statusFilter === f ? N.navy : (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: statusFilter === f ? '#fff' : T.textMuted, border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'Plus Jakarta Sans', textTransform: 'capitalize' }}>{f}</button>
          ))}
        </div>
        {loading ? (
          <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading…</div>
        ) : error ? (
          <div style={{ padding: 24, textAlign: 'center', color: '#C94C4C', fontSize: 13 }}>{error}</div>
        ) : rows.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No groups found.</div>
        ) : (
          <AdminTable
            cols={['Name', 'Unit', 'Privacy', 'Members', 'Created', 'Status']}
            rows={rows.map(r => [
              r.name,
              r.unit_code || '—',
              r.privacy,
              r.member_count.toString(),
              r.created_at ? new Date(r.created_at).toLocaleDateString() : '—',
              <AdminBadge text={r.is_active ? 'Active' : 'Inactive'} color={r.is_active ? 'green' : 'gray'} />,
            ])}
            actions={i => (
              <button disabled={actionBusy} onClick={() => toggleActive(rows[i].id, !rows[i].is_active)} style={{ background: rows[i].is_active ? '#FEF3C7' : '#DBEAFE', color: rows[i].is_active ? '#D97706' : '#2563EB', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>{rows[i].is_active ? 'Deactivate' : 'Activate'}</button>
            )}
          />
        )}
      </AdminCard>
    </div>
  )
}

// ─── ADMIN: UNIVERSITIES (real CRUD against /admin/universities, /admin/programs) ───

type AdminUniversityRow = { id: number; name: string; short_code: string; country: string | null; is_active: boolean; created_at: string | null }
type AdminProgramRow = { id: number; university_id: number; university_name: string | null; name: string; degree_level: string | null; discipline_category: string | null; is_active: boolean; created_at: string | null }

function AdminUniversitiesPanel() {
  const { mode, tokens: T } = useTheme()
  const [csrfToken, setCsrfToken] = useState('')
  const [universities, setUniversities] = useState<AdminUniversityRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedUniId, setSelectedUniId] = useState<number | null>(null)
  const [programs, setPrograms] = useState<AdminProgramRow[]>([])
  const [programsLoading, setProgramsLoading] = useState(false)
  const [programsError, setProgramsError] = useState('')
  const [actionBusy, setActionBusy] = useState(false)
  const [actionError, setActionError] = useState('')

  const [showCreateUni, setShowCreateUni] = useState(false)
  const [newUniName, setNewUniName] = useState('')
  const [newUniCode, setNewUniCode] = useState('')
  const [newUniCountry, setNewUniCountry] = useState('Kenya')

  const [showCreateProgram, setShowCreateProgram] = useState(false)
  const [newProgramName, setNewProgramName] = useState('')
  const [newProgramLevel, setNewProgramLevel] = useState('')

  const [editUni, setEditUni] = useState<AdminUniversityRow | null>(null)
  const [editUniName, setEditUniName] = useState('')
  const [editUniCode, setEditUniCode] = useState('')
  const [editUniCountry, setEditUniCountry] = useState('')

  const [editProgram, setEditProgram] = useState<AdminProgramRow | null>(null)
  const [editProgramName, setEditProgramName] = useState('')
  const [editProgramLevel, setEditProgramLevel] = useState('')

  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  const loadUniversities = () => {
    setLoading(true); setError('')
    api<{ universities: AdminUniversityRow[] }>('/admin/universities')
      .then(res => {
        setUniversities(res.universities)
        setSelectedUniId(prev => (prev && res.universities.some(u => u.id === prev)) ? prev : (res.universities[0]?.id ?? null))
      })
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load universities.'))
      .finally(() => setLoading(false))
  }
  useEffect(() => { loadUniversities() }, [])

  const loadPrograms = (uniId: number) => {
    setProgramsLoading(true); setProgramsError('')
    api<{ programs: AdminProgramRow[] }>(`/admin/programs?university_id=${uniId}`)
      .then(res => setPrograms(res.programs))
      .catch(e => setProgramsError(e instanceof ApiError ? e.message : 'Could not load programs.'))
      .finally(() => setProgramsLoading(false))
  }
  useEffect(() => { if (selectedUniId != null) loadPrograms(selectedUniId) }, [selectedUniId])

  const createUniversity = async () => {
    if (!newUniName.trim() || !newUniCode.trim() || actionBusy) return
    setActionBusy(true); setActionError('')
    try {
      await api('/admin/universities', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ name: newUniName.trim(), short_code: newUniCode.trim(), country: newUniCountry.trim() || undefined }),
      })
      setNewUniName(''); setNewUniCode(''); setShowCreateUni(false)
      loadUniversities()
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Could not create university.')
    } finally { setActionBusy(false) }
  }

  const toggleUniActive = async (u: AdminUniversityRow) => {
    setActionBusy(true); setActionError('')
    try {
      await api(`/admin/universities/${u.id}`, {
        method: 'PATCH',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ is_active: !u.is_active }),
      })
      loadUniversities()
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Could not update university.')
    } finally { setActionBusy(false) }
  }

  const openEditUni = (u: AdminUniversityRow) => {
    setEditUni(u); setEditUniName(u.name); setEditUniCode(u.short_code); setEditUniCountry(u.country || '')
  }
  const saveEditUni = async () => {
    if (!editUni || actionBusy) return
    setActionBusy(true); setActionError('')
    try {
      await api(`/admin/universities/${editUni.id}`, {
        method: 'PATCH',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ name: editUniName.trim(), short_code: editUniCode.trim(), country: editUniCountry.trim() || null }),
      })
      setEditUni(null)
      loadUniversities()
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Could not save changes.')
    } finally { setActionBusy(false) }
  }

  const createProgram = async () => {
    if (!newProgramName.trim() || selectedUniId == null || actionBusy) return
    setActionBusy(true); setActionError('')
    try {
      await api('/admin/programs', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ university_id: selectedUniId, name: newProgramName.trim(), degree_level: newProgramLevel.trim() || undefined }),
      })
      setNewProgramName(''); setNewProgramLevel(''); setShowCreateProgram(false)
      loadPrograms(selectedUniId)
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Could not create program.')
    } finally { setActionBusy(false) }
  }

  const toggleProgramActive = async (p: AdminProgramRow) => {
    setActionBusy(true); setActionError('')
    try {
      await api(`/admin/programs/${p.id}`, {
        method: 'PATCH',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ is_active: !p.is_active }),
      })
      if (selectedUniId != null) loadPrograms(selectedUniId)
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Could not update program.')
    } finally { setActionBusy(false) }
  }

  const openEditProgram = (p: AdminProgramRow) => {
    setEditProgram(p); setEditProgramName(p.name); setEditProgramLevel(p.degree_level || '')
  }
  const saveEditProgram = async () => {
    if (!editProgram || actionBusy) return
    setActionBusy(true); setActionError('')
    try {
      await api(`/admin/programs/${editProgram.id}`, {
        method: 'PATCH',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ name: editProgramName.trim(), degree_level: editProgramLevel.trim() || null }),
      })
      setEditProgram(null)
      if (selectedUniId != null) loadPrograms(selectedUniId)
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Could not save changes.')
    } finally { setActionBusy(false) }
  }

  const selectedUni = universities.find(u => u.id === selectedUniId) || null

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading universities…</div>
  if (error) return <div style={{ padding: 40, textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{error}</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {actionError && <div style={{ color: '#DC2626', fontSize: 12 }}>{actionError}</div>}
      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 16 }}>
        <AdminCard title={`Universities — ${universities.length}`} action={() => setShowCreateUni(v => !v)} actionLabel={showCreateUni ? 'Cancel' : '+ Add'}>
          {showCreateUni && (
            <div style={{ padding: '14px 18px', borderBottom: `1px solid ${T.border}`, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <input value={newUniName} onChange={e => setNewUniName(e.target.value)} placeholder="University name" style={{ border: `1px solid ${T.border}`, borderRadius: 8, padding: '8px 10px', fontSize: 12, fontFamily: 'Plus Jakarta Sans', background: T.card, color: T.text }} />
              <input value={newUniCode} onChange={e => setNewUniCode(e.target.value.toUpperCase())} placeholder="Short code (e.g. KU)" style={{ border: `1px solid ${T.border}`, borderRadius: 8, padding: '8px 10px', fontSize: 12, fontFamily: 'Plus Jakarta Sans', background: T.card, color: T.text }} />
              <input value={newUniCountry} onChange={e => setNewUniCountry(e.target.value)} placeholder="Country" style={{ border: `1px solid ${T.border}`, borderRadius: 8, padding: '8px 10px', fontSize: 12, fontFamily: 'Plus Jakarta Sans', background: T.card, color: T.text }} />
              <button onClick={createUniversity} disabled={actionBusy || !newUniName.trim() || !newUniCode.trim()} style={{ background: N.gold, color: N.navy, border: 'none', borderRadius: 8, padding: '8px 0', fontWeight: 700, fontSize: 12, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Create</button>
            </div>
          )}
          <div style={{ maxHeight: 520, overflowY: 'auto' }}>
            {universities.map(u => (
              <div key={u.id} onClick={() => setSelectedUniId(u.id)} style={{ padding: '11px 18px', borderBottom: `1px solid ${T.border}`, cursor: 'pointer', background: selectedUniId === u.id ? (mode === 'dark' ? 'rgba(255,255,255,0.05)' : '#F9FAFB') : 'none', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: T.text }} className="line-clamp-1">{u.name}</div>
                  <div style={{ fontSize: 11, color: T.textMuted }}>{u.short_code}{u.country ? ` · ${u.country}` : ''}</div>
                </div>
                <AdminBadge text={u.is_active ? 'Active' : 'Inactive'} color={u.is_active ? 'green' : 'gray'} />
              </div>
            ))}
            {universities.length === 0 && <div style={{ padding: '20px 18px', fontSize: 12, color: T.textMuted }}>No universities yet.</div>}
          </div>
        </AdminCard>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {selectedUni && (
            <AdminCard title={selectedUni.name}>
              <div style={{ padding: '14px 18px', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button onClick={() => openEditUni(selectedUni)} style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: T.text, border: 'none', borderRadius: 8, padding: '7px 14px', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Edit Details</button>
                <button onClick={() => toggleUniActive(selectedUni)} disabled={actionBusy} style={{ background: selectedUni.is_active ? '#FEF3C7' : '#F0FDF4', color: selectedUni.is_active ? '#D97706' : '#16A34A', border: 'none', borderRadius: 8, padding: '7px 14px', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{selectedUni.is_active ? 'Deactivate' : 'Activate'}</button>
              </div>
            </AdminCard>
          )}
          <AdminCard title={`Programs — ${programs.length}`} action={() => setShowCreateProgram(v => !v)} actionLabel={showCreateProgram ? 'Cancel' : '+ Add'}>
            {showCreateProgram && (
              <div style={{ padding: '14px 18px', borderBottom: `1px solid ${T.border}`, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <input value={newProgramName} onChange={e => setNewProgramName(e.target.value)} placeholder="Program name" style={{ flex: 1, minWidth: 160, border: `1px solid ${T.border}`, borderRadius: 8, padding: '8px 10px', fontSize: 12, fontFamily: 'Plus Jakarta Sans', background: T.card, color: T.text }} />
                <input value={newProgramLevel} onChange={e => setNewProgramLevel(e.target.value)} placeholder="Degree level (optional)" style={{ flex: 1, minWidth: 120, border: `1px solid ${T.border}`, borderRadius: 8, padding: '8px 10px', fontSize: 12, fontFamily: 'Plus Jakarta Sans', background: T.card, color: T.text }} />
                <button onClick={createProgram} disabled={actionBusy || !newProgramName.trim() || selectedUniId == null} style={{ background: N.gold, color: N.navy, border: 'none', borderRadius: 8, padding: '8px 16px', fontWeight: 700, fontSize: 12, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Create</button>
              </div>
            )}
            {selectedUniId == null ? (
              <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Select a university to see its programs.</div>
            ) : programsLoading ? (
              <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading…</div>
            ) : programsError ? (
              <div style={{ padding: 24, textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{programsError}</div>
            ) : programs.length === 0 ? (
              <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No programs yet for this university.</div>
            ) : (
              <AdminTable
                cols={['Name', 'Degree Level', 'Status']}
                rows={programs.map(p => [p.name, p.degree_level || '—', <AdminBadge text={p.is_active ? 'Active' : 'Inactive'} color={p.is_active ? 'green' : 'gray'} />])}
                actions={i => (
                  <div style={{ display: 'flex', gap: 5, justifyContent: 'flex-end' }}>
                    <button onClick={() => openEditProgram(programs[i])} style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: T.text, border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Edit</button>
                    <button onClick={() => toggleProgramActive(programs[i])} disabled={actionBusy} style={{ background: programs[i].is_active ? '#FEF3C7' : '#F0FDF4', color: programs[i].is_active ? '#D97706' : '#16A34A', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>{programs[i].is_active ? 'Deactivate' : 'Activate'}</button>
                  </div>
                )}
              />
            )}
          </AdminCard>
        </div>
      </div>

      {editUni && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setEditUni(null)}>
          <div style={{ background: T.card, borderRadius: 16, padding: 24, maxWidth: 380, width: '90%' }} onClick={e => e.stopPropagation()}>
            <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 14 }}>Edit University</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
              <input value={editUniName} onChange={e => setEditUniName(e.target.value)} placeholder="Name" style={{ border: `1px solid ${T.border}`, borderRadius: 10, padding: '10px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', background: T.card, color: T.text }} />
              <input value={editUniCode} onChange={e => setEditUniCode(e.target.value.toUpperCase())} placeholder="Short code" style={{ border: `1px solid ${T.border}`, borderRadius: 10, padding: '10px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', background: T.card, color: T.text }} />
              <input value={editUniCountry} onChange={e => setEditUniCountry(e.target.value)} placeholder="Country" style={{ border: `1px solid ${T.border}`, borderRadius: 10, padding: '10px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', background: T.card, color: T.text }} />
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => setEditUni(null)} style={{ flex: 1, background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: T.text, border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 13 }}>Cancel</button>
              <button onClick={saveEditUni} disabled={actionBusy || !editUniName.trim() || !editUniCode.trim()} style={{ flex: 1, background: N.gold, color: N.navy, border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13 }}>Save</button>
            </div>
          </div>
        </div>
      )}
      {editProgram && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setEditProgram(null)}>
          <div style={{ background: T.card, borderRadius: 16, padding: 24, maxWidth: 380, width: '90%' }} onClick={e => e.stopPropagation()}>
            <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 14 }}>Edit Program</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
              <input value={editProgramName} onChange={e => setEditProgramName(e.target.value)} placeholder="Name" style={{ border: `1px solid ${T.border}`, borderRadius: 10, padding: '10px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', background: T.card, color: T.text }} />
              <input value={editProgramLevel} onChange={e => setEditProgramLevel(e.target.value)} placeholder="Degree level" style={{ border: `1px solid ${T.border}`, borderRadius: 10, padding: '10px 12px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', background: T.card, color: T.text }} />
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => setEditProgram(null)} style={{ flex: 1, background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: T.text, border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 13 }}>Cancel</button>
              <button onClick={saveEditProgram} disabled={actionBusy || !editProgramName.trim()} style={{ flex: 1, background: N.gold, color: N.navy, border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13 }}>Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── ADMIN: COMMUNITY (forum reports, filtered from the existing /admin/content-reports queue) ───

function AdminCommunityPanel() {
  const { mode, tokens: T } = useTheme()
  const [csrfToken, setCsrfToken] = useState('')
  const [reports, setReports] = useState<AdminContentReport[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionBusy, setActionBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [warnTarget, setWarnTarget] = useState<number | null>(null)
  const [warnMessage, setWarnMessage] = useState('')
  const [warnConsequence, setWarnConsequence] = useState('')

  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  const load = () => {
    setLoading(true); setError('')
    api<{ reports: AdminContentReport[] }>('/admin/content-reports?status=pending')
      .then(res => setReports(res.reports.filter(r => r.target_type === 'forum_post' || r.target_type === 'forum_reply')))
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load community reports.'))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const dismiss = async (id: number) => {
    setActionBusy(true); setActionError('')
    try {
      await api(`/admin/content-reports/${id}/dismiss`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      load()
    } catch (e) { setActionError(e instanceof ApiError ? e.message : 'Could not dismiss this report.') } finally { setActionBusy(false) }
  }
  const remove = async (id: number) => {
    setActionBusy(true); setActionError('')
    try {
      await api(`/admin/content-reports/${id}/remove`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      load()
    } catch (e) { setActionError(e instanceof ApiError ? e.message : 'Could not remove this content.') } finally { setActionBusy(false) }
  }
  const warn = async () => {
    if (warnTarget == null || !warnMessage.trim() || !warnConsequence.trim() || actionBusy) return
    setActionBusy(true); setActionError('')
    try {
      await api(`/admin/content-reports/${warnTarget}/warn`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ message: warnMessage.trim(), consequence: warnConsequence.trim() }),
      })
      setWarnTarget(null); setWarnMessage(''); setWarnConsequence('')
      load()
    } catch (e) { setActionError(e instanceof ApiError ? e.message : 'Could not send this warning.') } finally { setActionBusy(false) }
  }

  const forumPostCount = reports.filter(r => r.target_type === 'forum_post').length
  const forumReplyCount = reports.filter(r => r.target_type === 'forum_reply').length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 12 }}>
        <AdminKPI label="Open Forum Post Reports" value={forumPostCount.toString()} color="#DC2626" />
        <AdminKPI label="Open Reply Reports" value={forumReplyCount.toString()} color="#D97706" />
      </div>
      <div style={{ fontSize: 11, color: T.textMuted, lineHeight: 1.5 }}>
        Forum posts and replies are moderated through the same report queue as the rest of the platform - see Moderation for the full cross-content queue. This view filters that queue down to forum items only.
      </div>
      {actionError && <div style={{ color: '#DC2626', fontSize: 12 }}>{actionError}</div>}
      <AdminCard title={`Forum Reports — ${reports.length} Open`}>
        {loading ? (
          <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>Loading…</div>
        ) : error ? (
          <div style={{ padding: 24, textAlign: 'center', color: '#DC2626', fontSize: 13 }}>{error}</div>
        ) : reports.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: T.textMuted, fontSize: 13 }}>No open forum reports.</div>
        ) : (
          <AdminTable
            cols={['#', 'Type', 'Content', 'Reported By', 'Reason', 'Received']}
            rows={reports.map(r => [
              `#${r.id}`,
              r.target_type === 'forum_post' ? 'Forum Post' : 'Forum Reply',
              r.snippet ? `"${r.snippet.slice(0, 60)}${r.snippet.length > 60 ? '…' : ''}"` : '(content removed)',
              r.reporter_email,
              r.reason,
              r.created_at ? new Date(r.created_at).toLocaleString() : '—',
            ])}
            actions={i => (
              <div style={{ display: 'flex', gap: 5 }}>
                <button onClick={() => dismiss(reports[i].id)} disabled={actionBusy} style={{ background: '#F0FDF4', color: '#16A34A', border: 'none', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Dismiss</button>
                <button onClick={() => remove(reports[i].id)} disabled={actionBusy} style={{ background: '#FEE2E2', color: '#DC2626', border: 'none', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Remove</button>
                <button onClick={() => setWarnTarget(reports[i].id)} disabled={actionBusy} style={{ background: '#FEF3C7', color: '#D97706', border: 'none', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'Plus Jakarta Sans' }}>Warn</button>
              </div>
            )}
          />
        )}
      </AdminCard>
      {warnTarget != null && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => setWarnTarget(null)}>
          <div style={{ background: T.card, borderRadius: 16, padding: 24, maxWidth: 400, width: '90%' }} onClick={e => e.stopPropagation()}>
            <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 12 }}>Issue a warning</div>
            <div style={{ fontSize: 11, color: T.textMuted, fontWeight: 600, marginBottom: 4 }}>WHAT THEY DID WRONG</div>
            <textarea value={warnMessage} onChange={e => setWarnMessage(e.target.value)} rows={2} style={{ width: '100%', boxSizing: 'border-box', border: `1px solid ${T.border}`, borderRadius: 10, padding: 10, fontSize: 13, fontFamily: 'Plus Jakarta Sans', marginBottom: 10, resize: 'vertical' }} />
            <div style={{ fontSize: 11, color: T.textMuted, fontWeight: 600, marginBottom: 4 }}>CONSEQUENCE</div>
            <textarea value={warnConsequence} onChange={e => setWarnConsequence(e.target.value)} rows={2} style={{ width: '100%', boxSizing: 'border-box', border: `1px solid ${T.border}`, borderRadius: 10, padding: 10, fontSize: 13, fontFamily: 'Plus Jakarta Sans', marginBottom: 16, resize: 'vertical' }} />
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => setWarnTarget(null)} style={{ flex: 1, background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: T.text, border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 600, fontSize: 13 }}>Cancel</button>
              <button onClick={warn} disabled={!warnMessage.trim() || !warnConsequence.trim() || actionBusy} style={{ flex: 1, background: '#D97706', color: '#fff', border: 'none', borderRadius: 10, padding: '10px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13 }}>Send Warning</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function AdminPlatform({ onExit }: { onExit: () => void }) {
  const { mode, tokens: T } = useTheme()
  const [section, setSection] = useState('dashboard')
  const [adminExpanded, setAdminExpanded] = useState<Record<string, boolean>>({})
  const sectionLabels: Record<string, string> = { dashboard: 'Dashboard', users: 'Users', content: 'Content', universities: 'Universities', community: 'Community', opportunities: 'Opportunities', promotions: 'Promotions', organisations: 'Organisations', 'ai-usage': 'AI & Usage', payments: 'Payments', 'b2b-finance': 'B2B Finance', communications: 'Communications', analytics: 'Analytics', moderation: 'Moderation', system: 'System', operations: 'Operations', settings: 'Settings', groups: 'Groups' }

  return (
    <div style={{ display: 'flex', width: '100vw', height: '100vh', background: T.pageBg, fontFamily: 'Plus Jakarta Sans', overflow: 'hidden' }}>
      {/* Sidebar */}
      <div style={{ width: 220, background: N.navy, display: 'flex', flexDirection: 'column', flexShrink: 0, overflowY: 'auto' }} className="scrollbar-hide">
        <div style={{ padding: '20px 16px 14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <img src="/icon-192.png" alt="Prepza" style={{ width: 32, height: 32, borderRadius: 9 }} />
            <div>
              <div style={{ fontWeight: 800, fontSize: 14, color: '#fff', letterSpacing: '-0.3px' }}>PREPZA</div>
              <div style={{ fontSize: 10, color: N.gold, fontWeight: 600 }}>Admin Platform</div>
            </div>
          </div>
        </div>
        <div style={{ height: 1, background: 'rgba(255,255,255,0.08)', margin: '0 14px 10px' }} />
        <div style={{ flex: 1, padding: '0 8px' }}>
          {adminNavGroups.map(group => {
            const open = Boolean(adminExpanded[group.key])
            const activeGroup = group.items.some(item => item.key === section)
            return <div key={group.key} style={{marginBottom:3}}>
              <button type="button" onClick={()=>setAdminExpanded(v=>({...v,[group.key]:!open}))} style={{width:'100%',display:'flex',alignItems:'center',gap:10,padding:'9px 12px',borderRadius:10,background:activeGroup?'rgba(201,168,76,0.10)':'transparent',border:'1px solid transparent',cursor:'pointer',color:activeGroup?N.gold:'rgba(255,255,255,.78)'}}>
                <AdminNavIcon name={group.icon}/><span style={{flex:1,fontSize:13,fontWeight:activeGroup?750:600,textAlign:'left'}}>{group.label}</span><span style={{fontSize:12,opacity:.55}}>{open?'−':'+'}</span>
              </button>
              {open && <div style={{padding:'2px 0 5px 28px'}}>
                {group.items.map(item=><button type="button" key={item.key} onClick={()=>setSection(item.key)} style={{width:'100%',display:'flex',alignItems:'center',padding:'7px 10px',border:0,borderLeft:`2px solid ${section===item.key?N.gold:'rgba(255,255,255,.08)'}`,background:'transparent',color:section===item.key?N.gold:'rgba(255,255,255,.52)',fontSize:11,cursor:'pointer',textAlign:'left'}}>{item.label}</button>)}
              </div>}
            </div>
          })}
        </div>
        <div style={{ padding: '10px 8px 20px' }}>
          <div style={{ height: 1, background: 'rgba(255,255,255,0.08)', margin: '0 6px 10px' }} />
          <div style={{ padding: '10px 12px', display: 'flex', gap: 10, alignItems: 'center' }}>
            <div style={{ width: 32, height: 32, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, color: N.navy, flexShrink: 0 }}>PA</div>
            <div style={{ flex: 1 }}><div style={{ fontSize: 12, fontWeight: 700, color: '#fff' }}>Prepza Admin</div><div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)' }}>Super Admin</div></div>
          </div>
          <button onClick={onExit} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 10, background: 'transparent', border: '1px solid rgba(255,255,255,0.1)', cursor: 'pointer', marginTop: 6 }}>
            <span style={{ fontSize: 14 }}>📱</span>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'rgba(255,255,255,0.5)' }}>Student App</span>
          </button>
        </div>
      </div>

      {/* Main */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
        {/* Top bar */}
        <div style={{ background: T.card, borderBottom: `1px solid ${T.border}`, padding: '0 24px', height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: 18, color: T.text }}>{sectionLabels[section]}</div>
            <div style={{ fontSize: 11, color: T.textMuted }}>Prepza Admin · {new Date().toLocaleDateString('en-KE', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</div>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 99, padding: '4px 12px' }}>
              <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#16A34A' }} />
              <span style={{ fontSize: 11, fontWeight: 600, color: '#16A34A' }}>All Systems Operational</span>
            </div>
            <button style={{ width: 36, height: 36, background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), border: 'none', borderRadius: 10, cursor: 'pointer', fontSize: 16 }}>🔔</button>
            <div style={{ width: 36, height: 36, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, color: N.navy }}>PA</div>
          </div>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 24 }} className="scrollbar-hide">
          <AdminSection section={section} setSection={setSection} />
        </div>
      </div>
    </div>
  )
}

// ─── APP SHELL ────────────────────────────────────────────────────────────────
// ─── AMBASSADOR PROGRAM ────────────────────────────────────────────────────
// Wired to the live Chunk 9 backend endpoints:
//   GET  /ambassador/status              -> { enrolled, status, referral_code, rejection_reason }
//   GET  /ambassador/dashboard           -> tier/earnings/funnel snapshot
//   GET  /ambassador/referrals           -> { referrals: [...] }
//   GET  /ambassador/payouts             -> { payouts: [...] }
//   POST /ambassador/apply               -> { id, status, referral_code }
//   POST /ambassador/payouts/request     -> { id, amount, status }
// Follows this file's existing per-screen CSRF pattern (fetch /me once on
// mount, store csrf_token in local state, attach it to mutating calls).

