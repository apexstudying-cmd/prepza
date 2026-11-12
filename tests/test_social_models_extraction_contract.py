from __future__ import annotations

from pathlib import Path

from social_models import (
    Announcement, ContentReport, Follow, FollowRequest, Group, GroupFile,
    GroupMember, GroupPost, GroupPostComment, GroupPostLike, GroupQuestionVote,
    Notification, NotificationPreference, UserWarning,
    CONTENT_REPORT_ACTIONS, CONTENT_REPORT_REASONS, CONTENT_REPORT_STATUSES,
    CONTENT_REPORT_TARGET_TYPES, PROFILE_VISIBILITY_VALUES,
    WHO_CAN_FOLLOW_VALUES, WHO_CAN_MESSAGE_VALUES,
)

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def test_social_models_and_policy_constants_are_reexported_by_legacy_app() -> None:
    assert "from social_models import (" in APP_SOURCE
    for name in (
        "Group", "GroupMember", "GroupPost", "GroupPostComment", "GroupPostLike",
        "GroupQuestionVote", "GroupFile", "Follow", "FollowRequest",
        "Notification", "NotificationPreference", "Announcement",
        "ContentReport", "UserWarning",
    ):
        assert f"class {name}(db.Model)" not in APP_SOURCE
        assert name in APP_SOURCE


def test_social_model_table_contracts_are_preserved() -> None:
    expected = (
        (Group, "group", {"id", "name", "description", "privacy", "university_id", "program_id", "year", "created_by", "member_count", "created_at", "is_active"}),
        (GroupMember, "group_member", {"id", "group_id", "user_id", "role", "joined_at"}),
        (GroupPost, "group_post", {"id", "group_id", "user_id", "post_type", "body", "created_at", "is_removed"}),
        (GroupPostComment, "group_post_comment", {"id", "group_post_id", "user_id", "body", "created_at", "is_removed", "marked_helpful"}),
        (Follow, "follow", {"id", "follower_id", "followed_id", "created_at"}),
        (FollowRequest, "follow_request", {"id", "requester_id", "target_id", "status", "created_at", "responded_at"}),
        (Notification, "notification", {"id", "user_id", "type", "title", "body", "related_type", "related_id", "is_read", "created_at"}),
        (NotificationPreference, "notification_preference", {"id", "user_id", "community_enabled", "messages_enabled", "created_at", "updated_at"}),
        (Announcement, "announcement", {"id", "title", "body", "sent_by", "reach", "created_at"}),
        (ContentReport, "content_report", {"id", "target_type", "target_id", "reporter_user_id", "reason", "details", "priority", "status", "action_taken", "admin_notes", "reviewed_by", "reviewed_at", "created_at"}),
        (UserWarning, "user_warning", {"id", "user_id", "issued_by", "content_report_id", "reason", "message", "consequence", "created_at"}),
    )
    for model, table, columns in expected:
        assert model.__tablename__ == table
        assert set(model.__table__.columns.keys()) == columns


def test_social_uniqueness_and_moderation_vocabulary_are_preserved() -> None:
    for model, constraint_name in (
        (GroupMember, "uq_group_member_group_user"),
        (GroupPostLike, "uq_group_post_like_post_user"),
        (GroupQuestionVote, "uq_group_question_vote_post_user"),
        (GroupFile, "uq_group_file_group_document"),
        (Follow, "uq_follow_follower_followed"),
        (FollowRequest, "uq_follow_request_requester_target"),
    ):
        assert any(getattr(c, "name", None) == constraint_name for c in model.__table__.constraints)
    assert PROFILE_VISIBILITY_VALUES == {"public", "private"}
    assert WHO_CAN_MESSAGE_VALUES == {"everyone", "followers"}
    assert WHO_CAN_FOLLOW_VALUES == {"everyone", "approval_required"}
    assert CONTENT_REPORT_TARGET_TYPES == ("group_post", "group_post_comment", "user")
    assert CONTENT_REPORT_STATUSES == ("pending", "dismissed", "actioned")
    assert CONTENT_REPORT_ACTIONS == ("dismissed", "removed", "warned")
    assert set(CONTENT_REPORT_REASONS) == {
        "academic_dishonesty", "harassment", "offensive_content",
        "misinformation", "spam_scam", "duplicate", "bot_activity", "other",
    }
