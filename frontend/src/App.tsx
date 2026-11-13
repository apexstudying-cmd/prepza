// @ts-nocheck
import { useState, useEffect, useRef, type ChangeEvent } from 'react'

import { api, ApiError } from './lib/appApi'
import { N, useTheme } from './theme/theme'
import { Ic } from './ui/icons'
import Avi from './ui/Avi'
import CompleteProfileScreen from './screens/onboarding/CompleteProfileScreen'
import SplashScreen from './screens/onboarding/SplashScreen'
import LoginScreen from './screens/auth/LoginScreen'
import { ForgotPasswordScreen, ResetPasswordScreen, VerifyConfirmScreen, SignupScreen, CheckEmailScreen } from './screens/auth/AuthScreens'
import AmbassadorScreen from './screens/ambassador/AmbassadorScreen'
import PodcastLibraryScreen from './screens/podcast/PodcastLibraryScreen'
import PodcastPlayerScreen from './screens/podcast/PodcastPlayerScreen'
import StudyMaterialsScreen from './screens/study/StudyMaterialsScreen'
import DocReadyScreen from './screens/study/DocReadyScreen'
import DocumentStudyHubScreen from './screens/study/DocumentStudyHubScreen'
import DocumentReaderScreen from './screens/study/DocumentReaderScreen'
import HomeScreen from './screens/home/HomeScreen'
import { rememberLastStudyDocument } from './lib/lastStudyDocument'
import ExploreScreen from './screens/explore/ExploreScreen'
import { FlashcardsStudyScreen, QuizStudyScreen, SummaryStudyScreen, MindMapStudyScreen } from './screens/study/GeneratedStudyScreens'
import AchievementsScreen from './screens/gamification/AchievementsScreen'
import AITutorScreen from './screens/tutor/AITutorScreen'
import type { Achievement, AchievementsResponse } from './types/achievements'
import type { Screen } from './types/navigation'
import { useAppNavigation } from './navigation/useAppNavigation'
import AppShell from './navigation/AppShell'
import { XPProgressScreen } from './screens/gamification/ProgressScreens'
// Screen implementations are feature-owned; this file keeps the existing route dispatch and shared app state.
import TimeStudiedScreen from './screens/gamification/TimeStudiedScreen'
import StudyStreakScreen from './screens/gamification/StudyStreakScreen'
import type { GamificationSummary, StudyTimeResponse } from './types/gamification'
import type { HomeDocument } from './types/profile'
import type { OpportunityPublic, SponsoredCampaign } from './types/opportunities'
import type { DocumentDetail } from './types/documents'
import { formatStudyTime } from './lib/studyTime'
import { oppTypeMeta, fmtDeadline } from './lib/opportunities'
import { LIBRARY_MATERIAL_TYPES, materialTypeLabel } from './lib/library'
import LibraryScreen from './screens/library/LibraryScreen'
import { podcastColor, podcastDuration, type PodcastItem } from './types/podcast'
import SettingsScreen from './screens/settings/SettingsScreen'
import EditProfileScreen from './screens/profile/EditProfileScreen'
import ProfileScreen from './screens/profile/ProfileScreen'
// Profile data/cache live with the screen; route state and loading skeleton remain app-owned.
import NotificationsScreen from './screens/notifications/NotificationsScreen'
import GroupDetailScreen from './screens/groups/GroupDetailScreen'
import { FollowListScreen, FollowRequestsScreen } from './screens/social/FollowScreens'
import StudentProfileScreen from './screens/profile/StudentProfileScreen'
import type { FollowRequestItem, MessageRequestItem } from './types/social'
import ChatOptionsScreen from './screens/chat/ChatOptionsScreen'
import NewChatScreen from './screens/chat/NewChatScreen'
import ChatDetailScreen from './screens/chat/ChatDetailScreen'
import type { ChatDetail, ChatMessageData } from './types/chat'
import GroupCreateScreen from './screens/groups/GroupCreateScreen'
import type { UserSearchResult } from './types/users'
import type { GroupSummary } from './types/groups'
import ShareOppForm from './screens/opportunities/ShareOppForm'
import { OpportunitiesScreen, OppDetailScreen } from './screens/opportunities/OpportunityScreens'
import Pill from './ui/Pill'
import { subscribeToPush, unsubscribeFromPush } from './lib/pushNotifications'
import type { UniversityOption, ProgramOption } from './types/academic'
import { resetChatRealtime } from './crypto/chatRealtime'
import WhatsAppChatExperience from './crypto/WhatsAppChatExperience'
import { getOfflineStudyDocumentUrlByContentHash, getSavedStudyHubOffline, listSavedStudyHubOffline, saveStudyHubDocumentOffline, saveUploadedFileOffline } from './offline/studyHubOffline'
import { cacheGeneratedAudioOffline, getCachedGeneratedAudioUrl, getGeneratedMaterialOffline, getLatestGeneratedMaterialForPath, listOfflineGeneratedMaterials, saveGeneratedMaterialOffline, setOfflineUserId } from './offline/generatedMaterials'
import { installStudyHubActivityTracker, setStudyHubActive, setStudyHubUserId } from './offline/studyHubActivityTracker'
import { installActivityHeartbeat } from './activityHeartbeat'
import PremiumOrganisationPortal from './organisation/PremiumOrganisationPortal'
import B2BFinanceAdmin from './admin/B2BFinanceAdmin'
import AdminPlatform from './admin/AdminPlatform'
import { PAYMENT_STATUS_META } from './admin/AdminPlatform'
import StudyShareSheet from './share/StudyShareSheet'
import StudyActivityScreen from './StudyActivityScreen'
import { cacheAvatar, getCachedAvatar, clearCachedAvatar } from './offline/avatarCache'

// ─── API helper ─────────────────────────────────────────────────────────────
// Launch verification: generated frontend architecture and theme contrast are validated in CI.
// Dev: Vite proxies these paths straight to the Flask backend (see
// vite.config.ts), so relative paths work identically in dev and once this
// app is eventually served by Flask itself in production - no base URL
// switching needed.
type GenerationProgress = { progress_percent: number; progress_stage: string; status: string; found?: boolean; error_message?: string | null }

function normalizeGeneratedMaterialFeature(value: unknown): string {
  const feature = String(value || '').toLowerCase().replace(/-/g, '_')
  if (feature === 'summary') return 'summarize'
  if (feature === 'practice_questions') return 'quiz'
  if (feature === 'mindmap') return 'mind_map'
  return feature
}

function getSelectedGeneratedMaterialId(documentId: string | number, feature: string): number | null {
  try {
    const raw = sessionStorage.getItem('prepza-open-material')
    if (!raw) return null
    const selected = JSON.parse(raw)
    const materialId = Number(selected?.materialId)
    if (
      String(selected?.documentId) === String(documentId) &&
      normalizeGeneratedMaterialFeature(selected?.type) === normalizeGeneratedMaterialFeature(feature) &&
      Number.isInteger(materialId) &&
      materialId > 0
    ) return materialId
  } catch { /* malformed session state is non-fatal */ }
  return null
}

async function replaySelectedGeneratedMaterialOffline(documentId: string | number, feature: string): Promise<any | null> {
  const materialId = getSelectedGeneratedMaterialId(documentId, feature)
  if (!materialId) return null

  const cached = await getGeneratedMaterialOffline(
    `/documents/${documentId}/materials/${materialId}`,
    null,
  )
  if (
    !cached ||
    Number(cached.material_id) !== materialId ||
    cached.status !== 'ready' ||
    normalizeGeneratedMaterialFeature(cached.type) !== normalizeGeneratedMaterialFeature(feature) ||
    cached.payload == null
  ) return null

  const normalizedFeature = normalizeGeneratedMaterialFeature(feature)
  const payloadKey = normalizedFeature === 'summarize' ? 'summary' : normalizedFeature
  return { material_id: materialId, reused: true, [payloadKey]: cached.payload }
}


// Save the canonical API representation of a private material only when the
// signed-in student owns it. The generation POST response is a UI response
// (summary/flashcards/etc.), not the ready-material record needed for offline
// listing and replay. Shared Library materials must not become offline
// entitlements just because a student can currently view them.
async function cachePrivateReadyGeneratedMaterialOffline(
  documentId: string | number,
  materialId: unknown,
  userId: unknown,
  canonicalOverride?: {
    material_id: number
    type: string
    status: string
    parameters?: Record<string, unknown>
    payload: unknown
    private_to_current_user?: boolean
  },
  expectedType?: string,
): Promise<boolean> {
  const id = Number(materialId)
  const ownerId = Number(userId)
  if (!Number.isInteger(id) || id <= 0 || !Number.isInteger(ownerId) || ownerId <= 0) return false

  try {
    const path = `/documents/${documentId}/materials/${id}`
    const canonical = canonicalOverride ?? await api<{
      material_id: number
      type: string
      status: string
      parameters?: Record<string, unknown>
      payload: unknown
      private_to_current_user?: boolean
    }>(path)
    if (
      Number(canonical.material_id) !== id ||
      canonical.status !== 'ready' ||
      canonical.payload == null ||
      canonical.private_to_current_user !== true ||
      (expectedType != null &&
        normalizeGeneratedMaterialFeature(canonical.type) !== normalizeGeneratedMaterialFeature(expectedType))
    ) return false

    await saveGeneratedMaterialOffline(path, null, canonical)
    return true
  } catch {
    // Offline persistence is best-effort. A failed cache write must never
    // interrupt opening a material that the server has already authorized.
    return false
  }
}

async function cachePodcastReadyOffline(
  documentId: number | null,
  materialId: number | null,
  path: string,
  status: { audio_status: string; audio_url: string | null; duration_seconds: number | null },
): Promise<void> {
  if (!navigator.onLine || documentId == null || !materialId || status.audio_status !== 'ready' || !status.audio_url) return
  try {
    const me = await api<{ id: number }>('/me')
    const eligible = await cachePrivateReadyGeneratedMaterialOffline(documentId, materialId, me.id, undefined, 'podcast')
    if (!eligible) return
    await saveGeneratedMaterialOffline(path, null, status)
    await cacheGeneratedAudioOffline(status.audio_url)
  } catch {
    // Best-effort persistence must not delay or interrupt playback.
  }
}

async function getCachedPodcastAudio(path: string): Promise<{ audioUrl: string | null; duration: number }> {
  const cachedAudio = await getLatestGeneratedMaterialForPath(path)
  const sourceAudioUrl = typeof cachedAudio?.audio_url === 'string' ? cachedAudio.audio_url : ''
  const audioUrl = sourceAudioUrl ? await getCachedGeneratedAudioUrl(sourceAudioUrl) : null
  return { audioUrl, duration: Number(cachedAudio?.duration_seconds || 0) }
}

async function generationRequest<T = any>(
  path: string,
  options: RequestInit = {},
  onProgress?: (progress: GenerationProgress) => void,
  currentUserId?: number,
): Promise<T> {
  const publish = (progress: GenerationProgress) => {
    onProgress?.(progress)
    window.dispatchEvent(new CustomEvent('prepza:generation-progress', { detail: progress }))
  }
  const match = path.match(/^\/documents\/(\d+)\/(summarize|quiz|flashcards|mind-map|podcast-script)$/)
  const documentId = match?.[1]
  const feature = match?.[2] === 'podcast-script' ? 'podcast'
    : match?.[2] === 'mind-map' ? 'mind_map'
    : match?.[2]

  if (!documentId || !feature) return api<T>(path, options)

  // Resolve the exact ready artifact selected by the student. Feature aliases
  // are normalized here because the UI labels summary as "summary" while its
  // generation endpoint is /summarize, and quiz/mind-map have legacy aliases.
  const selectedMaterialId = getSelectedGeneratedMaterialId(documentId, feature)

  // A selected ready artifact is replay-only, online or offline. Prefer the
  // device cache. If this device has not cached it yet, fetch the one canonical
  // material record (GET), never POST to a generation endpoint just to replay it.
  if (selectedMaterialId) {
    const replay = await replaySelectedGeneratedMaterialOffline(documentId, feature)
    if (replay) {
      if (feature !== 'podcast') {
        try { sessionStorage.removeItem('prepza-open-material') } catch {}
      }
      publish({
        found: true,
        status: 'completed',
        progress_percent: 100,
        progress_stage: 'Found your saved material',
      })
      return replay as T
    }

    if (!navigator.onLine) {
      throw new Error('This study material is not saved for offline use on this device.')
    }

    const materialPath = `/documents/${documentId}/materials/${selectedMaterialId}`
    const canonical = await api<{
      material_id: number
      type: string
      status: string
      parameters?: Record<string, unknown>
      payload: unknown
    }>(materialPath)
    if (
      Number(canonical.material_id) !== selectedMaterialId ||
      canonical.status !== 'ready' ||
      canonical.payload == null ||
      normalizeGeneratedMaterialFeature(canonical.type) !== normalizeGeneratedMaterialFeature(feature)
    ) {
      throw new Error('The selected study material is no longer available.')
    }

    // The authenticated canonical response says whether this artifact is
    // private to this student. Shared Library material remains outside this cache.
    if (currentUserId != null) {
      await cachePrivateReadyGeneratedMaterialOffline(
        documentId,
        selectedMaterialId,
        currentUserId,
        canonical,
        feature,
      )
    }

    const normalizedFeature = normalizeGeneratedMaterialFeature(feature)
    const payloadKey = normalizedFeature === 'summarize' ? 'summary' : normalizedFeature
    if (feature !== 'podcast') {
      try { sessionStorage.removeItem('prepza-open-material') } catch {}
    }
    publish({
      found: true,
      status: 'completed',
      progress_percent: 100,
      progress_stage: 'Found your saved material',
    })
    return {
      material_id: selectedMaterialId,
      reused: true,
      [payloadKey]: canonical.payload,
    } as T
  }

  // A request without an explicitly selected artifact is a create/generate
  // operation. Offline mode must never allow that request to reach the server.
  if (!navigator.onLine) {
    throw new Error('This study material is not saved for offline use on this device.')
  }

  let stopped = false
  let timer: ReturnType<typeof setTimeout> | null = null
  const requestOptions = () => {
    const nextHeaders = new Headers(options.headers || {})
    if (selectedMaterialId) nextHeaders.set('X-Prepza-Material-ID', String(selectedMaterialId))
    return { ...options, headers: nextHeaders }
  }

  const pollUntilReady = async (jobId?: number): Promise<GenerationProgress> => {
    for (;;) {
      if (stopped) throw new Error('Generation cancelled')
      const progress = jobId
        ? await api<GenerationProgress>(`/ai-jobs/${jobId}`)
        : await api<GenerationProgress>(`/documents/${documentId}/generation-progress?feature=${feature}`)
      if (progress.found !== false) publish(progress)
      if (progress.status === 'completed') return progress
      if (progress.status === 'failed') {
        throw new ApiError(progress.error_message || progress.error_message || 'Generation failed. Please try again.', 500)
      }
      await new Promise(resolve => { timer = setTimeout(resolve, 700) })
    }
  }

  publish({ found: false, status: 'starting', progress_percent: 3, progress_stage: 'Preparing your study material' })

  return api<any>(path, requestOptions()).then(async result => {
    if (selectedMaterialId) {
      try { sessionStorage.removeItem('prepza-open-material') } catch {}
    }
    if (!result?.async || !result?.job_id) {
      if (result?.material_id) {
        await cachePrivateReadyGeneratedMaterialOffline(documentId, result.material_id, currentUserId, undefined, feature)
      }
      publish({
        found: true,
        status: 'completed',
        progress_percent: 100,
        progress_stage: result?.reused ? 'Found your saved material' : 'Ready',
      })
      return result as T
    }

    publish({
      found: true,
      status: 'processing',
      progress_percent: Number(result.progress_percent || 5),
      progress_stage: 'Queued',
    })

    await pollUntilReady(Number(result.job_id))

    // The worker has finished and the exact fingerprint is now persisted.
    // Resolve the artifact through the normal route; this is a cache hit and
    // returns the saved payload without another model call.
    const resolveHeaders = new Headers(options.headers || {})
    resolveHeaders.set('X-Prepza-Resolve-Generation', '1')
    const resolved = await api<T>(path, { ...options, headers: resolveHeaders })
    await cachePrivateReadyGeneratedMaterialOffline(documentId, (resolved as any)?.material_id, currentUserId, undefined, feature)
    publish({
      found: true,
      status: 'completed',
      progress_percent: 100,
      progress_stage: resolved && (resolved as any).reused ? 'Found your saved material' : 'Ready',
    })
    return resolved
  }).catch(error => {
    if (selectedMaterialId) {
      try { sessionStorage.removeItem('prepza-open-material') } catch {}
    }
    stopped = true
    if (timer) clearTimeout(timer)
    publish({
      found: true,
      status: 'failed',
      progress_percent: 100,
      progress_stage: 'Generation failed',
      error_message: error instanceof ApiError ? error.message : String(error),
    })
    throw error
  }).finally(() => {
    stopped = true
    if (timer) clearTimeout(timer)
  })
}

// ─── Document upload helpers ───────────────────────────────────────────────
const ALLOWED_UPLOAD_EXTENSIONS = ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'jpg', 'jpeg', 'png']
const MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024 // 50 MB - matches backend MAX_DOCUMENT_SIZE_BYTES
const MAX_CHAT_ATTACHMENT_SIZE_BYTES = 20 * 1024 * 1024 // 20 MB - matches backend CHAT_ATTACHMENT_MAX_SIZE_BYTES
const IMAGE_FILE_TYPES = ['jpg', 'jpeg', 'png']

function getFileExtension(filename: string): string | null {
  const parts = filename.split('.')
  if (parts.length < 2) return null
  return parts[parts.length - 1].toLowerCase()
}

async function sha256Hex(file: File): Promise<string> {
  const buffer = await file.arrayBuffer()
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer)
  return Array.from(new Uint8Array(hashBuffer)).map(b => b.toString(16).padStart(2, '0')).join('')
}



// Payload shape inside `summary`/`quiz`/`flashcards`/`mindmap` below is
// whatever ai_service.py produces - not pinned down here, so every
// consumer renders defensively (checks a few likely field names, falls
// back to raw JSON) rather than assuming one exact shape.
type CompletionResponse = { xp_awarded: number; newly_unlocked_achievements: string[] }

function AchievementToast({ codes }: { codes: string[] }) {
  if (codes.length === 0) return null
  return (
    <div style={{ background: 'rgba(201,168,76,0.15)', border: `1px solid ${N.gold}55`, borderRadius: 12, padding: '10px 14px', margin: '0 0 14px', fontSize: 12, fontWeight: 700, color: N.gold }}>
      🏆 Achievement unlocked: {codes.join(', ')}
    </div>
  )
}

