"""
Prepza - Chunk 7 (Opportunities + Organisation portal), Step 7 patch.

Adds server-side auto-expiry for published Opportunities:

  - sweep_expired_opportunities()       - bulk-flips published+expired
                                           Opportunity rows to 'expired'
  - _sweep_expired_opportunities_safe() - wraps the sweep so a failure
                                           can never break /health
  - POST /admin/opportunities/sweep-expired - manual admin trigger
  - One-line hook into the existing /health route, so the sweep piggy-
    backs on the GitHub Actions keep-alive ping (~every 10 min) - no
    new cron/infra needed.

Deliberately scoped to status='published' only. Opportunities stuck in
pending_review/approved whose expiry_date has quietly passed never
went live, so 'expired' would be the wrong terminal state for them -
those are left for an admin to handle manually via reject/remove.

Idempotent: safe to re-run. The /health hook is a single-line insertion
right after a verified-unique anchor line (db.session.execute(text(...)))
rather than a reproduction of the whole function body - lower risk of
colliding with a parallel session's edits to that route's docstring or
error handling. The new function/route block is appended before the
`if __name__ == "__main__":` guard, same pattern as every prior patch
in this chunk. Preserves the file's existing line-ending convention.

Usage:
    cd ~/Desktop/prepza
    python chunk7_opportunity_expiry_patch.py
"""

import sys

APP_PY = "app.py"

MARKER = "def sweep_expired_opportunities():"

HEALTH_ANCHOR_LINE = 'db.session.execute(text("SELECT 1"))'

REQUIRED_DEPENDENCIES = [
    "class Opportunity(db.Model):",
    "def require_admin(",
    "def require_csrf(",
    '@app.route("/health")',
    'if __name__ == "__main__":',
]

NEW_CODE = '''
# ---------- Opportunity auto-expiry (Step 7) ----------

def sweep_expired_opportunities():
    """
    Flips any Opportunity still marked 'published' whose expiry_date has
    passed into 'expired'. Never trusts a frontend clock for this - per
    the MVP spec, expiry is always computed server-side. Bulk UPDATE (no
    per-row SELECT/commit loop) so this stays cheap even when called on
    every health-check tick. Returns the number of rows updated.

    Deliberately scoped to status='published' only - opportunities still
    stuck in pending_review/approved past their own expiry_date never
    went live, so 'expired' is the wrong terminal state for them; those
    are left for an admin to handle manually via the existing
    reject/remove routes rather than silently auto-expired here.
    """
    now = datetime.utcnow()
    updated = Opportunity.query.filter(
        Opportunity.status == "published",
        Opportunity.expiry_date <= now,
    ).update({"status": "expired"}, synchronize_session=False)
    db.session.commit()
    return updated


def _sweep_expired_opportunities_safe():
    """
    Wraps sweep_expired_opportunities() for use inside /health - a sweep
    failure must NEVER turn /health into a false-negative for the
    GitHub Actions keep-alive ping, whose only job is preventing
    Render's free tier from spinning down and Supabase's free tier from
    auto-pausing. Swallows and logs, never raises or affects the
    response.
    """
    try:
        count = sweep_expired_opportunities()
        if count:
            print(f"INFO: swept {count} expired opportunity(ies) to status='expired'")
    except Exception as e:
        db.session.rollback()
        print(f"WARNING: expired-opportunity sweep failed during health check: {e}")


@app.route("/admin/opportunities/sweep-expired", methods=["POST"])
@require_csrf
@require_admin
def admin_sweep_expired_opportunities():
    """
    Manual trigger for the expiry sweep - lets an admin force it on
    demand (e.g. right after changing an expiry_date, or for testing)
    rather than waiting for the next /health ping, which piggybacks the
    same sweep on roughly a 10-minute cadence via the existing GitHub
    Actions keep-alive workflow.
    """
    count = sweep_expired_opportunities()
    return jsonify({"swept_count": count})


'''


def main():
    with open(APP_PY, "rb") as f:
        raw = f.read()

    uses_crlf = b"\r\n" in raw
    text = raw.decode("utf-8")

    if MARKER in text:
        print("Already applied - sweep_expired_opportunities found in app.py. Nothing to do.")
        return 0

    missing = [dep for dep in REQUIRED_DEPENDENCIES if dep not in text]
    if missing:
        print("ERROR: required dependency not found in app.py - cannot safely patch:")
        for m in missing:
            print(f"  - {m}")
        return 1

    anchor_count = text.count(HEALTH_ANCHOR_LINE)
    if anchor_count != 1:
        print(
            f"ERROR: expected exactly 1 occurrence of the /health anchor line, "
            f"found {anchor_count}. Refusing to guess which one to patch - "
            f"app.py has likely changed shape since this patch was written."
        )
        return 1

    # ---- 1) Hook the sweep into /health with a minimal, single-line
    #         insertion right after the anchor line (same indentation),
    #         rather than reproducing the whole function body. ----
    anchor_idx = text.index(HEALTH_ANCHOR_LINE)
    # Determine the anchor line's leading whitespace so the inserted
    # call matches it exactly.
    line_start = text.rfind("\n", 0, anchor_idx) + 1
    indent = text[line_start:anchor_idx]
    line_end = text.index("\n", anchor_idx)  # end of the anchor line (before its \n)

    insertion = f"\n{indent}_sweep_expired_opportunities_safe()"
    text = text[:line_end] + insertion + text[line_end:]

    # ---- 2) Append the sweep function + admin route before __main__. ----
    anchor = 'if __name__ == "__main__":'
    idx = text.rfind(anchor)
    if idx == -1:
        print("ERROR: could not locate the __main__ guard anchor.")
        return 1

    block = NEW_CODE
    if uses_crlf:
        block = block.replace("\r\n", "\n").replace("\n", "\r\n")

    patched = text[:idx] + block.lstrip("\r\n") + ("\r\n" if uses_crlf else "\n") + text[idx:]

    if uses_crlf:
        patched = patched.replace("\r\n", "\n").replace("\n", "\r\n")

    with open(APP_PY, "wb") as f:
        f.write(patched.encode("utf-8"))

    print("Patched app.py successfully.")
    print("Added:")
    print("  sweep_expired_opportunities() + _sweep_expired_opportunities_safe()")
    print("  POST /admin/opportunities/sweep-expired")
    print("  Hooked sweep into GET /health (fails silently, never breaks the health check)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
