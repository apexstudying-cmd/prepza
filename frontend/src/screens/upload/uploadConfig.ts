// Shared upload and attachment policy. Values preserve the backend limits.
export const ALLOWED_UPLOAD_EXTENSIONS = ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'jpg', 'jpeg', 'png']
export const MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024 // 50 MB - matches backend MAX_DOCUMENT_SIZE_BYTES
export const MAX_CHAT_ATTACHMENT_SIZE_BYTES = 20 * 1024 * 1024 // 20 MB - matches backend CHAT_ATTACHMENT_MAX_SIZE_BYTES
export const IMAGE_FILE_TYPES = ['jpg', 'jpeg', 'png']
