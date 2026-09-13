export type PdfRenderPage = {
  pageNumber: number
  width: number
  height: number
}

type PdfPage = {
  getViewport: (options: { scale: number }) => { width: number; height: number }
  render: (options: { canvasContext: CanvasRenderingContext2D; viewport: { width: number; height: number } }) => { promise: Promise<void> }
}

export type PdfDocument = {
  numPages: number
  getPage: (pageNumber: number) => Promise<PdfPage>
}

type PdfModule = {
  getDocument: (options: { data: Uint8Array }) => { promise: Promise<PdfDocument> }
  GlobalWorkerOptions?: { workerSrc: string }
}

const PDFJS_VERSION = '6.3.289'
const PDFJS_BASE = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${PDFJS_VERSION}/build`
let modulePromise: Promise<PdfModule> | null = null

async function loadPdfJs(): Promise<PdfModule> {
  if (!modulePromise) {
    modulePromise = import(/* @vite-ignore */ `${PDFJS_BASE}/pdf.mjs`).then((module) => {
      const pdfjs = module as PdfModule
      if (pdfjs.GlobalWorkerOptions) pdfjs.GlobalWorkerOptions.workerSrc = `${PDFJS_BASE}/pdf.worker.mjs`
      return pdfjs
    })
  }
  return modulePromise
}

export async function openPdf(bytes: Uint8Array): Promise<PdfDocument> {
  if (!bytes.byteLength) throw new Error('The study document is empty.')
  const pdfjs = await loadPdfJs()
  return pdfjs.getDocument({ data: bytes }).promise
}

export async function getPdfPageSize(document: PdfDocument, pageNumber: number) {
  if (!Number.isInteger(pageNumber) || pageNumber < 1 || pageNumber > document.numPages) throw new Error('Invalid PDF page.')
  const page = await document.getPage(pageNumber)
  const viewport = page.getViewport({ scale: 1 })
  return { width: viewport.width, height: viewport.height }
}

export async function renderPdfPage(document: PdfDocument, pageNumber: number, scale: number, canvas: HTMLCanvasElement): Promise<PdfRenderPage> {
  if (!Number.isInteger(pageNumber) || pageNumber < 1 || pageNumber > document.numPages) throw new Error('Invalid PDF page.')
  if (!Number.isFinite(scale) || scale <= 0 || scale > 4) throw new Error('Invalid PDF zoom.')
  const page = await document.getPage(pageNumber)
  const viewport = page.getViewport({ scale })
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width = Math.max(1, Math.floor(viewport.width * dpr))
  canvas.height = Math.max(1, Math.floor(viewport.height * dpr))
  canvas.style.width = `${viewport.width}px`
  canvas.style.height = `${viewport.height}px`
  const context = canvas.getContext('2d')
  if (!context) throw new Error('This device cannot render the study document.')
  context.setTransform(dpr, 0, 0, dpr, 0, 0)
  await page.render({ canvasContext: context, viewport }).promise
  return { pageNumber, width: viewport.width, height: viewport.height }
}
