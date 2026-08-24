"""
Chunk 2 patch: wires HomeScreen, ProfileScreen, EditProfileScreen, and
SettingsScreen in frontend/src/App.tsx to the real backend, replacing
mock data with GET /me, GET /gamification/summary, GET /documents,
GET /universities, GET /universities/:id/programs, PATCH /profile, and
DELETE /delete-account.

Every replacement is assert-guarded: if the expected original text
isn't found exactly once, the script stops and changes nothing.

Run from the project root:
    cd ~/Desktop/prepza
    python chunk2_patch.py

Then review with:
    git diff frontend/src/App.tsx
"""
import io

PATH = "frontend/src/App.tsx"

with io.open(PATH, encoding="utf-8", newline="") as f:
    src = f.read()

original_src = src


def apply(label, old, new):
    global src
    count = src.count(old)
    assert count == 1, (
        f"[{label}] expected exactly 1 occurrence, found {count}. "
        f"File may have drifted - aborting without changes."
    )
    src = src.replace(old, new, 1)
    print(f"  ok: {label}")


print("Applying Chunk 2 patches...")

# ─────────────────────────────────────────────────────────────────────────
# 1. HomeScreen: real greeting, real documents, real streak/XP
# ─────────────────────────────────────────────────────────────────────────

apply(
    "HomeScreen signature + state",
    """function HomeScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [notifCount] = useState(3)
  const loading = useLoading(1200)
  if (loading) return <SkeletonHome />
  return (""",
    """type HomeDocument = { id: number; title: string; status: string; file_type: string | null; page_count: number | null; created_at: string | null }
type GamificationSummary = { xp_total: number; level: number; level_title: string; current_streak: number; longest_streak: number; documents_count: number; followers_count: number }

function HomeScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [notifCount] = useState(3)
  const loading = useLoading(1200)

  const [displayName, setDisplayName] = useState<string | null>(null)
  const [documents, setDocuments] = useState<HomeDocument[]>([])
  const [docsLoading, setDocsLoading] = useState(true)
  const [summary, setSummary] = useState<GamificationSummary | null>(null)

  useEffect(() => {
    api<{ display_name: string | null }>('/me')
      .then(me => setDisplayName(me.display_name))
      .catch(() => {})
    api<{ documents: HomeDocument[] }>('/documents')
      .then(res => setDocuments(res.documents))
      .catch(() => {})
      .finally(() => setDocsLoading(false))
    api<GamificationSummary>('/gamification/summary')
      .then(setSummary)
      .catch(() => {})
  }, [])

  const greetingName = displayName || 'there'
  const activeDocs = documents.filter(d => !docsLoading)
  const featuredDoc = activeDocs[0]
  const restDocs = activeDocs.slice(1)

  if (loading) return <SkeletonHome />
  return (""",
)

apply(
    "HomeScreen greeting name",
    """              <div style={{ color: '#fff', fontSize: 17, fontWeight: 800, letterSpacing: '-0.3px' }}>Arnold 👋</div>""",
    """              <div style={{ color: '#fff', fontSize: 17, fontWeight: 800, letterSpacing: '-0.3px' }}>{greetingName} 👋</div>""",
)

apply(
    "HomeScreen streak banner",
    """        <div style={{ background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.22)', borderRadius: 14, padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 20 }}>🔥</span>
          <div style={{ flex: 1 }}>
            <div style={{ color: N.gold, fontWeight: 800, fontSize: 13 }}>7-Day Streak — Keep it up!</div>
            <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11 }}>Study 30 mins today to extend it</div>
          </div>
          <Pill text="+25 XP" color={N.gold} />
        </div>""",
    """        <div style={{ background: 'rgba(201,168,76,0.1)', border: '1px solid rgba(201,168,76,0.22)', borderRadius: 14, padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 20 }}>🔥</span>
          <div style={{ flex: 1 }}>
            <div style={{ color: N.gold, fontWeight: 800, fontSize: 13 }}>
              {summary ? `${summary.current_streak}-Day Streak${summary.current_streak > 0 ? ' — Keep it up!' : ''}` : 'Loading streak...'}
            </div>
            <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11 }}>Study 30 mins today to extend it</div>
          </div>
          {summary && <Pill text={`${summary.xp_total.toLocaleString()} XP`} color={N.gold} />}
        </div>""",
)

