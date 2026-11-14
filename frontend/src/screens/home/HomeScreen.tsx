import { useEffect, useState, type ComponentType, type ReactNode } from 'react'

import { api } from '../../lib/appApi'
import { readLastStudyDocumentId, rememberLastStudyDocument } from '../../lib/lastStudyDocument'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Pill from '../../ui/Pill'
import { setOfflineUserId } from '../../offline/generatedMaterials'
import { podcastColor, podcastDuration, type PodcastItem } from '../../types/podcast'
import { oppTypeMeta, fmtDeadline } from '../../lib/opportunities'
import type { HomeDocument } from '../../types/profile'
import type { GamificationSummary } from '../../types/gamification'
import type { OpportunityPublic, SponsoredCampaign } from '../../types/opportunities'

type HomeRoute = 'ai-tutor' | 'notifications' | 'library' | 'upload' | 'document-study' | 'study-materials' | 'podcast-library' | 'podcast-player' | 'opportunities' | 'opportunity-detail' | 'shop'
type HomeScreenProps = {
  setScreen: (screen: HomeRoute) => void
  setActiveDocumentId: (id: number | null) => void
  setActiveOpportunityId: (id: number | null) => void
  SponsoredOpportunityCard: ComponentType<any>
  loadingView: ReactNode
}

