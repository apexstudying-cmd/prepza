export type PrepzaUsage = {
  plan: 'free' | 'premium'
  price_kes: number
  billing_period: string
  limits: {
    summary_generations: number
    summary_max_pages: number
    podcast_generations: number
    podcast_max_minutes: number
    flashcard_generations: number
    flashcard_max_cards: number
    quiz_generations: number
    quiz_max_questions: number
    mind_map_generations: number
    mind_map_max_nodes: number
    tutor_messages: number
  }
  usage: Record<string, { requests: number; units: number }>
  period_start: string
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
  const limits = usage.limits
  const current = usage.usage[feature] || { requests: 0, units: 0 }

  const requestLimit =
    feature === 'summary' ? limits.summary_generations :
    feature === 'podcast' ? limits.podcast_generations :
    feature === 'flashcards' ? limits.flashcard_generations :
    feature === 'quiz' ? limits.quiz_generations :
    limits.mind_map_generations

  const unitLimit =
    feature === 'summary' ? limits.summary_max_pages :
    feature === 'podcast' ? limits.podcast_max_minutes :
    feature === 'flashcards' ? limits.flashcard_max_cards :
    feature === 'quiz' ? limits.quiz_max_questions :
    limits.mind_map_max_nodes

  return (
    units <= unitLimit &&
    current.requests < requestLimit &&
    current.units + units <= unitLimit * requestLimit
  )
}

export function usageLabel(usage: PrepzaUsage | null) {
  if (!usage) return ''
  return usage.plan === 'premium'
    ? 'Premium · full generation limits'
    : 'Free · limited generation'
}
