from pathlib import Path

APP = Path('app.py')
FRONT = Path('frontend/src/App.tsx')

def rep(text, old, new, label):
    if old in text: return text.replace(old, new, 1)
    if new in text: return text
    raise SystemExit(f'{label} anchor not found')

app = APP.read_text()
model_anchor = '\n\nclass GeneratedMaterial(db.Model):\n'
model = '''\n\nclass DocumentReadingProgress(db.Model):\n    """Durable per-student page position for the native document reader."""\n    id = db.Column(db.Integer, primary_key=True)\n    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)\n    document_id = db.Column(db.Integer, db.ForeignKey("document.id"), nullable=False)\n    page_num = db.Column(db.Integer, nullable=False, default=0)\n    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)\n    __table_args__ = (db.UniqueConstraint("user_id", "document_id", name="uq_document_reading_progress_user_document"),)\n'''
if 'class DocumentReadingProgress(db.Model):' not in app:
    app = rep(app, model_anchor, model + model_anchor, 'reading model')

route_anchor = '\n\n@app.route("/documents/<int:document_id>", methods=["PATCH"])\n'
routes = '''\n\ndef _can_study_document(user_id, document):\n    if not document or document.is_removed: return False\n    if document.user_id == user_id: return True\n    pub = LibraryPublication.query.filter_by(document_id=document.id, status="approved").first()\n    return bool(pub)\n\n\ndef _get_studyable_document(user_id, document_id):\n    document = db.session.get(Document, document_id)\n    if not _can_study_document(user_id, document): return None\n    content = db.session.get(DocumentContent, document.document_content_id) if document.document_content_id else None\n    if not content or content.status != "ready": return None\n    return document, content\n\n\n@app.route("/documents/<int:document_id>/reading", methods=["GET"])\ndef get_document_reading(document_id):\n    user_id = session.get("user_id")\n    if not user_id: return jsonify({"error": "Not logged in"}), 401\n    pair = _get_studyable_document(user_id, document_id)\n    if not pair: return jsonify({"error": "Document not found"}), 404\n    document, content = pair\n    progress = DocumentReadingProgress.query.filter_by(user_id=user_id, document_id=document.id).first()\n    page_num = progress.page_num if progress else 0\n    max_page = max(0, (content.page_count or 1) - 1)\n    return jsonify({"document_id": document.id, "page_num": min(max(0, page_num), max_page), "page_count": content.page_count})\n\n\n@app.route("/documents/<int:document_id>/reading", methods=["POST"])\n@require_csrf\ndef save_document_reading(document_id):\n    user_id = session.get("user_id")\n    if not user_id: return jsonify({"error": "Not logged in"}), 401\n    pair = _get_studyable_document(user_id, document_id)\n    if not pair: return jsonify({"error": "Document not found"}), 404\n    document, content = pair\n    data = request.get_json(silent=True) or {}\n    page_num = data.get("page_num")\n    if not isinstance(page_num, int) or isinstance(page_num, bool) or page_num < 0: return jsonify({"error": "page_num must be a non-negative integer"}), 400\n    max_page = max(0, (content.page_count or 1) - 1)\n    if page_num > max_page: return jsonify({"error": "page_num is outside the document"}), 400\n    progress = DocumentReadingProgress.query.filter_by(user_id=user_id, document_id=document.id).first()\n    if not progress: db.session.add(DocumentReadingProgress(user_id=user_id, document_id=document.id, page_num=page_num))\n    else: progress.page_num = page_num\n    db.session.commit()\n    return jsonify({"ok": True, "page_num": page_num})\n\n\n@app.route("/documents/<int:document_id>/reading/page/<int:page_num>")\ndef render_document_reading_page(document_id, page_num):\n    user_id = session.get("user_id")\n    if not user_id: return jsonify({"error": "Not logged in"}), 401\n    pair = _get_studyable_document(user_id, document_id)\n    if not pair: return jsonify({"error": "Document not found"}), 404\n    document, content = pair\n    if content.file_type != "pdf": return jsonify({"error": "Native reading currently supports PDF documents only"}), 415\n    if page_num < 0 or content.page_count is None or page_num >= content.page_count: return jsonify({"error": "Page not found"}), 404\n    file_bytes = fetch_private_file_bytes(content.storage_path, bucket="documents")\n    if not file_bytes: return jsonify({"error": "Document file could not be loaded"}), 502\n    viewer = db.session.get(User, user_id)\n    watermark = (viewer.email if viewer and viewer.email else "Prepza")\n    try:\n        image_bytes, _ = render_watermarked_page(file_bytes, page_num, watermark, zoom=1.6)\n    except Exception:\n        return jsonify({"error": "Document page could not be rendered"}), 500\n    response = Response(image_bytes, mimetype="image/png")\n    response.headers["Cache-Control"] = "private, no-store, max-age=0"\n    response.headers["Content-Disposition"] = "inline"\n    return response\n'''
if 'def render_document_reading_page(' not in app:
    app = rep(app, route_anchor, routes + route_anchor, 'reading routes')

