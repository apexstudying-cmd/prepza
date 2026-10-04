"""Reconciled admin routes restored from the last complete admin runtime."""
import app as _app
# The module is imported at the end of app.py, after the current application
# globals and modular runtimes have been initialized.
globals().update({k:getattr(_app,k) for k in dir(_app) if not k.startswith("__")})

ANNOUNCEMENT_TITLE_MAX = 200

ANNOUNCEMENT_BODY_MAX = 500

@app.route("/admin/announcements", methods=["POST"])

def admin_send_announcement():
    """
    Broadcasts an announcement to every non-suspended user as a
    Notification(type="announcement"), and logs the send in
    Announcement for the Communications history table. Reach is
    computed and stored at send time.
    """
    acting_admin_id = session.get("user_id")

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()

    if not title or len(title) > ANNOUNCEMENT_TITLE_MAX:
        return jsonify({"error": f"title is required and must be {ANNOUNCEMENT_TITLE_MAX} characters or fewer"}), 400
    if not body or len(body) > ANNOUNCEMENT_BODY_MAX:
        return jsonify({"error": f"body is required and must be {ANNOUNCEMENT_BODY_MAX} characters or fewer"}), 400

    university_id = data.get("university_id")
    program_id = data.get("program_id")
    year = data.get("year")
    semester = data.get("semester")
    group_id = data.get("group_id")

    audience_query = User.query.filter(User.is_suspended.is_(False))

    if university_id is not None:
        if not isinstance(university_id, int) or isinstance(university_id, bool):
            return jsonify({"error": "university_id must be an integer"}), 400
        audience_query = audience_query.filter(User.university_id == university_id)

    if program_id is not None:
        if not isinstance(program_id, int) or isinstance(program_id, bool):
            return jsonify({"error": "program_id must be an integer"}), 400
        audience_query = audience_query.filter(User.program_id == program_id)

    if year is not None:
        if not isinstance(year, int) or isinstance(year, bool):
            return jsonify({"error": "year must be an integer"}), 400
        audience_query = audience_query.filter(User.year == year)

    if semester is not None:
        if not isinstance(semester, int) or isinstance(semester, bool):
            return jsonify({"error": "semester must be an integer"}), 400
        audience_query = audience_query.filter(User.semester == semester)

    if group_id is not None:
        if not isinstance(group_id, int) or isinstance(group_id, bool):
            return jsonify({"error": "group_id must be an integer"}), 400
        if not db.session.get(Group, group_id):
            return jsonify({"error": "Group not found"}), 404
        member_ids = [
            row[0] for row in
            db.session.query(GroupMember.user_id).filter(GroupMember.group_id == group_id).all()
        ]
        audience_query = audience_query.filter(User.id.in_(member_ids))

    recipient_ids = [row.id for row in audience_query.with_entities(User.id).all()]

    announcement = Announcement(title=title, body=body, sent_by=acting_admin_id, reach=len(recipient_ids))
    db.session.add(announcement)
    db.session.flush()  # assign announcement.id before Notification.related_id references it

    for recipient_id in recipient_ids:
        db.session.add(Notification(
            user_id=recipient_id,
            type="announcement",
            title=title,
            body=body,
            related_type="announcement",
            related_id=announcement.id,
        ))

    db.session.commit()

    # Best-effort push fan-out to the same audience - never blocks or fails
    # the announcement itself if push sending has issues (see
    # send_push_notification()'s own internal error handling).
    for recipient_id in recipient_ids:
        send_push_notification(recipient_id, title, body)

    return jsonify({
        "id": announcement.id,
        "title": announcement.title,
        "body": announcement.body,
        "reach": announcement.reach,
        "created_at": announcement.created_at.isoformat(),
    }), 201

@app.route("/admin/announcements")

