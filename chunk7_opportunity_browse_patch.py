"""
Prepza - Chunk 7 (Opportunities + Organisation portal), Step 6 patch.

Adds student-facing browse routes + a save/bookmark feature (the
frontend already has bookmark/saveOpportunity references expecting
this):

  - class SavedOpportunity(db.Model)          - new table
  - _serialize_organisation_public()          - name/logo/website ONLY,
                                                 never contact_email/phone
  - _opportunity_publicly_visible_query()      - published + not expired +
                                                 org verified + org active
  - _get_active_promotions_map()               - read-only lookup, never
                                                 mutates Opportunity
  - GET    /opportunities                      - browse/search
  - GET    /opportunities/<id>                 - detail (increments
                                                 view_count)
  - POST   /opportunities/<id>/save            - bookmark
  - DELETE /opportunities/<id>/save            - remove bookmark
  - GET    /opportunities/saved                - list bookmarks

Idempotent: safe to re-run. Anchors structurally on the
`if __name__ == "__main__":` guard, preserves the file's existing
line-ending convention (CRLF/LF).

IMPORTANT: this patch adds a new SQLAlchemy model (SavedOpportunity),
so a NEW DB TABLE is required. After running this patch, also run
create_saved_opportunity_table.py (delivered alongside this file) to
create it - same two-step pattern used for the original Chunk 7
models (create_chunk7_tables.py).

Usage:
    cd ~/Desktop/prepza
    python chunk7_opportunity_browse_patch.py
    python create_saved_opportunity_table.py
"""

import sys

APP_PY = "app.py"

MARKER = "def browse_opportunities():"

REQUIRED_DEPENDENCIES = [
    "OPPORTUNITY_TYPES = (",
    "class Opportunity(db.Model):",
    "class OpportunityPromotion(db.Model):",
    "class Organisation(db.Model):",
    'if __name__ == "__main__":',
]

