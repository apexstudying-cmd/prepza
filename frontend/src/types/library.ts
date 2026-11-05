export type LibraryPublicationSummary = {
  id: number; document_id: number | null; title: string; description: string | null; material_type: string
  unit_id: number | null; unit_code: string | null; author: string
  view_count: number; save_count: number; created_at: string | null; locked?: boolean
}
export type SavedLibraryItem = LibraryPublicationSummary & { saved_at: string | null }
export type MySubmission = {
  id: number; document_id: number; title: string; description: string | null; material_type: string
  unit_id: number | null; unit_code: string | null; status: string; rejection_reason: string | null
  view_count: number; save_count: number; created_at: string | null; updated_at: string | null
}
