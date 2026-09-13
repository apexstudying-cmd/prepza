"""Focused regression checks for Chunk 2 chat metadata hooks."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import session

import chat_interactions as ci
from app import app


@pytest.fixture(autouse=True)
def request_context():
    with app.test_request_context('/'):
        yield


def test_post_records_kind_and_never_needs_plaintext_emoji(monkeypatch):
    execute = Mock()
    monkeypatch.setattr(ci, 'ensure_chat_metadata_schema', Mock())
    monkeypatch.setattr(ci.db.session, 'execute', execute)
    monkeypatch.setattr(ci.db.session, 'commit', Mock())
    response = app.response_class(response=json.dumps({'message': {
        'id': 44, 'conversation_id': 12, 'sender_id': 7, 'body': 'ciphertext',
    }}), status=201, mimetype='application/json')
    with app.test_request_context('/chats/12/messages', method='POST', json={
        'body': 'ciphertext', 'nonce': 'nonce', 'kind': 'reaction',
    }):
        returned = ci._chat_metadata_after_request(response)
    assert returned.get_json()['message']['kind'] == 'reaction'
    sql = str(execute.call_args.args[0])
    assert 'chat_message_meta' in sql
    assert 'emoji' not in sql.lower()


def test_message_list_adds_kind_and_read_receipt_fields(monkeypatch):
    participant = SimpleNamespace(user_id=8, last_read_at=None)
    fake_query = Mock()
    fake_query.filter_by.return_value.all.return_value = [participant]
    monkeypatch.setattr(ci, 'ConversationParticipant', SimpleNamespace(query=fake_query))
    monkeypatch.setattr(ci, '_message_kind_map', Mock(return_value={44: 'text'}))
    response = app.response_class(response=json.dumps({'messages': [{
        'id': 44, 'conversation_id': 12, 'sender_id': 7,
        'body': 'ciphertext', 'created_at': '2026-09-13T10:00:00+00:00',
    }]}), status=200, mimetype='application/json')
    with app.test_request_context('/chats/12/messages', method='GET'):
        session['user_id'] = 7
        returned = ci._chat_metadata_after_request(response)
    item = returned.get_json()['messages'][0]
    assert item['kind'] == 'text'
    assert item['read_by_count'] == 0
    assert item['read_by_all'] is False


def test_reaction_events_are_removed_from_unread_badges(monkeypatch):
    participant = SimpleNamespace(user_id=7, last_read_at=None)
    fake_query = Mock()
    fake_query.filter_by.return_value.first.return_value = participant
    monkeypatch.setattr(ci, 'ConversationParticipant', SimpleNamespace(query=fake_query))
    monkeypatch.setattr(ci, '_reaction_unread_count', Mock(return_value=1))
    monkeypatch.setattr(ci, 'ensure_chat_metadata_schema', Mock())
    response = app.response_class(response=json.dumps({'chats': [{
        'id': 12, 'name': 'Study group', 'unread_count': 1,
        'last_message': 'ciphertext', 'last_message_at': '2026-09-13T10:00:00+00:00',
    }]}), status=200, mimetype='application/json')
    with app.test_request_context('/chats', method='GET'):
        session['user_id'] = 7
        returned = ci._chat_metadata_after_request(response)
    chat = returned.get_json()['chats'][0]
    assert chat['unread_count'] == 0
    assert chat['last_message'] == 'Encrypted message'
