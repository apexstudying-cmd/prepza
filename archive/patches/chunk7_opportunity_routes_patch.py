"""
Chunk 7 patch 4/N: Opportunity CRUD routes for organisation members.

Adds:
  POST    /organisations/<org_id>/opportunities                create (status=draft)
  GET     /organisations/<org_id>/opportunities                list own, ?status= filter
  GET     /organisations/<org_id>/opportunities/<id>            get one
  PATCH   /organisations/<org_id>/opportunities/<id>            edit (draft/rejected only)
  POST    /organisations/<org_id>/opportunities/<id>/submit     draft/rejected -> pending_review
  POST    /organisations/<org_id>/opportunities/<id>/archive    published/expired -> archived
  DELETE  /organisations/<org_id>/opportunities/<id>            withdraw (-> removed)

Approval/rejection/publishing by admins is a separate patch (step 5) -
this one only covers what an org can do to its own opportunity before
and after admin review, not the review itself.

Submission is gated on the organisation being verified AND active, and
on the opportunity's own deadline/expiry not already being in the past
- never trust the frontend clock for any of this.

Anchoring strategy: same as chunk7_org_routes_patch.py - inserts right
before the literal "if __name__ == \"__main__\":" line.

Safe to re-run: checks whether create_opportunity already exists before
doing anything.

Usage:
    cd ~/Desktop/prepza
    python chunk7_opportunity_routes_patch.py
"""

APP_PY = "app.py"

MAIN_GUARD_LINE = 'if __name__ == "__main__":'

