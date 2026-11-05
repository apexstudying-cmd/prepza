from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "App.tsx"
LIBRARY_MODULE = ROOT / "frontend" / "src" / "screens" / "library" / "LibraryScreen.tsx"
STUDY_MODULE = ROOT / "frontend" / "src" / "screens" / "study" / "StudyMaterialsScreen.tsx"
text = APP.read_text(encoding="utf-8")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if old not in source:
        raise RuntimeError(f"Library/My Study patch anchor missing: {label}")
    if source.count(old) != 1:
        raise RuntimeError(f"Library/My Study patch anchor is not unique: {label}")
    return source.replace(old, new, 1)


def transform_library_screen(source: str) -> str:
    # Idempotence matters because the checked-in build chain may be invoked
    # repeatedly by local development, CI, and deployment builds.
    original_tab_state = "const [activeTab, setActiveTab] = useState<'Browse' | 'Saved' | 'Published'>('Browse')"
    if original_tab_state not in source:
        if "saveActionError" in source and "useState<'Browse' | 'Published'>" in source:
            return source
        raise RuntimeError("Library/My Study: LibraryScreen ownership or active-tab anchor is missing")

    source = replace_once(
        source,
        original_tab_state,
        "const [activeTab, setActiveTab] = useState<'Browse' | 'Published'>('Browse')",
        "Library active tab type",
    )
    source = replace_once(
        source,
        "{(['Browse', 'Saved', 'Published'] as const).map(t => (",
        "{(['Browse', 'Published'] as const).map(t => (",
        "Library tab list",
    )

    saved_block = re.compile(r"\n        \{activeTab === 'Saved' && \([\s\S]*?\n        \)\}\n        \{activeTab === 'Published' && \(")
    source, count = saved_block.subn("\n        {activeTab === 'Published' && (", source, count=1)
    if count != 1:
        raise RuntimeError("Library Saved tab content block anchor missing or ambiguous")

    source = replace_once(
        source,
        "const [savedIds, setSavedIds] = useState<Set<number>>(new Set())",
        "const [savedIds, setSavedIds] = useState<Set<number>>(new Set())\n  const [saveActionError, setSaveActionError] = useState('')",
        "Library save action error state",
    )
    source = replace_once(
        source,
        "    const isSaved = savedIds.has(pub.id)",
        "    const isSaved = savedIds.has(pub.id)\n    setSaveActionError('')",
        "Library save error reset",
    )
    source = replace_once(
        source,
        "    } catch {\n      setSavedIds(prev => { const next = new Set(prev); isSaved ? next.add(pub.id) : next.delete(pub.id); return next })",
        "    } catch (error) {\n      setSavedIds(prev => { const next = new Set(prev); isSaved ? next.add(pub.id) : next.delete(pub.id); return next })\n      setSaveActionError(error instanceof ApiError ? error.message : 'Could not update this Library item.')",
        "Library save error message",
    )
    source = replace_once(
        source,
        "        {activeTab === 'Browse' && (\n          browseLoading ? (",
        "        {saveActionError && <div style={{marginBottom:12,padding:'10px 12px',borderRadius:12,background:'rgba(201,168,76,0.10)',border:`1px solid ${N.gold}55`,color:T.text,fontSize:12,fontWeight:700}}>{saveActionError}</div>}\n        {activeTab === 'Browse' && (\n          browseLoading ? (",
        "Library save error banner",
    )
    return source


# Keep the app module as the compatibility integration point. Once LibraryScreen
# is extracted, its transform-owned source is the feature module, not App.tsx.
library_is_extracted = LIBRARY_MODULE.exists() and "function LibraryScreen(" in LIBRARY_MODULE.read_text(encoding="utf-8")
library_source = LIBRARY_MODULE.read_text(encoding="utf-8") if library_is_extracted else text

