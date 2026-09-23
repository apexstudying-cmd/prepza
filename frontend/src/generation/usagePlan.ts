export type PrepzaUsage = {
  plan: 'free' | 'plus' | 'pro' | 'premium'
  price_kes: number
  billing_period: string
  limits: {
    podcast_minutes: number
    summary_pages: number
    questions: number
    mind_map_nodes: number
    flashcards: number
    offline_study: boolean
    premium_library: boolean
    study_hub_uploads: boolean
  }
  usage: Record<string, { requests: number; units: number; remaining_units?: number; unit_limit?: number; max_units_per_generation?: number }>
  period_start: string
  active_plans?: Array<'plus' | 'pro'>
  offline_access_expires_at?: string | null
}

export async function fetchPrepzaUsage(): Promise<PrepzaUsage> {
  const response = await fetch('/api/usage/me', { credentials: 'include' })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body?.error || 'Could not load usage limits.')
  return body as PrepzaUsage
}

export function canGenerate(
  usage: PrepzaUsage | null,
  feature: 'summary' | 'podcast' | 'flashcards' | 'quiz' | 'mind_map',
  units: number,
) {
  if (!usage || !Number.isFinite(units) || units <= 0) return false
  const limitKey = {
    summary: 'summary_pages',
    podcast: 'podcast_minutes',
    flashcards: 'flashcards',
    quiz: 'questions',
    mind_map: 'mind_map_nodes',
  } as const
  const limit = Number(usage.limits[limitKey[feature]] || 0)
  const current = usage.usage[feature] || { requests: 0, units: 0, remaining_units: limit }
  const maxPerGeneration = Number(current.max_units_per_generation ?? limit)
  // Overlapping paid entitlements stack their monthly wallet, while a single
  // generation cannot exceed the largest individual entitlement's generation size.
  return units <= maxPerGeneration && units <= Number(current.remaining_units ?? Math.max(0, limit - Number(current.units || 0)))
}

export function remainingUnits(usage: PrepzaUsage | null, feature: 'summary' | 'podcast' | 'flashcards' | 'quiz' | 'mind_map') {
  return Math.max(0, Number(usage?.usage?.[feature]?.remaining_units ?? 0))
}

export function usageExhausted(usage: PrepzaUsage | null, feature: 'summary' | 'podcast' | 'flashcards' | 'quiz' | 'mind_map') {
  return usage != null && remainingUnits(usage, feature) <= 0
}

export function usageLabel(usage: PrepzaUsage | null) {
  if (!usage) return ''
  return usage.plan === 'pro'
    ? 'Pro · expanded generation allowance'
    : usage.plan === 'plus'
      ? 'Plus · expanded generation allowance'
      : usage.plan === 'premium'
        ? 'Premium · expanded generation allowance'
        : 'Free · limited generation allowance'
}