function GenerationError({ error }: { error: string }) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 32, textAlign: 'center' }}>
      <div style={{ fontSize: 40, marginBottom: 14 }}>⚠️</div>
      <div style={{ color: '#6B7280', fontSize: 13, maxWidth: 280 }}>{error}</div>
    </div>
  )
}

function DelayedScreenSkeleton({ children }: { children: React.ReactNode }) {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(true), 220)
    return () => window.clearTimeout(timer)
  }, [])
  if (!visible) return null
  return <>{children}</>
}

function GenerationLoading({ label }: { label: string }) {
  const { tokens: T } = useTheme()
  const [percent, setPercent] = useState(5)
  const [stage, setStage] = useState(label)
  useEffect(() => {
    const onProgress = (event: Event) => {
      const detail = (event as CustomEvent).detail || {}
      setPercent(Math.max(0, Math.min(100, Number(detail.progress_percent || 0))))
      setStage(detail.progress_stage || label)
    }
    window.addEventListener('prepza:generation-progress', onProgress)
    return () => window.removeEventListener('prepza:generation-progress', onProgress)
  }, [label])
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 32 }}>
      <div style={{ width: '100%', maxWidth: 380, background: T.card, borderRadius: 22, padding: 24, boxShadow: '0 8px 30px rgba(0,0,0,0.07)' }}>
        <div style={{ color: N.gold, fontSize: 10, fontWeight: 900, letterSpacing: 1, textTransform: 'uppercase' }}>Prepza AI</div>
        <div style={{ color: T.text, fontSize: 18, fontWeight: 800, marginTop: 7 }}>{label}</div>
        <div style={{ color: T.textMuted, fontSize: 12, marginTop: 5 }}>{stage}</div>
        <div style={{ height: 8, background: T.border, borderRadius: 99, overflow: 'hidden', marginTop: 20 }}>
          <div style={{ width: `${percent}%`, height: '100%', background: `linear-gradient(90deg,${N.gold},${N.goldL})`, transition: 'width .45s ease' }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 7, color: T.textMuted, fontSize: 11 }}>
          <span>{percent}%</span><span>Please wait</span>
        </div>
      </div>
    </div>
  )
}

// ─── Icon helpers ─────────────────────────────────────────────────────────────
// ─── Types ────────────────────────────────────────────────────────────────────
// ─── Kenyan Data ──────────────────────────────────────────────────────────────
// USER mock constant removed (Chunk 14 sweep) - screens now derive display name/initials from GET /me

function SponsoredOpportunityCard({
  campaign,
  setScreen,
  setActiveOpportunityId,
  compact = false,
}: {
  campaign: SponsoredCampaign
  setScreen: (s: Screen) => void
  setActiveOpportunityId: (id: number | null) => void
  compact?: boolean
}) {
  const { tokens: T } = useTheme()
  const cardRef = useRef<HTMLButtonElement | null>(null)
  const impressionSent = useRef(false)
  const impressionRecorded = useRef(false)
  const impressionRejected = useRef(false)
  const impressionQualified = useRef(false)
  const eventId = useRef<string | null>(null)
  const clickEventId = useRef<string | null>(null)
  const timerRef = useRef<number | null>(null)
  const retryTimerRef = useRef<number | null>(null)
  const retryAttempts = useRef(0)
  const visibleEnough = useRef(false)
  const opp = campaign.opportunity

  const createEventId = () => {
    const cryptoApi = crypto as Crypto & { randomUUID?: () => string }
    if (typeof cryptoApi.randomUUID === 'function') return cryptoApi.randomUUID()
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, char => {
      const random = Math.floor(Math.random() * 16)
      return (char === 'x' ? random : (random & 0x3) | 0x8).toString(16)
    })
  }

  const impressionStorageKey = 'prepza:b2b:impression-pending:' + campaign.campaign_id
  const clickStorageKey = 'prepza:b2b:click-pending:' + campaign.campaign_id

  const pendingEventId = (storageKey: string, current: React.MutableRefObject<string | null>) => {
    if (current.current) return current.current
    try {
      current.current = sessionStorage.getItem(storageKey)
      if (current.current) return current.current
    } catch { /* session storage may be unavailable */ }
    current.current = createEventId()
    try { sessionStorage.setItem(storageKey, current.current) } catch { /* keep in memory */ }
    return current.current
  }

  const clearPendingEvent = (storageKey: string) => {
    try { sessionStorage.removeItem(storageKey) } catch { /* best effort */ }
  }

  const clearRetryTimer = () => {
    if (retryTimerRef.current != null) {
      window.clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }
  }

  const scheduleImpressionRetry = () => {
    if (
      retryTimerRef.current != null ||
      impressionRecorded.current ||
      impressionRejected.current ||
      !impressionQualified.current ||
      document.visibilityState !== 'visible' ||
      !navigator.onLine
    ) return
    // A lost HTTP response may mean the server already charged. Keep the
    // same UUID and use capped exponential backoff to make retries safe.
    const delay = Math.min(30000, 1000 * (2 ** Math.min(retryAttempts.current, 5)))
    retryAttempts.current += 1
    retryTimerRef.current = window.setTimeout(() => {
      retryTimerRef.current = null
      if (navigator.onLine && document.visibilityState === 'visible') {
        void recordImpression()
      }
    }, delay)
  }

  const recordImpression = async () => {
    if (impressionRecorded.current) return true
    if (impressionRejected.current || impressionSent.current) return false
    // Do not queue a stale view while disconnected. After reconnect, qualify
    // a fresh continuous visible period before sending an impression.
    if (!navigator.onLine) return false
    impressionSent.current = true
    const stableEventId = pendingEventId(impressionStorageKey, eventId)
    try {
      const result = await api<{ eligible?: boolean; recorded?: boolean }>(
        '/api/discovery/campaigns/' + campaign.campaign_id + '/impression',
        {
          method: 'POST',
          body: JSON.stringify({ event_id: stableEventId }),
        },
      )
      impressionSent.current = false
      if (result.eligible === false) {
        impressionRejected.current = true
        clearRetryTimer()
        clearPendingEvent(impressionStorageKey)
        return false
      }
      impressionRecorded.current = true
      retryAttempts.current = 0
      clearRetryTimer()
      clearPendingEvent(impressionStorageKey)
      return true
    } catch {
      impressionSent.current = false
      scheduleImpressionRetry()
      return false
    }
  }
  const meta = oppTypeMeta(opp.opportunity_type)

  useEffect(() => {
    const node = cardRef.current
    if (!node || typeof IntersectionObserver === 'undefined') return

    const clearTimer = () => {
      if (timerRef.current != null) {
        window.clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
    const scheduleImpression = () => {
      if (
        timerRef.current != null ||
        impressionRecorded.current ||
        impressionRejected.current ||
        impressionSent.current ||
        impressionQualified.current ||
        !visibleEnough.current ||
        document.visibilityState !== 'visible'
      ) return
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null
        if (!visibleEnough.current || document.visibilityState !== 'visible') return
        // If offline, wait for reconnection and then require a fresh 1.5s
        // visible period. Never bill a cached ad merely because it was shown
        // while disconnected.
        if (!navigator.onLine) return
        impressionQualified.current = true
        void recordImpression()
      }, 1500)
    }
    const observer = new IntersectionObserver(entries => {
      const entry = entries.find(item => item.target === node) || entries[0]
      visibleEnough.current = Boolean(entry?.isIntersecting && entry.intersectionRatio >= 0.5)
      if (visibleEnough.current && document.visibilityState === 'visible') {
        if (impressionQualified.current) scheduleImpressionRetry()
        else scheduleImpression()
      } else {
        clearTimer()
      }
    }, { threshold: [0, 0.5, 1] })
    const onVisibilityChange = () => {
      if (document.visibilityState !== 'visible') {
        clearTimer()
        clearRetryTimer()
      } else if (impressionQualified.current) {
        scheduleImpressionRetry()
      } else if (visibleEnough.current) {
        scheduleImpression()
      }
    }
    const onOnline = () => {
      if (!visibleEnough.current || document.visibilityState !== 'visible') return
      if (impressionQualified.current) {
        clearRetryTimer()
        void recordImpression()
      } else {
        // Requalify after the network returns; do not backdate an offline view.
        scheduleImpression()
      }
    }

    observer.observe(node)
    document.addEventListener('visibilitychange', onVisibilityChange)
    window.addEventListener('online', onOnline)
    return () => {
      observer.disconnect()
      document.removeEventListener('visibilitychange', onVisibilityChange)
      window.removeEventListener('online', onOnline)
      clearTimer()
      clearRetryTimer()
    }
  }, [campaign.campaign_id])

  const open = async () => {
    if (impressionRecorded.current) {
      const stableClickId = pendingEventId(clickStorageKey, clickEventId)
      try {
        const result = await api<{ eligible?: boolean }>(
          '/api/discovery/campaigns/' + campaign.campaign_id + '/click',
          {
            method: 'POST',
            body: JSON.stringify({ event_id: stableClickId }),
          },
        )
        if (result.eligible !== false) clearPendingEvent(clickStorageKey)
      } catch {
        // Keep the UUID in sessionStorage. A retry after reconnection or a
        // later visit will reuse it, even if the first response was lost.
      }
    }
    if (opp.id) {
      setActiveOpportunityId(opp.id)
      setScreen('opportunity-detail')
    }
  }

  return (
    <button
      ref={cardRef}
      onClick={() => { void open() }}
      aria-label={'View sponsored opportunity: ' + opp.title}
      style={{
        flex: compact ? '0 0 280px' : undefined,
        width: compact ? 280 : '100%',
        textAlign: 'left',
        border: '1px solid ' + N.gold + '35',
        background: T.card,
        borderRadius: 16,
        padding: 13,
        cursor: 'pointer',
        boxShadow: '0 4px 14px rgba(0,0,0,0.06)',
        fontFamily: 'Plus Jakarta Sans',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 8 }}>
        <span style={{ fontSize: 9, fontWeight: 900, letterSpacing: 0.8, color: N.gold }}>SPONSORED</span>
        <span style={{ marginLeft: 'auto', fontSize: 9, color: T.textMuted }}>{meta.label}</span>
      </div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <div style={{ width: 40, height: 40, borderRadius: 11, background: N.navy, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', flexShrink: 0 }}>
          {opp.organisation?.logo_url
            ? <img src={opp.organisation.logo_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            : <span style={{ color: N.gold, fontWeight: 900 }}>{(opp.organisation?.name || 'P').slice(0, 1).toUpperCase()}</span>}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ color: T.text, fontWeight: 800, fontSize: compact ? 12 : 13 }} className="line-clamp-2">{opp.title}</div>
          <div style={{ color: T.textMuted, fontSize: 10, marginTop: 3 }} className="line-clamp-1">{opp.organisation?.name || 'Organisation'}</div>
        </div>
      </div>
      {opp.application_deadline && <div style={{ color: T.textMuted, fontSize: 10, marginTop: 8 }}>Deadline · {fmtDeadline(opp.application_deadline)}</div>}
    </button>
  )
}

const podcasts = [
  { id: 1, title: 'Interest Theory Explained', subject: 'ACT 101', duration: '9 min', icon: '∑', color: '#C9A84C' },
  { id: 2, title: 'Integration Techniques', subject: 'MAT 101', duration: '12 min', icon: '∫', color: '#4C7BC9' },
  { id: 3, title: 'Normal Distributions', subject: 'STA 101', duration: '7 min', icon: 'σ', color: '#4CC97B' },
  { id: 4, title: 'Probability Foundations', subject: 'STA 101', duration: '14 min', icon: 'P', color: '#9B59B6' },
]

// ─── Shared atoms ─────────────────────────────────────────────────────────────
const PREPZA_BRANDLINE = 'Prepza: Study smarter together.'

// ─── Theme (light/dark) ─────────────────────────────────────────────────────
// N above stays constant in both modes - it's brand color (navy header/hero
// backgrounds, gold button accents) and is meant to look the same either
// way. These tokens are for surfaces/text that actually need to invert.
// Rollout is screen-by-screen: only components that call useTheme() react
// to a mode change - everything else still reads N/raw hex directly until
// it's migrated in a later pass.
// Prevents skeleton-loader flicker on fast networks: only flips true if
// `active` is still true after `delay` ms. Returns false immediately once
// `active` goes false, so real content always shows as soon as it's ready.
function useDelayedFlag(active: boolean, delay = 200) {
  const [show, setShow] = useState(false)
  useEffect(() => {
    if (!active) { setShow(false); return }
    const t = setTimeout(() => setShow(true), delay)
    return () => clearTimeout(t)
  }, [active, delay])
  return show
}

function Btn({ label, onClick, variant = 'primary', small }: { label: string; onClick?: () => void; variant?: 'primary'|'ghost'|'outline'; small?: boolean }) {
  const styles: Record<string, React.CSSProperties> = {
    primary: { background: `linear-gradient(135deg,${N.navy},${N.navy3})`, color: N.gold, border: 'none' },
    ghost:   { background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, border: 'none' },
    outline: { background: 'transparent', color: N.navy, border: `1.5px solid ${N.navy}22` },
  }
  return (
    <button onClick={onClick} style={{ ...styles[variant], fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: small ? 12 : 14, borderRadius: 14, padding: small ? '8px 16px' : '13px 24px', cursor: 'pointer', letterSpacing: 0.2 }}>{label}</button>
  )
}
function Bar({ pct, color = N.gold }: { pct: number; color?: string }) {
  return <div style={{ background: '#E5E7EB', borderRadius: 99, height: 5 }}><div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 99, transition: 'width 0.6s ease' }} /></div>
}

function StatusBar({ dark = true }: { dark?: boolean }) {
  const c = dark ? '#fff' : N.navy
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 22px 6px', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, color: c }}>
      <span>9:41</span>
      <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
        <svg width="16" height="11" viewBox="0 0 16 12" fill={c}><rect x="0" y="4" width="3" height="8" rx="1"/><rect x="4.5" y="2.5" width="3" height="9.5" rx="1"/><rect x="9" y="0.5" width="3" height="11.5" rx="1"/><rect x="13.5" y="0" width="2.5" height="12" rx="1" opacity="0.3"/></svg>
        <svg width="25" height="12" viewBox="0 0 25 12" fill="none"><rect x="0.5" y="0.5" width="21" height="11" rx="3.5" stroke={c} strokeOpacity="0.35"/><rect x="2" y="2" width="16" height="8" rx="2" fill={c}/><path d="M23 4v4a2 2 0 000-4z" fill={c} fillOpacity="0.4"/></svg>
      </div>
    </div>
  )
}

function TopBar({ title, onBack, setScreen, rightEl }: { title?: string; onBack?: () => void; setScreen?: (s: Screen) => void; rightEl?: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 18px 14px' }}>
      {onBack && (
        <button aria-label="Back" onClick={onBack} style={{ width: 36, height: 36, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 11, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <div style={{ color: '#fff' }}>{Ic.back()}</div>
        </button>
      )}
      {title && <span style={{ flex: 1, fontWeight: 800, fontSize: 17, color: '#fff' }}>{title}</span>}
      {rightEl}
    </div>
  )
}


// ─── DOCUMENT STUDY HUB ─────────────────────────────────────────────────────
// A document is the student's study home: read it, ask Morio about it, replay
// existing materials, or create a new material. Generation remains owned by
// the existing material screens/reusable-generation backend.
// ─── LOADING SYSTEM ───────────────────────────────────────────────────────────

function Sk({ w, h = 14, r = 8, dark, style: sx }: { w?: string | number; h?: number; r?: number; dark?: boolean; style?: React.CSSProperties }) {
  const { mode } = useTheme()
  const base: React.CSSProperties = { width: w ?? '100%', height: h, borderRadius: r, flexShrink: 0, ...sx }
  return (dark || mode === 'dark')
    ? <div style={{ ...base, background: 'linear-gradient(90deg,rgba(255,255,255,0.05) 25%,rgba(255,255,255,0.12) 50%,rgba(255,255,255,0.05) 75%)', backgroundSize: '200% 100%', animation: 'shimmer 1.8s infinite' }} />
    : <div className="shimmer" style={base} />
}

function SkCircle({ size = 40, dark }: { size?: number; dark?: boolean }) {
  return <Sk w={size} h={size} r={size / 2} dark={dark} />
}

function AsyncBtn({ label, loadLabel, onClick, style, variant = 'primary', loadingMs = 1500 }: {
  label: string; loadLabel?: string; onClick?: () => void; style?: React.CSSProperties
  variant?: 'primary' | 'ghost' | 'danger'; loadingMs?: number
}) {
  const [busy, setBusy] = useState(false)
  const bg = variant === 'primary' ? `linear-gradient(135deg,${N.gold},${N.goldL})` : variant === 'ghost' ? `linear-gradient(135deg,${N.navy},${N.navy3})` : '#C94C4C'
  const fg = variant === 'primary' ? N.navy : variant === 'ghost' ? N.gold : '#fff'
  const handle = () => { if (busy) return; setBusy(true); onClick?.(); setTimeout(() => setBusy(false), loadingMs) }
  return (
    <button onClick={handle} disabled={busy} style={{ background: bg, color: fg, border: 'none', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, borderRadius: 14, cursor: busy ? 'wait' : 'pointer', opacity: busy ? 0.82 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, transition: 'opacity 0.2s', ...style }}>
      {busy
        ? <><div style={{ width: 13, height: 13, border: '2px solid currentColor', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin-slow 0.65s linear infinite', flexShrink: 0 }} />{loadLabel ?? 'Working…'}</>
        : label}
    </button>
  )
}

// ─── SKELETON ATOMS ───────────────────────────────────────────────────────────

function SkPostCard() {
  const { tokens: T } = useTheme()
  return (
    <div style={{ background: T.card, borderRadius: 16, padding: '14px 16px', marginBottom: 10, boxShadow: '0 2px 10px rgba(0,0,0,0.05)' }}>
      <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
        <SkCircle size={38} />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><Sk w="50%" h={13} /><Sk w="70%" h={10} /></div>
        <Sk w={50} h={18} r={99} />
      </div>
      <Sk h={12} style={{ marginBottom: 6 }} /><Sk h={12} w="80%" style={{ marginBottom: 6 }} /><Sk h={12} w="60%" style={{ marginBottom: 14 }} />
      <div style={{ display: 'flex', gap: 16 }}>
        <Sk w={50} h={14} r={6} /><Sk w={50} h={14} r={6} />
        <div style={{ flex: 1 }} /><Sk w={18} h={18} r={4} /><Sk w={18} h={18} r={4} />
      </div>
    </div>
  )
}

function SkDocCard() {
  const { tokens: T } = useTheme()
  return (
    <div style={{ background: T.card, borderRadius: 14, padding: 14, marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
      <Sk w={42} h={42} r={12} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><Sk h={13} w="80%" /><Sk h={10} w="55%" /><Sk h={9} w="40%" /></div>
      <Sk w={36} h={18} r={99} />
    </div>
  )
}

function SkChatRow() {
  const { tokens: T } = useTheme()
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '12px 16px', borderBottom: `1px solid ${T.border}` }}>
      <SkCircle size={46} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}><Sk w="45%" h={14} /><Sk w={40} h={11} /></div>
        <Sk w="70%" h={11} />
      </div>
    </div>
  )
}

function SkOppCard() {
  const { tokens: T } = useTheme()
  return (
    <div style={{ background: T.card, borderRadius: 18, overflow: 'hidden', boxShadow: '0 4px 14px rgba(0,0,0,0.08)', marginBottom: 14 }}>
      <div style={{ height: 5, background: T.border }} />
      <div style={{ padding: 16 }}>
        <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
          <Sk w={48} h={48} r={14} />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 7 }}><Sk h={14} w="75%" /><Sk h={11} w="50%" /></div>
          <Sk w={60} h={20} r={99} />
        </div>
        <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>{[80,100,90].map((w, i) => <Sk key={i} w={w} h={11} r={99} />)}</div>
        <div style={{ display: 'flex', gap: 8 }}><Sk h={42} r={12} /><Sk w={44} h={42} r={12} /><Sk w={44} h={42} r={12} /></div>
      </div>
    </div>
  )
}

