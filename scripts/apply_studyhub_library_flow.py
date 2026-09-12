from pathlib import Path

p = Path("app.py")
s = p.read_text()

old = '''@app.route("/library/<int:publication_id>/save", methods=["POST"])
@require_csrf
def save_library_item(publication_id):
    """
    Bookmarks an approved Library publication for the logged-in student.
    Idempotent from the caller's perspective: saving an already-saved
    item just returns success rather than erroring, since the frontend
    doesn't need to track whether this is the first save.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    publication = db.session.get(LibraryPublication, publication_id)
    if not publication or publication.status != "approved":
        return jsonify({"error": "Library item not found"}), 404

    existing = SavedLibraryMaterial.query.filter_by(
        user_id=user_id, library_publication_id=publication_id
    ).first()
    if existing:
        return jsonify({"message": "Already saved"}), 200

    saved = SavedLibraryMaterial(user_id=user_id, library_publication_id=publication_id)
    db.session.add(saved)
    publication.save_count = (publication.save_count or 0) + 1
    db.session.commit()

    return jsonify({"message": "Saved", "save_count": publication.save_count}), 201
'''

new = '''def _ensure_studyhub_document_for_publication(user_id, publication):
    """Attach an approved Library publication to the student's StudyHub.

    The underlying DocumentContent remains shared/deduplicated. The student
    receives their own Document row, so title/delete/read-progress state is
    personal and cannot mutate the publisher's Document row.
    """
    source = db.session.get(Document, publication.document_id)
    if not source or source.is_removed or not source.document_content_id:
        return None

    content = db.session.get(DocumentContent, source.document_content_id)
    if not content or content.status != "ready":
        return None

    existing = Document.query.filter_by(
        user_id=user_id,
        document_content_id=content.id,
        is_removed=False,
    ).first()
    if existing:
        return existing

    removed = Document.query.filter_by(
        user_id=user_id,
        document_content_id=content.id,
        is_removed=True,
    ).first()
    if removed:
        removed.is_removed = False
        removed.title = publication.title
        removed.original_filename = source.original_filename
        removed.status = "ready"
        return removed

    return Document(
        user_id=user_id,
        document_content_id=content.id,
        title=publication.title,
        original_filename=source.original_filename,
        status="ready",
    )


@app.route("/library/<int:publication_id>/save", methods=["POST"])
@require_csrf
def save_library_item(publication_id):
    """Save an approved Library item and make it available in StudyHub.

    Saving is idempotent. The first save creates/reuses a personal Document
    row pointing at the same deduplicated DocumentContent; repeated saves do
    not create duplicate StudyHub rows or increment save_count again.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    publication = db.session.get(LibraryPublication, publication_id)
    if not publication or publication.status != "approved":
        return jsonify({"error": "Library item not found"}), 404

    source = db.session.get(Document, publication.document_id)
    if not source or source.is_removed or not source.document_content_id:
        return jsonify({"error": "Library document is not ready"}), 409
    if _document_content_has_flagged_material(source.document_content_id):
        return jsonify({"error": "Library item is currently unavailable"}), 404

    studyhub_document = _ensure_studyhub_document_for_publication(user_id, publication)
    if not studyhub_document:
        return jsonify({"error": "Library document is not ready"}), 409

    existing = SavedLibraryMaterial.query.filter_by(
        user_id=user_id, library_publication_id=publication_id
    ).first()
    if existing:
        db.session.commit()
        return jsonify({
            "message": "Already saved",
            "document_id": studyhub_document.id,
            "in_studyhub": True,
            "save_count": publication.save_count,
        }), 200

    db.session.add(studyhub_document)
    db.session.flush()
    saved = SavedLibraryMaterial(user_id=user_id, library_publication_id=publication_id)
    db.session.add(saved)
    publication.save_count = (publication.save_count or 0) + 1
    try:
        db.session.commit()
    except IntegrityError:
        # A concurrent request may have won the SavedLibraryMaterial unique
        # constraint after both requests observed no existing save. Roll back
        # the losing transaction, then return the already-created StudyHub
        # document instead of surfacing a 500 or creating a second save count.
        db.session.rollback()
        saved_existing = SavedLibraryMaterial.query.filter_by(
            user_id=user_id, library_publication_id=publication_id
        ).first()
        if not saved_existing:
            raise
        winner_document = Document.query.filter_by(
            user_id=user_id,
            document_content_id=source.document_content_id,
            is_removed=False,
        ).order_by(Document.id.asc()).first()
        if not winner_document:
            return jsonify({"error": "Library save could not be completed"}), 409
        publication = db.session.get(LibraryPublication, publication_id)
        return jsonify({
            "message": "Already saved",
            "document_id": winner_document.id,
            "in_studyhub": True,
            "save_count": publication.save_count if publication else None,
        }), 200

    return jsonify({
        "message": "Saved",
        "document_id": studyhub_document.id,
        "in_studyhub": True,
        "save_count": publication.save_count,
    }), 201

'''

if old not in s:
    if new not in s:
        raise SystemExit("library save route anchor not found")
else:
    s = s.replace(old, new, 1)

p.write_text(s)
print("StudyHub/Library save patch applied")
