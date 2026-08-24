"""
Prepza - Audit Logging module.

The master prompt names "Audit Logs" as its own module, states "Admin
changes must be recorded in audit logs" and "Moderation actions must
be auditable", and lists "Audit logs work" as a literal acceptance
criterion. None of that existed anywhere in app.py before this patch.

Adds:
  - class AuditLog(db.Model)        - new table (append-only by
                                       convention; no update/delete
                                       route is exposed for it)
  - log_admin_action()              - helper; stages a log row on the
                                       current session, never raises
  - GET /admin/audit-logs           - filterable admin-facing list
                                       (actor_id, action substring,
                                       target_type, days window, page)

Wires log_admin_action() into six existing admin/moderation routes,
chosen because they're explicitly covered by the prompt's own
language ("moderation actions must be auditable" -> the four
content-report/content-material actions below; "admin changes" ->
the highest-stakes admin toggle, is_admin/is_suspended):
  - admin_flag_content_material
  - admin_unflag_content_material
  - admin_dismiss_content_report
  - admin_remove_reported_content
  - admin_warn_from_content_report
  - admin_update_user (only logs when is_admin or is_suspended is
    actually included in the request body)

This intentionally does NOT wire logging into every other admin route
in the file (organisations, opportunities, settings, content,
universities, ambassadors, payments, etc) - that's a larger, separate
follow-up patch once this foundation is reviewed, rather than one
sprawling patch touching ~30 functions at once.

Idempotent: safe to re-run. Six of the seven changes are minimal,
structurally-anchored insertions right before an existing
`db.session.commit()` call (found by locating a verified-unique marker
line first, then the *next* commit() after it - not a blind first
match, since commit() appears dozens of times file-wide). The new
model/helper/route block is appended before `if __name__ == "__main__":`,
same pattern as every other patch in this project. Preserves the
file's existing line-ending convention.

IMPORTANT: this patch adds a new SQLAlchemy model (AuditLog), so a NEW
DB TABLE is required. After running this patch, also run
create_audit_log_table.py (delivered alongside this file).

Usage:
    cd ~/Desktop/prepza
    python audit_logging_patch.py
    python create_audit_log_table.py
"""

import sys

APP_PY = "app.py"

MARKER = "class AuditLog(db.Model):"

# (unique_anchor_line, log_admin_action(...) call to insert before the
#  next db.session.commit() found after that anchor)
INSERTIONS = [
    (
        "material.flagged_by = acting_admin_id",
        '    log_admin_action(acting_admin_id, "content_material_flagged", '
        'target_type="generated_material", target_id=material.id, details={"reason": reason})',
    ),
    (
        "material.flagged_by = None",
        '    log_admin_action(session.get("user_id"), "content_material_unflagged", '
        'target_type="generated_material", target_id=material.id)',
    ),
    (
        'report.action_taken = "dismissed"',
        '    log_admin_action(acting_admin_id, "content_report_dismissed", '
        'target_type="content_report", target_id=report.id, '
        'details={"admin_notes": admin_notes} if admin_notes else None)',
    ),
    (
        'report.action_taken = "removed"',
        '    log_admin_action(acting_admin_id, "content_report_content_removed", '
        'target_type="content_report", target_id=report.id, '
        'details={"target_type": report.target_type, "target_id": report.target_id})',
    ),
    (
        'report.action_taken = "warned"',
        '    log_admin_action(acting_admin_id, "content_report_warning_issued", '
        'target_type="user_warning", target_id=warning.id, '
        'details={"warned_user_id": warned_user_id, "reason": report.reason})',
    ),
    (
        "target_user.is_suspended = is_suspended",
        '    _audit_details = {}\n'
        '    if "is_admin" in data:\n'
        '        _audit_details["is_admin"] = target_user.is_admin\n'
        '    if "is_suspended" in data:\n'
        '        _audit_details["is_suspended"] = target_user.is_suspended\n'
        '    if _audit_details:\n'
        '        log_admin_action(acting_admin_id, "user_updated", target_type="user", '
        'target_id=target_user.id, details=_audit_details)',
    ),
]

REQUIRED_DEPENDENCIES = [
    "class User(db.Model):",
    "def require_admin(",
    "import json",
    'if __name__ == "__main__":',
] + [anchor for anchor, _ in INSERTIONS]

