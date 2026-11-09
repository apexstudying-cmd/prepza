import * as React from 'react'
import { useEffect, useState, useRef, type ChangeEvent } from 'react'
import { api, ApiError } from '../lib/appApi'
import { N, useTheme, currentThemeMode, DARK_THEME } from '../theme/theme'
import { Ic } from '../ui/icons'
import Pill from '../ui/Pill'
import { LIBRARY_MATERIAL_TYPES, materialTypeLabel } from '../lib/library'
import B2BFinanceAdmin from './B2BFinanceAdmin'
import AdminOperationsDashboard from './AdminOperationsDashboard'
import { AdminBadge, AdminBarChart, AdminLineChart, AdminKPI, AdminTable, AdminCard } from './AdminShared'
import type { AdminLibraryQueueItem, AdminLibraryReportItem, AdminInfrastructure, AdminStorageCapacity, AdminSystemCapacity, AdminUniversityEngagement, AdminAnalytics, AdminContentReport, AdminModerationSummary, AdminPlatformSettings, AdminAuditLogEntry, AdminContentMaterial, AdminAiUsage, AdminAiJob, AdminPayment, AdminUserRow, AdminAnnouncementItem } from './AdminShared'
import { AdminAmbassadorsPanel, AdminOpportunitiesPanel, AdminPromotionsPanel, AdminOrganisationsPanel, AdminGroupsPanel, AdminUniversitiesPanel, AdminCommunityPanel } from './AdminPanels'

export default function AdminSection({ section, setSection }: { section: string; setSection: (s: string) => void }) {
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
