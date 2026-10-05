"""Runtime check for the real Redis-backed chat worker path.

This is intentionally different from scripts/test_realtime_runtime.py:
that suite uses Socket.IO's in-process test client and REDIS_URL=memory://.
This script requires the Docker Redis service and starts the real
chat_event_worker.py process.

It proves:
1. a Redis Stream event can be enqueued;
2. the real worker process consumes it;
3. the worker acknowledges it in the consumer group;
4. the worker publishes the resulting Socket.IO event to the configured
   prepza-realtime Redis channel.

It does not claim that a browser received the event; that final client-facing
hop is a separate deployment-level check.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid

import redis


def _wait_for_redis(client):
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            client.ping()
            return
        except redis.RedisError:
            time.sleep(0.2)
    raise AssertionError("Redis did not become reachable")


def _pending_count(client, stream, group):
    info = client.xpending(stream, group)
    return int(info["pending"] if isinstance(info, dict) else info[0])


def main():
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url.startswith(("redis://", "rediss://")):
        raise SystemExit("FAIL: REDIS_URL must be a real redis:// or rediss:// URL")

    suffix = uuid.uuid4().hex
    stream = f"prepza:test:chat-worker:{suffix}"
    group = f"prepza-test-group-{suffix}"
    consumer = f"prepza-test-consumer-{suffix}"

    env = os.environ.copy()
    env.update(
        {
            "PREPZA_CHAT_EVENT_STREAM": stream,
            "PREPZA_CHAT_EVENT_GROUP": group,
            "PREPZA_CHAT_EVENT_CONSUMER": consumer,
        }
    )

    client = redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    worker = None
    pubsub = client.pubsub(ignore_subscribe_messages=True)

    try:
        _wait_for_redis(client)
        pubsub.subscribe("prepza-realtime")

        worker = subprocess.Popen(
            [sys.executable, "chat_event_worker.py"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Give the real worker enough time to import Flask/Socket.IO and
        # create the consumer group.
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                groups = client.xinfo_groups(stream)
                if any(g["name"] == group for g in groups):
                    break
            except redis.ResponseError:
                pass
            if worker.poll() is not None:
                output = worker.stdout.read() if worker.stdout else ""
                raise AssertionError(
                    f"chat_event_worker.py exited early with {worker.returncode}: {output}"
                )
            time.sleep(0.2)
        else:
            raise AssertionError("chat_event_worker.py did not create its Redis consumer group")

        payload = {
            "id": 987654321,
            "conversation_id": 123456789,
            "body": "ciphertext-runtime-check",
            "sender_id": 42,
        }
        message_id = client.xadd(
            stream,
            {
                "event": "chat:message",
                "conversation_id": str(payload["conversation_id"]),
                "payload": json.dumps(payload, separators=(",", ":")),
                "created_at": str(time.time()),
            },
        )

        published = None
        deadline = time.time() + 15
        while time.time() < deadline:
            published = pubsub.get_message(timeout=0.2)
            if published and published.get("type") == "message":
                try:
                    decoded = json.loads(published["data"])
                except (TypeError, json.JSONDecodeError):
                    decoded = None
                if (
                    isinstance(decoded, dict)
                    and decoded.get("method") == "emit"
                    and decoded.get("event") == "chat:message"
                    and decoded.get("room") == f"chat:{payload['conversation_id']}"
                    and decoded.get("data") == [payload]
                ):
                    break
                published = None

            if _pending_count(client, stream, group) == 0 and published is None:
                # Ack proves consumption, but keep polling briefly for the
                # subsequent Socket.IO Redis publication.
                pass
        else:
            raise AssertionError("Timed out waiting for worker Redis consumption/publication")

        if _pending_count(client, stream, group) != 0:
            raise AssertionError("Worker consumed the event but did not acknowledge it")

        if not published:
            raise AssertionError("Worker acknowledged the event but no Socket.IO Redis publication was observed")

        print("PASS: real Redis chat worker consumed and acknowledged the event")
        print("PASS: worker published chat:message onto prepza-realtime for the conversation room")
        print(f"PASS: Redis stream entry {message_id} was processed")

    finally:
        pubsub.close()
        if worker is not None and worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)
        try:
            client.xgroup_destroy(stream, group)
        except redis.RedisError:
            pass
        try:
            client.delete(stream)
        except redis.RedisError:
            pass
        client.close()


if __name__ == "__main__":
    main()
