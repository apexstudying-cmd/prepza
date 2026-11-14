export type SubscriptionPlan = {
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

export type SubscriptionStatus = {
  plan: string
  is_active: boolean
  expires_at: string | null
}

export type PaymentHistoryItem = {
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
