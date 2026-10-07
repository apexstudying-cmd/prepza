"""
Chunk 5 patch script (4): adds Group Post routes - covers both the
Posts tab (like/comment) and Questions tab (vote/reply) in
GroupDetailScreen. Requires chunk5_models_patch.py and
chunk5_routes_groups_patch.py to already be applied.

Also restores a "# ---------- Content routes ----------" comment
header that the previous patch accidentally dropped (cosmetic only -
no code was lost, verified against your app.py).

Safe to re-run: exits without changes if already applied.

Usage:
    cd ~/Desktop/prepza
    python chunk5_routes_group_posts_patch.py
    git diff app.py
"""

APP_PY = "app.py"

ANCHOR = '''    return jsonify({"message": "Left group", "member_count": group.member_count})

@app.route("/units")'''

MARKER = "def create_group_post(group_id):"

NEW_CONTENT = '''    return jsonify({"message": "Left group", "member_count": group.member_count})


def _get_group_visible(group_id, user_id):
    """
    Returns (group, membership) if the group exists and is visible to
    user_id - public/course_only groups are visible to anyone, private
    groups only to members. Returns (None, None) otherwise, so callers
    can 404 without distinguishing "doesn't exist" from "private and
    you're not in it".
    """
    group = db.session.get(Group, group_id)
    if not group:
        return None, None
    membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
    if group.privacy == "private" and not membership:
        return None, None
    return group, membership


GROUP_POST_TYPES = {"post", "question"}
GROUP_POST_BODY_MAX = 3000
GROUP_POST_COMMENT_MAX = 2000


def _serialize_group_post(post, user_id):
    author = db.session.get(User, post.user_id)
    like_count = None
    vote_count = None
    viewer_liked = False
    viewer_voted = False
    if post.post_type == "post":
        like_count = GroupPostLike.query.filter_by(group_post_id=post.id).count()
        viewer_liked = GroupPostLike.query.filter_by(group_post_id=post.id, user_id=user_id).first() is not None
    else:
        vote_count = GroupQuestionVote.query.filter_by(group_post_id=post.id).count()
        viewer_voted = GroupQuestionVote.query.filter_by(group_post_id=post.id, user_id=user_id).first() is not None
    comment_count = GroupPostComment.query.filter_by(group_post_id=post.id).count()
    return {
        "id": post.id,
        "group_id": post.group_id,
        "post_type": post.post_type,
        "body": post.body,
        "author": _display_name(author) if author else "Deleted user",
        "author_id": post.user_id,
        "like_count": like_count,
        "viewer_liked": viewer_liked,
        "vote_count": vote_count,
        "viewer_voted": viewer_voted,
        "comment_count": comment_count,
        "created_at": post.created_at.isoformat() if post.created_at else None,
    }


def _serialize_group_post_comment(comment):
    author = db.session.get(User, comment.user_id)
    return {
        "id": comment.id,
        "group_post_id": comment.group_post_id,
        "body": comment.body,
        "author": _display_name(author) if author else "Deleted user",
        "author_id": comment.user_id,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


@app.route("/groups/<int:group_id>/posts", methods=["POST"])
@require_csrf
def create_group_post(group_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    if not membership:
        return jsonify({"error": "You must join this group first"}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    post_type = (data.get("post_type") or "post").strip().lower()
    if post_type not in GROUP_POST_TYPES:
        return jsonify({"error": "post_type must be 'post' or 'question'"}), 400

    body = (data.get("body") or "").strip()
    if not body or len(body) > GROUP_POST_BODY_MAX:
        return jsonify({"error": f"body is required and must be {GROUP_POST_BODY_MAX} characters or fewer"}), 400

    post = GroupPost(group_id=group_id, user_id=user_id, post_type=post_type, body=body)
    db.session.add(post)
    db.session.commit()

    return jsonify(_serialize_group_post(post, user_id)), 201


@app.route("/groups/<int:group_id>/posts")
def list_group_posts(group_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    post_type = (request.args.get("type") or "post").strip().lower()
    if post_type not in GROUP_POST_TYPES:
        return jsonify({"error": "type must be 'post' or 'question'"}), 400

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 20

    posts = (
        GroupPost.query.filter_by(group_id=group_id, post_type=post_type)
        .order_by(GroupPost.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return jsonify({
        "page": page,
        "posts": [_serialize_group_post(p, user_id) for p in posts],
    })


@app.route("/groups/<int:group_id>/posts/<int:post_id>")
def get_group_post(group_id, post_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    post = db.session.get(GroupPost, post_id)
    if not post or post.group_id != group_id:
        return jsonify({"error": "Post not found"}), 404

    comments = (
        GroupPostComment.query.filter_by(group_post_id=post_id)
        .order_by(GroupPostComment.created_at.asc())
        .all()
    )

    result = _serialize_group_post(post, user_id)
    result["comments"] = [_serialize_group_post_comment(c) for c in comments]
    return jsonify(result)


@app.route("/groups/<int:group_id>/posts/<int:post_id>/comments", methods=["POST"])
@require_csrf
def create_group_post_comment(group_id, post_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    if not membership:
        return jsonify({"error": "You must join this group first"}), 403

    post = db.session.get(GroupPost, post_id)
    if not post or post.group_id != group_id:
        return jsonify({"error": "Post not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    body = (data.get("body") or "").strip()
    if not body or len(body) > GROUP_POST_COMMENT_MAX:
        return jsonify({"error": f"body is required and must be {GROUP_POST_COMMENT_MAX} characters or fewer"}), 400

    comment = GroupPostComment(group_post_id=post_id, user_id=user_id, body=body)
    db.session.add(comment)
    db.session.commit()

    return jsonify(_serialize_group_post_comment(comment)), 201


@app.route("/groups/<int:group_id>/posts/<int:post_id>/like", methods=["POST"])
@require_csrf
def like_group_post(group_id, post_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    if not membership:
        return jsonify({"error": "You must join this group first"}), 403

    post = db.session.get(GroupPost, post_id)
    if not post or post.group_id != group_id:
        return jsonify({"error": "Post not found"}), 404
    if post.post_type != "post":
        return jsonify({"error": "Only Posts-tab posts can be liked - use vote for questions"}), 400

    existing = GroupPostLike.query.filter_by(group_post_id=post_id, user_id=user_id).first()
    if not existing:
        db.session.add(GroupPostLike(group_post_id=post_id, user_id=user_id))
        db.session.commit()

    return jsonify({
        "message": "Already liked" if existing else "Liked",
        "like_count": GroupPostLike.query.filter_by(group_post_id=post_id).count(),
    }), (200 if existing else 201)


@app.route("/groups/<int:group_id>/posts/<int:post_id>/like", methods=["DELETE"])
@require_csrf
def unlike_group_post(group_id, post_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    existing = GroupPostLike.query.filter_by(group_post_id=post_id, user_id=user_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()

    return jsonify({
        "message": "Unliked" if existing else "Not liked",
        "like_count": GroupPostLike.query.filter_by(group_post_id=post_id).count(),
    })


@app.route("/groups/<int:group_id>/posts/<int:post_id>/vote", methods=["POST"])
@require_csrf
def vote_group_post(group_id, post_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    group, membership = _get_group_visible(group_id, user_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    if not membership:
        return jsonify({"error": "You must join this group first"}), 403

    post = db.session.get(GroupPost, post_id)
    if not post or post.group_id != group_id:
        return jsonify({"error": "Post not found"}), 404
    if post.post_type != "question":
        return jsonify({"error": "Only Questions-tab posts can be voted on - use like for posts"}), 400

    existing = GroupQuestionVote.query.filter_by(group_post_id=post_id, user_id=user_id).first()
    if not existing:
        db.session.add(GroupQuestionVote(group_post_id=post_id, user_id=user_id))
        db.session.commit()

    return jsonify({
        "message": "Already voted" if existing else "Voted",
        "vote_count": GroupQuestionVote.query.filter_by(group_post_id=post_id).count(),
    }), (200 if existing else 201)


@app.route("/groups/<int:group_id>/posts/<int:post_id>/vote", methods=["DELETE"])
@require_csrf
def unvote_group_post(group_id, post_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    existing = GroupQuestionVote.query.filter_by(group_post_id=post_id, user_id=user_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()

    return jsonify({
        "message": "Unvoted" if existing else "Not voted",
        "vote_count": GroupQuestionVote.query.filter_by(group_post_id=post_id).count(),
    })


# ---------- Content routes (student-facing) ----------

@app.route("/units")'''