function SkNotifRow() {
  const { tokens: T } = useTheme()
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', background: T.card, borderRadius: 14, padding: '13px 14px', marginBottom: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
      <Sk w={42} h={42} r={12} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><Sk h={13} w="55%" /><Sk h={11} /><Sk h={11} w="70%" /></div>
      <Sk w={40} h={10} />
    </div>
  )
}

// ─── SCREEN SKELETONS ─────────────────────────────────────────────────────────

function SkeletonHome() {
  const { tokens: T } = useTheme()
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Sk w={36} h={36} r={10} dark />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><Sk w={60} h={10} dark /><Sk w={100} h={14} dark /></div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}><Sk w={38} h={38} r={12} dark /><Sk w={38} h={38} r={12} dark /></div>
        </div>
        <Sk h={52} r={14} dark />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24, padding: '20px 18px 24px' }}>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}><Sk w={140} h={14} /><Sk w={70} h={12} /></div>
          <div style={{ background: T.card, borderRadius: 18, padding: 18, marginBottom: 10 }}>
            <div style={{ display: 'flex', gap: 14, marginBottom: 14 }}>
              <Sk w={48} h={48} r={14} />
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 7 }}><Sk h={14} /><Sk w="65%" h={11} /></div>
            </div>
            <Sk h={5} r={99} />
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}><Sk w={80} h={10} /><Sk w={80} h={28} r={10} /></div>
          </div>
          {[1,2].map(i => (
            <div key={i} style={{ background: T.card, borderRadius: 14, padding: '12px 14px', marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center' }}>
              <Sk w={40} h={40} r={12} />
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><Sk h={12} w="70%" /><Sk h={10} w="50%" /><Sk h={5} r={99} /></div>
              <Sk w={30} h={12} />
            </div>
          ))}
        </div>
        <div>
          <Sk w={120} h={14} style={{ marginBottom: 14 }} />
          <div style={{ display: 'flex', gap: 8, justifyContent: 'space-between' }}>
            {[1,2,3,4,5].map(i => (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                <Sk w={52} h={52} r={16} /><Sk w={40} h={9} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function SkeletonExplore() {
  const { tokens: T } = useTheme()
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <Sk w={80} h={20} dark style={{ marginBottom: 12 }} />
        <Sk h={44} r={13} dark style={{ marginBottom: 12 }} />
        <div style={{ display: 'flex', gap: 8 }}>{[40,70,90,70,80].map((w,i) => <Sk key={i} w={w} h={28} r={20} dark />)}</div>
      </div>
      <div style={{ padding: '20px 18px', display: 'flex', flexDirection: 'column', gap: 24 }}>
        <div>
          <Sk w={220} h={14} style={{ marginBottom: 12 }} />
        </div>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}><Sk w={100} h={14} /><Sk w={60} h={12} /></div>
          {[1,2,3].map(i => (
            <div key={i} style={{ background: T.card, borderRadius: 14, padding: 14, marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center' }}>
              <Sk w={42} h={42} r={12} />
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><Sk h={12} w="60%" /><Sk h={10} w="40%" /></div>
              <Sk w={44} h={22} r={9} />
            </div>
          ))}
        </div>
        <div><Sk w={160} h={14} style={{ marginBottom: 12 }} />{[1,2,3].map(i => <SkDocCard key={i} />)}</div>
        <div>
          <Sk w={160} h={14} style={{ marginBottom: 12 }} />
          <div style={{ display: 'flex', gap: 10, overflowX: 'hidden' }}>
            {[1,2,3].map(i => (
              <div key={i} style={{ flexShrink: 0, background: T.card, borderRadius: 16, padding: '16px 14px', width: 148, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
                <SkCircle size={48} /><Sk h={12} /><Sk h={10} w="70%" /><Sk h={28} r={10} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function SkeletonDocument() {
  const { tokens: T } = useTheme()
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 14px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12 }}>
          <Sk w={34} h={34} r={10} dark />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 5 }}><Sk h={14} dark /><Sk w="50%" h={10} dark /></div>
          <Sk w={34} h={34} r={10} dark />
        </div>
        <Sk h={34} r={12} dark />
      </div>
      <div style={{ flex: 1, padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', gap: 8 }}>{[1,2,3,4].map(i => <Sk key={i} w={80} h={28} r={20} />)}</div>
        <div style={{ background: T.card, borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 10px rgba(0,0,0,0.06)', height: '60vh' }}>
          <div className="shimmer" style={{ width: '100%', height: '100%' }} />
        </div>
      </div>
    </div>
  )
}

function SkeletonAITutor() {
  const { tokens: T } = useTheme()
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12 }}>
          <Sk w={34} h={34} r={10} dark /><Sk w={38} h={38} r={12} dark />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 5 }}><Sk w={140} h={14} dark /><Sk w={100} h={10} dark /></div>
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>{[1,2,3,4,5].map(i => <Sk key={i} w={70} h={28} r={20} dark />)}</div>
        <div style={{ display: 'flex', gap: 8 }}>{[1,2,3,4,5].map(i => <Sk key={i} w={80} h={28} r={20} dark />)}</div>
      </div>
      <div style={{ flex: 1, padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', gap: 10 }}>
          <Sk w={32} h={32} r={9} />
          <div style={{ maxWidth: '78%', background: T.card, borderRadius: '0 14px 14px 14px', padding: 14, flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Sk h={12} /><Sk h={12} w="90%" /><Sk h={12} w="75%" />
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <div style={{ maxWidth: '65%', background: N.navy2, borderRadius: '14px 0 14px 14px', padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Sk h={12} dark /><Sk h={12} w="80%" dark />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <Sk w={32} h={32} r={9} />
          <div style={{ background: T.card, borderRadius: '0 14px 14px 14px', padding: '12px 16px', display: 'flex', gap: 6, alignItems: 'center' }}>
            {[0,1,2].map(i => <div key={i} style={{ width: 8, height: 8, background: T.border, borderRadius: '50%', animation: `shimmer ${0.5 + i * 0.25}s ease-in-out infinite alternate` }} />)}
          </div>
        </div>
      </div>
    </div>
  )
}

function SkeletonPodcastLibrary() {
  const { tokens: T } = useTheme()
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 8 }}><Sk w={34} h={34} r={10} dark /><Sk w={160} h={18} dark /></div>
        <Sk w={200} h={11} dark />
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 16 }} className="scrollbar-hide">
        <Sk w={120} h={13} style={{ marginBottom: 12 }} />
        {[1,2,3,4,5].map(i => (
          <div key={i} style={{ display: 'flex', gap: 14, alignItems: 'center', background: T.card, borderRadius: 14, padding: '13px 14px', marginBottom: 8 }}>
            <Sk w={52} h={52} r={14} />
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><Sk h={13} w="65%" /><Sk h={10} w="45%" /></div>
            <Sk w={24} h={24} r={4} />
          </div>
        ))}
      </div>
    </div>
  )
}

function SkeletonOppDetail() {
  const { tokens: T } = useTheme()
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <Sk w={34} h={34} r={10} dark /><Sk w="60%" h={16} dark /><Sk w={34} h={34} r={10} dark />
        </div>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
          <Sk w={60} h={60} r={18} dark />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Sk w={180} h={16} dark /><Sk w={120} h={12} dark /><Sk w={60} h={18} r={99} dark />
          </div>
        </div>
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'flex', gap: 10 }}>{[1,2,3].map(i => <Sk key={i} h={36} r={12} />)}</div>
        <div style={{ background: T.card, borderRadius: 16, padding: 16 }}>
          <Sk w={180} h={14} style={{ marginBottom: 12 }} />
          {[100,90,100,85,100,70].map((w,i) => <Sk key={i} h={12} w={`${w}%`} style={{ marginBottom: 8 }} />)}
        </div>
        <div style={{ background: T.card, borderRadius: 16, padding: 16 }}>
          <Sk w={120} h={14} style={{ marginBottom: 12 }} />
          {[1,2,3,4].map(i => (
            <div key={i} style={{ display: 'flex', gap: 10, marginBottom: 10 }}><Sk w={20} h={20} r={10} /><Sk h={13} /></div>
          ))}
        </div>
        <Sk h={50} r={16} /><Sk h={46} r={16} />
      </div>
    </div>
  )
}

function SkeletonChats() {
  const { tokens: T } = useTheme()
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <Sk w={60} h={20} dark /><Sk w={34} h={34} r={10} dark />
        </div>
        <Sk h={40} r={12} dark style={{ marginBottom: 12 }} />
        <Sk h={36} r={12} dark />
      </div>
      <div style={{ background: N.navy2, margin: '12px 14px 0', borderRadius: 14, padding: '12px 14px', display: 'flex', gap: 12, alignItems: 'center' }}>
        <Sk w={44} h={44} r={12} dark />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}><Sk w={120} h={14} dark /><Sk w={180} h={10} dark /></div>
      </div>
      <div style={{ flex: 1 }}>{[1,2,3,4,5].map(i => <SkChatRow key={i} />)}</div>
    </div>
  )
}

function SkeletonChatDetail() {
  const { tokens: T } = useTheme()
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 16px 14px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <Sk w={34} h={34} r={10} dark />
          <SkCircle size={38} dark />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 5 }}><Sk w={160} h={14} dark /><Sk w={100} h={10} dark /></div>
          <Sk w={34} h={34} r={10} dark />
        </div>
      </div>
      <div style={{ flex: 1, padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {[
          { me: false, lines: [160, 120] },
          { me: true, lines: [180, 100] },
          { me: false, lines: [200] },
          { me: true, lines: [140, 90] },
          { me: false, lines: [170, 130] },
        ].map(({ me, lines }, i) => (
          <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: me ? 'flex-end' : 'flex-start', gap: 2 }}>
            {!me && <Sk w={60} h={10} />}
            <div style={{ maxWidth: '75%', background: me ? N.navy2 : T.card, borderRadius: me ? '14px 0 14px 14px' : '0 14px 14px 14px', padding: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {lines.map((w, j) => <Sk key={j} w={w} h={12} dark={me} />)}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function SkeletonProfile() {
  const { tokens: T } = useTheme()
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: `linear-gradient(180deg,${N.navy} 0%,${N.navy3} 100%)`, padding: '0 18px 24px' }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}><Sk w={34} h={34} r={10} dark /></div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
          <SkCircle size={76} dark />
          <Sk w={160} h={20} dark /><Sk w={200} h={13} dark /><Sk w={130} h={11} dark />
          <div style={{ display: 'flex', gap: 8 }}><Sk w={80} h={32} r={12} dark /><Sk w={80} h={32} r={12} dark /></div>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, padding: '14px 14px 0' }}>
        {[1,2,3,4].map(i => (
          <div key={i} style={{ background: T.card, borderRadius: 14, padding: '12px 8px', boxShadow: '0 2px 6px rgba(0,0,0,0.05)', display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center' }}>
            <Sk w={40} h={16} /><Sk w={50} h={10} />
          </div>
        ))}
      </div>
      <div style={{ margin: '14px 14px 0', background: T.card, borderRadius: 16, padding: 14 }}>
        <Sk w={120} h={14} style={{ marginBottom: 14 }} />
      </div>
      <div style={{ margin: '14px 14px 0', background: T.card, borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' }}>
        <div style={{ display: 'flex' }}>{[1,2,3,4].map(i => <Sk key={i} h={42} r={0} style={{ borderRadius: 0 }} />)}</div>
        <div style={{ padding: 14 }}>
          <Sk h={12} style={{ marginBottom: 6 }} /><Sk h={12} w="80%" style={{ marginBottom: 10 }} />
          <div style={{ display: 'flex', gap: 12 }}><Sk w={40} h={11} /><Sk w={40} h={11} /></div>
        </div>
      </div>
      <div style={{ height: 24 }} />
    </div>
  )
}

function SkeletonNotifications() {
  const { tokens: T } = useTheme()
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}><Sk w={34} h={34} r={10} dark /><Sk w={130} h={18} dark /></div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }} className="scrollbar-hide">
        {[1,2,3,4,5,6,7].map(i => <SkNotifRow key={i} />)}
      </div>
    </div>
  )
}

// ─── SPLASH ───────────────────────────────────────────────────────────────────
// ─── LOGIN ────────────────────────────────────────────────────────────────────

// ─── HOME ─────────────────────────────────────────────────────────────────────


// ─── Social (Chunk 12) ─────────────────────────────────────────────────────────
// GET /users/:id/public-profile (added in the Chunk 12 close-out patch)
// supplies bio/year/university/program/documents/XP for a profile you're
// VIEWING (not your own) - display_name is still carried along from wherever
// navigation originated (a follow list row, a notification body, etc) as a
// fallback while this loads, same as before.


// Stale-while-revalidate cache for the Home screen: on repeat visits within
// the same session, render instantly from cache while a fresh fetch runs
// quietly in the background — no skeleton flash on data you already have.
function CreateModal({ setScreen }: { setScreen: (s: Screen) => void }) {
  const { tokens: T } = useTheme()
  return (
    <div style={{ flex: 1, background: T.pageBg, overflowY: 'auto' }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontWeight: 800, fontSize: 20, color: '#fff' }}>Create</div>
          <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: '#fff' }}>{Ic.close()}</div>
          </button>
        </div>
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {[
          { icon: '📤', label: 'Upload Document', sub: 'PDF, Word, PowerPoint, Images, Notes', action: () => setScreen('upload'), gold: true },
          { icon: '📖', label: 'Publish to Prepza Library', sub: 'Share educational materials · Earn XP', action: () => setScreen('publish-library') },
          { icon: '👥', label: 'Create Group', sub: 'Start a course or study group', action: () => setScreen('group-create') },
          { icon: '🚀', label: 'Share Opportunity', sub: 'Jobs, internships, scholarships, events', action: () => setScreen('share-opp-form') },
        ].map((item, i) => (
          <button key={i} onClick={item.action} style={{ display: 'flex', alignItems: 'center', gap: 14, background: T.card, border: item.gold ? `2px solid ${N.gold}44` : `1px solid ${T.border}`, borderRadius: 16, padding: 16, cursor: 'pointer', textAlign: 'left', boxShadow: item.gold ? `0 4px 20px rgba(201,168,76,0.12)` : '0 2px 8px rgba(0,0,0,0.04)', fontFamily: 'Plus Jakarta Sans' }}>
            <div style={{ width: 50, height: 50, borderRadius: 15, background: item.gold ? `linear-gradient(135deg,${N.gold},${N.goldL})` : `linear-gradient(135deg,${N.navy2},${N.navy3})`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, flexShrink: 0 }}>{item.icon}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 800, fontSize: 14, color: T.text, marginBottom: 3 }}>{item.label}</div>
              <div style={{ fontSize: 12, color: T.textMuted }}>{item.sub}</div>
            </div>
            {item.gold && <Pill text="CORE" />}
          </button>
        ))}
      </div>
    </div>
  )
}

