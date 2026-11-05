import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../../lib/appApi'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import type { UniversityOption, ProgramOption } from '../../types/academic'
import { setOfflineUserId } from '../../offline/generatedMaterials'
import { cacheAvatar, getCachedAvatar, clearCachedAvatar } from '../../offline/avatarCache'

type EditProfileMe = {
  id?: number | null
  csrf_token: string
  avatar_url?: string | null
  display_name: string | null
  bio: string | null
  university_id: number | null
  program_id: number | null
  year: number | null
  semester: number | null
}

export default function EditProfileScreen({ setScreen }: { setScreen: (s: 'profile') => void }) {
  const { tokens: T } = useTheme()
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
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null)
  const avatarGalleryRef = useRef<HTMLInputElement>(null)
  const avatarCameraRef = useRef<HTMLInputElement>(null)
  const [avatarBusy, setAvatarBusy] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api<EditProfileMe>('/me')
      .then(me => {
        setCsrfToken(me.csrf_token)
        if (me.id) { setOfflineUserId(Number(me.id)); if (me.avatar_url) void cacheAvatar(Number(me.id), me.avatar_url) }
        setAvatarUrl(me.avatar_url || null)
        setForm({
          display_name: me.display_name || '',
          bio: me.bio || '',
          university_id: me.university_id,
          program_id: me.program_id,
          year: me.year,
          semester: me.semester,
        })
      })
      .catch(async () => {
        const id=Number(localStorage.getItem('prepza-offline-user-id')||0)
        if (Number.isInteger(id) && id>0) { const cached=await getCachedAvatar(id); if (cached) setAvatarUrl(cached) }
        setLoadError('Could not load your profile. Check your connection and try again.')
      })
      .finally(() => setLoadingMe(false))
  }, [])

  useEffect(() => {
    api<UniversityOption[]>('/universities').then(setUniversities).catch(() => {})
  }, [])

  useEffect(() => {
    if (form.university_id == null) { setPrograms([]); return }
    api<ProgramOption[]>(`/universities/${form.university_id}/programs`).then(setPrograms).catch(() => {})
  }, [form.university_id])

  const handleAvatarFile = async (file: File) => {
    if (!file.type.startsWith('image/')) { setSaveError('Please choose an image.'); return }
    setAvatarBusy(true); setSaveError('')
    try {
      const bitmap = await createImageBitmap(file)
      const side = Math.min(bitmap.width, bitmap.height)
      const sx = (bitmap.width - side) / 2, sy = (bitmap.height - side) / 2
      const canvas = document.createElement('canvas'); canvas.width = 512; canvas.height = 512
      const ctx = canvas.getContext('2d'); if (!ctx) throw new Error('Image processing is unavailable.')
      ctx.drawImage(bitmap, sx, sy, side, side, 0, 0, 512, 512)
      const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/webp', 0.82))
      if (!blob || blob.size > 512 * 1024) throw new Error('The processed photo is too large. Please choose a smaller image.')
      const prepared = await api<{upload_url:string;storage_path:string}>('/profile/avatar', {
        method:'POST', headers:{'X-CSRF-Token':csrfToken},
        body:JSON.stringify({filename:'avatar.webp',content_type:'image/webp',file_size_bytes:blob.size})
      })
      const upload = await fetch(prepared.upload_url,{method:'PUT',body:blob,headers:{'Content-Type':'image/webp'}})
      if (!upload.ok) throw new Error('Could not upload the photo.')
      const confirmed = await api<{avatar_url:string}>('/profile/avatar/confirm',{
        method:'POST',headers:{'X-CSRF-Token':csrfToken},body:JSON.stringify({storage_path:prepared.storage_path})
      })
      setAvatarUrl(confirmed.avatar_url)
      const id=Number(localStorage.getItem('prepza-offline-user-id')||0)
      if (id>0) void cacheAvatar(id, confirmed.avatar_url)
    } catch(e) { setSaveError(e instanceof ApiError ? e.message : (e instanceof Error ? e.message : 'Could not update photo.')) }
    finally { setAvatarBusy(false) }
  }

  const removeAvatar = async () => {
    setAvatarBusy(true); setSaveError('')
    try { await api('/profile/avatar',{method:'DELETE',headers:{'X-CSRF-Token':csrfToken}}); const id=Number(localStorage.getItem('prepza-offline-user-id')||0); if(id>0) void clearCachedAvatar(id); setAvatarUrl(null) }
    catch(e){setSaveError(e instanceof ApiError ? e.message : 'Could not remove photo.')}
    finally{setAvatarBusy(false)}
  }

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
      window.dispatchEvent(new CustomEvent('prepza:academic-context-changed', { detail: {
        university_id: form.university_id, program_id: form.program_id, year: form.year, semester: form.semester
      }}))
      setSaved(true)
      setTimeout(() => setScreen('profile'), 1000)
    } catch (e) {
      setSaveError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const inputStyle = { width: '100%', border: `1px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card, boxSizing: 'border-box' as const }
  const initials = (form.display_name || 'ST').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()

  if (loadingMe) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: T.pageBg }}>
        <div style={{ color: T.textMuted, fontSize: 14 }}>Loading your profile...</div>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => window.history.back()} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Edit Profile</span>
          <button onClick={handleSave} disabled={saving} style={{ background: saved ? '#4CC97B' : `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 12, padding: '8px 16px', cursor: saving ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 13, color: saved ? '#fff' : N.navy, opacity: saving ? 0.7 : 1 }}>{saved ? '✓ Saved' : saving ? 'Saving...' : 'Save'}</button>
        </div>
      </div>
      {loadError && <div style={{ margin: '14px 20px 0', color: '#C94C4C', fontSize: 12, fontWeight: 600 }}>{loadError}</div>}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '24px 20px 12px' }}>
        <div style={{ position: 'relative', marginBottom: 10 }}>
          {avatarUrl ? <img src={avatarUrl} alt="" style={{ width:80,height:80,borderRadius:'50%',objectFit:'cover',display:'block' }} /> :
            <div style={{ width:80,height:80,background:`linear-gradient(135deg,${N.gold},${N.goldL})`,borderRadius:'50%',display:'flex',alignItems:'center',justifyContent:'center',fontWeight:800,fontSize:28,color:N.navy }}>{initials}</div>}
          <label style={{ position:'absolute',bottom:0,right:0,width:26,height:26,background:N.gold,borderRadius:'50%',border:'2px solid #fff',display:'flex',alignItems:'center',justifyContent:'center',cursor:'pointer',opacity:avatarBusy?.6:1 }}>
            <input ref={avatarGalleryRef} type="file" accept="image/*" disabled={avatarBusy} onChange={e=>{const f=e.target.files?.[0];if(f)void handleAvatarFile(f);e.currentTarget.value=''}} style={{display:'none'}} />
            <div style={{color:T.text}}>{Ic.edit('w-3 h-3')}</div>
          </label>
        </div>
        <input ref={avatarCameraRef} type="file" accept="image/*" capture="environment" disabled={avatarBusy} onChange={e=>{const f=e.target.files?.[0];if(f)void handleAvatarFile(f);e.currentTarget.value=''}} style={{display:'none'}} />
        <div style={{display:'flex',gap:8,alignItems:'center',justifyContent:'center',marginBottom:8}}>
          <button type="button" disabled={avatarBusy} onClick={()=>avatarCameraRef.current?.click()} style={{display:'flex',alignItems:'center',gap:6,border:`1px solid ${T.border}`,background:T.card,color:T.text,padding:'7px 10px',borderRadius:10,cursor:'pointer',fontSize:10,fontWeight:750}}>{Ic.camera('w-4 h-4')} Camera</button>
          <button type="button" disabled={avatarBusy} onClick={()=>avatarGalleryRef.current?.click()} style={{display:'flex',alignItems:'center',gap:6,border:`1px solid ${T.border}`,background:T.card,color:T.text,padding:'7px 10px',borderRadius:10,cursor:'pointer',fontSize:10,fontWeight:750}}>{Ic.gallery('w-4 h-4')} Gallery</button>
        </div>
        <div style={{display:'flex',gap:12,alignItems:'center'}}>
          <div style={{fontSize:12,color:T.textMuted}}>{avatarBusy?'Updating photo…':'Photo is compressed on this device before upload.'}</div>
          {avatarUrl&&<button type="button" onClick={()=>void removeAvatar()} disabled={avatarBusy} style={{border:'none',background:'transparent',color:'#C94C4C',fontWeight:700,fontSize:11}}>Remove</button>}
        </div>
      </div>
      <div style={{ padding: '0 20px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: T.textMuted, marginBottom: 6 }}>Full Name</div>
          <input value={form.display_name} onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))} maxLength={50} style={inputStyle} />
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: T.textMuted, marginBottom: 6 }}>Bio</div>
          <textarea value={form.bio} onChange={e => setForm(f => ({ ...f, bio: e.target.value }))} rows={3} maxLength={160} style={{ ...inputStyle, resize: 'none', lineHeight: 1.6 }} />
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: T.textMuted, marginBottom: 6 }}>University</div>
          <select value={form.university_id ?? ''} onChange={e => setForm(f => ({ ...f, university_id: e.target.value ? Number(e.target.value) : null, program_id: null }))} style={inputStyle}>
            <option value="">Select university</option>
            {universities.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: T.textMuted, marginBottom: 6 }}>Course</div>
          <select value={form.program_id ?? ''} onChange={e => setForm(f => ({ ...f, program_id: e.target.value ? Number(e.target.value) : null }))} disabled={!form.university_id} style={{ ...inputStyle, opacity: form.university_id ? 1 : 0.5 }}>
            <option value="">Select course</option>
            {programs.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: T.textMuted, marginBottom: 6 }}>Year</div>
            <select value={form.year ?? ''} onChange={e => setForm(f => ({ ...f, year: e.target.value ? Number(e.target.value) : null }))} style={inputStyle}>
              <option value="">—</option>
              {[1, 2, 3, 4, 5].map(y => <option key={y} value={y}>Year {y}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: T.textMuted, marginBottom: 6 }}>Semester</div>
            <select value={form.semester ?? ''} onChange={e => setForm(f => ({ ...f, semester: e.target.value ? Number(e.target.value) : null }))} style={inputStyle}>
              <option value="">—</option>
              {[1, 2, 3].map(s => <option key={s} value={s}>Semester {s}</option>)}
            </select>
          </div>
        </div>
        {saveError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600 }}>{saveError}</div>}
        <button onClick={handleSave} disabled={saving} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '14px 0', cursor: saving ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', opacity: saving ? 0.7 : 1 }}>{saving ? 'Saving...' : 'Save Changes'}</button>
      </div>
    </div>
  )
}
