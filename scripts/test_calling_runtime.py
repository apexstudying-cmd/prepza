"""Runtime regression checks for authenticated 1:1 call signaling."""
from unittest.mock import patch

from realtime_server import _active_calls, app, socketio


def _session_client(user_id=None):
    flask_client = app.test_client()
    if user_id is not None:
        with flask_client.session_transaction() as session:
            session['user_id'] = user_id
    client = socketio.test_client(app, flask_test_client=flask_client)
    if client.is_connected():
        client.get_received()
    return client


def _events(client, name):
    return [event for event in client.get_received() if event['name'] == name]


def test_call_invite_requires_exact_two_member_conversation():
    client = _session_client(7)
    try:
        with patch('realtime_server.call_participants', return_value=[7, 8, 9]):
            result = client.emit('call:invite', {'call_id': 'test-call-1234', 'conversation_id': 12, 'to_user_id': 8, 'kind': 'voice'}, callback=True)
        assert result == {'ok': False}
    finally:
        client.disconnect()


def test_call_invite_routes_only_to_authenticated_peer():
    caller = _session_client(7)
    callee = _session_client(8)
    observer = _session_client(9)
    try:
        with patch('realtime_server.call_participants', return_value=[7, 8]), patch('realtime_server.db.session.get') as get_user:
            get_user.return_value = type('UserStub', (), {'display_name': 'Caller'})()
            result = caller.emit('call:invite', {'call_id': 'test-call-1234', 'conversation_id': 12, 'to_user_id': 8, 'kind': 'voice'}, callback=True)
        assert result == {'ok': True}
        assert len(_events(callee, 'call:incoming')) == 1
        assert _events(observer, 'call:incoming') == []
    finally:
        _active_calls.clear()
        caller.disconnect(); callee.disconnect(); observer.disconnect()


def test_call_signaling_requires_membership_in_active_call():
    caller = _session_client(7)
    attacker = _session_client(9)
    try:
        with patch('realtime_server.call_participants', return_value=[7, 8]), patch('realtime_server.db.session.get') as get_user:
            get_user.return_value = type('UserStub', (), {'display_name': 'Caller'})()
            assert caller.emit('call:invite', {'call_id': 'test-call-5678', 'conversation_id': 12, 'to_user_id': 8, 'kind': 'video'}, callback=True) == {'ok': True}
        result = attacker.emit('call:offer', {'call_id': 'test-call-5678', 'conversation_id': 12, 'to_user_id': 8, 'payload': {'type': 'offer', 'sdp': 'fake'}}, callback=True)
        assert result == {'ok': False}
    finally:
        _active_calls.clear()
        caller.disconnect(); attacker.disconnect()


def test_call_end_clears_active_call():
    caller = _session_client(7)
    callee = _session_client(8)
    try:
        with patch('realtime_server.call_participants', return_value=[7, 8]), patch('realtime_server.db.session.get') as get_user:
            get_user.return_value = type('UserStub', (), {'display_name': 'Caller'})()
            assert caller.emit('call:invite', {'call_id': 'test-call-9012', 'conversation_id': 12, 'to_user_id': 8, 'kind': 'video'}, callback=True) == {'ok': True}
        result = caller.emit('call:end', {'call_id': 'test-call-9012', 'conversation_id': 12, 'to_user_id': 8}, callback=True)
        assert result == {'ok': True}
        assert 'test-call-9012' not in _active_calls
        assert len(_events(callee, 'call:ended')) == 1
    finally:
        _active_calls.clear()
        caller.disconnect(); callee.disconnect()
