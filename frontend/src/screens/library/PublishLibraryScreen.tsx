import { useEffect, useState, type ComponentType } from 'react'
import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import { LIBRARY_MATERIAL_TYPES, materialTypeLabel } from '../../lib/library'
import type { UniversityOption, ProgramOption } from '../../types/academic'
import type { PublishableDoc } from '../../types/library'

type LibraryAcademicContext = { university_id: number | null; program_id: number | null; year: number | null; semester: number | null }
type PublishLibraryScreenProps = {
  setScreen: (screen: 'create-modal' | 'upload' | 'library' | 'home') => void
  activeDocumentId: number | null
  EmptyState: ComponentType<{ icon: string; title: string; sub: string; action?: string; onAction?: () => void }>
}

// ─── PUBLISH TO LIBRARY ───────────────────────────────────────────────────────

export default function PublishLibraryScreen({ setScreen, activeDocumentId, EmptyState }: PublishLibraryScreenProps) {
  const { tokens: T } = useTheme()
  const [step, setStep] = useState(1)

  const [csrfToken, setCsrfToken] = useState('')
  const [docs, setDocs] = useState<PublishableDoc[]>([])
  const [docsLoading, setDocsLoading] = useState(true)
  const [docsError, setDocsError] = useState('')

  const [selectedDocId, setSelectedDocId] = useState<number | null>(null)
  const [title, setTitle] = useState('')
  const [matType, setMatType] = useState(LIBRARY_MATERIAL_TYPES[0].value)
  const [desc, setDesc] = useState('')
  const [rightsChecked, setRightsChecked] = useState(false)

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [submittedStatus, setSubmittedStatus] = useState<string | null>(null)

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
    api<{ documents: { id: number; title: string; status: string; file_type: string | null; page_count: number | null }[] }>('/documents')
      .then(res => {
        const available = res.documents.filter(d => d.status === 'ready' || d.id === activeDocumentId)
        setDocs(available)
        const uploaded = activeDocumentId == null ? null : available.find(d => d.id === activeDocumentId)
        if (uploaded) {
          setSelectedDocId(uploaded.id)
          setTitle(uploaded.title)
        }
      })
      .catch(() => setDocsError('Could not load your documents - check your connection and try again.'))
      .finally(() => setDocsLoading(false))
  }, [activeDocumentId])

  const selectedDoc = selectedDocId == null ? null : docs.find(d => d.id === selectedDocId) || null
  const canProceed1 = selectedDocId != null && title.trim().length > 0 && selectedDoc?.status === 'ready'
  const canProceed2 = true
  const canProceed3 = rightsChecked

  const submit = async () => {
    if (selectedDocId == null) return
    setSubmitting(true)
    setSubmitError('')
    setStep(4)
    try {
      const result = await api<{ publication_id?: number; status?: string; duplicate?: boolean; published?: boolean; message?: string }>('/library/publish', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({
          document_id: selectedDocId,
          title: title.trim(),
          description: desc.trim() || undefined,
          material_type: matType,
        }),
      })
      setSubmittedStatus(result.duplicate ? 'already_in_library' : (result.status || 'pending'))
      setStep(5)
    } catch (e) {
      setSubmitError(e instanceof ApiError ? e.message : 'Something went wrong submitting your material. Please try again.')
      setStep(3)
    } finally {
      setSubmitting(false)
    }
  }

  const stepLabel = ['Select Document', 'Add Details', 'Confirm Rights', '', ''][step - 1]

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      {/* Header */}
      <div style={{ background: N.navy, padding: '0 18px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: step <= 3 ? 14 : 0 }}>
          <button onClick={() => step > 1 && step <= 3 ? setStep(s => s - 1) : setScreen('create-modal')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 17, color: '#fff' }}>Publish to Prepza Library</div>
            {step <= 3 && <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>Step {step} of 3 — {stepLabel}</div>}
          </div>
        </div>
        {step <= 3 && (
          <div style={{ display: 'flex', gap: 4 }}>
            {[1, 2, 3].map(s => (
              <div key={s} style={{ flex: 1, height: 3, borderRadius: 99, background: s <= step ? N.gold : 'rgba(255,255,255,0.15)', transition: 'background 0.3s' }} />
            ))}
          </div>
        )}
      </div>

      {/* Step 1: Select doc + title */}
      {step === 1 && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
          <div style={{ background: `${N.gold}10`, border: `1px solid ${N.gold}30`, borderRadius: 14, padding: '12px 16px', marginBottom: 20 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: N.gold, marginBottom: 4 }}>Free to publish · Shared immediately</div>
            <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.6 }}>Share educational materials with students across Kenya. Once published, students can save them to Study Hub. Reported material can be taken down by admins.</div>
          </div>
          <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 10 }}>Select a document</div>
          {docsLoading ? (
            <div style={{ fontSize: 12, color: T.textMuted, padding: '12px 0' }}>Loading your documents…</div>
          ) : docsError ? (
            <div style={{ fontSize: 12, color: '#C94C4C', fontWeight: 600, padding: '12px 0' }}>{docsError}</div>
          ) : docs.length === 0 ? (
            <EmptyState icon="📄" title="No ready documents" sub="Upload and finish processing a document before publishing it to the library." action="Upload Document" onAction={() => setScreen('upload')} />
          ) : docs.map(d => (
            <div key={d.id} onClick={() => { setSelectedDocId(d.id); setTitle(d.title) }}
              style={{ background: T.card, borderRadius: 14, padding: '14px 16px', marginBottom: 10, border: `2px solid ${selectedDocId === d.id ? N.gold : 'rgba(0,0,0,0.06)'}`, cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'center', boxShadow: selectedDocId === d.id ? `0 4px 16px ${N.gold}20` : '0 2px 8px rgba(0,0,0,0.04)', transition: 'all 0.2s' }}>
              <div style={{ width: 40, height: 44, background: '#F3F4F6', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <svg width="20" height="24" viewBox="0 0 20 24" fill="none"><path d="M4 0h8l8 8v16H4V0z" fill="#E5E7EB"/><path d="M12 0l8 8h-8V0z" fill="#D1D5DB"/><rect x="6" y="12" width="8" height="1.5" rx="0.75" fill="#9CA3AF"/><rect x="6" y="15" width="6" height="1.5" rx="0.75" fill="#9CA3AF"/><rect x="6" y="18" width="7" height="1.5" rx="0.75" fill="#9CA3AF"/></svg>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.title}</div>
                <div style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>
                  {(d.file_type || '').toUpperCase()}{d.page_count != null ? ` · ${d.page_count} pages` : ''}{d.status !== 'ready' ? ` · ${d.status === 'processing' ? 'Preparing…' : d.status}` : ''}
                </div>
              </div>
              {selectedDocId === d.id && <div style={{ color: N.gold, flexShrink: 0 }}>{Ic.check('w-5 h-5')}</div>}
            </div>
          ))}
          <div style={{ marginTop: 8, marginBottom: 20 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 8 }}>Publication title</div>
            <input value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. ACT 101 Lecture Notes – Semester 1" maxLength={200} style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, boxSizing: 'border-box' }} />
            <div style={{ fontSize: 11, color: T.textMuted, marginTop: 6 }}>This will be the public title visible to other students.</div>
          </div>
          <button onClick={() => canProceed1 && setStep(2)} style={{ width: '100%', background: canProceed1 ? `linear-gradient(135deg,${N.gold},${N.goldL})` : '#E5E7EB', color: canProceed1 ? N.navy : T.textMuted, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: canProceed1 ? 'pointer' : 'not-allowed', fontFamily: 'Plus Jakarta Sans' }}>
            {selectedDoc?.status === 'ready' ? 'Continue' : 'Document still preparing…'}
          </button>
        </div>
      )}

      {/* Step 2: Details */}
      {step === 2 && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 8 }}>Material Type</div>
            <select value={matType} onChange={e => setMatType(e.target.value)} style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card, appearance: 'none' }}>
              {LIBRARY_MATERIAL_TYPES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 8 }}>Description <span style={{ color: T.textMuted, fontWeight: 500 }}>(optional)</span></div>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={3} maxLength={1000} placeholder="What does this material cover? Who is it useful for?" style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, resize: 'none', lineHeight: 1.6, boxSizing: 'border-box' }} />
          </div>
          <button onClick={() => canProceed2 && setStep(3)} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
            Continue
          </button>
        </div>
      )}

      {/* Step 3: Rights confirmation */}
      {step === 3 && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
          <div style={{ background: T.card, borderRadius: 16, padding: '18px 18px', marginBottom: 16, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
            <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 12 }}>Publishing: {title}</div>
            {[['Type', materialTypeLabel(matType)]].map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #F3F4F6' }}>
                <span style={{ fontSize: 12, color: T.textMuted }}>{k}</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: T.text, maxWidth: 180, textAlign: 'right' }}>{v}</span>
              </div>
            ))}
          </div>
          <div style={{ background: '#FEF9F0', border: '1px solid rgba(201,168,76,0.25)', borderRadius: 14, padding: '16px 16px', marginBottom: 20 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: '#92400E', marginBottom: 8 }}>Content responsibility</div>
            <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.75 }}>
              You are responsible for ensuring you have the right or permission to share this material. Prepza does not claim ownership of student-uploaded content. Unauthorised sharing of copyrighted materials may result in removal of the content and restrictions on your account.
            </div>
          </div>
          {submitError && (
            <div style={{ background: 'rgba(201,68,68,0.08)', border: '1px solid rgba(201,68,68,0.25)', borderRadius: 12, padding: '12px 14px', color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 16 }}>{submitError}</div>
          )}
          <div onClick={() => setRightsChecked(r => !r)} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', padding: '14px 16px', background: T.card, borderRadius: 14, border: `2px solid ${rightsChecked ? N.gold : 'rgba(0,0,0,0.08)'}`, cursor: 'pointer', marginBottom: 16, transition: 'border-color 0.2s' }}>
            <div style={{ width: 22, height: 22, borderRadius: 6, border: `2px solid ${rightsChecked ? N.gold : T.textMuted}`, background: rightsChecked ? N.gold : T.card, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, transition: 'all 0.2s' }}>
              {rightsChecked && <div style={{ color: T.text }}>{Ic.check('w-3 h-3')}</div>}
            </div>
            <div style={{ fontSize: 13, color: T.text, lineHeight: 1.6 }}>I confirm that I have the right or permission to share this material, and I agree to Prepza's <span style={{ color: N.gold, fontWeight: 700 }}>Terms of Service</span>, <span style={{ color: N.gold, fontWeight: 700 }}>Content Policy</span>, and <span style={{ color: N.gold, fontWeight: 700 }}>Copyright Policy</span>.</div>
          </div>
          <button onClick={() => canProceed3 && !submitting && submit()} style={{ width: '100%', background: canProceed3 ? `linear-gradient(135deg,${N.gold},${N.goldL})` : '#E5E7EB', color: canProceed3 ? N.navy : T.textMuted, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: canProceed3 ? 'pointer' : 'not-allowed', fontFamily: 'Plus Jakarta Sans', boxShadow: canProceed3 ? `0 6px 24px ${N.gold}40` : 'none' }}>
            Publish to Library
          </button>
          <button onClick={() => setScreen('home')} style={{ width: '100%', background: 'transparent', color: T.textMuted, fontSize: 12, fontWeight: 600, border: 'none', padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Cancel — don't publish</button>
        </div>
      )}

      {/* Step 4: Submitting */}
      {step === 4 && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 20, padding: '0 32px', textAlign: 'center' }}>
          <div style={{ width: 72, height: 72, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ width: 28, height: 28, border: '3px solid rgba(11,20,55,0.4)', borderTopColor: N.navy, borderRadius: '50%', animation: 'spin-slow 0.7s linear infinite' }} />
          </div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 18, color: T.text, marginBottom: 6 }}>Submitting…</div>
            <div style={{ fontSize: 13, color: T.textMuted }}>Uploading to Prepza Library</div>
          </div>
        </div>
      )}

      {/* Step 5: Published */}
      {step === 5 && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px 20px' }} className="scrollbar-hide">
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <div style={{ width: 72, height: 72, background: submittedStatus === 'already_in_library' ? `${N.gold}18` : 'rgba(76,201,123,0.1)', borderRadius: '50%', border: `3px solid ${submittedStatus === 'already_in_library' ? N.gold : '#4CC97B'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px', fontSize: 28 }}>{submittedStatus === 'already_in_library' ? '✓' : '📥'}</div>
            <div style={{ fontWeight: 800, fontSize: 20, color: T.text, marginBottom: 8 }}>{submittedStatus === 'already_in_library' ? 'Already in Prepza Library' : 'Published to Prepza Library'}</div>
            <div style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.65 }}>
              {submittedStatus === 'already_in_library'
                ? 'This exact document is already represented in the Prepza Library. Your personal StudyHub copy remains yours, and no duplicate Library submission was created.'
                : 'Your material is now in the Prepza Library. Other students can see it and save it to Study Hub. If it is later reported and found unsuitable, an admin can take it down.'}
            </div>
          </div>

          <div style={{ background: T.card, borderRadius: 14, padding: '14px 16px', marginBottom: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.text, marginBottom: 4 }}>Library moderation</div>
            <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.65 }}>Students can report a published document when it is inaccurate, inappropriate, plagiarised, or not appropriate for their academic context. Admins review reports and can remove the item.</div>
          </div>

          <button onClick={() => setScreen('library')} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: `0 6px 24px ${N.gold}40` }}>
            Go to My Library
          </button>
          <button onClick={() => setScreen('home')} style={{ width: '100%', background: 'transparent', color: T.textMuted, fontSize: 12, fontWeight: 600, border: 'none', padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Back to Home</button>
        </div>
      )}
    </div>
  )
}

// ─── END PUBLISH LIBRARY SCREEN ───────────────────────────────────────────────
