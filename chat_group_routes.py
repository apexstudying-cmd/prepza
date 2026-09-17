"""Membership controls for Prepza's WhatsApp-style multi-user chats.

These routes deliberately use Conversation/ConversationParticipant, not the
separate community Group model. A chat group is therefore the same message
thread as a direct chat; the only structural difference is multiple active
participant user IDs. Membership changes advance the encrypted group epoch so
new messages use a fresh key and removed members cannot decrypt future traffic.
"""
from datetime import datetime

from flask import jsonify, request, session
from sqlalchemy import text

from app import (
    app,
    db,
    Conversation,
    ConversationParticipant,
    User,
    _active_participant,
    _serialize_conversation_detail,
    require_csrf,
)


MAX_CHAT_GROUP_MEMBERS = 100


def _group_for_member_change(conversation_id, user_id):
    conversation = db.session.get(Conversation, conversation_id)
    if not conversation or not conversation.is_group:
        return None, None
    requester = _active_participant(conversation_id, user_id)
    if not requester:
        return None, None
    return conversation, requester


def _active_group_member_count(conversation_id):
    return ConversationParticipant.query.filter_by(
        conversation_id=conversation_id, left_at=None
    ).count()


def _current_group_key_epoch(conversation_id):
    value = db.session.execute(
        text("SELECT key_epoch FROM conversation WHERE id = :conversation_id"),
        {"conversation_id": conversation_id},
    ).scalar_one_or_none()
    return int(value or 0)


@app.route("/chats/<int:conversation_id>/members", methods=["POST"])
@require_csrf
def add_chat_group_members(conversation_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    conversation, requester = _group_for_member_change(conversation_id, user_id)
    if not conversation:
        return jsonify({"error": "Group conversation not found"}), 404
    if requester.role != "admin":
        return jsonify({"error": "Only group admins can add members"}), 403

    data = request.get_json(silent=True) or {}
    ids = data.get("user_ids")
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "user_ids must be a non-empty list"}), 400
    if len(ids) > MAX_CHAT_GROUP_MEMBERS:
        return jsonify({"error": f"A group can have at most {MAX_CHAT_GROUP_MEMBERS} members"}), 400

    try:
        requested_ids = {int(value) for value in ids}
    except (TypeError, ValueError):
        return jsonify({"error": "user_ids must contain integers"}), 400

    requested_ids.discard(user_id)
    if not requested_ids:
        return jsonify({"error": "No new members were supplied"}), 400

    existing_ids = {
        row.user_id
        for row in ConversationParticipant.query.filter_by(
            conversation_id=conversation_id
        ).all()
    }
    new_ids = requested_ids - existing_ids
    if not new_ids:
        return jsonify({"conversation": _serialize_conversation_detail(conversation, user_id), "added_user_ids": []}), 200

    current_count = _active_group_member_count(conversation_id)
    if current_count + len(new_ids) > MAX_CHAT_GROUP_MEMBERS:
        return jsonify({"error": f"A group can have at most {MAX_CHAT_GROUP_MEMBERS} active members"}), 400

    users = User.query.filter(User.id.in_(new_ids), User.is_suspended.is_(False)).all()
    valid_ids = {user.id for user in users}
    if valid_ids != new_ids:
        return jsonify({"error": "One or more users were not found or are unavailable"}), 404

    # A live E2EE group cannot safely add a member who has no registered
    # identity key: the next epoch requires an encrypted envelope for every
    # active member. Reject the membership change before mutating the group
    # rather than leaving the group waiting for an impossible key setup.
    mode = db.session.execute(
        text("SELECT e2ee_mode FROM conversation WHERE id = :conversation_id"),
        {"conversation_id": conversation_id},
    ).scalar_one_or_none()
    if mode == "group_v1":
        keyed_ids = {
            row[0]
            for row in db.session.execute(
                text("SELECT user_id FROM user_key WHERE user_id = ANY(:user_ids)"),
                {"user_ids": list(new_ids)},
            ).all()
        }
        missing_ids = sorted(new_ids - keyed_ids)
        if missing_ids:
            return jsonify({
                "error": "Every new group member must set up secure chat before they can be added",
                "missing_user_ids": missing_ids,
            }), 409

    for member_id in sorted(new_ids):
        db.session.add(ConversationParticipant(
            conversation_id=conversation_id,
            user_id=member_id,
            role="member",
        ))

    conversation.updated_at = datetime.utcnow()
    # The E2EE membership mapper rotates once per transaction. Do not also
    # bump the epoch here: doing both caused the response to report an epoch
    # older than the committed database state.
    db.session.commit()
    new_epoch = _current_group_key_epoch(conversation_id)

    return jsonify({
        "conversation": _serialize_conversation_detail(conversation, user_id),
        "added_user_ids": sorted(new_ids),
        "key_epoch": new_epoch,
    }), 201


@app.route("/chats/<int:conversation_id>/members/<int:target_user_id>", methods=["DELETE"])
@require_csrf
def remove_chat_group_member(conversation_id, target_user_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    conversation, requester = _group_for_member_change(conversation_id, user_id)
    if not conversation:
        return jsonify({"error": "Group conversation not found"}), 404
    if requester.role != "admin":
        return jsonify({"error": "Only group admins can remove members"}), 403
    if target_user_id == user_id:
        return jsonify({"error": "Use /leave to leave the group"}), 400

    target = _active_participant(conversation_id, target_user_id)
    if not target:
        return jsonify({"error": "Member not found"}), 404
    if target.role == "admin":
        return jsonify({"error": "Demote this admin before removing them"}), 400

    target.left_at = datetime.utcnow()
    conversation.updated_at = datetime.utcnow()
    # The E2EE membership mapper rotates once for this transaction. Keeping
    # rotation in one place prevents a double increment and stale response.
    db.session.commit()
    new_epoch = _current_group_key_epoch(conversation_id)

    return jsonify({
        "conversation": _serialize_conversation_detail(conversation, user_id),
        "removed_user_id": target_user_id,
        "key_epoch": new_epoch,
    })