def main():
    with open(APP_PY, "r", encoding="utf-8", newline="") as f:
        content = f.read()

    if MARKER in content:
        print("Already patched (create_group_post route found) - nothing to do.")
        return

    assert "class GroupPost(db.Model):" in content, (
        "GroupPost model not found - run chunk5_models_patch.py first."
    )
    assert "def leave_group(group_id):" in content, (
        "leave_group route not found - run chunk5_routes_groups_patch.py first."
    )

    uses_crlf = "\r\n" in content
    anchor = ANCHOR.replace("\n", "\r\n") if uses_crlf else ANCHOR
    new_content_block = NEW_CONTENT.replace("\n", "\r\n") if uses_crlf else NEW_CONTENT

    assert anchor in content, (
        "Anchor block not found in app.py - has leave_group() or the /units "
        "route moved/changed? Patch script needs updating."
    )
    assert content.count(anchor) == 1, "Anchor block is not unique - refusing to guess which one."

    new_content = content.replace(anchor, new_content_block, 1)

    assert new_content != content, "Replacement had no effect - aborting."
    assert new_content.count(MARKER) == 1, "Sanity check failed after patch."

    with open(APP_PY, "w", encoding="utf-8", newline="") as f:
        f.write(new_content)

    print("Patched app.py - added group post routes (create/list/detail, "
          "comments, like/unlike, vote/unvote) and restored the Content "
          "routes section comment.")


if __name__ == "__main__":
    main()
