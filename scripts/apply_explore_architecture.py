from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'


def replace_explore(text: str) -> str:
    pattern = r"(?ms)^function ExploreScreen\b.*?(?=^// ─── CREATE MODAL)"
    match = re.search(pattern, text)
    if not match:
        # Explore was already consolidated into the current App architecture.
        # This build-time transform must be idempotent across CI and local builds.
        return text

    new_screen = r'''function ExploreScreen({ setScreen, setActiveGroupId, setActiveDocumentId, setActiveProfileUserId, setActiveProfileName }: { setScreen: (s: Screen) => void; setActiveGroupId: (id: number) => void; setActiveDocumentId: (id: number | null) => void; setActiveProfileUserId?: (id: number) => void; setActiveProfileName?: (name: string) => void }) {
  const { tokens: T } = useTheme()
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('All')
  const [groups, setGroups] = useState<GroupSummary[]>([])
  const [students, setStudents] = useState<ExploreStudent[]>([])
  const [opportunities, setOpportunities] = useState<OpportunityPublic[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')
  const [followBusy, setFollowBusy] = useState<Record<number, boolean>>({})
  const [joiningGroupId, setJoiningGroupId] = useState<number | null>(null)

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
    Promise.all([
      api<{ groups: GroupSummary[] }>('/groups').then(r => r.groups).catch(() => []),
      api<{ students: ExploreStudent[] }>('/students').then(r => r.students).catch(() => []),
      api<{ opportunities: OpportunityPublic[] }>('/opportunities').then(r => r.opportunities).catch(() => []),
    ]).then(([g, s, o]) => {
      setGroups(g)
      setStudents(s)
      setOpportunities(o)
      setLoading(false)
    })
  }, [])

  const matches = (value: string | null | undefined) => !query.trim() || String(value || '').toLowerCase().includes(query.trim().toLowerCase())
  const filteredStudents = students.filter(s => matches(s.display_name) || matches(s.program_name))
  const filteredGroups = groups.filter(g => matches(g.name) || matches(g.unit_code))
  const filteredOpportunities = opportunities.filter(o => matches(o.title) || matches(o.organisation?.name) || matches(o.opportunity_type) || matches(o.location))
  const trendingOpportunities = opportunities.slice(0, 6)

  const toggleFollow = async (s: ExploreStudent) => {
    if (followBusy[s.user_id]) return
    setFollowBusy(b => ({ ...b, [s.user_id]: true }))
    try {
      if (s.is_following) {
        await api(`/users/${s.user_id}/follow`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
        setStudents(list => list.map(x => x.user_id === s.user_id ? { ...x, is_following: false, is_pending: false } : x))
      } else {
        const res = await api<{ status?: string }>(`/users/${s.user_id}/follow`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
        const pending = res.status === 'pending'
        setStudents(list => list.map(x => x.user_id === s.user_id ? { ...x, is_following: !pending, is_pending: pending } : x))
      }
    } catch {}
    setFollowBusy(b => ({ ...b, [s.user_id]: false }))
  }

  const openStudentProfile = (s: ExploreStudent) => {
    setActiveProfileUserId?.(s.user_id)
    setActiveProfileName?.(s.display_name)
    setScreen('student-profile')
  }

  const quickJoin = async (g: GroupSummary) => {
    if (joiningGroupId != null) return
    setJoiningGroupId(g.id)
    try {
      await api(`/groups/${g.id}/join`, { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })
      setGroups(gs => gs.map(x => x.id === g.id ? { ...x, is_member: true, member_count: x.is_member ? x.member_count : x.member_count + 1 } : x))
    } catch {}
    setJoiningGroupId(null)
  }

  const openGroup = (id: number) => { setActiveGroupId(id); setScreen('group-detail') }

  if (loading) return <SkeletonExplore />
  if (error) return <GenerationError error={error} />

  const showOpps = filter === 'All' || filter === 'Opportunities'
  const showStudents = filter === 'All' || filter === 'Students'
  const showGroups = filter === 'All' || filter === 'Groups'

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ fontWeight: 800, fontSize: 20, color: '#fff', marginBottom: 12 }}>Explore</div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', background: 'rgba(255,255,255,0.09)', borderRadius: 13, padding: '10px 14px', border: '1px solid rgba(255,255,255,0.1)' }}>
          <div style={{ color: 'rgba(255,255,255,0.4)' }}>{Ic.search()}</div>
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search opportunities, students..." style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: 13, fontFamily: 'Plus Jakarta Sans' }} />
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 12, overflowX: 'auto', paddingBottom: 2 }} className="scrollbar-hide">
          {['All', 'Opportunities', 'Students', 'Groups'].map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{ flexShrink: 0, padding: '6px 14px', borderRadius: 20, background: filter === f ? N.gold : 'rgba(255,255,255,0.1)', color: filter === f ? N.navy : 'rgba(255,255,255,0.65)', fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{f}</button>
          ))}
        </div>
      </div>

      <div style={{ padding: '20px 18px 32px', display: 'flex', flexDirection: 'column', gap: 24 }}>
        {showOpps && (
          <section>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <div style={{ fontWeight: 800, fontSize: 14, color: T.text }}>🔥 Trending Opportunities</div>
              <button onClick={() => setScreen('opportunities')} style={{ fontSize: 12, fontWeight: 700, color: N.gold, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>See all →</button>
            </div>
            {trendingOpportunities.length === 0 ? <div style={{ fontSize: 12, color: T.textMuted }}>No opportunities available yet.</div> : (
              <div style={{ display: 'flex', gap: 10, overflowX: 'auto' }} className="scrollbar-hide">
                {trendingOpportunities.map(o => {
                  const meta = oppTypeMeta(o.opportunity_type)
                  return <div key={o.id} onClick={() => setScreen('opportunities')} style={{ flexShrink: 0, width: 210, background: T.card, borderRadius: 16, padding: 14, boxShadow: '0 2px 10px rgba(0,0,0,0.06)', cursor: 'pointer' }}>
                    <div style={{ width: 38, height: 38, background: meta.color + '18', borderRadius: 11, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, marginBottom: 10 }}>{meta.icon}</div>
                    <div style={{ fontWeight: 800, fontSize: 12, color: T.text }} className="line-clamp-2">{o.title}</div>
                    <div style={{ fontSize: 10, color: T.textMuted, marginTop: 5 }}>{o.organisation?.name || 'Organisation'}</div>
                  </div>
                })}
              </div>
            )}
          </section>
        )}

        {showOpps && (
          <section>
            <div style={{ fontWeight: 800, fontSize: 14, color: T.text, marginBottom: 12 }}>Opportunities</div>
            {filteredOpportunities.length === 0 ? <div style={{ fontSize: 12, color: T.textMuted }}>No matching opportunities.</div> : filteredOpportunities.slice(0, filter === 'All' ? 4 : 12).map(o => {
              const meta = oppTypeMeta(o.opportunity_type)
              const deadline = fmtDeadline(o.application_deadline)
              return <div key={o.id} onClick={() => setScreen('opportunities')} style={{ background: T.card, borderRadius: 15, padding: '13px 14px', marginBottom: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.04)', cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'center' }}>
                <div style={{ width: 42, height: 42, background: meta.color + '18', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 19, flexShrink: 0 }}>{meta.icon}</div>
                <div style={{ flex: 1, minWidth: 0 }}><div style={{ fontWeight: 700, fontSize: 12, color: T.text }} className="line-clamp-1">{o.title}</div><div style={{ fontSize: 11, color: T.textMuted }}>{o.organisation?.name || 'Unknown organisation'}</div>{deadline && <div style={{ fontSize: 10, color: T.textMuted, marginTop: 2 }}>Deadline · {deadline}</div>}</div>
                <Pill text={meta.label} color={meta.color} />
              </div>
            })}
          </section>
        )}

        {showStudents && (
          <section>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}><div style={{ fontWeight: 800, fontSize: 14, color: T.text }}>👥 Students</div><span style={{ fontSize: 11, color: T.textMuted }}>{filteredStudents.length} found</span></div>
            {filteredStudents.length === 0 ? <div style={{ fontSize: 12, color: T.textMuted }}>No students found.</div> : <div style={{ display: 'flex', gap: 10, overflowX: 'auto' }} className="scrollbar-hide">
              {filteredStudents.slice(0, 12).map(s => {
                const initials = s.display_name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() || 'ST'
                return <div key={s.user_id} style={{ flexShrink: 0, width: 148, background: T.card, borderRadius: 16, padding: '15px 14px', textAlign: 'center', boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
                  <div onClick={() => openStudentProfile(s)} style={{ cursor: 'pointer' }}><div style={{ display: 'flex', justifyContent: 'center', marginBottom: 8 }}><Avi name={initials} size={48} /></div><div style={{ fontWeight: 700, fontSize: 12, color: T.text }} className="line-clamp-1">{s.display_name}</div><div style={{ fontSize: 10, color: T.textMuted }} className="line-clamp-1">{s.program_name || 'Student'}{s.year ? ` · Y${s.year}` : ''}</div></div>
                  <button onClick={() => toggleFollow(s)} disabled={followBusy[s.user_id] || s.is_pending} style={{ marginTop: 10, background: (s.is_following || s.is_pending) ? 'rgba(201,168,76,0.15)' : N.navy, color: N.gold, border: (s.is_following || s.is_pending) ? `1px solid ${N.gold}44` : 'none', borderRadius: 10, padding: '6px 16px', fontSize: 11, fontWeight: 700, cursor: s.is_pending ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: followBusy[s.user_id] ? 0.6 : 1 }}>{followBusy[s.user_id] ? '…' : s.is_pending ? 'Requested' : s.is_following ? 'Following ✓' : 'Follow'}</button>
                </div>
              })}
            </div>}
          </section>
        )}

        {showGroups && (
          <section>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}><div style={{ fontWeight: 800, fontSize: 14, color: T.text }}>👥 Study Groups</div><button onClick={() => setScreen('group-create')} style={{ fontSize: 12, fontWeight: 700, color: N.gold, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>+ Create</button></div>
            {filteredGroups.length === 0 ? <div style={{ fontSize: 12, color: T.textMuted }}>No groups found.</div> : filteredGroups.slice(0, 8).map(g => <div key={g.id} onClick={() => openGroup(g.id)} style={{ background: T.card, borderRadius: 14, padding: 13, marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', cursor: 'pointer' }}><div style={{ width: 42, height: 42, background: `linear-gradient(135deg,${N.navy},${N.navy3})`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 14, color: N.gold }}>{g.name.slice(0, 2).toUpperCase()}</div><div style={{ flex: 1, minWidth: 0 }}><div style={{ fontWeight: 700, fontSize: 12, color: T.text }} className="line-clamp-1">{g.name}</div><div style={{ fontSize: 11, color: T.textMuted }}>{g.member_count} member{g.member_count === 1 ? '' : 's'}</div></div>{g.is_member ? <Pill text="Joined" color="#4CC97B" /> : <button onClick={e => { e.stopPropagation(); quickJoin(g) }} disabled={joiningGroupId === g.id} style={{ background: N.gold, color: N.navy, border: 'none', borderRadius: 9, padding: '6px 12px', fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{joiningGroupId === g.id ? '…' : 'Join'}</button>}</div>)}
          </section>
        )}
      </div>
    </div>
  )
}

'''
    return text[:match.start()] + new_screen + text[match.end():]


if __name__ == '__main__':
    text = APP.read_text(encoding='utf-8')
    transformed = replace_explore(text)
    if transformed == text:
        print('Explore architecture already matches the current App architecture; skipping.')
        raise SystemExit(0)
    APP.write_text(transformed, encoding='utf-8')
    print('Explore architecture applied: study-material discovery removed; opportunities, students, and groups retained.')
