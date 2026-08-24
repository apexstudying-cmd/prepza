"""
One-off test fixture: creates a fake DocumentContent + Document row,
already status="ready", for a given user - so the Chunk 4 sanity test can
publish something without going through the real Supabase upload flow.

The "file" is fake: a random content_hash and a storage_path that points
at nothing real in Supabase Storage. That's fine for testing
/library/publish and everything downstream, since none of those routes
touch the actual file bytes - they only need Document.status == "ready".

Run from project root (~/Desktop/prepza):
    python seed_test_document.py <user_email>

Example:
    python seed_test_document.py xgichuru3@gmail.com
"""

import sys
import secrets

from app import app, db, User, Document, DocumentContent


def main():
    if len(sys.argv) != 2:
        print("Usage: python seed_test_document.py <user_email>")
        sys.exit(1)

    email = sys.argv[1].strip().lower()

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if not user:
            print(f"No user found with email={email}")
            sys.exit(1)

        content_hash = secrets.token_hex(32)  # 64 hex chars, fake but valid-shaped
        content = DocumentContent(
            content_hash=content_hash,
            storage_path=f"{content_hash}.pdf",  # does not exist in Supabase - fine for this test
            file_type="pdf",
            file_size_bytes=123456,
            page_count=1,
            status="ready",
        )
        db.session.add(content)
        db.session.flush()

        document = Document(
            user_id=user.id,
            document_content_id=content.id,
            title="Chunk4 Test Fixture Document",
            original_filename="chunk4_test_fixture.pdf",
            status="ready",
        )
        db.session.add(document)
        db.session.commit()

        print(f"Created Document id={document.id} for user {email} (status=ready).")
        print(f"Use this as DOCUMENT_ID for test_chunk4_flow.py:\n")
        print(f"  export DOCUMENT_ID={document.id}")


if __name__ == "__main__":
    main()
