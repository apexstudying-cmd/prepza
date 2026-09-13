"""Focused regression checks for Chunk 2 chat metadata and UX contracts."""
import json
from datetime import datetime, timedelta

import pytest
from flask import session
from sqlalchemy import text

from app import Conversation, ConversationParticipant, Message, User, app, db
from chat_interactions import _chat_metadata_after_request, ensure_chat_metadata_schema


@pytest.fixture(autouse=True)
def application_context():
    with app.app_context():
        db.create_all()
        ensure_chat_metadata_schema()
        yield
        db.session.remove()


def _make_chat():
    stamp = str(datetime.utcnow().timestamp()).replace('.', '')
    one = User(email=f'chunk2-a-{stamp}@example.test', password_hash='x')
    two = User(email=f'chunk2-b-{stamp}@example.test', password_hash='x')
    db.session.add_all([one, two])
    db.session.flush()
    chat = Conversation(is_group=False, created_by=one.id, status='accepted')
    db.session.add(chat)
    db.session.flush()
    db.session.add_all([
        ConversationParticipant(conversation_id=chat.id, user_id=one.id),
        ConversationParticipant(conversation_id=chat.id, user_id=two.id),
    ])
    db.session.commit()
    return one, two, chat


def _cleanup(one, two, chat):
    try:
        db.session.execute(text('DELETE FROM chat_message_meta WHERE conversation_id = :id'), {'id': chat.id})
        ConversationParticipant.query.filter_by(conversation_id=chat.id).delete(synchronize_session=False)
        Message.query.filter_by(conversation_id=chat.id).delete(synchronize_session=False)
        Conversation.query.filter_by(id=chat.id).delete(synchronize_session=False)
        User.query.filter(User.id.in_([one.id, two.id])).delete(synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()


def test_reaction_metadata_is_recorded_without_plaintext_emoji():
    one, two, chat = _make_chat()
    try:
        message = Message(conversation_id=chat.id, sender_id=one.id, body='opaque-ciphertext', nonce='opaque-nonce')
        db.session.add(message)
        db.session.commit()
        response = app.response_class(response=json.dumps({'message': {
            'id': message.id, 'conversation_id': chat.id, 'sender_id': one.id, 'body': 'opaque-ciphertext',
        }}), status=201, mimetype='application/json')
        with app.test_request_context(f'/chats/{chat.id}/messages', method='POST', json={
            'body': 'opaque-ciphertext', 'nonce': 'opaque-nonce', 'kind': 'reaction',
        }):
            returned = _chat_metadata_after_request(response)
        assert returned is response
        row = db.session.execute(text('SELECT kind FROM chat_message_meta WHERE message_id = :id'), {'id': message.id}).first()
        assert row and row[0] == 'reaction'
    finally:
        _cleanup(one, two, chat)


def test_message_list_gets_read_receipt_counts_and_kind():
    one, two, chat = _make_chat()
    try:
        created = datetime.utcnow() - timedelta(seconds=2)
        message = Message(conversation_id=chat.id, sender_id=one.id, body='opaque-ciphertext', nonce='opaque-nonce', created_at=created)
        db.session.add(message)
        db.session.flush()
        ConversationParticipant.query.filter_by(conversation_id=chat.id, user_id=two.id).update({'last_read_at': datetime.utcnow()})
        db.session.execute(text('INSERT INTO chat_message_meta (message_id, conversation_id, kind) VALUES (:m, :c, :k)'), {'m': message.id, 'c': chat.id, 'k': 'text'})
        db.session.commit()
        response = app.response_class(response=json.dumps({'messages': [{
            'id': message.id, 'conversation_id': chat.id, 'sender_id': one.id,
            'body': 'opaque-ciphertext', 'created_at': created.isoformat(),
        }]}), status=200, mimetype='application/json')
        with app.test_request_context(f'/chats/{chat.id}/messages', method='GET'):
            session['user_id'] = one.id
            returned = _chat_metadata_after_request(response)
        item = returned.get_json()['messages'][0]
        assert item['kind'] == 'text'
        assert item['read_by_count'] == 1
        assert item['read_by_all'] is True
    finally:
        _cleanup(one, two, chat)


def test_reaction_events_do_not_create_unread_badges():
    one, two, chat = _make_chat()
    try:
        message = Message(conversation_id=chat.id, sender_id=two.id, body='opaque-reaction-ciphertext', nonce='opaque-nonce')
        db.session.add(message)
        db.session.flush()
        db.session.execute(text('INSERT INTO chat_message_meta (message_id, conversation_id, kind) VALUES (:m, :c, :k)'), {'m': message.id, 'c': chat.id, 'k': 'reaction'})
        db.session.commit()
        response = app.response_class(response=json.dumps({'chats': [{
            'id': chat.id, 'is_group': False, 'name': 'Test', 'last_message': 'ciphertext',
            'last_message_at': datetime.utcnow().isoformat(), 'unread_count': 1,
        }]}), status=200, mimetype='application/json')
        with app.test_request_context('/chats', method='GET'):
            session['user_id'] = one.id
            returned = _chat_metadata_after_request(response)
        chat_payload = returned.get_json()['chats'][0]
        assert chat_payload['unread_count'] == 0
        assert chat_payload['last_message'] == 'Encrypted message'
    finally:
        _cleanup(one, two, chat)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
