export type XpHistoryItem = { icon: string; label: string; xp: number; created_at: string | null }
export type HowToEarnItem = { label: string; xp: string }
export type XpProgressResponse = {
  level: number
  level_title: string
  xp_total: number
  xp_into_level: number
  xp_for_level_gap: number
  next_level_xp: number
  page: number
  history: XpHistoryItem[]
  how_to_earn: HowToEarnItem[]
}

export type StudyTimeResponse = { period: string; total_seconds: number; by_feature: Record<string, number> }
