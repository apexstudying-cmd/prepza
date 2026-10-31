import { useEffect, useState } from 'react'

import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import type { UniversityOption, ProgramOption } from '../../types/academic'
import type { GroupPrivacy } from '../../types/groups'
import type { UserSearchResult } from '../../types/users'

// ─── GROUP CREATE ─────────────────────────────────────────────────────────────
type GroupCreateScreenProps = {
  setScreen: (s: 'create-modal' | 'group-detail' | 'home') => void
  setActiveGroupId: (id: number) => void
}

export default function GroupCreateScreen({ setScreen, setActiveGroupId }: GroupCreateScreenProps) {
  const { tokens: T } = useTheme()
  const [step, setStep] = useState(1)
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [privacy, setPrivacy] = useState<'Public' | 'Private' | 'Course-only'>('Public')

  const [universities, setUniversities] = useState<UniversityOption[]>([])
  const [universityId, setUniversityId] = useState<number | null>(null)
  const [programs, setPrograms] = useState<ProgramOption[]>([])
  const [programId, setProgramId] = useState<number | null>(null)
  const [year, setYear] = useState<number | null>(null)

  const [memberSearch, setMemberSearch] = useState('')
  const [candidates, setCandidates] = useState<UserSearchResult[]>([])
  const [selected, setSelected] = useState<UserSearchResult[]>([])
  const [csrfToken, setCsrfToken] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => {
    api<{ csrf_token: string; university_id: number | null }>('/me')
      .then(me => { setCsrfToken(me.csrf_token); if (me.university_id) setUniversityId(me.university_id) })
      .catch(() => {})
    api<UniversityOption[]>('/universities').then(setUniversities).catch(() => {})
  }, [])

  useEffect(() => {
    if (universityId == null) { setPrograms([]); return }
    api<ProgramOption[]>(`/universities/${universityId}/programs`).then(setPrograms).catch(() => setPrograms([]))
  }, [universityId])

  useEffect(() => {
    if (!memberSearch.trim()) { setCandidates([]); return }
    const handle = setTimeout(() => {
      api<{ users: UserSearchResult[] }>(`/users/search?q=${encodeURIComponent(memberSearch.trim())}`)
        .then(res => setCandidates(res.users))
        .catch(() => setCandidates([]))
    }, 300)
    return () => clearTimeout(handle)
  }, [memberSearch])

  const create = async () => {
    if (!name.trim() || creating) return
    setCreating(true); setError('')
    try {
      const privacyValue: GroupPrivacy = privacy === 'Public' ? 'public' : privacy === 'Private' ? 'private' : 'course_only'
      const res = await api<{ id: number }>('/groups', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({
          name: name.trim(),
          description: desc.trim() || undefined,
          privacy: privacyValue,
          university_id: universityId ?? undefined,
          program_id: programId ?? undefined,
          year: year ?? undefined,
          member_user_ids: selected.map(s => s.id),
        }),
      })
      setDone(true)
      setActiveGroupId(res.id)
      setTimeout(() => setScreen('group-detail'), 1400)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not create the group. Please try again.')
    } finally {
      setCreating(false)
    }
  }

  if (done) return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: T.pageBg, gap: 20, padding: '0 28px', textAlign: 'center', animation: 'fadeSlideUp 0.4s ease' }}>
      <div style={{ width: 72, height: 72, background: 'rgba(76,201,123,0.1)', borderRadius: '50%', border: '3px solid #4CC97B', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 28 }}>✓</div>
      <div>
        <div style={{ fontWeight: 800, fontSize: 20, color: T.text, marginBottom: 8 }}>{name} created!</div>
        <div style={{ fontSize: 13, color: T.textMuted }}>Taking you to the group…</div>
      </div>
    </div>
  )

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: step < 3 ? 14 : 0 }}>
          <button onClick={() => step > 1 ? setStep(s => s - 1) : setScreen('create-modal')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div>
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Create Group</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>Step {step} of 3</div>
          </div>
        </div>
        {step < 3 && (
          <div style={{ display: 'flex', gap: 4 }}>
            {[1,2,3].map(s => <div key={s} style={{ flex: 1, height: 3, borderRadius: 99, background: s <= step ? N.gold : 'rgba(255,255,255,0.15)', transition: 'background 0.3s' }} />)}
          </div>
        )}
      </div>

      {step === 1 && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 8 }}>Group name</div>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. ACT 101 — Year 1 · KU" style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, boxSizing: 'border-box' }} />
          </div>
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 8 }}>Description <span style={{ color: T.textMuted, fontWeight: 500 }}>(optional)</span></div>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={3} placeholder="What is this group for?" style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, resize: 'none', lineHeight: 1.6, boxSizing: 'border-box' }} />
          </div>
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 10 }}>Privacy</div>
            {(['Public', 'Private', 'Course-only'] as const).map(p => (
              <div key={p} onClick={() => setPrivacy(p)} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '12px 14px', background: T.card, borderRadius: 12, border: `1.5px solid ${privacy === p ? N.gold : 'rgba(0,0,0,0.08)'}`, marginBottom: 8, cursor: 'pointer', transition: 'border-color 0.2s' }}>
                <div style={{ width: 18, height: 18, borderRadius: '50%', border: `2px solid ${privacy === p ? N.gold : T.textMuted}`, background: privacy === p ? N.gold : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  {privacy === p && <div style={{ width: 6, height: 6, borderRadius: '50%', background: N.navy }} />}
                </div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13, color: T.text }}>{p}</div>
                  <div style={{ fontSize: 11, color: T.textMuted }}>{p === 'Public' ? 'Anyone can find and join' : p === 'Private' ? 'Invite-only, hidden from search' : 'Only students on this course'}</div>
                </div>
              </div>
            ))}
          </div>
          <button onClick={() => name.trim() && setStep(2)} style={{ width: '100%', background: name.trim() ? `linear-gradient(135deg,${N.gold},${N.goldL})` : '#E5E7EB', color: name.trim() ? N.navy : T.textMuted, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: name.trim() ? 'pointer' : 'not-allowed', fontFamily: 'Plus Jakarta Sans' }}>Continue</button>
        </div>
      )}

      {step === 2 && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 8 }}>University <span style={{ color: T.textMuted, fontWeight: 500 }}>(optional)</span></div>
            <select value={universityId ?? ''} onChange={e => { setUniversityId(e.target.value ? Number(e.target.value) : null); setProgramId(null) }} style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card, appearance: 'none', boxSizing: 'border-box' }}>
              <option value="">Any university</option>
              {universities.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          </div>
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 8 }}>Course <span style={{ color: T.textMuted, fontWeight: 500 }}>(optional)</span></div>
            <select value={programId ?? ''} onChange={e => setProgramId(e.target.value ? Number(e.target.value) : null)} disabled={!universityId} style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card, appearance: 'none', boxSizing: 'border-box', opacity: universityId ? 1 : 0.6 }}>
              <option value="">Any course</option>
              {programs.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 8 }}>Year of Study <span style={{ color: T.textMuted, fontWeight: 500 }}>(optional)</span></div>
            <select value={year ?? ''} onChange={e => setYear(e.target.value ? Number(e.target.value) : null)} style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card, appearance: 'none', boxSizing: 'border-box' }}>
              <option value="">Mixed</option>
              {[1,2,3,4,5].map(y => <option key={y} value={y}>Year {y}</option>)}
            </select>
          </div>
          <button onClick={() => setStep(3)} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', marginTop: 8 }}>Continue</button>
        </div>
      )}

      {step === 3 && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '14px 18px 0' }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 10 }}>Add members <span style={{ color: T.textMuted, fontWeight: 500 }}>(optional — you can add later)</span></div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: T.card, border: '1.5px solid rgba(0,0,0,0.1)', borderRadius: 12, padding: '10px 14px', marginBottom: 12 }}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="6" cy="6" r="5" stroke="#9CA3AF" strokeWidth="1.5"/><path d="M10 10l2.5 2.5" stroke="#9CA3AF" strokeWidth="1.5" strokeLinecap="round"/></svg>
              <input value={memberSearch} onChange={e => setMemberSearch(e.target.value)} placeholder="Search students…" style={{ flex: 1, border: 'none', outline: 'none', fontSize: 14, fontFamily: 'Plus Jakarta Sans', color: T.text }} />
            </div>
            {selected.length > 0 && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                {selected.map(s => (
                  <div key={s.id} style={{ background: `${N.gold}20`, borderRadius: 99, padding: '4px 10px 4px 8px', display: 'flex', gap: 5, alignItems: 'center' }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: T.text }}>{s.display_name.split(' ')[0]}</span>
                    <button onClick={() => setSelected(arr => arr.filter(x => x.id !== s.id))} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.textMuted, fontSize: 14, lineHeight: 1, padding: 0 }}>×</button>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '0 18px' }} className="scrollbar-hide">
            {memberSearch.trim() === '' ? (
              <div style={{ fontSize: 12, color: T.textMuted, padding: '14px 0' }}>Search by name to invite classmates.</div>
            ) : candidates.length === 0 ? (
              <div style={{ fontSize: 12, color: T.textMuted, padding: '14px 0' }}>No students match "{memberSearch.trim()}".</div>
            ) : candidates.map(p => {
              const sel = selected.some(s => s.id === p.id)
              return (
                <div key={p.id} onClick={() => setSelected(arr => sel ? arr.filter(x => x.id !== p.id) : [...arr, p])} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '12px 0', borderBottom: '1px solid #F3F4F6', cursor: 'pointer' }}>
                  <div style={{ width: 38, height: 38, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, color: N.navy, flexShrink: 0 }}>{p.display_name.slice(0, 2).toUpperCase()}</div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 13, color: T.text }}>{p.display_name}</div>
                    {p.year != null && <div style={{ fontSize: 11, color: T.textMuted }}>Year {p.year}{p.semester != null ? `, Sem ${p.semester}` : ''}</div>}
                  </div>
                  <div style={{ width: 22, height: 22, borderRadius: 6, border: `2px solid ${sel ? N.gold : T.textMuted}`, background: sel ? N.gold : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 0.2s' }}>
                    {sel && <div style={{ color: T.text }}>{Ic.check('w-3 h-3')}</div>}
                  </div>
                </div>
              )
            })}
          </div>
          <div style={{ padding: '14px 18px 20px', flexShrink: 0 }}>
            {error && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 10 }}>{error}</div>}
            <button onClick={create} disabled={creating} style={{ width: '100%', background: creating ? '#E5E7EB' : `linear-gradient(135deg,${N.gold},${N.goldL})`, color: creating ? T.textMuted : N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: creating ? 'wait' : 'pointer', fontFamily: 'Plus Jakarta Sans', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, boxShadow: creating ? 'none' : `0 6px 24px ${N.gold}40` }}>
              {creating && <div style={{ width: 16, height: 16, border: '2px solid #9CA3AF', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin-slow 0.65s linear infinite' }} />}
              {creating ? 'Creating group…' : `Create Group${selected.length > 0 ? ` with ${selected.length} member${selected.length > 1 ? 's' : ''}` : ''}`}
            </button>
            <button onClick={() => !creating && setScreen('home')} style={{ width: '100%', background: 'transparent', color: T.textMuted, fontSize: 12, fontWeight: 600, border: 'none', padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}
