"""Reconciled admin routes restored from the last complete admin runtime."""
import app as _app
# The module is imported at the end of app.py, after the current application
# globals and modular runtimes have been initialized.
globals().update({k:getattr(_app,k) for k in dir(_app) if not k.startswith("__")})

ORGANISATION_NAME_MAX = 150

ORGANISATION_DESCRIPTION_MAX = 1000

ORGANISATION_WEBSITE_MAX = 500

ORGANISATION_LOGO_URL_MAX = 500

ORGANISATION_CONTACT_PHONE_MAX = 20

def _serialize_organisation(org, membership=None):
    return {
        "id": org.id,
        "name": org.name,
        "description": org.description,
        "website": org.website,
        "logo_url": org.logo_url,
        "contact_email": org.contact_email,
        "contact_phone": org.contact_phone,
        "verification_status": org.verification_status,
        "verification_notes": org.verification_notes,
        "is_active": org.is_active,
        "created_by": org.created_by,
        "created_at": org.created_at.isoformat() if org.created_at else None,
        "updated_at": org.updated_at.isoformat() if org.updated_at else None,
        "is_member": membership is not None,
        "role": membership.role if membership else None,
    }

def _validate_organisation_fields(data, partial=False):
    """
    Shared validation for create + update. Returns (fields, error_response)
    - fields is a dict of validated values to apply, error_response is
    (jsonify(...), status) or None. In partial mode, a field is only
    validated/included if present in data (PATCH semantics); in
    non-partial mode name/contact_email are always required (POST semantics).
    """
    fields = {}

    if not partial or "name" in data:
        name = (data.get("name") or "").strip()
        if not name or len(name) > ORGANISATION_NAME_MAX:
            return None, (jsonify({
                "error": f"name is required and must be {ORGANISATION_NAME_MAX} characters or fewer"
            }), 400)
        fields["name"] = name

    if not partial or "contact_email" in data:
        contact_email = (data.get("contact_email") or "").strip().lower()
        if not contact_email or not EMAIL_REGEX.match(contact_email):
            return None, (jsonify({"error": "A valid contact_email is required"}), 400)
        fields["contact_email"] = contact_email

    if "description" in data:
        description = data.get("description")
        if description is not None:
            if not isinstance(description, str):
                return None, (jsonify({"error": "description must be a string"}), 400)
            description = description.strip() or None
            if description and len(description) > ORGANISATION_DESCRIPTION_MAX:
                return None, (jsonify({
                    "error": f"description must be {ORGANISATION_DESCRIPTION_MAX} characters or fewer"
                }), 400)
        fields["description"] = description

    if "website" in data:
        website = data.get("website")
        if website is not None:
            if not isinstance(website, str):
                return None, (jsonify({"error": "website must be a string"}), 400)
            website = website.strip() or None
            if website and len(website) > ORGANISATION_WEBSITE_MAX:
                return None, (jsonify({
                    "error": f"website must be {ORGANISATION_WEBSITE_MAX} characters or fewer"
                }), 400)
        fields["website"] = website

    if "logo_url" in data:
        logo_url = data.get("logo_url")
        if logo_url is not None:
            if not isinstance(logo_url, str):
                return None, (jsonify({"error": "logo_url must be a string"}), 400)
            logo_url = logo_url.strip() or None
            if logo_url and len(logo_url) > ORGANISATION_LOGO_URL_MAX:
                return None, (jsonify({
                    "error": f"logo_url must be {ORGANISATION_LOGO_URL_MAX} characters or fewer"
                }), 400)
        fields["logo_url"] = logo_url

    if "contact_phone" in data:
        contact_phone = data.get("contact_phone")
        if contact_phone is not None:
            if not isinstance(contact_phone, str):
                return None, (jsonify({"error": "contact_phone must be a string"}), 400)
            contact_phone = contact_phone.strip() or None
            if contact_phone and len(contact_phone) > ORGANISATION_CONTACT_PHONE_MAX:
                return None, (jsonify({
                    "error": f"contact_phone must be {ORGANISATION_CONTACT_PHONE_MAX} characters or fewer"
                }), 400)
        fields["contact_phone"] = contact_phone

    return fields, None

