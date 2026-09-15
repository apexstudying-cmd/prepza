from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.tsx"
text = APP.read_text()
start = text.find("function PublishLibraryScreen(")
if start < 0:
    raise SystemExit("FAIL CLOSED: PublishLibraryScreen anchor not found")
end = text.find("\n}\n\n// ───", start)
if end < 0:
    raise SystemExit("FAIL CLOSED: PublishLibraryScreen end anchor not found")
function = text[start:end + 2]


def replace_once(old, new, label):
    global function
    count = function.count(old)
    if count != 1:
        raise SystemExit(f"FAIL CLOSED: {label}: expected 1 match, found {count}")
    function = function.replace(old, new, 1)

replace_once(
'''type PublishableDoc = { id: number; title: string; status: string; file_type: string | null; page_count: number | null }\n''',
'''type PublishableDoc = { id: number; title: string; status: string; file_type: string | null; page_count: number | null }\ntype LibraryAcademicContext = { university_id: number | null; program_id: number | null; year: number | null; semester: number | null }\n''',
    "publish context type",
)

replace_once(
'''  const [selectedDocId, setSelectedDocId] = useState<number | null>(null)\n  const [title, setTitle] = useState('')\n  const [matType, setMatType] = useState(LIBRARY_MATERIAL_TYPES[0].value)''',
'''  const [selectedDocId, setSelectedDocId] = useState<number | null>(null)\n  const [title, setTitle] = useState('')\n  const [profileContext, setProfileContext] = useState<LibraryAcademicContext>({ university_id: null, program_id: null, year: null, semester: null })\n  const [context, setContext] = useState<LibraryAcademicContext>({ university_id: null, program_id: null, year: null, semester: null })\n  const [universities, setUniversities] = useState<UniversityOption[]>([])\n  const [programs, setPrograms] = useState<ProgramOption[]>([])\n  const [matType, setMatType] = useState(LIBRARY_MATERIAL_TYPES[0].value)''',
    "publish context state",
)

replace_once(
'''  const [submittedStatus, setSubmittedStatus] = useState<string | null>(null)\n\n  useEffect(() => {\n    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})''',
'''  const [submittedStatus, setSubmittedStatus] = useState<string | null>(null)\n  const [profileUpdateState, setProfileUpdateState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')\n\n  useEffect(() => {\n    api<{ csrf_token: string; university_id: number | null; program_id: number | null; year: number | null; semester: number | null }>('/me')\n      .then(me => {\n        setCsrfToken(me.csrf_token)\n        const current = { university_id: me.university_id, program_id: me.program_id, year: me.year, semester: me.semester }\n        setProfileContext(current)\n        setContext(current)\n      })\n      .catch(() => {})\n    api<UniversityOption[]>('/universities').then(setUniversities).catch(() => {})''',
    "publish profile context loading",
)

replace_once(
'''      .finally(() => setDocsLoading(false))\n  }, [activeDocumentId])\n\n  const selectedDoc =''',
'''      .finally(() => setDocsLoading(false))\n  }, [activeDocumentId])\n\n  useEffect(() => {\n    if (context.university_id == null) { setPrograms([]); return }\n    api<ProgramOption[]>(`/universities/${context.university_id}/programs`)\n      .then(setPrograms)\n      .catch(() => setPrograms([]))\n  }, [context.university_id])\n\n  const selectedDoc =''',
    "publish program loading",
)

replace_once(
'''  const canProceed1 = selectedDocId != null && title.trim().length > 0 && selectedDoc?.status === 'ready'\n  const canProceed2 = true\n  const canProceed3 = rightsChecked''',
'''  const canProceed1 = selectedDocId != null && title.trim().length > 0 && selectedDoc?.status === 'ready'\n  const canProceed2 = context.university_id != null && context.program_id != null && context.year != null && context.semester != null\n  const canProceed3 = rightsChecked\n  const contextChangedFromProfile = JSON.stringify(context) !== JSON.stringify(profileContext)''',
    "publish context validation",
)

replace_once(
'''          material_type: matType,\n        }),''',
'''          material_type: matType,\n          university_id: context.university_id,\n          program_id: context.program_id,\n          year: context.year,\n          semester: context.semester,\n        }),''',
    "publish context payload",
)

