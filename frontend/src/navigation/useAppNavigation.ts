import { useEffect, useState } from 'react'

import type { Screen } from '../types/navigation'

export type StoredNavigationState = {
  stack: Screen[]
  activeConversationId: number | null
  activeDocumentId: number | null
  activeGroupId: number | null
  activeProfileUserId: number | null
  activeOpportunityId: number | null
}

function readStoredNavigationState(): StoredNavigationState | null {
  try {
    const raw = sessionStorage.getItem('prepza-navigation-state')
    if (!raw) return null
    const value = JSON.parse(raw)
    if (!value || !Array.isArray(value.stack) || value.stack.length === 0) return null
    return value as StoredNavigationState
  } catch {
    return null
  }
}

export function useAppNavigation({ onResetToLogin }: { onResetToLogin?: () => void } = {}) {
  const [storedNavigation] = useState<StoredNavigationState | null>(() => readStoredNavigationState())
  const [screenStack, setScreenStack] = useState<Screen[]>(() => storedNavigation?.stack || ['splash'])
  const screen = screenStack[screenStack.length - 1]

  const setScreen = (target: Screen) => {
    if (target === screen) return
    setScreenStack(stack => {
      const ancestorIndex = stack.lastIndexOf(target)
      return ancestorIndex >= 0 ? stack.slice(0, ancestorIndex + 1) : [...stack, target]
    })
    window.history.pushState({ prepzaNav: true }, '')
  }

  const resetNavigation = (target: Screen) => {
    if (target === 'login') onResetToLogin?.()
    setScreenStack([target])
    window.history.replaceState({ prepzaNav: true }, window.location.pathname)
  }

  useEffect(() => {
    window.history.replaceState({ prepzaNav: true }, window.location.pathname)
    const onPopState = () => {
      setScreenStack(stack => (stack.length > 1 ? stack.slice(0, -1) : stack))
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  return { storedNavigation, screenStack, screen, setScreen, resetNavigation }
}
