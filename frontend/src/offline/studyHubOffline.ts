const STUDY_CACHE = 'prepza-study-assets-v2'
const META_DB = 'prepza-offline-v2'
const META_STORE = 'savedStudyHub'
const MAX_SINGLE_ASSET_BYTES = 75 * 1024 * 1024

type SavedStudyHubMeta = {
  key: string
  userId: number
  documentId: number
  title?: string
  fileType?: string
  pageCount?: number
  savedAt: number
  assetUrls: string[]
}

function openMetaDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(META_DB, 1)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(META_STORE)) db.createObjectStore(META_STORE, { keyPath: 'key' })
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error || new Error('Could not open offline storage.'))
  })
}

async function putMeta(meta: SavedStudyHubMeta) {
  const db = await openMetaDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(META_STORE, 'readwrite')
    tx.objectStore(META_STORE).put(meta)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error || new Error('Could not persist offline metadata.'))
  })
  db.close()
}

async function deleteMeta(key: string) {
  try {
    const db = await openMetaDb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(META_STORE, 'readwrite')
      tx.objectStore(META_STORE).delete(key)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
    db.close()
  } catch (_) {}
}

function absoluteUrl(value: string): string {
  return new URL(value, window.location.origin).href
}

async function cacheResponse(cache: Cache, url: string, response: Response): Promise<boolean> {
  if (!response.ok || response.type === 'opaque') return false
  const length = Number(response.headers.get('content-length') || 0)
  if (length > MAX_SINGLE_ASSET_BYTES) throw new Error('This document is too large to save for offline study.')
  await cache.put(url, response.clone())
  return true
}

async function cacheUrl(cache: Cache, url: string): Promise<boolean> {
  const response = await fetch(url, { credentials: 'include', cache: 'no-store' })
  return cacheResponse(cache, url, response)
}

/**
 * Explicit Save -> Download contract. This is only called after the student
 * saves an item into StudyHub; arbitrary Explore opens never call this.
 */
export async function saveStudyHubDocumentOffline(documentId: number): Promise<SavedStudyHubMeta> {
  if (!('caches' in window) || !('indexedDB' in window)) throw new Error('Offline storage is unavailable in this browser.')

  let me: { id: number }
  let detail: any
  try {
    const [meResponse, detailResponse] = await Promise.all([
      fetch('/me', { credentials: 'include', cache: 'no-store' }),
      fetch(`/documents/${documentId}`, { credentials: 'include', cache: 'no-store' }),
    ])
    if (!meResponse.ok || !detailResponse.ok) throw new Error('Could not prepare this StudyHub item for offline use.')
    me = await meResponse.json()
    detail = await detailResponse.json()
  } catch (error) {
    throw error instanceof Error ? error : new Error('Could not prepare this StudyHub item for offline use.')
  }

  const userId = Number(me.id)
  if (!Number.isInteger(userId) || userId <= 0) throw new Error('Could not identify the signed-in student.')

  if (navigator.storage?.persist) {
    try { await navigator.storage.persist() } catch (_) {}
  }

  const cache = await caches.open(STUDY_CACHE)
  const assetUrls: string[] = []
  const fileUrl = detail.file_url || detail.url || detail.download_url
  if (typeof fileUrl === 'string' && fileUrl) {
    const url = absoluteUrl(fileUrl)
    await cacheUrl(cache, url)
    assetUrls.push(url)
  }

  const pageCount = Number(detail.page_count || 0)
  // Native reader pages are the canonical offline representation for content
  // that is not directly renderable by the browser (DOC/DOCX/PPT/PPTX/images).
  // Cache every page now, while the student is online, rather than lazily.
  if (pageCount > 0) {
    for (let page = 1; page <= pageCount; page += 1) {
      const pageUrl = `/documents/${documentId}/reading/page/${page}?prepza_user=${encodeURIComponent(String(userId))}`
      const absolute = absoluteUrl(pageUrl)
      const ok = await cacheUrl(cache, absolute)
      if (!ok) throw new Error(`Could not save page ${page} for offline study.`)
      assetUrls.push(absolute)
    }
  }

  if (!assetUrls.length) throw new Error('This StudyHub document has no downloadable study content yet.')

  const meta: SavedStudyHubMeta = {
    key: `${userId}:${documentId}`,
    userId,
    documentId,
    title: detail.title,
    fileType: detail.file_type,
    pageCount: pageCount || undefined,
    savedAt: Date.now(),
    assetUrls,
  }
  await putMeta(meta)
  window.dispatchEvent(new CustomEvent('prepza:studyhub-offline-changed', { detail: meta }))
  return meta
}

export async function removeStudyHubOfflineCopy(documentId: number, userId: number): Promise<void> {
  const key = `${userId}:${documentId}`
  try {
    const db = await openMetaDb()
    const meta = await new Promise<SavedStudyHubMeta | undefined>((resolve, reject) => {
      const tx = db.transaction(META_STORE, 'readonly')
      const request = tx.objectStore(META_STORE).get(key)
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
    db.close()
    const cache = await caches.open(STUDY_CACHE)
    for (const url of meta?.assetUrls || []) await cache.delete(url)
  } catch (_) {}
  await deleteMeta(key)
  window.dispatchEvent(new CustomEvent('prepza:studyhub-offline-changed', { detail: { userId, documentId, availableOffline: false } }))
}
