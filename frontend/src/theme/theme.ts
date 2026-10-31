import { useEffect, useState } from 'react'

export const N = { navy: '#0B1437', navy2: '#132046', navy3: '#1A2A5E', gold: '#C9A84C', goldL: '#E8C97E', bg: '#F8F9FC' }

export type ThemeTokens = { pageBg: string; card: string; text: string; textMuted: string; border: string }
const LIGHT_THEME: ThemeTokens = { pageBg: '#F8F9FC', card: '#FFFFFF', text: '#0B1437', textMuted: '#596579', border: 'rgba(0,0,0,0.05)' }
export const DARK_THEME: ThemeTokens = { pageBg: '#0A0E1A', card: '#132046', text: '#F5F6FA', textMuted: '#9AA3B8', border: 'rgba(255,255,255,0.08)' }
export type ThemeMode = 'light' | 'dark'
const THEME_STORAGE_KEY = 'prepza-theme'
export let currentThemeMode: ThemeMode = (typeof window !== 'undefined' && (window.localStorage.getItem(THEME_STORAGE_KEY) as ThemeMode)) || 'light'
const themeListeners = new Set<() => void>()
function applyThemeDocument(mode: ThemeMode) {
  if (typeof document === 'undefined') return
  const theme = mode === 'dark' ? DARK_THEME : LIGHT_THEME
  const root = document.documentElement
  root.dataset.prepzaTheme = mode

  // Generation screens live in their own module, but share the same theme
  // source. Update variables on the document root so a theme toggle updates
  // those screens immediately without introducing a second React theme store.
  root.style.setProperty('--prepza-generation-color-scheme', mode)
  root.style.setProperty('--prepza-generation-text', theme.text)
  root.style.setProperty('--prepza-generation-page', theme.pageBg)
  root.style.setProperty('--prepza-generation-card', theme.card)
  root.style.setProperty('--prepza-generation-muted', mode === 'dark' ? '#AAB4C8' : '#596579')
  root.style.setProperty('--prepza-generation-border', mode === 'dark' ? '#2A3654' : '#E1E5ED')
}
function setThemeMode(next: ThemeMode) {
  currentThemeMode = next
  applyThemeDocument(next)
  try { window.localStorage.setItem(THEME_STORAGE_KEY, next) } catch { /* private browsing etc */ }
  themeListeners.forEach(fn => fn())
}
applyThemeDocument(currentThemeMode)
function toggleThemeMode() {
  setThemeMode(currentThemeMode === 'light' ? 'dark' : 'light')
}
export function useTheme() {
  const [, forceRerender] = useState(0)
  useEffect(() => {
    const listener = () => forceRerender(n => n + 1)
    themeListeners.add(listener)
    return () => { themeListeners.delete(listener) }
  }, [])
  return { mode: currentThemeMode, tokens: currentThemeMode === 'dark' ? DARK_THEME : LIGHT_THEME, toggleTheme: toggleThemeMode }
}