NEW_CODE = '''
# ---------- Audit Logging ----------
# "Admin changes must be recorded in audit logs." / "Moderation actions
# must be auditable." per the MVP spec's Admin Platform and Moderation
# phases, and "Audit logs work" is a listed acceptance criterion.

class AuditLog(db.Model):
    """
    Records administrative and moderation actions for accountability.
    Append-only by convention - no UPDATE/DELETE route is exposed for
    this table anywhere; a log that can be edited after the fact isn't
    an audit trail.
    """
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    # nullable to leave room for a future system-initiated entry (e.g.
    # an automated sweep) without forcing a fake actor.
    action = db.Column(db.String(60), nullable=False)
    # short verb-based code, e.g. "user_updated", "content_report_dismissed"
    target_type = db.Column(db.String(40), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    # optional JSON-serialized context (best-effort; falls back to str()
    # for anything that isn't directly JSON-serializable)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def log_admin_action(actor_id, action, target_type=None, target_id=None, details=None):
    """
    Stages one audit log row on the current session. Deliberately does
    NOT call db.session.commit() itself - callers invoke this right
    before their own existing commit, so the audit row lands atomically
    together with the change it's describing, same transaction. If
    details isn't JSON-serializable, falls back to str() rather than
    raising - an audit-logging quirk must never break the admin action
    it's describing.
    """
    payload = None
    if details is not None:
        try:
            payload = json.dumps(details)
        except (TypeError, ValueError):
            payload = str(details)
    db.session.add(AuditLog(
        actor_id=actor_id, action=action, target_type=target_type,
        target_id=target_id, details=payload,
    ))


@app.route("/admin/audit-logs")
@require_admin
def admin_list_audit_logs():
    """
    Lists audit log entries, newest first. Optional filters:
    actor_id (exact match), action (substring match), target_type
    (exact match), days (window, default 30, same convention as
    /admin/ai-usage), page (1-indexed, 50 per page).
    """
    try:
        days = int(request.args.get("days", 30))
    except ValueError:
        days = 30
    days = max(1, min(days, 365))
    window_start = datetime.utcnow() - timedelta(days=days)

    query = AuditLog.query.filter(AuditLog.created_at >= window_start)

    actor_id = request.args.get("actor_id", type=int)
    if actor_id:
        query = query.filter(AuditLog.actor_id == actor_id)

    action_filter = (request.args.get("action") or "").strip()
    if action_filter:
        query = query.filter(AuditLog.action.ilike(f"%{action_filter}%"))

    target_type = (request.args.get("target_type") or "").strip()
    if target_type:
        query = query.filter(AuditLog.target_type == target_type)

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 50

    entries = (
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    result = []
    for e in entries:
        actor = db.session.get(User, e.actor_id) if e.actor_id else None
        parsed_details = None
        if e.details:
            try:
                parsed_details = json.loads(e.details)
            except (TypeError, ValueError):
                parsed_details = e.details
        result.append({
            "id": e.id,
            "actor_id": e.actor_id,
            "actor_email": actor.email if actor else None,
            "action": e.action,
            "target_type": e.target_type,
            "target_id": e.target_id,
            "details": parsed_details,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })

    return jsonify({"page": page, "logs": result})


'''


def apply_insertions(text):
    """
    For each (anchor, log_call) pair: find the anchor's position, then
    find the NEXT 'db.session.commit()' after that position (not a
    blind first match - commit() appears dozens of times file-wide),
    and insert the log call as its own line immediately before that
    specific commit call.
    """
    for anchor, log_call in INSERTIONS:
        anchor_idx = text.index(anchor)
        commit_marker = "db.session.commit()"
        commit_idx = text.index(commit_marker, anchor_idx)

        # Find the start of the commit line. text[commit_line_start:]
        # already carries that line's own leading whitespace (e.g.
        # "    db.session.commit()") - do NOT re-add it, or the commit
        # line ends up double-indented (a real bug caught in testing:
        # it nested db.session.commit() inside an `if` block, silently
        # skipping the commit whenever that condition was false).
        commit_line_start = text.rfind("\n", 0, commit_idx) + 1

        insertion = f"{log_call}\n"
        text = text[:commit_line_start] + insertion + text[commit_line_start:]
    return text


def main():
    with open(APP_PY, "rb") as f:
        raw = f.read()

    uses_crlf = b"\r\n" in raw
    text = raw.decode("utf-8")

    if MARKER in text:
        print("Already applied - AuditLog model found in app.py. Nothing to do.")
        return 0

    missing = [dep for dep in REQUIRED_DEPENDENCIES if dep not in text]
    if missing:
        print("ERROR: required dependency/anchor not found in app.py - cannot safely patch:")
        for m in missing:
            print(f"  - {m}")
        print("This usually means app.py has changed shape since this patch was written.")
        return 1

    # Guard: every anchor line must be unique, or "next commit() after
    # this anchor" could target the wrong call site.
    for anchor, _ in INSERTIONS:
        count = text.count(anchor)
        if count != 1:
            print(f"ERROR: anchor line is not unique ({count} occurrences) - refusing to patch:")
            print(f"  {anchor}")
            return 1

    # ---- 1) Six minimal in-place insertions right before their
    #         respective existing db.session.commit() calls. ----
    text = apply_insertions(text)

    # ---- 2) Append the model + helper + admin route before __main__. ----
    anchor = 'if __name__ == "__main__":'
    idx = text.rfind(anchor)
    if idx == -1:
        print("ERROR: could not locate the __main__ guard anchor.")
        return 1

    block = NEW_CODE
    patched = text[:idx] + block.lstrip("\n") + "\n" + text[idx:]

    if uses_crlf:
        patched = patched.replace("\r\n", "\n").replace("\n", "\r\n")

    with open(APP_PY, "wb") as f:
        f.write(patched.encode("utf-8"))

    print("Patched app.py successfully.")
    print("Added: AuditLog model, log_admin_action() helper, GET /admin/audit-logs")
    print("Wired logging into 6 existing routes:")
    print("  admin_flag_content_material, admin_unflag_content_material,")
    print("  admin_dismiss_content_report, admin_remove_reported_content,")
    print("  admin_warn_from_content_report, admin_update_user")
    print()
    print("NEXT STEP: run create_audit_log_table.py to create the new table.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
