import { Ic } from '../ui/icons'
import { N } from '../theme/theme'
import type { Screen } from '../types/navigation'

export default function BottomNav({ active, setScreen, unreadChats = 0, exploreAttention = false, setExploreAttention }: { active: Screen; setScreen: (s: Screen) => void; unreadChats?: number; exploreAttention?: boolean; setExploreAttention?: (value: boolean) => void }) {
  const isHome = ['home','ai-tutor','opportunities','opportunity-detail','podcast-player','podcast-library','flashcards','quiz','summary','upload','processing','doc-ready','document-study','study-materials','share-sheet','share-opp-form','edu-upload-form','notifications','library','mind-map','document-reader','shop'].includes(active)
  const isExp = active === 'explore' || active === 'student-profile'
  const isChat = active === 'chats' || active === 'chat-detail' || active === 'new-chat' || active === 'chat-options'
  const isProf = active === 'profile' || active === 'settings' || active === 'edit-profile'
  const tabs = [
    { key: 'home' as Screen, icon: Ic.home, label: 'Home', hit: isHome },
    { key: 'explore' as Screen, icon: Ic.explore, label: 'Explore', hit: isExp },
    { key: 'create-modal' as Screen, icon: Ic.plus, label: 'Create', hit: false },
    { key: 'chats' as Screen, icon: Ic.chat, label: 'Chats', hit: isChat },
    { key: 'profile' as Screen, icon: Ic.person, label: 'Profile', hit: isProf },
  ]
  return (
    <div role="navigation" aria-label="Primary navigation" style={{ background: N.navy, borderTop: '1px solid rgba(255,255,255,.07)', display: 'flex', alignItems: 'center', paddingBottom: 6, flexShrink: 0 }}>
      {tabs.map((tab) => {
        const isCta = tab.key === 'create-modal'
        const badge = tab.key === 'chats' ? unreadChats : 0
        const attention = tab.key === 'explore' && exploreAttention
        const handleClick = () => {
          if (tab.key === 'explore') {
            localStorage.setItem('prepza-last-explore-opportunity-id', localStorage.getItem('prepza-latest-explore-opportunity-id') || '0')
            setExploreAttention?.(false)
          }
          setScreen(tab.key)
        }
        return (
          <button type="button" key={tab.key} onClick={handleClick} aria-label={tab.label} aria-current={tab.hit ? 'page' : undefined} style={{ flex: 1, minWidth: 44, minHeight: 44, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, background: 'none', border: 'none', cursor: 'pointer', padding: isCta ? '0 0 4px' : '8px 0 4px', position: 'relative' }}>
            {isCta ? (
              <>
                <div aria-hidden="true" style={{ width: 50, height: 50, borderRadius: '50%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginTop: -22, boxShadow: '0 4px 18px rgba(201,168,76,.55)' }}>
                  <div style={{ color: N.navy }}>{Ic.plus()}</div>
                </div>
                <span style={{ fontSize: 11, fontWeight: 700, color: N.gold, fontFamily: 'Plus Jakarta Sans' }}>Create</span>
              </>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                {tab.hit && <div style={{ position: 'absolute', top: 0, left: '50%', transform: 'translateX(-50%)', width: 18, height: 2, background: N.gold, borderRadius: 2 }} />}
                <div style={{ position: 'relative', color: tab.hit ? N.gold : 'rgba(255,255,255,.70)' }}>
                  {tab.icon()}
                  {badge > 0 && <span aria-label={`${badge} unread messages`} style={{ position: 'absolute', top: -7, right: -10, minWidth: 17, height: 17, padding: '0 4px', borderRadius: 99, background: '#C94C4C', color: '#fff', fontSize: 9, fontWeight: 800, display: 'flex', alignItems: 'center', justifyContent: 'center', border: `2px solid ${N.navy}` }}>{badge > 99 ? '99+' : badge}</span>}
                  {attention && <span aria-label="New opportunities" style={{ position: 'absolute', top: -5, right: -5, width: 8, height: 8, borderRadius: '50%', background: N.goldL, border: `2px solid ${N.navy}`, boxShadow: '0 0 0 4px rgba(232,201,126,.12)' }} />}
                </div>
                <span style={{ fontSize: 11, fontWeight: tab.hit ? 800 : 600, color: tab.hit ? N.gold : 'rgba(255,255,255,.70)', fontFamily: 'Plus Jakarta Sans' }}>{tab.label}</span>
              </div>
            )}
          </button>
        )
      })}
    </div>
  )
}
