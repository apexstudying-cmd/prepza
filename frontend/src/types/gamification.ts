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

export type StreakCalendarDay = { date: string; studied: boolean; is_future: boolean; study_seconds: number }
export type StreakMilestone = { days: number; label: string; xp: string; done: boolean }
export type StreakResponse = {
  current_streak: number
  longest_streak: number
  calendar_month: string
  calendar_start_weekday: number
  earliest_month: string
  calendar: StreakCalendarDay[]
  milestones: StreakMilestone[]
}

export type StudyTimeResponse = { period: string; total_seconds: number; by_feature: Record<string, number> }
