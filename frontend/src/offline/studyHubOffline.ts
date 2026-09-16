import { setOfflineUserId, saveGeneratedMaterialOffline, cacheGeneratedAudioOffline } from './generatedMaterials'

const STUDY_CACHE = 'prepza-study-assets-v1'
const META_DB = 'prepza-offline-v2'
const META_STORE = 'savedStudyHub'
const ASSET_DB = 'prepza-offline-study-v1'
const ASSET_STORE = 'documents'
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

type StoredStudyAsset = {
  key: string
  userId: number
  documentId: number
  blob: Blob
  savedAt: number
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

function openAssetDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(ASSET_DB, 1)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(ASSET_STORE)) db.createObjectStore(ASSET_STORE, { keyPath: 'key' })
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error || new Error('Could not open offline study package storage.'))
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

async function putStudyAsset(asset: StoredStudyAsset) {
  const db = await openAssetDb()
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(ASSET_STORE, 'readwrite')
      tx.objectStore(ASSET_STORE).put(asset)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error || new Error('Could not persist the complete study document.'))
    })
  } finally { db.close() }
}

async function getStudyAsset(key: string): Promise<StoredStudyAsset | undefined> {
  const db = await openAssetDb()
  try {
    return await new Promise<StoredStudyAsset | undefined>((resolve, reject) => {
      const tx = db.transaction(ASSET_STORE, 'readonly')
      const request = tx.objectStore(ASSET_STORE).get(key)
      request.onsuccess = () => resolve(request.result as StoredStudyAsset | undefined)
      request.onerror = () => reject(request.error)
    })
  } finally { db.close() }
}

async function deleteStudyAsset(key: string) {
  try {
    const db = await openAssetDb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(ASSET_STORE, 'readwrite')
      tx.objectStore(ASSET_STORE).delete(key)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
    db.close()
  } catch (_) {}
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

/**
 * Explicit Save -> Download. A saved study is a self-contained local package:
 * the complete source document is stored as a Blob in IndexedDB. Generated
 * materials already attached to the document are also copied into the local
 * generated-material store so reopening the study never needs their API.
 */
export async function saveStudyHubDocumentOffline(documentId: number): Promise<SavedStudyHubMeta> {
  if (!('indexedDB' in window)) throw new Error('Offline storage is unavailable in this browser.')
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

  const assetKey = `${userId}:${documentId}`
  const cache = 'caches' in window ? await caches.open(STUDY_CACHE) : null
  const assetUrls: string[] = []
  const fileUrl = detail.view_url || detail.file_url || detail.url || detail.download_url

  try {
    if (typeof fileUrl !== 'string' || !fileUrl) throw new Error('This StudyHub document has no downloadable study content yet.')
    const url = absoluteUrl(fileUrl)
    const response = await fetch(url, { credentials: 'include', cache: 'no-store' })
    if (!response.ok || response.type === 'opaque') throw new Error('Could not download the complete study document.')
    const length = Number(response.headers.get('content-length') || 0)
    if (length > MAX_SINGLE_ASSET_BYTES) throw new Error('This document is too large to save for offline study.')
    const blob = await response.blob()
    if (!blob.size) throw new Error('The downloaded study document is empty.')
    if (blob.size > MAX_SINGLE_ASSET_BYTES) throw new Error('This document is too large to save for offline study.')

    await putStudyAsset({ key: assetKey, userId, documentId, blob, savedAt: Date.now() })
    assetUrls.push(url)
    if (cache) { try { await cacheResponse(cache, url, new Response(blob, { headers: { 'Content-Type': blob.type || 'application/pdf' } })) } catch (_) {} }

    // Package every generated material that already exists for this document.
    // Missing/unsupported GET endpoints are intentionally non-fatal: Save must
    // still succeed with the complete source document, while available results
    // are persisted for zero-network reopening.
    const generatedPaths = ['summarize', 'quiz', 'flashcards', 'podcast-script', 'podcast-audio', 'mind-map']
    await Promise.all(generatedPaths.map(async feature => {
      try {
        const materialResponse = await fetch(`/documents/${documentId}/${feature}`, { credentials: 'include', cache: 'no-store' })
        if (!materialResponse.ok) return
        const payload = await materialResponse.json()
        await saveGeneratedMaterialOffline(`/documents/${documentId}/${feature}`, null, payload)
        if (feature === 'podcast-audio' && payload?.audio_status === 'ready' && payload?.audio_url) {
          await cacheGeneratedAudioOffline(String(payload.audio_url))
        }
      } catch (_) {}
    }))

    const meta: SavedStudyHubMeta = { key: assetKey, userId, documentId, title: detail.title, fileType: detail.file_type, pageCount: Number(detail.page_count || 0) || undefined, savedAt: Date.now(), assetUrls }
    await putMeta(meta)
    window.dispatchEvent(new CustomEvent('prepza:studyhub-offline-changed', { detail: meta }))
    return meta
  } catch (error) {
    await deleteStudyAsset(assetKey)
    for (const url of assetUrls) { if (cache) { try { await cache.delete(url) } catch (_) {} } }
    throw error
  }
}

export async function getOfflineStudyDocumentBlob(documentId: number, userId: number): Promise<Blob | null> {
  if (!Number.isInteger(documentId) || documentId <= 0 || !Number.isInteger(userId) || userId <= 0) return null
  try {
    const meta = await getMeta(`${userId}:${documentId}`)
    if (!meta) return null
    const asset = await getStudyAsset(`${userId}:${documentId}`)
    return asset?.blob instanceof Blob ? asset.blob : null
  } catch (_) { return null }
}

export async function getOfflineStudyDocumentUrl(documentId: number, userId: number): Promise<string | null> {
  const blob = await getOfflineStudyDocumentBlob(documentId, userId)
  return blob ? URL.createObjectURL(blob) : null
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
    let bytes = 0
    let documents = 0
    for (const row of rows) {
      const asset = await getStudyAsset(row.key)
      if (!asset?.blob) continue
      bytes += asset.blob.size
      documents += 1
    }
    return { bytes, documents }
  } catch (_) { return { bytes: 0, documents: 0 } }
}

export async function removeStudyHubOfflineCopy(documentId: number, userId: number): Promise<void> {
  const key = `${userId}:${documentId}`
  const meta = await getSavedStudyHubOffline(documentId, userId)
  await deleteStudyAsset(key)
  try {
    const cache = await caches.open(STUDY_CACHE)
    for (const url of meta?.assetUrls || []) await cache.delete(url)
  } catch (_) {}
  await deleteMeta(key)
  window.dispatchEvent(new CustomEvent('prepza:studyhub-offline-changed', { detail: { userId, documentId, availableOffline: false } }))
}
