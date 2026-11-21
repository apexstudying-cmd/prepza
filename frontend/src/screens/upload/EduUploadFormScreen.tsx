import { useState, type ComponentType } from 'react'

import { N } from '../../theme/theme'
import type { Screen } from '../../types/navigation'

type UploadTopBar = ComponentType<{ title?: string; onBack?: () => void }>

export default function EduUploadFormScreen({ setScreen, TopBar }: { setScreen: (s: Screen) => void; TopBar: UploadTopBar }) {
  const [type, setType] = useState('Notes')
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <TopBar title="Upload Educational Content" onBack={() => window.history.back()} />
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 8 }}>Content Type</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {['Notes','Summary','Guide','Past Paper','Cheat Sheet','Other'].map(t => (
              <button key={t} onClick={() => setType(t)} style={{ padding: '7px 14px', borderRadius: 20, background: type === t ? N.navy : '#F3F4F6', color: type === t ? N.gold : '#6B7280', fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{t}</button>
            ))}
          </div>
        </div>
        {[['Title', 'e.g. ACT 101 Interest Theory – Complete Notes'], ['Unit / Course', 'e.g. ACT 101'], ['University', 'e.g. Kenyatta University']].map(([l, p]) => (
          <div key={l}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>{l}</div>
            <input placeholder={p} style={{ width: '100%', border: '1px solid rgba(0,0,0,0.1)', borderRadius: 12, padding: '12px 14px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: '#374151', boxSizing: 'border-box' }} />
          </div>
        ))}
        <button onClick={() => setScreen('upload')} style={{ background: `linear-gradient(135deg,${N.navy},${N.navy3})`, color: N.gold, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Select & Upload File →</button>
      </div>
    </div>
  )
}
