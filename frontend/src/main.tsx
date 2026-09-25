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
import { installChatDraftPersistence } from './crypto/chatDraftPersistence'
import { installNavigationTransitions } from './crypto/navigationTransitions'
import { installGlobalPullRefresh } from './crypto/globalPullRefresh'
import { installOfflineBootstrap } from './offline/bootstrap'
import { installActivityHeartbeat } from './activityHeartbeat'
import App from './App'
import ExternalDocumentImport from './ExternalDocumentImport'
import './index.css'

type BootstrapError = Error & { digest?: string }

class StartupErrorBoundary extends React.Component<React.PropsWithChildren, { error: BootstrapError | null; info: string }> {
  state = { error: null as BootstrapError | null, info: '' }

  static getDerivedStateFromError(error: BootstrapError) {
    return { error }
  }

  componentDidCatch(error: BootstrapError, info: React.ErrorInfo) {
    console.error('[Prepza] frontend render failure', error, info)
    const diagnostic = JSON.stringify({
      message: error?.message || 'Unknown render error',
      stack: error?.stack || '',
      componentStack: info?.componentStack || '',
      digest: error?.digest || '',
      at: Date.now(),
    })
    this.setState({ error, info: info?.componentStack || '' })
    try { localStorage.setItem('prepza-last-render-error', diagnostic) } catch {}
  }

  render() {
    if (!this.state.error) return this.props.children
    const message = this.state.error.message || 'Unknown frontend error'
    const component = this.state.info || 'No component stack available'
    return (
      <div style={{ minHeight: '100dvh', boxSizing: 'border-box', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, background: '#0B1437', color: '#fff', fontFamily: 'system-ui, sans-serif', textAlign: 'center' }}>
        <div style={{ width: '100%', maxWidth: 520 }}>
          <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 10 }}>Prepza could not open</div>
          <div style={{ color: 'rgba(255,255,255,.7)', fontSize: 14, lineHeight: 1.5, marginBottom: 18 }}>The app hit a frontend error. Your account and study data are still on the server.</div>
          <button type="button" onClick={() => window.location.reload()} style={{ border: 0, borderRadius: 10, padding: '11px 18px', background: '#C9A84C', color: '#0B1437', fontWeight: 800 }}>Reload Prepza</button>
          <details style={{ marginTop: 22, textAlign: 'left', color: 'rgba(255,255,255,.72)', fontSize: 11 }}>
            <summary style={{ cursor: 'pointer' }}>Technical details</summary>
            <div style={{ marginTop: 10, padding: 12, background: 'rgba(255,255,255,.06)', borderRadius: 10, overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
              <strong>{message}</strong>{'\n\n'}{component}
            </div>
          </details>
        </div>
      </div>
    )
  }
}

function installSafely(name: string, installer: () => void): void {
  try { installer() } catch (error) { console.error(`[Prepza] optional startup module failed: ${name}`, error) }
}

const root = ReactDOM.createRoot(document.getElementById('root')!, {
  onUncaughtError: (error, info) => console.error('[Prepza] uncaught React error', error, info),
  onCaughtError: (error, info) => console.error('[Prepza] caught React error', error, info),
  onRecoverableError: (error, info) => console.warn('[Prepza] recoverable React error', error, info),
})

root.render(
  <React.StrictMode>
    <StartupErrorBoundary>
      <App />
      <ExternalDocumentImport />
      <InChatAdaEnhancer />
      <DirectInChatAdaEnhancer />
      <ChatStudyDocumentReader />
    </StartupErrorBoundary>
  </React.StrictMode>,
)

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
installSafely('chat draft persistence', installChatDraftPersistence)
installSafely('navigation transitions', installNavigationTransitions)
installSafely('global pull refresh', installGlobalPullRefresh)
installSafely('offline bootstrap', installOfflineBootstrap)
installSafely('active-user heartbeat', installActivityHeartbeat)

void ensureE2EEIdentityReady().catch((error) => console.warn('[Prepza] E2EE identity setup deferred', error))

// Android/Chromium File Handling API: when Prepza is installed and the
// operating system offers "Open with Prepza", forward the selected file to
// the same import surface used by in-app uploads.
try {
  const launchQueueApi = (window as Window & { launchQueue?: { setConsumer: (consumer: (params: { files: FileSystemFileHandle[] }) => void) => void } }).launchQueue
  launchQueueApi?.setConsumer(async ({ files }) => {
    for (const handle of files || []) {
      try {
        const file = await handle.getFile()
        window.dispatchEvent(new CustomEvent('prepza:external-document', { detail: { file } }))
      } catch (error) {
        console.warn('[Prepza] could not read an OS-opened file', error)
      }
    }
  })
} catch (error) {
  console.warn('[Prepza] file-handler registration unavailable', error)
}