NEW_CODE = '''
# ---------- Opportunities (student-facing browse) (Step 6) ----------

class SavedOpportunity(db.Model):
    """A student bookmarking an Opportunity - same shape/reasoning as
    SavedLibraryMaterial."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("opportunity.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("user_id", "opportunity_id", name="uq_saved_opportunity_user_opp"),
    )


OPPORTUNITY_BROWSE_PAGE_SIZE = 20

# sponsored > featured > standard - lower rank number surfaces first.
_PROMOTION_TYPE_RANK = {"sponsored": 0, "featured": 1, "standard": 2}


def _serialize_organisation_public(org):
    """
    Public-safe organisation fields only. Deliberately excludes
    contact_email/contact_phone, which are org-management-only per the
    existing _serialize_organisation() - students browsing Opportunities
    must never see an org's contact details through this surface.
    """
    return {
        "id": org.id,
        "name": org.name,
        "logo_url": org.logo_url,
        "website": org.website,
    }


def _opportunity_publicly_visible_query():
    """
    Base query for opportunities a student is allowed to see: published,
    not yet expired, AND the owning organisation is still verified and
    active. The org re-check matters because an org can be deactivated
    or have its verification revoked AFTER an opportunity was already
    published - this keeps that opportunity from staying visible.
    """
    now = datetime.utcnow()
    return (
        Opportunity.query
        .join(Organisation, Opportunity.organisation_id == Organisation.id)
        .filter(
            Opportunity.status == "published",
            Opportunity.expiry_date > now,
            Organisation.verification_status == "verified",
            Organisation.is_active.is_(True),
        )
    )


def _get_active_promotions_map(opportunity_ids):
    """
    Returns {opportunity_id: promotion_type} for the highest-ranked
    currently-active, APPROVED promotion per opportunity (sponsored >
    featured > standard). Computed in Python against the already-small,
    already-filtered result set - same SQLAlchemy-version-safety
    reasoning as the admin moderation queue's priority sort elsewhere in
    this file, rather than a fragile SQL CASE/join. Read-only: never
    mutates Opportunity itself - OpportunityPromotion stays the single
    source of truth for promotion state, per the MVP spec.
    """
    if not opportunity_ids:
        return {}
    now = datetime.utcnow()
    rows = OpportunityPromotion.query.filter(
        OpportunityPromotion.opportunity_id.in_(opportunity_ids),
        OpportunityPromotion.approval_status == "approved",
        OpportunityPromotion.start_date <= now,
        OpportunityPromotion.end_date >= now,
    ).all()
    best = {}
    for r in rows:
        rank = _PROMOTION_TYPE_RANK.get(r.promotion_type, 99)
        current = best.get(r.opportunity_id)
        if current is None or rank < current[0]:
            best[r.opportunity_id] = (rank, r.promotion_type)
    return {oid: promo_type for oid, (rank, promo_type) in best.items()}


def _serialize_opportunity_public(opp, promotion_type=None, viewer_saved=None):
    org = db.session.get(Organisation, opp.organisation_id)
    result = {
        "id": opp.id,
        "title": opp.title,
        "description": opp.description,
        "opportunity_type": opp.opportunity_type,
        "location": opp.location,
        "is_remote": opp.is_remote,
        "application_url": opp.application_url,
        "application_instructions": opp.application_instructions,
        "application_deadline": opp.application_deadline.isoformat() if opp.application_deadline else None,
        "expiry_date": opp.expiry_date.isoformat() if opp.expiry_date else None,
        "published_at": opp.published_at.isoformat() if opp.published_at else None,
        "view_count": opp.view_count,
        "organisation": _serialize_organisation_public(org) if org else None,
        "promotion_type": promotion_type,
    }
    if viewer_saved is not None:
        result["saved"] = viewer_saved
    return result


@app.route("/opportunities")
def browse_opportunities():
    """
    Browse/search publicly visible opportunities. Login required, same
    convention as /library and /groups (session-gated, not tied to the
    viewer's own year/semester - any student can browse any opportunity).

    Query params (all optional):
      q               - substring match against title
      opportunity_type - job | internship | scholarship | competition |
                          volunteering | event | other
      is_remote       - "true" or "false"
      page            - 1-indexed, 20 per page

    Currently-active promotions (sponsored > featured > standard) sort
    to the top; newest-first within each tier and among unpromoted
    listings.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    query = _opportunity_publicly_visible_query()

    q = (request.args.get("q") or "").strip()
    if q:
        query = query.filter(Opportunity.title.ilike(f"%{q}%"))

    opportunity_type = request.args.get("opportunity_type")
    if opportunity_type:
        if opportunity_type not in OPPORTUNITY_TYPES:
            return jsonify({
                "error": "opportunity_type must be one of: " + ", ".join(OPPORTUNITY_TYPES)
            }), 400
        query = query.filter(Opportunity.opportunity_type == opportunity_type)

    is_remote_param = request.args.get("is_remote")
    if is_remote_param is not None:
        query = query.filter(Opportunity.is_remote.is_(is_remote_param.strip().lower() == "true"))

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = OPPORTUNITY_BROWSE_PAGE_SIZE

    # Promotion-aware ordering needs the full matching set sorted before
    # pagination, so this is done in Python rather than SQL OFFSET/LIMIT -
    # same tradeoff as the admin content-reports priority sort. Volume
    # here is bounded by "currently published, unexpired opportunities",
    # not the whole table, so this stays cheap.
    all_matching = query.order_by(Opportunity.created_at.desc()).all()
    opportunity_ids = [o.id for o in all_matching]
    promo_map = _get_active_promotions_map(opportunity_ids)
    all_matching.sort(key=lambda o: _PROMOTION_TYPE_RANK.get(promo_map.get(o.id), 99))

    page_items = all_matching[(page - 1) * per_page: page * per_page]

    saved_ids = set()
    if page_items:
        saved_rows = SavedOpportunity.query.filter(
            SavedOpportunity.user_id == user_id,
            SavedOpportunity.opportunity_id.in_([o.id for o in page_items]),
        ).all()
        saved_ids = {r.opportunity_id for r in saved_rows}

    return jsonify({
        "page": page,
        "opportunities": [
            _serialize_opportunity_public(
                o, promotion_type=promo_map.get(o.id), viewer_saved=(o.id in saved_ids)
            )
            for o in page_items
        ],
    })


@app.route("/opportunities/<int:opportunity_id>")
def get_opportunity_public(opportunity_id):
    """
    Single opportunity detail. 404s (not 403) if the opportunity isn't
    currently publicly visible, hiding existence - same pattern as
    get_group()/get_organisation(). Increments view_count unconditionally
    on every hit, matching the existing LibraryPublication.view_count
    convention elsewhere in this file (a display/analytics counter, not
    a security- or payout-sensitive one, so no per-user cap is needed).
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    opp = _opportunity_publicly_visible_query().filter(Opportunity.id == opportunity_id).first()
    if not opp:
        return jsonify({"error": "Opportunity not found"}), 404

    opp.view_count = (opp.view_count or 0) + 1
    db.session.commit()

    promo_map = _get_active_promotions_map([opp.id])
    saved = SavedOpportunity.query.filter_by(user_id=user_id, opportunity_id=opp.id).first() is not None

    return jsonify(_serialize_opportunity_public(
        opp, promotion_type=promo_map.get(opp.id), viewer_saved=saved
    ))


@app.route("/opportunities/<int:opportunity_id>/save", methods=["POST"])
@require_csrf
def save_opportunity(opportunity_id):
    """
    Bookmarks a publicly visible opportunity. Idempotent from the
    caller's perspective - saving an already-saved item just returns
    success, same pattern as save_library_item(). Only allows saving
    currently-visible opportunities (published/unexpired/org in good
    standing) - same gate as the detail route.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    opp = _opportunity_publicly_visible_query().filter(Opportunity.id == opportunity_id).first()
    if not opp:
        return jsonify({"error": "Opportunity not found"}), 404

    existing = SavedOpportunity.query.filter_by(user_id=user_id, opportunity_id=opportunity_id).first()
    if existing:
        return jsonify({"message": "Already saved"}), 200

    db.session.add(SavedOpportunity(user_id=user_id, opportunity_id=opportunity_id))
    db.session.commit()

    return jsonify({"message": "Saved"}), 201


@app.route("/opportunities/<int:opportunity_id>/save", methods=["DELETE"])
@require_csrf
def unsave_opportunity(opportunity_id):
    """
    Removes a bookmark. Deliberately NOT gated on current visibility -
    a student must always be able to remove their own bookmark, even for
    an opportunity that has since expired/been withdrawn/had its org
    deactivated, same reasoning as unsave_library_item().
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    existing = SavedOpportunity.query.filter_by(user_id=user_id, opportunity_id=opportunity_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()

    return jsonify({"message": "Removed" if existing else "Not saved"})


@app.route("/opportunities/saved")
def list_saved_opportunities():
    """
    Lists the logged-in student's saved opportunities. Skips any saved
    row whose opportunity is no longer publicly visible (expired,
    withdrawn, org deactivated) rather than erroring - same pattern as
    list_saved_library_items().
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    saved_rows = (
        SavedOpportunity.query.filter_by(user_id=user_id)
        .order_by(SavedOpportunity.created_at.desc())
        .all()
    )

    now = datetime.utcnow()
    result = []
    opportunity_ids = [r.opportunity_id for r in saved_rows]
    promo_map = _get_active_promotions_map(opportunity_ids)
    for row in saved_rows:
        opp = db.session.get(Opportunity, row.opportunity_id)
        if not opp or opp.status != "published" or opp.expiry_date <= now:
            continue
        org = db.session.get(Organisation, opp.organisation_id)
        if not org or org.verification_status != "verified" or not org.is_active:
            continue
        result.append(_serialize_opportunity_public(
            opp, promotion_type=promo_map.get(opp.id), viewer_saved=True
        ))

    return jsonify({"saved": result})


'''


