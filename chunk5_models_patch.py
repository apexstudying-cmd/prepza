"""
Chunk 5 patch script (1/2): adds the new SQLAlchemy models for
Groups + posts/comments/likes/votes + Follow + Notification.

Safe to re-run: if the new models are already present, it exits
without changing anything instead of erroring or duplicating.

Usage:
    cd ~/Desktop/prepza
    python chunk5_models_patch.py
    git diff app.py
"""
import re

APP_PY = "app.py"

ANCHOR = '''    cache_read_tokens = db.Column(db.Integer, default=0)
    cache_creation_tokens = db.Column(db.Integer, default=0)
    cost_usd = db.Column(db.Numeric(10, 6), default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def get_mpesa_access_token():'''

MARKER = "class Group(db.Model):"

NEW_MODELS = '''    cache_read_tokens = db.Column(db.Integer, default=0)
    cache_creation_tokens = db.Column(db.Integer, default=0)
    cost_usd = db.Column(db.Numeric(10, 6), default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.String(1000), nullable=True)
    privacy = db.Column(db.String(20), nullable=False, default="public")
    # public | private | course_only
    university_id = db.Column(db.Integer, db.ForeignKey("university.id"), nullable=True)
    program_id = db.Column(db.Integer, db.ForeignKey("program.id"), nullable=True)
    unit_id = db.Column(db.Integer, db.ForeignKey("unit.id"), nullable=True)
    year = db.Column(db.Integer, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    member_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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


class GroupPostComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_post_id = db.Column(db.Integer, db.ForeignKey("group_post.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Used for both Posts-tab comments and Questions-tab replies - the
    # frontend's shared CommentsScreen doesn't distinguish them either.


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


def get_mpesa_access_token():'''


def main():
    # newline="" preserves whatever line endings app.py already uses
    # (this repo's app.py is CRLF) instead of Python's universal-newline
    # translation silently rewriting every line to LF, which would blow
    # up the git diff.
    with open(APP_PY, "r", encoding="utf-8", newline="") as f:
        content = f.read()

    if MARKER in content:
        print("Already patched (Group model found) - nothing to do.")
        return

    uses_crlf = "\r\n" in content
    anchor = ANCHOR.replace("\n", "\r\n") if uses_crlf else ANCHOR
    new_models = NEW_MODELS.replace("\n", "\r\n") if uses_crlf else NEW_MODELS

    assert anchor in content, (
        "Anchor block not found in app.py - has the AiUsageLog model or "
        "get_mpesa_access_token() moved/changed? Patch script needs updating."
    )
    assert content.count(anchor) == 1, "Anchor block is not unique - refusing to guess which one."

    new_content = content.replace(anchor, new_models, 1)

    assert new_content != content, "Replacement had no effect - aborting."
    assert new_content.count(MARKER) == 1, "Sanity check failed after patch."

    with open(APP_PY, "w", encoding="utf-8", newline="") as f:
        f.write(new_content)

    print("Patched app.py - added Group, GroupMember, GroupPost, "
          "GroupPostComment, GroupPostLike, GroupQuestionVote, GroupFile, "
          "Follow, Notification models.")


if __name__ == "__main__":
    main()
