from __future__ import annotations

from pathlib import Path
import re

APP = Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.tsx"
text = APP.read_text(encoding="utf-8")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if old not in source:
        raise RuntimeError(f"Library/My Study patch anchor missing: {label}")
    if source.count(old) != 1:
        raise RuntimeError(f"Library/My Study patch anchor is not unique: {label}")
    return source.replace(old, new, 1)


# Library is the discovery surface. Saved library items now live under My Study,
# while the existing save/bookmark action remains available in Browse.
text = replace_once(
    text,
    "const [activeTab, setActiveTab] = useState<'Browse' | 'Saved' | 'Published'>('Browse')",
    "const [activeTab, setActiveTab] = useState<'Browse' | 'Published'>('Browse')",
    "Library active tab type",
)

text = replace_once(
    text,
    "{(['Browse', 'Saved', 'Published'] as const).map(t => (",
    "{(['Browse', 'Published'] as const).map(t => (",
    "Library tab list",
)

saved_block = re.compile(
    r"\n        \{activeTab === 'Saved' && \([\s\S]*?\n        \)\}\n        \{activeTab === 'Published' && \(",
)
text, count = saved_block.subn("\n        {activeTab === 'Published' && (", text, count=1)
if count != 1:
    raise RuntimeError("Library Saved tab content block anchor missing or ambiguous")

# Surface a precise save failure when the student already has the same content
# in Study Hub. The backend remains authoritative; this just gives the student
# the product-level explanation instead of silently reverting the bookmark UI.
text = replace_once(
    text,
    "const [savedIds, setSavedIds] = useState<Set<number>>(new Set())",
    "const [savedIds, setSavedIds] = useState<Set<number>>(new Set())\n  const [saveActionError, setSaveActionError] = useState('')",
    "Library save action error state",
)

text = replace_once(
    text,
    "  const toggleSave = async (pub: LibraryPublicationSummary) => {\n    if (!csrfToken) return\n    const isSaved = savedIds.has(pub.id)",
    "  const toggleSave = async (pub: LibraryPublicationSummary) => {\n    if (!csrfToken) return\n    setSaveActionError('')\n    const isSaved = savedIds.has(pub.id)",
    "Library save error reset",
)

text = replace_once(
    text,
    "    } catch {\n      setSavedIds(prev => { const next = new Set(prev); isSaved ? next.add(pub.id) : next.delete(pub.id); return next })",
    "    } catch (error) {\n      setSavedIds(prev => { const next = new Set(prev); isSaved ? next.add(pub.id) : next.delete(pub.id); return next })\n      setSaveActionError(error instanceof ApiError ? error.message : 'Could not update this Library item.')",
    "Library save error message",
)

# My Study owns the student's saved Library publications. Reuse the existing
# /library/saved endpoint rather than creating a second persistence mechanism.
text = replace_once(
    text,
    "const [materials, setMaterials] = useState<{ documentId: number; documentTitle: string; type: string }[]>([])\n  const [loading, setLoading] = useState(true)",
    "const [materials, setMaterials] = useState<{ documentId: number; documentTitle: string; type: string }[]>([])\n  const [savedLibrary, setSavedLibrary] = useState<SavedLibraryItem[]>([])\n  const [csrfToken, setCsrfToken] = useState('')\n  const [removedMaterialKeys, setRemovedMaterialKeys] = useState<Set<string>>(() => {\n    try { return new Set(JSON.parse(localStorage.getItem('prepza-removed-study-materials') || '[]')) } catch { return new Set() }\n  })\n  const [loading, setLoading] = useState(true)",
    "My Study saved Library state and removal state",
)

text = replace_once(
    text,
    "  useEffect(() => {\n    let cancelled = false\n    api<{ documents: HomeDocument[] }>('/documents').then(async res => {",
    "  useEffect(() => {\n    api<{ csrf_token?: string }>('/me').then(res => { if (res.csrf_token) setCsrfToken(res.csrf_token) }).catch(() => {})\n  }, [])\n\n  useEffect(() => {\n    let cancelled = false\n    api<{ documents: HomeDocument[] }>('/documents').then(async res => {",
    "My Study CSRF loader",
)

study_effect_anchor = "  useEffect(() => {\n    let cancelled = false\n    api<{ documents: HomeDocument[] }>('/documents').then(async res => {"
text = replace_once(
    text,
    study_effect_anchor,
    "  useEffect(() => {\n    let cancelled = false\n    api<{ saved: SavedLibraryItem[] }>('/library/saved').then(res => {\n      if (!cancelled) {\n        const normalized = (res.saved || []).map(item => ({\n          ...item,\n          document_id: item.document_id ?? (item as any).documentId,\n        }))\n        setSavedLibrary(normalized)\n      }\n    }).catch(() => {})\n    return () => { cancelled = true }\n  }, [])\n\n" + study_effect_anchor,
    "My Study saved Library loader",
)

