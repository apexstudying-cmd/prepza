"""Community, social graph, notifications and moderation ORM models."""
from datetime import datetime

from extensions import db


class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.String(1000), nullable=True)
    privacy = db.Column(db.String(20), nullable=False, default="public")
    # public | private | course_only
    university_id = db.Column(db.Integer, db.ForeignKey("university.id"), nullable=True)
    program_id = db.Column(db.Integer, db.ForeignKey("program.id"), nullable=True)

    year = db.Column(db.Integer, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    member_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Admin kill-switch (Chunk 10) - deactivating a group hides it from
    # browse/join and blocks new posts/comments/joins for existing
    # members too (see _get_group_visible() and the is_active checks in
    # create_group_post/create_group_post_comment/join_group below).
    # Same reactive pattern as Organisation.is_active elsewhere in this
    # file, but stricter: Organisation only hides new opportunities,
    # this also blocks ongoing member activity.


class GroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("group.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="member")
    # admin | member
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("group_id", "user_id", name="uq_group_member_group_user"),
    )


class GroupPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("group.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_type = db.Column(db.String(20), nullable=False, default="post")
    # post | question - Posts tab vs Questions tab in GroupDetailScreen
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_removed = db.Column(db.Boolean, nullable=False, default=False)


class GroupPostComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_post_id = db.Column(db.Integer, db.ForeignKey("group_post.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_removed = db.Column(db.Boolean, nullable=False, default=False)
    # Used for both Posts-tab comments and Questions-tab replies - the
    # frontend's shared CommentsScreen doesn't distinguish them either.
    marked_helpful = db.Column(db.Boolean, nullable=False, default=False)
    # Set once by the original post's author via /helpful below - awards
    # XP_COMMUNITY_HELPFUL_REPLY to the comment's author (Chunk 7).


class GroupPostLike(db.Model):
    """Heart/like on a Posts-tab GroupPost."""
    id = db.Column(db.Integer, primary_key=True)
    group_post_id = db.Column(db.Integer, db.ForeignKey("group_post.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("group_post_id", "user_id", name="uq_group_post_like_post_user"),
    )


class GroupQuestionVote(db.Model):
    """Upvote on a Questions-tab GroupPost. Kept separate from
    GroupPostLike since a post can only be one type (post XOR question)
    but the two interactions have different semantics and copy."""
    id = db.Column(db.Integer, primary_key=True)
    group_post_id = db.Column(db.Integer, db.ForeignKey("group_post.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("group_post_id", "user_id", name="uq_group_question_vote_post_user"),
    )


class GroupFile(db.Model):
    """Shares an existing personal Document into a group's Files tab -
    does not duplicate storage, just links to the student's own
    Document row (must already be status=ready)."""
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("group.id", ondelete="CASCADE"), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey("document.id"), nullable=False)
    shared_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("group_id", "document_id", name="uq_group_file_group_document"),
    )


class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("follower_id", "followed_id", name="uq_follow_follower_followed"),
    )


PROFILE_VISIBILITY_VALUES = {"public", "private"}
WHO_CAN_MESSAGE_VALUES = {"everyone", "followers"}
WHO_CAN_FOLLOW_VALUES = {"everyone", "approval_required"}


class FollowRequest(db.Model):
    """
    A pending/accepted/declined follow request, used only when the
    target has who_can_follow='approval_required' (private-account-
    style gating, see PATCH /profile). Unique on (requester, target)
    so a re-request after a decline updates the same row back to
    pending rather than creating duplicates - same reapply pattern
    as Ambassador elsewhere in this file. Accepting a request creates
    a real Follow row; the FollowRequest row itself is not the
    source of truth for "is following" once accepted.
    """
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    target_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(10), nullable=False, default="pending")
    # pending -> accepted | declined
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (
        db.UniqueConstraint("requester_id", "target_id", name="uq_follow_request_requester_target"),
    )


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    type = db.Column(db.String(40), nullable=False)
    # e.g. group_post, group_comment, group_join_request, new_follower,
    # forum_ai_reply, study_reminder, opportunity, achievement, announcement
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.String(500), nullable=True)
    related_type = db.Column(db.String(40), nullable=True)
    # e.g. "group", "group_post", "user", "forum_post" - paired with
    # related_id so the frontend notification tap-target can be resolved
    # without a different table shape per notification type.
    related_id = db.Column(db.Integer, nullable=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class NotificationPreference(db.Model):
    """
    Per-user, per-category notification opt-out (Settings > Notifications).
    A missing row means "everything on" (see get_or_create_notification_prefs) -
    rows are created lazily on first read/write, not at signup. Only
    categories with an actual notification-producing code path are
    represented here - "push" (browser subscription on/off) is handled
    entirely by PushSubscription and isn't duplicated here.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    community_enabled = db.Column(db.Boolean, nullable=False, default=True)
    # gates: new_follower, group_like, group_vote, group_comment, group_promoted
    messages_enabled = db.Column(db.Boolean, nullable=False, default=True)
    # gates: chat DM push (see send_message())
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Announcement(db.Model):
    """
    A record of one admin broadcast (Communications tab). Sending an
    announcement fans out a Notification(type="announcement") row to
    every eligible user at send time - reach is snapshotted here rather
    than recomputed later, since the user population (and who was
    suspended at send time) will keep changing after the fact.
    """
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.String(500), nullable=False)
    sent_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    reach = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------- Moderation (Chunk 10) ----------

CONTENT_REPORT_TARGET_TYPES = (
    "group_post", "group_post_comment", "user",
)
CONTENT_REPORT_REASONS = {
    # reason -> auto-assigned priority. Deliberately a fixed mapping
    # rather than an admin-editable one for MVP, same tradeoff as the
    # hardcoded XP_* amounts elsewhere in this file.
    "academic_dishonesty": "high",
    "harassment": "high",
    "offensive_content": "medium",
    "misinformation": "medium",
    "spam_scam": "medium",
    "duplicate": "low",
    "bot_activity": "low",
    "other": "low",
}
CONTENT_REPORT_STATUSES = ("pending", "dismissed", "actioned")
CONTENT_REPORT_ACTIONS = ("dismissed", "removed", "warned")


class ContentReport(db.Model):
    """
    A student report against a piece of community content (forum
    posts/replies, group posts/comments) or against a user directly.
    Deliberately separate from LibraryReport, which already covers
    document/library-item reports with its own queue - this table
    fills the gap for everything else, which previously had no
    reporting mechanism at all.
    """
    id = db.Column(db.Integer, primary_key=True)
    target_type = db.Column(db.String(30), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    reporter_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    # nullable to leave room for future automated/system-flagged reports
    reason = db.Column(db.String(40), nullable=False)
    details = db.Column(db.String(500), nullable=True)
    priority = db.Column(db.String(10), nullable=False)
    # high | medium | low - derived from `reason` at creation time
    status = db.Column(db.String(20), nullable=False, default="pending")
    # pending -> dismissed | actioned
    action_taken = db.Column(db.String(20), nullable=True)
    # set alongside status='actioned': 'removed' | 'warned'
    admin_notes = db.Column(db.String(500), nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class UserWarning(db.Model):
    """
    A formal warning issued to a student, always paired with a
    Notification(type='moderation_warning') so the student actually
    sees it - not just an internal admin note. `message` states what
    they did wrong, `consequence` states what happens as a result /
    next time, both admin-authored per warning rather than templated,
    since the punishment should match the specific violation.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    issued_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    content_report_id = db.Column(db.Integer, db.ForeignKey("content_report.id"), nullable=True)
    reason = db.Column(db.String(40), nullable=False)
    # same vocabulary as ContentReport.reason, so warnings and reports
    # can be filtered/grouped consistently
    message = db.Column(db.String(500), nullable=False)
    consequence = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------- Opportunities + Organisation portal ----------

ORGANISATION_VERIFICATION_STATUSES = ("pending", "verified", "rejected")
