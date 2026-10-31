import { useEffect, useState, type ComponentType } from 'react'
import { api, ApiError } from '../../lib/appApi'
import { N, useTheme, currentThemeMode } from '../../theme/theme'
import { Ic } from '../../ui/icons'
import { listSavedStudyHubOffline } from '../../offline/studyHubOffline'
import { listOfflineGeneratedMaterials, setOfflineUserId } from '../../offline/generatedMaterials'

type StudyMaterialsScreenTarget =
  | 'home'
  | 'document-study'
  | 'upload'
  | 'summary'
  | 'flashcards'
  | 'quiz'
  | 'mind-map'
  | 'podcast-player'

type StudyHubDocument = {
  id: number
  title: string
  status: string
  file_type: string | null
  file_size_bytes?: number | null
  page_count: number | null
  created_at: string | null
  last_opened_at?: string | null
  original_filename?: string
  materials?: { id: number; type: string; status: string; parameters?: Record<string, unknown> }[]
}

type SavedStudyLibraryItem = {
  id: number
  document_id: number | null
  title: string
  material_type?: string
}

type StudyMaterialsScreenProps = {
  setScreen: (screen: StudyMaterialsScreenTarget) => void
  setActiveDocumentId: (id: number | null) => void
  LoadingView: ComponentType<{ label: string }>
  ErrorView: ComponentType<{ error: string }>
  EmptyStateView: ComponentType<{
    icon: string
    title: string
    sub: string
    action?: string
    onAction?: () => void
  }>
  onRememberLastStudyDocument?: (documentId: number) => void
}

type StudyMaterialRow = {
  documentId: number
  documentTitle: string
  materialId: number
  type: string
  parameters?: Record<string, unknown>
}

/**
 * The online /documents response and the IndexedDB lookup intentionally run
 * in parallel. Keep rows from both sources whichever resolves first; replacing
 * the whole array lets a late, empty offline lookup erase online materials.
 */
function mergeStudyMaterialRows(
  current: StudyMaterialRow[],
  incoming: StudyMaterialRow[],
): StudyMaterialRow[] {
  const merged = current.slice()
  const seen = new Set(current.map(row => `${row.documentId}:${row.materialId}`))
  for (const row of incoming) {
    const key = `${row.documentId}:${row.materialId}`
    if (seen.has(key)) continue
    seen.add(key)
    merged.push(row)
  }
  return merged
}

