import pytest

from ai_artifact_fingerprint import build_generation_fingerprint


def test_shared_identity_is_deterministic():
    first = build_generation_fingerprint(
        content_hash="abc",
        material_type="podcast",
        parameters={"duration_minutes": 10},
        prompt_version="podcast-v1",
        schema_version="podcast-v1",
    )
    second = build_generation_fingerprint(
        content_hash="abc",
        material_type="podcast",
        parameters={"duration_minutes": 10},
        prompt_version="podcast-v1",
        schema_version="podcast-v1",
    )
    assert first == second
    assert len(first) == 64


def test_parameters_change_identity():
    short = build_generation_fingerprint(
        content_hash="abc", material_type="podcast", parameters={"duration_minutes": 10}
    )
    long = build_generation_fingerprint(
        content_hash="abc", material_type="podcast", parameters={"duration_minutes": 20}
    )
    assert short != long


def test_prompt_and_schema_versions_change_identity():
    base = build_generation_fingerprint(content_hash="abc", material_type="summary")
    prompt = build_generation_fingerprint(
        content_hash="abc", material_type="summary", prompt_version="v2"
    )
    schema = build_generation_fingerprint(
        content_hash="abc", material_type="summary", schema_version="v2"
    )
    assert base != prompt
    assert base != schema


def test_private_identity_is_owner_specific():
    user_one = build_generation_fingerprint(
        content_hash="abc", material_type="summary", scope="private", owner_user_id=1
    )
    user_two = build_generation_fingerprint(
        content_hash="abc", material_type="summary", scope="private", owner_user_id=2
    )
    assert user_one != user_two


def test_private_requires_owner():
    with pytest.raises(ValueError):
        build_generation_fingerprint(
            content_hash="abc", material_type="summary", scope="private"
        )


def test_shared_rejects_owner():
    with pytest.raises(ValueError):
        build_generation_fingerprint(
            content_hash="abc", material_type="summary", scope="shared", owner_user_id=1
        )