apply(
    "HomeScreen Continue Studying section (documents)",
    """          {/* Featured doc */}
          <div onClick={() => setScreen('document-study')} style={{ background: `linear-gradient(135deg,${N.navy},${N.navy3})`, borderRadius: 18, padding: 18, cursor: 'pointer', position: 'relative', overflow: 'hidden', marginBottom: 10 }}>
            <div style={{ position: 'absolute', right: -20, top: -20, width: 120, height: 120, background: 'rgba(201,168,76,0.07)', borderRadius: '50%' }} />
            <div style={{ display: 'flex', gap: 14, alignItems: 'center', marginBottom: 14 }}>
              <div style={{ width: 48, height: 48, background: 'rgba(201,168,76,0.15)', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, color: N.gold, fontWeight: 800 }}>∑</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 800, fontSize: 14, color: '#fff' }}>ACT 101 – Actuarial Mathematics</div>
                <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', marginTop: 2 }}>Ch.3 – Interest Theory & Annuities</div>
              </div>
            </div>
            <Bar pct={52} />
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
              <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>52% complete</span>
              <button onClick={e => { e.stopPropagation(); setScreen('document-study') }} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 11, border: 'none', borderRadius: 10, padding: '6px 14px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Continue →</button>
            </div>
          </div>
          {/* Other docs */}
          {studyDocs.slice(1).map(d => (
            <div key={d.id} onClick={() => setScreen('document-study')} style={{ background: '#fff', borderRadius: 14, padding: '12px 14px', marginBottom: 8, boxShadow: '0 2px 10px rgba(0,0,0,0.05)', display: 'flex', gap: 12, alignItems: 'center', cursor: 'pointer', border: '1px solid rgba(0,0,0,0.04)' }}>
              <div style={{ width: 40, height: 40, background: d.color + '18', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, color: d.color, fontWeight: 800 }}>{d.icon}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 12, color: N.navy }} className="line-clamp-1">{d.subject}</div>
                <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 6 }} className="line-clamp-1">{d.chapter}</div>
                <Bar pct={d.progress} color={d.color} />
              </div>
              <div style={{ fontSize: 12, fontWeight: 800, color: d.color, flexShrink: 0 }}>{d.progress}%</div>
            </div>
          ))}""",
    """          {docsLoading ? (
            <div style={{ fontSize: 12, color: '#9CA3AF', padding: '12px 0' }}>Loading your documents...</div>
          ) : !featuredDoc ? (
            <div onClick={() => setScreen('upload')} style={{ background: '#fff', borderRadius: 14, padding: '18px 16px', textAlign: 'center', cursor: 'pointer', border: '1px dashed rgba(0,0,0,0.15)' }}>
              <div style={{ fontSize: 12, color: '#6B7280', fontWeight: 600 }}>No documents yet — upload one to get started 📤</div>
            </div>
          ) : (
            <>
              {/* Featured doc */}
              <div onClick={() => setScreen('document-study')} style={{ background: `linear-gradient(135deg,${N.navy},${N.navy3})`, borderRadius: 18, padding: 18, cursor: 'pointer', position: 'relative', overflow: 'hidden', marginBottom: 10 }}>
                <div style={{ position: 'absolute', right: -20, top: -20, width: 120, height: 120, background: 'rgba(201,168,76,0.07)', borderRadius: '50%' }} />
                <div style={{ display: 'flex', gap: 14, alignItems: 'center', marginBottom: 14 }}>
                  <div style={{ width: 48, height: 48, background: 'rgba(201,168,76,0.15)', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, color: N.gold, fontWeight: 800 }}>📄</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 800, fontSize: 14, color: '#fff' }} className="line-clamp-1">{featuredDoc.title}</div>
                    <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', marginTop: 2, textTransform: 'capitalize' }}>{featuredDoc.status}</div>
                  </div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <button onClick={e => { e.stopPropagation(); setScreen('document-study') }} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 11, border: 'none', borderRadius: 10, padding: '6px 14px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Continue →</button>
                </div>
              </div>
              {/* Other docs */}
              {restDocs.map(d => (
                <div key={d.id} onClick={() => setScreen('document-study')} style={{ background: '#fff', borderRadius: 14, padding: '12px 14px', marginBottom: 8, boxShadow: '0 2px 10px rgba(0,0,0,0.05)', display: 'flex', gap: 12, alignItems: 'center', cursor: 'pointer', border: '1px solid rgba(0,0,0,0.04)' }}>
                  <div style={{ width: 40, height: 40, background: N.gold + '18', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, color: N.gold, fontWeight: 800 }}>📄</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 12, color: N.navy }} className="line-clamp-1">{d.title}</div>
                    <div style={{ fontSize: 11, color: '#6B7280', textTransform: 'capitalize' }}>{d.status}</div>
                  </div>
                </div>
              ))}
            </>
          )}""",
)

