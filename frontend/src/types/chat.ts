export type MessageAttachmentData = { id: number; file_type: string; original_filename: string; file_size_bytes: number; view_url: string | null }
export type ChatMessageData = {
  id: number; conversation_id: number; sender_id: number; body: string | null
  is_deleted: boolean; created_at: string | null; edited_at: string | null
  attachment: MessageAttachmentData | null; kind?: 'text' | 'reaction'
  read_by_count?: number; read_by_all?: boolean
}
export type ChatDetail = { id: number; is_group: boolean; name: string; created_by: number; created_by_name: string; member_count: number; participants: { user_id: number; display_name: string; role: string }[]; viewer_muted: boolean }
