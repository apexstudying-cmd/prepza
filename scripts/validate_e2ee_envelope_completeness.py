"""Static regression checks for current-epoch group-key provisioning.

The server must not accept a partially provisioned epoch: every active member
needs exactly one envelope, otherwise a member can be left unable to decrypt
messages after a rotation.
"""

from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "e2ee_chat_routes.py"


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    required = (
        "active_member_ids = {int(row[0]) for row in active_member_rows if row[0] is not None}",
        "if len(envelopes) != len(active_member_ids):",
        "seen_recipient_ids = set()",
        "if recipient_id in seen_recipient_ids:",
        "if seen_recipient_ids != active_member_ids:",
    )
    missing = [anchor for anchor in required if anchor not in source]
    if missing:
        raise SystemExit("Missing E2EE envelope completeness guard(s): " + "; ".join(missing))
    print("E2EE envelope completeness guards: OK")


if __name__ == "__main__":
    main()
