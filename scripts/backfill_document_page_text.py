"""Backfill page citations for existing ready PDFs without paid OCR.

Default mode is a read-only inventory. --apply performs private object reads and
writes only documents with usable native text on every page. Scanned/mixed PDFs
are skipped rather than sent to an AI provider; OCR backfills need a separately
approved, budget-bounded run.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import inspect

from app import (
    app,
    db,
    DocumentContent,
    DocumentPageText,
    GeneratedMaterial,
    fetch_private_file_bytes,
)
from document_pipeline import EXTRACTOR_VERSION, extracted_text_changed, extract_native_pdf_pages
from study_retrieval_service import make_source_version


def backfill(*, apply: bool, limit: int | None = None) -> dict:
    if not inspect(db.engine).has_table("document_page_text"):
        raise RuntimeError(
            "document_page_text is missing; apply migrations/20261029_document_page_text.sql first"
        )

    counts = {"candidates": 0, "backfilled": 0, "already_indexed": 0, "scanned_or_empty": 0, "unavailable": 0}
    last_id = 0
    remaining = limit
    while True:
        batch_size = 25 if remaining is None else min(25, remaining)
        if batch_size <= 0:
            break
        batch = (
            DocumentContent.query
            .filter(
                DocumentContent.status == "ready",
                DocumentContent.file_type == "pdf",
                DocumentContent.id > last_id,
            )
            .order_by(DocumentContent.id.asc())
            .limit(batch_size)
            .all()
        )
        if not batch:
            break
        for content in batch:
            counts["candidates"] += 1
            last_id = content.id
        existing = DocumentPageText.query.filter_by(
            document_content_id=content.id
        ).count()
        if existing:
            counts["already_indexed"] += 1
            continue
        if not apply:
            continue

        try:
            file_bytes = fetch_private_file_bytes(content.storage_path, bucket="documents")
            if not file_bytes:
                counts["unavailable"] += 1
                continue
            pages = extract_native_pdf_pages(file_bytes)
            if not pages or (content.page_count and len(pages) != content.page_count):
                counts["scanned_or_empty"] += 1
                continue

            source_version = make_source_version(
                content.content_hash, pages, extractor_version=EXTRACTOR_VERSION
            )
            prior_text = content.extracted_text or ""
            source_changed = extracted_text_changed([], prior_text, pages)
            for page_number, page_text in enumerate(pages, start=1):
                db.session.add(DocumentPageText(
                    document_content_id=content.id,
                    page_number=page_number,
                    page_text=page_text,
                    content_hash=content.content_hash,
                    source_version=source_version,
                    extractor_version=EXTRACTOR_VERSION,
                ))
            if source_changed:
                GeneratedMaterial.query.filter_by(
                    document_content_id=content.id, status="ready"
                ).update({
                    "status": "failed",
                    "error_message": "Source page text was backfilled; regenerate this study material.",
                }, synchronize_session=False)
            db.session.commit()
            counts["backfilled"] += 1
            except Exception:
                db.session.rollback()
                counts["unavailable"] += 1
                print(f"Backfill failed for document_content_id={content.id}; see application logs.", file=sys.stderr)
        if remaining is not None:
            remaining -= len(batch)

    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write page rows; without this flag only count candidates")
    parser.add_argument("--limit", type=int, help="limit candidate rows for a staged rehearsal")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be a positive integer")

    with app.app_context():
        counts = backfill(apply=args.apply, limit=args.limit)
    print(("APPLIED" if args.apply else "DRY RUN") + f": {counts}")
    if not args.apply:
        print("No private objects were fetched and no database rows were changed.")


if __name__ == "__main__":
    main()
