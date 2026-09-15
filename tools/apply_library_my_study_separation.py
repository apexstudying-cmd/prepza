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

# My Study owns the student's saved Library publications. Reuse the existing
# /library/saved endpoint rather than creating a second persistence mechanism.
text = replace_once(
    text,
    "const [materials, setMaterials] = useState<{ documentId: number; documentTitle: string; type: string }[]>([])\n  const [loading, setLoading] = useState(true)",
    "const [materials, setMaterials] = useState<{ documentId: number; documentTitle: string; type: string }[]>([])\n  const [savedLibrary, setSavedLibrary] = useState<SavedLibraryItem[]>([])\n  const [loading, setLoading] = useState(true)",
    "My Study saved Library state",
)

study_effect_anchor = "  useEffect(() => {\n    let cancelled = false\n    api<{ documents: HomeDocument[] }>('/documents').then(async res => {"
text = replace_once(
    text,
    study_effect_anchor,
    "  useEffect(() => {\n    let cancelled = false\n    api<{ saved: SavedLibraryItem[] }>('/library/saved').then(res => {\n      if (!cancelled) setSavedLibrary(res.saved)\n    }).catch(() => {\n      // Saved Library content is supplementary; My Study documents remain usable.\n    })\n    return () => { cancelled = true }\n  }, [])\n\n" + study_effect_anchor,
    "My Study saved Library loader",
)

# Replace only the Documents tab branch. The existing document cards and click
# behavior are retained; saved Library publications are appended as a distinct
# subsection and open through the same activeDocumentId/document-study flow.
doc_branch = re.compile(r"tab==='documents' \? <>[\s\S]*?</> : <>")
replacement = """tab==='documents' ? <>
        <div style={{fontSize:12,color:T.textMuted,marginBottom:12}}>Your documents and anything you've saved from the Prepza Library.</div>
        {documents.length===0 && savedLibrary.length===0 ? <EmptyState icon=\"▣\" title=\"No study items yet\" sub=\"Save study material from the Prepza Library or upload your own notes, slides, or past papers.\" action=\"Open Prepza Library\" onAction={()=>setScreen('library')}/> : <>
          {documents.length>0 && <>
            <div style={{fontSize:11,fontWeight:800,color:T.textMuted,marginBottom:8,textTransform:'uppercase',letterSpacing:0.5}}>My Documents</div>
            {documents.map(d=><button key={d.id} onClick={()=>openDocument(d.id)} style={{width:'100%',textAlign:'left',background:T.card,border:`1px solid ${T.border}`,borderRadius:16,padding:15,marginBottom:10,cursor:'pointer',fontFamily:'Plus Jakarta Sans'}}><div style={{display:'flex',alignItems:'center',gap:12}}><div style={{width:44,height:44,borderRadius:12,background:`${N.gold}18`,color:N.gold,display:'flex',alignItems:'center',justifyContent:'center',fontWeight:900}}>▣</div><div style={{flex:1,minWidth:0}}><div style={{fontWeight:800,fontSize:13,color:T.text}} className=\"line-clamp-1\">{d.title}</div><div style={{fontSize:11,color:T.textMuted,marginTop:4}}>{d.page_count?`${d.page_count} pages`:'Document'}{d.created_at?` · ${new Date(d.created_at).toLocaleDateString()}`:''}</div></div><div style={{color:T.textMuted}}>{Ic.chevR()}</div></div></button>)}
          </>}
          {savedLibrary.length>0 && <>
            <div style={{fontSize:11,fontWeight:800,color:T.textMuted,margin:'16px 0 8px',textTransform:'uppercase',letterSpacing:0.5}}>Saved from Prepza Library</div>
            {savedLibrary.map(item=><button key={`library-${item.id}`} onClick={()=>openDocument(item.document_id)} style={{width:'100%',textAlign:'left',background:T.card,border:`1px solid ${T.border}`,borderRadius:16,padding:15,marginBottom:10,cursor:'pointer',fontFamily:'Plus Jakarta Sans'}}><div style={{display:'flex',alignItems:'center',gap:12}}><div style={{width:44,height:44,borderRadius:12,background:`${N.gold}18`,color:N.gold,display:'flex',alignItems:'center',justifyContent:'center',fontWeight:900}}>{Ic.bookmark()}</div><div style={{flex:1,minWidth:0}}><div style={{fontWeight:800,fontSize:13,color:T.text}} className=\"line-clamp-1\">{item.title}</div><div style={{fontSize:11,color:T.textMuted,marginTop:4}}>{item.material_type.replace(/_/g,' ')}{item.author?` · ${item.author}`:''}</div></div><div style={{color:T.textMuted}}>{Ic.chevR()}</div></div></button>)}
          </>}
        </>}
      </> : <>"""
text, count = doc_branch.subn(replacement, text, count=1)
if count != 1:
    raise RuntimeError("My Study Documents tab branch anchor missing or ambiguous")

APP.write_text(text, encoding="utf-8")
print("Library/My Study separation applied")