// ─── POST COMPOSER ────────────────────────────────────────────────────────────
// ─── EDU UPLOAD FORM ──────────────────────────────────────────────────────────
function EduUploadForm({ setScreen }: { setScreen: (s: Screen) => void }) {
  const [type, setType] = useState('Notes')
  return (
    <div style={{ flex: 1, overflowY: 'auto', background: N.bg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <TopBar title="Upload Educational Content" onBack={() => window.history.back()} />
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 8 }}>Content Type</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {['Notes','Summary','Guide','Past Paper','Cheat Sheet','Other'].map(t => (
              <button key={t} onClick={() => setType(t)} style={{ padding: '7px 14px', borderRadius: 20, background: type === t ? N.navy : '#F3F4F6', color: type === t ? N.gold : '#6B7280', fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>{t}</button>
            ))}
          </div>
        </div>
        {[['Title', 'e.g. ACT 101 Interest Theory – Complete Notes'], ['Unit / Course', 'e.g. ACT 101'], ['University', 'e.g. Kenyatta University']].map(([l, p]) => (
          <div key={l}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#6B7280', marginBottom: 6 }}>{l}</div>
            <input placeholder={p} style={{ width: '100%', border: '1px solid rgba(0,0,0,0.1)', borderRadius: 12, padding: '12px 14px', fontSize: 13, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: '#374151', boxSizing: 'border-box' }} />
          </div>
        ))}
        <button onClick={() => setScreen('upload')} style={{ background: `linear-gradient(135deg,${N.navy},${N.navy3})`, color: N.gold, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Select & Upload File →</button>
      </div>
    </div>
  )
}

// ─── UPLOAD ───────────────────────────────────────────────────────────────────
function UploadScreen({ setScreen, setActiveDocumentId }: { setScreen: (s: Screen) => void; setActiveDocumentId: (id: number | null) => void }) {
  const { mode, tokens: T } = useTheme()
  const fileRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadStage, setUploadStage] = useState('')
  const [error, setError] = useState('')

  const startUpload = async (file: File) => {
    setError('')

    const ext = getFileExtension(file.name)
    if (!ext || !ALLOWED_UPLOAD_EXTENSIONS.includes(ext)) {
      setError(`Unsupported file type. Allowed: ${ALLOWED_UPLOAD_EXTENSIONS.join(', ').toUpperCase()}`)
      return
    }
    if (file.size > MAX_UPLOAD_SIZE_BYTES) {
      setError(`File exceeds the ${MAX_UPLOAD_SIZE_BYTES / (1024 * 1024)} MB limit`)
      return
    }

    setUploading(true)
    try {
      setUploadStage('Hashing file...')
      const contentHash = await sha256Hex(file)

      setUploadStage('Registering upload...')
      const me = await api<{ id: number; csrf_token: string }>('/me')
      const title = file.name.includes('.') ? file.name.slice(0, file.name.lastIndexOf('.')) : file.name

      const created = await api<{
        document_id: number; status: string; duplicate: boolean
        upload_url?: string; storage_path?: string
      }>('/documents', {
        method: 'POST',
        headers: { 'X-CSRF-Token': me.csrf_token },
        body: JSON.stringify({
          title,
          original_filename: file.name,
          file_size_bytes: file.size,
          content_hash: contentHash,
        }),
      })

      if (!created.duplicate && created.upload_url) {
        setUploadStage('Uploading file...')
        const putRes = await fetch(created.upload_url, { method: 'PUT', body: file })
        if (!putRes.ok) throw new Error('Upload to storage failed - please try again')

        setUploadStage('Confirming upload...')
        try {
          await api(`/documents/${created.document_id}/uploaded`, {
            method: 'POST',
            headers: { 'X-CSRF-Token': me.csrf_token },
          })
        } catch (e) {
          if (e instanceof ApiError && e.status === 409) {
            await new Promise(r => setTimeout(r, 1500))
            await api(`/documents/${created.document_id}/uploaded`, {
              method: 'POST',
              headers: { 'X-CSRF-Token': me.csrf_token },
            })
          } else {
            throw e
          }
        }
      }

      // Study Hub ingestion is local-first. The original File is already the
      // canonical bytes, so persist it before declaring the new Study Hub item
      // ready. This avoids an extra download and guarantees the item is usable
      // offline immediately after ingestion.
      setUploadStage('Preparing offline copy...')
      await saveUploadedFileOffline(created.document_id, file, {
        userId: me.id,
        title,
        fileType: ext,
        contentHash,
      })

      setActiveDocumentId(created.document_id)
      setScreen('upload-share-choice')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'Upload failed - please check your connection and try again.')
    } finally {
      setUploading(false)
      setUploadStage('')
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) startUpload(file)
    e.target.value = ''
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <TopBar title="Upload Document" onBack={() => window.history.back()} />
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', marginTop: -8 }}>Prepza AI processes your document instantly</div>
      </div>
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 18 }}>
        {error && (
          <div style={{ background: 'rgba(201,68,68,0.08)', border: '1px solid rgba(201,68,68,0.25)', borderRadius: 12, padding: '12px 14px', color: '#C94C4C', fontSize: 12, fontWeight: 600 }}>{error}</div>
        )}
        <div
          onDragOver={e => { e.preventDefault(); if (!uploading) setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={e => { e.preventDefault(); setDragging(false); const file = e.dataTransfer.files?.[0]; if (file && !uploading) startUpload(file) }}
          onClick={() => !uploading && fileRef.current?.click()}
          style={{ border: `2px dashed ${dragging ? N.gold : T.border}`, borderRadius: 20, padding: '40px 20px', textAlign: 'center', background: dragging ? 'rgba(201,168,76,0.04)' : T.card, cursor: uploading ? 'wait' : 'pointer', opacity: uploading ? 0.7 : 1, transition: 'all 0.2s' }}
        >
          <input ref={fileRef} type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png" style={{ display: 'none' }} onChange={handleFileChange} disabled={uploading} />
          <div style={{ fontSize: 48, marginBottom: 12 }}>{uploading ? '⏳' : '📤'}</div>
          <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 6 }}>{uploading ? (uploadStage || 'Uploading...') : 'Drop your file here'}</div>
          {!uploading && <div style={{ fontSize: 13, color: T.textMuted, marginBottom: 16 }}>or tap to browse from your device</div>}
          {!uploading && (
            <div style={{ display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap' }}>
              {['PDF','Word','PowerPoint','JPG','PNG'].map(t => <span key={t} style={{ background: (mode === 'dark' ? 'rgba(255,255,255,0.08)' : '#F3F4F6'), color: T.text, fontSize: 10, fontWeight: 600, padding: '4px 10px', borderRadius: 20 }}>{t}</span>)}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── POST-UPLOAD STUDYHUB / LIBRARY CHOICE ────────────────────────────────────
function UploadShareChoiceScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const { tokens: T } = useTheme()
  const [doc, setDoc] = useState<DocumentDetail | null>(null)

  useEffect(() => {
    if (activeDocumentId == null) return
    api<DocumentDetail>(`/documents/${activeDocumentId}`)
      .then(setDoc)
      .catch(() => {})
  }, [activeDocumentId])

  const openStudyHub = () => setScreen('processing')
  const publish = () => setScreen('publish-library')

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 24px' }}>
        <TopBar title="Document added to StudyHub" onBack={openStudyHub} />
      </div>
      <div style={{ padding: '24px 18px 40px', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
        <div style={{ width: 72, height: 72, borderRadius: 22, background: `${N.gold}18`, border: `1px solid ${N.gold}40`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 18, fontSize: 34 }}>✓</div>
        <div style={{ fontWeight: 850, fontSize: 21, color: T.text, marginBottom: 8 }}>Your document is in StudyHub</div>
        <div style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.65, maxWidth: 360, marginBottom: 8 }}>
          {doc?.title ? <><strong style={{ color: T.text }}>{doc.title}</strong> is safely in your personal StudyHub.</> : 'Your document is safely in your personal StudyHub.'}
        </div>
        <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.6, maxWidth: 360, marginBottom: 26 }}>
          It is private by default. Sharing to Library is optional and requires your explicit choice.
        </div>

        <div style={{ width: '100%', maxWidth: 420, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <button onClick={publish} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, border: 'none', borderRadius: 16, padding: '15px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 850, fontSize: 14, boxShadow: `0 6px 22px ${N.gold}35` }}>
            Share to Prepza Library
            <span style={{ display: 'block', fontSize: 11, fontWeight: 600, opacity: 0.7, marginTop: 3 }}>Help other students · Earn XP on approval</span>
          </button>
          <button onClick={openStudyHub} style={{ width: '100%', background: T.card, color: T.text, border: `1px solid ${T.border}`, borderRadius: 16, padding: '14px 16px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 750, fontSize: 14 }}>
            Study my document
          </button>
          <button onClick={openStudyHub} style={{ background: 'none', border: 'none', color: T.textMuted, padding: '10px 8px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 650, fontSize: 12 }}>
            Maybe later
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── PROCESSING ───────────────────────────────────────────────────────────────
function ProcessingScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const { tokens: T } = useTheme()
  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [pollError, setPollError] = useState('')

  useEffect(() => {
    if (activeDocumentId == null) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>

    const poll = async () => {
      try {
        const result = await api<DocumentDetail>(`/documents/${activeDocumentId}`)
        if (cancelled) return
        setDoc(result)
        if (result.status === 'ready' || result.status === 'failed') return
        timer = setTimeout(poll, 2500)
      } catch (e) {
        if (cancelled) return
        setPollError(e instanceof ApiError ? e.message : 'Lost connection while checking status - retrying...')
        timer = setTimeout(poll, 2500)
      }
    }
    poll()

    return () => { cancelled = true; clearTimeout(timer) }
  }, [activeDocumentId])

  const status = doc?.status
  const stageLabel = status === 'uploading' ? 'Uploading document…'
    : status === 'processing' ? 'Extracting content & analysing…'
    : status === 'ready' ? 'Ready to study!'
    : status === 'failed' ? 'Something went wrong'
    : 'Getting started…'

  if (activeDocumentId == null) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.navy, padding: 32, textAlign: 'center' }}>
        <div style={{ color: '#fff', fontWeight: 800, fontSize: 18, marginBottom: 10 }}>No upload in progress</div>
        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginBottom: 28 }}>Head back to upload a document to see its processing status here.</div>
        <button onClick={() => setScreen('upload')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '12px 28px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Go to Upload</button>
      </div>
    )
  }

  if (status === 'failed') {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.navy, padding: 32, textAlign: 'center' }}>
        <div style={{ fontSize: 44, marginBottom: 16 }}>⚠️</div>
        <div style={{ color: '#fff', fontWeight: 800, fontSize: 18, marginBottom: 10 }}>Processing failed</div>
        <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginBottom: 28, maxWidth: 280 }}>{doc?.error_message || 'This document could not be processed. Please try uploading again.'}</div>
        <button onClick={() => setScreen('upload')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '12px 28px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Try Again</button>
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: N.navy, padding: 32 }}>
      <div style={{ position: 'relative', width: 120, height: 120, marginBottom: 36 }}>
        <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: '3px solid rgba(201,168,76,0.18)' }} />
        <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: '3px solid transparent', borderTopColor: N.gold, animation: 'spin-slow 1.1s linear infinite' }} />
        <div style={{ position: 'absolute', inset: 14, borderRadius: '50%', background: 'rgba(201,168,76,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <img src="/icon-192.png" alt="Prepza" style={{ width: 52, height: 52, borderRadius: 14 }} />
        </div>
      </div>
      <div style={{ color: '#fff', fontWeight: 800, fontSize: 20, marginBottom: 6, textAlign: 'center' }}>{stageLabel}</div>
      <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 13, textAlign: 'center', marginBottom: 20 }}>{doc?.title || 'Your document'}</div>
      {pollError && <div style={{ color: '#E8A54C', fontSize: 12, marginBottom: 20, textAlign: 'center' }}>{pollError}</div>}
      {status === 'ready' && (
        <button onClick={() => setScreen('doc-ready')} style={{ marginTop: 12, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 44px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 4px 20px rgba(201,168,76,0.4)' }}>
          View Document →
        </button>
      )}
    </div>
  )
}