const HOME_CACHE: { me?: { display_name: string | null }; documents?: HomeDocument[] } = {}
export default function HomeScreen({ setScreen, setActiveDocumentId, setActiveOpportunityId, SponsoredOpportunityCard, loadingView }: HomeScreenProps) {
  const { tokens: T } = useTheme()
  const [notifCount, setNotifCount] = useState(0)

  const [displayName, setDisplayName] = useState<string | null>(HOME_CACHE.me?.display_name ?? null)
  const [meLoading, setMeLoading] = useState(HOME_CACHE.me === undefined)
  const [documents, setDocuments] = useState<HomeDocument[]>(HOME_CACHE.documents ?? [])
  const [docsLoading, setDocsLoading] = useState(HOME_CACHE.documents === undefined)
  const [summary, setSummary] = useState<GamificationSummary | null>(null)

  const [previewOpps, setPreviewOpps] = useState<OpportunityPublic[]>([])
  const [sponsoredHome, setSponsoredHome] = useState<SponsoredCampaign[]>([])
  const [homePodcasts, setHomePodcasts] = useState<PodcastItem[]>([])

  useEffect(() => {
    api<{ opportunities: OpportunityPublic[] }>('/opportunities')
      .then(res => setPreviewOpps(res.opportunities.slice(0, 2)))
      .catch(() => {})
    api<{ campaigns: SponsoredCampaign[] }>('/api/discovery/feed?placement=home_carousel')
      .then(res => setSponsoredHome(res.campaigns || []))
      .catch(() => setSponsoredHome([]))
    api<{ podcasts: PodcastItem[] }>('/podcasts')
      .then(res => setHomePodcasts(res.podcasts.slice(0, 4)))
      .catch(() => {})
  }, [])

  useEffect(() => {
    api<{ id?: number; display_name: string | null }>('/me')
      .then(me => {
        if (Number.isInteger(Number(me.id)) && Number(me.id) > 0) setOfflineUserId(Number(me.id))
        setDisplayName(me.display_name); HOME_CACHE.me = me
      })
      .catch(() => {})
      .finally(() => setMeLoading(false))
    api<{ documents: HomeDocument[] }>('/documents')
      .then(res => { setDocuments(res.documents); HOME_CACHE.documents = res.documents })
      .catch(() => {})
      .finally(() => setDocsLoading(false))
    api<GamificationSummary>('/gamification/summary')
      .then(setSummary)
      .catch(() => {})
    api<{ unread_count: number }>('/notifications/unread-count')
      .then(r => setNotifCount(r.unread_count))
      .catch(() => {})
  }, [])

  const greetingName = displayName || 'there'
  const activeDocs = documents.filter(d => !docsLoading)
  const lastStudyId = readLastStudyDocumentId()
  const featuredDoc = activeDocs.find(document => document.id === lastStudyId) || activeDocs[0]
  const restDocs = featuredDoc ? activeDocs.filter(document => document.id !== featuredDoc.id) : []

  if (meLoading || docsLoading) return loadingView
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      {/* Header */}
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <img src="/icon-192.png" alt="Prepza" style={{ width: 36, height: 36, borderRadius: 10 }} />
            <div>
              <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11, fontWeight: 500 }}>Good morning,</div>
              <div style={{ color: '#fff', fontSize: 17, fontWeight: 800, letterSpacing: '-0.3px' }}>{greetingName} 👋</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setScreen('ai-tutor')} style={{ width: 38, height: 38, background: 'rgba(201,168,76,0.14)', border: '1px solid rgba(201,168,76,0.28)', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <div style={{ color: N.gold, fontSize: 18 }}>✦</div>
            </button>
            <button onClick={() => setScreen('notifications')} style={{ position: 'relative', width: 38, height: 38, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <div style={{ color: '#fff' }}>{Ic.bell()}</div>
              {notifCount > 0 && <div style={{ position: 'absolute', top: 7, right: 7, width: 8, height: 8, background: N.gold, borderRadius: '50%', border: `1.5px solid ${N.navy}` }} />}
            </button>
          </div>
        </div>
        {/* Streak */}
        <div style={{ background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.22)', borderRadius: 14, padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 20 }}>🔥</span>
          <div style={{ flex: 1 }}>
            <div style={{ color: N.gold, fontWeight: 800, fontSize: 13 }}>
              {summary ? `${summary.current_streak}-Day Streak${summary.current_streak > 0 ? ' — Keep it up!' : ''}` : 'Loading streak...'}
            </div>
            <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11 }}>Study 30 mins today to extend it</div>
          </div>
          {summary && <Pill text={`${summary.xp_total.toLocaleString()} XP`} color={N.gold} />}
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 24, paddingBottom: 24 }}>
        {/* Continue Studying */}
        <section style={{ padding: '20px 18px 0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={{ fontWeight: 800, fontSize: 15, color: T.text }}>Continue Studying</span>
            
          </div>
          {docsLoading ? (
            <div style={{ fontSize: 12, color: T.textMuted, padding: '12px 0' }}>Loading your documents...</div>
          ) : !featuredDoc ? (
            <div onClick={() => setScreen('upload')} style={{ background: T.card, borderRadius: 14, padding: '18px 16px', textAlign: 'center', cursor: 'pointer', border: `1px dashed ${T.border}` }}>
              <div style={{ fontSize: 12, color: T.textMuted, fontWeight: 600 }}>No documents yet — upload one to get started 📤</div>
            </div>
          ) : (
            <>
              {/* Featured doc */}
              <div onClick={() => { rememberLastStudyDocument(featuredDoc.id); setActiveDocumentId(featuredDoc.id); setScreen('document-study') }} style={{ background: `linear-gradient(135deg,${N.navy},${N.navy3})`, borderRadius: 18, padding: 18, cursor: 'pointer', position: 'relative', overflow: 'hidden', marginBottom: 10 }}>
                <div style={{ position: 'absolute', right: -20, top: -20, width: 120, height: 120, background: 'rgba(201,168,76,0.07)', borderRadius: '50%', pointerEvents: 'none' }} />
                <div style={{ display: 'flex', gap: 14, alignItems: 'center', marginBottom: 14 }}>
                  <div style={{ width: 48, height: 48, background: 'rgba(201,168,76,0.15)', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, color: N.gold, fontWeight: 800 }}>{Ic.book('w-6 h-6')}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 800, fontSize: 14, color: '#fff' }} className="line-clamp-1">{featuredDoc.title}</div>
                    <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', marginTop: 2, textTransform: 'capitalize' }}>{featuredDoc.status}</div>
                  </div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <button onClick={e => { e.stopPropagation(); rememberLastStudyDocument(featuredDoc.id); setActiveDocumentId(featuredDoc.id); setScreen('document-study') }} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 11, border: 'none', borderRadius: 10, padding: '6px 14px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Continue →</button>
                </div>
              </div>
              {/* Other docs */}
              {restDocs.map(d => (
                <div key={d.id} onClick={() => { rememberLastStudyDocument(d.id); setActiveDocumentId(d.id); setScreen('document-study') }} style={{ background: T.card, borderRadius: 14, padding: '12px 14px', marginBottom: 8, boxShadow: '0 2px 10px rgba(0,0,0,0.05)', display: 'flex', gap: 12, alignItems: 'center', cursor: 'pointer', border: '1px solid rgba(0,0,0,0.04)' }}>
                  <div style={{ width: 40, height: 40, background: N.gold + '18', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, color: N.gold, fontWeight: 800 }}>{Ic.book('w-5 h-5')}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 12, color: T.text }} className="line-clamp-1">{d.title}</div>
                    <div style={{ fontSize: 11, color: T.textMuted, textTransform: 'capitalize' }}>{d.status}</div>
                  </div>
                </div>
              ))}
            </>
          )}
        </section>

        {/* AI Study Tools */}
        <section style={{ padding: '0 18px' }}>
          <div style={{ fontWeight: 800, fontSize: 15, color: T.text, marginBottom: 14 }}>AI Study Tools</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 8 }}>
            {[
              { icon: Ic.upload('w-6 h-6'), label: 'Upload', action: () => setScreen('upload') },
              { icon: Ic.book('w-6 h-6'), label: 'My Study', action: () => setScreen('study-materials') },
              { icon: Ic.explore('w-6 h-6'), label: 'Library', action: () => setScreen('library') },
              { icon: Ic.flash('w-6 h-6'), label: 'Morio', action: () => setScreen('ai-tutor') },
              { icon: Ic.image('w-6 h-6'), label: 'Shop', action: () => setScreen('shop') },
            ].map((t, i) => (
              <button key={i} onClick={t.action} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                <div style={{ width: 52, height: 52, borderRadius: 16, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, border: '1px solid rgba(201,168,76,0.15)' }}>{t.icon}</div>
                <span style={{ fontSize: 10, fontWeight: 600, color: T.textMuted, fontFamily: 'Plus Jakarta Sans' }}>{t.label}</span>
              </button>
            ))}
          </div>
        </section>

        {/* Podcasts */}
        {homePodcasts.length > 0 && (
          <section>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 18px', marginBottom: 12 }}>
              <span style={{ fontWeight: 800, fontSize: 15, color: T.text }}>Study Podcasts</span>
              <span onClick={() => setScreen('podcast-library')} style={{ fontSize: 12, color: N.gold, fontWeight: 700, cursor: 'pointer' }}>See all →</span>
            </div>
            <div style={{ display: 'flex', gap: 12, padding: '0 18px', overflowX: 'auto' }} className="scrollbar-hide">
              {homePodcasts.map(p => {
                const color = podcastColor(p.document_id)
                return (
                  <div key={p.document_id} onClick={() => { setActiveDocumentId(p.document_id); setScreen('podcast-player') }} style={{ flexShrink: 0, width: 140, borderRadius: 16, overflow: 'hidden', boxShadow: '0 4px 14px rgba(0,0,0,0.09)', cursor: 'pointer' }}>
                    <div style={{ height: 90, background: `linear-gradient(135deg,${color},${color}99)`, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', fontSize: 28, color: '#fff', fontWeight: 800 }}>{Ic.podcast('w-8 h-8')}</div>
                    <div style={{ background: T.card, padding: '10px 10px 12px' }}>
                      <div style={{ fontWeight: 700, fontSize: 12, color: T.text, marginBottom: 5 }} className="line-clamp-1">{p.title}</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <div style={{ color }}>{Ic.play('w-3 h-3')}</div>
                        <span style={{ fontSize: 10, color, fontWeight: 700 }}>{p.audio_status === 'ready' ? podcastDuration(p.duration_seconds) : 'Processing…'}</span>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </section>
        )}

        {/* Sponsored opportunities */}
        {sponsoredHome.length > 0 && (
          <section style={{ padding: '0 18px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <span style={{ fontWeight: 800, fontSize: 15, color: T.text }}>Sponsored opportunities</span>
              <button onClick={() => setScreen('opportunities')} style={{ background: 'none', border: 'none', padding: 0, color: N.gold, fontWeight: 800, fontSize: 12, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>See all</button>
            </div>
            <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 4 }} className="scrollbar-hide">
              {sponsoredHome.slice(0, 3).map(c => (
                <SponsoredOpportunityCard key={c.campaign_id} campaign={c} compact setScreen={setScreen} setActiveOpportunityId={setActiveOpportunityId} />
              ))}
            </div>
          </section>
        )}

        {/* Opportunities */}
        {previewOpps.length > 0 && (
          <section style={{ padding:'0 18px' }}>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:12}}>
              <span style={{fontWeight:800,fontSize:15,color:T.text}}>Opportunities</span>
              <button onClick={()=>setScreen('opportunities')} style={{background:'none',border:'none',padding:0,color:N.gold,fontWeight:800,fontSize:12,cursor:'pointer',fontFamily:'Plus Jakarta Sans'}}>See all</button>
            </div>
            <div style={{display:'flex',gap:12,overflowX:'auto',paddingBottom:4}} className="scrollbar-hide">
              {previewOpps.map(o=>{
                const meta=oppTypeMeta(o.opportunity_type)
                return <button key={o.id} onClick={()=>{setActiveOpportunityId(o.id);setScreen('opportunity-detail')}} style={{flex:'0 0 250px',background:T.card,border:'1px solid rgba(0,0,0,.05)',borderRadius:16,padding:14,textAlign:'left',cursor:'pointer',fontFamily:'Plus Jakarta Sans',boxShadow:'0 2px 10px rgba(0,0,0,.05)'}}>
                  <div style={{display:'flex',alignItems:'center',gap:9}}><div style={{width:36,height:36,borderRadius:10,background:meta.color+'18',display:'flex',alignItems:'center',justifyContent:'center',fontSize:11,fontWeight:800,color:meta.color}}>{meta.label.slice(0,1)}</div><span style={{fontSize:10,fontWeight:800,color:meta.color,textTransform:'uppercase'}}>{meta.label}</span></div>
                  <div style={{fontSize:13,fontWeight:800,color:T.text,marginTop:12}} className="line-clamp-2">{o.title}</div>
                  <div style={{fontSize:10,color:T.textMuted,marginTop:5}}>{o.organisation?.name || 'Organisation'}</div>
                  {o.application_deadline && <div style={{fontSize:10,color:T.textMuted,marginTop:5}}>Deadline {fmtDeadline(o.application_deadline)}</div>}
                </button>
              })}
            </div>
          </section>
        )}

      </div>
    </div>
  )
}
