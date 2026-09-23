from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
app=(ROOT/"app.py").read_text(encoding="utf-8")
streaks=(ROOT/"study_friend_streak_routes.py").read_text(encoding="utf-8")
chat=(ROOT/"frontend/src/crypto/WhatsAppChatExperience.tsx").read_text(encoding="utf-8")
share=(ROOT/"frontend/src/share/StudyShareSheet.tsx").read_text(encoding="utf-8")
frontend=(ROOT/"frontend/src/App.tsx").read_text(encoding="utf-8")
assert "GROUP_MAX_MEMBERS = 200_000" in app
assert "mode = db.Column(db.String(20)" in app
assert "/groups/join-by-code/" in app
assert "group.allow_member_posts" in app
assert "study_friend_streak_activity" in streaks
assert "weekend_pause" in streaks
assert "/study-friend-streaks" in streaks
assert "Pause shared streak on weekends" in chat
assert "study-streak/settings" in chat
assert "friendStreaks" in frontend
assert "study-friend-streaks" in share
print("large-group and shared-streak contract passed")