def admin_list_announcements():
    """History for the Communications tab, newest first."""
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).limit(50).all()
    return jsonify([
        {
            "id": a.id,
            "title": a.title,
            "body": a.body,
            "reach": a.reach,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in announcements
    ])


# ---------- Admin: moderation (Chunk 10) ----------

def _content_report_preview(report):
    """
    Best-effort preview of the reported content for the admin queue -
    a short text snippet plus who authored it. Returns None fields if
    the target was hard-deleted out from under the report (shouldn't
    normally happen since content is soft-removed, but don't 500 if it
    does).
    """
    author_id = None
    snippet = None

    if report.target_type == "group_post":
        row = db.session.get(GroupPost, report.target_id)
        if row:
            author_id = row.user_id
            snippet = row.body
    elif report.target_type == "group_post_comment":
        row = db.session.get(GroupPostComment, report.target_id)
        if row:
            author_id = row.user_id
            snippet = row.body
    elif report.target_type == "user":
        author_id = report.target_id

    author = db.session.get(User, author_id) if author_id else None
    return {
        "author_id": author_id,
        "author_email": author.email if author else None,
        "snippet": (snippet[:200] if snippet else None),
    }

def _serialize_content_report(report):
    reporter = db.session.get(User, report.reporter_user_id) if report.reporter_user_id else None
    entry = {
        "id": report.id,
        "target_type": report.target_type,
        "target_id": report.target_id,
        "reporter_email": reporter.email if reporter else "System",
        "reason": report.reason,
        "details": report.details,
        "priority": report.priority,
        "status": report.status,
        "action_taken": report.action_taken,
        "admin_notes": report.admin_notes,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }
    entry.update(_content_report_preview(report))
    return entry

@app.route("/admin/content-reports")

def admin_list_content_reports():
    """
    Moderation queue. Defaults to pending only, ordered highest
    priority first (then oldest first within a priority tier) so the
    most urgent reports surface at the top; pass status=all to see
    dismissed/actioned ones too.

    Sorted in Python rather than via a SQL CASE expression - same
    pattern as admin_list_users() below, which avoids depending on
    SQLAlchemy version-specific case() syntax (the tuple-positional
    form needs 1.4+; older installs need the list/`whens=` form).
    Report volume is small enough that this costs nothing.
    """
    status_filter = request.args.get("status", "pending")
    if status_filter != "all" and status_filter not in CONTENT_REPORT_STATUSES:
        return jsonify({"error": "status must be 'all' or one of: " + ", ".join(CONTENT_REPORT_STATUSES)}), 400

    query = ContentReport.query
    if status_filter != "all":
        query = query.filter_by(status=status_filter)

    reports = query.order_by(ContentReport.created_at.asc()).all()
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    reports.sort(key=lambda r: priority_rank.get(r.priority, 3))

    return jsonify({"reports": [_serialize_content_report(r) for r in reports]})

@app.route("/admin/content-reports/summary")

def admin_content_reports_summary():
    """KPI row for the Moderation tab header."""
    open_reports = ContentReport.query.filter_by(status="pending").count()
    today = datetime.utcnow().date()
    resolved_today = ContentReport.query.filter(
        ContentReport.status != "pending",
        func.date(ContentReport.reviewed_at) == today,
    ).count()
    suspended_users = User.query.filter_by(is_suspended=True).count()
    warnings_issued = UserWarning.query.count()

    return jsonify({
        "open_reports": open_reports,
        "resolved_today": resolved_today,
        "suspended_users": suspended_users,
        "warnings_issued": warnings_issued,
    })

def _load_pending_report(report_id):
    report = db.session.get(ContentReport, report_id)
    if not report:
        return None, (jsonify({"error": "Report not found"}), 404)
    if report.status != "pending":
        return None, (jsonify({"error": f"Report is not pending (status: {report.status})"}), 400)
    return report, None

@app.route("/admin/content-reports/<int:report_id>/dismiss", methods=["POST"])

def admin_dismiss_content_report(report_id):
    acting_admin_id = session.get("user_id")
    report, error = _load_pending_report(report_id)
    if error:
        return error

    data = request.get_json(silent=True) or {}
    admin_notes = data.get("admin_notes")
    if admin_notes is not None:
        admin_notes = admin_notes.strip()
        if len(admin_notes) > CONTENT_REPORT_DETAILS_MAX:
            return jsonify({"error": f"admin_notes must be {CONTENT_REPORT_DETAILS_MAX} characters or fewer"}), 400
        admin_notes = admin_notes or None

    report.status = "dismissed"
    report.action_taken = "dismissed"
    report.admin_notes = admin_notes
    report.reviewed_by = acting_admin_id
    report.reviewed_at = datetime.utcnow()
    log_admin_action(acting_admin_id, "content_report_dismissed", target_type="content_report", target_id=report.id, details={"admin_notes": admin_notes} if admin_notes else None)
    db.session.commit()

    return jsonify(_serialize_content_report(report))

@app.route("/admin/content-reports/<int:report_id>/remove", methods=["POST"])

def admin_remove_reported_content(report_id):
    """
    Hides the reported content (soft-remove, same is_removed pattern
    used everywhere else) and marks the report actioned. Not valid for
    target_type='user' - there's no "content" to remove for a user
    report; use /warn or the existing /admin/users suspend toggle
    instead.
    """
    acting_admin_id = session.get("user_id")
    report, error = _load_pending_report(report_id)
    if error:
        return error

    if report.target_type == "user":
        return jsonify({
            "error": "Can't 'remove' a user report - use /admin/content-reports/<id>/warn, "
                     "or suspend the user via PATCH /admin/users/<id>"
        }), 400

    model_by_type = {
        "group_post": GroupPost,
        "group_post_comment": GroupPostComment,
    }
    model = model_by_type[report.target_type]
    target = db.session.get(model, report.target_id)
    if not target:
        return jsonify({"error": "Reported content no longer exists"}), 404

    target.is_removed = True

    data = request.get_json(silent=True) or {}
    admin_notes = data.get("admin_notes")
    if admin_notes is not None:
        admin_notes = admin_notes.strip()
        if len(admin_notes) > CONTENT_REPORT_DETAILS_MAX:
            return jsonify({"error": f"admin_notes must be {CONTENT_REPORT_DETAILS_MAX} characters or fewer"}), 400
        admin_notes = admin_notes or None

    report.status = "actioned"
    report.action_taken = "removed"
    report.admin_notes = admin_notes
    report.reviewed_by = acting_admin_id
    report.reviewed_at = datetime.utcnow()
    log_admin_action(acting_admin_id, "content_report_content_removed", target_type="content_report", target_id=report.id, details={"target_type": report.target_type, "target_id": report.target_id})
    db.session.commit()

    return jsonify(_serialize_content_report(report))

@app.route("/admin/content-reports/<int:report_id>/warn", methods=["POST"])

def admin_warn_from_content_report(report_id):
    """
    Issues a UserWarning to the content's author (or the reported user
    directly, for target_type='user'), tied back to this report. The
    warning ALWAYS reaches the student as a Notification - message
    states what they did wrong, consequence states what happens as a
    result. Both are admin-authored per warning, not templated, since
    the punishment should fit the specific violation. Optionally also
    removes the content in the same call (remove_content=true).
    """
    acting_admin_id = session.get("user_id")
    report, error = _load_pending_report(report_id)
    if error:
        return error

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    consequence = (data.get("consequence") or "").strip()
    remove_content = bool(data.get("remove_content"))

    if not message or len(message) > CONTENT_REPORT_DETAILS_MAX:
        return jsonify({"error": f"message is required and must be {CONTENT_REPORT_DETAILS_MAX} characters or fewer"}), 400
    if not consequence or len(consequence) > CONTENT_REPORT_DETAILS_MAX:
        return jsonify({"error": f"consequence is required and must be {CONTENT_REPORT_DETAILS_MAX} characters or fewer"}), 400

    if report.target_type == "user":
        warned_user_id = report.target_id
    else:
        preview = _content_report_preview(report)
        warned_user_id = preview["author_id"]
        if not warned_user_id:
            return jsonify({"error": "Could not determine the content's author to warn"}), 404

        if remove_content:
            model_by_type = {
                "group_post": GroupPost,
                "group_post_comment": GroupPostComment,
            }
            target = db.session.get(model_by_type[report.target_type], report.target_id)
            if target:
                target.is_removed = True

    warning = UserWarning(
        user_id=warned_user_id,
        issued_by=acting_admin_id,
        content_report_id=report.id,
        reason=report.reason,
        message=message,
        consequence=consequence,
    )
    db.session.add(warning)
    db.session.flush()  # assign warning.id before Notification.related_id references it

    db.session.add(Notification(
        user_id=warned_user_id,
        type="moderation_warning",
        title="You've received a warning",
        body=f"{message} {consequence}",
        related_type="user_warning",
        related_id=warning.id,
    ))
    send_push_notification(warned_user_id, "You've received a warning", f"{message} {consequence}")

    report.status = "actioned"
    report.action_taken = "warned"
    report.reviewed_by = acting_admin_id
    report.reviewed_at = datetime.utcnow()
    log_admin_action(acting_admin_id, "content_report_warning_issued", target_type="user_warning", target_id=warning.id, details={"warned_user_id": warned_user_id, "reason": report.reason})
    db.session.commit()

    return jsonify({
        "report": _serialize_content_report(report),
        "warning_id": warning.id,
        "content_removed": remove_content and report.target_type != "user",
    })

def list_my_warnings():
    """Lets a student see their own warning history - what they did
    wrong and the consequence, in their own words from the admin."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    warnings = (
        UserWarning.query.filter_by(user_id=user_id)
        .order_by(UserWarning.created_at.desc())
        .all()
    )
    return jsonify({"warnings": [
        {
            "id": w.id,
            "reason": w.reason,
            "message": w.message,
            "consequence": w.consequence,
            "created_at": w.created_at.isoformat() if w.created_at else None,
        }
        for w in warnings
    ]})

@app.route("/admin/ai-usage")

def admin_ai_usage():
    """
    Rollup of AI usage/cost for the admin AI & Usage dashboard, sourced
    from AiUsageLog (populated by ai_service.py on every AI call - both
    document actions and forum Q&A share this table via request_type).

    NOTE on gaps this endpoint deliberately does NOT paper over:
      - AiUsageLog has no success/failure column, so a request-level
        error rate can't be computed from it. failed_jobs/completed_jobs
        below come from AiJob instead, which only covers the document
        pipeline (text_extraction/summary/quiz/flashcards/podcast) -
        forum Q&A failures aren't persisted anywhere today (ai_service
        raises an exception, the route translates it to an HTTP error,
        nothing is logged). Treat failed_jobs as a partial signal, not
        a true platform-wide error rate.
      - Average response time isn't tracked anywhere in the schema, so
        it's omitted entirely rather than estimated.
    """
    try:
        days = int(request.args.get("days", 30))
    except ValueError:
        days = 30
    days = max(1, min(days, 365))
    window_start = datetime.utcnow() - timedelta(days=days)

    base = AiUsageLog.query.filter(AiUsageLog.created_at >= window_start)

    total_requests = base.count()
    totals_row = db.session.query(
        func.coalesce(func.sum(AiUsageLog.cost_usd), 0),
        func.coalesce(func.sum(AiUsageLog.input_tokens), 0),
        func.coalesce(func.sum(AiUsageLog.output_tokens), 0),
        func.coalesce(func.sum(AiUsageLog.cache_read_tokens), 0),
        func.coalesce(func.sum(AiUsageLog.cache_creation_tokens), 0),
    ).filter(AiUsageLog.created_at >= window_start).first()
    total_cost_usd, total_input_tokens, total_output_tokens, total_cache_read, total_cache_creation = totals_row

    by_feature_raw = (
        db.session.query(
            AiUsageLog.request_type,
            func.count(AiUsageLog.id),
            func.coalesce(func.sum(AiUsageLog.cost_usd), 0),
        )
        .filter(AiUsageLog.created_at >= window_start)
        .group_by(AiUsageLog.request_type)
        .order_by(func.count(AiUsageLog.id).desc())
        .all()
    )
    by_feature = [
        {"request_type": request_type, "requests": count, "cost_usd": float(cost)}
        for request_type, count, cost in by_feature_raw
    ]

    daily_raw = (
        db.session.query(
            func.date(AiUsageLog.created_at).label("day"),
            func.count(AiUsageLog.id),
            func.coalesce(func.sum(AiUsageLog.cost_usd), 0),
        )
        .filter(AiUsageLog.created_at >= window_start)
        .group_by(func.date(AiUsageLog.created_at))
        .order_by(func.date(AiUsageLog.created_at))
        .all()
    )
    daily_trend = [
        {"date": day.isoformat(), "requests": count, "cost_usd": float(cost)}
        for day, count, cost in daily_raw
    ]

    today = datetime.utcnow().date()
    requests_today = AiUsageLog.query.filter(func.date(AiUsageLog.created_at) == today).count()

    failed_jobs = AiJob.query.filter(
        AiJob.status == "failed", AiJob.created_at >= window_start,
    ).count()
    completed_jobs = AiJob.query.filter(
        AiJob.status == "completed", AiJob.created_at >= window_start,
    ).count()

    return jsonify({
        "period_days": days,
        "total_requests": total_requests,
        "requests_today": requests_today,
        "total_cost_usd": float(total_cost_usd),
        "total_tokens": int(total_input_tokens) + int(total_output_tokens),
        "input_tokens": int(total_input_tokens),
        "output_tokens": int(total_output_tokens),
        "cache_read_tokens": int(total_cache_read),
        "cache_creation_tokens": int(total_cache_creation),
        "by_feature": by_feature,
        "daily_trend": daily_trend,
        "document_pipeline_jobs": {
            "completed": completed_jobs,
            "failed": failed_jobs,
            "note": "Covers text_extraction/summary/quiz/flashcards/podcast jobs only - forum Q&A failures aren't logged.",
        },
    })

@app.route("/admin/ai-jobs")

def admin_list_ai_jobs():
    """
    Lists recent AiJob rows for admin visibility, optionally filtered
    by status (?status=failed). Newest first.
    """
    status_filter = request.args.get("status")

    query = AiJob.query
    if status_filter:
        query = query.filter_by(status=status_filter)

    jobs = query.order_by(AiJob.created_at.desc()).limit(100).all()

    return jsonify([
        {
            "id": j.id,
            "document_content_id": j.document_content_id,
            "feature": j.feature,
            "status": j.status,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            "error_message": j.error_message,
            "retry_count": j.retry_count,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ])

@app.route("/admin/ai-jobs/<int:job_id>/retry", methods=["POST"])

def admin_retry_ai_job(job_id):
    """
    Re-runs a failed job synchronously (not backgrounded - admin is
    waiting on the response) and increments retry_count regardless of
    outcome, so repeated failures are visible in the job list.
    """
    job = db.session.get(AiJob, job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job.status not in ("failed", "completed"):
        return jsonify({"error": f"Job is currently '{job.status}' - wait for it to finish before retrying"}), 400

    job.retry_count = (job.retry_count or 0) + 1
    db.session.commit()

    try:
        if job.feature == "text_extraction":
            document_pipeline.process_document(job.document_content_id)
        else:
            return jsonify({"error": f"No retry handler for feature '{job.feature}' yet"}), 400
    except Exception as e:
        return jsonify({"error": f"Retry failed: {e}"}), 502

    return jsonify({"message": "Retry completed", "job_id": job.id})

@app.route("/admin/content", methods=["GET"])

def admin_list_content():
    # The current ContentItem schema is no longer unit-backed. Older
    # versions exposed unit_id/unit_code here, but the Unit model and
    # ContentItem.unit_id column were removed by the current schema.
    if request.args.get("unit_id") is not None:
        return jsonify({"error": "unit_id is no longer supported"}), 400

    items = ContentItem.query.order_by(ContentItem.id.desc()).all()

    result = [
        {
            "id": item.id,
            "unit_id": None,
            "unit_code": None,
            "content_type": item.content_type,
            "title": item.title,
            "file_url": item.file_url,
            "paper_year": item.paper_year,
            "is_downloadable": item.is_downloadable,
            "price": get_price_for_type(item.content_type),
        }
        for item in items
    ]

    return jsonify({"content": result})

@app.route("/admin/content", methods=["POST"])

def admin_add_content():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    if data.get("unit_id") is not None:
        return jsonify({"error": "unit_id is no longer supported"}), 400

    content_type = data.get("content_type")
    title = data.get("title")
    file_url = data.get("file_url")
    paper_year = data.get("paper_year")

    if not content_type or not title:
        return jsonify({"error": "content_type and title are required"}), 400

    if content_type not in ("past_paper", "notes", "qna"):
        return jsonify({"error": "content_type must be past_paper, notes, or qna"}), 400

    is_downloadable = False if content_type == "qna" else True

    item = ContentItem(
        content_type=content_type,
        title=title,
        file_url=file_url,
        paper_year=paper_year,
        is_downloadable=is_downloadable,
    )
    db.session.add(item)
    db.session.commit()

    return jsonify({"message": "Content added", "content_id": item.id}), 201

@app.route("/admin/content/<int:content_id>", methods=["PATCH"])

def admin_update_content(content_id):
    item = db.session.get(ContentItem, content_id)
    if not item:
        return jsonify({"error": "Content not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    if "title" in data:
        item.title = data["title"]
    if "file_url" in data:
        item.file_url = data["file_url"]
    if "paper_year" in data:
        item.paper_year = data["paper_year"]

    db.session.commit()

    return jsonify({
        "message": "Content updated",
        "content_id": item.id,
        "price": get_price_for_type(item.content_type),
        "title": item.title,
    })

@app.route("/admin/payments", methods=["GET"])

def admin_list_payments():
    status_filter = request.args.get("status")

    query = Payment.query
    if status_filter:
        query = query.filter_by(status=status_filter)

    payments = query.order_by(Payment.created_at.desc()).all()

    result = []
    for p in payments:
        content_item = db.session.get(ContentItem, p.content_item_id) if p.content_item_id else None
        user = db.session.get(User, p.user_id) if p.user_id else None
        result.append({
            "id": p.id,
            "user_id": p.user_id,
            "user_email": user.email if user else None,
            "user_display_name": user.display_name if user else None,
            "payment_type": p.payment_type,
            "content_title": content_item.title if content_item else None,
            "plan": p.plan,
            "phone_number": p.phone_number,
            "amount": p.amount,
            "status": p.status,
            "provider": p.provider,
            "reference": p.reference,
            "subscription_expires_at": p.subscription_expires_at.isoformat() if p.subscription_expires_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    return jsonify({"payments": result})

@app.route("/admin/analytics")

def admin_analytics():
    total_revenue = db.session.query(
        func.coalesce(func.sum(Payment.amount), 0)
    ).filter(Payment.status == "success").scalar()

    total_users = db.session.query(func.count(User.id)).scalar()

    # "Active today" = any authenticated request today (login, browsing,
    # chatting, studying - see track_last_active()), not just specific
    # study actions.
    today = datetime.utcnow().date()
    active_today = db.session.query(
        func.count(User.id)
    ).filter(func.date(User.last_active_at) == today).scalar()

    # Storage is summed off DocumentContent, not Document - DocumentContent
    # is the deduplicated, one-row-per-unique-file table, so a document
    # shared by many students' Document rows is only counted once.
    storage_used_bytes = db.session.query(
        func.coalesce(func.sum(DocumentContent.file_size_bytes), 0)
    ).scalar()

    # Unit is no longer part of the current content schema. Keep the
    # response field for backward-compatible admin clients, but do not
    # query a removed model/table.
    total_units = 0
    total_content = db.session.query(func.count(ContentItem.id)).scalar()

    content_by_type = dict(
        db.session.query(ContentItem.content_type, func.count(ContentItem.id))
        .group_by(ContentItem.content_type)
        .all()
    )

    payments_by_status = dict(
        db.session.query(Payment.status, func.count(Payment.id))
        .group_by(Payment.status)
        .all()
    )

    revenue_30d = db.session.query(
        func.coalesce(func.sum(Payment.amount), 0)
    ).filter(
        Payment.status == "success",
        Payment.created_at >= datetime.utcnow() - timedelta(days=30),
    ).scalar()

    trend_start = datetime.utcnow() - timedelta(days=30)

    signups_raw = (
        db.session.query(
            func.date(User.created_at).label("day"),
            func.count(User.id),
        )
        .filter(User.created_at >= trend_start)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
        .all()
    )
    signups_per_day = [
        {"date": day.isoformat(), "count": count}
        for day, count in signups_raw
    ]

    revenue_raw = (
        db.session.query(
            func.date(Payment.created_at).label("day"),
            func.coalesce(func.sum(Payment.amount), 0),
        )
        .filter(
            Payment.status == "success",
            Payment.created_at >= trend_start,
        )
        .group_by(func.date(Payment.created_at))
        .order_by(func.date(Payment.created_at))
        .all()
    )
    revenue_per_day = [
        {"date": day.isoformat(), "amount": amount}
        for day, amount in revenue_raw
    ]

    top_content_raw = (
        db.session.query(
            ContentItem.id,
            ContentItem.title,
            ContentItem.content_type,
            func.coalesce(func.sum(Payment.amount), 0).label("revenue"),
            func.count(Payment.id).label("purchases"),
        )
        .join(Payment, Payment.content_item_id == ContentItem.id)
        .filter(Payment.status == "success")
        .group_by(ContentItem.id, ContentItem.title, ContentItem.content_type)
        .order_by(func.coalesce(func.sum(Payment.amount), 0).desc())
        .limit(10)
        .all()
    )
    top_performing_content = [
        {
            "id": cid,
            "title": title,
            "content_type": content_type,
            "revenue": revenue,
            "purchases": purchases,
        }
        for cid, title, content_type, revenue, purchases in top_content_raw
    ]

    return jsonify({
        "total_revenue": total_revenue,
        "revenue_last_30d": revenue_30d,
        "total_users": total_users,
        "active_today": active_today,
        "storage_used_bytes": int(storage_used_bytes),
        "total_units": total_units,
        "total_content_items": total_content,
        "content_by_type": content_by_type,
        "payments_by_status": payments_by_status,
        "signups_per_day": signups_per_day,
        "revenue_per_day": revenue_per_day,
        "top_performing_content": top_performing_content,
    })

@app.route("/admin/analytics/universities")

def admin_analytics_universities():
    """
    Per-university engagement rollup for the admin Analytics tab.
    Only includes universities with at least one signed-up student.
    Engagement tier is a relative ranking (top/bottom quartile of a
    combined documents+AI-requests score) among the universities
    returned here, not an absolute scale - same reasoning as the
    percentile-based work used elsewhere (e.g. XP leaderboards): with
    a handful of universities, fixed thresholds like ">10000 requests
    = Very High" would be meaningless noise, whereas relative ranking
    stays useful regardless of platform size.

    "Premium users" reuses the same latest-successful-subscription
    dedup logic as GET /admin/users, just grouped by university
    instead of returned per-user.
    """
    student_counts = dict(
        db.session.query(User.university_id, func.count(User.id))
        .filter(User.university_id.isnot(None))
        .group_by(User.university_id)
        .all()
    )
    if not student_counts:
        return jsonify({"universities": []})

    uni_ids = list(student_counts.keys())
    universities = {u.id: u.name for u in University.query.filter(University.id.in_(uni_ids)).all()}

    doc_counts = dict(
        db.session.query(User.university_id, func.count(Document.id))
        .select_from(Document)
        .join(User, Document.user_id == User.id)
        .filter(Document.is_removed.is_(False), User.university_id.in_(uni_ids))
        .group_by(User.university_id)
        .all()
    )

    ai_counts = dict(
        db.session.query(User.university_id, func.count(AiUsageLog.id))
        .select_from(AiUsageLog)
        .join(User, AiUsageLog.user_id == User.id)
        .filter(User.university_id.in_(uni_ids))
        .group_by(User.university_id)
        .all()
    )

    # Same active-subscription dedup as GET /admin/users, then grouped
    # by university instead of returned per-user.
    sub_rows = (
        db.session.query(Payment.user_id, Payment.subscription_expires_at)
        .join(User, Payment.user_id == User.id)
        .filter(
            User.university_id.in_(uni_ids),
            Payment.payment_type == "subscription",
            Payment.status == "success",
            Payment.subscription_expires_at.isnot(None),
        )
        .all()
    )
    latest_expiry = {}
    for uid, expires_at in sub_rows:
        if uid not in latest_expiry or expires_at > latest_expiry[uid]:
            latest_expiry[uid] = expires_at
    now = datetime.utcnow()
    active_user_ids = [uid for uid, expires_at in latest_expiry.items() if expires_at > now]
    premium_counts = dict(
        db.session.query(User.university_id, func.count(User.id))
        .filter(User.id.in_(active_user_ids), User.university_id.in_(uni_ids))
        .group_by(User.university_id)
        .all()
    ) if active_user_ids else {}

    rows = []
    for uid in uni_ids:
        docs = doc_counts.get(uid, 0)
        ai_reqs = ai_counts.get(uid, 0)
        rows.append({
            "university_id": uid,
            "university_name": universities.get(uid, "Unknown"),
            "students": student_counts.get(uid, 0),
            "documents": docs,
            "ai_requests": ai_reqs,
            "premium_users": premium_counts.get(uid, 0),
            "_score": docs + ai_reqs,
        })

    rows.sort(key=lambda r: r["_score"], reverse=True)
    n = len(rows)
    for i, r in enumerate(rows):
        percentile = i / n
        if percentile < 0.25:
            r["engagement"] = "Very High"
        elif percentile < 0.5:
            r["engagement"] = "High"
        elif percentile < 0.75:
            r["engagement"] = "Medium"
        else:
            r["engagement"] = "Low"
        del r["_score"]

    return jsonify({"universities": rows})


# Plan tiers a bootstrapped single-operator app can pick between on the
# System tab - approximate published Supabase limits per tier. Not
# fetched from a Supabase API (that would need a separate integration);
# the admin just clicks which tier they're currently on, and it's
# persisted in SystemSetting like other admin-editable values (see
# admin_get_settings / admin_update_settings above for the same
# pattern). Add a new key here if Supabase adds/changes a tier.

SUPABASE_TIER_LIMITS = {
    "free": {"db_size_bytes": 500 * 1024 * 1024, "storage_bytes": 1 * 1024 * 1024 * 1024, "connections": 60},
    "pro": {"db_size_bytes": 8 * 1024 * 1024 * 1024, "storage_bytes": 100 * 1024 * 1024 * 1024, "connections": 200},
    "team": {"db_size_bytes": 8 * 1024 * 1024 * 1024, "storage_bytes": 200 * 1024 * 1024 * 1024, "connections": 400},
}

SUPABASE_DEFAULT_TIER = "free"

def _get_supabase_tier():
    setting = SystemSetting.query.filter_by(key="supabase_tier").first()
    tier = setting.value if setting and setting.value in SUPABASE_TIER_LIMITS else SUPABASE_DEFAULT_TIER
    return tier

@app.route("/admin/system/capacity")

def admin_system_capacity():
    """
    Capacity/budget tracking for a bootstrapped, single-operator app -
    answers "am I about to outgrow my plan" and "what's my AI burn
    rate," not "is SendGrid up right now" (that would need a real
    health-check system with historical uptime storage, out of scope
    here). Plan limits come from SUPABASE_TIER_LIMITS keyed by whichever
    tier is currently selected in SystemSetting - see
    /admin/system/capacity/tier to change it.
    """
    tier = _get_supabase_tier()
    limits = SUPABASE_TIER_LIMITS[tier]

    db_size_bytes = db.session.execute(
        db.text("SELECT pg_database_size(current_database())")
    ).scalar()

    storage_used_bytes = db.session.query(
        func.coalesce(func.sum(DocumentContent.file_size_bytes), 0)
    ).scalar()

    active_connections = db.session.execute(
        db.text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
    ).scalar()

    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    ai_spend_mtd = db.session.query(
        func.coalesce(func.sum(AiUsageLog.cost_usd), 0)
    ).filter(AiUsageLog.created_at >= month_start).scalar()

    days_elapsed = max((now - month_start).days + 1, 1)
    if now.month == 12:
        next_month_start = datetime(now.year + 1, 1, 1)
    else:
        next_month_start = datetime(now.year, now.month + 1, 1)
    days_in_month = (next_month_start - month_start).days
    ai_spend_projected = float(ai_spend_mtd) / days_elapsed * days_in_month

    return jsonify({
        "tier": tier,
        "available_tiers": list(SUPABASE_TIER_LIMITS.keys()),
        "db_size_bytes": int(db_size_bytes),
        "db_size_limit_bytes": limits["db_size_bytes"],
        "storage_used_bytes": int(storage_used_bytes),
        "storage_limit_bytes": limits["storage_bytes"],
        "active_connections": int(active_connections),
        "connection_limit": limits["connections"],
        "ai_spend_mtd_usd": float(ai_spend_mtd),
        "ai_spend_projected_month_end_usd": round(ai_spend_projected, 2),
        "days_elapsed_this_month": days_elapsed,
        "days_in_month": days_in_month,
    })

@app.route("/admin/system/capacity/tier", methods=["POST"])

def admin_set_supabase_tier():
    """Switches which Supabase plan tier the capacity bars are measured against."""
    data = request.get_json(silent=True) or {}
    tier = data.get("tier")
    if tier not in SUPABASE_TIER_LIMITS:
        return jsonify({"error": "tier must be one of: " + ", ".join(SUPABASE_TIER_LIMITS.keys())}), 400

    setting = SystemSetting.query.filter_by(key="supabase_tier").first()
    if not setting:
        setting = SystemSetting(key="supabase_tier", value=tier)
        db.session.add(setting)
    else:
        setting.value = tier
    db.session.commit()

    return jsonify({"tier": tier})

@app.route("/admin/payments/<int:payment_id>/refund", methods=["POST"])

def admin_refund_payment(payment_id):
    payment = db.session.get(Payment, payment_id)
    if not payment:
        return jsonify({"error": "Payment not found"}), 404

    if payment.status != "success":
        return jsonify({
            "error": f"Only successful payments can be refunded (current status: {payment.status})"
        }), 400

    payment.status = "refunded"

    if payment.payment_type == "subscription" and payment.user_id is not None:
        recompute_subscription_expiries(payment.user_id)

    referral = Referral.query.filter_by(first_payment_id=payment.id).first()
    referral_commission_voided = False
    if referral and referral.payout_id is None and referral.voided_at is None:
        referral.voided_at = datetime.utcnow()
        referral.void_reason = "Underlying payment refunded"
        referral_commission_voided = True

    db.session.commit()

    return jsonify({
        "message": "Payment marked as refunded. Access to this content has been revoked.",
        "referral_commission_voided": referral_commission_voided,
        "payment_id": payment.id,
        "note": "This only updates records in Prepza. You must still send the actual M-Pesa refund manually.",
    })
