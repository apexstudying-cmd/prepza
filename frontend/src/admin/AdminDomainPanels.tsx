import * as React from 'react'
import { useEffect, useState, useRef, type ChangeEvent } from 'react'
import { api, ApiError } from '../lib/appApi'
import { N, useTheme, currentThemeMode, DARK_THEME } from '../theme/theme'
import { Ic } from '../ui/icons'
import Pill from '../ui/Pill'
import { AdminBadge, AdminBarChart, AdminLineChart, AdminKPI, AdminTable, AdminCard } from './AdminShared'
import type { AdminLibraryQueueItem, AdminLibraryReportItem, AdminInfrastructure, AdminStorageCapacity, AdminSystemCapacity, AdminUniversityEngagement, AdminAnalytics, AdminContentReport, AdminModerationSummary, AdminPlatformSettings, AdminAuditLogEntry, AdminContentMaterial, AdminAiUsage, AdminAiJob, AdminPayment, AdminUserRow, AdminAnnouncementItem } from './AdminShared'

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

export function AdminPromotionsPanel() {
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

export function AdminOrganisationsPanel() {
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

export function AdminGroupsPanel() {
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

export function AdminUniversitiesPanel() {
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

export function AdminCommunityPanel() {
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
