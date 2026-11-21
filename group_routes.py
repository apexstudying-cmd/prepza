"""Study group, post, membership and shared-file routes.

Existing handlers are kept intact inside an injected registration function.
Late-defined shared helpers are passed through lazy callables from app.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import jsonify, request, session


def register_group_routes(
    app: Any,
    db: Any,
    *,
    Group: Any,
    GroupMember: Any,
    GroupPost: Any,
    GroupPostComment: Any,
    GroupPostLike: Any,
    GroupQuestionVote: Any,
    GroupFile: Any,
    User: Any,
    Notification: Any,
    University: Any,
    Program: Any,
    Document: Any,
    XP_COMMUNITY_HELPFUL_REPLY: Any,
    award_xp: Any,
    check_and_unlock_achievements: Any,
    _display_name: Any,
    get_signed_url: Any,
    should_notify: Any,
    send_push_notification: Any,
    require_csrf: Any,
) -> None:
    """Register the existing study-group route surface."""
    # ---------- Groups ----------

    GROUP_NAME_MAX = 150
    GROUP_DESCRIPTION_MAX = 1000
    GROUP_PRIVACY_VALUES = {"public", "private", "course_only"}


    def _serialize_group(group, membership=None):
        return {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "privacy": group.privacy,
            "university_id": group.university_id,
            "program_id": group.program_id,
            "year": group.year,
            "member_count": group.member_count,
            "created_by": group.created_by,
            "created_at": group.created_at.isoformat() if group.created_at else None,
            "is_active": group.is_active,
            "is_member": membership is not None,
            "role": membership.role if membership else None,
        }


    @app.route("/groups", methods=["POST"])
    @require_csrf
    def create_group():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Request body must be valid JSON"}), 400

        name = (data.get("name") or "").strip()
        if not name or len(name) > GROUP_NAME_MAX:
            return jsonify({"error": f"name is required and must be {GROUP_NAME_MAX} characters or fewer"}), 400

        description = data.get("description")
        if description is not None:
            if not isinstance(description, str):
                return jsonify({"error": "description must be a string"}), 400
            description = description.strip() or None
            if description and len(description) > GROUP_DESCRIPTION_MAX:
                return jsonify({"error": f"description must be {GROUP_DESCRIPTION_MAX} characters or fewer"}), 400

        privacy = (data.get("privacy") or "public").strip().lower()
        if privacy not in GROUP_PRIVACY_VALUES:
            return jsonify({"error": "privacy must be one of: " + ", ".join(sorted(GROUP_PRIVACY_VALUES))}), 400

        university_id = data.get("university_id")
        if university_id is not None:
            if not isinstance(university_id, int) or not db.session.get(University, university_id):
                return jsonify({"error": "Invalid university_id"}), 400

        program_id = data.get("program_id")
        if program_id is not None:
            if not isinstance(program_id, int) or not db.session.get(Program, program_id):
                return jsonify({"error": "Invalid program_id"}), 400
        if data.get("unit_id") is not None:
            return jsonify({"error": "unit_id is no longer supported"}), 400

        year = data.get("year")
        if year is not None:
            if not isinstance(year, int) or isinstance(year, bool) or year < 1 or year > 5:
                return jsonify({"error": "year must be a number between 1 and 5, or omitted for 'Mixed'"}), 400

        member_user_ids = data.get("member_user_ids")
        if member_user_ids is not None:
            if not isinstance(member_user_ids, list) or len(member_user_ids) > 50:
                return jsonify({"error": "member_user_ids must be a list of at most 50 user ids"}), 400
            if not all(isinstance(uid, int) and not isinstance(uid, bool) for uid in member_user_ids):
                return jsonify({"error": "member_user_ids must all be integers"}), 400
            member_user_ids = sorted({uid for uid in member_user_ids if uid != user_id})
        else:
            member_user_ids = []

        group = Group(
            name=name,
            description=description,
            privacy=privacy,
            university_id=university_id,
            program_id=program_id,

            year=year,
            created_by=user_id,
            member_count=1,
        )
        db.session.add(group)
        db.session.flush()  # assign group.id before the membership row references it

        membership = GroupMember(group_id=group.id, user_id=user_id, role="admin")
        db.session.add(membership)

        added_members = 0
        for member_id in member_user_ids:
            # Silently skip unknown ids rather than failing the whole create -
            # a stale/typo'd id in the initial member list shouldn't block
            # group creation.
            if db.session.get(User, member_id):
                db.session.add(GroupMember(group_id=group.id, user_id=member_id, role="member"))
                added_members += 1
        group.member_count = 1 + added_members

        db.session.commit()

        return jsonify(_serialize_group(group, membership)), 201


    @app.route("/groups")
    def browse_groups():
        """
        Browse/discover groups. Private groups are excluded entirely - no
        invite/request flow exists yet, so surfacing them would just be a
        dead end. Course-only groups ARE listed (not yet restricted to
        matching students - that's a later refinement, not a security
        boundary, since course_only groups still require an explicit join).
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        query = Group.query.filter(Group.privacy != "private", Group.is_active.is_(True))

        q = (request.args.get("q") or "").strip()
        if q:
            query = query.filter(Group.name.ilike(f"%{q}%"))
        unit_id = None

        university_id = request.args.get("university_id", type=int)
        if university_id:
            query = query.filter(Group.university_id == university_id)

        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        per_page = 20

        groups = (
            query.order_by(Group.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        group_ids = [g.id for g in groups]
        memberships = {
            m.group_id: m
            for m in GroupMember.query.filter(
                GroupMember.user_id == user_id, GroupMember.group_id.in_(group_ids)
            ).all()
        } if group_ids else {}

        return jsonify({
            "page": page,
            "groups": [_serialize_group(g, memberships.get(g.id)) for g in groups],
        })


    @app.route("/groups/mine")
    def my_groups():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        memberships = (
            GroupMember.query.filter_by(user_id=user_id)
            .order_by(GroupMember.joined_at.desc())
            .all()
        )

        result = []
        for m in memberships:
            group = db.session.get(Group, m.group_id)
            if not group:
                continue
            result.append(_serialize_group(group, m))

        return jsonify({"groups": result})


    @app.route("/groups/<int:group_id>")
    def get_group(group_id):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        group = db.session.get(Group, group_id)
        if not group:
            return jsonify({"error": "Group not found"}), 404

        membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()

        if group.privacy == "private" and not membership:
            # Hide existence of private groups from non-members rather than
            # a 403 that would confirm the group exists.
            return jsonify({"error": "Group not found"}), 404

        return jsonify(_serialize_group(group, membership))


    @app.route("/groups/<int:group_id>/join", methods=["POST"])
    @require_csrf
    def join_group(group_id):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        group = db.session.get(Group, group_id)
        if not group:
            return jsonify({"error": "Group not found"}), 404

        existing = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
        if existing:
            return jsonify({"message": "Already a member", "role": existing.role}), 200

        if not group.is_active:
            return jsonify({"error": "This group has been deactivated"}), 403

        if group.privacy == "private":
            # No invite/request flow yet.
            return jsonify({"error": "This group is invite-only"}), 403

        membership = GroupMember(group_id=group_id, user_id=user_id, role="member")
        db.session.add(membership)
        group.member_count = (group.member_count or 0) + 1
        db.session.commit()

        return jsonify({
            "message": "Joined",
            "role": membership.role,
            "member_count": group.member_count,
        }), 201


    @app.route("/groups/<int:group_id>/leave", methods=["POST"])
    @require_csrf
    def leave_group(group_id):
        """
        A sole admin can't leave while other members remain - there's no
        promote-another-admin endpoint yet, so this would strand the group.
        If they're the last member overall, leaving is allowed (the group
        is simply left empty for now - cleanup/deletion is a later item).
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        group = db.session.get(Group, group_id)
        if not group:
            return jsonify({"error": "Group not found"}), 404

        membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
        if not membership:
            return jsonify({"message": "Not a member"}), 200

        if membership.role == "admin":
            other_admins = GroupMember.query.filter(
                GroupMember.group_id == group_id,
                GroupMember.role == "admin",
                GroupMember.user_id != user_id,
            ).count()
            other_members = GroupMember.query.filter(
                GroupMember.group_id == group_id,
                GroupMember.user_id != user_id,
            ).count()
            if other_admins == 0 and other_members > 0:
                return jsonify({
                    "error": "You're the only admin - promote another member to admin before leaving"
                }), 400

        db.session.delete(membership)
        group.member_count = max(0, (group.member_count or 1) - 1)
        db.session.commit()

        return jsonify({"message": "Left group", "member_count": group.member_count})


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
            "body": post.body if not post.is_removed else None,
            "is_removed": post.is_removed,
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
            "body": comment.body if not comment.is_removed else None,
            "is_removed": comment.is_removed,
            "author": _display_name(author) if author else "Deleted user",
            "author_id": comment.user_id,
            "marked_helpful": comment.marked_helpful,
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
        if not group.is_active:
            return jsonify({"error": "This group has been deactivated"}), 403

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
            GroupPost.query.filter_by(group_id=group_id, post_type=post_type, is_removed=False)
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
        if not group.is_active:
            return jsonify({"error": "This group has been deactivated"}), 403

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

        if post.user_id != user_id and should_notify(post.user_id, "community"):
            commenter = db.session.get(User, user_id)
            group = db.session.get(Group, group_id)
            db.session.add(Notification(
                user_id=post.user_id,
                type="group_comment",
                title="New comment" if post.post_type == "post" else "New reply",
                body=f"{_display_name(commenter)} commented on your {post.post_type} in {group.name if group else 'a group'}",
                related_type="group_post",
                related_id=post.id,
            ))
            send_push_notification(
                post.user_id,
                "New comment" if post.post_type == "post" else "New reply",
                f"{_display_name(commenter)} commented on your {post.post_type} in {group.name if group else 'a group'}",
            )

        db.session.commit()

        return jsonify(_serialize_group_post_comment(comment)), 201


    @app.route("/groups/<int:group_id>/posts/<int:post_id>/comments/<int:comment_id>/helpful", methods=["POST"])
    @require_csrf
    def mark_comment_helpful(group_id, post_id, comment_id):
        """
        Lets the ORIGINAL POST author mark a reply as helpful, once, awarding
        the replier community_helpful_reply XP (Chunk 7). Restricted to the
        post author (not any group member) so this can't be used to farm XP
        for friends, and restricted to Questions-tab posts since "helpful"
        only makes sense as an answer-quality signal there.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        group, membership = _get_group_visible(group_id, user_id)
        if not group:
            return jsonify({"error": "Group not found"}), 404

        post = db.session.get(GroupPost, post_id)
        if not post or post.group_id != group_id:
            return jsonify({"error": "Post not found"}), 404
        if post.post_type != "question":
            return jsonify({"error": "Only replies on Questions-tab posts can be marked helpful"}), 400
        if post.user_id != user_id:
            return jsonify({"error": "Only the person who asked the question can mark a reply helpful"}), 403

        comment = db.session.get(GroupPostComment, comment_id)
        if not comment or comment.group_post_id != post_id:
            return jsonify({"error": "Comment not found"}), 404
        if comment.user_id == user_id:
            return jsonify({"error": "You can't mark your own reply helpful"}), 400
        if comment.marked_helpful:
            return jsonify({"message": "Already marked helpful"}), 200

        comment.marked_helpful = True
        xp_awarded = award_xp(
            comment.user_id, "community_helpful_reply", XP_COMMUNITY_HELPFUL_REPLY, related_id=comment.id,
        )
        newly_unlocked = check_and_unlock_achievements(comment.user_id) if xp_awarded else []
        db.session.commit()

        return jsonify({
            "message": "Marked helpful",
            "xp_awarded": XP_COMMUNITY_HELPFUL_REPLY if xp_awarded else 0,
            "newly_unlocked_achievements": newly_unlocked,
        })


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
            if post.user_id != user_id and should_notify(post.user_id, "community"):
                liker = db.session.get(User, user_id)
                db.session.add(Notification(
                    user_id=post.user_id,
                    type="group_like",
                    title="New like",
                    body=f"{_display_name(liker)} liked your post",
                    related_type="group_post",
                    related_id=post.id,
                ))
                send_push_notification(
                    post.user_id,
                    "New like",
                    f"{_display_name(liker)} liked your post",
                    data={"screen": "notifications", "related_type": "group_post", "related_id": post.id},
                )
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
            if post.user_id != user_id and should_notify(post.user_id, "community"):
                voter = db.session.get(User, user_id)
                db.session.add(Notification(
                    user_id=post.user_id,
                    type="group_vote",
                    title="New vote",
                    body=f"{_display_name(voter)} voted on your question",
                    related_type="group_post",
                    related_id=post.id,
                ))
                send_push_notification(
                    post.user_id,
                    "New vote",
                    f"{_display_name(voter)} voted on your question",
                    data={"screen": "notifications", "related_type": "group_post", "related_id": post.id},
                )
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


    # ---------- Group members ----------

    def _serialize_group_member(membership):
        user = db.session.get(User, membership.user_id)
        return {
            "user_id": membership.user_id,
            "display_name": _display_name(user) if user else "Deleted user",
            "avatar_url": (get_signed_url(user.avatar_storage_path, expires_in=3600, bucket="avatars") if user and user.avatar_storage_path else None),
            "role": membership.role,
            "joined_at": membership.joined_at.isoformat() if membership.joined_at else None,
        }


    @app.route("/groups/<int:group_id>/members")
    def list_group_members(group_id):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        group, membership = _get_group_visible(group_id, user_id)
        if not group:
            return jsonify({"error": "Group not found"}), 404

        members = GroupMember.query.filter_by(group_id=group_id).all()
        members.sort(key=lambda m: (0 if m.role == "admin" else 1, m.joined_at or datetime.min))

        return jsonify({"members": [_serialize_group_member(m) for m in members]})


    @app.route("/groups/<int:group_id>/members/<int:target_user_id>", methods=["PATCH"])
    @require_csrf
    def update_group_member_role(group_id, target_user_id):
        """
        Promote a member to admin, or demote an admin to member. Admin-only.
        Refuses to demote the last remaining admin - they'd need to promote
        someone else first (this is also how a sole admin unblocks
        themselves from the leave_group restriction).
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        group = db.session.get(Group, group_id)
        if not group:
            return jsonify({"error": "Group not found"}), 404

        requester = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
        if not requester or requester.role != "admin":
            return jsonify({"error": "Only group admins can change member roles"}), 403

        target = GroupMember.query.filter_by(group_id=group_id, user_id=target_user_id).first()
        if not target:
            return jsonify({"error": "Member not found"}), 404

        data = request.get_json(silent=True) or {}
        role = (data.get("role") or "").strip().lower()
        if role not in ("admin", "member"):
            return jsonify({"error": "role must be 'admin' or 'member'"}), 400

        if role == "member" and target.role == "admin":
            other_admins = GroupMember.query.filter(
                GroupMember.group_id == group_id,
                GroupMember.role == "admin",
                GroupMember.user_id != target_user_id,
            ).count()
            if other_admins == 0:
                return jsonify({"error": "Can't demote the only admin - promote someone else first"}), 400

        was_admin = target.role == "admin"
        target.role = role

        if role == "admin" and not was_admin and should_notify(target_user_id, "community"):
            group = db.session.get(Group, group_id)
            db.session.add(Notification(
                user_id=target_user_id,
                type="group_promoted",
                title="You're now an admin",
                body=f"You were made an admin of {group.name if group else 'a group'}",
                related_type="group",
                related_id=group_id,
            ))
            send_push_notification(
                target_user_id,
                "You're now an admin",
                f"You were made an admin of {group.name if group else 'a group'}",
            )

        db.session.commit()

        return jsonify(_serialize_group_member(target))


    @app.route("/groups/<int:group_id>/members/<int:target_user_id>", methods=["DELETE"])
    @require_csrf
    def remove_group_member(group_id, target_user_id):
        """
        Admin-only kick. Self-removal is deliberately rejected here - use
        POST /groups/<id>/leave instead, which has its own sole-admin
        protection. An admin target must be demoted first (kicking an
        admin outright would bypass that protection entirely).
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        if target_user_id == user_id:
            return jsonify({"error": "Use POST /groups/<id>/leave to remove yourself"}), 400

        group = db.session.get(Group, group_id)
        if not group:
            return jsonify({"error": "Group not found"}), 404

        requester = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
        if not requester or requester.role != "admin":
            return jsonify({"error": "Only group admins can remove members"}), 403

        target = GroupMember.query.filter_by(group_id=group_id, user_id=target_user_id).first()
        if not target:
            return jsonify({"error": "Member not found"}), 404

        if target.role == "admin":
            return jsonify({"error": "Demote this admin before removing them"}), 400

        db.session.delete(target)
        group.member_count = max(0, (group.member_count or 1) - 1)
        db.session.commit()

        return jsonify({"message": "Member removed", "member_count": group.member_count})


    # ---------- Group files ----------

    def _serialize_group_file(group_file):
        document = db.session.get(Document, group_file.document_id)
        content = (
            db.session.get(DocumentContent, document.document_content_id)
            if document and document.document_content_id else None
        )
        sharer = db.session.get(User, group_file.shared_by_user_id)
        view_url = None
        if content and content.status == "ready":
            view_url = get_signed_url(content.storage_path, bucket="documents")
        return {
            "id": group_file.id,
            "group_id": group_file.group_id,
            "document_id": group_file.document_id,
            "title": document.title if document else None,
            "file_type": content.file_type if content else None,
            "file_size_bytes": content.file_size_bytes if content else None,
            "page_count": content.page_count if content else None,
            "view_url": view_url,
            "shared_by": _display_name(sharer) if sharer else "Deleted user",
            "shared_by_user_id": group_file.shared_by_user_id,
            "created_at": group_file.created_at.isoformat() if group_file.created_at else None,
        }


    @app.route("/groups/<int:group_id>/files", methods=["POST"])
    @require_csrf
    def share_group_file(group_id):
        """
        Shares one of the caller's OWN ready Documents into the group's
        Files tab. Does not touch storage - just links the existing
        Document row, same dedup-friendly pattern as the rest of the app.
        """
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

        document_id = data.get("document_id")
        if not isinstance(document_id, int) or isinstance(document_id, bool):
            return jsonify({"error": "document_id is required"}), 400

        document = db.session.get(Document, document_id)
        if not document or document.user_id != user_id or document.is_removed:
            return jsonify({"error": "Document not found"}), 404

        content = (
            db.session.get(DocumentContent, document.document_content_id)
            if document.document_content_id else None
        )
        effective_status = content.status if (content and document.status != "uploading") else document.status
        if effective_status != "ready":
            return jsonify({"error": f"Document is not ready to share (status: {effective_status})"}), 400

        existing = GroupFile.query.filter_by(group_id=group_id, document_id=document_id).first()
        if existing:
            return jsonify(_serialize_group_file(existing)), 200

        group_file = GroupFile(group_id=group_id, document_id=document_id, shared_by_user_id=user_id)
        db.session.add(group_file)
        db.session.commit()

        return jsonify(_serialize_group_file(group_file)), 201


    @app.route("/groups/<int:group_id>/files")
    def list_group_files(group_id):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        group, membership = _get_group_visible(group_id, user_id)
        if not group:
            return jsonify({"error": "Group not found"}), 404

        files = (
            GroupFile.query.filter_by(group_id=group_id)
            .order_by(GroupFile.created_at.desc())
            .all()
        )

        return jsonify({"files": [_serialize_group_file(f) for f in files]})


    @app.route("/groups/<int:group_id>/files/<int:file_id>", methods=["DELETE"])
    @require_csrf
    def remove_group_file(group_id, file_id):
        """Removable by whoever shared it, or by any group admin."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        group = db.session.get(Group, group_id)
        if not group:
            return jsonify({"error": "Group not found"}), 404

        group_file = db.session.get(GroupFile, file_id)
        if not group_file or group_file.group_id != group_id:
            return jsonify({"error": "File not found"}), 404

        membership = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
        is_admin = bool(membership and membership.role == "admin")

        if group_file.shared_by_user_id != user_id and not is_admin:
            return jsonify({"error": "Only the person who shared this file or a group admin can remove it"}), 403

        db.session.delete(group_file)
        db.session.commit()

        return jsonify({"message": "File removed"})