NEW_ROUTES_TEMPLATE = '''# ---------- Opportunities (organisation-side CRUD) ----------

from datetime import timezone

OPPORTUNITY_TITLE_MAX = 200
OPPORTUNITY_DESCRIPTION_MAX = 5000
OPPORTUNITY_LOCATION_MAX = 200
OPPORTUNITY_APPLICATION_URL_MAX = 500
OPPORTUNITY_INSTRUCTIONS_MAX = 3000
OPPORTUNITY_EDITABLE_STATUSES = ("draft", "rejected")


def _get_org_membership(organisation_id, user_id):
    return OrganisationMember.query.filter_by(
        organisation_id=organisation_id, user_id=user_id
    ).first()


def _parse_iso_datetime(value):
    """
    Parses an ISO-8601 string into a naive UTC datetime (matching the
    naive datetime.utcnow() convention used throughout this file).
    Returns None if value is missing/invalid rather than raising -
    callers turn that into a 400.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _serialize_opportunity(opp):
    return {
        "id": opp.id,
        "organisation_id": opp.organisation_id,
        "created_by": opp.created_by,
        "title": opp.title,
        "description": opp.description,
        "opportunity_type": opp.opportunity_type,
        "location": opp.location,
        "is_remote": opp.is_remote,
        "application_url": opp.application_url,
        "application_instructions": opp.application_instructions,
        "application_deadline": opp.application_deadline.isoformat() if opp.application_deadline else None,
        "expiry_date": opp.expiry_date.isoformat() if opp.expiry_date else None,
        "status": opp.status,
        "rejection_reason": opp.rejection_reason,
        "submitted_at": opp.submitted_at.isoformat() if opp.submitted_at else None,
        "reviewed_at": opp.reviewed_at.isoformat() if opp.reviewed_at else None,
        "published_at": opp.published_at.isoformat() if opp.published_at else None,
        "view_count": opp.view_count,
        "created_at": opp.created_at.isoformat() if opp.created_at else None,
        "updated_at": opp.updated_at.isoformat() if opp.updated_at else None,
    }


def _validate_opportunity_fields(data, partial=False):
    """
    Shared validation for create + update. Returns (fields, error_response).
    Does NOT validate the deadline/expiry cross-field ordering - callers
    do that themselves once they know the row's effective final values
    (needed because PATCH may only change one of the two dates).
    """
    fields = {}

    if not partial or "title" in data:
        title = (data.get("title") or "").strip()
        if not title or len(title) > OPPORTUNITY_TITLE_MAX:
            return None, (jsonify({
                "error": f"title is required and must be {OPPORTUNITY_TITLE_MAX} characters or fewer"
            }), 400)
        fields["title"] = title

    if not partial or "description" in data:
        description = (data.get("description") or "").strip()
        if not description or len(description) > OPPORTUNITY_DESCRIPTION_MAX:
            return None, (jsonify({
                "error": f"description is required and must be {OPPORTUNITY_DESCRIPTION_MAX} characters or fewer"
            }), 400)
        fields["description"] = description

    if not partial or "opportunity_type" in data:
        opportunity_type = (data.get("opportunity_type") or "").strip().lower()
        if opportunity_type not in OPPORTUNITY_TYPES:
            return None, (jsonify({
                "error": "opportunity_type must be one of: " + ", ".join(OPPORTUNITY_TYPES)
            }), 400)
        fields["opportunity_type"] = opportunity_type

    if "location" in data:
        location = data.get("location")
        if location is not None:
            if not isinstance(location, str):
                return None, (jsonify({"error": "location must be a string"}), 400)
            location = location.strip() or None
            if location and len(location) > OPPORTUNITY_LOCATION_MAX:
                return None, (jsonify({
                    "error": f"location must be {OPPORTUNITY_LOCATION_MAX} characters or fewer"
                }), 400)
        fields["location"] = location

    if "is_remote" in data:
        is_remote = data.get("is_remote")
        if not isinstance(is_remote, bool):
            return None, (jsonify({"error": "is_remote must be true or false"}), 400)
        fields["is_remote"] = is_remote

    if "application_url" in data:
        application_url = data.get("application_url")
        if application_url is not None:
            if not isinstance(application_url, str):
                return None, (jsonify({"error": "application_url must be a string"}), 400)
            application_url = application_url.strip() or None
            if application_url and len(application_url) > OPPORTUNITY_APPLICATION_URL_MAX:
                return None, (jsonify({
                    "error": f"application_url must be {OPPORTUNITY_APPLICATION_URL_MAX} characters or fewer"
                }), 400)
        fields["application_url"] = application_url

    if "application_instructions" in data:
        instructions = data.get("application_instructions")
        if instructions is not None:
            if not isinstance(instructions, str):
                return None, (jsonify({"error": "application_instructions must be a string"}), 400)
            instructions = instructions.strip() or None
            if instructions and len(instructions) > OPPORTUNITY_INSTRUCTIONS_MAX:
                return None, (jsonify({
                    "error": f"application_instructions must be {OPPORTUNITY_INSTRUCTIONS_MAX} characters or fewer"
                }), 400)
        fields["application_instructions"] = instructions

    if not partial or "application_deadline" in data:
        deadline = _parse_iso_datetime(data.get("application_deadline"))
        if not deadline:
            return None, (jsonify({
                "error": "application_deadline is required and must be a valid ISO datetime"
            }), 400)
        fields["application_deadline"] = deadline

    if not partial or "expiry_date" in data:
        expiry = _parse_iso_datetime(data.get("expiry_date"))
        if not expiry:
            return None, (jsonify({
                "error": "expiry_date is required and must be a valid ISO datetime"
            }), 400)
        fields["expiry_date"] = expiry

    return fields, None


@app.route("/organisations/<int:organisation_id>/opportunities", methods=["POST"])
@require_csrf
def create_opportunity(organisation_id):
    """
    Creates a new Opportunity in status='draft'. Allowed even if the
    organisation isn't verified yet - verification is only required to
    submit for review (see submit_opportunity below), not to draft one.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    fields, error = _validate_opportunity_fields(data, partial=False)
    if error:
        return error

    if fields["expiry_date"] <= fields["application_deadline"]:
        return jsonify({"error": "expiry_date must be after application_deadline"}), 400
    if fields["application_deadline"] <= datetime.utcnow():
        return jsonify({"error": "application_deadline must be in the future"}), 400

    opp = Opportunity(
        organisation_id=organisation_id, created_by=user_id, status="draft", **fields
    )
    db.session.add(opp)
    db.session.commit()

    return jsonify(_serialize_opportunity(opp)), 201


@app.route("/organisations/<int:organisation_id>/opportunities")
def list_org_opportunities(organisation_id):
    """Lists this org's own opportunities, any status. ?status= filters
    to one status (management view - not the public browse endpoint)."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    query = Opportunity.query.filter_by(organisation_id=organisation_id)

    status_filter = request.args.get("status")
    if status_filter:
        if status_filter not in OPPORTUNITY_STATUSES:
            return jsonify({
                "error": "status must be one of: " + ", ".join(OPPORTUNITY_STATUSES)
            }), 400
        query = query.filter_by(status=status_filter)

    opportunities = query.order_by(Opportunity.created_at.desc()).all()
    return jsonify({"opportunities": [_serialize_opportunity(o) for o in opportunities]})


@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>")
def get_org_opportunity(organisation_id, opportunity_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp or opp.organisation_id != organisation_id:
        return jsonify({"error": "Opportunity not found"}), 404

    return jsonify(_serialize_opportunity(opp))


@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>", methods=["PATCH"])
@require_csrf
def update_opportunity(organisation_id, opportunity_id):
    """
    Edits an opportunity. Only allowed while status is 'draft' or
    'rejected' - once it's in the review/published pipeline, the org
    can't silently change it out from under an approval; they'd need to
    withdraw and recreate, or (for rejected ones) fix it up here and
    resubmit via /submit.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp or opp.organisation_id != organisation_id:
        return jsonify({"error": "Opportunity not found"}), 404

    if opp.status not in OPPORTUNITY_EDITABLE_STATUSES:
        return jsonify({
            "error": f"Cannot edit an opportunity with status '{opp.status}' - "
                     f"only draft or rejected opportunities can be edited"
        }), 400

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    fields, error = _validate_opportunity_fields(data, partial=True)
    if error:
        return error

    effective_deadline = fields.get("application_deadline", opp.application_deadline)
    effective_expiry = fields.get("expiry_date", opp.expiry_date)
    if effective_expiry <= effective_deadline:
        return jsonify({"error": "expiry_date must be after application_deadline"}), 400

    for key, value in fields.items():
        setattr(opp, key, value)
    db.session.commit()

    return jsonify(_serialize_opportunity(opp))


@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>/submit", methods=["POST"])
@require_csrf
def submit_opportunity(organisation_id, opportunity_id):
    """
    Moves draft/rejected -> pending_review. Requires the organisation to
    be verified AND active (an unverified or deactivated org's postings
    never enter the admin review queue), and requires the opportunity's
    own dates to not already be in the past.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    if org.verification_status != "verified" or not org.is_active:
        return jsonify({
            "error": "Organisation must be verified and active before submitting opportunities for review"
        }), 400

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp or opp.organisation_id != organisation_id:
        return jsonify({"error": "Opportunity not found"}), 404

    if opp.status not in OPPORTUNITY_EDITABLE_STATUSES:
        return jsonify({
            "error": f"Cannot submit an opportunity with status '{opp.status}'"
        }), 400

    now = datetime.utcnow()
    if opp.application_deadline <= now or opp.expiry_date <= now:
        return jsonify({
            "error": "Cannot submit - application_deadline or expiry_date has already passed. "
                     "Update the dates first."
        }), 400

    opp.status = "pending_review"
    opp.submitted_at = now
    opp.rejection_reason = None
    db.session.commit()

    return jsonify(_serialize_opportunity(opp))


@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>/archive", methods=["POST"])
@require_csrf
def archive_opportunity(organisation_id, opportunity_id):
    """Org self-service archive - lets them retire a published or
    already-expired posting without waiting on an admin."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp or opp.organisation_id != organisation_id:
        return jsonify({"error": "Opportunity not found"}), 404

    if opp.status not in ("published", "expired"):
        return jsonify({
            "error": f"Cannot archive an opportunity with status '{opp.status}'"
        }), 400

    opp.status = "archived"
    db.session.commit()

    return jsonify(_serialize_opportunity(opp))


@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>", methods=["DELETE"])
@require_csrf
def withdraw_opportunity(organisation_id, opportunity_id):
    """Org withdraws its own opportunity at any point in its lifecycle
    (except if already removed). Soft-delete via status='removed', same
    pattern as Document.is_removed elsewhere in this file."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp or opp.organisation_id != organisation_id:
        return jsonify({"error": "Opportunity not found"}), 404

    if opp.status == "removed":
        return jsonify({"message": "Already removed"}), 200

    opp.status = "removed"
    db.session.commit()

    return jsonify({"message": "Opportunity withdrawn"})


'''


def main():
    with open(APP_PY, "rb") as f:
        raw = f.read()

    uses_crlf = b"\r\n" in raw
    text = raw.decode("utf-8")

    if "def create_opportunity(organisation_id):" in text:
        print("Already applied - create_opportunity route found. Nothing to do.")
        return

    assert "class Opportunity(db.Model):" in text, (
        "Opportunity model not found - run chunk7_models_patch.py first."
    )
    assert "def create_organisation():" in text, (
        "Organisation routes not found - run chunk7_org_routes_patch.py first."
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

    assert "def create_opportunity(organisation_id):" in new_text
    assert "def submit_opportunity(organisation_id, opportunity_id):" in new_text
    assert "def withdraw_opportunity(organisation_id, opportunity_id):" in new_text

    with open(APP_PY, "wb") as f:
        f.write(new_text.encode("utf-8"))

    print("Patched app.py: added Opportunity CRUD routes for organisation members.")
    print("Routes added: POST/GET /organisations/<id>/opportunities, "
          "GET/PATCH/DELETE .../opportunities/<id>, POST .../submit, POST .../archive.")


if __name__ == "__main__":
    main()