// ─── DOC READY ────────────────────────────────────────────────────────────────
// ─── DOCUMENT STUDY ───────────────────────────────────────────────────────────
// Stale-while-revalidate cache keyed by document ID: reopening a document
// already viewed this session renders instantly while a fresh fetch runs
// quietly in the background.
const DOC_CACHE: Record<number, DocumentDetail> = {}
function DocumentStudyScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const { tokens: T } = useTheme()
  const [tab, setTab] = useState<'doc'|'ai'|'tools'>('doc')
  const [askInput, setAskInput] = useState('')
  const [showMenu, setShowMenu] = useState(false)
  const [showDots, setShowDots] = useState(false)
  const [showRename, setShowRename] = useState(false)
  const [showDelete, setShowDelete] = useState(false)
  const [showReport, setShowReport] = useState(false)
  const [reportBusy, setReportBusy] = useState(false)
  const [reportError, setReportError] = useState('')
  const [reportSubmitted, setReportSubmitted] = useState(false)
  const [renameVal, setRenameVal] = useState('')
  const [savedToLib, setSavedToLib] = useState(false)
  const [saveOfflineBusy, setSaveOfflineBusy] = useState(false)
  const [saveOfflineError, setSaveOfflineError] = useState('')
  const [messages, setMessages] = useState([
    { role: 'ai', text: "I've read your document. I can explain concepts, quiz you, create flashcards, or summarise any section. What would you like to do?" },
  ])

  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [docLoadError, setDocLoadError] = useState('')
  const [heartbeatCsrf, setHeartbeatCsrf] = useState('')
  useEffect(() => {
    rememberLastStudyDocument(activeDocumentId)
  }, [activeDocumentId])

  useEffect(() => {
    if (activeDocumentId == null) return
    let cancelled = false
    let offlineUrl: string | null = null
    const cached = DOC_CACHE[activeDocumentId]
    if (cached) { setDoc(cached); setRenameVal(cached.title) }
    api<DocumentDetail>(`/documents/${activeDocumentId}`)
      .then(async d => {
        if (cancelled) return
        const userId = Number(localStorage.getItem('prepza-offline-user-id') || 0)
        let localUrl: string | null = null
        if (Number.isInteger(userId) && userId > 0 && d.content_hash) {
          localUrl = await getOfflineStudyDocumentUrlByContentHash(d.content_hash, userId)
        }
        if (localUrl) {
          offlineUrl = localUrl
          const localDoc = { ...d, view_url: localUrl }
          setDoc(localDoc); setRenameVal(d.title); setSavedToLib(true); setDocLoadError(''); DOC_CACHE[activeDocumentId] = localDoc
        } else {
          setDoc(d); setRenameVal(d.title); setDocLoadError(''); DOC_CACHE[activeDocumentId] = d
        }
      })
      .catch(async e => {
        if (cancelled) return
        const userId = Number(localStorage.getItem('prepza-offline-user-id') || 0)
        if (Number.isInteger(userId) && userId > 0) {
          try {
            const saved = await getSavedStudyHubOffline(activeDocumentId, userId)
            const url = await getOfflineStudyDocumentUrl(activeDocumentId, userId)
            if (!cancelled && saved && url) {
              offlineUrl = url
              setDoc({
                id: activeDocumentId,
                title: saved.title || 'Saved study document',
                original_filename: saved.title || 'Study document',
                status: 'ready',
                file_type: saved.fileType || 'pdf',
                file_size_bytes: null,
                content_hash: saved.contentHash || null,
                page_count: saved.pageCount || null,
                error_message: null,
                view_url: url,
                materials: [],
                created_at: new Date(saved.savedAt).toISOString(),
              })
              setRenameVal(saved.title || 'Saved study document')
              setSavedToLib(true)
              setDocLoadError('')
              return
            }
          } catch { /* fall through to the normal error state */ }
        }
        if (!cancelled) setDocLoadError(e instanceof ApiError ? e.message : 'Could not load this document. It may not be saved for offline study yet.')
      })
    return () => {
      cancelled = true
      if (offlineUrl) URL.revokeObjectURL(offlineUrl)
    }
  }, [activeDocumentId])

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setHeartbeatCsrf(me.csrf_token)).catch(() => {})
  }, [])

  // Study Hub timing is owned by the global tracker installed above.
  // There is deliberately no per-document 20-second heartbeat here.


  const REPORT_REASONS: { label: string; value: string }[] = [
    { label: 'Inaccurate content', value: 'inaccurate_content' },
    { label: 'Plagiarised material', value: 'plagiarised_material' },
    { label: 'Inappropriate content', value: 'inappropriate_content' },
    { label: 'Copyright violation', value: 'copyright_violation' },
    { label: 'Wrong academic category or year', value: 'wrong_academic_category_year' },
    { label: 'Other', value: 'other' },
  ]

  const submitReport = async (reason: string) => {
    if (activeDocumentId == null || reportBusy) return
    setReportBusy(true)
    setReportError('')
    try {
      await api(`/documents/${activeDocumentId}/report`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': heartbeatCsrf },
        body: JSON.stringify({ reason }),
      })
      setReportSubmitted(true)
    } catch (e) {
      setReportError(e instanceof ApiError ? e.message : 'Could not submit your report. Please try again.')
    } finally {
      setReportBusy(false)
    }
  }

  // Only pending while there's an active document whose fetch hasn't yet
  // resolved (success or error) - if no document is selected, this stays
  // false so the "no document selected" state below can render immediately.
  const docLoading = activeDocumentId != null && doc === null && !docLoadError
  if (docLoading) return <SkeletonDocument />

  if (activeDocumentId == null) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: T.pageBg, padding: 32, textAlign: 'center' }}>
        <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 8 }}>No document selected</div>
        <div style={{ color: T.textMuted, fontSize: 13, marginBottom: 24 }}>Open a document from Home to study it here.</div>
        <button onClick={() => setScreen('home')} style={{ background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 14, border: 'none', borderRadius: 14, padding: '12px 28px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Go Home</button>
      </div>
    )
  }
  const saveForOfflineStudy = async () => {
    if (activeDocumentId == null || saveOfflineBusy) return
    setSaveOfflineBusy(true)
    setSaveOfflineError('')
    try {
      await saveStudyHubDocumentOffline(activeDocumentId)
      setSavedToLib(true)
    } catch (e) {
      setSaveOfflineError(e instanceof Error ? e.message : 'Could not save this document for offline study.')
    } finally {
      setSaveOfflineBusy(false)
    }
  }

  const sendMsg = () => {
    if (!askInput.trim()) return
    const q = askInput; setAskInput('')
    setMessages(m => [...m, { role: 'user', text: q }])
    setTimeout(() => setMessages(m => [...m, { role: 'ai', text: `Great question about "${q}"! In the context of your ACT 101 notes, here's a clear explanation…` }]), 900)
  }

  const doExplain = () => {
    setShowMenu(false); setTab('ai')
    setMessages(m => [...m, { role: 'user', text: 'Explain the compound interest accumulation function' }, { role: 'ai', text: 'The compound interest accumulation function is:\n\nA(t) = A(0)(1+i)ᵗ\n\nWhere:\n• A(0) = initial principal\n• i = effective annual interest rate\n• t = time in years\n\nKey insight: under compound interest, each period\'s interest is reinvested, so you earn "interest on interest."\n\nKenyan example: KES 10,000 at 8% for 3 years:\nA(3) = 10,000 × (1.08)³ = KES 12,597.12 ✓' }])
  }
  const doSimplify = () => {
    setShowMenu(false); setTab('ai')
    setMessages(m => [...m, { role: 'user', text: 'Simplify this section for me' }, { role: 'ai', text: '✨ Simplified version:\n\nCompound interest = money growing on top of money that already grew.\n\nThink of it like a snowball rolling downhill — it gets bigger every time it rolls.\n\nSimple rule: A(t) = Starting amount × (1 + rate)^years\n\nAt 8% interest:\n• Year 1: KES 10,000 → KES 10,800\n• Year 2: KES 10,800 → KES 11,664\n• Year 3: KES 11,664 → KES 12,597' }])
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <button onClick={() => setScreen('home')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: 14, color: '#fff' }} className="line-clamp-1">{doc?.title || 'Loading…'}</div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>{doc?.page_count != null ? `${doc.page_count} pages · ` : ''}{doc?.status ? doc.status.charAt(0).toUpperCase() + doc.status.slice(1) : ''}</div>
          </div>
          <div style={{ position: 'relative' }}>
            <button onClick={() => setShowDots(v => !v)} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.dots()}</div></button>
            {showDots && (
              <div style={{ position: 'absolute', right: 0, top: 40, background: T.card, borderRadius: 14, boxShadow: '0 8px 24px rgba(0,0,0,0.15)', zIndex: 20, width: 160, overflow: 'hidden' }}>
                <button onClick={() => { setShowDots(false); setShowRename(true) }} style={{ display: 'block', width: '100%', padding: '12px 16px', background: 'none', border: 'none', textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: T.text, cursor: 'pointer' }}>Rename</button>
                <button onClick={() => { setShowDots(false); setScreen('share-sheet') }} style={{ display: 'block', width: '100%', padding: '12px 16px', background: 'none', border: 'none', textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: T.text, cursor: 'pointer' }}>Share</button>
                <button onClick={() => { setShowDots(false); void saveForOfflineStudy() }} style={{ display: 'block', width: '100%', padding: '12px 16px', background: 'none', border: 'none', textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: T.text, cursor: 'pointer' }}>Save for offline study</button>
                <button onClick={() => { setShowDots(false); setShowDelete(true) }} style={{ display: 'block', width: '100%', padding: '12px 16px', background: 'none', border: 'none', textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: '#C94C4C', cursor: 'pointer' }}>Delete</button>
                <button onClick={() => { setShowDots(false); setReportSubmitted(false); setReportError(''); setShowReport(true) }} style={{ display: 'block', width: '100%', padding: '12px 16px', background: 'none', border: 'none', textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: '#C94C4C', cursor: 'pointer' }}>Report</button>
              </div>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', background: 'rgba(255,255,255,0.08)', borderRadius: 12, padding: 3, gap: 2 }}>
          {(['doc','ai','tools'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{ flex: 1, padding: '7px 0', borderRadius: 9, background: tab === t ? N.gold : 'transparent', color: tab === t ? N.navy : 'rgba(255,255,255,0.55)', fontWeight: 700, fontSize: 11, border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', transition: 'all 0.2s' }}>
              {t === 'doc' ? '📄 Document' : t === 'ai' ? '✦ AI Chat' : '🛠 Tools'}
            </button>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: 18 }} className="scrollbar-hide">
        {tab === 'doc' && (
          <div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 14, overflowX: 'auto' }} className="scrollbar-hide">
              <button onClick={() => setScreen('summary')} style={{ flexShrink: 0, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, border: `1px solid ${N.gold}33`, color: N.gold, fontSize: 11, fontWeight: 700, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Summarize</button>
              <button onClick={() => setScreen('quiz')} style={{ flexShrink: 0, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, border: `1px solid ${N.gold}33`, color: N.gold, fontSize: 11, fontWeight: 700, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Quiz Me</button>
              <button onClick={() => setScreen('flashcards')} style={{ flexShrink: 0, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, border: `1px solid ${N.gold}33`, color: N.gold, fontSize: 11, fontWeight: 700, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Flashcards</button>
              <button onClick={() => setScreen('mind-map')} style={{ flexShrink: 0, background: `linear-gradient(135deg,${N.navy2},${N.navy3})`, border: `1px solid ${N.gold}33`, color: N.gold, fontSize: 11, fontWeight: 700, padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Mind Map</button>
            </div>
            {docLoadError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 12 }}>{docLoadError}</div>}
            {doc?.view_url ? (
              <div style={{ background: T.card, borderRadius: 16, overflow: 'hidden', boxShadow: '0 2px 10px rgba(0,0,0,0.06)', height: '60vh' }}>
                {doc.file_type && ['jpg', 'jpeg', 'png'].includes(doc.file_type) ? (
                  <img src={doc.view_url} alt={doc.title} style={{ width: '100%', height: '100%', objectFit: 'contain', background: '#000' }} />
                ) : (
                  <iframe src={doc.view_url} title={doc.title} style={{ width: '100%', height: '100%', border: 'none' }} />
                )}
              </div>
            ) : (
              <div style={{ background: T.card, borderRadius: 16, padding: 18, boxShadow: '0 2px 10px rgba(0,0,0,0.06)', textAlign: 'center' }}>
                <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 6 }}>{doc?.title || 'Loading document…'}</div>
                <div style={{ fontSize: 12, color: T.textMuted }}>{doc ? 'Preview not available for this file type - use the tools above to study it.' : 'Fetching your document…'}</div>
              </div>
            )}
          </div>
        )}

        {tab === 'ai' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {messages.map((m, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', gap: 10, alignItems: 'flex-start' }}>
                {m.role === 'ai' && <div style={{ width: 30, height: 30, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: 9, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, flexShrink: 0 }}>✦</div>}
                <div style={{ maxWidth: '78%', background: m.role === 'user' ? `linear-gradient(135deg,${N.navy},${N.navy3})` : '#fff', borderRadius: m.role === 'user' ? '14px 0 14px 14px' : '0 14px 14px 14px', padding: '11px 14px', boxShadow: '0 2px 8px rgba(0,0,0,0.07)' }}>
                  <div style={{ fontSize: 13, color: m.role === 'user' ? '#fff' : T.text, lineHeight: 1.7 }}>{m.text}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === 'tools' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[
              { icon: Ic.book('w-5 h-5'), title: 'Flashcards', sub: '35 cards generated', action: () => setScreen('flashcards'), color: N.gold },
              { icon: Ic.check('w-5 h-5'), title: 'Practice Quiz', sub: '15 MCQ questions', action: () => setScreen('quiz'), color: '#4C7BC9' },
              { icon: Ic.book('w-5 h-5'), title: 'Summary', sub: '2-page condensed notes', action: () => setScreen('summary'), color: '#4CC97B' },
              { icon: Ic.podcast('w-5 h-5'), title: 'Study Podcast', sub: '9 min AI-generated episode', action: () => setScreen('podcast-player'), color: '#C94C4C' },
              { icon: Ic.explore('w-5 h-5'), title: 'Mind Map', sub: 'Visual concept overview', action: () => setScreen('mind-map'), color: '#9B59B6' },
              { icon: Ic.download('w-5 h-5'), title: 'Offline ready', sub: 'Complete study copy is stored on this device', action: () => {}, color: T.textMuted },
            ].map((t, i) => (
              <button key={i} onClick={t.action} style={{ display: 'flex', alignItems: 'center', gap: 12, background: T.card, border: '1px solid rgba(0,0,0,0.04)', borderRadius: 14, padding: '13px 15px', cursor: 'pointer', boxShadow: '0 2px 8px rgba(0,0,0,0.04)', fontFamily: 'Plus Jakarta Sans' }}>
                <div style={{ width: 44, height: 44, background: t.color + '18', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0 }}>{t.icon}</div>
                <div style={{ flex: 1, textAlign: 'left' }}>
                  <div style={{ fontWeight: 700, fontSize: 13, color: T.text }}>{t.title}</div>
                  <div style={{ fontSize: 11, color: T.textMuted }}>{t.sub}</div>
                </div>
                <div style={{ color: T.textMuted }}>{Ic.chevR()}</div>
              </button>
            ))}
          </div>
        )}
      </div>

      <div style={{ padding: '10px 14px 14px', background: T.card, borderTop: '1px solid rgba(0,0,0,0.06)' }}>
        {savedToLib && <div style={{ background: '#D1FAE5', color: '#065F46', fontSize: 12, fontWeight: 700, padding: '8px 14px', borderRadius: 10, marginBottom: 8, textAlign: 'center' }}>Saved for offline study</div>}
        {saveOfflineBusy && <div style={{ background: T.pageBg, color: T.textMuted, fontSize: 12, fontWeight: 700, padding: '8px 14px', borderRadius: 10, marginBottom: 8, textAlign: 'center' }}>Saving this study offline…</div>}
        {saveOfflineError && <div style={{ background: '#FEE2E2', color: '#991B1B', fontSize: 12, fontWeight: 700, padding: '8px 14px', borderRadius: 10, marginBottom: 8, textAlign: 'center' }}>{saveOfflineError}</div>}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', background: T.pageBg, borderRadius: 14, padding: '8px 12px', border: '1px solid rgba(11,20,55,0.08)' }}>
          <input value={askInput} onChange={e => setAskInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && sendMsg()} placeholder="Ask about this document…" style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 13, color: T.text, fontFamily: 'Plus Jakarta Sans' }} />
          <button onClick={sendMsg} style={{ width: 32, height: 32, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 9, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: T.text }}>{Ic.send('w-4 h-4')}</div>
          </button>
        </div>
      </div>

      {/* Rename modal */}
      {showRename && (
        <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 50 }}>
          <div style={{ background: T.card, borderRadius: 20, padding: 24, width: '100%' }}>
            <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 16 }}>Rename Document</div>
            <input value={renameVal} onChange={e => setRenameVal(e.target.value)} style={{ width: '100%', border: `1px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, boxSizing: 'border-box' }} />
            <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
              <button onClick={() => setShowRename(false)} style={{ flex: 1, background: '#F3F4F6', border: 'none', borderRadius: 12, padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, color: T.text }}>Cancel</button>
              <button onClick={() => setShowRename(false)} style={{ flex: 1, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 12, padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 13, color: N.navy }}>Save</button>
            </div>
          </div>
        </div>
      )}
      {/* Delete modal */}
      {showDelete && (
        <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 50 }}>
          <div style={{ background: T.card, borderRadius: 20, padding: 24, width: '100%' }}>
            <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 8 }}>Delete Document?</div>
            <div style={{ fontSize: 13, color: T.textMuted, marginBottom: 20 }}>This will permanently remove "ACT 101 – Interest Theory" from your library.</div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => setShowDelete(false)} style={{ flex: 1, background: '#F3F4F6', border: 'none', borderRadius: 12, padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, color: T.text }}>Cancel</button>
              <button onClick={() => { setShowDelete(false); setScreen('home') }} style={{ flex: 1, background: '#C94C4C', border: 'none', borderRadius: 12, padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 13, color: '#fff' }}>Delete</button>
            </div>
          </div>
        </div>
      )}
      {/* Report modal */}
      {showReport && (
        <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 50 }}>
          <div style={{ background: T.card, borderRadius: 20, padding: 24, width: '100%' }}>
            {reportSubmitted ? (
              <>
                <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 8 }}>Report submitted</div>
                <div style={{ fontSize: 13, color: T.textMuted, marginBottom: 20 }}>Thanks - we've received your report and will take a look.</div>
                <button onClick={() => setShowReport(false)} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, border: 'none', borderRadius: 12, padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 800, fontSize: 13, color: N.navy }}>Done</button>
              </>
            ) : (
              <>
                <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 14 }}>Report Document</div>
                {REPORT_REASONS.map((r) => (
                  <button key={r.value} onClick={() => submitReport(r.value)} disabled={reportBusy} style={{ display: 'block', width: '100%', background: '#F8F9FC', border: 'none', borderRadius: 10, padding: '11px 14px', marginBottom: 8, textAlign: 'left', fontSize: 13, fontFamily: 'Plus Jakarta Sans', fontWeight: 600, color: T.text, cursor: reportBusy ? 'wait' : 'pointer', opacity: reportBusy ? 0.6 : 1 }}>{r.label}</button>
                ))}
                {reportError && <div style={{ color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 8 }}>{reportError}</div>}
                <button onClick={() => setShowReport(false)} disabled={reportBusy} style={{ width: '100%', background: '#F3F4F6', border: 'none', borderRadius: 12, padding: '12px 0', marginTop: 4, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', fontWeight: 700, fontSize: 13, color: T.text }}>Cancel</button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── NATIVE DOCUMENT READER ──────────────────────────────────────────────────

// ─── AI TUTOR ─────────────────────────────────────────────────────────────────
// ─── NEW CHAT ─────────────────────────────────────────────────────────────────
// Chat options UI is owned by screens/chat/ChatOptionsScreen.tsx.
// ─── PUBLISH TO LIBRARY ───────────────────────────────────────────────────────

type PublishableDoc = { id: number; title: string; status: string; file_type: string | null; page_count: number | null }

function PublishLibraryScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const { tokens: T } = useTheme()
  const [step, setStep] = useState(1)

  const [csrfToken, setCsrfToken] = useState('')
  const [docs, setDocs] = useState<PublishableDoc[]>([])
  const [docsLoading, setDocsLoading] = useState(true)
  const [docsError, setDocsError] = useState('')

  const [selectedDocId, setSelectedDocId] = useState<number | null>(null)
  const [title, setTitle] = useState('')
  const [matType, setMatType] = useState(LIBRARY_MATERIAL_TYPES[0].value)
  const [desc, setDesc] = useState('')
  const [rightsChecked, setRightsChecked] = useState(false)

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [submittedStatus, setSubmittedStatus] = useState<string | null>(null)

  useEffect(() => {
    api<{ csrf_token: string }>('/me').then(me => setCsrfToken(me.csrf_token)).catch(() => {})
    api<{ documents: { id: number; title: string; status: string; file_type: string | null; page_count: number | null }[] }>('/documents')
      .then(res => {
        const available = res.documents.filter(d => d.status === 'ready' || d.id === activeDocumentId)
        setDocs(available)
        const uploaded = activeDocumentId == null ? null : available.find(d => d.id === activeDocumentId)
        if (uploaded) {
          setSelectedDocId(uploaded.id)
          setTitle(uploaded.title)
        }
      })
      .catch(() => setDocsError('Could not load your documents - check your connection and try again.'))
      .finally(() => setDocsLoading(false))
  }, [activeDocumentId])

  const selectedDoc = selectedDocId == null ? null : docs.find(d => d.id === selectedDocId) || null
  const canProceed1 = selectedDocId != null && title.trim().length > 0 && selectedDoc?.status === 'ready'
  const canProceed2 = true
  const canProceed3 = rightsChecked

  const submit = async () => {
    if (selectedDocId == null) return
    setSubmitting(true)
    setSubmitError('')
    setStep(4)
    try {
      const result = await api<{ publication_id?: number; status?: string; duplicate?: boolean; published?: boolean; message?: string }>('/library/publish', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({
          document_id: selectedDocId,
          title: title.trim(),
          description: desc.trim() || undefined,
          material_type: matType,
        }),
      })
      setSubmittedStatus(result.duplicate ? 'already_in_library' : (result.status || 'pending'))
      setStep(5)
    } catch (e) {
      setSubmitError(e instanceof ApiError ? e.message : 'Something went wrong submitting your material. Please try again.')
      setStep(3)
    } finally {
      setSubmitting(false)
    }
  }

  const stepLabel = ['Select Document', 'Add Details', 'Confirm Rights', '', ''][step - 1]

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      {/* Header */}
      <div style={{ background: N.navy, padding: '0 18px 16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: step <= 3 ? 14 : 0 }}>
          <button onClick={() => step > 1 && step <= 3 ? setStep(s => s - 1) : setScreen('create-modal')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 17, color: '#fff' }}>Publish to Prepza Library</div>
            {step <= 3 && <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>Step {step} of 3 — {stepLabel}</div>}
          </div>
        </div>
        {step <= 3 && (
          <div style={{ display: 'flex', gap: 4 }}>
            {[1, 2, 3].map(s => (
              <div key={s} style={{ flex: 1, height: 3, borderRadius: 99, background: s <= step ? N.gold : 'rgba(255,255,255,0.15)', transition: 'background 0.3s' }} />
            ))}
          </div>
        )}
      </div>

      {/* Step 1: Select doc + title */}
      {step === 1 && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
          <div style={{ background: `${N.gold}10`, border: `1px solid ${N.gold}30`, borderRadius: 14, padding: '12px 16px', marginBottom: 20 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: N.gold, marginBottom: 4 }}>Free to publish · Shared immediately</div>
            <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.6 }}>Share educational materials with students across Kenya. Once published, students can save them to Study Hub. Reported material can be taken down by admins.</div>
          </div>
          <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 10 }}>Select a document</div>
          {docsLoading ? (
            <div style={{ fontSize: 12, color: T.textMuted, padding: '12px 0' }}>Loading your documents…</div>
          ) : docsError ? (
            <div style={{ fontSize: 12, color: '#C94C4C', fontWeight: 600, padding: '12px 0' }}>{docsError}</div>
          ) : docs.length === 0 ? (
            <EmptyState icon="📄" title="No ready documents" sub="Upload and finish processing a document before publishing it to the library." action="Upload Document" onAction={() => setScreen('upload')} />
          ) : docs.map(d => (
            <div key={d.id} onClick={() => { setSelectedDocId(d.id); setTitle(d.title) }}
              style={{ background: T.card, borderRadius: 14, padding: '14px 16px', marginBottom: 10, border: `2px solid ${selectedDocId === d.id ? N.gold : 'rgba(0,0,0,0.06)'}`, cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'center', boxShadow: selectedDocId === d.id ? `0 4px 16px ${N.gold}20` : '0 2px 8px rgba(0,0,0,0.04)', transition: 'all 0.2s' }}>
              <div style={{ width: 40, height: 44, background: '#F3F4F6', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <svg width="20" height="24" viewBox="0 0 20 24" fill="none"><path d="M4 0h8l8 8v16H4V0z" fill="#E5E7EB"/><path d="M12 0l8 8h-8V0z" fill="#D1D5DB"/><rect x="6" y="12" width="8" height="1.5" rx="0.75" fill="#9CA3AF"/><rect x="6" y="15" width="6" height="1.5" rx="0.75" fill="#9CA3AF"/><rect x="6" y="18" width="7" height="1.5" rx="0.75" fill="#9CA3AF"/></svg>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.title}</div>
                <div style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>
                  {(d.file_type || '').toUpperCase()}{d.page_count != null ? ` · ${d.page_count} pages` : ''}{d.status !== 'ready' ? ` · ${d.status === 'processing' ? 'Preparing…' : d.status}` : ''}
                </div>
              </div>
              {selectedDocId === d.id && <div style={{ color: N.gold, flexShrink: 0 }}>{Ic.check('w-5 h-5')}</div>}
            </div>
          ))}
          <div style={{ marginTop: 8, marginBottom: 20 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 8 }}>Publication title</div>
            <input value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. ACT 101 Lecture Notes – Semester 1" maxLength={200} style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, boxSizing: 'border-box' }} />
            <div style={{ fontSize: 11, color: T.textMuted, marginTop: 6 }}>This will be the public title visible to other students.</div>
          </div>
          <button onClick={() => canProceed1 && setStep(2)} style={{ width: '100%', background: canProceed1 ? `linear-gradient(135deg,${N.gold},${N.goldL})` : '#E5E7EB', color: canProceed1 ? N.navy : T.textMuted, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: canProceed1 ? 'pointer' : 'not-allowed', fontFamily: 'Plus Jakarta Sans' }}>
            {selectedDoc?.status === 'ready' ? 'Continue' : 'Document still preparing…'}
          </button>
        </div>
      )}

      {/* Step 2: Details */}
      {step === 2 && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 8 }}>Material Type</div>
            <select value={matType} onChange={e => setMatType(e.target.value)} style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, background: T.card, appearance: 'none' }}>
              {LIBRARY_MATERIAL_TYPES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: T.text, marginBottom: 8 }}>Description <span style={{ color: T.textMuted, fontWeight: 500 }}>(optional)</span></div>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={3} maxLength={1000} placeholder="What does this material cover? Who is it useful for?" style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 14, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, resize: 'none', lineHeight: 1.6, boxSizing: 'border-box' }} />
          </div>
          <button onClick={() => canProceed2 && setStep(3)} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>
            Continue
          </button>
        </div>
      )}

      {/* Step 3: Rights confirmation */}
      {step === 3 && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
          <div style={{ background: T.card, borderRadius: 16, padding: '18px 18px', marginBottom: 16, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
            <div style={{ fontWeight: 800, fontSize: 16, color: T.text, marginBottom: 12 }}>Publishing: {title}</div>
            {[['Type', materialTypeLabel(matType)]].map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #F3F4F6' }}>
                <span style={{ fontSize: 12, color: T.textMuted }}>{k}</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: T.text, maxWidth: 180, textAlign: 'right' }}>{v}</span>
              </div>
            ))}
          </div>
          <div style={{ background: '#FEF9F0', border: '1px solid rgba(201,168,76,0.25)', borderRadius: 14, padding: '16px 16px', marginBottom: 20 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: '#92400E', marginBottom: 8 }}>Content responsibility</div>
            <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.75 }}>
              You are responsible for ensuring you have the right or permission to share this material. Prepza does not claim ownership of student-uploaded content. Unauthorised sharing of copyrighted materials may result in removal of the content and restrictions on your account.
            </div>
          </div>
          {submitError && (
            <div style={{ background: 'rgba(201,68,68,0.08)', border: '1px solid rgba(201,68,68,0.25)', borderRadius: 12, padding: '12px 14px', color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 16 }}>{submitError}</div>
          )}
          <div onClick={() => setRightsChecked(r => !r)} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', padding: '14px 16px', background: T.card, borderRadius: 14, border: `2px solid ${rightsChecked ? N.gold : 'rgba(0,0,0,0.08)'}`, cursor: 'pointer', marginBottom: 16, transition: 'border-color 0.2s' }}>
            <div style={{ width: 22, height: 22, borderRadius: 6, border: `2px solid ${rightsChecked ? N.gold : T.textMuted}`, background: rightsChecked ? N.gold : T.card, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, transition: 'all 0.2s' }}>
              {rightsChecked && <div style={{ color: T.text }}>{Ic.check('w-3 h-3')}</div>}
            </div>
            <div style={{ fontSize: 13, color: T.text, lineHeight: 1.6 }}>I confirm that I have the right or permission to share this material, and I agree to Prepza's <span style={{ color: N.gold, fontWeight: 700 }}>Terms of Service</span>, <span style={{ color: N.gold, fontWeight: 700 }}>Content Policy</span>, and <span style={{ color: N.gold, fontWeight: 700 }}>Copyright Policy</span>.</div>
          </div>
          <button onClick={() => canProceed3 && !submitting && submit()} style={{ width: '100%', background: canProceed3 ? `linear-gradient(135deg,${N.gold},${N.goldL})` : '#E5E7EB', color: canProceed3 ? N.navy : T.textMuted, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: canProceed3 ? 'pointer' : 'not-allowed', fontFamily: 'Plus Jakarta Sans', boxShadow: canProceed3 ? `0 6px 24px ${N.gold}40` : 'none' }}>
            Publish to Library
          </button>
          <button onClick={() => setScreen('home')} style={{ width: '100%', background: 'transparent', color: T.textMuted, fontSize: 12, fontWeight: 600, border: 'none', padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Cancel — don't publish</button>
        </div>
      )}

      {/* Step 4: Submitting */}
      {step === 4 && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 20, padding: '0 32px', textAlign: 'center' }}>
          <div style={{ width: 72, height: 72, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ width: 28, height: 28, border: '3px solid rgba(11,20,55,0.4)', borderTopColor: N.navy, borderRadius: '50%', animation: 'spin-slow 0.7s linear infinite' }} />
          </div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 18, color: T.text, marginBottom: 6 }}>Submitting…</div>
            <div style={{ fontSize: 13, color: T.textMuted }}>Uploading to Prepza Library</div>
          </div>
        </div>
      )}

      {/* Step 5: Published */}
      {step === 5 && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px 20px' }} className="scrollbar-hide">
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <div style={{ width: 72, height: 72, background: submittedStatus === 'already_in_library' ? `${N.gold}18` : 'rgba(76,201,123,0.1)', borderRadius: '50%', border: `3px solid ${submittedStatus === 'already_in_library' ? N.gold : '#4CC97B'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px', fontSize: 28 }}>{submittedStatus === 'already_in_library' ? '✓' : '📥'}</div>
            <div style={{ fontWeight: 800, fontSize: 20, color: T.text, marginBottom: 8 }}>{submittedStatus === 'already_in_library' ? 'Already in Prepza Library' : 'Published to Prepza Library'}</div>
            <div style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.65 }}>
              {submittedStatus === 'already_in_library'
                ? 'This exact document is already represented in the Prepza Library. Your personal StudyHub copy remains yours, and no duplicate Library submission was created.'
                : 'Your material is now in the Prepza Library. Other students can see it and save it to Study Hub. If it is later reported and found unsuitable, an admin can take it down.'}
            </div>
          </div>

          <div style={{ background: T.card, borderRadius: 14, padding: '14px 16px', marginBottom: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.text, marginBottom: 4 }}>Library moderation</div>
            <div style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.65 }}>Students can report a published document when it is inaccurate, inappropriate, plagiarised, or not appropriate for their academic context. Admins review reports and can remove the item.</div>
          </div>

          <button onClick={() => setScreen('library')} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: `0 6px 24px ${N.gold}40` }}>
            Go to My Library
          </button>
          <button onClick={() => setScreen('home')} style={{ width: '100%', background: 'transparent', color: T.textMuted, fontSize: 12, fontWeight: 600, border: 'none', padding: '12px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Back to Home</button>
        </div>
      )}
    </div>
  )
}



