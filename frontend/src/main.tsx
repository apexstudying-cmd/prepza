import React from 'react'
import ReactDOM from 'react-dom/client'
import { installE2EEFetchBridge } from './crypto/e2eeFetchBridge'
import { installNewGroupE2EECreationGuard } from './crypto/newGroupE2EECreationGuard'
import { installStudyAdaFetchGuard } from './crypto/studyAdaFetchGuard'
import App from './App'
import './index.css'

installStudyAdaFetchGuard()
installE2EEFetchBridge()
installNewGroupE2EECreationGuard()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
