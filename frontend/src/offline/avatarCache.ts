const DB_NAME = 'prepza-avatar-cache-v1'
const STORE = 'avatars'
const KEY = 'current'

type AvatarRow = { key:string; userId:number; blob:Blob; savedAt:number }

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve,reject)=>{
    const request=indexedDB.open(DB_NAME,1)
    request.onupgradeneeded=()=>{ const db=request.result; if(!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE,{keyPath:'key'}) }
    request.onsuccess=()=>resolve(request.result)
    request.onerror=()=>reject(request.error||new Error('Avatar cache unavailable'))
  })
}

export async function cacheAvatar(userId:number, avatarUrl:string): Promise<void> {
  if(!Number.isInteger(userId)||userId<=0||!avatarUrl||typeof indexedDB==='undefined') return
  try {
    const response=await fetch(avatarUrl,{credentials:'include',cache:'no-store'})
    if(!response.ok) return
    const blob=await response.blob()
    if(!blob.size||blob.size>2*1024*1024) return
    const db=await openDb()
    try {
      await new Promise<void>((resolve,reject)=>{
        const tx=db.transaction(STORE,'readwrite')
        tx.objectStore(STORE).put({key:KEY,userId,blob,savedAt:Date.now()} satisfies AvatarRow)
        tx.oncomplete=()=>resolve(); tx.onerror=()=>reject(tx.error)
      })
    } finally { db.close() }
  } catch {}
}

export async function getCachedAvatar(userId:number): Promise<string|null> {
  if(!Number.isInteger(userId)||userId<=0||typeof indexedDB==='undefined') return null
  try {
    const db=await openDb()
    try {
      const row=await new Promise<AvatarRow|undefined>((resolve,reject)=>{
        const tx=db.transaction(STORE,'readonly'); const req=tx.objectStore(STORE).get(KEY)
        req.onsuccess=()=>resolve(req.result as AvatarRow|undefined); req.onerror=()=>reject(req.error)
      })
      if(!row||row.userId!==userId||!(row.blob instanceof Blob)||!row.blob.size) return null
      return URL.createObjectURL(row.blob)
    } finally { db.close() }
  } catch { return null }
}

export async function clearCachedAvatar(userId:number): Promise<void> {
  if(!Number.isInteger(userId)||userId<=0||typeof indexedDB==='undefined') return
  try {
    const db=await openDb()
    try {
      await new Promise<void>((resolve,reject)=>{
        const tx=db.transaction(STORE,'readwrite'); const req=tx.objectStore(STORE).delete(KEY)
        req.onsuccess=()=>resolve(); req.onerror=()=>reject(req.error)
      })
    } finally { db.close() }
  } catch {}
}
