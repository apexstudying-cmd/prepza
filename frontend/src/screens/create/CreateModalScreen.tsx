import { N, useTheme } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import Pill from '../../ui/Pill'
import type { Screen } from '../../types/navigation'

export default function CreateModal({ setScreen }: { setScreen: (s: Screen) => void }) {
  const { tokens: T } = useTheme()
  return (
    <div style={{ flex: 1, background: T.pageBg, overflowY: 'auto' }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontWeight: 800, fontSize: 20, color: '#fff' }}>Create</div>
          <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: '#fff' }}>{Ic.close()}</div>
          </button>
        </div>
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {[
          { icon: '📤', label: 'Upload Document', sub: 'PDF, Word, PowerPoint, Images, Notes', action: () => setScreen('upload'), gold: true },
          { icon: '📖', label: 'Publish to Prepza Library', sub: 'Share educational materials · Earn XP', action: () => setScreen('publish-library') },
          { icon: '👥', label: 'Create Group', sub: 'Start a course or study group', action: () => setScreen('group-create') },
          { icon: '🚀', label: 'Share Opportunity', sub: 'Jobs, internships, scholarships, events', action: () => setScreen('share-opp-form') },
        ].map((item, i) => (
          <button key={i} onClick={item.action} style={{ display: 'flex', alignItems: 'center', gap: 14, background: T.card, border: item.gold ? `2px solid ${N.gold}44` : `1px solid ${T.border}`, borderRadius: 16, padding: 16, cursor: 'pointer', textAlign: 'left', boxShadow: item.gold ? `0 4px 20px rgba(201,168,76,0.12)` : '0 2px 8px rgba(0,0,0,0.04)', fontFamily: 'Plus Jakarta Sans' }}>
            <div style={{ width: 50, height: 50, borderRadius: 15, background: item.gold ? `linear-gradient(135deg,${N.gold},${N.goldL})` : `linear-gradient(135deg,${N.navy2},${N.navy3})`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, flexShrink: 0 }}>{item.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 800, fontSize: 14, color: T.text, marginBottom: 3 }}>{item.label}</div>
              <div style={{ fontSize: 12, color: T.textMuted }}>{item.sub}</div>
            </div>
            {item.gold && <Pill text="CORE" />}
          </button>
        ))}
      </div>
    </div>
  )
}
