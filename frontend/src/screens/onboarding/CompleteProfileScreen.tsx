import { useEffect, useState } from 'react'
import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import type { UniversityOption, ProgramOption } from '../../types/academic'

// ─── COMPLETE PROFILE (lands here after a first-time Google Sign-In) ──────────
export default function CompleteProfileScreen({ setScreen }: { setScreen: (s: 'login' | 'home') => void }) {
  const { tokens: T } = useTheme()
  const steps = ['University', 'Course', 'Year', 'Semester']
  const [step, setStep] = useState(0)
  const [data, setData] = useState({
    university_id: null as number | null, university_name: '',
    program_id: null as number | null, program_name: '',
    year: null as number | null, semester: null as number | null,
  })
  const [csrfToken, setCsrfToken] = useState('')
  const [loadingMe, setLoadingMe] = useState(true)

  const [universities, setUniversities] = useState<UniversityOption[]>([])
  const [loadingUniversities, setLoadingUniversities] = useState(true)
  const [uniSearch, setUniSearch] = useState('')

  const [programs, setPrograms] = useState<ProgramOption[]>([])
  const [loadingPrograms, setLoadingPrograms] = useState(false)
  const [courseSearch, setCourseSearch] = useState('')

  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Confirms there's an actual logged-in session (this screen is only ever
  // reached via the /auth/google/callback redirect) and grabs the CSRF
  // token PATCH /profile requires. Pre-fills anything already set, in case
  // this is a re-visit rather than the very first sign-in.
  useEffect(() => {
    api<{ university_id: number | null; program_id: number | null; year: number | null; semester: number | null; csrf_token: string }>('/me')
      .then(me => {
        setCsrfToken(me.csrf_token)
        setData(d => ({ ...d, university_id: me.university_id, program_id: me.program_id, year: me.year, semester: me.semester }))
      })
      .catch(() => setScreen('login'))
      .finally(() => setLoadingMe(false))
  }, [])

  useEffect(() => {
    api<UniversityOption[]>('/universities')
      .then(setUniversities)
      .catch(() => setError('Could not load the university list. Check your connection and try again.'))
      .finally(() => setLoadingUniversities(false))
  }, [])

  useEffect(() => {
    if (data.university_id == null) { setPrograms([]); return }
    setLoadingPrograms(true)
    api<ProgramOption[]>(`/universities/${data.university_id}/programs`)
      .then(setPrograms)
      .catch(() => setError('Could not load courses for that university.'))
      .finally(() => setLoadingPrograms(false))
  }, [data.university_id])

  const goBack = () => { setError(''); setStep(s => Math.max(0, s - 1)) }
  const advance = () => { setError(''); setStep(s => s + 1) }

  const filteredUniversities = universities.filter(u => u.name.toLowerCase().includes(uniSearch.toLowerCase()))
  const filteredPrograms = programs.filter(p => p.name.toLowerCase().includes(courseSearch.toLowerCase()))

  const handleFinish = async (overrides: Partial<typeof data> = {}) => {
    const payload = { ...data, ...overrides }
    setSubmitting(true)
    setError('')
    try {
      await api('/profile', {
        method: 'PATCH',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({
          university_id: payload.university_id,
          program_id: payload.program_id,
          year: payload.year,
          semester: payload.semester,
        }),
      })
      window.dispatchEvent(new CustomEvent('prepza:academic-context-changed', { detail: {
        university_id: payload.university_id, program_id: payload.program_id, year: payload.year, semester: payload.semester
      }}))
      setScreen('home')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const inputStyle = { width: '100%', boxSizing: 'border-box' as const, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 14, padding: '13px 16px', color: '#fff', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', marginBottom: 12 }
  const optionStyle = (selected: boolean) => ({ background: selected ? 'rgba(201,168,76,0.2)' : 'rgba(255,255,255,0.08)', border: `1px solid ${selected ? N.gold + '55' : 'rgba(255,255,255,0.1)'}`, borderRadius: 14, padding: '14px 18px', color: '#fff', fontWeight: 600, fontSize: 14, cursor: 'pointer', textAlign: 'left' as const, fontFamily: 'Plus Jakarta Sans' })

  if (loadingMe) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: `linear-gradient(170deg,${N.navy} 0%,${N.navy2} 60%,${N.bg} 100%)` }}>
        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 14 }}>Loading your account...</div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: `linear-gradient(170deg,${N.navy} 0%,${N.navy2} 60%,${N.bg} 100%)` }}>
      <div style={{ padding: '20px 24px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          {step > 0 && <button onClick={goBack} style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, padding: '8px 10px', color: '#fff', cursor: 'pointer' }}>{Ic.back('w-4 h-4')}</button>}
          <div style={{ flex: 1, background: 'rgba(255,255,255,0.12)', borderRadius: 99, height: 4 }}>
            <div style={{ width: `${((step + 1) / steps.length) * 100}%`, height: '100%', background: N.gold, borderRadius: 99, transition: 'width 0.3s' }} />
          </div>
          <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12, fontWeight: 600 }}>{step + 1}/{steps.length}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 20 }}>
          <img src="/icon-192.png" alt="Prepza" style={{ width: 56, height: 56, borderRadius: 16 }} />
        </div>
      </div>
      <div style={{ flex: 1, padding: '0 24px 32px', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div style={{ fontWeight: 800, fontSize: 26, color: '#fff', marginBottom: 6 }}>Finish setting up</div>
        <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 13, marginBottom: 20 }}>Just a few details left to personalise your Prepza experience</div>

        {error && (
          <div style={{ background: 'rgba(140,29,43,0.25)', border: '1px solid rgba(140,29,43,0.5)', borderRadius: 12, padding: '10px 14px', color: '#ffb4bd', fontSize: 13, marginBottom: 16 }}>{error}</div>
        )}

        {step === 0 && (
          <>
            <input value={uniSearch} onChange={e => setUniSearch(e.target.value)} placeholder="Type to search your university..." style={inputStyle} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1, overflowY: 'auto', minHeight: 0 }} className="scrollbar-hide">
              {loadingUniversities ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>Loading universities...</div>
              ) : filteredUniversities.length === 0 ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>University not found. Prepza doesn't have your university yet - try a different search, or check back soon.</div>
              ) : filteredUniversities.map(u => (
                <button key={u.id} onClick={() => { setData(d => ({ ...d, university_id: u.id, university_name: u.name, program_id: null, program_name: '' })); setCourseSearch(''); advance() }}
                  style={optionStyle(data.university_id === u.id)}>{u.name}</button>
              ))}
            </div>
          </>
        )}

        {step === 1 && (
          <>
            <input value={courseSearch} onChange={e => setCourseSearch(e.target.value)} placeholder="Type to search your course..." style={inputStyle} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1, overflowY: 'auto', minHeight: 0 }} className="scrollbar-hide">
              {loadingPrograms ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>Loading courses...</div>
              ) : programs.length === 0 ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>No courses listed yet for {data.university_name}. Check back soon - we're adding more universities regularly.</div>
              ) : filteredPrograms.length === 0 ? (
                <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>Course not found for {data.university_name}. Try a different search.</div>
              ) : filteredPrograms.map(p => (
                <button key={p.id} onClick={() => { setData(d => ({ ...d, program_id: p.id, program_name: p.name })); advance() }}
                  style={optionStyle(data.program_id === p.id)}>{p.name}</button>
              ))}
            </div>
          </>
        )}

        {step === 2 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[1, 2, 3, 4, 5].map(y => (
              <button key={y} onClick={() => { setData(d => ({ ...d, year: y })); advance() }} style={optionStyle(data.year === y)}>Year {y}</button>
            ))}
          </div>
        )}

        {step === 3 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[1, 2, 3].map(s => (
              <button key={s} disabled={submitting} onClick={() => { setData(d => ({ ...d, semester: s })); handleFinish({ semester: s }) }} style={optionStyle(data.semester === s)}>Semester {s}</button>
            ))}
            {submitting && <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginTop: 8 }}>Saving...</div>}
          </div>
        )}
      </div>
    </div>
  )
}
