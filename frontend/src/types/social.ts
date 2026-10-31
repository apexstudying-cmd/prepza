export type FollowListUser = { user_id: number; display_name: string; is_following: boolean; is_pending?: boolean }
export type FollowRequestItem = { id: number; requester_id: number; requester_display_name: string; created_at: string | null }
export type MessageRequestItem = { conversation_id: number; requester_id: number; requester_display_name: string; has_message: boolean; created_at: string | null }
