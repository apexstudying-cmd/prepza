import React, { useState } from 'react'
import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'

export default function ShareOppForm({ setScreen }: { setScreen: (s: 'create-modal' | 'opportunities') => void }) {
  const { tokens: T } = useTheme()
  const [form, setForm] = useState({ title: '', org: '', type: 'Internship', deadline: '', location: '', reward: '', desc: '', link: '' })
  const upd = (k: string) => (e: React.ChangeEvent<HTMLInputElement|HTMLTextAreaElement|HTMLSelectElement>) => setForm(f => ({ ...f, [k]: e.target.value }))
  const inp = (placeholder: string, key: string, type?: string) => (
    <input type={type ?? 'text'} placeholder={placeholder} value={(form as any)[key]} onChange={upd(key)} style={{ width: '100%', border: `1px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card, boxSizing: 'border-box' }} />
  )
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => setScreen('create-modal')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <span style={{ flex: 1, fontWeight: 800, fontSize: 16, color: '#fff' }}>Share Opportunity</span>
          <button onClick={() => setScreen('opportunities')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 13, border: 'none', borderRadius: 12, padding: '8px 18px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Post</button>
        </div>
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
        {[['Title', 'title'], ['Organisation', 'org'], ['Location', 'location'], ['Reward / Stipend (e.g. KES 35,000/mo)', 'reward'], ['Application Link', 'link']].map(([p, k]) => (
          <div key={k}><div style={{ fontSize: 12, fontWeight: 600, color: T.textMuted, marginBottom: 6 }}>{p}</div>{inp(p as string, k as string)}</div>
        ))}
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: T.textMuted, marginBottom: 6 }}>Category</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {['Internship','Scholarship','Competition','Job','Event'].map(c => (
              <button key={c} onClick={() => setForm(f => ({ ...f, type: c }))} style={{ padding: '7px 14px', borderRadius: 20, background: form.type === c ? N.navy : '#F3F4F6', color: form.type === c ? N.gold : T.textMuted, fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{c}</button>
            ))}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: T.textMuted, marginBottom: 6 }}>Deadline</div>
          {inp('e.g. Sep 30, 2025', 'deadline')}
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: T.textMuted, marginBottom: 6 }}>Description</div>
          <textarea value={form.desc} onChange={upd('desc')} placeholder="Describe the opportunity, requirements, and how to apply..." rows={4} style={{ width: '100%', border: `1px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', resize: 'none', outline: 'none', color: T.text, background: T.card, lineHeight: 1.7, boxSizing: 'border-box' }} />
        </div>
      </div>
    </div>
  )
}
