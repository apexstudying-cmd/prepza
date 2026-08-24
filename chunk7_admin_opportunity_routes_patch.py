"""
Chunk 7 patch 5a/N: admin review routes for the Opportunity lifecycle.

Adds:
  GET   /admin/opportunities                    review queue, ?status= filter
  POST  /admin/opportunities/<id>/approve        pending_review -> approved
  POST  /admin/opportunities/<id>/reject         pending_review -> rejected, reason required
  POST  /admin/opportunities/<id>/publish        approved -> published
  POST  /admin/opportunities/<id>/archive        admin-side archive (broader than the org's
                                                  own self-service archive route - admin can
                                                  archive from approved/published/expired)
  POST  /admin/opportunities/<id>/remove         takedown from any non-removed state

Approve/publish both re-check the organisation is still verified AND
active at the moment of the action - an org's standing can change
between submission and review, and this must never be trusted stale.

Reuses the existing `rejection_reason` column as a general free-text
admin note for both reject and remove actions (documented inline),
rather than adding a new column for what is effectively the same
"why did an admin act on this" concept.

Anchoring strategy: same as the rest of chunk 7 - inserts right before
the literal "if __name__ == \"__main__\":" line.

Safe to re-run: checks whether admin_list_opportunities already exists
before doing anything.

Usage:
    cd ~/Desktop/prepza
    python chunk7_admin_opportunity_routes_patch.py
"""

APP_PY = "app.py"

MAIN_GUARD_LINE = 'if __name__ == "__main__":'

NEW_ROUTES_TEMPLATE = '''# ---------- Admin: Opportunity review ----------

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
@require_admin
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
@require_csrf
@require_admin
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
@require_csrf
@require_admin
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
@require_csrf
@require_admin
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
@require_csrf
@require_admin
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
@require_csrf
@require_admin
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


'''


def main():
    with open(APP_PY, "rb") as f:
        raw = f.read()

    uses_crlf = b"\r\n" in raw
    text = raw.decode("utf-8")

    if "def admin_list_opportunities():" in text:
        print("Already applied - admin_list_opportunities route found. Nothing to do.")
        return

    assert "def _serialize_opportunity(opp):" in text, (
        "_serialize_opportunity helper not found - run chunk7_opportunity_routes_patch.py first."
    )

    lines = text.splitlines(keepends=True)
    guard_idx = None
    for i, line in enumerate(lines):
        if line.rstrip("\r\n") == MAIN_GUARD_LINE:
            guard_idx = i
            break
    assert guard_idx is not None, (
        'Could not find \'if __name__ == "__main__":\' in app.py. '
        "Aborting without modifying anything."
    )

    new_block = NEW_ROUTES_TEMPLATE
    if uses_crlf:
        new_block = new_block.replace("\n", "\r\n")

    lines.insert(guard_idx, new_block)
    new_text = "".join(lines)

    assert "def admin_list_opportunities():" in new_text
    assert "def admin_approve_opportunity(opportunity_id):" in new_text
    assert "def admin_remove_opportunity(opportunity_id):" in new_text

    with open(APP_PY, "wb") as f:
        f.write(new_text.encode("utf-8"))

    print("Patched app.py: added admin review routes for the Opportunity lifecycle.")
    print("Routes added: GET /admin/opportunities, POST .../approve, .../reject, "
          ".../publish, .../archive, .../remove.")


if __name__ == "__main__":
    main()