def main():
    with open(APP_PY, "rb") as f:
        raw = f.read()

    uses_crlf = b"\r\n" in raw
    text = raw.decode("utf-8")

    if MARKER in text:
        print("Already applied - browse_opportunities found in app.py. Nothing to do.")
        return 0

    missing = [dep for dep in REQUIRED_DEPENDENCIES if dep not in text]
    if missing:
        print("ERROR: required dependency not found in app.py - cannot safely patch:")
        for m in missing:
            print(f"  - {m}")
        print("This usually means app.py has changed shape since this patch was written.")
        return 1

    anchor = 'if __name__ == "__main__":'
    idx = text.rfind(anchor)
    if idx == -1:
        print("ERROR: could not locate the __main__ guard anchor.")
        return 1

    block = NEW_CODE
    if uses_crlf:
        block = block.replace("\r\n", "\n").replace("\n", "\r\n")

    patched = text[:idx] + block.lstrip("\r\n") + ("\r\n" if uses_crlf else "\n") + text[idx:]

    with open(APP_PY, "wb") as f:
        f.write(patched.encode("utf-8"))

    print("Patched app.py successfully.")
    print("Added: SavedOpportunity model + routes:")
    print("  GET    /opportunities")
    print("  GET    /opportunities/<id>")
    print("  POST   /opportunities/<id>/save")
    print("  DELETE /opportunities/<id>/save")
    print("  GET    /opportunities/saved")
    print()
    print("NEXT STEP: run create_saved_opportunity_table.py to create the new table.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