# ─────────────────────────────────────────────────────────────────────────
# 2. ProfileScreen: real name/uni/course header + real stats
# ─────────────────────────────────────────────────────────────────────────

apply(
    "ProfileScreen signature + state",
    """function ProfileScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [tab, setTab] = useState<'posts'|'saved'|'activity'|'materials'>('posts')
  const [showMenu, setShowMenu] = useState(false)
  const [showAvatarPicker, setShowAvatarPicker] = useState(false)
  const loading = useLoading(900)
  if (loading) return <SkeletonProfile />
  const stats = [
    { label: 'Streak', value: '7🔥', color: N.gold },
    { label: 'XP', value: '1,240', color: '#4CC97B' },
    { label: 'Docs', value: '8', color: '#4C7BC9' },
    { label: 'Followers', value: '23', color: '#9B59B6' },
  ]
  return (""",
    """type ProfileMe = { display_name: string | null; bio: string | null; university_id: number | null; program_id: number | null }

function ProfileScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [tab, setTab] = useState<'posts'|'saved'|'activity'|'materials'>('posts')
  const [showMenu, setShowMenu] = useState(false)
  const [showAvatarPicker, setShowAvatarPicker] = useState(false)
  const loading = useLoading(900)

  const [me, setMe] = useState<ProfileMe | null>(null)
  const [uniName, setUniName] = useState<string | null>(null)
  const [programName, setProgramName] = useState<string | null>(null)
  const [summary, setSummary] = useState<GamificationSummary | null>(null)

  useEffect(() => {
    api<ProfileMe>('/me').then(setMe).catch(() => {})
    api<GamificationSummary>('/gamification/summary').then(setSummary).catch(() => {})
  }, [])

  useEffect(() => {
    if (me?.university_id == null) return
    api<UniversityOption[]>('/universities')
      .then(list => setUniName(list.find(u => u.id === me.university_id)?.name ?? null))
      .catch(() => {})
    if (me.program_id != null) {
      api<ProgramOption[]>(`/universities/${me.university_id}/programs`)
        .then(list => setProgramName(list.find(p => p.id === me.program_id)?.name ?? null))
        .catch(() => {})
    }
  }, [me?.university_id, me?.program_id])

  if (loading) return <SkeletonProfile />
  const displayName = me?.display_name || 'Student'
  const initials = displayName.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() || 'ST'
  return (""",
)

apply(
    "ProfileScreen avatar initials + name/course/uni header",
    """            <div style={{ width: 76, height: 76, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 28, color: N.navy, border: `3px solid rgba(201,168,76,0.4)` }}>AG</div>
            <button onClick={() => setShowAvatarPicker(true)} style={{ position: 'absolute', bottom: 0, right: 0, width: 22, height: 22, background: N.gold, borderRadius: '50%', border: `2px solid ${N.navy}`, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <div style={{ color: N.navy }}>{Ic.edit('w-3 h-3')}</div>
            </button>
          </div>
          <div style={{ fontWeight: 800, fontSize: 20, color: '#fff', marginBottom: 2 }}>{USER.name}</div>
          <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.55)' }}>{USER.course} · {USER.year}</div>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.35)', marginTop: 2, marginBottom: 14 }}>{USER.uni}</div>""",
    """            <div style={{ width: 76, height: 76, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 28, color: N.navy, border: `3px solid rgba(201,168,76,0.4)` }}>{initials}</div>
            <button onClick={() => setShowAvatarPicker(true)} style={{ position: 'absolute', bottom: 0, right: 0, width: 22, height: 22, background: N.gold, borderRadius: '50%', border: `2px solid ${N.navy}`, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
              <div style={{ color: N.navy }}>{Ic.edit('w-3 h-3')}</div>
            </button>
          </div>
          <div style={{ fontWeight: 800, fontSize: 20, color: '#fff', marginBottom: 2 }}>{displayName}</div>
          {programName && <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.55)' }}>{programName}</div>}
          {uniName && <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.35)', marginTop: 2, marginBottom: 14 }}>{uniName}</div>}
          {!programName && !uniName && <div style={{ marginBottom: 14 }} />}""",
)

