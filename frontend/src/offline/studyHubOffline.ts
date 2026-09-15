import { setOfflineUserId } from './generatedMaterials'

const STUDY_CACHE = 'prepza-study-assets-v1'
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
    const request = indexedDB.open(META_DB, 2)
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
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(META_STORE, 'readwrite')
      tx.objectStore(META_STORE).put(meta)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error || new Error('Could not persist offline metadata.'))
    })
  } finally { db.close() }
}

async function getMeta(key: string): Promise<SavedStudyHubMeta | undefined> {
  const db = await openMetaDb()
  try {
    return await new Promise<SavedStudyHubMeta | undefined>((resolve, reject) => {
      const tx = db.transaction(META_STORE, 'readonly')
      const request = tx.objectStore(META_STORE).get(key)
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
  } finally { db.close() }
}

async function getAllMeta(userId?: number): Promise<SavedStudyHubMeta[]> {
  const db = await openMetaDb()
  try {
    return await new Promise<SavedStudyHubMeta[]>((resolve, reject) => {
      const tx = db.transaction(META_STORE, 'readonly')
      const request = tx.objectStore(META_STORE).getAll()
      request.onsuccess = () => {
        const rows = (request.result as SavedStudyHubMeta[]).filter(row => !userId || row.userId === userId)
        rows.sort((a, b) => b.savedAt - a.savedAt)
        resolve(rows)
      }
      request.onerror = () => reject(request.error)
    })
  } finally { db.close() }
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

function absoluteUrl(value: string): string { return new URL(value, window.location.origin).href }

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

/** Explicit Save -> Download. Explore opens never call this function. */
export async function saveStudyHubDocumentOffline(documentId: number): Promise<SavedStudyHubMeta> {
  if (!('caches' in window) || !('indexedDB' in window)) throw new Error('Offline storage is unavailable in this browser.')
  const [meResponse, detailResponse] = await Promise.all([
    fetch('/me', { credentials: 'include', cache: 'no-store' }),
    fetch(`/documents/${documentId}`, { credentials: 'include', cache: 'no-store' }),
  ])
  if (!meResponse.ok || !detailResponse.ok) throw new Error('Could not prepare this StudyHub item for offline use.')

  const me: { id: number } = await meResponse.json()
  const detail: any = await detailResponse.json()
  const userId = Number(me.id)
  if (!Number.isInteger(userId) || userId <= 0) throw new Error('Could not identify the signed-in student.')
  setOfflineUserId(userId)

  if (navigator.storage?.persist) { try { await navigator.storage.persist() } catch (_) {} }

  const cache = await caches.open(STUDY_CACHE)
  const assetUrls: string[] = []
  const fileUrl = detail.view_url || detail.file_url || detail.url || detail.download_url

  try {
    if (typeof fileUrl === 'string' && fileUrl) {
      const url = absoluteUrl(fileUrl)
      if (await cacheUrl(cache, url)) assetUrls.push(url)
    }

    const pageCount = Number(detail.page_count || 0)
    if (pageCount > 0) {
      for (let page = 0; page < pageCount; page += 1) {
        const url = absoluteUrl(`/documents/${documentId}/reading/page/${page}?prepza_user=${encodeURIComponent(String(userId))}`)
        if (!await cacheUrl(cache, url)) throw new Error(`Could not save page ${page + 1} for offline study.`)
        assetUrls.push(url)
      }
    }
    if (!assetUrls.length) throw new Error('This StudyHub document has no downloadable study content yet.')

    const meta: SavedStudyHubMeta = { key: `${userId}:${documentId}`, userId, documentId, title: detail.title, fileType: detail.file_type, pageCount: pageCount || undefined, savedAt: Date.now(), assetUrls }
    await putMeta(meta)
    window.dispatchEvent(new CustomEvent('prepza:studyhub-offline-changed', { detail: meta }))
    return meta
  } catch (error) {
    // Never leave a half-downloaded document presenting as available offline.
    for (const url of assetUrls) { try { await cache.delete(url) } catch (_) {} }
    throw error
  }
}

export async function listSavedStudyHubOffline(userId?: number): Promise<SavedStudyHubMeta[]> {
  try { return await getAllMeta(userId) } catch (_) { return [] }
}

export async function getSavedStudyHubOffline(documentId: number, userId: number): Promise<SavedStudyHubMeta | null> {
  try { return (await getMeta(`${userId}:${documentId}`)) || null } catch (_) { return null }
}

export async function getOfflineStudyStorageUsage(userId?: number): Promise<{ bytes: number; documents: number }> {
  try {
    const rows = await getAllMeta(userId)
    const urls = new Set(rows.flatMap(row => row.assetUrls || []))
    const cache = await caches.open(STUDY_CACHE)
    let bytes = 0
    for (const url of urls) {
      const response = await cache.match(url)
      if (!response) continue
      const length = Number(response.headers.get('content-length') || 0)
      if (length > 0) bytes += length
      else { try { bytes += (await response.clone().arrayBuffer()).byteLength } catch (_) {} }
    }
    return { bytes, documents: rows.length }
  } catch (_) { return { bytes: 0, documents: 0 } }
}

export async function removeStudyHubOfflineCopy(documentId: number, userId: number): Promise<void> {
  const key = `${userId}:${documentId}`
  const meta = await getSavedStudyHubOffline(documentId, userId)
  try {
    const cache = await caches.open(STUDY_CACHE)
    for (const url of meta?.assetUrls || []) await cache.delete(url)
  } catch (_) {}
  await deleteMeta(key)
  window.dispatchEvent(new CustomEvent('prepza:studyhub-offline-changed', { detail: { userId, documentId, availableOffline: false } }))
}
