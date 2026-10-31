export type PodcastItem = {
  document_id: number
  title: string
  audio_status: string
  duration_seconds: number | null
  created_at: string | null
}

const PODCAST_COLORS = ['#C9A84C', '#4C7BC9', '#4CC97B', '#9B59B6', '#C94C4C', '#E67E22']

export const podcastColor = (id: number) => PODCAST_COLORS[id % PODCAST_COLORS.length]

export const podcastDuration = (seconds: number | null) =>
  seconds == null ? '—' : `${Math.max(1, Math.round(seconds / 60))} min`
