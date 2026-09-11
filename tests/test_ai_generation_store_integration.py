"""PostgreSQL integration tests for the reusable-generation concurrency boundary."""

from __future__ import annotations

import sys
import threading
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from ai_generation_store import claim_or_get_generation, mark_generation_failed


@pytest.fixture(scope="module")
def postgres_db():
    url = "postgresql+psycopg2://prepza:prepza@127.0.0.1:5432/prepza_test"
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS ai_generation_artifact"))
        conn.execute(
            text(
                """
                CREATE TABLE ai_generation_artifact (
                    id BIGSERIAL PRIMARY KEY,
                    fingerprint VARCHAR(64) NOT NULL UNIQUE,
                    content_hash VARCHAR(128) NOT NULL,
                    feature VARCHAR(100) NOT NULL,
                    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
                    prompt_version VARCHAR(100) NOT NULL,
                    schema_version VARCHAR(100) NOT NULL,
                    scope VARCHAR(20) NOT NULL DEFAULT 'shared',
                    owner_user_id BIGINT,
                    status VARCHAR(30) NOT NULL DEFAULT 'generating',
                    payload JSONB,
                    error_message TEXT,
                    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP WITHOUT TIME ZONE,
                    CHECK (status IN ('generating', 'ready', 'failed')),
                    CHECK (scope IN ('shared', 'private')),
                    CHECK ((scope = 'shared' AND owner_user_id IS NULL)
                        OR (scope = 'private' AND owner_user_id IS NOT NULL))
                )
                """
            )
        )

    factory = sessionmaker(bind=engine, expire_on_commit=False)

    class DBProxy:
        def __init__(self):
            self.local = threading.local()

        @property
        def session(self):
            session = getattr(self.local, "session", None)
            if session is None:
                session = factory()
                self.local.session = session
            return session

        def close(self):
            session = getattr(self.local, "session", None)
            if session is not None:
                session.close()
                self.local.session = None

    proxy = DBProxy()
    fake_app = type("FakeApp", (), {"db": proxy})
    previous_app = sys.modules.get("app")
    sys.modules["app"] = fake_app
    try:
        yield engine, proxy
    finally:
        proxy.close()
        if previous_app is None:
            sys.modules.pop("app", None)
        else:
            sys.modules["app"] = previous_app
        engine.dispose()


def _claim(fingerprint, *, scope="shared", owner_user_id=None):
    return claim_or_get_generation(
        fingerprint=fingerprint,
        content_hash="content-abc",
        feature="summary",
        parameters={"language": "English"},
        prompt_version="summary-v2",
        schema_version="schema-v2",
        scope=scope,
        owner_user_id=owner_user_id,
    )


def test_concurrent_same_fingerprint_has_one_owner(postgres_db):
    _engine, proxy = postgres_db
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        try:
            barrier.wait(timeout=5)
            results.append(_claim("a" * 64))
        except Exception as exc:  # pragma: no cover - failure is asserted below
            errors.append(exc)
        finally:
            proxy.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    assert len(results) == 2
    assert sum(result.owner for result in results) == 1
    assert {result.status for result in results} == {"generating"}
    assert len({result.artifact_id for result in results}) == 1


def test_failed_fingerprint_can_be_reclaimed(postgres_db):
    _engine, proxy = postgres_db
    first = _claim("b" * 64)
    assert first.owner is True
    mark_generation_failed(first.artifact_id, "provider failed")
    proxy.close()

    retry = _claim("b" * 64)
    assert retry.owner is True
    assert retry.status == "generating"
    proxy.close()


def test_private_scope_is_owner_specific(postgres_db):
    _engine, proxy = postgres_db
    first = _claim("c" * 64, scope="private", owner_user_id=101)
    assert first.owner is True
    proxy.close()

    second = _claim("d" * 64, scope="private", owner_user_id=202)
    assert second.owner is True
    proxy.close()


def test_shared_scope_rejects_owner(postgres_db):
    _engine, proxy = postgres_db
    with pytest.raises(ValueError):
        _claim("e" * 64, scope="shared", owner_user_id=101)
    proxy.close()