export default function StudyMaterialsScreen({ setScreen, setActiveDocumentId, LoadingView, ErrorView, EmptyStateView, onRememberLastStudyDocument }: StudyMaterialsScreenProps) {
  const { tokens: T } = useTheme()
  const [tab, setTab] = useState<'documents' | 'materials'>('documents')
  const [documents, setDocuments] = useState<StudyHubDocument[]>([])
  const [materials, setMaterials] = useState<StudyMaterialRow[]>([])
  const [offlineDocuments, setOfflineDocuments] = useState<StudyHubDocument[]>([])
  const [savedLibrary, setSavedLibrary] = useState<SavedStudyLibraryItem[]>([])
  const [csrfToken, setCsrfToken] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    let cancelled = false
    const loadOffline = async () => {
      try {
        // Reuse the current session's /me request so local packages remain
        // account-scoped without issuing a duplicate authentication request.
        let userId = Number(localStorage.getItem('prepza-offline-user-id') || 0)
        if (!Number.isInteger(userId) || userId <= 0) userId = 0
        try {
          const me = await meRequest
          const serverUserId = Number(me.id || 0)
          if (Number.isInteger(serverUserId) && serverUserId > 0) {
            userId = serverUserId
            setOfflineUserId(serverUserId)
          }
        } catch { /* offline: keep the last local account id */ }
        if (userId <= 0) return
        const saved = await listSavedStudyHubOffline(userId)
        if (!cancelled) {
          const offlineDocs = saved.map(row => ({
            id: row.documentId,
            title: row.title || 'Saved study document',
            original_filename: row.title || 'Study document',
            status: 'ready',
            file_type: row.fileType || null,
            file_size_bytes: null,
            page_count: row.pageCount || null,
            created_at: new Date(row.savedAt).toISOString(),
          } as StudyHubDocument))
          setOfflineDocuments(offlineDocs)
          const cached = await listOfflineGeneratedMaterials()
          const cachedMaterials = cached.flatMap(row => {
            const match = row.path.match(/^\/documents\/(\d+)\/materials\/(\d+)$/)
            if (!match) return []
            const payload = row.payload as any
            const documentId = Number(match[1])
            const materialId = Number(match[2])
            const doc = offlineDocs.find(d => d.id === documentId)
            if (!payload?.type || !Number.isInteger(materialId) || materialId <= 0) return []
            return [{
              documentId,
              documentTitle: doc?.title || payload?.payload?._prepza?.document_title || 'Study document',
              materialId,
              type: payload.type,
              parameters: payload.parameters || {},
            }]
          })
          // This IndexedDB lookup races the online /documents request. Merge
          // instead of replacing, so an empty cache result cannot erase API rows.
          if (!cancelled) {
            setMaterials(current => mergeStudyMaterialRows(current, cachedMaterials))
          }
        }
      } catch { /* offline package lookup is non-fatal */ }
    }
    const meRequest = api<{ id?: number; csrf_token?: string }>('/me')
    void loadOffline()
    meRequest.then(me => {
      const serverUserId = Number(me.id || 0)
      if (Number.isInteger(serverUserId) && serverUserId > 0) setOfflineUserId(serverUserId)
      if (me.csrf_token) setCsrfToken(me.csrf_token)
    }).catch(() => {})
    api<{ saved: SavedStudyLibraryItem[] }>('/library/saved').then(res => {
      if (!cancelled) setSavedLibrary(res.saved || [])
    }).catch(() => {})
    api<{ documents: StudyHubDocument[] }>('/documents').then(async res => {
      if (cancelled) return
      const ready = res.documents.filter(d => d.status === 'ready')
      setDocuments(ready)
      // /documents now includes the student's ready-material summaries, so
      // My Study no longer needs one HTTP request per document on load.
      const rows = ready.flatMap(d => (d.materials || [])
        .filter(m => m.status === 'ready')
        .map(m => ({
          documentId: d.id,
          documentTitle: d.title,
          materialId: m.id,
          type: m.type,
          parameters: m.parameters,
        })))
      // Merge for the same reason as loadOffline(): whichever source resolves
      // first must not erase rows contributed by the other source.
      if (!cancelled) {
        setMaterials(current => mergeStudyMaterialRows(current, rows))
      }
    }).catch(e => {
      if (!cancelled) {
        setError(e instanceof ApiError ? e.message : 'Could not load your study library.')
        void loadOffline()
      }
    }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])
  const openDocument = (id: number) => { onRememberLastStudyDocument?.(id); setActiveDocumentId(id); setScreen('document-study') }
  const openMaterial = (row: { documentId: number; materialId: number; type: string }) => {
    setActiveDocumentId(row.documentId)
    try {
      sessionStorage.setItem('prepza-open-material', JSON.stringify({
        documentId: row.documentId,
        materialId: row.materialId,
        type: row.type.toLowerCase().replace(/-/g, '_'),
      }))
    } catch {}
    const type = row.type.toLowerCase().replace(/-/g, '_')
    setScreen(type === 'summary' ? 'summary' : type === 'flashcards' ? 'flashcards' : type === 'quiz' || type === 'practice_questions' ? 'quiz' : type === 'mind_map' || type === 'mindmap' ? 'mind-map' : type === 'podcast' ? 'podcast-player' : 'document-study')
  }
  const label = (type: string, parameters?: Record<string, unknown>) => {
    const key = String(type || '').toLowerCase().replace(/-/g, '_')
    const base = ({ summary:'Summary', flashcards:'Flashcards', quiz:'Practice Questions', practice_questions:'Practice Questions', mind_map:'Mind Map', mindmap:'Mind Map', podcast:'Podcast' } as Record<string,string>)[key] || String(type || '').replace(/_/g,' ')
    if (key === 'podcast' && Number(parameters?.duration_minutes) > 0) return `${base} · ${parameters?.duration_minutes} min`
    if (key === 'flashcards' && Number(parameters?.card_count) > 0) return `${base} · ${parameters?.card_count} cards`
    if ((key === 'quiz' || key === 'practice_questions') && Number(parameters?.question_count) > 0) return `${base} · ${parameters?.question_count} questions`
    if (key === 'summary' && Number(parameters?.max_pages) > 0) return `${base} · ${parameters?.max_pages} pages`
    if ((key === 'mind_map' || key === 'mindmap') && Number(parameters?.node_count) > 0) return `${base} · ${parameters?.node_count} nodes`
    return base
  }
  const icon = (type: string) => {
    const key = type.toLowerCase().replace(/-/g, '_')
    if (key === 'summary') return Ic.book('w-5 h-5')
    if (key === 'flashcards') return <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="5" y="5" width="14" height="16" rx="2"/><path d="M8 3h11a2 2 0 0 1 2 2v12M9 9h6M9 13h6"/></svg>
    if (key === 'quiz' || key === 'practice_questions') return Ic.check('w-5 h-5')
    if (key === 'mind_map' || key === 'mindmap') return <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="5" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/><path d="M12 7v4M12 11 6 16M12 11l6 5"/></svg>
    if (key === 'podcast') return Ic.podcast('w-5 h-5')
    return Ic.book('w-5 h-5')
  }
  return <div style={{flex:1,minHeight:0,display:'flex',flexDirection:'column',background:T.pageBg}}>
    <div style={{background:N.navy,padding:'0 18px 20px',flexShrink:0}}>
      <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:10}}><button type="button" aria-label="Back to Home" onClick={()=>setScreen('home')} style={{width:44,height:44,flexShrink:0,background:'rgba(255,255,255,0.1)',border:'none',borderRadius:12,cursor:'pointer',display:'flex',alignItems:'center',justifyContent:'center'}}><div aria-hidden="true" style={{color:'#fff'}}>{Ic.back()}</div></button><div><div style={{fontWeight:800,fontSize:18,color:'#fff'}}>My Study</div><div style={{fontSize:11,color:'rgba(255,255,255,0.45)',marginTop:2}}>Documents and the materials created from them</div></div></div>
      <div style={{display:'flex',gap:8}}>{([['documents','Documents'],['materials','Study Materials']] as const).map(([key,name])=><button key={key} onClick={()=>setTab(key)} style={{flex:1,padding:'8px 10px',borderRadius:11,background:tab===key?N.gold:'rgba(255,255,255,0.08)',color:tab===key?N.navy:'rgba(255,255,255,0.7)',border:'none',fontWeight:800,fontSize:11,cursor:'pointer',fontFamily:'Plus Jakarta Sans'}}>{name}</button>)}</div>
    </div>
    <div style={{flex:1,overflowY:'auto',padding:16}} className="scrollbar-hide">
      {loading ? <LoadingView label="Loading your study library…"/> : error && documents.length===0 && offlineDocuments.length===0 ? <ErrorView error={error}/> : tab==='documents' ? <><div style={{fontSize:12,color:T.textMuted,marginBottom:12}}>Open a document to read, ask Morio about it, or create study materials.</div>{documents.length===0 && offlineDocuments.length===0 && savedLibrary.length===0?<EmptyStateView icon="▣" title="No documents yet" sub="Upload your notes, slides, or past papers to start studying." action="Upload document" onAction={()=>setScreen('upload')}/>:<>
        {Array.from(new Map([...documents, ...offlineDocuments].map(d=>[d.id,d])).values()).map(d=><button key={d.id} onClick={()=>openDocument(d.id)} style={{width:'100%',textAlign:'left',background:T.card,border:`1px solid ${T.border}`,borderRadius:16,padding:15,marginBottom:10,cursor:'pointer',fontFamily:'Plus Jakarta Sans'}}><div style={{display:'flex',alignItems:'center',gap:12}}><div aria-hidden="true" style={{width:44,height:44,flexShrink:0,borderRadius:12,background:currentThemeMode==='dark'?'rgba(201,168,76,0.14)':'rgba(11,20,55,0.05)',color:currentThemeMode==='dark'?N.goldL:N.navy,display:'flex',alignItems:'center',justifyContent:'center'}}>{Ic.book('w-5 h-5')}</div><div style={{flex:1,minWidth:0}}><div style={{fontWeight:800,fontSize:13,color:T.text}} className="line-clamp-1">{d.title}</div><div style={{fontSize:11,color:T.textMuted,marginTop:4}}>{d.page_count?`${d.page_count} pages`:'Document'}{d.last_opened_at?` · studied ${new Date(d.last_opened_at).toLocaleDateString()}`:d.created_at?` · ${new Date(d.created_at).toLocaleDateString()}`:''}</div></div><div style={{color:T.textMuted}}>{Ic.chevR()}</div></div></button>)}
        {savedLibrary.length>0 && <div style={{marginTop:18}}>
          <div style={{fontSize:11,fontWeight:800,color:T.textMuted,marginBottom:8,textTransform:'uppercase',letterSpacing:0.5}}>Saved from Prepza Library</div>
          {savedLibrary.map(item=>{const id=Number(item.document_id);return <div key={item.id} style={{display:'flex',alignItems:'stretch',gap:8,background:T.card,border:`1px solid ${T.border}`,borderRadius:16,padding:8,marginBottom:10}}>
            <button onClick={()=>id>0&&openDocument(id)} style={{flex:1,minWidth:0,textAlign:'left',background:'none',border:'none',padding:7,cursor:id>0?'pointer':'default',fontFamily:'Plus Jakarta Sans'}}><div style={{display:'flex',alignItems:'center',gap:12}}><div aria-hidden="true" style={{width:44,height:44,flexShrink:0,borderRadius:12,background:currentThemeMode==='dark'?'rgba(201,168,76,0.14)':'rgba(11,20,55,0.05)',color:currentThemeMode==='dark'?N.goldL:N.navy,display:'flex',alignItems:'center',justifyContent:'center'}}>{Ic.bookmark('w-5 h-5')}</div><div style={{flex:1,minWidth:0}}><div style={{fontWeight:800,fontSize:13,color:T.text}} className="line-clamp-1">{item.title}</div><div style={{fontSize:11,color:T.textMuted,marginTop:4}}>{String(item.material_type || 'document').replace(/_/g,' ')}</div></div><div style={{color:T.textMuted}}>{Ic.chevR()}</div></div></button>
            <button aria-label={`Remove ${item.title} from Study Hub`} title="Remove from Study Hub" onClick={async()=>{if(!csrfToken)return;try{await api(`/library/${item.id}/save`,{method:'DELETE',headers:{'X-CSRF-Token':csrfToken}});setSavedLibrary(items=>items.filter(x=>x.id!==item.id));if(id>0)setDocuments(items=>items.filter(d=>d.id!==id))}catch{}}} style={{width:42,border:'none',background:'transparent',color:T.textMuted,cursor:'pointer',fontSize:20,borderRadius:10}}>×</button>
          </div>})}
        </div>}
      </>}</> : <><div style={{fontSize:12,color:T.textMuted,marginBottom:12}}>Everything here was created from one of your documents. Tap a material to replay it.</div>{materials.length===0?<EmptyStateView icon="✦" title="No study materials yet" sub="Open a document and create a summary, flashcards, practice questions, mind map, or podcast." action="Open My Documents" onAction={()=>setTab('documents')}/>:materials.map((m,i)=><button key={`${m.documentId}-${m.type}-${i}`} onClick={()=>openMaterial(m)} style={{width:'100%',textAlign:'left',background:T.card,border:`1px solid ${T.border}`,borderRadius:16,padding:15,marginBottom:10,cursor:'pointer',fontFamily:'Plus Jakarta Sans'}}><div style={{display:'flex',alignItems:'center',gap:12}}><div aria-hidden="true" style={{width:44,height:44,flexShrink:0,borderRadius:12,background:currentThemeMode==='dark'?'rgba(201,168,76,0.14)':'rgba(11,20,55,0.05)',color:currentThemeMode==='dark'?N.goldL:N.navy,display:'flex',alignItems:'center',justifyContent:'center'}}>{icon(m.type)}</div><div style={{flex:1,minWidth:0}}><div style={{fontWeight:800,fontSize:13,color:T.text}}>{label(m.type, m.parameters)}</div><div style={{fontSize:11,color:T.textMuted,marginTop:4}} className="line-clamp-1">From: {m.documentTitle}</div></div><div style={{color:T.textMuted}}>{Ic.chevR()}</div></div></button>)}</>}
      <div style={{height:'calc(90px + env(safe-area-inset-bottom, 0px))'}}/>
    </div>
  </div>
}
