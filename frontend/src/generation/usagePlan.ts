export type PrepzaFeature = 'summary' | 'podcast' | 'flashcards' | 'quiz' | 'mind_map'

export type PrepzaUsage = {
  plan: 'free' | 'plus' | 'pro'
  price_kes: number
  billing_period: string
  limits: {
    display_name: string
    podcast_minutes: number
    summary_pages: number
    questions: number
    mind_map_nodes: number
    flashcards: number
    offline_study: boolean
    premium_library: boolean
    study_hub_uploads: boolean
  }
  usage: Record<PrepzaFeature, {
    requests: number
    units: number
    remaining_units?: number
    unit_limit?: number
    max_units_per_generation?: number
  }>
  period_start: string
}

export async function fetchPrepzaUsage(): Promise<PrepzaUsage> {
  const response = await fetch('/api/usage/me', { credentials: 'include' })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body?.error || 'Could not load your study allowance.')
  return body as PrepzaUsage
}

export function featureLimit(usage: PrepzaUsage | null, feature: PrepzaFeature): number {
  if (!usage) return 0
  const key = feature === 'summary' ? 'summary_pages'
    : feature === 'podcast' ? 'podcast_minutes'
    : feature === 'flashcards' ? 'flashcards'
    : feature === 'quiz' ? 'questions'
    : 'mind_map_nodes'
  return Number(usage.limits[key] || 0)
}

export function remainingUnits(usage: PrepzaUsage | null, feature: PrepzaFeature): number {
  return Number(usage?.usage?.[feature]?.remaining_units ?? 0)
}

export function canGenerate(usage: PrepzaUsage | null, feature: PrepzaFeature, units: number): boolean {
  if (!usage || !Number.isFinite(units) || units <= 0) return false
  const limit = featureLimit(usage, feature)
  return units <= limit && units <= remainingUnits(usage, feature)
}

export function usageLabel(usage: PrepzaUsage | null) {
  if (!usage) return ''
  return usage.plan === 'pro'
    ? 'Pro · expanded generation allowance'
    : usage.plan === 'plus'
      ? 'Plus · expanded generation allowance'
      : 'Free · limited generation allowance'
}
