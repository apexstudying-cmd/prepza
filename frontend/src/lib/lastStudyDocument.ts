const LAST_STUDY_DOCUMENT_KEY = 'prepza-last-study-document-id'

function storageKey(): string {
  try {
    const userId = typeof window === 'undefined' ? null : window.localStorage.getItem('prepza-offline-user-id')
    return userId ? LAST_STUDY_DOCUMENT_KEY + ':' + userId : LAST_STUDY_DOCUMENT_KEY
  } catch {
    return LAST_STUDY_DOCUMENT_KEY
  }
}

export function rememberLastStudyDocument(documentId: number | null): void {
  if (documentId == null || !Number.isSafeInteger(documentId) || documentId <= 0) return
  try {
    if (typeof window !== 'undefined') window.localStorage.setItem(storageKey(), String(documentId))
  } catch {
    // Browser storage is optional; navigation must continue when it is unavailable.
  }
}

export function readLastStudyDocumentId(): number | null {
  try {
    if (typeof window === 'undefined') return null
    const raw = window.localStorage.getItem(storageKey())
    const documentId = raw ? Number(raw) : NaN
    return Number.isSafeInteger(documentId) && documentId > 0 ? documentId : null
  } catch {
    return null
  }
}
