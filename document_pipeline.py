"""
document_pipeline.py — Chunk 3: document text extraction.

Turns an uploaded DocumentContent (PDF bytes in Supabase's private
"documents" bucket) into extracted_text, so the rest of the AI pipeline
(Tutor, Summaries, Quizzes, Flashcards, Podcasts, Mind maps) has real
material to work from instead of nothing.

Runs as a lightweight in-process background thread - no Redis/Celery
required. Every run is tracked in the ai_job table (feature, status,
timestamps, failure), so upgrading to a real queue (Celery/RQ, or a
Render Cron Job sweeping for stuck jobs) later means swapping how a job
gets picked up, not the job bookkeeping itself.

Same deferred-import pattern as ai_service.py: `from app import ...`
happens inside function bodies, never at module level, to avoid a
circular import with app.py (which imports this module).
"""

import base64
import threading
from datetime import datetime

import fitz  # PyMuPDF

import ai_service

# Below this many characters of native text, a PDF page is treated as
# scanned/image-only and sent through vision transcription instead.
MIN_CHARS_PER_PAGE_BEFORE_OCR = 20


def start_processing(document_content_id, flask_app):
    """
    Fire-and-forget: spawns a background thread that processes one
    DocumentContent. `flask_app` is passed explicitly (not imported)
    because Flask's request/session context does not carry into a new
    thread - the thread pushes its own app context to get a working
    db.session.
    """
    thread = threading.Thread(
        target=_process_in_background,
        args=(document_content_id, flask_app),
        daemon=True,
    )
    thread.start()


def _process_in_background(document_content_id, flask_app):
    with flask_app.app_context():
        try:
            process_document(document_content_id)
        except Exception as e:  # noqa: BLE001 - last-resort safety net, thread has no caller to raise to
            print(f"ERROR: document processing crashed for content {document_content_id}: {e}")


def process_document(document_content_id):
    """
    Synchronous extraction pipeline for one DocumentContent row. Safe
    to call directly (e.g. from an admin retry endpoint) without going
    through start_processing's background thread.
    """
    from app import db, DocumentContent

    content = db.session.get(DocumentContent, document_content_id)
    if not content:
        raise ValueError(f"DocumentContent {document_content_id} not found")

    job = _create_job(document_content_id, feature="text_extraction")

    try:
        file_bytes = _fetch_file_bytes(content.storage_path)
        if not file_bytes:
            raise RuntimeError("Could not download file from storage")

        if content.file_type != "pdf":
            # Non-PDF uploads (images, docx, etc.) are a documented gap
            # for this pass - extraction only covers PDF. Marking this
            # clearly beats silently producing empty text.
            raise RuntimeError(f"Text extraction not yet implemented for file_type '{content.file_type}'")

        text, page_count = _extract_pdf_text(file_bytes)

        content.extracted_text = text
        content.page_count = page_count
        content.status = "ready"
        _complete_job(job, success=True)

    except Exception as e:
        content.status = "failed"
        content.error_message = str(e)[:500]
        _complete_job(job, success=False, error_message=str(e))
        db.session.commit()
        raise

    db.session.commit()


def _fetch_file_bytes(storage_path):
    from app import fetch_private_file_bytes
    return fetch_private_file_bytes(storage_path, bucket="documents")


def _extract_pdf_text(file_bytes):
    """
    Extracts text page-by-page with PyMuPDF. Pages with near-empty
    native text (scanned/image-only) are transcribed via a Claude
    vision call rather than adding a Tesseract/OCR system dependency -
    reuses the same provider abstraction as everything else and gets
    logged like any other AI call. Done per-page (not one full-document
    vision call) to keep individual requests small and cheap.
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages_text = []

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            native_text = page.get_text().strip()

            if len(native_text) >= MIN_CHARS_PER_PAGE_BEFORE_OCR:
                pages_text.append(native_text)
                continue

            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
            image_bytes = pix.tobytes("png")
            pages_text.append(_transcribe_page_image(image_bytes))
    finally:
        doc.close()

    return "\n\n".join(pages_text), len(pages_text)


def _transcribe_page_image(image_bytes):
    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    response = ai_service.route_and_generate(ai_service.AIRequest(
        task="OCR_TRANSCRIBE",
        system_prompt=(
            "Transcribe all readable text from this scanned study document page "
            "exactly as written, preserving structure (headings, bullet points, "
            "numbered steps, equations in plain text). Output only the transcribed "
            "text - no commentary, no markdown fences, no notes about the image."
        ),
        user_message="Transcribe this page.",
        image_b64=image_b64,
        image_media_type="image/png",
    ))

    ai_service.log_usage(
        user_id=None,
        request_type="extraction",
        model=response.model_used,
        provider=response.provider,
        usage=response.usage,
    )

    return response.text


def _create_job(document_content_id, feature):
    from app import db, AiJob

    job = AiJob(
        document_content_id=document_content_id,
        feature=feature,
        status="processing",
        started_at=datetime.utcnow(),
    )
    db.session.add(job)
    db.session.commit()
    return job


def _complete_job(job, success, error_message=None):
    from app import db

    job.status = "completed" if success else "failed"
    job.completed_at = datetime.utcnow()
    if error_message:
        job.error_message = error_message[:500]
    db.session.commit()
