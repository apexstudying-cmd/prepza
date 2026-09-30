"""Reconciled admin routes restored from the last complete admin runtime."""
import app as _app
# The module is imported at the end of app.py, after the current application
# globals and modular runtimes have been initialized.
globals().update({k:getattr(_app,k) for k in dir(_app) if not k.startswith("__")})

@app.route("/admin/ambassadors")

def admin_list_ambassadors():
    """Lists ambassadors, optionally filtered by ?status= (pending |
    active | suspended | rejected). Newest applications first."""
    status_filter = request.args.get("status")

    query = Ambassador.query
    if status_filter:
        query = query.filter_by(status=status_filter)

    ambassadors = query.order_by(Ambassador.applied_at.desc()).all()

    result = []
    for a in ambassadors:
        user = db.session.get(User, a.user_id)
        result.append({
            "id": a.id,
            "user_id": a.user_id,
            "email": user.email if user else None,
            "display_name": _display_name(user) if user else None,
            "referral_code": a.referral_code,
            "status": a.status,
            "applied_at": a.applied_at.isoformat() if a.applied_at else None,
            "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
            "rejection_reason": a.rejection_reason,
        })

    return jsonify({"ambassadors": result})

@app.route("/admin/ambassadors/<int:ambassador_id>")

def admin_get_ambassador(ambassador_id):
    """
    Full detail view for one ambassador - their referral list with
    per-referral commission/void state, meant for the fraud-review
    pass before approving a payout (self-referral patterns, unusually
    fast conversions, etc. are all visible here per-referral).
    """
    ambassador = db.session.get(Ambassador, ambassador_id)
    if not ambassador:
        return jsonify({"error": "Ambassador not found"}), 404

    user = db.session.get(User, ambassador.user_id)
    referrals = (
        Referral.query.filter_by(ambassador_id=ambassador.id)
        .order_by(Referral.created_at.desc())
        .all()
    )

    referral_rows = []
    for r in referrals:
        referred_user = db.session.get(User, r.referred_user_id)
        referral_rows.append({
            "id": r.id,
            "referred_email": referred_user.email if referred_user else None,
            "status": r.status,
            "channel": r.channel,
            "converted": r.first_payment_id is not None,
            "commission_amount": r.commission_amount,
            "unlock_at": r.unlock_at.isoformat() if r.unlock_at else None,
            "voided": r.voided_at is not None,
            "void_reason": r.void_reason,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    converted = [r for r in referrals if r.first_payment_id and not r.voided_at]
    total_commission_awarded = sum((r.commission_amount or 0) for r in converted)
    total_paid = db.session.query(func.coalesce(func.sum(AmbassadorPayout.amount), 0)).filter(
        AmbassadorPayout.ambassador_id == ambassador.id, AmbassadorPayout.status == "paid",
    ).scalar()

    return jsonify({
        "id": ambassador.id,
        "user_id": ambassador.user_id,
        "email": user.email if user else None,
        "display_name": _display_name(user) if user else None,
        "referral_code": ambassador.referral_code,
        "status": ambassador.status,
        "applied_at": ambassador.applied_at.isoformat() if ambassador.applied_at else None,
        "reviewed_by": ambassador.reviewed_by,
        "reviewed_at": ambassador.reviewed_at.isoformat() if ambassador.reviewed_at else None,
        "rejection_reason": ambassador.rejection_reason,
        "referred_count": len(referrals),
        "paying_count": len(converted),
        "total_commission_awarded_kes": total_commission_awarded,
        "total_paid_kes": total_paid,
        "referrals": referral_rows,
    })

@app.route("/admin/ambassadors/<int:ambassador_id>/approve", methods=["POST"])

def admin_approve_ambassador(ambassador_id):
    acting_admin_id = session.get("user_id")

    ambassador = db.session.get(Ambassador, ambassador_id)
    if not ambassador:
        return jsonify({"error": "Ambassador not found"}), 404
    if ambassador.status != "pending":
        return jsonify({"error": f"Ambassador is not pending (status: {ambassador.status})"}), 400

    ambassador.status = "active"
    ambassador.reviewed_by = acting_admin_id
    ambassador.reviewed_at = datetime.utcnow()
    ambassador.rejection_reason = None
    db.session.commit()

    return jsonify({"id": ambassador.id, "status": ambassador.status})

@app.route("/admin/ambassadors/<int:ambassador_id>/reject", methods=["POST"])

def admin_reject_ambassador(ambassador_id):
    acting_admin_id = session.get("user_id")

    ambassador = db.session.get(Ambassador, ambassador_id)
    if not ambassador:
        return jsonify({"error": "Ambassador not found"}), 404
    if ambassador.status != "pending":
        return jsonify({"error": f"Ambassador is not pending (status: {ambassador.status})"}), 400

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason or len(reason) > 500:
        return jsonify({"error": "reason is required and must be 500 characters or fewer"}), 400

    ambassador.status = "rejected"
    ambassador.rejection_reason = reason
    ambassador.reviewed_by = acting_admin_id
    ambassador.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"id": ambassador.id, "status": ambassador.status})