apply(
    "ProfileScreen stats grid (real gamification numbers)",
    """      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, padding: '14px 14px 0' }}>
        {[
          { label: 'Streak', value: '12🔥', color: N.gold, dest: 'study-streak' as Screen },
          { label: 'XP', value: '1,240', color: '#4CC97B', dest: 'xp-progress' as Screen },
          { label: 'Docs', value: '8', color: '#4C7BC9', dest: 'library' as Screen },
          { label: 'Followers', value: '143', color: '#9B59B6', dest: 'followers' as Screen },
        ].map(s => (""",
    """      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, padding: '14px 14px 0' }}>
        {[
          { label: 'Streak', value: summary ? `${summary.current_streak}🔥` : '—', color: N.gold, dest: 'study-streak' as Screen },
          { label: 'XP', value: summary ? summary.xp_total.toLocaleString() : '—', color: '#4CC97B', dest: 'xp-progress' as Screen },
          { label: 'Docs', value: summary ? String(summary.documents_count) : '—', color: '#4C7BC9', dest: 'library' as Screen },
          { label: 'Followers', value: summary ? String(summary.followers_count) : '—', color: '#9B59B6', dest: 'followers' as Screen },
        ].map(s => (""",
)

# ─────────────────────────────────────────────────────────────────────────
# 3. EditProfileScreen: real load + real PATCH /profile save
# ─────────────────────────────────────────────────────────────────────────