// ─── STUDY STREAK ─────────────────────────────────────────────────────────────

function EmptyState({ icon, title, sub, action, onAction }: { icon: string; title: string; sub: string; action?: string; onAction?: () => void }) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 32px', textAlign: 'center', gap: 14 }}>
      <div style={{ fontSize: 52, lineHeight: 1, marginBottom: 4 }}>{icon}</div>
      <div style={{ fontWeight: 800, fontSize: 18, color: N.navy }}>{title}</div>
      <div style={{ fontSize: 13, color: '#9CA3AF', lineHeight: 1.65, maxWidth: 260 }}>{sub}</div>
      {action && onAction && (
        <button onClick={onAction} style={{ marginTop: 8, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 13, border: 'none', borderRadius: 14, padding: '12px 24px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: `0 4px 16px rgba(201,168,76,0.35)` }}>{action}</button>
      )}
    </div>
  )
}

function ErrorState({ onRetry }: { onRetry?: () => void }) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 32px', textAlign: 'center', gap: 14 }}>
      <div style={{ fontSize: 52 }}>⚠️</div>
      <div style={{ fontWeight: 800, fontSize: 18, color: N.navy }}>Something went wrong</div>
      <div style={{ fontSize: 13, color: '#9CA3AF', lineHeight: 1.65 }}>We couldn't load this content. Check your connection and try again.</div>
      {onRetry && <button onClick={onRetry} style={{ marginTop: 8, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 13, border: 'none', borderRadius: 14, padding: '12px 24px', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Try Again</button>}
    </div>
  )
}

// ─── SUBSCRIPTION ─────────────────────────────────────────────────────────────
type SubscriptionPlan = {
  id: string
  name: string
  price: number
  period: string | null
  quota_period?: string
  podcast_minutes?: number
  summary_pages?: number
  questions?: number
  mind_map_nodes?: number
  flashcards?: number
  offline_study?: boolean
  premium_library?: boolean
  study_hub_uploads?: boolean
}
type SubscriptionStatus = { plan: string; is_active: boolean; expires_at: string | null }

// Static display metadata (badges/colors/feature bullets) keyed by plan id -
// the backend only knows price/period, not marketing copy, so this stays
// client-side and is merged onto whatever plans GET /subscription/plans
// actually returns.
const SUBSCRIPTION_PLAN_META: Record<string, { badge?: string; badgeColor?: string; color: string }> = {
  free: { color: '#6B7280' },
  plus: { badge: 'Plus', badgeColor: N.gold, color: N.gold },
  pro: { badge: 'Pro', badgeColor: '#4CC97B', color: '#4C7BC9' },
}

function subscriptionFeatures(plan: SubscriptionPlan): string[] {
  const features = [
    'Morio — personalized AI study support',
    `${Number(plan.podcast_minutes || 0).toLocaleString()} podcast minutes`,
    `${Number(plan.summary_pages || 0).toLocaleString()} summary pages`,
    `${Number(plan.questions || 0).toLocaleString()} questions`,
    `${Number(plan.mind_map_nodes || 0).toLocaleString()} mind-map nodes`,
    `${Number(plan.flashcards || 0).toLocaleString()} flashcards`,
  ]
  if (plan.offline_study) features.push('Offline study')
  if (plan.premium_library) features.push('Premium library')
  if (plan.study_hub_uploads) features.push('Unlimited StudyHub uploads')
  return features
}