heartbeat_old = '''    feature = data.get("feature", "reading")\n    if feature not in STUDY_TIME_FEATURES:\n        return jsonify({"error": f"feature must be one of {sorted(STUDY_TIME_FEATURES)}"}), 400\n\n    seconds_today = record_study_time_heartbeat(user_id, feature=feature)\n    record_study_activity(user_id)\n'''
heartbeat_new = '''    feature = data.get("feature", "reading")\n    if feature not in STUDY_TIME_FEATURES:\n        return jsonify({"error": f"feature must be one of {sorted(STUDY_TIME_FEATURES)}"}), 400\n\n    document_content_id = None\n    document_id = data.get("document_id")\n    if document_id is not None:\n        if not isinstance(document_id, int) or isinstance(document_id, bool): return jsonify({"error": "document_id must be an integer"}), 400\n        pair = _get_studyable_document(user_id, document_id)\n        if not pair: return jsonify({"error": "Document not found"}), 404\n        document_content_id = pair[1].id\n\n    seconds_today = record_study_time_heartbeat(user_id, feature=feature)\n    record_study_activity(user_id, document_content_id=document_content_id)\n'''
app = rep(app, heartbeat_old, heartbeat_new, 'heartbeat binding')
APP.write_text(app)

front = FRONT.read_text()
marker = '// ─── AI TUTOR ─────────────────────────────────────────────────────────────────\n'
component = r'''// ─── NATIVE DOCUMENT READER ──────────────────────────────────────────────────
function DocumentReaderScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {
  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [page, setPage] = useState(0)
  const [savedPage, setSavedPage] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [csrfToken, setCsrfToken] = useState('')
  useEffect(() => {
    if (activeDocumentId == null) { setLoading(false); setError('No document selected.'); return }
    let cancelled = false
    Promise.all([api<DocumentDetail>(`/documents/${activeDocumentId}`), api<{page_num:number}>(`/documents/${activeDocumentId}/reading`), api<{csrf_token:string}>('/me')])
      .then(([detail, progress, me]) => { if (cancelled) return; setDoc(detail); setPage(progress.page_num || 0); setSavedPage(progress.page_num || 0); setCsrfToken(me.csrf_token) })
      .catch(e => { if (!cancelled) setError(e instanceof ApiError ? e.message : 'Could not open this document.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [activeDocumentId])
  useEffect(() => {
    if (activeDocumentId == null || !csrfToken) return
    const ping = () => { if (document.visibilityState === 'visible') api('/study-time/heartbeat', { method:'POST', headers:{'X-CSRF-Token':csrfToken}, body:JSON.stringify({feature:'reading', document_id:activeDocumentId}) }).catch(()=>{}) }
    ping(); const interval = setInterval(ping, 20000); return () => clearInterval(interval)
  }, [activeDocumentId, csrfToken])
  useEffect(() => {
    if (activeDocumentId == null || !csrfToken || page === savedPage) return
    const timer = setTimeout(() => api(`/documents/${activeDocumentId}/reading`, {method:'POST', headers:{'X-CSRF-Token':csrfToken}, body:JSON.stringify({page_num:page})}).then(()=>setSavedPage(page)).catch(()=>{}), 250)
    return () => clearTimeout(timer)
  }, [activeDocumentId, csrfToken, page, savedPage])
  if (loading) return <GenerationLoading label="Opening your document…" />
  if (error) return <GenerationError error={error} />
  if (!doc || activeDocumentId == null) return <GenerationError error="Document unavailable." />
  if (doc.file_type !== 'pdf') return <GenerationError error="Native reading currently supports PDF documents only." />
  const count = Math.max(1, doc.page_count || 1), current = Math.min(Math.max(page,0), count-1), progress = ((current+1)/count)*100
  const pageUrl = `/documents/${activeDocumentId}/reading/page/${current}`
  const atEnd = current >= count - 1
  const nextBackground = atEnd ? 'rgba(255,255,255,0.06)' : `linear-gradient(135deg,${N.gold},${N.goldL})`
  const nextColor = atEnd ? 'rgba(255,255,255,0.25)' : N.navy
  return <div style={{flex:1,minHeight:0,display:'flex',flexDirection:'column',background:'#111827'}}>
    <div style={{background:N.navy,padding:'10px 14px 12px',flexShrink:0}}><div style={{display:'flex',alignItems:'center',gap:10}}>
      <button onClick={()=>setScreen('document-study')} style={{width:34,height:34,background:'rgba(255,255,255,0.1)',border:'none',borderRadius:10,cursor:'pointer',display:'flex',alignItems:'center',justifyContent:'center'}}><div style={{color:'#fff'}}>{Ic.back()}</div></button>
      <div style={{flex:1,minWidth:0}}><div style={{color:'#fff',fontWeight:800,fontSize:14,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{doc.title}</div><div style={{color:'rgba(255,255,255,0.5)',fontSize:10}}>Page {current+1} of {count}</div></div>
    </div><div style={{marginTop:10,height:3,background:'rgba(255,255,255,0.12)',borderRadius:99,overflow:'hidden'}}><div style={{width:`${progress}%`,height:'100%',background:N.gold}}/></div></div>
    <div style={{flex:1,minHeight:0,overflow:'auto',padding:'14px 10px',display:'flex',justifyContent:'center'}}><img key={pageUrl} src={pageUrl} alt={`Page ${current+1} of ${doc.title}`} style={{display:'block',width:'min(100%,900px)',height:'auto',background:'#fff',boxShadow:'0 4px 24px rgba(0,0,0,0.35)'}} /></div>
    <div style={{background:N.navy,padding:'10px 14px calc(10px + env(safe-area-inset-bottom))',display:'flex',alignItems:'center',gap:10,flexShrink:0}}>
      <button disabled={current===0} onClick={()=>setPage(p=>Math.max(0,p-1))} style={{flex:1,border:'none',borderRadius:12,padding:'11px 0',background:current===0?'rgba(255,255,255,0.06)':'rgba(255,255,255,0.1)',color:current===0?'rgba(255,255,255,0.25)':'#fff',fontWeight:800,fontFamily:'Plus Jakarta Sans'}}>Previous</button>
      <div style={{color:'rgba(255,255,255,0.55)',fontSize:11,fontWeight:700,minWidth:62,textAlign:'center'}}>{Math.round(progress)}%</div>
      <button disabled={atEnd} onClick={()=>setPage(p=>Math.min(count-1,p+1))} style={{flex:1,border:'none',borderRadius:12,padding:'11px 0',background:nextBackground,color:nextColor,fontWeight:800,fontFamily:'Plus Jakarta Sans'}}>Next</button>
    </div></div>
}

'''
if 'function DocumentReaderScreen(' not in front: front = rep(front, marker, component + marker, 'reader component')
front = rep(front, "      case 'document-reader': return <DocumentStudyScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />", "      case 'document-reader': return <DocumentReaderScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />", 'reader route')
FRONT.write_text(front)
print('document reader patch applied')
