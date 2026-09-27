from chat_event_queue import decode_event


def test_decode_event_round_trips_payload():
    event = decode_event({
        "event": "chat:message",
        "conversation_id": "42",
        "payload": '{"id": 7, "conversation_id": 42}',
        "created_at": "123.5",
    })
    assert event["event"] == "chat:message"
    assert event["conversation_id"] == 42
    assert event["payload"]["id"] == 7
    assert event["created_at"] == 123.5
