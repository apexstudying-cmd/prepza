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

# Fallback if the "ocr_batch_page_threshold" SystemSetting row is
# missing (e.g. SQL migration not yet run). Kept in sync with the
# seeded default in add_ocr_batch_support.sql.
DEFAULT_OCR_BATCH_PAGE_THRESHOLD = 3

# Shared between the synchronous (_transcribe_page_image) and batch
# (_transcribe_pages_via_batch) OCR paths, so both prompt the model
# identically regardless of which path a given document takes.
_OCR_SYSTEM_PROMPT = (
    "Transcribe all readable text from this scanned study document page "
    "exactly as written, preserving structure (headings, bullet points, "
    "numbered steps, equations in plain text). Output only the transcribed "
    "text - no commentary, no markdown fences, no notes about the image."
)


def _get_ocr_batch_threshold():
    """
    Minimum number of OCR-needed pages a document must have before its
    transcription is routed through the Batch API instead of the fast
    synchronous per-page path. Configurable via the SystemSetting row
    "ocr_batch_page_threshold" (see add_ocr_batch_support.sql) - no
    redeploy needed to change it.
    """
    from app import SystemSetting

    setting = SystemSetting.query.filter_by(key="ocr_batch_page_threshold").first()
    if not setting:
        return DEFAULT_OCR_BATCH_PAGE_THRESHOLD
    try:
        return max(1, int(setting.value))
    except (TypeError, ValueError):
        return DEFAULT_OCR_BATCH_PAGE_THRESHOLD


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

        text, page_count = _extract_pdf_text(file_bytes, job)

        content.extracted_text = text
        content.page_count = page_count
        content.status = "ready"
        _complete_job(job, success=True)

    except Exception as e:
        content.status = "failed"
        content.error_message = str(e)[:500]
        _complete_job(job, success=False, error_message=str(e))
        db.session.commit()
        _sync_document_statuses(document_content_id, "failed")
        raise

    db.session.commit()
    _sync_document_statuses(document_content_id, "ready")


def _fetch_file_bytes(storage_path):
    from app import fetch_private_file_bytes
    return fetch_private_file_bytes(storage_path, bucket="documents")


def _extract_pdf_text(file_bytes, job):
    """
    Extracts text page-by-page with PyMuPDF. Pages with near-empty
    native text (scanned/image-only) are transcribed via a Claude
    vision call rather than adding a Tesseract/OCR system dependency -
    reuses the same provider abstraction as everything else and gets
    logged like any other AI call.

    If a document has at least _get_ocr_batch_threshold() pages needing
    OCR, all of them are submitted together through the Batch API (50%
    cheaper) instead of one-at-a-time synchronous calls. Below that
    threshold, the coordination overhead isn't worth it and pages go
    through the original fast synchronous path. Either way, this never
    blocks a user-facing request - it only ever runs inside the
    background thread spawned by start_processing().
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")

    try:
        native_pages = {}
        ocr_page_nums = []
        for page_num in range(len(doc)):
            native_text = doc[page_num].get_text().strip()
            if len(native_text) >= MIN_CHARS_PER_PAGE_BEFORE_OCR:
                native_pages[page_num] = native_text
            else:
                ocr_page_nums.append(page_num)

        ocr_results = {}
        if ocr_page_nums:
            if len(ocr_page_nums) >= _get_ocr_batch_threshold():
                ocr_results = _transcribe_pages_via_batch(doc, ocr_page_nums, job)
            else:
                for page_num in ocr_page_nums:
                    ocr_results[page_num] = _transcribe_page_image(_render_page_png(doc[page_num]))

        pages_text = [
            native_pages.get(page_num, ocr_results.get(page_num, ""))
            for page_num in range(len(doc))
        ]
        page_count = len(pages_text)
    finally:
        doc.close()

    return "\n\n".join(pages_text), page_count


def _render_page_png(page):
    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
    return pix.tobytes("png")


def _transcribe_page_image(image_bytes):
    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    response = ai_service.route_and_generate(ai_service.AIRequest(
        task="OCR_TRANSCRIBE",
        system_prompt=_OCR_SYSTEM_PROMPT,
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


def _transcribe_pages_via_batch(doc, page_nums, job):
    """
    Submits all given pages as one Anthropic Message Batch. Any page
    whose batch item comes back errored/expired falls back to a normal
    synchronous call for just that page, so one bad page never fails
    extraction for the whole document. If batch submission itself
    fails (e.g. transient API error), every page falls back to the
    synchronous path instead.
    """
    from app import db

    items = []
    for page_num in page_nums:
        image_bytes = _render_page_png(doc[page_num])
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        ai_request = ai_service.AIRequest(
            task="OCR_TRANSCRIBE",
            system_prompt=_OCR_SYSTEM_PROMPT,
            user_message="Transcribe this page.",
            image_b64=image_b64,
            image_media_type="image/png",
        )
        items.append((f"page-{page_num}", ai_request))

    def _record_batch_id(batch_id):
        job.batch_id = batch_id
        db.session.commit()

    try:
        _, batch_results = ai_service.route_and_generate_batch(
            "OCR_TRANSCRIBE", items, on_batch_created=_record_batch_id,
        )
    except Exception as e:
        print(f"WARNING: OCR batch failed for job {job.id}, falling back to "
              f"synchronous calls for all {len(page_nums)} pages: {e}")
        return {
            page_num: _transcribe_page_image(_render_page_png(doc[page_num]))
            for page_num in page_nums
        }

    results = {}
    for custom_id, item in batch_results.items():
        page_num = int(custom_id.split("-")[1])
        if isinstance(item, Exception):
            print(f"WARNING: OCR batch item {custom_id} failed ({item}), "
                  f"retrying synchronously")
            results[page_num] = _transcribe_page_image(_render_page_png(doc[page_num]))
        else:
            ai_service.log_usage(
                user_id=None,
                request_type="extraction_batch",
                model=item.model_used,
                provider=item.provider,
                usage=item.usage,
            )
            results[page_num] = item.text

    return results


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


def _sync_document_statuses(document_content_id, status):
    """
    Mirrors the final DocumentContent status onto every Document row
    that points at it. DocumentContent can be shared across several
    students' personal Document rows (dedup), but only this function's
    caller knows when processing has actually finished - without this,
    Document.status freezes at "processing" forever, silently blocking
    anything that gates on it (e.g. publish_document requiring
    status == "ready" before a document can be submitted to the
    library).
    """
    from app import db, Document

    Document.query.filter_by(document_content_id=document_content_id).update(
        {"status": status}, synchronize_session=False
    )
    db.session.commit()