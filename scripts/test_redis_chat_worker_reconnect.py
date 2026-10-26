"""Verify the real Redis-backed chat worker survives a transient Redis restart.

Run in an isolated CI environment with Docker available, a disposable Redis
container named by PREPZA_REDIS_CONTAINER, and a disposable DATABASE_URL.
This intentionally tests a real worker process and real Redis Streams.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid

import redis


def _wait_for_redis(client, timeout: int = 25) -> None:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            client.ping()
            return
        except redis.RedisError as exc:
            last_error = exc
            time.sleep(0.25)
    raise AssertionError(f"Redis did not recover within {timeout}s: {last_error}")


def _pending_count(client, stream: str, group: str) -> int:
    info = client.xpending(stream, group)
    return int(info["pending"] if isinstance(info, dict) else info[0])


def _wait_for_group(client, stream: str, group: str, worker) -> None:
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            if any(row["name"] == group for row in client.xinfo_groups(stream)):
                return
        except redis.ResponseError:
            pass
        if worker.poll() is not None:
            output = worker.stdout.read() if worker.stdout else ""
            raise AssertionError(
                f"chat_event_worker.py exited early ({worker.returncode}): {output}"
            )
        time.sleep(0.2)
    raise AssertionError("chat worker did not establish its Redis Stream consumer group")


def main() -> int:
    redis_url = os.environ.get("REDIS_URL", "").strip()
    container = os.environ.get("PREPZA_REDIS_CONTAINER", "").strip()
    if not redis_url.startswith(("redis://", "rediss://")):
        raise SystemExit("FAIL: REDIS_URL must point to the disposable real Redis service")
    if not container:
        raise SystemExit("FAIL: PREPZA_REDIS_CONTAINER must name the disposable Redis container")

    suffix = uuid.uuid4().hex
    stream = f"prepza:test:chat-worker-reconnect:{suffix}"
    group = f"prepza-test-reconnect-group-{suffix}"
    consumer = f"prepza-test-reconnect-consumer-{suffix}"
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
        socket_timeout=3,
    )
    worker = None
    pubsub = None

    try:
        _wait_for_redis(client)
        worker = subprocess.Popen(
            [sys.executable, "chat_event_worker.py"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        _wait_for_group(client, stream, group, worker)
        print("PASS: real chat worker is connected before the Redis interruption")

        # Restart the same container, retaining its isolated stream/group data.
        # This creates a genuine, short connection failure for the live worker.
        restarted = subprocess.run(
            ["docker", "restart", container],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        print(f"PASS: disposable Redis container restarted ({restarted.stdout.strip()})")
        _wait_for_redis(client)

        pubsub = client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe("prepza-realtime")
        # Drain the subscription confirmation before enqueuing the event.
        deadline = time.time() + 5
        while time.time() < deadline:
            message = pubsub.get_message(timeout=0.2)
            if message is not None:
                break

        payload = {
            "id": 987654322,
            "conversation_id": 123456790,
            "body": "ciphertext-after-redis-restart",
            "sender_id": 43,
        }
        stream_id = client.xadd(
            stream,
            {
                "event": "chat:message",
                "conversation_id": str(payload["conversation_id"]),
                "payload": json.dumps(payload, separators=(",", ":")),
                "created_at": str(time.time()),
            },
        )

        published = False
        deadline = time.time() + 25
        while time.time() < deadline:
            if worker.poll() is not None:
                output = worker.stdout.read() if worker.stdout else ""
                raise AssertionError(
                    f"chat worker exited after Redis restart ({worker.returncode}): {output}"
                )
            message = pubsub.get_message(timeout=0.25)
            if message and message.get("type") == "message":
                try:
                    decoded = json.loads(message["data"])
                except (TypeError, json.JSONDecodeError):
                    decoded = None
                if (
                    isinstance(decoded, dict)
                    and decoded.get("method") == "emit"
                    and decoded.get("event") == "chat:message"
                    and decoded.get("room") == f"chat:{payload['conversation_id']}"
                    and decoded.get("data") == [payload]
                ):
                    published = True
                    break

        if not published:
            raise AssertionError(
                "worker did not publish a queued chat event after Redis recovered"
            )

        # Publication happens inside the handler just before XACK. Allow the
        # worker's acknowledgement to complete instead of racing that boundary.
        ack_deadline = time.time() + 5
        while time.time() < ack_deadline and _pending_count(client, stream, group) != 0:
            if worker.poll() is not None:
                output = worker.stdout.read() if worker.stdout else ""
                raise AssertionError(
                    f"chat worker exited before acknowledging the event: {output}"
                )
            time.sleep(0.05)
        if _pending_count(client, stream, group) != 0:
            raise AssertionError("worker published the event but did not acknowledge it")

        print("PASS: chat worker reconnected after Redis restart")
        print("PASS: post-restart stream event was published to the correct conversation")
        print(f"PASS: stream entry {stream_id} was acknowledged")

    finally:
        if pubsub is not None:
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
