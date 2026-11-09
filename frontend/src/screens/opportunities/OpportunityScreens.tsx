import { useEffect, useState, type ComponentType } from 'react'

import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Pill from '../../ui/Pill'
import type { OpportunityPublic, SponsoredCampaign } from '../../types/opportunities'

type OpportunityScreenTarget =
  | 'opportunity-detail'
  | 'home'
  | 'share-opp-form'
  | 'share-sheet'

const OPP_FILTERS = ['All', 'Internships', 'Scholarships', 'Competitions', 'Jobs', 'Events', 'Saved']
const OPP_FILTER_TYPE_MAP: Record<string, string | undefined> = {
  All: undefined,
  Internships: 'internship',
  Scholarships: 'scholarship',
  Competitions: 'competition',
  Jobs: 'job',
  Events: 'event',
}

const OPP_DETAIL_CACHE: Record<number, OpportunityPublic> = {}

export function OpportunitiesScreen({
  setScreen,
  setActiveOpportunityId,
  SponsoredOpportunityCard,
  SkOppCard,
  ErrorState,
  EmptyState,
}: {
  setScreen: (s: OpportunityScreenTarget) => void
  setActiveOpportunityId: (id: number | null) => void
  SponsoredOpportunityCard: ComponentType<{
    campaign: SponsoredCampaign
    setScreen: (s: OpportunityScreenTarget) => void
    setActiveOpportunityId: (id: number | null) => void
    compact?: boolean
  }>
  SkOppCard: ComponentType
  ErrorState: ComponentType<{ onRetry?: () => void }>
  EmptyState: ComponentType<{
    icon: string
    title: string
    sub: string
    action?: string
    onAction?: () => void
  }>
}) {
  const { tokens: T } = useTheme()
  const [filter, setFilter] = useState('All')
  const [query, setQuery] = useState('')
  const [opps, setOpps] = useState<OpportunityPublic[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')
  const [togglingId, setTogglingId] = useState<number | null>(null)
  const [sponsored, setSponsored] = useState<SponsoredCampaign[]>([])
  const [academicRefreshKey, setAcademicRefreshKey] = useState(0)

  useEffect(() => {
    const onAcademicChange = () => setAcademicRefreshKey(v => v + 1)
    window.addEventListener('prepza:academic-context-changed', onAcademicChange)
    return () => window.removeEventListener('prepza:academic-context-changed', onAcademicChange)
  }, [])

  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  useEffect(() => {
    api<{ campaigns: SponsoredCampaign[] }>('/api/discovery/feed?placement=opportunities')
      .then(res => setSponsored(res.campaigns || []))
      .catch(() => setSponsored([]))
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError('')
    const load = async () => {
      try {
        if (filter === 'Saved') {
          const res = await api<{ saved: OpportunityPublic[] }>('/opportunities/saved')
          if (!cancelled) setOpps(res.saved)
        } else {
          const params = new URLSearchParams()
          if (query.trim()) params.set('q', query.trim())
          const type = OPP_FILTER_TYPE_MAP[filter]
          if (type) params.set('opportunity_type', type)
          const res = await api<{ page: number; opportunities: OpportunityPublic[] }>(`/opportunities?${params.toString()}`)
          if (!cancelled) setOpps(res.opportunities)
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof ApiError ? e.message : 'Could not load opportunities.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    const t = setTimeout(load, 300)
    return () => { cancelled = true; clearTimeout(t) }
  }, [filter, query, academicRefreshKey])

  const toggleSave = async (o: OpportunityPublic) => {
    if (togglingId != null) return
    setTogglingId(o.id)
    const wasSaved = o.saved
    setOpps(list => list.map(x => x.id === o.id ? { ...x, saved: !wasSaved } : x))
    try {
      if (wasSaved) {
        await api(`/opportunities/${o.id}/save`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
        if (filter === 'Saved') setOpps(list => list.filter(x => x.id !== o.id))
      } else {
        await api(`/opportunities/${o.id}/save`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      }
    } catch {
      setOpps(list => list.map(x => x.id === o.id ? { ...x, saved: wasSaved } : x))
    } finally {
      setTogglingId(null)
    }
  }

  const openDetail = (id: number) => { setActiveOpportunityId(id); setScreen('opportunity-detail') }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Opportunities 🚀</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>Curated for Kenyan students</div>
          </div>
          <button onClick={() => setScreen('share-opp-form')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 10, padding: '7px 12px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 12, color: N.navy }}>+ Share</button>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', background: 'rgba(255,255,255,0.09)', borderRadius: 13, padding: '10px 14px', border: '1px solid rgba(255,255,255,0.1)', marginBottom: 12 }}>
          <div style={{ color: 'rgba(255,255,255,0.4)' }}>{Ic.search()}</div>
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search opportunities..." style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: 13, fontFamily: 'Plus Jakarta Sans' }} />
        </div>
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto' }} className="scrollbar-hide">
          {OPP_FILTERS.map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{ flexShrink: 0, padding: '6px 14px', borderRadius: 20, background: filter === f ? N.gold : 'rgba(255,255,255,0.1)', color: filter === f ? N.navy : 'rgba(255,255,255,0.65)', fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{f}</button>
          ))}
        </div>
      </div>
      <div style={{ padding: 16 }}>
        {sponsored.length > 0 && filter !== 'Saved' && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12, fontWeight: 800, color: T.textMuted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: .5 }}>For you</div>
            {sponsored.slice(0, 2).map(c => (
              <SponsoredOpportunityCard key={c.campaign_id} campaign={c} setScreen={setScreen} setActiveOpportunityId={setActiveOpportunityId} />
            ))}
          </div>
        )}
        {loading ? (
          [1,2,3].map(i => <SkOppCard key={i} />)
        ) : error ? (
          <ErrorState onRetry={() => setFilter(f => f)} />
        ) : opps.length === 0 ? (
          <EmptyState icon="🚀" title={filter === 'Saved' ? 'No saved opportunities' : 'No opportunities found'} sub={filter === 'Saved' ? 'Save opportunities to find them here later.' : 'Try a different search or filter.'} />
        ) : opps.map(o => {
          const meta = oppTypeMeta(o.opportunity_type)
          const deadline = fmtDeadline(o.application_deadline)
          return (
            <div key={o.id} onClick={() => openDetail(o.id)} style={{ background: T.card, borderRadius: 18, overflow: 'hidden', boxShadow: '0 4px 14px rgba(0,0,0,0.08)', marginBottom: 14, cursor: 'pointer' }}>
              <div style={{ height: 5, background: `linear-gradient(90deg,${meta.color},${meta.color}66)` }} />
              <div style={{ padding: 16 }}>
                <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
                  <div style={{ width: 48, height: 48, background: meta.color + '18', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, flexShrink: 0 }}>{meta.icon}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 800, fontSize: 14, color: T.text }} className="line-clamp-1">{o.title}</div>
                    <div style={{ fontSize: 12, color: T.textMuted }} className="line-clamp-1">{o.organisation?.name || 'Unknown organisation'}</div>
                  </div>
                  <Pill text={o.promotion_type === 'sponsored' ? 'Sponsored' : o.promotion_type === 'featured' ? 'Featured' : meta.label} color={o.promotion_type ? N.gold : meta.color} />
                </div>
                <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 14 }}>
                  {o.location && <span style={{ fontSize: 11, color: T.textMuted }}>📍 {o.location}{o.is_remote ? ' · Remote' : ''}</span>}
                  {!o.location && o.is_remote && <span style={{ fontSize: 11, color: T.textMuted }}>🌐 Remote</span>}
                  {deadline && <span style={{ fontSize: 11, color: T.textMuted }}>⏰ {deadline}</span>}
                  <span style={{ fontSize: 11, color: T.textMuted }}>👁 {o.view_count}</span>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button onClick={e => { e.stopPropagation(); openDetail(o.id) }} style={{ flex: 1, background: `linear-gradient(135deg,${N.navy},${N.navy3})`, color: N.gold, fontWeight: 700, fontSize: 13, border: 'none', borderRadius: 12, padding: '11px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>View Details →</button>
                  <button onClick={e => { e.stopPropagation(); toggleSave(o) }} disabled={togglingId === o.id} style={{ width: 44, height: 44, background: o.saved ? `${N.gold}20` : '#F8F9FC', border: `1px solid ${o.saved ? N.gold + '55' : 'rgba(0,0,0,0.06)'}`, borderRadius: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: o.saved ? N.gold : T.textMuted }}>{Ic.bookmark('w-4 h-4')}</div></button>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function OppDetailScreen({
  setScreen,
  opportunityId,
  TopBar,
  EmptyState,
  DelayedScreenSkeleton,
  SkeletonOppDetail,
  ErrorState,
}: {
  setScreen: (s: OpportunityScreenTarget) => void
  opportunityId: number | null
  TopBar: ComponentType<{ title?: string; onBack?: () => void }>
  EmptyState: ComponentType<{
    icon: string
    title: string
    sub: string
    action?: string
    onAction?: () => void
  }>
  DelayedScreenSkeleton: ComponentType<{ children: React.ReactNode }>
  SkeletonOppDetail: ComponentType
  ErrorState: ComponentType<{ onRetry?: () => void }>
}) {
  const { tokens: T } = useTheme()
  const [opp, setOpp] = useState<OpportunityPublic | null>(() => opportunityId != null ? (OPP_DETAIL_CACHE[opportunityId] ?? null) : null)
  const [loading, setLoading] = useState(() => opportunityId != null && !!OPP_DETAIL_CACHE[opportunityId] ? false : true)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')
  const [saving, setSaving] = useState(false)
  const [showApply, setShowApply] = useState(false)

  useEffect(() => { api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {}) }, [])

  useEffect(() => {
    if (opportunityId == null) { setLoading(false); return }
    const cached = OPP_DETAIL_CACHE[opportunityId]
    if (cached) { setOpp(cached); setLoading(false) } else { setLoading(true) }
    setError('')
    api<any>(`/api/opportunities/${opportunityId}/organic-view?source=${OPP_DETAIL_CACHE[opportunityId]?.promotion_type === 'sponsored' ? 'paid' : 'organic'}`)
      .then(res => { setOpp(res.opportunity || res); OPP_DETAIL_CACHE[opportunityId] = (res.opportunity || res) })
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load this opportunity.'))
      .finally(() => setLoading(false))
  }, [opportunityId])

  const toggleSave = async () => {
    if (!opp || saving) return
    setSaving(true)
    const wasSaved = opp.saved
    const optimistic = { ...opp, saved: !wasSaved }
    setOpp(optimistic)
    OPP_DETAIL_CACHE[optimistic.id] = optimistic
    try {
      await api(`/opportunities/${opp.id}/save`, { method: wasSaved ? 'DELETE' : 'POST', headers: { 'X-CSRF-Token': csrfToken } })
    } catch {
      setOpp(o => o ? { ...o, saved: wasSaved } : o)
      OPP_DETAIL_CACHE[opp.id] = { ...opp, saved: wasSaved }
    } finally {
      setSaving(false)
    }
  }

  if (opportunityId == null) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
        <div style={{ background: N.navy, padding: '0 18px 16px' }}>
          <TopBar title="Opportunity Details" onBack={() => window.history.back()} />
        </div>
        <EmptyState icon="🚀" title="No opportunity selected" sub="Go back and pick an opportunity to view its details." action="Back to Opportunities" onAction={() => window.history.back()} />
      </div>
    )
  }

  if (loading) return <DelayedScreenSkeleton><SkeletonOppDetail /></DelayedScreenSkeleton>

  if (error || !opp) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
        <div style={{ background: N.navy, padding: '0 18px 16px' }}>
          <TopBar title="Opportunity Details" onBack={() => window.history.back()} />
        </div>
        <ErrorState />
      </div>
    )
  }

  const meta = oppTypeMeta(opp.opportunity_type)
  const deadline = fmtDeadline(opp.application_deadline)

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <button onClick={() => window.history.back()} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Opportunity Details</span>
          <button onClick={toggleSave} disabled={saving} style={{ width: 34, height: 34, background: opp.saved ? 'rgba(201,168,76,0.2)' : 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: opp.saved ? N.gold : '#fff' }}>{Ic.bookmark()}</div>
          </button>
        </div>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
          <div style={{ width: 60, height: 60, background: `${meta.color}25`, borderRadius: 18, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 28 }}>{meta.icon}</div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 16, color: '#fff' }}>{opp.title}</div>
            <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.6)' }}>{opp.organisation?.name || 'Unknown organisation'}</div>
            {opp.promotion_type && <Pill text={opp.promotion_type === 'sponsored' ? 'Sponsored' : 'Featured'} color={N.gold} />}
          </div>
        </div>
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {[
            opp.location ? ['📍', opp.location + (opp.is_remote ? ' · Remote' : '')] : (opp.is_remote ? ['🌐', 'Remote'] : null),
            deadline ? ['⏰', `Deadline: ${deadline}`] : null,
            ['👁', `${opp.view_count} views`],
          ].filter((x): x is [string, string] => x !== null).map(([icon, val]) => (
            <div key={val} style={{ background: T.card, borderRadius: 12, padding: '8px 12px', display: 'flex', gap: 6, alignItems: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
              <span style={{ fontSize: 14 }}>{icon}</span>
              <span style={{ fontSize: 12, fontWeight: 600, color: T.text }}>{val}</span>
            </div>
          ))}
        </div>
        <div style={{ background: T.card, borderRadius: 16, padding: 16, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
          <div style={{ fontWeight: 800, fontSize: 14, color: T.text, marginBottom: 10 }}>About this Opportunity</div>
          <div style={{ fontSize: 13, color: T.text, lineHeight: 1.8, whiteSpace: 'pre-line' }}>{opp.description}</div>
        </div>
        {opp.application_instructions && (
          <div style={{ background: T.card, borderRadius: 16, padding: 16, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
            <div style={{ fontWeight: 800, fontSize: 14, color: T.text, marginBottom: 10 }}>How to Apply</div>
            <div style={{ fontSize: 13, color: T.text, lineHeight: 1.8, whiteSpace: 'pre-line' }}>{opp.application_instructions}</div>
          </div>
        )}
        {opp.application_url ? (
          <button onClick={() => setShowApply(true)} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '15px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: `0 6px 20px rgba(201,168,76,0.35)` }}>Apply Now →</button>
        ) : (
          <div style={{ background: '#F3F4F6', borderRadius: 16, padding: '14px 16px', textAlign: 'center', fontSize: 12, color: T.textMuted, fontWeight: 600 }}>No application link provided — check the description above for how to apply.</div>
        )}
        <button onClick={() => setScreen('share-sheet')} style={{ background: T.card, color: T.text, fontWeight: 700, fontSize: 14, border: '1px solid rgba(0,0,0,0.08)', borderRadius: 16, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          <div style={{ color: T.textMuted }}>{Ic.share('w-4 h-4')}</div> Share Opportunity
        </button>
      </div>

      {showApply && opp.application_url && (
        <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'flex-end', zIndex: 50 }}>
          <div style={{ background: T.card, borderRadius: '24px 24px 0 0', padding: '28px 24px 36px', width: '100%' }}>
            <div style={{ width: 40, height: 4, background: '#E5E7EB', borderRadius: 99, margin: '0 auto 20px' }} />
            <div style={{ fontSize: 24, textAlign: 'center', marginBottom: 12 }}>🌐</div>
            <div style={{ fontWeight: 800, fontSize: 17, color: T.text, textAlign: 'center', marginBottom: 10 }}>You're leaving Prepza</div>
            <div style={{ fontSize: 13, color: T.textMuted, textAlign: 'center', lineHeight: 1.65, marginBottom: 24 }}>
              You will be taken to <strong>{opp.organisation?.name || 'the organisation'}'s</strong> website to complete your application. Prepza is not responsible for third-party application processes.
            </div>
            <a href={opp.application_url} target="_blank" rel="noopener noreferrer" style={{ display: 'block', textAlign: 'center', textDecoration: 'none', width: '100%', boxSizing: 'border-box', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 14, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', marginBottom: 10 }}>Continue to Website →</a>
            <button onClick={() => setShowApply(false)} style={{ width: '100%', background: '#F3F4F6', color: T.text, fontWeight: 700, fontSize: 14, border: 'none', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── SHARE SHEET ──────────────────────────────────────────────────────────────
// There's no backend "share" endpoint (and no activeShareContext plumbing
// yet to say WHAT is being shared from each of the many screens that open
// this sheet), so this builds a generic Prepza link client-side and uses
// navigator.share()/clipboard - it does not know or claim to know the
// specific document/post/opportunity that triggered it.
