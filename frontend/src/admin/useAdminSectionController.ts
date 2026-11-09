import { useEffect, useState, useRef, type ChangeEvent } from 'react'
import { api, ApiError } from '../lib/appApi'
import { useTheme, currentThemeMode, DARK_THEME } from '../theme/theme'
import type { AdminLibraryQueueItem, AdminLibraryReportItem, AdminInfrastructure, AdminStorageCapacity, AdminSystemCapacity, AdminUniversityEngagement, AdminAnalytics, AdminContentReport, AdminModerationSummary, AdminPlatformSettings, AdminAuditLogEntry, AdminContentMaterial, AdminAiUsage, AdminAiJob, AdminPayment, AdminUserRow, AdminAnnouncementItem } from './AdminShared'

export function useAdminSectionController(section: string, setSection: (section: string) => void) { section, setSection }: { section: string; setSection: (s: string) => void }) {
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


  return {
    mode,
    T,
    search,
    setSearch,
    userFilter,
    setUserFilter,
    selectedUser,
    setSelectedUser,
    confirmAction,
    setConfirmAction,
    contentTab,
    setContentTab,
    commTab,
    setCommTab,
    adminExpanded,
    setAdminExpanded,
    csrfToken,
    setCsrfToken,
    annTitle,
    setAnnTitle,
    annBody,
    setAnnBody,
    annUniversityId,
    setAnnUniversityId,
    annProgramId,
    setAnnProgramId,
    annYear,
    setAnnYear,
    annSemester,
    setAnnSemester,
    annGroupId,
    setAnnGroupId,
    annGroupName,
    setAnnGroupName,
    annGroupSearch,
    setAnnGroupSearch,
    annGroupResults,
    setAnnGroupResults,
    annUniversities,
    setAnnUniversities,
    annPrograms,
    setAnnPrograms,
    annSending,
    setAnnSending,
    annError,
    setAnnError,
    annSent,
    setAnnSent,
    announcements,
    setAnnouncements,
    announcementsLoading,
    setAnnouncementsLoading,
    loadAnnouncements,
    sendAnnouncement,
    adminUsers,
    setAdminUsers,
    adminUsersLoading,
    setAdminUsersLoading,
    adminUsersError,
    setAdminUsersError,
    userActionError,
    setUserActionError,
    loadAdminUsers,
    setUserSuspended,
    libraryQueue,
    setLibraryQueue,
    libraryQueueLoading,
    setLibraryQueueLoading,
    libraryQueueError,
    setLibraryQueueError,
    libraryReports,
    setLibraryReports,
    libraryReportsLoading,
    setLibraryReportsLoading,
    libraryReportsError,
    setLibraryReportsError,
    contentActionError,
    setContentActionError,
    rejectPromptId,
    setRejectPromptId,
    rejectReason,
    setRejectReason,
    removePromptTarget,
    setRemovePromptTarget,
    removeReason,
    setRemoveReason,
    loadLibraryQueue,
    loadLibraryReports,
    approveLibraryItem,
    rejectLibraryItem,
    removeLibraryItem,
    resolveLibraryReport,
    adminPayments,
    setAdminPayments,
    adminPaymentsLoading,
    setAdminPaymentsLoading,
    adminPaymentsError,
    setAdminPaymentsError,
    paymentActionError,
    setPaymentActionError,
    loadAdminPayments,
    refundPayment,
    aiUsage,
    setAiUsage,
    aiUsageLoading,
    setAiUsageLoading,
    aiUsageError,
    setAiUsageError,
    aiUsageDays,
    setAiUsageDays,
    aiJobs,
    setAiJobs,
    aiJobsLoading,
    setAiJobsLoading,
    aiJobsError,
    setAiJobsError,
    aiJobsFilter,
    setAiJobsFilter,
    aiJobActionError,
    setAiJobActionError,
    loadAiUsage,
    loadAiJobs,
    retryAiJob,
    modReports,
    setModReports,
    modReportsLoading,
    setModReportsLoading,
    modReportsError,
    setModReportsError,
    modSummary,
    setModSummary,
    modActionError,
    setModActionError,
    warnPromptId,
    setWarnPromptId,
    warnMessage,
    setWarnMessage,
    warnConsequence,
    setWarnConsequence,
    warnRemoveContent,
    setWarnRemoveContent,
    loadModReports,
    loadModSummary,
    flaggedMaterials,
    setFlaggedMaterials,
    flaggedMaterialsLoading,
    setFlaggedMaterialsLoading,
    flaggedMaterialsError,
    setFlaggedMaterialsError,
    materialActionError,
    setMaterialActionError,
    flagMaterialId,
    setFlagMaterialId,
    flagMaterialReason,
    setFlagMaterialReason,
    flagMaterialBusy,
    setFlagMaterialBusy,
    loadFlaggedMaterials,
    unflagMaterial,
    submitFlagMaterial,
    dismissModReport,
    removeModReportContent,
    warnFromModReport,
    analytics,
    setAnalytics,
    analyticsLoading,
    setAnalyticsLoading,
    analyticsError,
    setAnalyticsError,
    universityEngagement,
    setUniversityEngagement,
    universityEngagementLoading,
    setUniversityEngagementLoading,
    universityEngagementError,
    setUniversityEngagementError,
    filteredUsers,
    dashAnalytics,
    setDashAnalytics,
    dashAnalyticsLoading,
    setDashAnalyticsLoading,
    dashAiUsage,
    setDashAiUsage,
    dashPayments,
    setDashPayments,
    dashPaymentsLoading,
    setDashPaymentsLoading,
    dashModSummary,
    setDashModSummary,
    dashLibraryQueueCount,
    setDashLibraryQueueCount,
    dashRecentUsers,
    setDashRecentUsers,
    dashError,
    setDashError,
    infrastructure,
    setInfrastructure,
    infrastructureLoading,
    setInfrastructureLoading,
    infrastructureError,
    setInfrastructureError,
    otpAdmin,
    setOtpAdmin,
    otpAdminLoading,
    setOtpAdminLoading,
    otpAdminSaving,
    setOtpAdminSaving,
    otpAdminError,
    setOtpAdminError,
    systemCapacity,
    setSystemCapacity,
    storageCapacity,
    setStorageCapacity,
    storageCapacityLoading,
    setStorageCapacityLoading,
    storageCapacityError,
    setStorageCapacityError,
    systemCapacityLoading,
    setSystemCapacityLoading,
    systemCapacityError,
    setSystemCapacityError,
    tierSwitching,
    setTierSwitching,
    tierSwitchError,
    setTierSwitchError,
    adminAccounts,
    setAdminAccounts,
    adminAccountsLoading,
    setAdminAccountsLoading,
    adminAccountsError,
    setAdminAccountsError,
    adminAccountActionError,
    setAdminAccountActionError,
    auditLogs,
    setAuditLogs,
    auditLogsLoading,
    setAuditLogsLoading,
    auditLogsError,
    setAuditLogsError,
    auditActionFilter,
    setAuditActionFilter,
    auditTargetTypeFilter,
    setAuditTargetTypeFilter,
    auditDays,
    setAuditDays,
    auditPage,
    setAuditPage,
    loadAuditLogs,
    saveOtpAdmin,
    loadStorageCapacity,
    loadSystemCapacity,
    switchSupabaseTier,
    loadAdminAccounts,
    setAdminAccountRole,
    platformSettings,
    setPlatformSettings,
    settingsDraft,
    setSettingsDraft,
    settingsLoading,
    setSettingsLoading,
    settingsError,
    setSettingsError,
    settingsSaving,
    setSettingsSaving,
    settingsSaveError,
    setSettingsSaveError,
    settingsSaved,
    setSettingsSaved,
    loadPlatformSettings,
    setPrepzaControlEnabled,
    savePlatformSettings,
    section,
    setSection
  }
}

export type AdminSectionController = ReturnType<typeof useAdminSectionController>
