"""Focused student-side release invariants that must stay aligned.

This complements the broader build/audit suite with contracts for the
recently hardened student surfaces: encrypted group chats, reactions,
logout CSRF, and shared study streaks.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
FRONTEND = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
PROVISION = (ROOT / "frontend/src/crypto/groupProvisioning.ts").read_text(encoding="utf-8")
STREAK = (ROOT / "study_friend_streak_routes.py").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("STUDENT_RELEASE_CONTRACT_FAILED: " + message)


require("CHAT_GROUP_MAX_MEMBERS = 100" in APP, "encrypted group-chat member ceiling missing")
require("len(participant_ids) + 1 > CHAT_GROUP_MAX_MEMBERS" in APP, "backend does not enforce the encrypted group-chat ceiling")
require("members.length > 100" in PROVISION, "client group-key provisioning ceiling missing")
require('if not isinstance(envelopes, list) or not envelopes or len(envelopes) > 100:' in (ROOT / "e2ee_chat_routes.py").read_text(encoding="utf-8"), "server group-key envelope ceiling missing")

logout_block = re.search(r'@app\.route\("/logout", methods=\["POST"\]\)\s+@require_csrf\s+def logout', APP)
require(logout_block is not None, "logout must require CSRF")
require("api('/logout', { method: 'POST', headers: { 'X-CSRF-Token': csrfToken } })" in FRONTEND, "frontend logout must send CSRF")

require('allowed_reactions = {"👍", "❤️", "😂", "😮", "😢", "🎉"}' in APP, "group reaction whitelist missing")
require("Unsupported reaction" in APP, "unsupported group reactions are not rejected")

require('os.environ.get("PREPZA_TIMEZONE", "Africa/Nairobi")' in STREAK, "shared streak timezone contract missing")
require("db.session.commit()\n\n        # Existing installations need the new setting" in STREAK, "streak schema bootstrap must commit before compatibility ALTER")
require("def local_today()" in STREAK, "shared streak local-date helper missing")
require("started = False" in STREAK and "elif started:" in STREAK, "shared streak must preserve an active streak when today is not yet qualified")

# Settings must be real end-to-end controls, not local-only toggles.
require('who_can_message: next ? \'everyone\' : \'followers\'' in FRONTEND, "message privacy toggle must persist through /profile")
require('who_can_follow: next ? \'everyone\' : \'approval_required\'' in FRONTEND, "follow privacy toggle must persist through /profile")
require('@app.route("/api/opportunity-discovery", methods=["GET", "POST"])' in APP, "opportunity discovery endpoint missing")
require("CREATE TABLE IF NOT EXISTS student_opportunity_discovery" in APP, "opportunity discovery persistence bootstrap missing")
require("/api/opportunity-discovery" in FRONTEND and "method: 'POST'" in FRONTEND, "opportunity discovery setting is not wired to the backend")
require("setPhoneNumber(me.phone_number || '')" in FRONTEND, "settings does not load the saved phone number")
require("phone_number: phoneNumber.trim() || null" in FRONTEND, "settings phone save is not wired to /profile")

# Child settings screens must return to Settings through the SPA stack.
require("function SubscriptionScreen" in FRONTEND and "setScreen('settings')" in FRONTEND[FRONTEND.index("function SubscriptionScreen"):FRONTEND.index("function PaymentScreen")], "subscription screen back navigation must return to settings")
require("function PaymentHistoryScreen" in FRONTEND, "payment history screen missing")
require("function EditProfileScreen" in FRONTEND, "edit profile screen missing")

print("STUDENT_RELEASE_CONTRACT_PASSED")