@app.route("/admin/ambassadors/<int:ambassador_id>/suspend", methods=["POST"])

def admin_suspend_ambassador(ambassador_id):
    """
    Suspending does NOT touch existing Referral/commission rows or
    in-flight payouts - it only blocks new applications-worth of
    trust (dashboard access, new payout requests). Any pending payout
    still goes through the normal admin approve/reject flow.
    """
    acting_admin_id = session.get("user_id")

    ambassador = db.session.get(Ambassador, ambassador_id)
    if not ambassador:
        return jsonify({"error": "Ambassador not found"}), 404
    if ambassador.status != "active":
        return jsonify({"error": f"Only active ambassadors can be suspended (status: {ambassador.status})"}), 400

    ambassador.status = "suspended"
    ambassador.reviewed_by = acting_admin_id
    ambassador.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"id": ambassador.id, "status": ambassador.status})

@app.route("/admin/ambassadors/<int:ambassador_id>/reinstate", methods=["POST"])

def admin_reinstate_ambassador(ambassador_id):
    acting_admin_id = session.get("user_id")

    ambassador = db.session.get(Ambassador, ambassador_id)
    if not ambassador:
        return jsonify({"error": "Ambassador not found"}), 404
    if ambassador.status != "suspended":
        return jsonify({"error": f"Only suspended ambassadors can be reinstated (status: {ambassador.status})"}), 400

    ambassador.status = "active"
    ambassador.reviewed_by = acting_admin_id
    ambassador.reviewed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"id": ambassador.id, "status": ambassador.status})


# ---------- Admin: ambassador payouts (Chunk 9) ----------

@app.route("/admin/payouts")

def admin_list_ambassador_payouts():
    """Lists ambassador payout requests, optionally filtered by
    ?status= (pending | approved | rejected | paid)."""
    status_filter = request.args.get("status")

    query = AmbassadorPayout.query
    if status_filter:
        query = query.filter_by(status=status_filter)

    payouts = query.order_by(AmbassadorPayout.requested_at.desc()).all()

    result = []
    for p in payouts:
        ambassador = db.session.get(Ambassador, p.ambassador_id)
        user = db.session.get(User, ambassador.user_id) if ambassador else None
        result.append({
            "id": p.id,
            "ambassador_id": p.ambassador_id,
            "email": user.email if user else None,
            "amount": p.amount,
            "status": p.status,
            "payout_destination": p.payout_destination,
            "paystack_transfer_code": p.paystack_transfer_code,
            "requested_at": p.requested_at.isoformat() if p.requested_at else None,
            "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
            "rejection_reason": p.rejection_reason,
            "paid_at": p.paid_at.isoformat() if p.paid_at else None,
        })

    return jsonify({"payouts": result})

