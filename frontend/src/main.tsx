import React from 'react'
import ReactDOM from 'react-dom/client'
import { installE2EEFetchBridge } from './crypto/e2eeFetchBridge'
import { installDirectChatE2EE } from './crypto/directChatE2EE'
import { ensureE2EEIdentityReady } from './crypto/e2eeChatApi'
import { installNewGroupE2EECreationGuard } from './crypto/newGroupE2EECreationGuard'
import { installStudyAdaFetchGuard } from './crypto/studyAdaFetchGuard'
import { installInChatAdaObserver, default as InChatAdaEnhancer } from './crypto/inChatAdaEnhancer'
import { installDirectInChatAdaObserver, default as DirectInChatAdaEnhancer } from './crypto/directInChatAdaEnhancer'
import { installChatStudyDocumentObserver, default as ChatStudyDocumentReader } from './crypto/chatStudyDocumentReader'
import { installChatRealtime } from './crypto/chatRealtime'
import { installChatSwipeReply } from './crypto/chatSwipeReply'
import { installChatUiPolish } from './crypto/chatUiPolish'
import { installNavigationTransitions } from './crypto/navigationTransitions'
import { installGlobalPullRefresh } from './crypto/globalPullRefresh'
import App from './App'
import './index.css'

class StartupErrorBoundary extends React.Component<React.PropsWithChildren, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[Prepza] frontend render failure', error, info)
    try {
      localStorage.setItem('prepza-last-render-error', JSON.stringify({
        message: error?.message || 'Unknown render error',
        stack: error?.stack || '',
        componentStack: info?.componentStack || '',
        at: Date.now(),
      }))
    } catch {}
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div style={{ minHeight: '100dvh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, background: '#0B1437', color: '#fff', fontFamily: 'system-ui, sans-serif', textAlign: 'center' }}>
        <div style={{ width: '100%', maxWidth: 420 }}>
          <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 10 }}>Prepza could not open</div>
          <div style={{ color: 'rgba(255,255,255,.7)', fontSize: 14, lineHeight: 1.5, marginBottom: 20 }}>The app hit a frontend error. Your account and study data are still on the server.</div>
          <button type="button" onClick={() => window.location.reload()} style={{ border: 0, borderRadius: 10, padding: '11px 18px', background: '#C9A84C', color: '#0B1437', fontWeight: 800 }}>Reload Prepza</button>
        </div>
      </div>
    )
  }
}

function installSafely(name: string, installer: () => void): void {
  try {
    installer()
  } catch (error) {
    console.error(`[Prepza] optional startup module failed: ${name}`, error)
  }
}

const root = ReactDOM.createRoot(document.getElementById('root')!, {
  onUncaughtError: (error, info) => console.error('[Prepza] uncaught React error', error, info),
  onCaughtError: (error, info) => console.error('[Prepza] caught React error', error, info),
  onRecoverableError: (error, info) => console.warn('[Prepza] recoverable React error', error, info),
})

// Render the application before any optional enhancement can execute. A
// navigation, chat, E2EE, or offline enhancement must never be able to prevent
// the core React tree from appearing on a production client.
root.render(
  <React.StrictMode>
    <StartupErrorBoundary>
      <App />
      <InChatAdaEnhancer />
      <DirectInChatAdaEnhancer />
      <ChatStudyDocumentReader />
    </StartupErrorBoundary>
  </React.StrictMode>,
)

// Install integrations after the core tree has been handed to React. Each is
// isolated so one bad enhancement cannot blank the entire application.
installSafely('Study Ada fetch guard', installStudyAdaFetchGuard)
installSafely('E2EE fetch bridge', installE2EEFetchBridge)
installSafely('direct chat E2EE', installDirectChatE2EE)
installSafely('new group E2EE guard', installNewGroupE2EECreationGuard)
installSafely('in-chat Ada observer', installInChatAdaObserver)
installSafely('direct in-chat Ada observer', installDirectInChatAdaObserver)
installSafely('chat study document observer', installChatStudyDocumentObserver)
installSafely('chat realtime', installChatRealtime)
installSafely('chat swipe/reply', installChatSwipeReply)
installSafely('chat UI polish', installChatUiPolish)
installSafely('navigation transitions', installNavigationTransitions)
installSafely('global pull refresh', installGlobalPullRefresh)

// E2EE is automatic: establish this device's identity in the background.
// The private key stays local; only the public key is registered server-side.
void ensureE2EEIdentityReady().catch((error) => console.warn('[Prepza] E2EE identity setup deferred', error))
