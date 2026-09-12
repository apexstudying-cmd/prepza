import React from 'react'
import ReactDOM from 'react-dom/client'
import { installE2EEFetchBridge } from './crypto/e2eeFetchBridge'
import { installDirectChatE2EE } from './crypto/directChatE2EE'
import { installNewGroupE2EECreationGuard } from './crypto/newGroupE2EECreationGuard'
import { installStudyAdaFetchGuard } from './crypto/studyAdaFetchGuard'
import { installInChatAdaObserver, default as InChatAdaEnhancer } from './crypto/inChatAdaEnhancer'
import { installDirectInChatAdaObserver, default as DirectInChatAdaEnhancer } from './crypto/directInChatAdaEnhancer'
import { installChatStudyDocumentObserver, default as ChatStudyDocumentReader } from './crypto/chatStudyDocumentReader'
import App from './App'
import './index.css'

installStudyAdaFetchGuard()
installE2EEFetchBridge()
installDirectChatE2EE()
installNewGroupE2EECreationGuard()
installInChatAdaObserver()
installDirectInChatAdaObserver()
installChatStudyDocumentObserver()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
    <InChatAdaEnhancer />
    <DirectInChatAdaEnhancer />
    <ChatStudyDocumentReader />
  </React.StrictMode>,
)