@app.route("/admin/payouts/<int:payout_id>/approve", methods=["POST"])

def admin_approve_ambassador_payout(payout_id):
    """
    Greenlights a payout request AND fires the actual Paystack transfer
    in the same action - approving IS sending, which is the fraud
    checkpoint you get instead of a separate "send" button. If the
    Paystack request fails, nothing is marked approved and the payout
    stays 'pending', so the admin can fix whatever's wrong (balance,
    recipient details) and retry the same click.

    In sandbox, test-mode transfers always auto-succeed - the payout may
    already be 'paid' by the time this returns. Once switching to live
    keys, a successful call here only means Paystack ACCEPTED the
    transfer for processing - the real outcome arrives later via
    /payment/paystack/webhook, or can be checked manually via
    /admin/payouts/<id>/sync-status.
    """
    acting_admin_id = session.get("user_id")

    payout = db.session.get(AmbassadorPayout, payout_id)
    if not payout:
        return jsonify({"error": "Payout not found"}), 404
    if payout.status != "pending":
        return jsonify({"error": f"Payout is not pending (status: {payout.status})"}), 400

    try:
        transfer_reference, transfer_status = initiate_paystack_transfer(payout)
    except Exception as e:
        return jsonify({"error": f"Paystack transfer request failed: {e}"}), 502

    payout.status = "approved"
    payout.paystack_transfer_code = transfer_reference
    payout.reviewed_by = acting_admin_id
    payout.reviewed_at = datetime.utcnow()
    db.session.commit()

    if transfer_status:
        _apply_paystack_transfer_result(payout, transfer_status)

    return jsonify({
        "id": payout.id, "status": payout.status, "paystack_transfer_code": payout.paystack_transfer_code,
    })

@app.route("/admin/payouts/<int:payout_id>/reject", methods=["POST"])

def admin_reject_ambassador_payout(payout_id):
    """
    Rejects a payout request and releases every Referral that had been
    bundled into it (payout_id back to NULL), so the ambassador can
    request again later - e.g. once a flagged referral is resolved -
    without losing the rest of their already-unlocked commissions.
    """
    acting_admin_id = session.get("user_id")

    payout = db.session.get(AmbassadorPayout, payout_id)
    if not payout:
        return jsonify({"error": "Payout not found"}), 404
    if payout.status != "pending":
        return jsonify({"error": f"Payout is not pending (status: {payout.status})"}), 400

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason or len(reason) > 500:
        return jsonify({"error": "reason is required and must be 500 characters or fewer"}), 400

    payout.status = "rejected"
    payout.rejection_reason = reason
    payout.reviewed_by = acting_admin_id
    payout.reviewed_at = datetime.utcnow()

    Referral.query.filter_by(payout_id=payout.id).update({"payout_id": None})

    db.session.commit()

    return jsonify({"id": payout.id, "status": payout.status})

@app.route("/admin/payouts/<int:payout_id>/sync-status", methods=["POST"])

def admin_sync_ambassador_payout_status(payout_id):
    """
    Manually re-checks a payout's status directly against Paystack's
    verify-transfer endpoint - useful if a webhook was missed. Safe to
    call any time after a payout has a paystack_transfer_code (i.e.
    after it's been approved/sent).
    """
    payout = db.session.get(AmbassadorPayout, payout_id)
    if not payout:
        return jsonify({"error": "Payout not found"}), 404
    if not payout.paystack_transfer_code:
        return jsonify({"error": "This payout has not been sent to Paystack yet"}), 400

    try:
        sync_paystack_transfer_status(payout)
    except Exception as e:
        return jsonify({"error": f"Paystack status check failed: {e}"}), 502

    return jsonify({
        "id": payout.id,
        "status": payout.status,
        "rejection_reason": payout.rejection_reason,
        "paid_at": payout.paid_at.isoformat() if payout.paid_at else None,
    })
