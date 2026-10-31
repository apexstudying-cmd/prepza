export type GroupPrivacy = 'public' | 'private' | 'course_only'
export type GroupSummary = {
  id: number; name: string; description: string | null; privacy: GroupPrivacy
  university_id: number | null; program_id: number | null; unit_id: number | null; unit_code: string | null
  year: number | null; member_count: number; created_by: number; created_at: string | null
  is_member: boolean; role: 'admin' | 'member' | null
}
export type GroupPostData = {
  id: number; group_id: number; post_type: 'post' | 'question'; body: string | null; is_removed: boolean
  author: string; author_id: number; like_count: number | null; viewer_liked: boolean
  vote_count: number | null; viewer_voted: boolean; comment_count: number; created_at: string | null
}
export type GroupPostCommentData = {
  id: number; group_post_id: number; body: string | null; is_removed: boolean; author: string; author_id: number
  marked_helpful: boolean; created_at: string | null
}
export type GroupPostDetail = GroupPostData & { comments: GroupPostCommentData[] }
export type GroupMemberData = { user_id: number; display_name: string; role: 'admin' | 'member'; joined_at: string | null }
export type GroupFileData = {
  id: number; group_id: number; document_id: number; title: string | null; file_type: string | null
  file_size_bytes: number | null; content_hash?: string | null; page_count: number | null; view_url: string | null
  shared_by: string; shared_by_user_id: number; created_at: string | null
}
