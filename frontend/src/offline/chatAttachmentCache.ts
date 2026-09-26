const DB_NAME = 'prepza-chat-attachments-v1'
const STORE = 'attachments'
const MAX_BYTES = 20 * 1024 * 1024

type Row = { key:string; userId:number; attachmentId:number; blob:Blob; fileType:string; filename:string; savedAt:number }

function userId(): number|null { try { const n=Number(localStorage.getItem('prepza-offline-user-id')||0); return Number.isInteger(n)&&n>0?n:null } catch { return null } }
function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve,reject)=>{
    const r=indexedDB.open(DB_NAME,1)
    r.onupgradeneeded=()=>{ const db=r.result; if(!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE,{keyPath:'key'}) }
    r.onsuccess=()=>resolve(r.result); r.onerror=()=>reject(r.error||new Error('Attachment cache unavailable'))
  })
}
export async function cacheChatAttachment(attachmentId:number, viewUrl:string, fileType:string, filename:string): Promise<void> {
  const uid=userId(); if(!uid||attachmentId<=0||!viewUrl||typeof indexedDB==='undefined') return
  try {
    const response=await fetch(viewUrl,{credentials:'include',cache:'no-store'})
    if(!response.ok) return
    const blob=await response.blob()
    if(!blob.size||blob.size>MAX_BYTES) return
    const db=await openDb()
    try { await new Promise<void>((resolve,reject)=>{const tx=db.transaction(STORE,'readwrite');tx.objectStore(STORE).put({key:`${uid}:${attachmentId}`,userId:uid,attachmentId,blob,fileType,filename,savedAt:Date.now()} satisfies Row);tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error)}) } finally { db.close() }
  } catch {}
}
export async function getCachedChatAttachmentUrl(attachmentId:number): Promise<string|null> {
  const uid=userId(); if(!uid||attachmentId<=0||typeof indexedDB==='undefined') return null
  try {
    const db=await openDb()
    try {
      const row=await new Promise<Row|undefined>((resolve,reject)=>{const tx=db.transaction(STORE,'readonly');const r=tx.objectStore(STORE).get(`${uid}:${attachmentId}`);r.onsuccess=()=>resolve(r.result as Row|undefined);r.onerror=()=>reject(r.error)})
      return row?.blob instanceof Blob && row.blob.size ? URL.createObjectURL(row.blob) : null
    } finally { db.close() }
  } catch { return null }
}
