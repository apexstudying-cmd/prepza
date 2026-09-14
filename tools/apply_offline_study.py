from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / 'frontend' / 'src' / 'crypto' / 'PdfStudyCanvas.tsx'
APP = ROOT / 'frontend' / 'src' / 'App.tsx'


def patch_reader():
    s = READER.read_text(encoding='utf-8')
    original = s

    s = s.replace(
        "type Props = { src: string; title: string; onPageChange?: (page: number) => void; onTextSelection?: (text: string) => void }",
        "type Props = { src: string; title: string; initialPage?: number; onPageChange?: (page: number) => void; onTextSelection?: (text: string) => void }",
        1,
    )
    s = s.replace(
        "export default function PdfStudyCanvas({ src, title, onPageChange, onTextSelection }: Props) {",
        "export default function PdfStudyCanvas({ src, title, initialPage = 1, onPageChange, onTextSelection }: Props) {",
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

    old = """const response = await window.fetch(src, { credentials: 'include' }); if (!response.ok) throw new Error(`The study document could not be loaded (${response.status}).`); const document = await openPdf(new Uint8Array(await response.arrayBuffer()));"""
    new = """let response: Response
        try {
          response = await window.fetch(src, { credentials: 'include', cache: 'no-store' })
          if (!response.ok) throw new Error(`The study document could not be loaded (${response.status}).`)
          if ('caches' in window && response.type !== 'opaque') {
            try { const cache = await window.caches.open('prepza-study-assets-v1'); await cache.put(src, response.clone()) } catch (_) {}
          }
        } catch (networkError) {
          if (!('caches' in window)) throw networkError
          const cached = await window.caches.match(src)
          if (!cached) throw networkError
          response = cached
        }
        const document = await openPdf(new Uint8Array(await response.arrayBuffer()));"""
    if old in s:
        s = s.replace(old, new, 1)
    elif "prepza-study-assets-v1" not in s:
        raise SystemExit('PDF fetch anchor not found')

    # The first render should resume from the persisted page, not always page 1.
    s = s.replace(
        "const result = await renderPdfPage(document, 1, 1, canvasRef.current!); if (!cancelled) { setText(result.text); onPageChange?.(1) }",
        "const resumePage = Math.min(Math.max(1, initialPage), document.numPages); setPage(resumePage); const result = await renderPdfPage(document, resumePage, 1, canvasRef.current!); if (!cancelled) { setText(result.text); onPageChange?.(resumePage) }",
        1,
    )
    s = s.replace(
        "}, [src, onPageChange])",
        "}, [src, initialPage, onPageChange])",
        1,
    )

    if s == original:
        raise SystemExit('offline PDF reader patch made no changes')
    READER.write_text(s, encoding='utf-8')


def patch_app():
    s = APP.read_text(encoding='utf-8')
    # Prefer an existing reader prop site if present; otherwise the reader may
    # already be wrapped by a generated/build transformation.
    patterns = [
        ("<PdfStudyCanvas src={document.file_url} title={document.title} onPageChange={handlePageChange}",
         "<PdfStudyCanvas src={document.file_url} title={document.title} initialPage={readingPage + 1} onPageChange={handlePageChange}"),
        ("<PdfStudyCanvas src={doc.file_url} title={doc.title} onPageChange={handlePageChange}",
         "<PdfStudyCanvas src={doc.file_url} title={doc.title} initialPage={readingPage + 1} onPageChange={handlePageChange}"),
    ]
    for old, new in patterns:
        if old in s and new not in s:
            s = s.replace(old, new, 1)
            break
    APP.write_text(s, encoding='utf-8')


def main():
    patch_reader()
    patch_app()
    print('Offline study asset caching and reader resume patch applied.')


if __name__ == '__main__':
    main()