# Replace the Documents tab branch. My Documents can be removed from Study Hub
# without touching Library source publications. Saved Library items use the
# Library unsave endpoint, which removes the student's personal Study Hub copy
# while leaving the public Library publication intact.
doc_branch = re.compile(r"tab==='documents' \? <>[\s\S]*?</> : <>")
replacement = """tab==='documents' ? <>
        <div style={{fontSize:12,color:T.textMuted,marginBottom:12}}>Your documents and anything you've saved from the Prepza Library.</div>
        {documents.length===0 && savedLibrary.length===0 ? <EmptyState icon=\"▣\" title=\"No study items yet\" sub=\"Save study material from the Prepza Library or upload your own notes, slides, or past papers.\" action=\"Open Prepza Library\" onAction={()=>setScreen('library')}/> : <>
          {documents.length>0 && <>
            <div style={{fontSize:11,fontWeight:800,color:T.textMuted,marginBottom:8,textTransform:'uppercase',letterSpacing:0.5}}>My Documents</div>
            {documents.map(d=><div key={d.id} style={{display:'flex',alignItems:'stretch',gap:8,background:T.card,border:`1px solid ${T.border}`,borderRadius:16,padding:8,marginBottom:10}}><button onClick={()=>openDocument(d.id)} style={{flex:1,minWidth:0,textAlign:'left',background:'none',border:'none',padding:7,cursor:'pointer',fontFamily:'Plus Jakarta Sans'}}><div style={{display:'flex',alignItems:'center',gap:12}}><div style={{width:44,height:44,borderRadius:12,background:`${N.gold}18`,color:N.gold,display:'flex',alignItems:'center',justifyContent:'center',fontWeight:900,flexShrink:0}}>▣</div><div style={{flex:1,minWidth:0}}><div style={{fontWeight:800,fontSize:13,color:T.text}} className=\"line-clamp-1\">{d.title}</div><div style={{fontSize:11,color:T.textMuted,marginTop:4}}>{d.page_count?`${d.page_count} pages`:'Document'}{d.created_at?` · ${new Date(d.created_at).toLocaleDateString()}`:''}</div></div><div style={{color:T.textMuted}}>{Ic.chevR()}</div></div></button><button aria-label={`Remove ${d.title} from Study Hub`} title=\"Remove from Study Hub\" onClick={async e=>{e.stopPropagation();if(!csrfToken)return;try{await api(`/documents/${d.id}`,{method:'DELETE',headers:{'X-CSRF-Token':csrfToken}});const me=await api<{id:number}>('/me');try{const mod=await import('./offline/studyHubOffline');await mod.removeStudyHubOfflineCopy(d.id,Number(me.id))}catch{}setDocuments(items=>items.filter(item=>item.id!==d.id));setSavedLibrary(items=>items.filter(item=>Number(item.document_id)!==d.id))}catch(error){window.alert(error instanceof ApiError?error.message:'Could not remove this document from Study Hub.')}}} style={{width:42,border:'none',background:'transparent',color:T.textMuted,cursor:'pointer',fontSize:20,borderRadius:10}}>×</button></div>)}
          </>}
          {savedLibrary.length>0 && <>
            <div style={{fontSize:11,fontWeight:800,color:T.textMuted,margin:'16px 0 8px',textTransform:'uppercase',letterSpacing:0.5}}>Saved from Prepza Library</div>
            {savedLibrary.map(item=>{ const targetDocumentId=Number(item.document_id ?? (item as any).documentId); return <div key={`library-${item.id}`} style={{display:'flex',alignItems:'stretch',gap:8,background:T.card,border:`1px solid ${T.border}`,borderRadius:16,padding:8,marginBottom:10}}><button onClick={()=>{if(Number.isFinite(targetDocumentId)&&targetDocumentId>0)openDocument(targetDocumentId)}} style={{flex:1,minWidth:0,textAlign:'left',background:'none',border:'none',padding:7,cursor:Number.isFinite(targetDocumentId)&&targetDocumentId>0?'pointer':'default',fontFamily:'Plus Jakarta Sans',opacity:Number.isFinite(targetDocumentId)&&targetDocumentId>0?1:0.72}}><div style={{display:'flex',alignItems:'center',gap:12}}><div style={{width:44,height:44,borderRadius:12,background:`${N.gold}18`,color:N.gold,display:'flex',alignItems:'center',justifyContent:'center',fontWeight:900,flexShrink:0}}>{Ic.bookmark()}</div><div style={{flex:1,minWidth:0}}><div style={{fontWeight:800,fontSize:13,color:T.text}} className=\"line-clamp-1\">{item.title}</div><div style={{fontSize:11,color:T.textMuted,marginTop:4}}>{item.material_type.replace(/_/g,' ')}{item.author?` · ${item.author}`:''}</div></div><div style={{color:T.textMuted}}>{Ic.chevR()}</div></div></button><button aria-label={`Remove ${item.title} from Study Hub`} title=\"Remove from Study Hub\" onClick={async e=>{e.stopPropagation();if(!csrfToken)return;try{await api(`/library/${item.id}/save`,{method:'DELETE',headers:{'X-CSRF-Token':csrfToken}});setSavedLibrary(items=>items.filter(saved=>saved.id!==item.id));if(Number.isFinite(targetDocumentId)&&targetDocumentId>0)setDocuments(items=>items.filter(doc=>doc.id!==targetDocumentId))}catch(error){window.alert(error instanceof ApiError?error.message:'Could not remove this Library item from Study Hub.')}}} style={{width:42,border:'none',background:'transparent',color:T.textMuted,cursor:'pointer',fontSize:20,borderRadius:10}}>×</button></div> })}
          </>}
        </>}
      </> : <>"""
