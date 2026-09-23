import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { getPdfPageSize, openPdf, renderPdfPage, type PdfDocument, type PdfTextItem } from './pdfStudyReaderEngine'
type Props = { src: string; title: string; storageKey?: string; onPageChange?: (page: number) => void; onTextSelection?: (text: string) => void }
type Tool = 'select' | 'highlight' | 'underline' | 'strike' | 'pen' | 'eraser' | 'note' | 'rect' | 'arrow'
type Annotation = { id: string; page: number; tool: Exclude<Tool, 'select'>; x: number; y: number; w: number; h: number; text?: string; points?: Array<[number, number]> }
const MIN_ZOOM = 0.5, MAX_ZOOM = 3, ZOOM_STEP = 0.15
const STORE = 'prepza-study-annotations-v2'
const MAX_ANNOTATIONS = 500
const MAX_ANNOTATION_BYTES = 900 * 1024
const MAX_PEN_POINTS = 1200
const BOOKMARKS = 'prepza-study-bookmarks-v1'
function loadAnnotations(key: string): Annotation[] { try { const value = JSON.parse(localStorage.getItem(key) || '[]'); return Array.isArray(value) ? value : [] } catch { return [] } }
function saveAnnotations(key: string, value: Annotation[]): boolean {
  try {
    const bounded = value.length > MAX_ANNOTATIONS ? value.slice(-MAX_ANNOTATIONS) : value
    const encoded = JSON.stringify(bounded)
    if (new Blob([encoded]).size > MAX_ANNOTATION_BYTES) return false
    localStorage.setItem(key, encoded)
    return true
  } catch { return false }
}
function loadBookmarks(key: string): number[] { try { const value = JSON.parse(localStorage.getItem(key) || '[]'); return Array.isArray(value) ? value.filter(v => Number.isInteger(v) && v > 0) : [] } catch { return [] } }
function saveBookmarks(key: string, value: number[]) { try { localStorage.setItem(key, JSON.stringify(value)) } catch {} }
function textStyle(item: PdfTextItem, pageHeight: number) { const fontSize = Math.max(6, Math.hypot(item.transform[2], item.transform[3]) || item.height); const x = item.transform[4]; const y = pageHeight - item.transform[5] - fontSize; return { left: x, top: y, width: Math.max(item.width, 1), height: Math.max(item.height, fontSize), fontSize } }
export default function PdfStudyCanvas({ src, title, storageKey, onPageChange, onTextSelection }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null), stageRef = useRef<HTMLDivElement | null>(null), overlayRef = useRef<HTMLDivElement | null>(null), documentRef = useRef<PdfDocument | null>(null), tokenRef = useRef(0), undoRef = useRef<Annotation[][]>([])
  const [page, setPage] = useState(1), [pages, setPages] = useState(0), [zoom, setZoom] = useState(1), [loading, setLoading] = useState(true), [error, setError] = useState(''), [text, setText] = useState<PdfTextItem[]>([]), [tool, setTool] = useState<Tool>('select'), [annotations, setAnnotations] = useState<Annotation[]>([]), [search, setSearch] = useState(''), [searchMatches, setSearchMatches] = useState<number[]>([]), [note, setNote] = useState(''), [bookmarks, setBookmarks] = useState<number[]>([]), [selectedRange, setSelectedRange] = useState<DOMRect[]>([]), [selectedText, setSelectedText] = useState('')
  // Signed/blob URLs can change across refreshes and cold restarts. Use the
  // stable document identity supplied by the caller whenever available so
  // offline annotations and bookmarks survive a new object URL.
  const stableStudyKey = storageKey || src
  const annotationKey = `${STORE}:${stableStudyKey}`, bookmarkKey = `${BOOKMARKS}:${stableStudyKey}`
  useEffect(() => { setAnnotations(loadAnnotations(annotationKey)); undoRef.current = []; setBookmarks(loadBookmarks(bookmarkKey)) }, [annotationKey, bookmarkKey])
  const commitAnnotations = (next: Annotation[]) => {
    const bounded = next.length > MAX_ANNOTATIONS ? next.slice(-MAX_ANNOTATIONS) : next
    if (!saveAnnotations(annotationKey, bounded)) return false
    undoRef.current.push(annotations)
    if (undoRef.current.length > 30) undoRef.current.shift()
    setAnnotations(bounded)
    return true
  }
  const render = useCallback(async (nextPage: number, nextZoom: number) => { const document = documentRef.current, canvas = canvasRef.current; if (!document || !canvas) return; const token = ++tokenRef.current; setLoading(true); setError(''); try { const result = await renderPdfPage(document, nextPage, nextZoom, canvas); if (token !== tokenRef.current) return; setText(result.text); setSelectedRange([]); setSelectedText(''); onTextSelection?.(''); setPage(nextPage); onPageChange?.(nextPage) } catch (value) { if (token === tokenRef.current) setError(value instanceof Error ? value.message : 'Could not render this page.') } finally { if (token === tokenRef.current) setLoading(false) } }, [onPageChange, onTextSelection])
  useEffect(() => { let cancelled = false; documentRef.current = null; setPage(1); setPages(0); setZoom(1); setLoading(true); setError(''); ;(async () => { try { const response = await window.fetch(src, { credentials: 'include' }); if (!response.ok) throw new Error(`The study document could not be loaded (${response.status}).`); const document = await openPdf(new Uint8Array(await response.arrayBuffer())); if (cancelled) return; documentRef.current = document; setPages(document.numPages); const result = await renderPdfPage(document, 1, 1, canvasRef.current!); if (!cancelled) { setText(result.text); onPageChange?.(1) } } catch (value) { if (!cancelled) setError(value instanceof Error ? value.message : 'Could not open this PDF.') } finally { if (!cancelled) setLoading(false) } })(); return () => { cancelled = true; tokenRef.current += 1; documentRef.current = null } }, [src, onPageChange])
  useEffect(() => { const query = search.trim().toLowerCase(); setSearchMatches(query ? text.map((item, i) => item.str.toLowerCase().includes(query) ? i : -1).filter(i => i >= 0) : []) }, [search, text])
  useEffect(() => { const handler = () => { if (tool !== 'select') return; const selection = window.getSelection(); const value = selection?.toString().trim() || ''; if (!selection || !value || !overlayRef.current || !overlayRef.current.contains(selection.anchorNode)) return; const base = overlayRef.current.getBoundingClientRect(); const rects = Array.from(selection.getRangeAt(0).getClientRects()).map(rect => new DOMRect(rect.left - base.left, rect.top - base.top, rect.width, rect.height)).filter(rect => rect.width > 1 && rect.height > 1); if (!rects.length) return; setSelectedText(value.slice(0, 20000)); setSelectedRange(rects); onTextSelection?.(value.slice(0, 20000)) }; document.addEventListener('selectionchange', handler); return () => document.removeEventListener('selectionchange', handler) }, [tool, onTextSelection])
  const fit = async (mode: 'width' | 'page') => { const document = documentRef.current, stage = stageRef.current; if (!document || !stage) return; const size = await getPdfPageSize(document, page); const w = Math.max(240, stage.clientWidth - 32), h = Math.max(240, stage.clientHeight - 100); const next = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, mode === 'width' ? w / size.width : Math.min(w / size.width, h / size.height))); setZoom(next); await render(page, next) }
  const changePage = async (next: number) => { if (next >= 1 && next <= pages) await render(next, zoom) }
  const applyTextAnnotation = (kind: 'highlight' | 'underline' | 'strike') => { if (!selectedRange.length) return; const additions = selectedRange.map(rect => ({ id: crypto.randomUUID(), page, tool: kind, x: rect.x, y: rect.y, w: rect.width, h: rect.height } as Annotation)); commitAnnotations([...annotations, ...additions]); setSelectedRange([]); window.getSelection()?.removeAllRanges() }
  const pointer = (event: ReactPointerEvent) => {
    if (tool === 'select' || !overlayRef.current) return
    const rect = overlayRef.current.getBoundingClientRect()
    const start: [number, number] = [Math.max(0, event.clientX - rect.left), Math.max(0, event.clientY - rect.top)]
    let points: Array<[number, number]> = [start]
    const move = (e: PointerEvent) => points.push([Math.max(0, e.clientX - rect.left), Math.max(0, e.clientY - rect.top)])
    const up = (e: PointerEvent) => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      const ex = Math.max(0, e.clientX - rect.left)
      const ey = Math.max(0, e.clientY - rect.top)
      const x = Math.min(start[0], ex)
      const y = Math.min(start[1], ey)
      const w = Math.max(3, Math.abs(ex - start[0]))
      const h = Math.max(3, Math.abs(ey - start[1]))

      if (tool === 'eraser') {
        const hit = [...annotations].reverse().find(a => a.page === page && start[0] >= a.x && start[0] <= a.x + a.w && start[1] >= a.y && start[1] <= a.y + a.h)
        if (hit) commitAnnotations(annotations.filter(a => a.id !== hit.id))
        return
      }

      if (tool === 'note') {
        const value = window.prompt('Study note', note || '')
        if (!value) return
        setNote(value)
        commitAnnotations([...annotations, { id: crypto.randomUUID(), page, tool, x: start[0], y: start[1], w: 180, h: 70, text: value }])
        return
      }

      // Drawing a rectangle is also a study-context action: collect the PDF
      // text items that overlap the drawn box and expose that text to Ada.
      // This is what makes "circle/box this passage -> ask Ada" work without
      // requiring the student to precisely drag-select the PDF text layer.
      if (tool === 'rect') {
        const overlay = overlayRef.current
        if (!overlay) return
        const pageHeight = overlay.clientHeight
        const picked = text
          .map(item => ({ item, box: textStyle(item, pageHeight) }))
          .filter(({ box }) => box.left < x + w && box.left + box.width > x && box.top < y + h && box.top + box.height > y)
          .map(({ item }) => item.str.trim())
          .filter(Boolean)
        const context = picked.join(' ').slice(0, 20000)
        setSelectedText(context)
        onTextSelection?.(context)
      }

      commitAnnotations([...annotations, { id: crypto.randomUUID(), page, tool, x, y, w, h, points: tool === 'pen' ? points.slice(0, MAX_PEN_POINTS) : undefined }])
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }
  const undo = () => { const previous = undoRef.current.pop(); if (previous && saveAnnotations(annotationKey, previous)) setAnnotations(previous) }
  const toggleBookmark = () => { const next = bookmarks.includes(page) ? bookmarks.filter(value => value !== page) : [...bookmarks, page].sort((a, b) => a - b); setBookmarks(next); saveBookmarks(bookmarkKey, next) }
  const ann = annotations.filter(a => a.page === page)
  return <section style={{ height: '100%', minHeight: 0, display: 'grid', gridTemplateRows: 'auto 1fr', background: '#171b22' }} aria-label={`PDF study reader for ${title}`}>
    <header style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6, padding: 8, borderBottom: '1px solid rgba(255,255,255,.1)', background: '#0f141c', color: '#fff' }}>
      <button type="button" disabled={page <= 1 || loading} onClick={() => void changePage(page - 1)}>‹</button><input aria-label="PDF page" type="number" min={1} max={pages || 1} value={page} onChange={e => void changePage(Number(e.target.value) || 1)} style={{ width: 55 }} /><span style={{ fontSize: 12 }}>/ {pages || '—'}</span><button type="button" disabled={page >= pages || loading} onClick={() => void changePage(page + 1)}>›</button>
      <button type="button" onClick={() => void fit('width')}>Fit width</button><button type="button" onClick={() => void fit('page')}>Fit page</button><button type="button" disabled={loading} onClick={() => void render(page, Math.max(MIN_ZOOM, zoom - ZOOM_STEP))}>−</button><span>{Math.round(zoom * 100)}%</span><button type="button" disabled={loading} onClick={() => void render(page, Math.min(MAX_ZOOM, zoom + ZOOM_STEP))}>+</button>
      <button type="button" aria-pressed={bookmarks.includes(page)} onClick={toggleBookmark}>{bookmarks.includes(page) ? 'Bookmarked' : 'Bookmark'}</button>{bookmarks.length > 0 && <select aria-label="Bookmarked pages" value={bookmarks.includes(page) ? page : ''} onChange={e => { const value = Number(e.target.value); if (value) void changePage(value) }}><option value="">Bookmarks</option>{bookmarks.map(value => <option key={value} value={value}>Page {value}</option>)}</select>}
      <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search document…" aria-label="Search document" style={{ minWidth: 130, flex: 1 }} />{search && <span style={{ fontSize: 11, opacity: .7 }}>{searchMatches.length} matches</span>}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>{(['select','highlight','underline','strike','pen','eraser','note','rect','arrow'] as Tool[]).map(value => <button key={value} type="button" aria-pressed={tool === value} onClick={() => { if (value === 'highlight' || value === 'underline' || value === 'strike') applyTextAnnotation(value); else setTool(value) }}>{value === 'select' ? 'Select' : value === 'highlight' ? 'Highlight selection' : value === 'underline' ? 'Underline selection' : value === 'strike' ? 'Strike selection' : value === 'pen' ? 'Pen' : value === 'eraser' ? 'Erase' : value === 'note' ? 'Note' : value === 'rect' ? 'Shape' : 'Arrow'}</button>)}</div>
      <button type="button" onClick={undo} disabled={!undoRef.current.length}>Undo</button><button type="button" onClick={() => commitAnnotations(annotations.filter(a => a.page !== page))}>Clear page</button>
    </header>
    <div ref={stageRef} style={{ minHeight: 0, overflow: 'auto', display: 'flex', justifyContent: 'center', alignItems: 'flex-start', padding: 16, position: 'relative' }}>
      <div style={{ position: 'relative', width: canvasRef.current?.style.width || 'auto', height: canvasRef.current?.style.height || 'auto', flex: '0 0 auto' }}>
        <canvas ref={canvasRef} aria-label={`Page ${page} of ${pages || 'PDF'}`} style={{ display: error ? 'none' : 'block', background: '#fff', boxShadow: '0 10px 35px rgba(0,0,0,.35)' }} />
        <div ref={overlayRef} onPointerDown={pointer} style={{ position: 'absolute', inset: 0, pointerEvents: tool === 'select' ? 'auto' : 'auto', userSelect: tool === 'select' ? 'text' : 'none' }}>
          {tool === 'select' && text.map((item, i) => <span key={i} data-search-match={searchMatches.includes(i) || undefined} style={{ position: 'absolute', ...textStyle(item, canvasRef.current?.clientHeight || 0), color: 'transparent', background: searchMatches.includes(i) ? 'rgba(232,195,106,.35)' : 'transparent', cursor: 'text' }}>{item.str}</span>)}
          {selectedRange.map((rect, i) => <div key={`selection-${i}`} style={{ position: 'absolute', left: rect.x, top: rect.y, width: rect.width, height: rect.height, background: 'rgba(90,160,255,.22)', pointerEvents: 'none' }} />)}
          <svg width="100%" height="100%" style={{ position: 'absolute', inset: 0, overflow: 'visible', pointerEvents: 'none' }}>{ann.map(a => a.tool === 'pen' && a.points ? <polyline key={a.id} points={a.points.map(p => p.join(',')).join(' ')} fill="none" stroke="#d6b35a" strokeWidth="3" /> : a.tool === 'arrow' ? <line key={a.id} x1={a.x} y1={a.y} x2={a.x + a.w} y2={a.y + a.h} stroke="#b88a35" strokeWidth="3" markerEnd="url(#arrow)" /> : <rect key={a.id} x={a.x} y={a.y} width={a.w} height={a.h} fill={a.tool === 'highlight' ? 'rgba(255,220,70,.35)' : 'transparent'} stroke={a.tool === 'underline' ? '#b88a35' : a.tool === 'strike' ? '#b84a4a' : '#b88a35'} strokeWidth={a.tool === 'highlight' ? 0 : 2} strokeDasharray={a.tool === 'rect' ? '5 3' : undefined} />)}<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6 z" fill="#b88a35" /></marker></defs></svg>
          {ann.filter(a => a.tool === 'note').map(a => <div key={a.id} style={{ position: 'absolute', left: a.x, top: a.y, width: a.w, minHeight: a.h, padding: 8, background: 'rgba(255,235,160,.92)', color: '#171717', border: '1px solid #b88a35', borderRadius: 6, whiteSpace: 'pre-wrap', fontSize: 12, pointerEvents: 'none' }}>{a.text}</div>)}
        </div>
      </div>
      {loading && <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', background: 'rgba(23,27,34,.72)', color: '#fff' }}>Rendering page…</div>}{error && <div role="alert" style={{ maxWidth: 520, padding: 20, margin: 'auto', color: '#ffb4ab', textAlign: 'center' }}>{error}</div>}
      {selectedText && <div style={{ position: 'absolute', left: 18, bottom: 18, maxWidth: 420, padding: '8px 10px', borderRadius: 10, background: '#0f141c', color: '#fff', fontSize: 12, boxShadow: '0 8px 25px rgba(0,0,0,.3)' }}>Selection ready for Ada</div>}
    </div>
  </section>
}