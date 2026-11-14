"""Library publication, saved-material and moderation routes.

The existing route handlers remain unchanged under an injected registration
boundary. Shared helpers defined later in app.py are resolved lazily.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import jsonify, request, session
from sqlalchemy.exc import IntegrityError


def register_library_routes(
    app: Any,
    db: Any,
    *,
    User: Any,
    Document: Any,
    DocumentContent: Any,
    GeneratedMaterial: Any,
    LibraryPublication: Any,
    SavedLibraryMaterial: Any,
    LibraryReport: Any,
    SystemSetting: Any,
    University: Any,
    Program: Any,
    XpEvent: Any,
    get_user_subscription_status: Any,
    _can_publish_document: Any,
    _display_name: Any,
    check_and_unlock_achievements: Any,
    log_admin_action: Any,
    require_csrf: Any,
    require_admin: Any,
) -> None:
    """Register the existing student Library and admin moderation routes."""
    @app.route("/library/publish", methods=["POST"])
    @require_csrf
    def publish_document():
        """
        Submits a student's own Document to the public Library for admin
        review. Only one active (pending or approved) publication is allowed
        per document - if a prior submission was rejected, this creates a
        fresh row rather than reviving the old one, keeping submission
        history intact.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Request body must be valid JSON"}), 400

        document_id = data.get("document_id")
        title = (data.get("title") or "").strip()
        description = data.get("description")
        material_type = (data.get("material_type") or "").strip()
        university_id = data.get("university_id")
        program_id = data.get("program_id")
        year = data.get("year")
        semester = data.get("semester")
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"error": "Account not found"}), 404
        if university_id is None: university_id = user.university_id
        if program_id is None: program_id = user.program_id
        if year is None: year = user.year
        if semester is None: semester = user.semester

        if not document_id:
            return jsonify({"error": "document_id is required"}), 400

        document = db.session.get(Document, document_id)
        if not _can_publish_document(user_id, document):
            return jsonify({"error": "Document not found"}), 404
        if document.status != "ready":
            return jsonify({"error": f"Document is not ready to publish (status: {document.status})"}), 400

        if not title or len(title) > LIBRARY_TITLE_MAX:
            return jsonify({"error": f"Title is required and must be {LIBRARY_TITLE_MAX} characters or fewer"}), 400

        if description is not None:
            if not isinstance(description, str):
                return jsonify({"error": "description must be a string"}), 400
            description = description.strip() or None
            if description and len(description) > LIBRARY_DESCRIPTION_MAX:
                return jsonify({"error": f"description must be {LIBRARY_DESCRIPTION_MAX} characters or fewer"}), 400

        if material_type not in LIBRARY_MATERIAL_TYPES:
            return jsonify({"error": "material_type must be one of: " + ", ".join(sorted(LIBRARY_MATERIAL_TYPES))}), 400

        if data.get("unit_id") is not None:
            return jsonify({"error": "unit_id is no longer supported for Library publications"}), 400
        if any(value is None for value in (university_id, program_id, year, semester)):
            return jsonify({"error": "university, course, year, and semester are required for Library publication"}), 400
        if not isinstance(university_id, int) or isinstance(university_id, bool):
            return jsonify({"error": "university_id must be an integer"}), 400
        university = University.query.filter_by(id=university_id, is_active=True).first()
        if not university:
            return jsonify({"error": "Selected university was not found"}), 400
        if not isinstance(program_id, int) or isinstance(program_id, bool):
            return jsonify({"error": "program_id must be an integer"}), 400
        program = Program.query.filter_by(id=program_id, university_id=university_id, is_active=True).first()
        if not program:
            return jsonify({"error": "Selected course does not belong to the selected university"}), 400
        if not isinstance(year, int) or isinstance(year, bool) or not 1 <= year <= 5:
            return jsonify({"error": "year must be an integer between 1 and 5"}), 400
        if not isinstance(semester, int) or isinstance(semester, bool) or semester not in (1, 2, 3):
            return jsonify({"error": "semester must be 1, 2, or 3"}), 400

        if _document_content_has_flagged_material(document.document_content_id):
            return jsonify({
                "error": "This document can't be published right now - one of its AI-generated "
                         "materials has been flagged for review"
            }), 400

        # Library publishing is content-addressed, not name/document-row addressed.
        # Multiple student Document rows may point at the same DocumentContent, but
        # the same underlying bytes must never become multiple active library copies.
        existing_active = (
            LibraryPublication.query
            .join(Document, LibraryPublication.document_id == Document.id)
            .filter(
                Document.document_content_id == document.document_content_id,
                LibraryPublication.status.in_(LIBRARY_ACTIVE_STATUSES),
            )
            .first()
        )
        if existing_active:
            # The content is already represented in the Library. Do not create
            # another publication row or duplicate storage. A duplicate publish
            # attempt is a successful no-op from the student's perspective.
            return jsonify({
                "published": False,
                "duplicate": True,
                "message": "Thank you for publishing. This document is already in the Library.",
            }), 200

        publication = LibraryPublication(
            document_id=document_id,
            user_id=user_id,
            university_id=university_id,
            program_id=program_id,
            year=year,
            semester=semester,
            title=title,
            description=description,
            material_type=material_type,
            status="approved",
            reviewed_by=None,
            reviewed_at=datetime.utcnow(),
        )
        db.session.add(publication)
        db.session.commit()

        return jsonify({
            "publication_id": publication.id,
            "status": publication.status,
            "published": True,
            "message": "Published to the Library. Other students can now save it to Study Hub.",
        }), 201


    @app.route("/library/my-submissions")
    def my_library_submissions():
        """
        Lists the logged-in student's own Library submissions, any status
        (pending/approved/rejected/removed) - powers the "review" tab on
        PublishLibraryScreen so a student can track where each one stands.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        publications = (
            LibraryPublication.query.filter_by(user_id=user_id)
            .order_by(LibraryPublication.created_at.desc())
            .all()
        )

        result = []
        for pub in publications:
            result.append({
                "id": pub.id,
                "document_id": pub.document_id,
                "title": pub.title,
                "description": pub.description,
                "material_type": pub.material_type,
                "status": pub.status,
                "rejection_reason": pub.rejection_reason,
                "view_count": pub.view_count,
                "save_count": pub.save_count,
                "created_at": pub.created_at.isoformat() if pub.created_at else None,
                "updated_at": pub.updated_at.isoformat() if pub.updated_at else None,
            })

        return jsonify({"submissions": result})


    @app.route("/library")
    def browse_library():
        """
        Browse/search approved Library publications. Login required (same
        pattern as other content routes) but not tied to the viewer's own
        year/semester - any student can browse any unit's published material,
        matching the "any student, any university" product direction.

        Query params (all optional):
          q            - substring match against title
          unit_id      - filter to one unit
          university_id - filter to units belonging to one university
          material_type - lecture_notes | past_paper | summary | other
          page         - 1-indexed, 20 per page
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        query = LibraryPublication.query.filter_by(status="approved")
        free_ids = _free_library_publication_ids(user_id)
        has_premium = _student_has_premium_library(user_id)
        flagged_document_ids = _flagged_document_ids()
        if flagged_document_ids:
            query = query.filter(~LibraryPublication.document_id.in_(flagged_document_ids))

        q = (request.args.get("q") or "").strip()
        if q:
            query = query.filter(LibraryPublication.title.ilike(f"%{q}%"))
        unit_id = None

        if request.args.get("unit_id") is not None:
            return jsonify({"error": "unit_id is no longer supported"}), 400

        university_id = request.args.get("university_id", type=int)
        if university_id:
            query = query.filter(LibraryPublication.university_id == university_id)

        program_id = request.args.get("program_id", type=int)
        if program_id:
            query = query.filter(LibraryPublication.program_id == program_id)
        year = request.args.get("year", type=int)
        if year:
            query = query.filter(LibraryPublication.year == year)
        semester = request.args.get("semester", type=int)
        if semester:
            query = query.filter(LibraryPublication.semester == semester)

        material_type = request.args.get("material_type")
        if material_type:
            if material_type not in LIBRARY_MATERIAL_TYPES:
                return jsonify({"error": "material_type must be one of: " + ", ".join(sorted(LIBRARY_MATERIAL_TYPES))}), 400
            query = query.filter(LibraryPublication.material_type == material_type)

        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        per_page = 20

        sort = request.args.get("sort")
        order_col = LibraryPublication.view_count.desc() if sort == "trending" else LibraryPublication.created_at.desc()

        publications = (
            query.order_by(order_col)
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        result = []
        for pub in publications:
            author = db.session.get(User, pub.user_id)
            result.append({
                "id": pub.id,
                "document_id": pub.document_id if (has_premium or pub.id in free_ids) else None,
                "title": pub.title,
                "description": pub.description if (has_premium or pub.id in free_ids) else None,
                "material_type": pub.material_type,
                "university_id": pub.university_id,
                "program_id": pub.program_id,
                "year": pub.year,
                "semester": pub.semester,
                "author": _display_name(author) if author else "Deleted user",
                "view_count": pub.view_count,
                "save_count": pub.save_count,
                "created_at": pub.created_at.isoformat() if pub.created_at else None,
                "locked": not (has_premium or pub.id in free_ids),
            })

        return jsonify({"page": page, "publications": result})


    def _ensure_studyhub_document_for_publication(user_id, publication):
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

        if not _student_has_premium_library(user_id):
            free_ids=_free_library_publication_ids(user_id)
            if publication_id not in free_ids:
                return jsonify({"error":"This Library item is outside your Free plan cohort allowance. Upgrade to Plus or Pro for premium Library access."}),403

        source = db.session.get(Document, publication.document_id)
        if not source or source.is_removed or not source.document_content_id:
            return jsonify({"error": "Library document is not ready"}), 409
        if _document_content_has_flagged_material(source.document_content_id):
            return jsonify({"error": "Library item is currently unavailable"}), 404

        existing_studyhub_document = Document.query.filter_by(
            user_id=user_id,
            document_content_id=source.document_content_id,
            is_removed=False,
        ).order_by(Document.id.asc()).first()
        already_in_studyhub = existing_studyhub_document is not None

        studyhub_document = _ensure_studyhub_document_for_publication(user_id, publication)
        if not studyhub_document:
            return jsonify({"error": "Library document is not ready"}), 409

        existing = SavedLibraryMaterial.query.filter_by(
            user_id=user_id, library_publication_id=publication_id
        ).first()
        if not existing:
            # Free students may save up to 3 Library documents. Plus/Pro get the
            # premium Library entitlement. Enforce this server-side; never trust
            # the frontend's plan display for an access decision.
            subscription = get_user_subscription_status(user_id)
            if not subscription["is_active"]:
                saved_count = SavedLibraryMaterial.query.filter_by(user_id=user_id).count()
                if saved_count >= 3:
                    return jsonify({
                        "error": "Free plan Library limit reached. Upgrade to Plus or Pro for premium Library access."
                    }), 403
        if existing:
            # A legacy SavedLibraryMaterial row may predate the StudyHub-document
            # guarantee. In that case _ensure_studyhub_document_for_publication
            # returns a new, transient Document that must be persisted here.
            if studyhub_document.id is None:
                db.session.add(studyhub_document)
                db.session.flush()
            db.session.commit()
            return jsonify({
                "message": "This document is already in your Study Hub. No download was needed.",
                "document_id": studyhub_document.id,
                "in_studyhub": True,
                "already_in_studyhub": True,
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
            "message": (
                "This document is already in your Study Hub. No download was needed."
                if already_in_studyhub
                else "Saved to your Study Hub."
            ),
            "document_id": studyhub_document.id,
            "in_studyhub": True,
            "already_in_studyhub": already_in_studyhub,
            "save_count": publication.save_count,
        }), 200 if already_in_studyhub else 201

    @app.route("/library/<int:publication_id>/save", methods=["DELETE"])
    @require_csrf
    def unsave_library_item(publication_id):
        """Removes the logged-in student's bookmark, if one exists."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        saved = SavedLibraryMaterial.query.filter_by(
            user_id=user_id, library_publication_id=publication_id
        ).first()
        if not saved:
            return jsonify({"message": "Not saved"}), 200

        publication = db.session.get(LibraryPublication, publication_id)
        db.session.delete(saved)
        if publication and publication.save_count > 0:
            publication.save_count -= 1
        db.session.commit()

        return jsonify({
            "message": "Removed",
            "save_count": publication.save_count if publication else None,
        })


    @app.route("/library/saved")
    def list_saved_library_items():
        """Lists the logged-in student's saved Library items (Saved tab)."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        saved_rows = (
            SavedLibraryMaterial.query.filter_by(user_id=user_id)
            .order_by(SavedLibraryMaterial.created_at.desc())
            .all()
        )
        flagged_document_ids = _flagged_document_ids()

        result = []
        for saved in saved_rows:
            pub = db.session.get(LibraryPublication, saved.library_publication_id)
            if not pub or pub.status != "approved":
                # Publication was later rejected/removed - skip rather than
                # error, so one bad row doesn't break the whole Saved tab.
                continue
            if pub.document_id in flagged_document_ids:
                # Underlying material was flagged after this was saved - hide
                # it the same way browse_library does, rather than error.
                continue
            author = db.session.get(User, pub.user_id)
            result.append({
                "id": pub.id,
                "title": pub.title,
                "description": pub.description,
                "material_type": pub.material_type,
                "university_id": pub.university_id,
                "program_id": pub.program_id,
                "year": pub.year,
                "semester": pub.semester,
                "author": _display_name(author) if author else "Deleted user",
                "view_count": pub.view_count,
                "save_count": pub.save_count,
                "saved_at": saved.created_at.isoformat() if saved.created_at else None,
            })

        return jsonify({"saved": result})


    LIBRARY_REPORT_REASONS = {
        "inaccurate_content", "plagiarised_material",
        "inappropriate_content", "copyright_violation",
        "wrong_academic_category_year", "other",
    }
    LIBRARY_REPORT_DETAILS_MAX = 500


    @app.route("/library/<int:publication_id>/report", methods=["POST"])
    @require_csrf
    def report_library_item(publication_id):
        """
        Files a moderation report against a published Library item. No
        duplicate-report guard - a student can report the same item more
        than once (e.g. for a different reason); admins dedupe/dismiss on
        the review side rather than this endpoint silently dropping reports.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        publication = db.session.get(LibraryPublication, publication_id)
        if not publication or publication.status != "approved":
            return jsonify({"error": "Library item not found"}), 404

        data = request.get_json(silent=True) or {}
        reason = (data.get("reason") or "").strip()
        if reason not in LIBRARY_REPORT_REASONS:
            return jsonify({"error": "Invalid report reason"}), 400

        details = data.get("details")
        if details is not None:
            details = details.strip()
            if len(details) > LIBRARY_REPORT_DETAILS_MAX:
                return jsonify({"error": f"details must be {LIBRARY_REPORT_DETAILS_MAX} characters or fewer"}), 400
            details = details or None

        report = LibraryReport(
            library_publication_id=publication_id,
            reporter_user_id=user_id,
            reason=reason,
            details=details,
            status="pending",
        )
        db.session.add(report)
        db.session.commit()

        return jsonify({"message": "Report submitted", "report_id": report.id}), 201


    LIBRARY_XP_ON_APPROVAL = 50


    @app.route("/admin/library/queue")
    @require_admin
    def admin_library_queue():
        """Lists pending Library publications for admin review, oldest first
        (first submitted, first reviewed)."""
        publications = (
            LibraryPublication.query.filter_by(status="pending")
            .order_by(LibraryPublication.created_at.asc())
            .all()
        )

        result = []
        for pub in publications:
            author = db.session.get(User, pub.user_id)
            document = db.session.get(Document, pub.document_id)
            result.append({
                "id": pub.id,
                "document_id": pub.document_id,
                "title": pub.title,
                "description": pub.description,
                "material_type": pub.material_type,
                "author_email": author.email if author else None,
                "original_filename": document.original_filename if document else None,
                "created_at": pub.created_at.isoformat() if pub.created_at else None,
            })

        return jsonify({"queue": result})


    @app.route("/admin/library/<int:publication_id>/approve", methods=["POST"])
    @require_csrf
    @require_admin
    def admin_approve_library_item(publication_id):
        """
        Approves a pending publication and awards the submitter XP. XP award
        is idempotent via the XpEvent unique constraint on
        (user_id, event_type, related_id) - if this route is called twice for
        the same publication (retry, double-click), the second XpEvent insert
        is caught and skipped rather than double-awarding.
        """
        acting_admin_id = session.get("user_id")

        publication = db.session.get(LibraryPublication, publication_id)
        if not publication:
            return jsonify({"error": "Publication not found"}), 404
        if publication.status != "pending":
            return jsonify({"error": f"Publication is not pending (status: {publication.status})"}), 400

        publication.status = "approved"
        publication.reviewed_by = acting_admin_id
        publication.reviewed_at = datetime.utcnow()
        publication.rejection_reason = None

        xp_awarded_now = False
        if not publication.xp_awarded:
            xp_event = XpEvent(
                user_id=publication.user_id,
                event_type="library_publication_approved",
                xp_amount=LIBRARY_XP_ON_APPROVAL,
                related_id=publication.id,
            )
            db.session.add(xp_event)
            try:
                db.session.flush()
                publication.xp_awarded = True
                xp_awarded_now = True
            except IntegrityError:
                db.session.rollback()
                # Another request already awarded XP for this publication -
                # re-apply the approval fields (rolled back with the session)
                # and just skip the XP award this time.
                publication = db.session.get(LibraryPublication, publication_id)
                publication.status = "approved"
                publication.reviewed_by = acting_admin_id
                publication.reviewed_at = datetime.utcnow()
                publication.rejection_reason = None

        newly_unlocked = check_and_unlock_achievements(publication.user_id)
        db.session.commit()

        return jsonify({
            "id": publication.id,
            "status": publication.status,
            "xp_awarded_now": xp_awarded_now,
            "newly_unlocked_achievements": newly_unlocked,
        })


    @app.route("/admin/library/<int:publication_id>/reject", methods=["POST"])
    @require_csrf
    @require_admin
    def admin_reject_library_item(publication_id):
        """Rejects a pending publication with a required reason."""
        acting_admin_id = session.get("user_id")

        publication = db.session.get(LibraryPublication, publication_id)
        if not publication:
            return jsonify({"error": "Publication not found"}), 404
        if publication.status != "pending":
            return jsonify({"error": f"Publication is not pending (status: {publication.status})"}), 400

        data = request.get_json(silent=True) or {}
        reason = (data.get("reason") or "").strip()
        if not reason or len(reason) > 500:
            return jsonify({"error": "reason is required and must be 500 characters or fewer"}), 400

        publication.status = "rejected"
        publication.rejection_reason = reason
        publication.reviewed_by = acting_admin_id
        publication.reviewed_at = datetime.utcnow()
        db.session.commit()

        return jsonify({"id": publication.id, "status": publication.status})


    @app.route("/admin/library/<int:publication_id>/remove", methods=["POST"])
    @require_csrf
    @require_admin
    def admin_remove_library_item(publication_id):
        """
        Takedown for an already-approved publication (e.g. a reported item
        an admin has decided to act on) - the counterpart to reject, which
        only covers not-yet-approved submissions. Requires a reason, stored
        in the same rejection_reason column reject uses (kept generic
        rather than adding a parallel column for what is functionally the
        same "why did an admin act on this" note - same pattern as
        admin_remove_opportunity).
        """
        acting_admin_id = session.get("user_id")

        publication = db.session.get(LibraryPublication, publication_id)
        if not publication:
            return jsonify({"error": "Publication not found"}), 404
        if publication.status != "approved":
            return jsonify({"error": f"Can only remove an approved publication (status: {publication.status})"}), 400

        data = request.get_json(silent=True) or {}
        reason = (data.get("reason") or "").strip()
        if not reason or len(reason) > 500:
            return jsonify({"error": "reason is required and must be 500 characters or fewer"}), 400

        publication.status = "removed"
        publication.rejection_reason = reason
        publication.reviewed_by = acting_admin_id
        publication.reviewed_at = datetime.utcnow()
        log_admin_action(acting_admin_id, "library_publication_removed", target_type="library_publication", target_id=publication.id, details={"reason": reason})
        db.session.commit()

        return jsonify({"id": publication.id, "status": publication.status})


    LIBRARY_REPORT_RESOLUTIONS = {"dismissed", "actioned"}
    LIBRARY_REPORT_ADMIN_NOTES_MAX = 500


    @app.route("/admin/library/reports")
    @require_admin
    def admin_list_library_reports():
        """
        Lists Library reports for the moderation queue. Defaults to pending
        only; pass status=all to see dismissed/actioned ones too.
        """
        status_filter = request.args.get("status", "pending")

        query = LibraryReport.query
        if status_filter != "all":
            query = query.filter_by(status=status_filter)

        reports = query.order_by(LibraryReport.created_at.asc()).all()

        result = []
        for report in reports:
            publication = db.session.get(LibraryPublication, report.library_publication_id)
            reporter = db.session.get(User, report.reporter_user_id)
            result.append({
                "id": report.id,
                "library_publication_id": report.library_publication_id,
                "publication_title": publication.title if publication else None,
                "publication_status": publication.status if publication else None,
                "reporter_email": reporter.email if reporter else None,
                "reason": report.reason,
                "details": report.details,
                "status": report.status,
                "admin_notes": report.admin_notes,
                "created_at": report.created_at.isoformat() if report.created_at else None,
            })

        return jsonify({"reports": result})


    @app.route("/admin/library/reports/<int:report_id>/resolve", methods=["POST"])
    @require_csrf
    @require_admin
    def admin_resolve_library_report(report_id):
        """
        Marks a report dismissed or actioned. Deliberately does NOT touch the
        underlying LibraryPublication's status - taking a publication down is
        a separate, explicit admin decision (existing reject/removal paths),
        not an automatic side effect of closing a report.
        """
        acting_admin_id = session.get("user_id")

        report = db.session.get(LibraryReport, report_id)
        if not report:
            return jsonify({"error": "Report not found"}), 404
        if report.status != "pending":
            return jsonify({"error": f"Report is not pending (status: {report.status})"}), 400

        data = request.get_json(silent=True) or {}
        resolution = (data.get("status") or "").strip()
        if resolution not in LIBRARY_REPORT_RESOLUTIONS:
            return jsonify({"error": "status must be one of: " + ", ".join(sorted(LIBRARY_REPORT_RESOLUTIONS))}), 400

        admin_notes = data.get("admin_notes")
        if admin_notes is not None:
            admin_notes = admin_notes.strip()
            if len(admin_notes) > LIBRARY_REPORT_ADMIN_NOTES_MAX:
                return jsonify({"error": f"admin_notes must be {LIBRARY_REPORT_ADMIN_NOTES_MAX} characters or fewer"}), 400
            admin_notes = admin_notes or None

        report.status = resolution
        report.admin_notes = admin_notes
        report.reviewed_by = acting_admin_id
        report.reviewed_at = datetime.utcnow()
        db.session.commit()

        return jsonify({"id": report.id, "status": report.status})


    # ---------- Admin: content review (Chunk 10) ----------
    # Flags an individual GeneratedMaterial row (not the Document, and not
    # the LibraryPublication). A flagged material only affects the public
    # Library - see _document_content_has_flagged_material() (blocks new
    # publishes) and _flagged_document_ids() (hides already-published items)
    # above. A student can still privately generate/study flagged material;
    # this is a sharing gate, not an access gate.

    CONTENT_MATERIAL_FLAG_REASON_MAX = 500


    def _serialize_admin_content_material(material):
        content = db.session.get(DocumentContent, material.document_content_id)
        flagged_by_user = db.session.get(User, material.flagged_by) if material.flagged_by else None
        return {
            "id": material.id,
            "document_content_id": material.document_content_id,
            "material_type": material.material_type,
            "status": material.status,
            "file_type": content.file_type if content else None,
            "is_flagged": material.is_flagged,
            "flagged_reason": material.flagged_reason,
            "flagged_by_email": flagged_by_user.email if flagged_by_user else None,
            "flagged_at": material.flagged_at.isoformat() if material.flagged_at else None,
            "created_at": material.created_at.isoformat() if material.created_at else None,
        }


    @app.route("/admin/content-materials")
    @require_admin
    def admin_list_content_materials():
        """
        Lists GeneratedMaterial rows for admin review. Defaults to flagged
        only; pass status=all to see everything. Newest first.
        """
        status_filter = request.args.get("status", "flagged")

        query = GeneratedMaterial.query
        if status_filter == "flagged":
            query = query.filter_by(is_flagged=True)
        elif status_filter != "all":
            return jsonify({"error": "status must be 'flagged' or 'all'"}), 400

        materials = query.order_by(GeneratedMaterial.created_at.desc()).limit(200).all()

        return jsonify({"materials": [_serialize_admin_content_material(m) for m in materials]})


    @app.route("/admin/content-materials/<int:material_id>/flag", methods=["POST"])
    @require_csrf
    @require_admin
    def admin_flag_content_material(material_id):
        """
        Flags a GeneratedMaterial row, requiring a reason. Idempotent -
        re-flagging an already-flagged row just updates the reason/admin
        rather than erroring, so an admin can amend a flag without an
        unflag/reflag round trip.
        """
        acting_admin_id = session.get("user_id")

        material = db.session.get(GeneratedMaterial, material_id)
        if not material:
            return jsonify({"error": "Material not found"}), 404

        data = request.get_json(silent=True) or {}
        reason = (data.get("reason") or "").strip()
        if not reason or len(reason) > CONTENT_MATERIAL_FLAG_REASON_MAX:
            return jsonify({
                "error": f"reason is required and must be {CONTENT_MATERIAL_FLAG_REASON_MAX} characters or fewer"
            }), 400

        material.is_flagged = True
        material.flagged_reason = reason
        material.flagged_by = acting_admin_id
        material.flagged_at = datetime.utcnow()
        log_admin_action(acting_admin_id, "content_material_flagged", target_type="generated_material", target_id=material.id, details={"reason": reason})
        db.session.commit()

        return jsonify(_serialize_admin_content_material(material))


    @app.route("/admin/content-materials/<int:material_id>/unflag", methods=["POST"])
    @require_csrf
    @require_admin
    def admin_unflag_content_material(material_id):
        material = db.session.get(GeneratedMaterial, material_id)
        if not material:
            return jsonify({"error": "Material not found"}), 404

        if not material.is_flagged:
            return jsonify({"message": "Not flagged"}), 200

        material.is_flagged = False
        material.flagged_reason = None
        material.flagged_by = None
        material.flagged_at = None
        log_admin_action(session.get("user_id"), "content_material_unflagged", target_type="generated_material", target_id=material.id)
        db.session.commit()

        return jsonify(_serialize_admin_content_material(material))


    # ---------- XP / Achievements / Streaks (Chunk 7) ----------
    #
    # Fixed-value MVP: XP amounts and the achievement catalog are hardcoded
    # constants below rather than admin-editable SystemSetting rows (unlike
    # content prices) - that's a Phase 17 (Platform Controls) concern, not
    # this chunk's. All awarding funnels through award_xp()/unlock_achievement(),
    # which are idempotent the same way admin_approve_library_item already is:
    # insert into a uniquely-constrained table, and treat IntegrityError as
    # "already awarded" rather than an error.

    XP_DOCUMENT_STUDIED = 15
    XP_QUIZ_COMPLETED = 20
    XP_FLASHCARDS_COMPLETED = 10
    XP_COMMUNITY_HELPFUL_REPLY = 5
    XP_LIBRARY_PUBLICATION_APPROVED = LIBRARY_XP_ON_APPROVAL  # defined earlier, kept as one source of truth
    XP_STREAK_MILESTONES = {7: 50, 14: 100, 21: 150, 30: 200}

    # Cumulative XP required to REACH a level: cumulative(L) = 75 * L * (L-1).
    # Chosen so the curve lands on whole numbers and gives a natural ramp
    # (Level 4 starts at 900 XP, Level 5 at 1500 XP, etc).
    LEVEL_TITLES = {
        1: "Fresher", 2: "Learner", 3: "Achiever", 4: "Scholar", 5: "Sage",
        6: "Master", 7: "Luminary", 8: "Legend",
    }
    LEVEL_TITLE_FALLBACK = "Legend"
