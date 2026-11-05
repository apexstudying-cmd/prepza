export type DocumentDetail = {
  id: number; title: string; original_filename: string; status: string
  content_hash?: string | null; last_opened_at?: string | null
  file_type: string | null; file_size_bytes: number | null; page_count: number | null
  error_message: string | null; view_url: string | null
  materials: { id: number; type: string; status: string; parameters?: Record<string, unknown> }[]; created_at: string | null
}
