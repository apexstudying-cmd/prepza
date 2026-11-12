import type { ReactNode } from 'react'

import CallExperience from '../crypto/CallExperience'
import StudentOnboarding from '../StudentOnboarding'
import { N, currentThemeMode, DARK_THEME } from '../theme/theme'
import type { Screen } from '../types/navigation'
import BottomNav from './BottomNav'

type AppShellProps = {
  screen: Screen
  setScreen: (screen: Screen) => void
  unreadChats: number
  exploreAttention: boolean
  setExploreAttention: (value: boolean) => void
  isAdmin: boolean
  onOpenAdmin: () => void
  children: ReactNode
}

const noNav: Screen[] = ['splash','login','forgot-password','signup','check-email','complete-profile','reset-password','verify-confirm','upload-share-choice','processing','doc-ready','document-study','document-reader','ai-tutor','flashcards','quiz','podcast-player','podcast-library','summary','opportunity-detail','share-sheet','settings','student-profile','notifications','library','mind-map','new-chat','chat-detail','chat-options','edit-profile','payment','payment-success','payment-failure','payment-history','publish-library','xp-progress','study-streak','study-activity','achievements','time-studied','followers','following','follow-requests','group-detail','group-create']

export default function AppShell({ screen, setScreen, unreadChats, exploreAttention, setExploreAttention, isAdmin, onOpenAdmin, children }: AppShellProps) {
  const isDark = ['splash', 'login', 'processing'].includes(screen)
  const callEnabled = !['splash', 'login', 'forgot-password', 'signup', 'check-email', 'complete-profile', 'reset-password', 'verify-confirm'].includes(screen)

  return (
    <>

      <div style={{ width: '100%', height: '100dvh', background: isDark ? N.navy : (currentThemeMode === 'dark' ? DARK_THEME.pageBg : N.bg), display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          {children}
          <StudentOnboarding screen={screen} setScreen={setScreen} />
          {callEnabled && <CallExperience userId={null} />}
        </div>
        {!noNav.includes(screen) && <BottomNav active={screen} setScreen={setScreen} unreadChats={unreadChats} exploreAttention={exploreAttention} setExploreAttention={setExploreAttention} />}
        {isAdmin && (
          <button onClick={onOpenAdmin} style={{ position: 'fixed', bottom: 10, right: 10, color: 'rgba(255,255,255,0.18)', fontSize: 10, fontFamily: 'Plus Jakarta Sans', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 99, padding: '3px 12px', cursor: 'pointer', letterSpacing: '0.5px', zIndex: 200 }}>
            ⚙ Admin Platform
          </button>
        )}
      </div>
    </>
  )
}