apply(
    "EditProfileScreen full rewrite",
    """function EditProfileScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [form, setForm] = useState({ name: USER.name, bio: 'Actuarial Science student at KU. Passionate about mathematics and finance.', uni: USER.uni, course: USER.course, year: USER.year })
  const [saved, setSaved] = useState(false)
  const upd = (k: string) => (e: React.ChangeEvent<HTMLInputElement|HTMLTextAreaElement>) => setForm(f => ({ ...f, [k]: e.target.value }))
  const handleSave = () => { setSaved(true); setTimeout(() => setScreen('profile'), 1000) }
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Edit Profile</span>
          <button onClick={handleSave} style={{ background: saved ? '#4CC97B' : `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 12, padding: '8px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 13, color: saved ? '#fff' : N.navy }}>{saved ? '✓ Saved' : 'Save'}</button>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '24px 20px 12px' }}>
        <div style={{ position: 'relative', marginBottom: 20 }}>
          <div style={{ width: 80, height: 80, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 28, color: N.navy }}>AG</div>
          <div style={{ position: 'absolute', bottom: 0, right: 0, width: 26, height: 26, background: N.gold, borderRadius: '50%', border: '2px solid #fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: N.navy }}>{Ic.edit('w-3 h-3')}</div>
          </div>
        </div>
        <div style={{ fontSize: 12, color: '#9CA3AF', cursor: 'pointer' }}>Change photo</div>
      </div>
      <div style={{ padding: '0 20px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        {[['Full Name','name',form.name],['University','uni',form.uni],['Course','course',form.course],['Year','year',form.year]].map(([label,key,val]) => (
          <div key={key}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>{label}</div>
            <input value={val} onChange={upd(key)} style={{ width: '100%', border: '1px solid rgba(0,0,0,0.1)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, boxSizing: 'border-box' }} />
          </div>
        ))}
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>Bio</div>
          <textarea value={form.bio} onChange={upd('bio')} rows={3} style={{ width: '100%', border: '1px solid rgba(0,0,0,0.1)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, resize: 'none', lineHeight: 1.6, boxSizing: 'border-box' }} />
        </div>
        <button onClick={handleSave} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Save Changes</button>
      </div>
    </div>
  )
}""",
    """type EditProfileMe = { display_name: string | null; bio: string | null; year: number | null; semester: number | null; university_id: number | null; program_id: number | null; csrf_token: string }

function EditProfileScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [csrfToken, setCsrfToken] = useState('')
  const [loadingMe, setLoadingMe] = useState(true)
  const [loadError, setLoadError] = useState('')

  const [form, setForm] = useState({
    display_name: '', bio: '',
    university_id: null as number | null, program_id: null as number | null,
    year: null as number | null, semester: null as number | null,
  })

  const [universities, setUniversities] = useState<UniversityOption[]>([])
  const [programs, setPrograms] = useState<ProgramOption[]>([])

  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api<EditProfileMe>('/me')
      .then(me => {
        setCsrfToken(me.csrf_token)
        setForm({
          display_name: me.display_name || '',
          bio: me.bio || '',
          university_id: me.university_id,
          program_id: me.program_id,
          year: me.year,
          semester: me.semester,
        })
      })
      .catch(() => setLoadError('Could not load your profile. Check your connection and try again.'))
      .finally(() => setLoadingMe(false))
  }, [])

  useEffect(() => {
    api<UniversityOption[]>('/universities').then(setUniversities).catch(() => {})
  }, [])

  useEffect(() => {
    if (form.university_id == null) { setPrograms([]); return }
    api<ProgramOption[]>(`/universities/${form.university_id}/programs`).then(setPrograms).catch(() => {})
  }, [form.university_id])

  const handleSave = async () => {
    setSaving(true)
    setSaveError('')
    try {
      await api('/profile', {
        method: 'PATCH',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({
          display_name: form.display_name.trim() || null,
          bio: form.bio.trim() || null,
          university_id: form.university_id,
          program_id: form.program_id,
          year: form.year,
          semester: form.semester,
        }),
      })
      setSaved(true)
      setTimeout(() => setScreen('profile'), 1000)
    } catch (e) {
      setSaveError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const inputStyle = { width: '100%', border: '1px solid rgba(0,0,0,0.1)', borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: N.navy, boxSizing: 'border-box' as const }
  const initials = (form.display_name || 'ST').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()

  if (loadingMe) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: N.bg }}>
        <div style={{ color: '#9CA3AF', fontSize: 14 }}>Loading your profile...</div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('profile')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Edit Profile</span>
          <button onClick={handleSave} disabled={saving} style={{ background: saved ? '#4CC97B' : `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 12, padding: '8px 16px', cursor: saving ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 13, color: saved ? '#fff' : N.navy, opacity: saving ? 0.7 : 1 }}>{saved ? '✓ Saved' : saving ? 'Saving...' : 'Save'}</button>
        </div>
      </div>
      {loadError && <div style={{ margin: '14px 20px 0', color: '#C94C4C', fontSize: 12, fontWeight: 600 }}>{loadError}</div>}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '24px 20px 12px' }}>
        <div style={{ position: 'relative', marginBottom: 20 }}>
          <div style={{ width: 80, height: 80, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 28, color: N.navy }}>{initials}</div>
          <div style={{ position: 'absolute', bottom: 0, right: 0, width: 26, height: 26, background: N.gold, borderRadius: '50%', border: '2px solid #fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: N.navy }}>{Ic.edit('w-3 h-3')}</div>
          </div>
        </div>
        <div style={{ fontSize: 12, color: '#9CA3AF' }}>Change photo (coming soon)</div>
      </div>
      <div style={{ padding: '0 20px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>Full Name</div>
          <input value={form.display_name} onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))} maxLength={50} style={inputStyle} />
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>Bio</div>
          <textarea value={form.bio} onChange={e => setForm(f => ({ ...f, bio: e.target.value }))} rows={3} maxLength={160} style={{ ...inputStyle, resize: 'none', lineHeight: 1.6 }} />
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>University</div>
          <select value={form.university_id ?? ''} onChange={e => setForm(f => ({ ...f, university_id: e.target.value ? Number(e.target.value) : null, program_id: null }))} style={inputStyle}>
            <option value="">Select university</option>
            {universities.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>Course</div>
          <select value={form.program_id ?? ''} onChange={e => setForm(f => ({ ...f, program_id: e.target.value ? Number(e.target.value) : null }))} disabled={!form.university_id} style={{ ...inputStyle, opacity: form.university_id ? 1 : 0.5 }}>
            <option value="">Select course</option>
            {programs.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>Year</div>
            <select value={form.year ?? ''} onChange={e => setForm(f => ({ ...f, year: e.target.value ? Number(e.target.value) : null }))} style={inputStyle}>
              <option value="">—</option>
              {[1, 2, 3, 4].map(y => <option key={y} value={y}>Year {y}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>Semester</div>
            <select value={form.semester ?? ''} onChange={e => setForm(f => ({ ...f, semester: e.target.value ? Number(e.target.value) : null }))} style={inputStyle}>
              <option value="">—</option>
              {[1, 2].map(s => <option key={s} value={s}>Semester {s}</option>)}
            </select>
          </div>
        </div>
        {saveError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600 }}>{saveError}</div>}
        <button onClick={handleSave} disabled={saving} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '14px 0', cursor: saving ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: saving ? 0.7 : 1 }}>{saving ? 'Saving...' : 'Save Changes'}</button>
      </div>
    </div>
  )
}""",
)

