export type ProfileMe = {
  id: number
  display_name: string | null
  bio: string | null
  university_id: number | null
  program_id: number | null
}

export type HomeDocument = {
  id: number
  title: string
  status: string
  file_type: string | null
  page_count: number | null
  created_at: string | null
  last_opened_at?: string | null
  materials?: { id: number; type: string; status: string; parameters?: Record<string, unknown> }[]
}
