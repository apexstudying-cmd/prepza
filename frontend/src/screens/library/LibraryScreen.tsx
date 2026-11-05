// Structural extraction only: behavior is covered by tests/test_library_screen_module_contract.py.
import { useEffect, useState, type ComponentType } from 'react'

import { api, ApiError } from '../../lib/appApi'
import { LIBRARY_MATERIAL_TYPES, materialTypeLabel } from '../../lib/library'
import { saveStudyHubDocumentOffline } from '../../offline/studyHubOffline'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Pill from '../../ui/Pill'
import type { UniversityOption } from '../../types/academic'
import type { LibraryPublicationSummary, MySubmission, SavedLibraryItem } from '../../types/library'

type EmptyStateProps = { icon: string; title: string; sub: string; action?: string; onAction?: () => void }
type ErrorStateProps = { onRetry?: () => void }

type LibraryScreenProps = {
  setScreen: (screen: 'publish-library' | 'document-study') => void
  setActiveDocumentId: (id: number | null) => void
  EmptyState: ComponentType<EmptyStateProps>
  ErrorState: ComponentType<ErrorStateProps>
}

export default function LibraryScreen({ setScreen, setActiveDocumentId, EmptyState, ErrorState }: LibraryScreenProps) {
  const { tokens: T } = useTheme()
  const [activeTab, setActiveTab] = useState<'Browse' | 'Saved' | 'Published'>('Browse')
  const [materialTypeFilter, setMaterialTypeFilter] = useState<string | null>(null)
  const [csrfToken, setCsrfToken] = useState('')

  const [browseItems, setBrowseItems] = useState<LibraryPublicationSummary[]>([])
  const [browseLoading, setBrowseLoading] = useState(true)
  const [browseError, setBrowseError] = useState('')

  const [savedItems, setSavedItems] = useState<SavedLibraryItem[]>([])
  const [savedLoading, setSavedLoading] = useState(true)
  const [savedError, setSavedError] = useState('')
  const [savedIds, setSavedIds] = useState<Set<number>>(new Set())
  const [saveNotice, setSaveNotice] = useState('')

  const [submissions, setSubmissions] = useState<MySubmission[]>([])
  const [submissionsLoading, setSubmissionsLoading] = useState(true)
  const [submissionsError, setSubmissionsError] = useState('')

  const [search, setSearch] = useState('')
  const [universityFilter, setUniversityFilter] = useState<number | null>(null)
  const [filterUniversities, setFilterUniversities] = useState<UniversityOption[]>([])

  const [reportItem, setReportItem] = useState<LibraryPublicationSummary | null>(null)
  const [reportReason, setReportReason] = useState('')
  const [reportDetails, setReportDetails] = useState('')
  const [reportSubmitting, setReportSubmitting] = useState(false)
  const [reportError, setReportError] = useState('')
  const [reportSubmitted, setReportSubmitted] = useState(false)

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
  }, [])

  useEffect(() => {
    api<UniversityOption[]>('/universities').then(setFilterUniversities).catch(() => {})
  }, [])

  const submitReport = async () => {
    if (!reportItem || !reportReason || reportSubmitting || !csrfToken) return
    setReportSubmitting(true)
    setReportError('')
    try {
      await api(`/library/${reportItem.id}/report`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ reason: reportReason, details: reportDetails.trim() || undefined }),
      })
      setReportSubmitted(true)
    } catch (e) {
      setReportError(e instanceof ApiError ? e.message : 'Could not submit report. Please try again.')
    } finally {
      setReportSubmitting(false)
    }
  }

  const closeReportModal = () => {
    setReportItem(null)
    setReportReason('')
    setReportDetails('')
    setReportError('')
    setReportSubmitted(false)
  }

  const REPORT_REASONS: { value: string; label: string }[] = [
    { value: 'inaccurate_content', label: 'Inaccurate content' },
    { value: 'plagiarised_material', label: 'Plagiarised material' },
    { value: 'inappropriate_content', label: 'Inappropriate content' },
    { value: 'copyright_violation', label: 'Copyright violation' },
    { value: 'wrong_academic_category_year', label: 'Wrong academic category or year' },
    { value: 'other', label: 'Other' },
  ]

  const loadBrowse = () => {
    setBrowseLoading(true)
    setBrowseError('')
    const params = new URLSearchParams({ page: '1' })
    if (materialTypeFilter) params.set('material_type', materialTypeFilter)
    if (search.trim()) params.set('q', search.trim())
    if (universityFilter != null) params.set('university_id', String(universityFilter))
    api<{ page: number; publications: LibraryPublicationSummary[] }>(`/library?${params.toString()}`)
      .then(res => setBrowseItems(res.publications))
      .catch(e => setBrowseError(e instanceof ApiError ? e.message : 'Could not load the library - check your connection and try again.'))
      .finally(() => setBrowseLoading(false))
  }

  const loadSaved = () => {
    setSavedLoading(true)
    setSavedError('')
    api<{ saved: SavedLibraryItem[] }>('/library/saved')
      .then(res => { setSavedItems(res.saved); setSavedIds(new Set(res.saved.map(s => s.id))) })
      .catch(e => setSavedError(e instanceof ApiError ? e.message : 'Could not load your saved items.'))
      .finally(() => setSavedLoading(false))
  }

  const loadSubmissions = () => {
    setSubmissionsLoading(true)
    setSubmissionsError('')
    api<{ submissions: MySubmission[] }>('/library/my-submissions')
      .then(res => setSubmissions(res.submissions))
      .catch(e => setSubmissionsError(e instanceof ApiError ? e.message : 'Could not load your submissions.'))
      .finally(() => setSubmissionsLoading(false))
  }

  const [academicRefreshKey, setAcademicRefreshKey] = useState(0)
  useEffect(() => {
    const onAcademicChange = () => setAcademicRefreshKey(v => v + 1)
    window.addEventListener('prepza:academic-context-changed', onAcademicChange)
    return () => window.removeEventListener('prepza:academic-context-changed', onAcademicChange)
  }, [])

  useEffect(() => {
    const t = setTimeout(() => { loadBrowse() }, search.trim() ? 350 : 0)
    return () => clearTimeout(t)
  }, [materialTypeFilter, universityFilter, search, academicRefreshKey])
  useEffect(() => { loadSaved() }, [])
  useEffect(() => { loadSubmissions() }, [])

  const toggleSave = async (pub: LibraryPublicationSummary) => {
    if (pub.locked || !pub.document_id) {
      setSaveNotice('This Library item is locked on your current plan. Upgrade to open it.')
      window.setTimeout(() => setSaveNotice(''), 3500)
      return
    }
    if (!csrfToken) return
    const isSaved = savedIds.has(pub.id)
    setSaveNotice('')
    setSavedIds(prev => { const next = new Set(prev); isSaved ? next.delete(pub.id) : next.add(pub.id); return next })
    setBrowseItems(items => items.map(it => it.id === pub.id ? { ...it, save_count: it.save_count + (isSaved ? -1 : 1) } : it))
    try {
      if (isSaved) {
        await api(`/library/${pub.id}/save`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
        setSavedItems(items => items.filter(it => it.id !== pub.id))
      } else {
        const result = await api<{ message: string; document_id?: number; in_studyhub?: boolean; already_in_studyhub?: boolean }>(`/library/${pub.id}/save`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
        if (result.document_id) {
          // A saved Library document is a Study Hub item too: prepare its
          // complete offline package immediately, including ready materials.
          await saveStudyHubDocumentOffline(Number(result.document_id))
        }
        if (result.already_in_studyhub) {
          setSaveNotice('This document is already in your Study Hub and is offline-ready.')
          setTimeout(() => setSaveNotice(''), 4500)
        } else {
          setSaveNotice('Saved to your Study Hub and prepared for offline study.')
          setTimeout(() => setSaveNotice(''), 3500)
        }
        loadSaved()
      }
    } catch {
      setSavedIds(prev => { const next = new Set(prev); isSaved ? next.add(pub.id) : next.delete(pub.id); return next })
      setBrowseItems(items => items.map(it => it.id === pub.id ? { ...it, save_count: it.save_count + (isSaved ? 1 : -1) } : it))
    }
  }

  const statusColor = (status: string) => status === 'approved' ? '#4CC97B' : status === 'rejected' ? '#C94C4C' : N.gold

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      {reportItem && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 99 }}>
          <div style={{ background: T.card, borderRadius: 20, padding: 24, width: '100%', maxWidth: 360 }}>
            {reportSubmitted ? (
              <>
                <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 8 }}>Report submitted</div>
                <div style={{ fontSize: 13, color: T.textMuted, marginBottom: 20 }}>Thanks - our team will review "{reportItem.title}".</div>
                <button onClick={closeReportModal} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 12, padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 13, color: N.navy }}>Done</button>
              </>
            ) : (
              <>
                <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 4 }}>Report Material</div>
                <div style={{ fontSize: 12, color: T.textMuted, marginBottom: 14 }} className="line-clamp-1">{reportItem.title}</div>
                {REPORT_REASONS.map(r => (
                  <button key={r.value} onClick={() => setReportReason(r.value)} style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', background: reportReason === r.value ? 'rgba(201,168,76,0.12)' : '#F8F9FC', border: reportReason === r.value ? `1px solid ${N.gold}55` : '1px solid transparent', borderRadius: 10, padding: '11px 14px', marginBottom: 8, textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: N.navy, cursor: 'pointer' }}>{r.label}</button>
                ))}
                <textarea value={reportDetails} onChange={e => setReportDetails(e.target.value)} placeholder="Additional details (optional)" rows={2} maxLength={500} style={{ width: '100%', border: '1px solid rgba(0,0,0,0.1)', borderRadius: 10, padding: '10px 12px', fontSize: 12, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, resize: 'none', boxSizing: 'border-box', marginTop: 4, marginBottom: 10 }} />
                {reportError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 10 }}>{reportError}</div>}
                <div style={{ display: 'flex', gap: 10 }}>
                  <button onClick={closeReportModal} style={{ flex: 1, background: '#F3F4F6', border: 'none', borderRadius: 12, padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, color: '#374151' }}>Cancel</button>
                  <button onClick={submitReport} disabled={!reportReason || reportSubmitting} style={{ flex: 1, background: (!reportReason || reportSubmitting) ? '#E5E7EB' : '#C94C4C', border: 'none', borderRadius: 12, padding: '12px 0', cursor: (!reportReason || reportSubmitting) ? 'not-allowed' : 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 13, color: (!reportReason || reportSubmitting) ? '#9CA3AF' : '#fff' }}>{reportSubmitting ? 'Submitting…' : 'Submit'}</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => window.history.back()} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 18, color: '#fff' }}>Prepza Library</span>
          <button onClick={() => setScreen('publish-library')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 11, border: 'none', borderRadius: 10, padding: '7px 12px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>+ Publish</button>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {(['Browse', 'Saved', 'Published'] as const).map(t => (
            <button key={t} onClick={() => setActiveTab(t)} style={{ flexShrink: 0, padding: '6px 14px', borderRadius: 20, background: activeTab === t ? N.gold : 'rgba(255,255,255,0.1)', color: activeTab === t ? N.navy : 'rgba(255,255,255,0.65)', fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{t}</button>
          ))}
        </div>
        {activeTab === 'Browse' && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, background: 'rgba(255,255,255,0.08)', borderRadius: 12, padding: '8px 12px' }}>
              <div style={{ color: 'rgba(255,255,255,0.4)' }}>{Ic.search('w-4 h-4')}</div>
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search the library…" style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: 12, fontFamily: 'Plus Jakarta Sans' }} />
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 10, overflowX: 'auto' }} className="scrollbar-hide">
              <button onClick={() => setMaterialTypeFilter(null)} style={{ flexShrink: 0, padding: '5px 12px', borderRadius: 20, background: !materialTypeFilter ? 'rgba(255,255,255,0.18)' : 'rgba(255,255,255,0.08)', color: '#fff', fontWeight: 600, fontSize: 10, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>All types</button>
              {LIBRARY_MATERIAL_TYPES.map(t => (
                <button key={t.value} onClick={() => setMaterialTypeFilter(t.value)} style={{ flexShrink: 0, padding: '5px 12px', borderRadius: 20, background: materialTypeFilter === t.value ? 'rgba(255,255,255,0.18)' : 'rgba(255,255,255,0.08)', color: '#fff', fontWeight: 600, fontSize: 10, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{t.label}</button>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 8, overflowX: 'auto' }} className="scrollbar-hide">
              <select value={universityFilter ?? ''} onChange={e => setUniversityFilter(e.target.value ? Number(e.target.value) : null)} style={{ flexShrink: 0, background: 'rgba(255,255,255,0.08)', color: '#fff', border: 'none', borderRadius: 10, padding: '5px 10px', fontSize: 10, fontFamily: 'Plus Jakarta Sans' }}>
                <option value="">All universities</option>
                {filterUniversities.map(u => <option key={u.id} value={u.id}>{u.short_code}</option>)}
              </select>
            </div>
          </>
        )}
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 16 }} className="scrollbar-hide">
        {activeTab === 'Browse' && (
          browseLoading ? (
            <div style={{ fontSize: 12, color: T.textMuted, padding: '12px 0' }}>Loading the library…</div>
          ) : browseError ? (
            <ErrorState onRetry={loadBrowse} />
          ) : browseItems.length === 0 ? (
            <EmptyState icon="📚" title="Nothing published yet" sub="Be the first to share notes or past papers with other students." action="Publish Material" onAction={() => setScreen('publish-library')} />
          ) : browseItems.map(pub => (
            <div key={pub.id} style={{ background: T.card, borderRadius: 14, padding: '13px 14px', marginBottom: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', display: 'flex', gap: 12, alignItems: 'center', opacity: pub.locked ? 0.62 : 1 }}>
              <div style={{ width: 44, height: 44, background: '#F3F4F6', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{pub.locked ? Ic.lock('w-5 h-5') : Ic.book('w-5 h-5')}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 2 }} className="line-clamp-1">{pub.title}</div>
                <div style={{ fontSize: 11, color: T.textMuted }}>{pub.author}{pub.unit_code ? ` · ${pub.unit_code}` : ''} · {pub.view_count} views</div>
                {pub.locked && <div style={{ fontSize: 10, color: N.gold, fontWeight: 800, marginTop: 4 }}>Premium Library · Upgrade to open</div>}
              </div>
              {!pub.locked && <button onClick={() => toggleSave(pub)} aria-label={savedIds.has(pub.id) ? 'Remove from Study Hub' : 'Save to Study Hub'} style={{ background: 'none', border: 'none', cursor: 'pointer', color: savedIds.has(pub.id) ? N.gold : '#9CA3AF', flexShrink: 0 }}>{Ic.bookmark('w-5 h-5')}</button>}
              <button onClick={() => setReportItem(pub)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.textMuted, flexShrink: 0 }}>{Ic.dots('w-4 h-4')}</button>
            </div>
          ))
        )}
        {activeTab === 'Saved' && (
          savedLoading ? (
            <div style={{ fontSize: 12, color: T.textMuted, padding: '12px 0' }}>Loading your saved items…</div>
          ) : savedError ? (
            <ErrorState onRetry={loadSaved} />
          ) : savedItems.length === 0 ? (
            <EmptyState icon="📚" title="No saved items yet" sub="Bookmark items from the library to find them here." action="Browse Library" onAction={() => setActiveTab('Browse')} />
          ) : savedItems.map(pub => (
            <div key={pub.id} style={{ background: T.card, borderRadius: 14, padding: '13px 14px', marginBottom: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', display: 'flex', gap: 12, alignItems: 'center' }}>
              <div style={{ width: 44, height: 44, background: '#F3F4F6', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, flexShrink: 0 }}>📕</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 2 }} className="line-clamp-1">{pub.title}</div>
                <div style={{ fontSize: 11, color: T.textMuted }}>{pub.author}{pub.unit_code ? ` · ${pub.unit_code}` : ''}</div>
              </div>
              <button onClick={() => toggleSave(pub)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: N.gold, flexShrink: 0 }}>{Ic.bookmark('w-5 h-5')}</button>
            </div>
          ))
        )}
        {activeTab === 'Published' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: T.textMuted }}>Materials you've published to the Prepza Library</div>
              <button onClick={() => setScreen('publish-library')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 11, border: 'none', borderRadius: 10, padding: '6px 12px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>+ Publish</button>
            </div>
            {submissionsLoading ? (
              <div style={{ fontSize: 12, color: T.textMuted, padding: '12px 0' }}>Loading your submissions…</div>
            ) : submissionsError ? (
              <ErrorState onRetry={loadSubmissions} />
            ) : submissions.length === 0 ? (
              <EmptyState icon="📖" title="Nothing published yet" sub="Share your notes and materials with students across Kenya." action="Publish Material" onAction={() => setScreen('publish-library')} />
            ) : submissions.map(p => (
              <div key={p.id} onClick={p.status === 'approved' && p.document_id ? () => { setActiveDocumentId(p.document_id); setScreen('document-study') } : undefined} style={{ background: T.card, borderRadius: 16, padding: '14px 16px', marginBottom: 10, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', border: `1.5px solid ${p.status === 'approved' ? 'rgba(76,201,123,0.2)' : 'rgba(0,0,0,0.06)'}`, cursor: p.status === 'approved' && p.document_id ? 'pointer' : 'default' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 3 }} className="line-clamp-1">{p.title}</div>
                    <div style={{ fontSize: 11, color: T.textMuted }}>{materialTypeLabel(p.material_type)}{p.unit_code ? ` · ${p.unit_code}` : ''}</div>
                  </div>
                  <Pill text={p.status.charAt(0).toUpperCase() + p.status.slice(1)} color={statusColor(p.status)} />
                </div>
                {p.status === 'approved' && (
                  <div style={{ display: 'flex', gap: 16, fontSize: 11, color: T.textMuted, marginTop: 8, paddingTop: 8, borderTop: '1px solid #F3F4F6' }}>
                    <span>{p.view_count} views</span>
                    <span>{p.save_count} saves</span>
                    <span style={{ marginLeft: 'auto' }}>{p.created_at ? new Date(p.created_at).toLocaleDateString() : ''}</span>
                  </div>
                )}
                {p.status === 'pending' && (
                  <div style={{ fontSize: 11, color: '#D97706', marginTop: 6, fontWeight: 600 }}>Submitted {p.created_at ? new Date(p.created_at).toLocaleDateString() : ''} · Published immediately</div>
                )}
                {p.status === 'rejected' && p.rejection_reason && (
                  <div style={{ fontSize: 11, color: '#C94C4C', marginTop: 6, fontWeight: 600 }}>Rejected: {p.rejection_reason}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
