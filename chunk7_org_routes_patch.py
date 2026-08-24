"""
Chunk 7 patch 3/N: Organisation account routes + admin verification queue.

Adds:
  POST   /organisations                          create org, creator becomes 'owner'
  GET    /organisations/mine                      orgs the caller belongs to
  GET    /organisations/<id>                      profile (members + admin only)
  PATCH  /organisations/<id>                       edit profile (owner only)
  GET    /admin/organisations                     list all, ?verification_status= filter
  POST   /admin/organisations/<id>/verify          admin-only
  POST   /admin/organisations/<id>/reject          admin-only, reason required
  PATCH  /admin/organisations/<id>                 admin-only, toggles is_active

Anchoring strategy: structural, same idea as chunk7_models_patch.py.
Finds the literal line "if __name__ == \"__main__\":" (the true end of
the file) and inserts the new section immediately before it. This is
deliberately NOT anchored to any other chunk's code, so it survives
whatever else has landed in app.py in the meantime.

Safe to re-run: checks whether create_organisation already exists
before doing anything.

Usage:
    cd ~/Desktop/prepza
    python chunk7_org_routes_patch.py
"""

APP_PY = "app.py"

MAIN_GUARD_LINE = 'if __name__ == "__main__":'

NEW_ROUTES_TEMPLATE = '''# ---------- Organisations (Opportunities + Organisation portal) ----------

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


@app.route("/organisations", methods=["POST"])
@require_csrf
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


@app.route("/organisations/mine")
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


@app.route("/organisations/<int:organisation_id>")
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


@app.route("/organisations/<int:organisation_id>", methods=["PATCH"])
@require_csrf
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
@require_admin
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
@require_csrf
@require_admin
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
@require_csrf
@require_admin
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
@require_csrf
@require_admin
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


'''


def main():
    with open(APP_PY, "rb") as f:
        raw = f.read()

    uses_crlf = b"\r\n" in raw
    text = raw.decode("utf-8")

    if "def create_organisation():" in text:
        print("Already applied - create_organisation route found. Nothing to do.")
        return

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

    assert "class Organisation(db.Model):" in text, (
        "Organisation model not found - run chunk7_models_patch.py first."
    )

    new_block = NEW_ROUTES_TEMPLATE
    if uses_crlf:
        new_block = new_block.replace("\n", "\r\n")

    lines.insert(guard_idx, new_block)
    new_text = "".join(lines)

    assert "def create_organisation():" in new_text
    assert "def admin_verify_organisation(organisation_id):" in new_text
    assert "def admin_update_organisation(organisation_id):" in new_text

    with open(APP_PY, "wb") as f:
        f.write(new_text.encode("utf-8"))

    print("Patched app.py: added Organisation account routes + admin verification queue.")
    print("Routes added: POST /organisations, GET /organisations/mine, "
          "GET/PATCH /organisations/<id>, GET /admin/organisations, "
          "POST /admin/organisations/<id>/verify, POST .../reject, PATCH /admin/organisations/<id>.")


if __name__ == "__main__":
    main()
