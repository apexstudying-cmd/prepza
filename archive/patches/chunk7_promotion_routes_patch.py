"""
Prepza - Chunk 7 (Opportunities + Organisation portal), Step 5b patch.

Adds Opportunity Promotion routes:
  - get_promotion_prices() helper
  - POST /organisations/<org_id>/opportunities/<opp_id>/promotions
  - GET  /organisations/<org_id>/opportunities/<opp_id>/promotions
  - GET  /admin/opportunity-promotions
  - POST /admin/opportunity-promotions/<id>/approve
  - POST /admin/opportunity-promotions/<id>/reject

Idempotent: safe to re-run. Anchors structurally on the
`if __name__ == "__main__":` guard rather than on exact surrounding
text, and preserves whatever line-ending convention (CRLF/LF) the
file already uses.

Usage:
    cd ~/Desktop/prepza
    python chunk7_promotion_routes_patch.py
"""

import sys

APP_PY = "app.py"

MARKER = 'def request_opportunity_promotion(organisation_id, opportunity_id):'

REQUIRED_DEPENDENCIES = [
    'def _get_org_membership(',
    'def _parse_iso_datetime(',
    'class OpportunityPromotion(db.Model):',
    'if __name__ == "__main__":',
]

NEW_CODE = '''
# ---------- Opportunity Promotions (Step 5b) ----------

OPPORTUNITY_PROMOTION_EDITABLE_OPPORTUNITY_STATUSES = ("pending_review", "approved", "published")


def get_promotion_prices():
    """
    Returns a dict of promotion_type -> price (KES), sourced from
    SystemSetting rows (price_promotion_standard, price_promotion_featured,
    price_promotion_sponsored) - same pattern as get_plan_prices() /
    get_content_prices(). Missing or invalid settings fall back to the
    defaults below.
    """
    keys = ("price_promotion_standard", "price_promotion_featured", "price_promotion_sponsored")
    settings = {
        s.key: s.value
        for s in SystemSetting.query.filter(SystemSetting.key.in_(keys)).all()
    }

    def parse(key, default):
        try:
            return int(settings.get(key) or default)
        except (TypeError, ValueError):
            return default

    return {
        "standard": parse("price_promotion_standard", 0),
        "featured": parse("price_promotion_featured", 300),
        "sponsored": parse("price_promotion_sponsored", 800),
    }


def _serialize_opportunity_promotion(promo, include_context=False):
    result = {
        "id": promo.id,
        "opportunity_id": promo.opportunity_id,
        "organisation_id": promo.organisation_id,
        "promotion_type": promo.promotion_type,
        "start_date": promo.start_date.isoformat() if promo.start_date else None,
        "end_date": promo.end_date.isoformat() if promo.end_date else None,
        "price": promo.price,
        "payment_status": promo.payment_status,
        "approval_status": promo.approval_status,
        "reviewed_at": promo.reviewed_at.isoformat() if promo.reviewed_at else None,
        "created_at": promo.created_at.isoformat() if promo.created_at else None,
        "updated_at": promo.updated_at.isoformat() if promo.updated_at else None,
    }
    if include_context:
        opp = db.session.get(Opportunity, promo.opportunity_id)
        org = db.session.get(Organisation, promo.organisation_id)
        result["opportunity_title"] = opp.title if opp else None
        result["organisation_name"] = org.name if org else None
    return result


@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>/promotions", methods=["POST"])
@require_csrf
def request_opportunity_promotion(organisation_id, opportunity_id):
    """
    Requests a promotion campaign for one of the org's own opportunities.
    price is snapshotted at request time from admin-configurable
    SystemSetting pricing (see get_promotion_prices()) - same reasoning
    as Payment.amount. Deliberately does NOT touch payment_status here;
    actual payment collection/webhook wiring belongs to the Payments
    chunk, which hasn't wired into this yet - payment_status stays at
    its 'unpaid' default until that lands.
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

    if opp.status not in OPPORTUNITY_PROMOTION_EDITABLE_OPPORTUNITY_STATUSES:
        return jsonify({
            "error": f"Cannot promote an opportunity with status '{opp.status}'"
        }), 400

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    promotion_type = (data.get("promotion_type") or "").strip().lower()
    if promotion_type not in OPPORTUNITY_PROMOTION_TYPES:
        return jsonify({
            "error": "promotion_type must be one of: " + ", ".join(OPPORTUNITY_PROMOTION_TYPES)
        }), 400

    start_date = _parse_iso_datetime(data.get("start_date"))
    if not start_date:
        return jsonify({"error": "start_date is required and must be a valid ISO datetime"}), 400

    end_date = _parse_iso_datetime(data.get("end_date"))
    if not end_date:
        return jsonify({"error": "end_date is required and must be a valid ISO datetime"}), 400

    now = datetime.utcnow()
    if start_date < now:
        return jsonify({"error": "start_date cannot be in the past"}), 400
    if end_date <= start_date:
        return jsonify({"error": "end_date must be after start_date"}), 400
    if end_date > opp.expiry_date:
        return jsonify({"error": "end_date cannot be after the opportunity's own expiry_date"}), 400

    price = get_promotion_prices().get(promotion_type, 0)

    promo = OpportunityPromotion(
        opportunity_id=opportunity_id,
        organisation_id=organisation_id,
        promotion_type=promotion_type,
        start_date=start_date,
        end_date=end_date,
        price=price,
        payment_status="unpaid",
        approval_status="pending",
    )
    db.session.add(promo)
    db.session.commit()

    return jsonify(_serialize_opportunity_promotion(promo)), 201


@app.route("/organisations/<int:organisation_id>/opportunities/<int:opportunity_id>/promotions")
def list_opportunity_promotions(organisation_id, opportunity_id):
    """Lists the org's own promotion requests for one opportunity, any
    approval_status, newest first."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    membership = _get_org_membership(organisation_id, user_id)
    if not membership:
        return jsonify({"error": "Organisation not found"}), 404

    opp = db.session.get(Opportunity, opportunity_id)
    if not opp or opp.organisation_id != organisation_id:
        return jsonify({"error": "Opportunity not found"}), 404

    promotions = (
        OpportunityPromotion.query.filter_by(
            opportunity_id=opportunity_id, organisation_id=organisation_id
        )
        .order_by(OpportunityPromotion.created_at.desc())
        .all()
    )

    return jsonify({"promotions": [_serialize_opportunity_promotion(p) for p in promotions]})


@app.route("/admin/opportunity-promotions")
@require_admin
def admin_list_opportunity_promotions():
    """
    Admin queue for promotion requests. Defaults to pending only; pass
    approval_status=all to see approved/rejected ones too. Each row
    includes opportunity_title/organisation_name for admin readability.
    """
    status_filter = request.args.get("approval_status", "pending")
    if status_filter != "all" and status_filter not in OPPORTUNITY_PROMOTION_APPROVAL_STATUSES:
        return jsonify({
            "error": "approval_status must be 'all' or one of: " + ", ".join(OPPORTUNITY_PROMOTION_APPROVAL_STATUSES)
        }), 400

    query = OpportunityPromotion.query
    if status_filter != "all":
        query = query.filter_by(approval_status=status_filter)

    promotions = query.order_by(OpportunityPromotion.created_at.asc()).all()

    return jsonify({
        "promotions": [_serialize_opportunity_promotion(p, include_context=True) for p in promotions]
    })


@app.route("/admin/opportunity-promotions/<int:promotion_id>/approve", methods=["POST"])
@require_csrf
@require_admin
def admin_approve_opportunity_promotion(promotion_id):
    """
    Approves a pending promotion request. Deliberately does NOT check or
    change payment_status - real payment collection/webhook wiring
    belongs to the Payments chunk, which hasn't wired into this yet.
    Approval here means "this promotion is allowed to run", not "it has
    been paid for" - don't assume the two are the same thing.
    """
    acting_admin_id = session.get("user_id")

    promo = db.session.get(OpportunityPromotion, promotion_id)
    if not promo:
        return jsonify({"error": "Promotion request not found"}), 404
    if promo.approval_status != "pending":
        return jsonify({
            "error": f"Promotion request is not pending (approval_status: {promo.approval_status})"
        }), 400

    promo.approval_status = "approved"
    promo.reviewed_by = acting_admin_id
    promo.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_serialize_opportunity_promotion(promo))


@app.route("/admin/opportunity-promotions/<int:promotion_id>/reject", methods=["POST"])
@require_csrf
@require_admin
def admin_reject_opportunity_promotion(promotion_id):
    """Rejects a pending promotion request. Reason is optional (unlike
    Opportunity rejection) since promotions are a lower-stakes add-on,
    not a content moderation decision."""
    acting_admin_id = session.get("user_id")

    promo = db.session.get(OpportunityPromotion, promotion_id)
    if not promo:
        return jsonify({"error": "Promotion request not found"}), 404
    if promo.approval_status != "pending":
        return jsonify({
            "error": f"Promotion request is not pending (approval_status: {promo.approval_status})"
        }), 400

    promo.approval_status = "rejected"
    promo.reviewed_by = acting_admin_id
    promo.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify(_serialize_opportunity_promotion(promo))


'''


def main():
    with open(APP_PY, "rb") as f:
        raw = f.read()

    uses_crlf = b"\r\n" in raw
    text = raw.decode("utf-8")

    if MARKER in text:
        print("Already applied - promotion routes found in app.py. Nothing to do.")
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

    # Insert the new block immediately before the anchor line, normalizing
    # our block (written with \n) to the file's actual line ending.
    block = NEW_CODE
    if uses_crlf:
        block = block.replace("\r\n", "\n").replace("\n", "\r\n")

    patched = text[:idx] + block.lstrip("\r\n") + ("\r\n" if uses_crlf else "\n") + text[idx:]

    with open(APP_PY, "wb") as f:
        f.write(patched.encode("utf-8"))

    print("Patched app.py successfully.")
    print("Added routes:")
    print("  POST /organisations/<org_id>/opportunities/<opp_id>/promotions")
    print("  GET  /organisations/<org_id>/opportunities/<opp_id>/promotions")
    print("  GET  /admin/opportunity-promotions")
    print("  POST /admin/opportunity-promotions/<id>/approve")
    print("  POST /admin/opportunity-promotions/<id>/reject")
    return 0


if __name__ == "__main__":
    sys.exit(main())
