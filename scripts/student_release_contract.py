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

# No Settings row may advertise unsupported controls as interactive.
require("Login Sessions" in FRONTEND and "Session management is not available yet" in FRONTEND, "login sessions must not be a fake action")
require("Two-Factor Authentication" in FRONTEND and "Not available yet" in FRONTEND, "2FA must not be a fake action")
require("Study Reminders" in FRONTEND and "Not available yet" in FRONTEND, "study reminders must not be a fake action")
require("Study Preferences" in FRONTEND and "Not available yet" in FRONTEND, "study preferences must not be a fake action")
require("AI Preferences" in FRONTEND and "Not available yet" in FRONTEND, "AI preferences must not be a fake action")
require("Help centre is not available yet" in FRONTEND and "Problem reporting is not available yet" in FRONTEND and "Contact Support" in FRONTEND and "setShowModal(\'contact\')" in FRONTEND, "support controls must be either explicitly unavailable or wired to the real contact flow")
require("setScreen('subscription')" in FRONTEND, "subscription settings navigation missing")
require("setScreen('payment-history')" in FRONTEND, "payment history navigation missing")
require("await api('/logout', { method: 'POST'" in FRONTEND, "logout must await server success")

# Support must be an actual admin-configurable contact surface.
require('@app.route("/support/contact", methods=["GET"])' in APP, "student support config endpoint missing")
require('support_email' in APP and 'support_phone' in APP and 'support_message' in APP, "support configuration fields missing")
require("/support/contact" in FRONTEND and "mailto:" in FRONTEND and "tel:" in FRONTEND, "contact support must use admin-configured contact details")
require("support_email: string" in FRONTEND and "support_phone: string" in FRONTEND, "admin support settings are not represented in the frontend")
require("Student Support Contact" in FRONTEND and "settingsDraft.support_email" in FRONTEND, "admin support settings UI missing")

# Account deletion must remove the user and personal rows while preserving
# detached payment history and reusable shared generation artifacts.
delete_block = re.search(r'@app\.route\("/delete-account", methods=\["DELETE"\]\).*?db\.session\.delete\(user\)', APP, re.S)
require(delete_block is not None, "account deletion endpoint missing")
require("Payment.query.filter_by(user_id=user_id).update({\"user_id\": None}" in APP, "payment history must be detached rather than deleted")
require("GeneratedMaterial.owner_user_id == user_id" in APP and "GeneratedMaterial.owner_user_id: None" in APP, "reusable generated artifacts must be detached from the deleted user")
require("ownership_requires_transfer" in APP and "not admin_user" in APP, "unsafe ownership deletion must be blocked without an admin transfer target")
require("DocumentContent/GeneratedMaterial" in APP, "deletion contract must document reusable artifact preservation")
require("Document.query.filter_by(user_id=user_id).delete" in APP, "student document ownership rows must be removed")


print("STUDENT_RELEASE_CONTRACT_PASSED")
