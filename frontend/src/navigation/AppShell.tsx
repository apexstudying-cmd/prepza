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
      <style>{`
        html[data-prepza-theme="dark"] [style*="color: rgb(11, 20, 55)"],
        html[data-prepza-theme="dark"] [style*="color:#0B1437"],
        html[data-prepza-theme="dark"] [style*="color: #0B1437"] { color: #F5F6FA !important; }
        html[data-prepza-theme="dark"] [style*="color: rgb(55, 65, 81)"],
        html[data-prepza-theme="dark"] [style*="color:#374151"],
        html[data-prepza-theme="dark"] [style*="color: #374151"] { color: #D7DBE5 !important; }
        html[data-prepza-theme="dark"] [style*="color: rgb(107, 114, 128)"],
        html[data-prepza-theme="dark"] [style*="color:#6B7280"],
        html[data-prepza-theme="dark"] [style*="color: #6B7280"] { color: #9AA3B8 !important; }
        html[data-prepza-theme="dark"] [style*="color: rgb(156, 163, 175)"],
        html[data-prepza-theme="dark"] [style*="color:#9CA3AF"],
        html[data-prepza-theme="dark"] [style*="color: #9CA3AF"] { color: #AEB7C7 !important; }
        html[data-prepza-theme="dark"] [style*="color: rgb(17, 24, 39)"],
        html[data-prepza-theme="dark"] [style*="color:#111827"],
        html[data-prepza-theme="dark"] [style*="color: #111827"] { color: #F5F6FA !important; }
      `}</style>

      <div style={{ width: '100%', height: '100dvh', background: isDark ? N.navy : (currentThemeMode === 'dark' ? DARK_THEME.pageBg : N.bg), display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          {children}
          <StudentOnboarding screen={screen} setScreen={setScreen} />
          {callEnabled && <CallExperience userId={null} />}
        </div>
        {!noNav.includes(screen) && <BottomNav active={screen} setScreen={setScreen} unreadChats={unreadChats} exploreAttention={exploreAttention} setExploreAttention={setExploreAttention} />}
        {isAdmin && (
          <button aria-label="Open Admin Platform" onClick={onOpenAdmin} style={{ position: 'fixed', bottom: 'calc(68px + env(safe-area-inset-bottom, 0px))', right: 10, color: 'rgba(255,255,255,0.18)', fontSize: 10, fontFamily: 'Plus Jakarta Sans', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 99, padding: '3px 12px', cursor: 'pointer', letterSpacing: '0.5px', zIndex: 200 }}>
            ⚙ Admin Platform
          </button>
        )}
      </div>
    </>
  )
}
