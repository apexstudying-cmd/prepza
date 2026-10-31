export type Achievement = {
  code: string
  icon: string
  name: string
  desc: string
  done: boolean
  unlocked_at: string | null
  progress: number
  total: number
}

export type AchievementsResponse = { unlocked_count: number; total_count: number; achievements: Achievement[] }
