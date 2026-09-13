import { useCallback, useEffect, useRef, useState } from 'react'
import { getPdfPageSize, openPdf, renderPdfPage, type PdfDocument } from './pdfStudyReaderEngine'

type Props = { src: string; title: string; onPageChange?: (page: number) => void }

const MIN_ZOOM = 0.5
const MAX_ZOOM = 3
const ZOOM_STEP = 0.15

export default function PdfStudyCanvas({ src, title, onPageChange }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const stageRef = useRef<HTMLDivElement | null>(null)
  const documentRef = useRef<PdfDocument | null>(null)
  const renderTokenRef = useRef(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(0)
  const [zoom, setZoom] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const render = useCallback(async (nextPage: number, nextZoom: number) => {
    const document = documentRef.current
    const canvas = canvasRef.current
    if (!document || !canvas) return
    const token = ++renderTokenRef.current
    setLoading(true)
    setError('')
    try {
      await renderPdfPage(document, nextPage, nextZoom, canvas)
      if (token !== renderTokenRef.current) return
      setPage(nextPage)
      onPageChange?.(nextPage)
    } catch (value) {
      if (token === renderTokenRef.current) setError(value instanceof Error ? value.message : 'Could not render this page.')
    } finally {
      if (token === renderTokenRef.current) setLoading(false)
    }
  }, [onPageChange])

  useEffect(() => {
    let cancelled = false
    documentRef.current = null
    setPage(1)
    setPages(0)
    setZoom(1)
    setLoading(true)
    setError('')
    ;(async () => {
      try {
        const response = await window.fetch(src, { credentials: 'include' })
        if (!response.ok) throw new Error(`The study document could not be loaded (${response.status}).`)
        const bytes = new Uint8Array(await response.arrayBuffer())
        const document = await openPdf(bytes)
        if (cancelled) return
        documentRef.current = document
        setPages(document.numPages)
        await renderPdfPage(document, 1, 1, canvasRef.current!)
        if (!cancelled) onPageChange?.(1)
      } catch (value) {
        if (!cancelled) setError(value instanceof Error ? value.message : 'Could not open this PDF.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
      renderTokenRef.current += 1
      documentRef.current = null
    }
  }, [src, onPageChange])

  const fitWidth = async () => {
    const document = documentRef.current
    const stage = stageRef.current
    if (!document || !stage) return
    const size = await getPdfPageSize(document, page)
    const available = Math.max(240, stage.clientWidth - 32)
    const nextZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, available / size.width))
    setZoom(nextZoom)
    await render(page, nextZoom)
  }

  const fitPage = async () => {
    const document = documentRef.current
    const stage = stageRef.current
    if (!document || !stage) return
    const size = await getPdfPageSize(document, page)
    const availableWidth = Math.max(240, stage.clientWidth - 32)
    const availableHeight = Math.max(240, stage.clientHeight - 32)
    const nextZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.min(availableWidth / size.width, availableHeight / size.height)))
    setZoom(nextZoom)
    await render(page, nextZoom)
  }

  const changeZoom = async (delta: number) => {
    const nextZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Number((zoom + delta).toFixed(2))))
    setZoom(nextZoom)
    await render(page, nextZoom)
  }

  const changePage = async (nextPage: number) => {
    if (nextPage < 1 || nextPage > pages) return
    await render(nextPage, zoom)
  }

  return <section style={{ height: '100%', minHeight: 0, display: 'grid', gridTemplateRows: 'auto 1fr', background: '#171b22' }} aria-label={`PDF reader for ${title}`}>
    <header style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'center', gap: 7, padding: '8px 10px', borderBottom: '1px solid rgba(255,255,255,.1)', background: '#0f141c' }}>
      <button type="button" disabled={page <= 1 || loading} onClick={() => void changePage(page - 1)}>Previous</button>
      <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
        <span style={{ fontSize: 12, opacity: .65 }}>Page</span>
        <input aria-label="PDF page" type="number" min={1} max={pages || 1} value={page} onChange={event => void changePage(Math.max(1, Number(event.target.value) || 1))} style={{ width: 64 }} />
        <span style={{ fontSize: 12, opacity: .65 }}>/ {pages || '—'}</span>
      </label>
      <button type="button" disabled={page >= pages || loading} onClick={() => void changePage(page + 1)}>Next</button>
      <button type="button" disabled={loading} onClick={() => void changeZoom(-ZOOM_STEP)} aria-label="Zoom out">−</button>
      <span style={{ minWidth: 52, textAlign: 'center', fontSize: 12 }}>{Math.round(zoom * 100)}%</span>
      <button type="button" disabled={loading} onClick={() => void changeZoom(ZOOM_STEP)} aria-label="Zoom in">+</button>
      <button type="button" disabled={loading} onClick={() => void fitWidth()}>Fit width</button>
      <button type="button" disabled={loading} onClick={() => void fitPage()}>Fit page</button>
    </header>
    <div ref={stageRef} style={{ minHeight: 0, overflow: 'auto', display: 'flex', justifyContent: 'center', alignItems: 'flex-start', padding: 16, position: 'relative' }}>
      <canvas ref={canvasRef} aria-label={`Page ${page} of ${pages || 'PDF'}`} style={{ display: error ? 'none' : 'block', background: '#fff', boxShadow: '0 10px 35px rgba(0,0,0,.35)', userSelect: 'text' }} />
      {loading && <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', background: 'rgba(23,27,34,.72)' }}>Rendering page…</div>}
      {error && <div role="alert" style={{ maxWidth: 520, padding: 20, margin: 'auto', color: '#ffb4ab', textAlign: 'center' }}>{error}</div>}
    </div>
  </section>
}