if (
    "const [activeTab, setActiveTab] = useState<'Browse' | 'Saved' | 'Published'>('Browse')" not in library_source
    and "saveActionError" in library_source
    and "useState<'Browse' | 'Published'>" in library_source
):
    print("Library/My Study separation: LibraryScreen transform already applied; skipping safely.")
    raise SystemExit(0)

# My Study's saved-Library integration remains a separate screen concern.
if "import StudyMaterialsScreen from './screens/study/StudyMaterialsScreen'" not in text:
    text = replace_once(
        text,
        "const [materials, setMaterials] = useState<{ documentId: number; documentTitle: string; type: string }[]>([])\n  const [loading, setLoading] = useState(true)",
        "const [materials, setMaterials] = useState<{ documentId: number; documentTitle: string; type: string }[]>([])\n  const [savedLibrary, setSavedLibrary] = useState<SavedLibraryItem[]>([])\n  const [csrfToken, setCsrfToken] = useState('')\n  const [loading, setLoading] = useState(true)",
        "My Study saved Library state",
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
        "  useEffect(() => {\n    let cancelled = false\n    api<{ saved: SavedLibraryItem[] }>('/library/saved').then(res => {\n      if (!cancelled) {\n        const normalized = (res.saved || []).map(item => ({ ...item, document_id: item.document_id ?? (item as any).documentId }))\n        setSavedLibrary(normalized)\n      }\n    }).catch(() => {})\n    return () => { cancelled = true }\n  }, [])\n\n" + study_effect_anchor,
        "My Study saved Library loader",
    )
    doc_branch = re.compile(r"tab==='documents' \? <>[\s\S]*?</> : <>")
    replacement = """tab==='documents' ? <>
            <div style={{fontSize:12,color:T.textMuted,marginBottom:12}}>Your documents and anything you've saved from the Prepza Library.</div>
            {documents.length===0 && savedLibrary.length===0 ? <EmptyState icon="▣" title="No study items yet" sub="Save study material from the Prepza Library or upload your own notes, slides, or past papers." action="Open Prepza Library" onAction={()=>setScreen('library')}/> : <>
              {documents.length>0 && <>
                <div style={{fontSize:11,fontWeight:800,color:T.textMuted,marginBottom:8,textTransform:'uppercase',letterSpacing:0.5}}>My Documents</div>
                {documents.map(d=><div key={d.id} style={{display:'flex',alignItems:'stretch',gap:8,background:T.card,border:`1px solid ${T.border}`,borderRadius:16,padding:8,marginBottom:10}}><button onClick={()=>openDocument(d.id)} style={{flex:1,minWidth:0,textAlign:'left',background:'none',border:'none',padding:7,cursor:'pointer',fontFamily:'Plus Jakarta Sans'}}><div style={{display:'flex',alignItems:'center',gap:12}}><div style={{width:44,height:44,borderRadius:12,background:`${N.gold}18`,color:N.gold,display:'flex',alignItems:'center',justifyContent:'center',fontWeight:900,flexShrink:0}}>▣</div><div style={{flex:1,minWidth:0}}><div style={{fontWeight:800,fontSize:13,color:T.text}} className="line-clamp-1">{d.title}</div><div style={{fontSize:11,color:T.textMuted,marginTop:4}}>{d.page_count?`${d.page_count} pages`:'Document'}{d.created_at?` · ${new Date(d.created_at).toLocaleDateString()}`:''}</div></div><div style={{color:T.textMuted}}>{Ic.chevR()}</div></div></button><button aria-label={`Remove ${d.title} from Study Hub`} title="Remove from Study Hub" onClick={async e=>{e.stopPropagation();if(!csrfToken)return;try{await api(`/documents/${d.id}`,{method:'DELETE',headers:{'X-CSRF-Token':csrfToken}});const me=await api<{id:number}>('/me');try{const mod=await import('./offline/studyHubOffline');await mod.removeStudyHubOfflineCopy(d.id,Number(me.id))}catch{}setDocuments(items=>items.filter(item=>item.id!==d.id));setSavedLibrary(items=>items.filter(item=>Number(item.document_id)!==d.id))}catch(error){window.alert(error instanceof ApiError?error.message:'Could not remove this document from Study Hub.')}}} style={{width:42,border:'none',background:'transparent',color:T.textMuted,cursor:'pointer',fontSize:20,borderRadius:10}}>×</button></div>)}
              </>}
              {savedLibrary.length>0 && <>
                <div style={{fontSize:11,fontWeight:800,color:T.textMuted,margin:'16px 0 8px',textTransform:'uppercase',letterSpacing:0.5}}>Saved from Prepza Library</div>
                {savedLibrary.map(item=>{ const targetDocumentId=Number(item.document_id ?? (item as any).documentId); return <div key={`library-${item.id}`} style={{display:'flex',alignItems:'stretch',gap:8,background:T.card,border:`1px solid ${T.border}`,borderRadius:16,padding:8,marginBottom:10}}><button onClick={()=>{if(Number.isFinite(targetDocumentId)&&targetDocumentId>0)openDocument(targetDocumentId)}} style={{flex:1,minWidth:0,textAlign:'left',background:'none',border:'none',padding:7,cursor:Number.isFinite(targetDocumentId)&&targetDocumentId>0?'pointer':'default',fontFamily:'Plus Jakarta Sans',opacity:Number.isFinite(targetDocumentId)&&targetDocumentId>0?1:0.72}}><div style={{display:'flex',alignItems:'center',gap:12}}><div style={{width:44,height:44,borderRadius:12,background:`${N.gold}18`,color:N.gold,display:'flex',alignItems:'center',justifyContent:'center',fontWeight:900,flexShrink:0}}>{Ic.bookmark()}</div><div style={{flex:1,minWidth:0}}><div style={{fontWeight:800,fontSize:13,color:T.text}} className="line-clamp-1">{item.title}</div><div style={{fontSize:11,color:T.textMuted,marginTop:4}}>{item.material_type.replace(/_/g,' ')}{item.author?` · ${item.author}`:''}</div></div><div style={{color:T.textMuted}}>{Ic.chevR()}</div></div></button><button aria-label={`Remove ${item.title} from Study Hub`} title="Remove from Study Hub" onClick={async e=>{e.stopPropagation();if(!csrfToken)return;try{await api(`/library/${item.id}/save`,{method:'DELETE',headers:{'X-CSRF-Token':csrfToken}});setSavedLibrary(items=>items.filter(saved=>saved.id!==item.id));if(Number.isFinite(targetDocumentId)&&targetDocumentId>0)setDocuments(items=>items.filter(doc=>doc.id!==targetDocumentId))}catch(error){window.alert(error instanceof ApiError?error.message:'Could not remove this Library item from Study Hub.')}}} style={{width:42,border:'none',background:'transparent',color:T.textMuted,cursor:'pointer',fontSize:20,borderRadius:10}}>×</button></div> })}
              </>}
            </>}
          </> : <>"""
    text, count = doc_branch.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError("My Study Documents tab branch anchor missing or ambiguous")
else:
    module_source = STUDY_MODULE.read_text(encoding="utf-8") if STUDY_MODULE.exists() else ""
    required_module_contracts = (
        "savedLibrary",
        "Saved from Prepza Library",
        "api<{ saved: SavedStudyLibraryItem[] }>('/library/saved')",
    )
    missing = [item for item in required_module_contracts if item not in module_source]
    if missing:
        raise RuntimeError("Extracted My Study module is missing Library integration: " + ", ".join(missing))

if library_is_extracted:
    library_source = transform_library_screen(library_source)
    LIBRARY_MODULE.write_text(library_source, encoding="utf-8")
else:
    text = transform_library_screen(text)

APP.write_text(text, encoding="utf-8")
print("Library/My Study separation and Study Hub removal controls applied")