def create_organisation():
    """
    Registers a new Organisation and makes the creator its 'owner'.
    New organisations start unverified (verification_status='pending') -
    they can be staffed and edited immediately, but their opportunities
    cannot be published until an admin verifies them (enforced in the
    opportunities routes patch).
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    fields, error = _validate_organisation_fields(data, partial=False)
    if error:
        return error

    org = Organisation(created_by=user_id, **fields)
    db.session.add(org)
    db.session.flush()  # assign org.id before the membership row references it

    membership = OrganisationMember(organisation_id=org.id, user_id=user_id, role="owner")
    db.session.add(membership)
    db.session.commit()

    return jsonify(_serialize_organisation(org, membership)), 201

def my_organisations():
    """Lists every Organisation the caller is a member of, any role."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    memberships = OrganisationMember.query.filter_by(user_id=user_id).all()
    result = []
    for m in memberships:
        org = db.session.get(Organisation, m.organisation_id)
        if not org:
            continue
        result.append(_serialize_organisation(org, m))

    return jsonify({"organisations": result})

def get_organisation(organisation_id):
    """
    Full org profile - members and admins only. Non-members get a 404
    (not a 403) so this can't be used to enumerate which organisations
    exist or probe their contact details.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    membership = OrganisationMember.query.filter_by(
        organisation_id=organisation_id, user_id=user_id
    ).first()

    viewer = db.session.get(User, user_id)
    is_admin = bool(viewer and viewer.is_admin)

    if not membership and not is_admin:
        return jsonify({"error": "Organisation not found"}), 404

    return jsonify(_serialize_organisation(org, membership))

def update_organisation(organisation_id):
    """
    Edits an org's own profile. Owner-only - per OrganisationMember's
    role split, 'manager' can submit/edit opportunities but does not
    manage the organisation account itself.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    membership = OrganisationMember.query.filter_by(
        organisation_id=organisation_id, user_id=user_id
    ).first()
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404
    if membership.role != "owner":
        return jsonify({"error": "Only the organisation owner can edit its profile"}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    fields, error = _validate_organisation_fields(data, partial=True)
    if error:
        return error

    for key, value in fields.items():
        setattr(org, key, value)
    db.session.commit()

    return jsonify(_serialize_organisation(org, membership))

@app.route("/admin/organisations")

def admin_list_organisations():
    """
    Lists organisations for the admin dashboard, optionally filtered by
    verification_status. Oldest-first, same "review queue" ordering as
    admin_library_queue - whether or not a status filter is applied.
    """
    status_filter = request.args.get("verification_status")
    query = Organisation.query
    if status_filter:
        if status_filter not in ORGANISATION_VERIFICATION_STATUSES:
            return jsonify({
                "error": "verification_status must be one of: " + ", ".join(ORGANISATION_VERIFICATION_STATUSES)
            }), 400
        query = query.filter_by(verification_status=status_filter)

    orgs = query.order_by(Organisation.created_at.asc()).all()

    result = []
    for org in orgs:
        owner_membership = OrganisationMember.query.filter_by(
            organisation_id=org.id, role="owner"
        ).first()
        owner_user = db.session.get(User, owner_membership.user_id) if owner_membership else None
        entry = _serialize_organisation(org)
        entry["owner_email"] = owner_user.email if owner_user else None
        result.append(entry)

    return jsonify({"organisations": result})

@app.route("/admin/organisations/<int:organisation_id>/verify", methods=["POST"])

def admin_verify_organisation(organisation_id):
    """Verifies a pending or previously-rejected organisation."""
    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404
    if org.verification_status == "verified":
        return jsonify({"error": "Organisation is already verified"}), 400

    org.verification_status = "verified"
    org.verification_notes = None
    db.session.commit()

    return jsonify(_serialize_organisation(org))

@app.route("/admin/organisations/<int:organisation_id>/reject", methods=["POST"])

def admin_reject_organisation(organisation_id):
    """
    Rejects a pending organisation with a required reason. Refuses to
    reject an already-verified org - revoking a verified org's standing
    is a separate action (the is_active kill-switch below), not a
    verification-flow rejection.
    """
    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404
    if org.verification_status == "verified":
        return jsonify({
            "error": "Cannot reject an already-verified organisation - deactivate it instead"
        }), 400

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason or len(reason) > 500:
        return jsonify({"error": "reason is required and must be 500 characters or fewer"}), 400

    org.verification_status = "rejected"
    org.verification_notes = reason
    db.session.commit()

    return jsonify(_serialize_organisation(org))

@app.route("/admin/organisations/<int:organisation_id>", methods=["PATCH"])

def admin_update_organisation(organisation_id):
    """Admin kill-switch: activate/deactivate an organisation. Deactivating
    hides its opportunities without deleting anything (enforced in the
    opportunities routes patch)."""
    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    if "is_active" in data:
        is_active = data["is_active"]
        if not isinstance(is_active, bool):
            return jsonify({"error": "is_active must be true or false"}), 400
        org.is_active = is_active

    db.session.commit()

    return jsonify(_serialize_organisation(org))


# ---------- Organisation staff management ----------
# Lets an org 'owner' invite/remove 'manager' staff. Deliberately does NOT
# support transferring ownership or promoting a manager to owner - every
# Organisation has exactly one owner (the creator, set at POST
# /organisations time) and that never changes here, same "no speculative
# building" tradeoff as elsewhere in this file. A manager can submit/edit
# opportunities (per the existing OrganisationMember role split) but has
# no say over org staffing itself.

def _serialize_org_member(membership):
    user = db.session.get(User, membership.user_id)
    return {
        "user_id": membership.user_id,
        "email": user.email if user else None,
        "display_name": _display_name(user) if user else "Deleted user",
        "role": membership.role,
        "joined_at": membership.joined_at.isoformat() if membership.joined_at else None,
    }

def list_organisation_members(organisation_id):
    """Any member (owner or manager) can view the staff list. Non-members
    get a 404, same "don't confirm existence" pattern as get_organisation()."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    members = (
        OrganisationMember.query.filter_by(organisation_id=organisation_id)
        .order_by(OrganisationMember.joined_at.asc())
        .all()
    )
    members.sort(key=lambda m: 0 if m.role == "owner" else 1)

    return jsonify({"members": [_serialize_org_member(m) for m in members]})

def add_organisation_member(organisation_id):
    """
    Owner-only: invites an existing Prepza user as a 'manager'. Takes a
    user_id (not an email) - same "search then add" pattern as group
    creation's member_user_ids, resolved client-side via the existing
    GET /users/search picker rather than an email-invite flow, since
    every staffer must already have a Prepza account to sign in as.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    membership = _get_org_membership(organisation_id, user_id)
    if not membership or membership.role != "owner":
        return jsonify({"error": "Only the organisation owner can add staff"}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    target_user_id = data.get("user_id")
    if not isinstance(target_user_id, int) or isinstance(target_user_id, bool):
        return jsonify({"error": "user_id is required"}), 400
    if target_user_id == user_id:
        return jsonify({"error": "You're already the owner of this organisation"}), 400

    target_user = db.session.get(User, target_user_id)
    if not target_user or target_user.is_suspended:
        return jsonify({"error": "User not found"}), 404

    existing = OrganisationMember.query.filter_by(
        organisation_id=organisation_id, user_id=target_user_id
    ).first()
    if existing:
        return jsonify({"message": "Already staff", "member": _serialize_org_member(existing)}), 200

    new_member = OrganisationMember(organisation_id=organisation_id, user_id=target_user_id, role="manager")
    db.session.add(new_member)
    db.session.commit()

    return jsonify(_serialize_org_member(new_member)), 201

def remove_organisation_member(organisation_id, target_user_id):
    """
    Owner-only removal of a manager. Refuses to remove the owner (there's
    no ownership-transfer flow, so removing the owner would strand the
    org with no one able to manage staff or edit its profile) and refuses
    self-removal for the same reason.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    org = db.session.get(Organisation, organisation_id)
    if not org:
        return jsonify({"error": "Organisation not found"}), 404

    membership = _get_org_membership(organisation_id, user_id)
    if not membership or membership.role != "owner":
        return jsonify({"error": "Only the organisation owner can remove staff"}), 403

    if target_user_id == user_id:
        return jsonify({"error": "The owner can't remove themselves"}), 400

    target = OrganisationMember.query.filter_by(
        organisation_id=organisation_id, user_id=target_user_id
    ).first()
    if not target:
        return jsonify({"error": "Staff member not found"}), 404
    if target.role == "owner":
        return jsonify({"error": "Can't remove the organisation owner"}), 400

    db.session.delete(target)
    db.session.commit()

    return jsonify({"message": "Staff member removed"})


# ---------- Opportunities (organisation-side CRUD) ----------

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

@app.route("/organisations/<int:organisation_id>/opportunities", methods=["POST"])\n@require_csrf\ndef create_opportunity(organisation_id):
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

@app.route("/organisations/<int:organisation_id>/opportunities")\ndef list_org_opportunities(organisation_id):
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

@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>")\ndef get_org_opportunity(organisation_id, opportunity_id):
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

@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>", methods=["PATCH"])\n@require_csrf\ndef update_opportunity(organisation_id, opportunity_id):
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

@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>/submit", methods=["POST"])\n@require_csrf\ndef submit_opportunity(organisation_id, opportunity_id):
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

@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>/archive", methods=["POST"])\n@require_csrf\ndef archive_opportunity(organisation_id, opportunity_id):
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

@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>", methods=["DELETE"])\n@require_csrf\ndef withdraw_opportunity(organisation_id, opportunity_id):
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
