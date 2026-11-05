export type NotificationItem = {
  id: number; type: string; title: string; body: string | null
  related_type: string | null; related_id: number | null
  is_read: boolean; created_at: string | null
}