function SubscriptionScreen({ setScreen, selectedPlan, setSelectedPlan }: { setScreen: (s: Screen) => void; selectedPlan: string; setSelectedPlan: (p: string) => void }) {
  const { tokens: T } = useTheme()
  const [plans, setPlans] = useState<SubscriptionPlan[]>([])
  const [status, setStatus] = useState<SubscriptionStatus | null>(null)
  const [usage, setUsage] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true); setError('')
    Promise.all([
      api<{ plans: SubscriptionPlan[] }>('/subscription/plans'),
      api<SubscriptionStatus>('/subscription/status'),
      api('/api/usage/me'),
    ])
      .then(([plansRes, statusRes, usageRes]) => { setPlans(plansRes.plans); setStatus(statusRes); setUsage(usageRes) })
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load subscription plans - check your connection and try again.'))
      .finally(() => setLoading(false))
  }, [])

  const paidPlans = plans.filter(p => p.id !== 'free')
  const selected = paidPlans.find(p => p.id === selectedPlan) || paidPlans[0]

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: T.pageBg }} className="scrollbar-hide">
      <div style={{ background: N.navy, padding: '0 18px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => window.history.back()} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ flex: 1 }}><div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Prepza Plans</div><div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>Unlock all AI study tools</div></div>
        </div>
        <div style={{ marginTop: 16, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 14, padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 20 }}>🎓</span>
          <div style={{ flex: 1 }}>
            <div style={{ color: '#fff', fontWeight: 700, fontSize: 13 }}>
              {status ? `Current Plan: ${status.plan === 'plus' ? 'Plus' : status.plan === 'pro' ? 'Pro' : 'Free'}` : 'Loading plan…'}
            </div>
            <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11 }}>
              {status?.is_active && status.expires_at
                ? `Renews/expires ${new Date(status.expires_at).toLocaleDateString()}`
                : 'Upgrade to unlock everything'}
            </div>
          </div>
          {status && <Pill text={status.is_active ? 'Active' : status.plan === 'free' ? 'Free' : 'Expired'} color={status.is_active ? '#4CC97B' : T.textMuted} />}
        </div>
      </div>
      <div style={{ padding: '20px 18px' }}>
        {loading ? (
          <div style={{ fontSize: 13, color: T.textMuted, textAlign: 'center', padding: '30px 0' }}>Loading plans…</div>
        ) : error ? (
          <ErrorState />
        ) : (
          <>
            {plans.map(p => {
              const meta = SUBSCRIPTION_PLAN_META[p.id] || { color: T.textMuted }
              const isCurrent = status?.plan === p.id && status.is_active
              const isSelectable = p.id !== 'free'
              const isSelected = selected?.id === p.id
              return (
                <div key={p.id} onClick={() => isSelectable && setSelectedPlan(p.id)}
                  style={{ background: T.card, borderRadius: 18, padding: 18, marginBottom: 12, border: `2px solid ${isSelectable && isSelected ? meta.color : 'rgba(0,0,0,0.06)'}`, cursor: isSelectable ? 'pointer' : 'default', position: 'relative', boxShadow: isSelectable && isSelected ? `0 4px 20px ${meta.color}25` : '0 2px 8px rgba(0,0,0,0.05)', transition: 'all 0.2s' }}>
                  {meta.badge && <div style={{ position: 'absolute', top: -11, right: 16, background: meta.badgeColor, color: p.id === 'plus' ? N.navy : '#fff', fontSize: 10, fontWeight: 800, padding: '3px 10px', borderRadius: 99, fontFamily: 'Plus Jakarta Sans' }}>{meta.badge}</div>}
                  {isCurrent && <div style={{ position: 'absolute', top: -11, left: 16, background: '#E5E7EB', color: T.textMuted, fontSize: 10, fontWeight: 700, padding: '3px 10px', borderRadius: 99, fontFamily: 'Plus Jakarta Sans' }}>Current</div>}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                    <div>
                      <div style={{ fontWeight: 800, fontSize: 16, color: T.text }}>{p.name}</div>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 2, marginTop: 2 }}>
                        <span style={{ fontWeight: 800, fontSize: 22, color: meta.color }}>KES {p.price.toLocaleString()}</span>
                        <span style={{ fontSize: 11, color: T.textMuted }}>{p.period ? `/${p.period}` : ''}</span>
                      </div>
                    </div>
                    {isSelectable && (
                      <div style={{ width: 24, height: 24, borderRadius: '50%', border: `2px solid ${isSelected ? meta.color : T.textMuted}`, background: isSelected ? meta.color : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        {isSelected && <div style={{ color: p.id === 'plus' ? N.navy : '#fff' }}>{Ic.check('w-3 h-3')}</div>}
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                    {subscriptionFeatures(p).map((f, i) => (
                      <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <div style={{ width: 16, height: 16, borderRadius: '50%', background: `${meta.color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><div style={{ color: meta.color }}>{Ic.check('w-2.5 h-2.5')}</div></div>
                        <span style={{ fontSize: 12, color: '#4B5563' }}>{f}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
            <button onClick={() => selected && setScreen('payment')} disabled={!selected} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: selected ? 'pointer' : 'default', fontFamily: 'Plus Jakarta Sans', boxShadow: `0 6px 24px rgba(201,168,76,0.4)`, marginTop: 4, opacity: selected ? 1 : 0.6 }}>
              {selected ? `Upgrade — KES ${selected.price.toLocaleString()}` : 'Upgrade'}
            </button>
          </>
        )}
        {usage && (
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: 14, marginTop: 8 }}>
            <div style={{ fontWeight: 800, fontSize: 13, color: T.text, marginBottom: 10 }}>{usage.plan === 'free' ? 'Free allowance' : usage.plan === 'plus' ? 'Plus allowance' : 'Pro allowance'}</div>
            {(['summary', 'podcast', 'flashcards', 'quiz', 'mind_map'] as const).map(feature => {
              const labels: Record<string, string> = { summary: 'Summary', podcast: 'Podcast', flashcards: 'Flashcards', quiz: 'Questions', mind_map: 'Mind map' }
              const units: Record<string, string> = { summary: 'pages', podcast: 'min', flashcards: 'cards', quiz: 'questions', mind_map: 'nodes' }
              const item = usage.usage?.[feature]
              const used = Number(item?.units || 0)
              const remaining = Number(item?.remaining_units || 0)
              const max = Number(item?.unit_limit || 0)
              return <div key={feature} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 11, color: T.textMuted, marginTop: 7 }}>
                <span>{labels[feature]}</span>
                <span>{remaining}/{max} {units[feature]} remaining</span>
              </div>
            })}
          </div>
        )}

        <button onClick={() => setScreen('payment-history')} style={{ width: '100%', background: 'transparent', color: T.textMuted, fontSize: 12, fontWeight: 600, border: 'none', padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>View payment history</button>
        <div style={{ textAlign: 'center', fontSize: 11, color: T.textMuted, lineHeight: 1.6 }}>🔒 Secured payments via M-Pesa & card, powered by Paystack.</div>
      </div>
    </div>
  )
}

// ─── PAYMENT ──────────────────────────────────────────────────────────────────
// Paystack checkout: POST /subscription/upgrade returns a redirect_url
// to Paystack's hosted payment page. The current student purchase model is
// subscription-only; future one-off purchases are reserved for usage/add-on
// credits rather than ownership of individual Library content.
function PaymentScreen({ setScreen, selectedPlan }: { setScreen: (s: Screen) => void; selectedPlan: string }) {
  const { tokens: T } = useTheme()
  const [phone, setPhone] = useState('')
  const [plan, setPlan] = useState<SubscriptionPlan | null>(null)
  const [loadingPlan, setLoadingPlan] = useState(true)
  const [redirecting, setRedirecting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api<{ plans: SubscriptionPlan[] }>('/subscription/plans')
      .then(res => setPlan(res.plans.find(p => p.id === selectedPlan) || null))
      .catch(() => setError('Could not load plan details.'))
      .finally(() => setLoadingPlan(false))
  }, [selectedPlan])

  const pay = async () => {
    if (redirecting) return
    setError('')
    setRedirecting(true)
    try {
      const me = await api<{ csrf_token: string }>('/me')
      const res = await api<{ redirect_url: string; order_tracking_id: string; merchant_reference: string }>('/subscription/upgrade', {
        method: 'POST',
        headers: { 'X-CSRF-Token': me.csrf_token },
        body: JSON.stringify({ plan: selectedPlan, phone_number: phone.trim() || undefined }),
      })
      window.location.href = res.redirect_url
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not start checkout - please try again.')
      setRedirecting(false)
    }
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 20px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <button onClick={() => setScreen('subscription')} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Checkout</div>
        </div>
        <div style={{ background: 'rgba(255,255,255,0.08)', borderRadius: 14, padding: '14px 16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ color: 'rgba(255,255,255,0.7)', fontSize: 13 }}>{plan ? `Prepza ${plan.name} Plan` : 'Loading plan…'}</span>
            <span style={{ color: N.gold, fontWeight: 800 }}>{plan ? `KES ${plan.price.toLocaleString()}` : '—'}</span>
          </div>
          <div style={{ height: 1, background: 'rgba(255,255,255,0.1)', marginBottom: 8 }} />
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: '#fff', fontWeight: 700, fontSize: 14 }}>Total</span>
            <span style={{ color: '#fff', fontWeight: 800, fontSize: 16 }}>{plan ? `KES ${plan.price.toLocaleString()}` : '—'}</span>
          </div>
        </div>
      </div>
      {redirecting ? (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 20, padding: '0 32px', textAlign: 'center' }}>
          <div style={{ width: 72, height: 72, background: `linear-gradient(135deg,${N.gold},${N.goldL})`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 36, animation: 'pulse-gold 2s infinite' }}>🔒</div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 17, color: T.text, marginBottom: 8 }}>Taking you to secure checkout…</div>
            <div style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.65 }}>You'll complete payment on Paystack's secure page, then return to Prepza.</div>
          </div>
        </div>
      ) : (
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 18px' }} className="scrollbar-hide">
          {error && (
            <div style={{ background: 'rgba(201,68,68,0.08)', border: '1px solid rgba(201,68,68,0.25)', borderRadius: 12, padding: '12px 14px', color: '#C94C4C', fontSize: 12, fontWeight: 600, marginBottom: 16 }}>{error}</div>
          )}
          <div style={{ background: T.card, borderRadius: 16, padding: 18, marginBottom: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
              <div style={{ width: 40, height: 40, background: '#4CC97B20', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>📱</div>
              <div><div style={{ fontWeight: 700, fontSize: 14, color: T.text }}>M-Pesa number</div><div style={{ fontSize: 11, color: T.textMuted }}>Optional - helps prefill checkout where supported</div></div>
            </div>
            <input value={phone} onChange={e => setPhone(e.target.value)} placeholder="07XX XXX XXX" style={{ width: '100%', border: `1.5px solid ${T.border}`, borderRadius: 12, padding: '12px 14px', fontSize: 15, fontFamily: 'Plus Jakarta Sans', outline: 'none', color: T.text, boxSizing: 'border-box', letterSpacing: 0.5 }} />
          </div>
          <button onClick={pay} disabled={loadingPlan || !plan} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: (loadingPlan || !plan) ? 'default' : 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 6px 24px rgba(201,168,76,0.4)', opacity: (loadingPlan || !plan) ? 0.6 : 1 }}>
            {plan ? `Continue to Payment — KES ${plan.price.toLocaleString()}` : 'Loading…'}
          </button>
          <div style={{ textAlign: 'center', marginTop: 12, fontSize: 11, color: T.textMuted }}>🔒 Secured by Paystack (M-Pesa & card)</div>
        </div>
      )}
    </div>
  )
}

function PaymentSuccessScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const { tokens: T } = useTheme()
  const [payment, setPayment] = useState<PaymentHistoryItem | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    api<{ payments: PaymentHistoryItem[] }>('/payment-history')
      .then(res => setPayment(res.payments[0] || null))
      .catch(() => setLoadError('Could not load your payment details.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const t = setTimeout(() => setScreen('home'), 6000)
    return () => clearTimeout(t)
  }, [])

  const itemLabel = payment
    ? (payment.plan === 'plus' ? 'Plus Plan' : payment.plan === 'pro' ? 'Pro Plan' : 'Prepza Subscription')
    : null

  const detailRows: [string, string][] = payment
    ? [
        ['Item', itemLabel || '—'],
        ['Amount', `KES ${payment.amount.toLocaleString()}`],
        ['Status', payment.status.charAt(0).toUpperCase() + payment.status.slice(1)],
        ...(payment.reference ? ([['Reference', payment.reference]] as [string, string][]) : []),
      ]
    : []

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: T.pageBg, padding: '0 28px', textAlign: 'center', gap: 20 }}>
      <div style={{ width: 80, height: 80, background: 'rgba(76,201,123,0.12)', borderRadius: '50%', border: '3px solid #4CC97B', display: 'flex', alignItems: 'center', justifyContent: 'center', animation: 'fadeSlideUp 0.5s ease both' }}>
        <div style={{ color: '#4CC97B' }}>{Ic.check('w-10 h-10')}</div>
      </div>
      <div>
        <div style={{ fontWeight: 800, fontSize: 22, color: T.text, marginBottom: 8 }}>Payment Successful! 🎉</div>
        <div style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.7 }}>
          {itemLabel
            ? `Your ${itemLabel} payment has gone through — your plan entitlements are now active.`
            : 'Your payment has gone through. Welcome to Prepza.'}
        </div>
      </div>
      {loading ? (
        <div style={{ fontSize: 12, color: T.textMuted }}>Loading your payment details…</div>
      ) : loadError ? (
        <div style={{ fontSize: 12, color: T.textMuted }}>{loadError} You can check <span onClick={() => setScreen('payment-history')} style={{ color: N.gold, fontWeight: 700, cursor: 'pointer' }}>Payment History</span> for details.</div>
      ) : payment && (
        <div style={{ background: T.card, borderRadius: 16, padding: '16px 20px', width: '100%', boxShadow: '0 2px 8px rgba(0,0,0,0.06)', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {detailRows.map(([k, v]) => (
            <div key={k} style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 12, color: T.textMuted }}>{k}</span>
              <span style={{ fontSize: 12, fontWeight: 700, color: T.text, fontFamily: k === 'Reference' ? 'monospace' : 'Plus Jakarta Sans' }}>{v}</span>
            </div>
          ))}
        </div>
      )}
      <button onClick={() => setScreen('home')} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 6px 24px rgba(201,168,76,0.4)' }}>
        Start Studying
      </button>
      <div style={{ fontSize: 11, color: T.textMuted }}>Redirecting to home in a moment…</div>
    </div>
  )
}

function PaymentFailureScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const { tokens: T } = useTheme()
  const [payment, setPayment] = useState<PaymentHistoryItem | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api<{ payments: PaymentHistoryItem[] }>('/payment-history')
      .then(res => setPayment(res.payments[0] || null))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const isPending = payment?.status === 'pending'

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: T.pageBg, padding: '0 28px', textAlign: 'center', gap: 20 }}>
      <div style={{ width: 80, height: 80, background: isPending ? 'rgba(217,119,6,0.1)' : 'rgba(201,76,76,0.1)', borderRadius: '50%', border: `3px solid ${isPending ? '#D97706' : '#C94C4C'}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {isPending ? <span style={{ fontSize: 32 }}>⏳</span> : <div style={{ color: '#C94C4C' }}>{Ic.close('w-9 h-9')}</div>}
      </div>
      <div>
        <div style={{ fontWeight: 800, fontSize: 22, color: T.text, marginBottom: 8 }}>{isPending ? 'Payment Still Processing' : 'Payment Failed'}</div>
        <div style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.7 }}>
          {isPending
            ? "We haven't received final confirmation yet. This can take a minute — check Payment History shortly, or try again if it doesn't update."
            : 'Your payment was cancelled or could not be completed. Please try again or use a different payment method.'}
        </div>
      </div>
      {!loading && !isPending && (
        <div style={{ background: T.card, borderRadius: 16, padding: '14px 18px', width: '100%', border: '1px solid rgba(201,76,76,0.2)', textAlign: 'left' }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#C94C4C', marginBottom: 8 }}>Common reasons:</div>
          {['Insufficient M-Pesa balance or card funds', 'Incorrect PIN or OTP entered', 'Payment request timed out', 'Card declined by your bank'].map((r, i) => (
            <div key={i} style={{ fontSize: 12, color: T.textMuted, marginBottom: 4 }}>• {r}</div>
          ))}
        </div>
      )}
      <button onClick={() => setScreen('subscription')} style={{ width: '100%', background: `linear-gradient(135deg,${N.gold},${N.goldL})`, color: N.navy, fontWeight: 800, fontSize: 15, border: 'none', borderRadius: 16, padding: '14px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Try Again</button>
      <button onClick={() => setScreen('payment-history')} style={{ width: '100%', background: 'transparent', color: T.textMuted, fontWeight: 600, fontSize: 13, border: '1.5px solid rgba(0,0,0,0.1)', borderRadius: 16, padding: '13px 0', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}>Check Payment History</button>
    </div>
  )
}

type PaymentHistoryItem = {
  id: number
  payment_type: string
  content_title?: string | null
  plan: string | null
  amount: number
  status: string
  provider: string | null
  reference: string | null
  created_at: string | null
}



function PaymentHistoryScreen({ setScreen }: { setScreen: (s: Screen) => void }) {
  const { tokens: T } = useTheme()
  const [payments, setPayments] = useState<PaymentHistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api<{ payments: PaymentHistoryItem[] }>('/payment-history')
      .then(res => setPayments(res.payments))
      .catch(e => setError(e instanceof ApiError ? e.message : 'Could not load payment history - check your connection and try again.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: T.pageBg }}>
      <div style={{ background: N.navy, padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={() => window.history.back()} style={{ width: 34, height: 34, background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ color: '#fff' }}>{Ic.back()}</div></button>
          <div style={{ fontWeight: 800, fontSize: 18, color: '#fff' }}>Payment History</div>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 18px' }} className="scrollbar-hide">
        {loading ? (
          <div style={{ fontSize: 13, color: T.textMuted, textAlign: 'center', padding: '30px 0' }}>Loading…</div>
        ) : error ? (
          <ErrorState />
        ) : payments.length === 0 ? (
          <EmptyState icon="💳" title="No payments yet" sub="Your Prepza subscription payments will show up here." />
        ) : payments.map(p => {
          const meta = PAYMENT_STATUS_META[p.status] || { icon: '•', color: T.textMuted, label: p.status }
          const label = p.plan === 'plus' ? 'Plus Plan'
            : p.plan === 'pro' ? 'Pro Plan'
            : p.payment_type === 'addon' ? 'Usage add-on'
            : 'Prepza Subscription'
          return (
            <div key={p.id} style={{ background: T.card, borderRadius: 16, padding: '14px 16px', marginBottom: 10, boxShadow: '0 2px 8px rgba(0,0,0,0.05)', display: 'flex', gap: 12, alignItems: 'center' }}>
              <div style={{ width: 44, height: 44, background: `${meta.color}18`, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0 }}>{meta.icon}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: T.text }} className="line-clamp-1">{label}</div>
                <div style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>{p.created_at ? new Date(p.created_at).toLocaleDateString() : ''}{p.provider ? ` · ${p.provider.charAt(0).toUpperCase()}${p.provider.slice(1)}` : ''}</div>
                {p.reference && <div style={{ fontSize: 10, color: T.textMuted, fontFamily: 'monospace', marginTop: 2 }}>{p.reference}</div>}
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontWeight: 800, fontSize: 14, color: T.text, marginBottom: 4 }}>KES {p.amount.toLocaleString()}</div>
                <Pill text={meta.label} color={meta.color} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── ADMIN PLATFORM ───────────────────────────────────────────────────────────

export default function App() {
  const { storedNavigation, screenStack, screen, setScreen, resetNavigation } = useAppNavigation({
    onResetToLogin: resetChatRealtime,
  })

  useEffect(() => {
    const onPageShow = (event: PageTransitionEvent) => {
      if (!event.persisted) return
      api('/me').catch((e) => {
        if (e instanceof ApiError && e.status === 401) resetNavigation('login')
      })
    }
    window.addEventListener('pageshow', onPageShow)
    return () => window.removeEventListener('pageshow', onPageShow)
  }, [])

  useEffect(() => {
    // Click telemetry is not an offline queue for new actions: this only
    // flushes a click UUID that SponsoredOpportunityCard already created
    // after a confirmed qualifying impression. It lets a lost response be
    // retried after navigation or reconnect without inventing a new click ID.
    const clickStoragePrefix = 'prepza:b2b:click-pending:'
    let flushInFlight = false
    let retryTimer: number | null = null
    let retryAttempt = 0

    const clearRetryTimer = () => {
      if (retryTimer !== null) {
        window.clearTimeout(retryTimer)
        retryTimer = null
      }
    }

    const pendingClickKeys = () => {
      const keys: string[] = []
      try {
        for (let index = 0; index < sessionStorage.length; index += 1) {
          const key = sessionStorage.key(index)
          if (key?.startsWith(clickStoragePrefix)) keys.push(key)
        }
      } catch { /* session storage may be unavailable */ }
      return keys
    }

    const removePendingClick = (key: string) => {
      try { sessionStorage.removeItem(key) } catch { /* best effort */ }
    }

    const scheduleRetry = () => {
      if (
        retryTimer !== null ||
        retryAttempt >= 5 ||
        !navigator.onLine ||
        document.visibilityState !== 'visible'
      ) return
      const delay = Math.min(30000, 1000 * (2 ** retryAttempt))
      retryAttempt += 1
      retryTimer = window.setTimeout(() => {
        retryTimer = null
        void flushPendingClicks()
      }, delay)
    }

    const flushPendingClicks = async () => {
      if (flushInFlight || !navigator.onLine || document.visibilityState !== 'visible') return
      const keys = pendingClickKeys()
      if (!keys.length) return

      flushInFlight = true
      let transientFailure = false
      try {
        for (const key of keys) {
          const campaignId = Number(key.slice(clickStoragePrefix.length))
          let eventId = ''
          try { eventId = sessionStorage.getItem(key) || '' } catch { /* checked below */ }
          if (!Number.isInteger(campaignId) || campaignId <= 0 || !eventId) {
            removePendingClick(key)
            continue
          }

          try {
            const result = await api<{ eligible?: boolean }>(
              '/api/discovery/campaigns/' + campaignId + '/click',
              {
                method: 'POST',
                body: JSON.stringify({ event_id: eventId }),
              },
            )
            // The click route returns an explicit eligibility decision on all
            // successful HTTP responses. Whether billable or capped, it is
            // now settled and must not remain in the pending queue.
            if (typeof result.eligible === 'boolean') removePendingClick(key)
            else transientFailure = true
          } catch (error) {
            if (error instanceof ApiError && [400, 404, 410].includes(error.status)) {
              removePendingClick(key)
              continue
            }
            // Retain authorization failures for the next authenticated
            // navigation, but do not poll a signed-out session repeatedly.
            if (error instanceof ApiError && [401, 403].includes(error.status)) continue
            transientFailure = true
          }
        }
      } finally {
        flushInFlight = false
        if (transientFailure) scheduleRetry()
        else {
          retryAttempt = 0
          clearRetryTimer()
        }
      }
    }

    const onOnline = () => {
      retryAttempt = 0
      clearRetryTimer()
      void flushPendingClicks()
    }
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') void flushPendingClicks()
      else clearRetryTimer()
    }
    const onPageShow = () => { void flushPendingClicks() }

    window.addEventListener('online', onOnline)
    window.addEventListener('pageshow', onPageShow)
    document.addEventListener('visibilitychange', onVisibilityChange)
    void flushPendingClicks()

    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('pageshow', onPageShow)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      clearRetryTimer()
    }
  }, [screen])

  useEffect(() => {
    const onExternalDocument = (event: Event) => {
      const documentId = Number((event as CustomEvent<{ documentId?: number }>).detail?.documentId || 0)
      if (!Number.isInteger(documentId) || documentId <= 0) return
      setActiveDocumentId(documentId)
      setScreen('document-study')
    }
    window.addEventListener('prepza:open-document', onExternalDocument)
    return () => window.removeEventListener('prepza:open-document', onExternalDocument)
  }, [])

  const [adminMode, setAdminMode] = useState(false)
  const [orgPortalMode, setOrgPortalMode] = useState(false)
  useEffect(() => {
    // Study Hub has one activity clock across all learning screens. Individual
    // documents/features only provide context; they do not own timers.
    installStudyHubActivityTracker()
    installActivityHeartbeat()
    const localUserId = Number(localStorage.getItem('prepza-offline-user-id') || 0)
    if (Number.isInteger(localUserId) && localUserId > 0) setStudyHubUserId(localUserId)
  }, [])

  const studyHubScreens = new Set<Screen>([
    'document-study', 'document-reader', 'ai-tutor', 'flashcards', 'quiz',
    'podcast-player', 'podcast-library', 'summary', 'mind-map', 'study-materials',
  ])

  useEffect(() => {
    setStudyHubActive(studyHubScreens.has(screen))
  }, [screen])
  const [oauthError, setOauthError] = useState('')
  const [isAdmin, setIsAdmin] = useState(false)
  // Which Document is open in SummaryScreen. Screens communicate purely via
  // the Screen string (no route params), so these - like other "currently
  // open X" ids - have to be lifted here rather than living inside the
  // screens themselves, which unmount on navigation.
  const [activeConversationId, setActiveConversationId] = useState<number | null>(() => storedNavigation?.activeConversationId ?? null)
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(() => storedNavigation?.activeDocumentId ?? null)

  useEffect(() => {
    const onServiceWorkerMessage = (event: MessageEvent) => {
      const data = event.data
      if (!data || data.type !== 'OPEN_PREPZA_NOTIFICATION') return
      if (data.screen === 'podcast-player' && data.document_id) {
        setActiveDocumentId(Number(data.document_id))
        setScreen('podcast-player')
      } else if (data.screen) {
        setScreen(data.screen as Screen)
      } else {
        setScreen('notifications')
      }
    }
    if ('serviceWorker' in navigator) navigator.serviceWorker.addEventListener('message', onServiceWorkerMessage)
    return () => {
      if ('serviceWorker' in navigator) navigator.serviceWorker.removeEventListener('message', onServiceWorkerMessage)
    }
  }, [])
  const [activeGroupId, setActiveGroupId] = useState<number | null>(() => storedNavigation?.activeGroupId ?? null)
  // Which subscription plan the user picked on SubscriptionScreen, carried
  // over to PaymentScreen the same way activeDocumentId etc. are - these
  // are two separate mounted components, not steps of one component, so
  // the selection has to be lifted here rather than living in either screen.
  const [selectedPlan, setSelectedPlan] = useState('plus')
  // Which user's profile is open in StudentProfileScreen / whose followers-
  // following list is open in FollowListScreen. activeProfileName is a
  // best-effort label carried over from wherever the navigation started
  // (never fetched separately - there's no endpoint for it), so the screen
  // isn't stuck showing "Student" when we already know the real name.
  const [activeProfileUserId, setActiveProfileUserId] = useState<number | null>(() => storedNavigation?.activeProfileUserId ?? null)
  const [activeProfileName, setActiveProfileName] = useState<string | null>(null)
  // Tracks where a profile was opened from so the profile's Back action does not
  // fall into the legacy chat-detail screen when the new WhatsApp chat experience is active.
  const [activeProfileBackScreen, setActiveProfileBackScreen] = useState<'chat-detail' | 'chats'>('chat-detail')
  const [activeOpportunityId, setActiveOpportunityId] = useState<number | null>(() => storedNavigation?.activeOpportunityId ?? null)
  // Set when the app loads at /signup?ref=CODE (an ambassador's share
  // link - see ambassador_dashboard()'s referral_link field). Carried as
  // a prop into SignupScreen so its final POST /signup body can include
  // ref/via, same lift-to-App() reasoning as the activeXxx ids above.
  const [referralCode, setReferralCode] = useState<string | null>(null)
  const [referralChannel, setReferralChannel] = useState<string | null>(null)
  const [unreadChats, setUnreadChats] = useState(0)
  const [exploreAttention, setExploreAttention] = useState(false)
  useEffect(() => {
    let timer: number | null = null, cancelled = false
    const refreshSignals = () => {
      api<{ chats: ChatSummary[] }>('/chats').then(res => { if (!cancelled) setUnreadChats((res.chats || []).reduce((sum, chat) => sum + Math.max(0, chat.unread_count || 0), 0)) }).catch(() => {})
      api<{ opportunities: OpportunityPublic[] }>('/opportunities?page=1').then(res => {
        if (cancelled) return
        const firstId = res.opportunities?.[0]?.id
        if (firstId) localStorage.setItem('prepza-latest-explore-opportunity-id', String(firstId))
        const seenId = Number(localStorage.getItem('prepza-last-explore-opportunity-id') || 0)
        setExploreAttention(Boolean(firstId && firstId !== seenId))
      }).catch(() => {})
    }
    refreshSignals()
    timer=window.setInterval(refreshSignals,30000)
    window.addEventListener('prepza-realtime-message',refreshSignals)
    return()=>{cancelled=true;if(timer!==null)window.clearInterval(timer);window.removeEventListener('prepza-realtime-message',refreshSignals)}
  }, [])

  useEffect(() => {
    try {
      sessionStorage.setItem('prepza-navigation-state', JSON.stringify({
        stack: screenStack,
        activeConversationId,
        activeDocumentId,
        activeGroupId,
        activeProfileUserId,
        activeOpportunityId,
      }))
    } catch { /* storage can be unavailable in private browsing */ }
  }, [screenStack, activeConversationId, activeDocumentId, activeGroupId, activeProfileUserId, activeOpportunityId])

  // Product activity is measured separately from authentication. A signed-in
  // user only becomes an active user after meaningful foreground engagement
  // or a core action; this heartbeat feeds the organisation audience meter.
  useEffect(() => {
    let timer: number | null = null
    let stopped = false
    let engagedSeconds = 0
    let lastTick = Date.now()
    let csrfToken = ''

    const sendHeartbeat = async (sessionStart = false) => {
      if (stopped || document.visibilityState !== 'visible') return
      const now = Date.now()
      const elapsed = Math.max(0, Math.min(60, Math.round((now - lastTick) / 1000)))
      lastTick = now
      engagedSeconds = Math.min(120, engagedSeconds + elapsed)
      try {
        if (!csrfToken) {
          const me = await api<{ csrf_token: string }>('/me')
          csrfToken = me.csrf_token || ''
        }
        if (!csrfToken) return
        await api('/api/analytics/heartbeat', {
          method: 'POST',
          headers: { 'X-CSRF-Token': csrfToken },
          body: JSON.stringify({
            session_start: sessionStart,
            engagement_seconds: sessionStart ? 0 : elapsed,
            core_actions: 0,
          }),
        })
      } catch {
        // Activity metering is non-blocking; never interrupt study/chat flows.
      }
    }

    const onVisibility = () => {
      lastTick = Date.now()
      if (document.visibilityState === 'visible') void sendHeartbeat(false)
    }

    void sendHeartbeat(true)
    timer = window.setInterval(() => { void sendHeartbeat(false) }, 30_000)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      stopped = true
      if (timer !== null) window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  // Handles the round-trip back from /auth/google/callback, which appends
  // ?complete_profile=1 (new Google account, needs university/course/year/
  // semester) or ?auth_error=... (Google sign-in failed) to the redirect.
  // This does NOT do general "am I still logged in" session restore on
  // every page load - only this specific OAuth round-trip.
  useEffect(() => {
    const path = window.location.pathname
    const params = new URLSearchParams(window.location.search)

    // Direct hits from emailed links - Flask serves this same SPA shell for
    // both paths, so routing happens client-side off the pathname. The
    // token itself stays in the query string; ResetPasswordScreen and
    // VerifyConfirmScreen each read it themselves.
    if (path === '/reset-password') {
      setScreen('reset-password')
      return
    }
    if (path === '/verify-email') {
      setScreen('verify-confirm')
      return
    }

    // Ambassador referral link - see GET /signup in app.py, which serves
    // this same app shell rather than 404ing. A visit with no ?ref= (e.g.
    // someone bookmarked /signup directly) just falls through normally.
    if (path === '/signup') {
      const refCode = params.get('ref')
      const viaChannel = params.get('via')
      if (refCode) {
        setReferralCode(refCode)
        if (viaChannel) setReferralChannel(viaChannel)
        setScreen('signup')
      }
      const cleanSignupUrl = new URL(window.location.href)
      cleanSignupUrl.searchParams.delete('ref')
      cleanSignupUrl.searchParams.delete('via')
      window.history.replaceState({}, '', cleanSignupUrl.toString())
    }

    const paymentStatus = params.get('payment_status')
    if (paymentStatus) {
      setScreen(paymentStatus === 'success' ? 'payment-success' : 'payment-failure')
      const cleanUrl = new URL(window.location.href)
      cleanUrl.searchParams.delete('payment_status')
      window.history.replaceState({}, '', cleanUrl.toString())
    }

    const wantsCompleteProfile = params.get('complete_profile') === '1'
    const authError = params.get('auth_error')
    if (wantsCompleteProfile) {
      setScreen('complete-profile')
    } else if (authError) {
      setOauthError(decodeURIComponent(authError))
      setScreen('login')
    }
    if (wantsCompleteProfile || authError) {
      const url = new URL(window.location.href)
      url.searchParams.delete('complete_profile')
      url.searchParams.delete('auth_error')
      window.history.replaceState({}, '', url.toString())
    }

    // Admin Platform is only ever shown to a confirmed admin session -
    // fails silently (stays false) for logged-out visitors or regular
    // students, on top of every /admin/* route already being server-side
    // gated via @require_admin.
    api<{ is_admin: boolean }>('/me')
      .then(me => setIsAdmin(!!me.is_admin))
      .catch(() => setIsAdmin(false))
  }, [])

  if (adminMode) return <AdminPlatform onExit={() => setAdminMode(false)} />
  if (orgPortalMode) return <PremiumOrganisationPortal onExit={() => setOrgPortalMode(false)} />

  // Bottom navigation belongs to the primary app surfaces. Detail/immersive flows must own the full viewport so the global nav does not compete with their back/close controls.
  const renderScreen = () => {
    switch (screen) {
      case 'ambassador': return <AmbassadorScreen setScreen={setScreen} />
      case 'splash':            return <SplashScreen setScreen={setScreen} brandline={PREPZA_BRANDLINE} />
      case 'login':             return <LoginScreen setScreen={setScreen} oauthError={oauthError} />
      case 'forgot-password':   return <ForgotPasswordScreen setScreen={setScreen} />
      case 'signup':            return <SignupScreen setScreen={setScreen} referralCode={referralCode} referralChannel={referralChannel} />
      case 'check-email':       return <CheckEmailScreen setScreen={setScreen} />
      case 'complete-profile':  return <CompleteProfileScreen setScreen={setScreen} />
      case 'reset-password':    return <ResetPasswordScreen setScreen={setScreen} />
      case 'verify-confirm':    return <VerifyConfirmScreen setScreen={setScreen} />
      case 'home':              return <HomeScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} setActiveOpportunityId={setActiveOpportunityId} SponsoredOpportunityCard={SponsoredOpportunityCard} loadingView={<SkeletonHome />} />
      case 'explore':           return <ExploreScreen setScreen={setScreen} setActiveGroupId={setActiveGroupId} setActiveDocumentId={setActiveDocumentId} setActiveOpportunityId={setActiveOpportunityId} setActiveProfileUserId={setActiveProfileUserId} setActiveProfileName={setActiveProfileName} SponsoredOpportunityCard={SponsoredOpportunityCard} loadingView={<DelayedScreenSkeleton><SkeletonExplore /></DelayedScreenSkeleton>} ErrorView={GenerationError} />
      case 'create-modal':      return <CreateModal setScreen={setScreen} />
      case 'share-opp-form':    return <ShareOppForm setScreen={setScreen} />
      case 'edu-upload-form':   return <EduUploadForm setScreen={setScreen} />
      case 'upload':            return <UploadScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} />
      case 'upload-share-choice': return <UploadShareChoiceScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'processing':        return <ProcessingScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'doc-ready':         return <DocReadyScreen setScreen={setScreen} activeDocumentId={activeDocumentId} TopBar={TopBar} />
      case 'document-study': return <DocumentStudyHubScreen setScreen={setScreen} activeDocumentId={activeDocumentId} LoadingView={GenerationLoading} ErrorView={GenerationError} DOC_CACHE={DOC_CACHE} />
      case 'document-reader': return <DocumentReaderScreen setScreen={setScreen} activeDocumentId={activeDocumentId} DOC_CACHE={DOC_CACHE} GenerationLoading={GenerationLoading} GenerationError={GenerationError} />
      case 'ai-tutor':          return <AITutorScreen setScreen={setScreen} activeDocumentId={activeDocumentId} setActiveDocumentId={setActiveDocumentId} GenerationError={GenerationError} DelayedScreenSkeleton={DelayedScreenSkeleton} SkeletonAITutor={SkeletonAITutor} />
      case 'flashcards':        return <FlashcardsStudyScreen setScreen={setScreen} activeDocumentId={activeDocumentId} GenerationLoading={GenerationLoading} GenerationError={GenerationError} AchievementToast={AchievementToast} generationRequest={generationRequest} replaySelectedGeneratedMaterialOffline={replaySelectedGeneratedMaterialOffline} getLatestGeneratedMaterialForPath={getLatestGeneratedMaterialForPath} />
      case 'quiz':              return <QuizStudyScreen setScreen={setScreen} activeDocumentId={activeDocumentId} GenerationLoading={GenerationLoading} GenerationError={GenerationError} AchievementToast={AchievementToast} generationRequest={generationRequest} replaySelectedGeneratedMaterialOffline={replaySelectedGeneratedMaterialOffline} getLatestGeneratedMaterialForPath={getLatestGeneratedMaterialForPath} />
      case 'podcast-player':    return <PodcastPlayerScreen
        setScreen={setScreen}
        activeDocumentId={activeDocumentId}
        setActiveOpportunityId={setActiveOpportunityId}
        generationRequest={generationRequest}
        cacheReadyPodcastOffline={cachePodcastReadyOffline}
        getCachedPodcastAudio={getCachedPodcastAudio}
        TopBar={TopBar}
        GenerationError={GenerationError}
        renderSponsoredOpportunities={campaigns => campaigns.map(c => (
          <SponsoredOpportunityCard key={c.campaign_id} campaign={c} compact setScreen={setScreen} setActiveOpportunityId={setActiveOpportunityId} />
        ))}
      />
      case 'podcast-library':   return <PodcastLibraryScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} DelayedScreenSkeleton={DelayedScreenSkeleton} SkeletonPodcastLibrary={SkeletonPodcastLibrary} EmptyState={EmptyState} ErrorState={ErrorState} />
      case 'summary':           return <SummaryStudyScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'chats':             return <WhatsAppChatExperience onClose={() => setScreen('home')} onOpenProfile={(userId, name, conversationId) => { setActiveProfileBackScreen('chats'); if (conversationId != null) setActiveConversationId(conversationId); setActiveProfileUserId(userId); setActiveProfileName(name || null); setScreen('student-profile') }} onOpenOptions={(conversationId) => { setActiveConversationId(conversationId); setScreen('chat-options') }} onOpenDocument={(documentId) => { setActiveDocumentId(documentId); setScreen('document-study') }} />
      case 'chat-detail':       return <ChatDetailScreen setScreen={setScreen} conversationId={activeConversationId} setActiveProfileUserId={setActiveProfileUserId} setActiveProfileName={setActiveProfileName} getFileExtension={getFileExtension} allowedUploadExtensions={ALLOWED_UPLOAD_EXTENSIONS} maxChatAttachmentSizeBytes={MAX_CHAT_ATTACHMENT_SIZE_BYTES} loadingView={<DelayedScreenSkeleton><SkeletonChatDetail /></DelayedScreenSkeleton>} />
      case 'opportunities':     return <OpportunitiesScreen setScreen={setScreen} setActiveOpportunityId={setActiveOpportunityId} SponsoredOpportunityCard={SponsoredOpportunityCard} SkOppCard={SkOppCard} ErrorState={ErrorState} EmptyState={EmptyState} />
      case 'opportunity-detail':return <OppDetailScreen setScreen={setScreen} opportunityId={activeOpportunityId} TopBar={TopBar} EmptyState={EmptyState} DelayedScreenSkeleton={DelayedScreenSkeleton} SkeletonOppDetail={SkeletonOppDetail} ErrorState={ErrorState} />
      case 'share-sheet':       return <ShareSheetScreen setScreen={setScreen} />
      case 'student-profile':   return <StudentProfileScreen setScreen={setScreen} targetUserId={activeProfileUserId} fallbackName={activeProfileName} setActiveConversationId={setActiveConversationId} activeConversationId={activeConversationId} backScreen={activeProfileBackScreen} />
      case 'profile':           return <ProfileScreen setScreen={setScreen} setActiveProfileUserId={setActiveProfileUserId} setActiveDocumentId={setActiveDocumentId} setActiveOpportunityId={setActiveOpportunityId} onOpenOrgPortal={() => setOrgPortalMode(true)} SkeletonProfile={SkeletonProfile} />
      case 'settings':          return <SettingsScreen setScreen={setScreen} resetToAuth={() => resetNavigation('login')} />
      case 'notifications':     return <NotificationsScreen setScreen={setScreen} setActiveProfileUserId={setActiveProfileUserId} setActiveDocumentId={setActiveDocumentId} EmptyStateView={EmptyState} loadingView={<DelayedScreenSkeleton><SkeletonNotifications /></DelayedScreenSkeleton>} />
      case 'library':           return <LibraryScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} EmptyState={EmptyState} ErrorState={ErrorState} />
      case 'study-materials':   return <StudyMaterialsScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} LoadingView={GenerationLoading} ErrorView={GenerationError} EmptyStateView={EmptyState} />
      case 'mind-map':          return <MindMapStudyScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'new-chat':          return <NewChatScreen setScreen={setScreen} setActiveConversationId={setActiveConversationId} />
      case 'chat-options':      return <ChatOptionsScreen setScreen={setScreen} conversationId={activeConversationId} setActiveProfileUserId={setActiveProfileUserId} setActiveProfileName={setActiveProfileName} backScreen="chats" setActiveProfileBackScreen={setActiveProfileBackScreen} getFileExtension={getFileExtension} imageFileTypes={IMAGE_FILE_TYPES} />
      case 'edit-profile':      return <EditProfileScreen setScreen={setScreen} />
      case 'subscription':      return <SubscriptionScreen setScreen={setScreen} selectedPlan={selectedPlan} setSelectedPlan={setSelectedPlan} />
      case 'payment':           return <PaymentScreen setScreen={setScreen} selectedPlan={selectedPlan} />
      case 'payment-success':   return <PaymentSuccessScreen setScreen={setScreen} />
      case 'payment-failure':   return <PaymentFailureScreen setScreen={setScreen} />
      case 'payment-history':   return <PaymentHistoryScreen setScreen={setScreen} />
      case 'publish-library':   return <PublishLibraryScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'xp-progress':       return <XPProgressScreen setScreen={setScreen} />
      case 'study-streak':      return <StudyActivityScreen setScreen={setScreen} />
      case 'study-activity':    return <StudyActivityScreen setScreen={setScreen} />
      case 'achievements':      return <AchievementsScreen setScreen={setScreen} />
      case 'time-studied':      return <StudyActivityScreen setScreen={setScreen} />
      case 'followers':         return <FollowListScreen mode="followers" setScreen={setScreen} targetUserId={activeProfileUserId} setActiveProfileUserId={setActiveProfileUserId} setActiveProfileName={setActiveProfileName} EmptyState={EmptyState} />
      case 'following':         return <FollowListScreen mode="following" setScreen={setScreen} targetUserId={activeProfileUserId} setActiveProfileUserId={setActiveProfileUserId} setActiveProfileName={setActiveProfileName} EmptyState={EmptyState} />
      case 'follow-requests':  return <FollowRequestsScreen setScreen={setScreen} setActiveProfileUserId={setActiveProfileUserId} setActiveProfileName={setActiveProfileName} EmptyState={EmptyState} />
      case 'group-detail':      return <GroupDetailScreen setScreen={setScreen} groupId={activeGroupId} EmptyState={EmptyState} ErrorState={ErrorState} />
      case 'group-create':      return <GroupCreateScreen setScreen={setScreen} setActiveGroupId={setActiveGroupId} />
      default:                  return <HomeScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} setActiveOpportunityId={setActiveOpportunityId} />
    }
  }

  return (
    <AppShell
      screen={screen}
      setScreen={setScreen}
      unreadChats={unreadChats}
      exploreAttention={exploreAttention}
      setExploreAttention={setExploreAttention}
      isAdmin={isAdmin}
      onOpenAdmin={() => setAdminMode(true)}
    >
      {renderScreen()}
    </AppShell>
  )
}
function friendlyGenerationError(error: unknown): string {
  const message = error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error || '')
  const lower = message.toLowerCase()
  if (lower.includes("Morio's safety limit") || lower.includes("used your Morio allowance")) {
    return message
  }
  if (lower.includes('generation quota exhausted') || lower.includes('used up this plan')) {
    return `You've used your plan's monthly allowance for this study material. Upgrade your plan for a larger allowance, or wait for your allowance to reset.`
  }
  if (lower.includes('supports at most') || lower.includes('generation amount')) {
    return message + ' You can choose a smaller generation or upgrade your plan for a larger one.'
  }
  if (lower.includes('student plan configuration is unavailable')) {
    return 'Your study allowance is temporarily unavailable. Please try again shortly.'
  }
  if (error instanceof ApiError && error.status === 429) {
    return 'Too many generation requests in a short time. Please wait a little and try again.'
  }
  if (error instanceof ApiError && error.status === 503) {
    return 'Prepza has temporarily paused fresh AI generation. Your existing study materials are still available. Please try again later.'
  }
  return message || 'We could not generate this study material. Please try again.'
}
