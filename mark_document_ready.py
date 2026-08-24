"""
One-off helper: marks a Document (and its underlying DocumentContent) as
"ready" so it can be published to the Library for testing. Needed because
the AI extraction pipeline that normally does this isn't built yet.

Run from project root (~/Desktop/prepza), with your .env DATABASE_URL set:
    python mark_document_ready.py <document_id>

Example:
    python mark_document_ready.py 7
"""

import sys

from app import app, db, Document, DocumentContent


def main():
    if len(sys.argv) != 2:
        print("Usage: python mark_document_ready.py <document_id>")
        sys.exit(1)

    try:
        document_id = int(sys.argv[1])
    except ValueError:
        print("document_id must be an integer")
        sys.exit(1)

    with app.app_context():
        document = db.session.get(Document, document_id)
        if not document:
            print(f"No Document found with id={document_id}")
            sys.exit(1)

        print(f"Document {document.id} ({document.title!r}) - current status: {document.status}")

        content = None
        if document.document_content_id:
            content = db.session.get(DocumentContent, document.document_content_id)

        document.status = "ready"
        if content:
            content.status = "ready"
            if content.page_count is None:
                content.page_count = 1  # placeholder, not used by the routes tested

        db.session.commit()

        print(f"Document {document.id} marked ready.")
        if content:
            print(f"DocumentContent {content.id} marked ready.")
        else:
            print("Note: this Document has no document_content_id - /library/publish "
                  "doesn't require content.status, so this is fine for testing, but "
                  "it's an unusual state outside of tests.")


if __name__ == "__main__":
    main()
