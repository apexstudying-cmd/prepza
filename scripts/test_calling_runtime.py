"""Runtime regression checks for authenticated 1:1 call signaling."""
import pytest
from unittest.mock import patch

from realtime_server import _active_calls, app, socketio
from runtime_test_fixtures import runtime_test_users

_USERS = {}


@pytest.fixture(scope="module", autouse=True)
def runtime_users():
    with runtime_test_users() as users:
        _USERS.update(users)
        yield users
    _USERS.clear()


def _session_client(role=None):
    flask_client = app.test_client()
    if role is not None:
        user = _USERS[role]
        with flask_client.session_transaction() as session:
            session['user_id'] = user.id
            session['_session_version'] = user.session_version
    client = socketio.test_client(app, flask_test_client=flask_client)
    if client.is_connected():
        client.get_received()
    return client


def _events(client, name):
    return [event for event in client.get_received() if event['name'] == name]


def test_call_invite_requires_exact_two_member_conversation():
    client = _session_client("primary")
    try:
        with patch('realtime_server.call_participants', return_value=[_USERS['primary'].id, _USERS['peer'].id, _USERS['attacker'].id]):
            result = client.emit('call:invite', {'call_id': 'test-call-1234', 'conversation_id': 12, 'to_user_id': _USERS['peer'].id, 'kind': 'voice'}, callback=True)
        assert result == {'ok': False}
    finally:
        client.disconnect()


def test_call_invite_routes_only_to_authenticated_peer():
    caller = _session_client("primary")
    callee = _session_client("peer")
    observer = _session_client("attacker")
    try:
        with patch('realtime_server.call_participants', return_value=[_USERS['primary'].id, _USERS['peer'].id]), patch('realtime_server.db.session.get') as get_user:
            get_user.return_value = type('UserStub', (), {'display_name': 'Caller', 'session_version': 1, 'is_suspended': False})()
            result = caller.emit('call:invite', {'call_id': 'test-call-1234', 'conversation_id': 12, 'to_user_id': _USERS['peer'].id, 'kind': 'voice'}, callback=True)
        assert result == {'ok': True}
        assert len(_events(callee, 'call:incoming')) == 1
        assert _events(observer, 'call:incoming') == []
    finally:
        _active_calls.clear()
        caller.disconnect(); callee.disconnect(); observer.disconnect()


def test_call_signaling_requires_membership_in_active_call():
    caller = _session_client("primary")
    attacker = _session_client("attacker")
    try:
        with patch('realtime_server.call_participants', return_value=[_USERS['primary'].id, _USERS['peer'].id]), patch('realtime_server.db.session.get') as get_user:
            get_user.return_value = type('UserStub', (), {'display_name': 'Caller', 'session_version': 1, 'is_suspended': False})()
            assert caller.emit('call:invite', {'call_id': 'test-call-5678', 'conversation_id': 12, 'to_user_id': _USERS['peer'].id, 'kind': 'video'}, callback=True) == {'ok': True}
        result = attacker.emit('call:offer', {'call_id': 'test-call-5678', 'conversation_id': 12, 'to_user_id': _USERS['peer'].id, 'payload': {'type': 'offer', 'sdp': 'fake'}}, callback=True)
        assert result == {'ok': False}
    finally:
        _active_calls.clear()
        caller.disconnect(); attacker.disconnect()


def test_call_end_clears_active_call():
    caller = _session_client("primary")
    callee = _session_client("peer")
    try:
        with patch('realtime_server.call_participants', return_value=[_USERS['primary'].id, _USERS['peer'].id]), patch('realtime_server.db.session.get') as get_user:
            get_user.return_value = type('UserStub', (), {'display_name': 'Caller', 'session_version': 1, 'is_suspended': False})()
            assert caller.emit('call:invite', {'call_id': 'test-call-9012', 'conversation_id': 12, 'to_user_id': _USERS['peer'].id, 'kind': 'video'}, callback=True) == {'ok': True}
        result = caller.emit('call:end', {'call_id': 'test-call-9012', 'conversation_id': 12, 'to_user_id': _USERS['peer'].id}, callback=True)
        assert result == {'ok': True}
        assert 'test-call-9012' not in _active_calls
        assert len(_events(callee, 'call:ended')) == 1
    finally:
        _active_calls.clear()
        caller.disconnect(); callee.disconnect()
