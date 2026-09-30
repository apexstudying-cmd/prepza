"""Reconciled admin routes restored from the last complete admin runtime."""
import app as _app
# The module is imported at the end of app.py, after the current application
# globals and modular runtimes have been initialized.
globals().update({k:getattr(_app,k) for k in dir(_app) if not k.startswith("__")})

def _serialize_opportunity_admin(opp):
    """Same shape as _serialize_opportunity() plus the organisation's
    name/verification state, so the admin queue doesn't need a second
    round trip per row."""
    org = db.session.get(Organisation, opp.organisation_id)
    entry = _serialize_opportunity(opp)
    entry["organisation_name"] = org.name if org else None
    entry["organisation_verification_status"] = org.verification_status if org else None
    entry["organisation_is_active"] = org.is_active if org else None
    return entry

@app.route("/admin/opportunities")

def admin_list_opportunities():
    """Review queue. Defaults to pending_review only (the actual queue);
    pass status=all to see every opportunity regardless of status, or
    a specific status to filter to just that one."""
    status_filter = request.args.get("status", "pending_review")

    query = Opportunity.query
    if status_filter != "all":
        if status_filter not in OPPORTUNITY_STATUSES:
            return jsonify({
                "error": "status must be 'all' or one of: " + ", ".join(OPPORTUNITY_STATUSES)
            }), 400
        query = query.filter_by(status=status_filter)

    opportunities = query.order_by(Opportunity.submitted_at.asc().nullslast(), Opportunity.created_at.asc()).all()
    return jsonify({"opportunities": [_serialize_opportunity_admin(o) for o in opportunities]})

@app.route("/admin/opportunities/<int:opportunity_id>/approve", methods=["POST"])

def admin_approve_opportunity(opportunity_id):
    """
    Approves a pending_review opportunity. Does NOT publish it - Publish
    is a separate, deliberate action (see admin_publish_opportunity)
    so an admin can approve now and schedule the actual go-live
    separately. Re-checks the organisation is still verified and active,
    since its standing could have changed since submission.
    """
    acting_admin_id = session.get("user_id")

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp:
        return jsonify({"error": "Opportunity not found"}), 404
    if opp.status != "pending_review":
        return jsonify({"error": f"Opportunity is not pending review (status: {opp.status})"}), 400

    org = db.session.get(Organisation, opp.organisation_id)
    if not org or org.verification_status != "verified" or not org.is_active:
        return jsonify({
            "error": "The submitting organisation is no longer verified and active - "
                     "resolve that before approving"
        }), 400

    opp.status = "approved"
    opp.rejection_reason = None
    opp.reviewed_by = acting_admin_id
    opp.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_serialize_opportunity_admin(opp))

@app.route("/admin/opportunities/<int:opportunity_id>/reject", methods=["POST"])

def admin_reject_opportunity(opportunity_id):
    """Rejects a pending_review opportunity with a required reason. The
    org can edit and resubmit via its own PATCH + /submit routes."""
    acting_admin_id = session.get("user_id")

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp:
        return jsonify({"error": "Opportunity not found"}), 404
    if opp.status != "pending_review":
        return jsonify({"error": f"Opportunity is not pending review (status: {opp.status})"}), 400

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason or len(reason) > 500:
        return jsonify({"error": "reason is required and must be 500 characters or fewer"}), 400

    opp.status = "rejected"
    opp.rejection_reason = reason
    opp.reviewed_by = acting_admin_id
    opp.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_serialize_opportunity_admin(opp))

@app.route("/admin/opportunities/<int:opportunity_id>/publish", methods=["POST"])

def admin_publish_opportunity(opportunity_id):
    """
    Makes an approved opportunity live (visible to students - see the
    browse routes patch). Re-checks the organisation's standing and the
    opportunity's own dates one more time, since time may have passed
    since approval.
    """
    opp = db.session.get(Opportunity, opportunity_id)
    if not opp:
        return jsonify({"error": "Opportunity not found"}), 404
    if opp.status != "approved":
        return jsonify({"error": f"Opportunity is not approved (status: {opp.status})"}), 400

    org = db.session.get(Organisation, opp.organisation_id)
    if not org or org.verification_status != "verified" or not org.is_active:
        return jsonify({
            "error": "The submitting organisation is no longer verified and active - "
                     "resolve that before publishing"
        }), 400

    now = datetime.utcnow()
    if opp.application_deadline <= now or opp.expiry_date <= now:
        return jsonify({
            "error": "Cannot publish - application_deadline or expiry_date has already passed"
        }), 400

    opp.status = "published"
    opp.published_at = now
    db.session.commit()

    return jsonify(_serialize_opportunity_admin(opp))

@app.route("/admin/opportunities/<int:opportunity_id>/archive", methods=["POST"])

def admin_archive_opportunity(opportunity_id):
    """Admin-side archive - broader than the org's own self-service
    archive route (which only allows published/expired); admins can
    also archive an approved-but-not-yet-published listing."""
    opp = db.session.get(Opportunity, opportunity_id)
    if not opp:
        return jsonify({"error": "Opportunity not found"}), 404
    if opp.status not in ("approved", "published", "expired"):
        return jsonify({
            "error": f"Cannot archive an opportunity with status '{opp.status}'"
        }), 400

    opp.status = "archived"
    db.session.commit()

    return jsonify(_serialize_opportunity_admin(opp))

@app.route("/admin/opportunities/<int:opportunity_id>/remove", methods=["POST"])

def admin_remove_opportunity(opportunity_id):
    """
    Admin takedown for a policy violation or similar, from any
    non-removed state - broader than either self-service route. An
    optional reason is stored in the same rejection_reason column used
    by the reject flow (kept generic rather than adding a parallel
    column for what is, functionally, the same "why did an admin act
    on this" note).
    """
    acting_admin_id = session.get("user_id")

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp:
        return jsonify({"error": "Opportunity not found"}), 404
    if opp.status == "removed":
        return jsonify({"message": "Already removed"}), 200

    data = request.get_json(silent=True) or {}
    reason = data.get("reason")
    if reason is not None:
        reason = reason.strip()
        if len(reason) > 500:
            return jsonify({"error": "reason must be 500 characters or fewer"}), 400
        reason = reason or None

    opp.status = "removed"
    opp.rejection_reason = reason
    opp.reviewed_by = acting_admin_id
    opp.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_serialize_opportunity_admin(opp))
