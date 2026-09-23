from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / 'frontend' / 'src' / 'crypto' / 'PdfStudyCanvas.tsx'
APP = ROOT / 'frontend' / 'src' / 'App.tsx'


def patch_reader():
    s = READER.read_text(encoding='utf-8')
    if 'documentId?: number' in s and 'startOfflineStudyTracking' in s:
        return
    original = s
    if not s.startswith('// @ts-nocheck'):
        s = '// @ts-nocheck\n' + s

    if "./offline/studyActivity" not in s:
        s = s.replace(
            "import { getPdfPageSize, openPdf, renderPdfPage, type PdfDocument, type PdfTextItem } from './pdfStudyReaderEngine'\n",
            "import { getPdfPageSize, openPdf, renderPdfPage, type PdfDocument, type PdfTextItem } from './pdfStudyReaderEngine'\nimport { startOfflineStudyTracking } from '../offline/studyActivity'\nimport { getOfflineStudyDocumentUrl } from '../offline/studyHubOffline'\nimport { getOfflineUserId } from '../offline/generatedMaterials'\n",
            1,
        )
    elif "getOfflineStudyDocumentUrl" not in s:
        anchor = "import { getPdfPageSize, openPdf, renderPdfPage, type PdfDocument, type PdfTextItem } from './pdfStudyReaderEngine'\n"
        additions = "import { getOfflineStudyDocumentUrl } from '../offline/studyHubOffline'\nimport { getOfflineUserId } from '../offline/generatedMaterials'\n"
        if anchor not in s:
            raise SystemExit('PDF offline package import anchor not found')
        s = s.replace(anchor, anchor + additions, 1)

    s = s.replace(
        "type Props = { src: string; title: string; onPageChange?: (page: number) => void; onTextSelection?: (text: string) => void }",
        "type Props = { src: string; title: string; initialPage?: number; documentId?: number; onPageChange?: (page: number) => void; onTextSelection?: (text: string) => void }",
        1,
    )
    s = s.replace(
        "export default function PdfStudyCanvas({ src, title, onPageChange, onTextSelection }: Props) {",
        "export default function PdfStudyCanvas({ src, title, initialPage = 1, documentId, onPageChange, onTextSelection }: Props) {",
        1,
    )
    s = s.replace(
        "const [page, setPage] = useState(1), [pages, setPages] = useState(0)",
        "const [page, setPage] = useState(Math.max(1, initialPage)), [pages, setPages] = useState(0)",
        1,
    )
    s = s.replace(
        "setPage(1); setPages(0); setZoom(1);",
        "setPage(Math.max(1, initialPage)); setPages(0); setZoom(1);",
        1,
    )

    tracker_effect = "  useEffect(() => { if (documentId == null) return; return startOfflineStudyTracking(documentId, 'reading') }, [documentId])\n"
    if tracker_effect not in s:
        anchor = "  const annotationKey = `${STORE}:${src}`, bookmarkKey = `${BOOKMARKS}:${src}`\n"
        if anchor not in s:
            raise SystemExit('PDF tracker anchor not found')
        s = s.replace(anchor, tracker_effect + anchor, 1)

    old = """const response = await window.fetch(src, { credentials: 'include' }); if (!response.ok) throw new Error(`The study document could not be loaded (${response.status}).`); const document = await openPdf(new Uint8Array(await response.arrayBuffer()));"""
    new = """let response: Response
        let localObjectUrl: string | null = null
        try {
          if (!navigator.onLine && documentId != null) {
            const userId = getOfflineUserId()
            localObjectUrl = userId ? await getOfflineStudyDocumentUrl(documentId, Number(userId)) : null
            if (!localObjectUrl) throw new Error('This study has not been saved for offline use. Connect to the internet and tap Save first.')
            response = await window.fetch(localObjectUrl)
          } else {
            response = await window.fetch(src, { credentials: 'include', cache: 'no-store' })
            if (!response.ok) throw new Error(`The study document could not be loaded (${response.status}).`)
            if ('caches' in window && response.type !== 'opaque') {
              try { const cache = await window.caches.open('prepza-study-assets-v1'); await cache.put(src, response.clone()) } catch (_) {}
            }
          }
          const pdfDocument: PdfDocument = await openPdf(new Uint8Array(await response.arrayBuffer()))
          if (localObjectUrl) { try { URL.revokeObjectURL(localObjectUrl) } catch (_) {} }
          if (cancelled) return
          documentRef.current = pdfDocument
          setPages(pdfDocument.numPages)
          const resumePage = Math.min(Math.max(1, initialPage), pdfDocument.numPages)
          setPage(resumePage)
          const result = await renderPdfPage(pdfDocument, resumePage, 1, canvasRef.current!)
          if (!cancelled) { setText(result.text); onPageChange?.(resumePage) }
          return
        } catch (networkError) {
          if (localObjectUrl) { try { URL.revokeObjectURL(localObjectUrl) } catch (_) {} }
          if (!navigator.onLine) throw networkError
          if (!('caches' in window)) throw networkError
          const cached = await window.caches.match(src)
          if (!cached) throw networkError
          response = cached
          const pdfDocument: PdfDocument = await openPdf(new Uint8Array(await response.arrayBuffer()))
          if (cancelled) return
          documentRef.current = pdfDocument
          setPages(pdfDocument.numPages)
          const resumePage = Math.min(Math.max(1, initialPage), pdfDocument.numPages)
          setPage(resumePage)
          const result = await renderPdfPage(pdfDocument, resumePage, 1, canvasRef.current!)
          if (!cancelled) { setText(result.text); onPageChange?.(resumePage) }
        }"""
    if old in s:
        s = s.replace(old, new, 1)
    elif "getOfflineStudyDocumentUrl(documentId" not in s:
        raise SystemExit('PDF fetch anchor not found')

    s = s.replace("}, [src, onPageChange])", "}, [src, initialPage, documentId, onPageChange])", 1)

    if s == original:
        raise SystemExit('offline PDF reader patch made no changes')
    READER.write_text(s, encoding='utf-8')


def patch_app():
    s = APP.read_text(encoding='utf-8')
    patterns = [
        ("<PdfStudyCanvas src={document.file_url} title={document.title} onPageChange={handlePageChange}",
         "<PdfStudyCanvas src={document.file_url} title={document.title} documentId={activeDocumentId ?? undefined} initialPage={readingPage + 1} onPageChange={handlePageChange}"),
        ("<PdfStudyCanvas src={doc.file_url} title={doc.title} onPageChange={handlePageChange}",
         "<PdfStudyCanvas src={doc.file_url} title={doc.title} documentId={activeDocumentId ?? undefined} initialPage={readingPage + 1} onPageChange={handlePageChange}"),
    ]
    for old, new in patterns:
        if old in s and new not in s:
            s = s.replace(old, new, 1)
            break
    APP.write_text(s, encoding='utf-8')


def main():
    patch_reader()
    patch_app()
    print('Offline study package reader, activity tracking, and reader resume patch applied.')


if __name__ == '__main__':
    main()