# ─────────────────────────────────────────────────────────────────────────
# 4. SettingsScreen: real email, real uni/course, delete account
# ─────────────────────────────────────────────────────────────────────────

apply(
    "SettingsScreen signature + state",
    """function SettingsScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [notifs, setNotifs] = useState({ push: true, messages: true, opportunities: false, community: true, reminders: true })
  const [priv, setPriv] = useState({ profilePublic: true, whoMessages: false, whoFollows: true })
  const [showLogout, setShowLogout] = useState(false)
  const [showModal, setShowModal] = useState<string|null>(null)""",
    """function SettingsScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [notifs, setNotifs] = useState({ push: true, messages: true, opportunities: false, community: true, reminders: true })
  const [priv, setPriv] = useState({ profilePublic: true, whoMessages: false, whoFollows: true })
  const [showLogout, setShowLogout] = useState(false)
  const [showModal, setShowModal] = useState<string|null>(null)

  const [csrfToken, setCsrfToken] = useState('')
  const [email, setEmail] = useState('')
  const [uniName, setUniName] = useState<string | null>(null)
  const [programName, setProgramName] = useState<string | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  useEffect(() => {
    api<{ email: string; csrf_token: string; university_id: number | null; program_id: number | null }>('/me')
      .then(me => {
        setCsrfToken(me.csrf_token)
        setEmail(me.email)
        if (me.university_id != null) {
          api<UniversityOption[]>('/universities')
            .then(list => setUniName(list.find(u => u.id === me.university_id)?.name ?? null))
            .catch(() => {})
        }
        if (me.university_id != null && me.program_id != null) {
          api<ProgramOption[]>(`/universities/${me.university_id}/programs`)
            .then(list => setProgramName(list.find(p => p.id === me.program_id)?.name ?? null))
            .catch(() => {})
        }
      })
      .catch(() => {})
  }, [])

  const handleDeleteAccount = async () => {
    setDeleting(true)
    setDeleteError('')
    try {
      await api('/delete-account', { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
      setScreen('login')
    } catch (e) {
      setDeleteError(e instanceof ApiError ? e.message : 'Could not delete your account. Please try again.')
      setDeleting(false)
    }
  }""",
)

