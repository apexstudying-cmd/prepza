"""Small runtime registration for server-side opportunity expiry.

Kept separate from app.py so restoring the admin control does not disturb
the current student opportunity runtime.
"""
import app as _app

globals().update({k: getattr(_app, k) for k in dir(_app) if not k.startswith("__")})


def sweep_expired_opportunities():
    now = datetime.utcnow()
    updated = Opportunity.query.filter(
        Opportunity.status == "published",
        Opportunity.expiry_date <= now,
    ).update({"status": "expired"}, synchronize_session=False)
    db.session.commit()
    return updated


def _sweep_expired_opportunities_safe():
    """Run the expiry sweep without allowing it to break /health."""
    try:
        count = sweep_expired_opportunities()
        if count:
            _app.logger.info(
                "Swept %s expired opportunity(ies) to status='expired'",
                count,
            )
    except Exception:
        db.session.rollback()
        _app.logger.exception("Expired-opportunity sweep failed during health check")


@app.route("/admin/opportunities/sweep-expired", methods=["POST"])
@require_csrf
@require_admin
def admin_sweep_expired_opportunities():
    count = sweep_expired_opportunities()
    return jsonify({"swept_count": count})