text, count = doc_branch.subn(replacement, text, count=1)
if count != 1:
    raise RuntimeError("My Study Documents tab branch anchor missing or ambiguous")

# Replace the Study Materials list with a per-student hide/remove action. The
# generated material itself stays shared and cannot be deleted globally.
materials_branch = re.compile(r"\{materials\.length===0\?<EmptyState[\s\S]*?\}\s*\}\s*<div style=\{\{height:'calc\(90px \+ env\(\\'safe-area-inset-bottom, 0px\\'\)\)'\}\}\/>\s*", re.M)
materials_old = """{materials.length===0?<EmptyState icon=\"✦\" title=\"No study materials yet\" sub=\"Open a document and create a summary, flashcards, practice questions, mind map, or podcast.\" action=\"Open My Documents\" onAction={()=>setTab('documents')}/>:materials.map((m,i)=><button key={`${m.documentId}-${m.type}-${i}`} onClick={()=>openMaterial(m)} style={{width:'100%',textAlign:'left',background:T.card,border:`1px solid ${T.border}`,borderRadius:16,padding:15,marginBottom:10,cursor:'pointer',fontFamily:'Plus Jakarta Sans'}}><div style={{display:'flex',alignItems:'center',gap:12}}><div style={{width:44,height:44,borderRadius:12,background:`${N.navy}0D`,color:N.navy,display:'flex',alignItems:'center',justifyContent:'center',fontWeight:900,fontSize:18}}>{icon(m.type)}</div><div style={{flex:1,minWidth:0}}><div style={{fontWeight:800,fontSize:13,color:T.text}}>{label(m.type)}</div><div style={{fontSize:11,color:T.textMuted,marginTop:4}} className=\"line-clamp-1\">From: {m.documentTitle}</div></div><div style={{color:T.textMuted}}>{Ic.chevR()}</div></div></button>)}
      <div style={{height:'calc(90px + env(safe-area-inset-bottom, 0px))'}}/>
"""
materials_new = """{materials.length===0?<EmptyState icon=\"✦\" title=\"No study materials yet\" sub=\"Open a document and create a summary, flashcards, practice questions, mind map, or podcast.\" action=\"Open My Documents\" onAction={()=>setTab('documents')}/>:materials.map((m,i)=>{const key=`${m.documentId}:${m.type}`;if(removedMaterialKeys.has(key))return null;return <div key={`${m.documentId}-${m.type}-${i}`} style={{display:'flex',alignItems:'stretch',gap:8,background:T.card,border:`1px solid ${T.border}`,borderRadius:16,padding:8,marginBottom:10}}><button onClick={()=>openMaterial(m)} style={{flex:1,minWidth:0,textAlign:'left',background:'none',border:'none',padding:7,cursor:'pointer',fontFamily:'Plus Jakarta Sans'}}><div style={{display:'flex',alignItems:'center',gap:12}}><div style={{width:44,height:44,borderRadius:12,background:`${N.navy}0D`,color:N.navy,display:'flex',alignItems:'center',justifyContent:'center',fontWeight:900,fontSize:18,flexShrink:0}}>{icon(m.type)}</div><div style={{flex:1,minWidth:0}}><div style={{fontWeight:800,fontSize:13,color:T.text}}>{label(m.type)}</div><div style={{fontSize:11,color:T.textMuted,marginTop:4}} className=\"line-clamp-1\">From: {m.documentTitle}</div></div><div style={{color:T.textMuted}}>{Ic.chevR()}</div></div></button><button aria-label={`Remove ${label(m.type)} from Study Hub`} title=\"Remove from Study Hub\" onClick={e=>{e.stopPropagation();const next=new Set(removedMaterialKeys);next.add(key);setRemovedMaterialKeys(next);try{localStorage.setItem('prepza-removed-study-materials',JSON.stringify([...next]))}catch{}}} style={{width:42,border:'none',background:'transparent',color:T.textMuted,cursor:'pointer',fontSize:20,borderRadius:10}}>×</button></div>})}
      <div style={{height:'calc(90px + env(safe-area-inset-bottom, 0px))'}}/>
"""
text = replace_once(text, materials_old, materials_new, "My Study material removal controls")

# Keep the Library save error visible without changing the existing layout.
text = replace_once(
    text,
    "        {activeTab === 'Browse' && (\n          browseLoading ? (",
    "        {saveActionError && <div style={{marginBottom:12,padding:'10px 12px',borderRadius:12,background:'rgba(201,168,76,0.10)',border:`1px solid ${N.gold}55`,color:T.text,fontSize:12,fontWeight:700}}>{saveActionError}</div>}\n        {activeTab === 'Browse' && (\n          browseLoading ? (",
    "Library save error banner",
)

APP.write_text(text, encoding="utf-8")
print("Library/My Study separation and Study Hub removal controls applied")