apply(
    "SettingsScreen Account section rows (real email/uni/course)",
    """        <Section title="Account">
          <Row label="Edit Profile" sub="Name, photo, bio" onPress={() => setScreen('edit-profile')} />
          <Row label="Email" sub="arnold@students.ku.ac.ke" onPress={() => setShowModal('email')} />
          <Row label="Phone" sub="+254 *** *** **89" onPress={() => setShowModal('phone')} />
          <Row label="University" sub="Kenyatta University" onPress={() => setShowModal('university')} />
          <Row label="Course" sub="Actuarial Science · Year 1" onPress={() => setShowModal('course')} />
        </Section>""",
    """        <Section title="Account">
          <Row label="Edit Profile" sub="Name, photo, bio" onPress={() => setScreen('edit-profile')} />
          <Row label="Email" sub={email || 'Loading...'} onPress={() => setShowModal('email')} />
          <Row label="Phone" sub="+254 *** *** **89" onPress={() => setShowModal('phone')} />
          <Row label="University" sub={uniName || 'Not set'} onPress={() => setScreen('edit-profile')} />
          <Row label="Course" sub={programName || 'Not set'} onPress={() => setScreen('edit-profile')} />
        </Section>""",
)

apply(
    "SettingsScreen add Delete Account row after Log Out",
    """        <div style={{ margin: '8px 16px 0', background: '#fff', borderRadius: 16, overflow: 'hidden' }}>
          <Row label="Log Out" danger onPress={() => setShowLogout(true)} right={<div style={{ color: '#C94C4C' }}>{Ic.logout()}</div>} />
        </div>
      </div>""",
    """        <div style={{ margin: '8px 16px 0', background: '#fff', borderRadius: 16, overflow: 'hidden' }}>
          <Row label="Log Out" danger onPress={() => setShowLogout(true)} right={<div style={{ color: '#C94C4C' }}>{Ic.logout()}</div>} />
        </div>
        <div style={{ margin: '10px 16px 0', background: '#fff', borderRadius: 16, overflow: 'hidden' }}>
          <Row label="Delete Account" sub="Permanently delete your account and data" danger onPress={() => setShowDeleteConfirm(true)} />
        </div>
      </div>""",
)

apply(
    "SettingsScreen add Delete Account confirmation modal (after logout modal)",
    """          <button onClick={() => setShowLogout(false)} style={{ width: '100%', background: '#F3F4F6', border: 'none', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 14, color: '#374151' }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── FORGOT PASSWORD ──────────────────────────────────────────────────────────""",
    """          <button onClick={() => setShowLogout(false)} style={{ width: '100%', background: '#F3F4F6', border: 'none', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 14, color: '#374151' }}>Cancel</button>
          </div>
        </div>
      )}

      {/* Delete account confirmation */}
      {showDeleteConfirm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 99 }}>
          <div style={{ background: '#fff', borderRadius: 20, padding: 24, width: '100%' }}>
            <div style={{ fontSize: 32, textAlign: 'center', marginBottom: 12 }}>⚠️</div>
            <div style={{ fontWeight: 800, fontSize: 17, color: N.navy, textAlign: 'center', marginBottom: 8 }}>Delete your account?</div>
            <div style={{ fontSize: 13, color: '#6B7280', textAlign: 'center', marginBottom: 16 }}>This permanently deletes your account and cannot be undone. Your uploaded documents and study history will be lost.</div>
            {deleteError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, textAlign: 'center', marginBottom: 12 }}>{deleteError}</div>}
            <button onClick={handleDeleteAccount} disabled={deleting} style={{ width: '100%', background: '#C94C4C', border: 'none', borderRadius: 14, padding: '14px 0', cursor: deleting ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 14, color: '#fff', marginBottom: 10, opacity: deleting ? 0.7 : 1 }}>{deleting ? 'Deleting...' : 'Yes, Delete My Account'}</button>
            <button onClick={() => { setShowDeleteConfirm(false); setDeleteError('') }} disabled={deleting} style={{ width: '100%', background: '#F3F4F6', border: 'none', borderRadius: 14, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 14, color: '#374151' }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── FORGOT PASSWORD ──────────────────────────────────────────────────────────""",
)

assert src != original_src, "No changes were made - something is wrong."

with io.open(PATH, "w", encoding="utf-8", newline="") as f:
    f.write(src)

print("\nAll Chunk 2 patches applied successfully.")
print("\nNext steps:")
print("  cd ~/Desktop/prepza")
print("  git diff frontend/src/App.tsx")
print("  cd frontend && npx tsc --noEmit")
