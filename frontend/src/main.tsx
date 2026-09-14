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

installStudyAdaFetchGuard()
installE2EEFetchBridge()
installDirectChatE2EE()
installNewGroupE2EECreationGuard()
installInChatAdaObserver()
installDirectInChatAdaObserver()
installChatStudyDocumentObserver()
installChatRealtime()
installChatSwipeReply()
installChatUiPolish()
installNavigationTransitions()
installGlobalPullRefresh()

// E2EE is automatic: establish this device's identity in the background.
// The private key stays local; only the public key is registered server-side.
void ensureE2EEIdentityReady().catch(() => undefined)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
    <InChatAdaEnhancer />
    <DirectInChatAdaEnhancer />
    <ChatStudyDocumentReader />
  </React.StrictMode>,
)
