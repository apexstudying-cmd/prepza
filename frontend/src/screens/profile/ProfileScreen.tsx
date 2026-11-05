import { useEffect, useState, type ComponentType } from 'react'
import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Pill from '../../ui/Pill'
import { formatStudyTime } from '../../lib/studyTime'
import type { Achievement, AchievementsResponse } from '../../types/achievements'
import type { GamificationSummary, StudyTimeResponse } from '../../types/gamification'
import type { HomeDocument, ProfileMe } from '../../types/profile'
import type { UniversityOption, ProgramOption } from '../../types/academic'

const PROFILE_CACHE: { me?: ProfileMe; uniName?: string | null; programName?: string | null; summary?: GamificationSummary | null; achievementsList?: Achievement[]; weeklyStudySeconds?: number | null } = {}

export default function ProfileScreen({ setScreen, setActiveProfileUserId, setActiveDocumentId, setActiveOpportunityId, onOpenOrgPortal, SkeletonProfile }: { setScreen: (s: 'edit-profile' | 'ambassador' | 'settings' | 'share-sheet' | 'follow-requests' | 'achievements' | 'opportunity-detail' | 'study-activity' | 'document-study' | 'xp-progress' | 'study-materials' | 'followers') => void; setActiveProfileUserId?: (id: number) => void; setActiveDocumentId: (id: number | null) => void; setActiveOpportunityId: (id: number | null) => void; onOpenOrgPortal?: () => void; SkeletonProfile: ComponentType }) {
  const { tokens: T } = useTheme()
  const [tab, setTab] = useState<'saved'|'activity'|'materials'>('activity')
  const [showMenu, setShowMenu] = useState(false)

  const [me, setMe] = useState<ProfileMe | null>(PROFILE_CACHE.me ?? null)
  const [meLoading, setMeLoading] = useState(PROFILE_CACHE.me === undefined)
  const [uniName, setUniName] = useState<string | null>(PROFILE_CACHE.uniName ?? null)
  const [programName, setProgramName] = useState<string | null>(PROFILE_CACHE.programName ?? null)
  const [summary, setSummary] = useState<GamificationSummary | null>(PROFILE_CACHE.summary ?? null)
  const [achievementsList, setAchievementsList] = useState<Achievement[]>(PROFILE_CACHE.achievementsList ?? [])
  const [weeklyStudySeconds, setWeeklyStudySeconds] = useState<number | null>(PROFILE_CACHE.weeklyStudySeconds ?? null)
  const [pendingRequestCount, setPendingRequestCount] = useState(0)
  const [profileTabLoading, setProfileTabLoading] = useState(false)
  const [profileSaved, setProfileSaved] = useState<any[]>([])
  const [profileActivity, setProfileActivity] = useState<any | null>(null)
  const [profileMaterials, setProfileMaterials] = useState<HomeDocument[]>([])
  const [profileTabError, setProfileTabError] = useState('')

  useEffect(() => {
    if (!showMenu) return
    const close = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null
      if (target && !target.closest('[data-prepza-profile-menu]')) setShowMenu(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [showMenu])

  useEffect(() => {
    api<ProfileMe>('/me').then(res => { setMe(res); PROFILE_CACHE.me = res }).catch(() => {}).finally(() => setMeLoading(false))
    api<GamificationSummary>('/gamification/summary').then(res => { setSummary(res); PROFILE_CACHE.summary = res }).catch(() => {})
    api<AchievementsResponse>('/achievements').then(res => { setAchievementsList(res.achievements); PROFILE_CACHE.achievementsList = res.achievements }).catch(() => {})
    api<StudyTimeResponse>('/study-time?period=week').then(res => { setWeeklyStudySeconds(res.total_seconds); PROFILE_CACHE.weeklyStudySeconds = res.total_seconds }).catch(() => {})
    api<{ requests: unknown[] }>('/follow-requests').then(res => setPendingRequestCount(res.requests.length)).catch(() => {})
  }, [])

  useEffect(() => {
    let cancelled = false
    setProfileTabLoading(true)
    setProfileTabError('')
    const load = async () => {
      try {
        if (tab === 'saved') {
          const res = await api<{ saved: any[] }>('/opportunities/saved')
          if (!cancelled) setProfileSaved(res.saved || [])
        } else if (tab === 'activity') {
          const [week, month] = await Promise.all([api<any>('/study-time?period=week'), api<any>('/study-time?period=month')])
          if (!cancelled) setProfileActivity({ week_seconds: week.total_seconds || 0, month_seconds: month.total_seconds || 0 })
        } else {
          const res = await api<{ documents: HomeDocument[] }>('/documents')
          if (!cancelled) setProfileMaterials(res.documents || [])
        }
      } catch (e) {
        if (!cancelled) setProfileTabError(e instanceof ApiError ? e.message : 'Could not load this profile section.')
      } finally {
        if (!cancelled) setProfileTabLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [tab])

  useEffect(() => {
    if (me?.university_id == null) return
    api<UniversityOption[]>('/universities')
      .then(list => { const name = list.find(u => u.id === me.university_id)?.name ?? null; setUniName(name); PROFILE_CACHE.uniName = name })
      .catch(() => {})
    if (me.program_id != null) {
      api<ProgramOption[]>(`/universities/${me.university_id}/programs`)
        .then(list => { const name = list.find(p => p.id === me.program_id)?.name ?? null; setProgramName(name); PROFILE_CACHE.programName = name })
        .catch(() => {})
    }
  }, [me?.university_id, me?.program_id])

  if (meLoading) return <SkeletonProfile />
  const displayName = me?.display_name || 'Student'
  const initials = displayName.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() || 'ST'
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: `linear-gradient(180deg,${N.navy} 0%,${N.navy3} 100%)`, padding: '0 18px 24px' }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
          <div style={{ position: 'relative' }} data-prepza-profile-menu>
            <button type="button" onClick={() => setShowMenu(v => !v)} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.dots()}</div></button>
            {showMenu && (
              <div style={{ position: 'absolute', right: 0, top: 40, background: T.card, borderRadius: 14, boxShadow: '0 8px 24px rgba(0,0,0,0.15)', zIndex: 20, width: 170, overflow: 'hidden' }}>
                {[['Edit Profile', () => { setShowMenu(false); setScreen('edit-profile') }], ['Ambassador Program', () => { setShowMenu(false); setScreen('ambassador') }], ['Organisation Portal', () => { setShowMenu(false); onOpenOrgPortal?.() }], ['Settings', () => { setShowMenu(false); setScreen('settings') }], ['Share Profile', () => { setShowMenu(false); setScreen('share-sheet') }]].map(([label, action]) => (
                  <button key={label as string} onClick={action as () => void} style={{ display: 'block', width: '100%', padding: '13px 16px', background: 'none', border: 'none', textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: T.text, cursor: 'pointer', borderBottom: '1px solid rgba(0,0,0,0.05)' }}>{label as string}</button>
                ))}
              </div>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
          <div style={{ position: 'relative', marginBottom: 14 }}>
            <div style={{ width: 76, height: 76, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 28, color: N.navy, border: `3px solid rgba(201,168,76,0.4)` }}>{initials}</div>
          </div>
          <div style={{ fontWeight: 800, fontSize: 20, color: '#fff', marginBottom: 2 }}>{displayName}</div>
          {programName && <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.55)' }}>{programName}</div>}
          {uniName && <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.35)', marginTop: 2, marginBottom: 14 }}>{uniName}</div>}
          {!programName && !uniName && <div style={{ marginBottom: 14 }} />}
        </div>
      </div>

      {pendingRequestCount > 0 && (
        <button onClick={() => setScreen('follow-requests')} style={{ margin: '14px 14px 0', width: 'calc(100% - 28px)', background: T.card, borderRadius: 14, padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 10, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
          <div style={{ width: 30, height: 30, borderRadius: '50%', background: 'rgba(201,168,76,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, flexShrink: 0 }}>👥</div>
          <div style={{ flex: 1, textAlign: 'left', fontSize: 13, fontWeight: 700, color: T.text }}>Follow requests</div>
          <Pill text={pendingRequestCount.toString()} color={N.gold} />
        </button>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, padding: '14px 14px 0' }}>
        {[
          { label: 'Study', value: summary ? `${summary.current_streak}d` : '—', color: N.gold, dest: 'study-activity' as Screen },
          { label: 'XP', value: summary ? summary.xp_total.toLocaleString() : '—', color: '#4CC97B', dest: 'xp-progress' as Screen },
          { label: 'Docs', value: summary ? String(summary.documents_count) : '—', color: '#4C7BC9', dest: 'study-materials' as Screen },
          { label: 'Followers', value: summary ? String(summary.followers_count) : '—', color: '#9B59B6', dest: 'followers' as Screen },
        ].map(s => (
          <button key={s.label} onClick={() => {
            if (s.dest === 'followers' && me && setActiveProfileUserId) setActiveProfileUserId(me.id)
            setScreen(s.dest)
          }} style={{ background: T.card, borderRadius: 14, padding: '12px 8px', textAlign: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 10, color: T.textMuted, fontWeight: 600 }}>{s.label}</div>
          </button>
        ))}
      </div>

      <div style={{ margin: '14px 14px 0', background: T.card, borderRadius: 16, padding: 14, boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div style={{ fontWeight: 800, fontSize: 13, color: T.text }}>Achievements</div>
          <button onClick={() => setScreen('achievements')} style={{ fontSize: 11, fontWeight: 700, color: N.gold, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>See all</button>
        </div>
        <div style={{ display: 'flex', gap: 14, overflowX: 'auto' }} className="scrollbar-hide">
          {achievementsList.filter(a => a.done).map(a => (
            <button key={a.code} onClick={() => setScreen('achievements')} style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, background: 'none', border: 'none', cursor: 'pointer' }}>
              <div style={{ width: 46, height: 46, background: `${N.gold}18`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, border: `2px solid ${N.gold}33` }}>{a.icon}</div>
              <div style={{ fontSize: 9, color: T.textMuted, textAlign: 'center', maxWidth: 50, lineHeight: 1.3 }}>{a.name}</div>
            </button>
          ))}
        </div>
      </div>

      <div style={{ margin: '14px 14px 0', background: T.card, borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
        <div style={{ display: 'flex', borderBottom: '1px solid rgba(0,0,0,0.06)' }}>
          {(['saved','activity','materials'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{ flex: 1, padding: '11px 0', background: 'none', border: 'none', fontWeight: tab === t ? 800 : 500, fontSize: 11, color: tab === t ? N.navy : '#9CA3AF', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', borderBottom: tab === t ? `2px solid ${N.gold}` : '2px solid transparent' }}>
              {t === 'saved' ? 'Saved' : t === 'activity' ? 'Activity' : 'Materials'}
            </button>
          ))}
        </div>
        <div style={{ padding: 14 }}>
          {profileTabLoading ? <div style={{ padding: '18px 0', textAlign: 'center', color: T.textMuted, fontSize: 12 }}>Loading…</div> : profileTabError ? <div style={{ padding: '18px 0', textAlign: 'center', color: '#B91C1C', fontSize: 12 }}>{profileTabError}</div> : (
            <>
              {tab === 'saved' && (profileSaved.length === 0 ? <div style={{ padding: '18px 0', textAlign:'center', color:T.textMuted, fontSize:12 }}>No saved opportunities yet.</div> : <div style={{display:'flex',flexDirection:'column',gap:8}}>{profileSaved.map((o:any)=><button key={o.id} onClick={()=>{setActiveOpportunityId(o.id);setScreen('opportunity-detail')}} style={{display:'flex',gap:10,alignItems:'center',width:'100%',background:'none',border:'none',padding:'8px 0',textAlign:'left',cursor:'pointer',fontFamily:'Plus Jakarta Sans'}}><div style={{width:34,height:34,borderRadius:10,background:`${N.gold}18`,display:'flex',alignItems:'center',justifyContent:'center',fontWeight:800,color:N.gold}}>{(o.title||'O').slice(0,1).toUpperCase()}</div><div style={{flex:1,minWidth:0}}><div style={{fontSize:12,fontWeight:700,color:T.text}} className="line-clamp-1">{o.title}</div><div style={{fontSize:10,color:T.textMuted}}>{o.organisation?.name || 'Opportunity'}</div></div>{Ic.chevR('w-4 h-4')}</button>)}</div>)}
              {tab === 'activity' && <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:9}}><div style={{background:'#F8F9FC',borderRadius:12,padding:12}}><div style={{fontSize:9,color:T.textMuted}}>THIS WEEK</div><div style={{fontSize:20,fontWeight:800,color:N.navy,marginTop:5}}>{formatStudyTime(profileActivity?.week_seconds || 0)}</div></div><div style={{background:'#F8F9FC',borderRadius:12,padding:12}}><div style={{fontSize:9,color:T.textMuted}}>THIS MONTH</div><div style={{fontSize:20,fontWeight:800,color:N.navy,marginTop:5}}>{formatStudyTime(profileActivity?.month_seconds || 0)}</div></div><button onClick={()=>setScreen('study-activity')} style={{gridColumn:'1 / -1',marginTop:2,padding:11,border:`1px solid ${N.navy}18`,borderRadius:12,background:T.card,color:N.navy,fontWeight:800,fontSize:11,cursor:'pointer'}}>View full study activity</button></div>}
              {tab === 'materials' && (profileMaterials.length === 0 ? <div style={{padding:'18px 0',textAlign:'center',color:T.textMuted,fontSize:12}}>No study materials yet.</div> : <div style={{display:'flex',flexDirection:'column',gap:8}}>{profileMaterials.slice(0,8).map(d=><button key={d.id} onClick={()=>{setActiveDocumentId(d.id);setScreen('document-study')}} style={{display:'flex',gap:10,alignItems:'center',width:'100%',background:'none',border:'none',padding:'7px 0',textAlign:'left',cursor:'pointer',fontFamily:'Plus Jakarta Sans'}}><div style={{width:34,height:34,borderRadius:10,background:'#F3F4F6',display:'flex',alignItems:'center',justifyContent:'center',fontWeight:800,fontSize:11,color:N.navy}}>{(d.file_type||'DOC').toUpperCase().slice(0,3)}</div><div style={{flex:1,minWidth:0}}><div style={{fontSize:12,fontWeight:700,color:T.text}} className="line-clamp-1">{d.title}</div><div style={{fontSize:10,color:T.textMuted}}>{d.status}</div></div>{Ic.chevR('w-4 h-4')}</button>)}</div>)}
            </>
          )}
        </div>
      </div>
      <div style={{ height: 24 }} />
    </div>
  )
}