replace_once(
'''      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">\n          <div style={{ marginBottom: 16 }}>\n            <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 8 }}>Material Type</div>''',
'''      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">\n          <div style={{ background: `${N.gold}10`, border: `1px solid ${N.gold}25`, borderRadius: 14, padding: '14px 16px', marginBottom: 18 }}>\n            <div style={{ fontWeight: 800, fontSize: 13, color: T.text, marginBottom: 4 }}>Where should this document appear?</div>\n            <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.55 }}>Your profile is the default. If you've just moved semester or year, change it here for this document without changing your profile.</div>\n          </div>\n          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 20 }}>\n            <div>\n              <div style={{ fontWeight: 700, fontSize: 12, color: T.textMuted, marginBottom: 6 }}>University</div>\n              <select value={context.university_id ?? ''} onChange={e => setContext(c => ({ ...c, university_id: e.target.value ? Number(e.target.value) : null, program_id: null }))} style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card }}>\n                <option value="">Select university</option>\n                {universities.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}\n              </select>\n            </div>\n            <div>\n              <div style={{ fontWeight: 700, fontSize: 12, color: T.textMuted, marginBottom: 6 }}>Course</div>\n              <select value={context.program_id ?? ''} onChange={e => setContext(c => ({ ...c, program_id: e.target.value ? Number(e.target.value) : null }))} disabled={!context.university_id} style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card, opacity: context.university_id ? 1 : 0.5 }}>\n                <option value="">Select course</option>\n                {programs.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}\n              </select>\n            </div>\n            <div style={{ display: 'flex', gap: 12 }}>\n              <div style={{ flex: 1 }}>\n                <div style={{ fontWeight: 700, fontSize: 12, color: T.textMuted, marginBottom: 6 }}>Year</div>\n                <select value={context.year ?? ''} onChange={e => setContext(c => ({ ...c, year: e.target.value ? Number(e.target.value) : null }))} style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card }}>\n                  <option value="">Select year</option>\n                  {[1, 2, 3, 4, 5, 6, 7, 8].map(y => <option key={y} value={y}>Year {y}</option>)}\n                </select>\n              </div>\n              <div style={{ flex: 1 }}>\n                <div style={{ fontWeight: 700, fontSize: 12, color: T.textMuted, marginBottom: 6 }}>Semester</div>\n                <select value={context.semester ?? ''} onChange={e => setContext(c => ({ ...c, semester: e.target.value ? Number(e.target.value) : null }))} style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card }}>\n                  <option value="">Select semester</option>\n                  {[1, 2].map(s => <option key={s} value={s}>Semester {s}</option>)}\n                </select>\n              </div>\n            </div>\n          </div>\n          <div style={{ marginBottom: 16 }}>\n            <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 8 }}>Material Type</div>''',
    "publish context form",
)

replace_once(
'''          <button onClick={() => canProceed2 && setStep(3)} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>\n            Continue\n          </button>''',
'''          <button onClick={() => canProceed2 && setStep(3)} disabled={!canProceed2} style={{ width: '100%', background: canProceed2 ? `linear-gradient(135deg,${N.gold},${N.goldL})` : '#E5E7EB', color: canProceed2 ? N.navy : T.textMuted, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: canProceed2 ? 'pointer' : 'not-allowed', fontFamily: 'Plus Jakarta Sans' }}>\n            Continue\n          </button>''',
    "publish context continue guard",
)

replace_once(
'''            {[['Type', materialTypeLabel(matType)]].map(([k, v]) => (''',
'''            {[\n              ['University', universities.find(u => u.id === context.university_id)?.name || 'Not selected'],\n              ['Course', programs.find(p => p.id === context.program_id)?.name || 'Not selected'],\n              ['Year', context.year ? `Year ${context.year}` : 'Not selected'],\n              ['Semester', context.semester ? `Semester ${context.semester}` : 'Not selected'],\n              ['Type', materialTypeLabel(matType)],\n            ].map(([k, v]) => (''',
    "publish context review summary",
)

replace_once(
'''          <div style={{ background: T.card, borderRadius: 14, padding: '14px 16px', marginBottom: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>\n            <div style={{ fontSize: 12, fontWeight: 700, color: T.text, marginBottom: 4 }}>What happens if rejected?</div>''',
'''          {contextChangedFromProfile && (\n            <div style={{ background: `${N.gold}10`, border: `1px solid ${N.gold}25`, borderRadius: 14, padding: '14px 16px', marginBottom: 16 }}>\n              <div style={{ fontSize: 12, fontWeight: 800, color: T.text, marginBottom: 5 }}>Your profile is different</div>\n              <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.55, marginBottom: 10 }}>That's okay. This document will use the context you confirmed above. Want Prepza to update your academic profile too?</div>\n              <button\n                disabled={profileUpdateState === 'saving' || profileUpdateState === 'saved'}\n                onClick={async () => {\n                  setProfileUpdateState('saving')\n                  try {\n                    await api('/profile', { method: 'PATCH', headers: { 'X-CSRF-Token': csrfToken }, body: JSON.stringify(context) })\n                    setProfileContext(context)\n                    setProfileUpdateState('saved')\n                  } catch { setProfileUpdateState('error') }\n                }}\n                style={{ background: profileUpdateState === 'saved' ? '#4CC97B' : T.card, border: `1px solid ${profileUpdateState === 'saved' ? '#4CC97B' : N.gold}50`, color: profileUpdateState === 'saved' ? '#fff' : N.gold, borderRadius: 10, padding: '8px 12px', fontSize: 11, fontWeight: 800, cursor: profileUpdateState === 'saving' ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans' }}\n              >{profileUpdateState === 'saving' ? 'Updating…' : profileUpdateState === 'saved' ? 'Profile updated' : profileUpdateState === 'error' ? 'Try again' : 'Update my profile'}</button>\n            </div>\n          )}\n          <div style={{ background: T.card, borderRadius: 14, padding: '14px 16px', marginBottom: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>\n            <div style={{ fontSize: 12, fontWeight: 700, color: T.text, marginBottom: 4 }}>What happens if rejected?</div>''',
    "publish profile update suggestion",
)

text = text[:start] + function + text[end + 2:]
APP.write_text(text)
print("Applied Library publish academic-context UX successfully.")
