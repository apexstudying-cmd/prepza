import pytest

from ai_reusable_generation import normalize_parameters


def test_normalize_parameters_is_deterministic_and_whitespace_safe():
    assert normalize_parameters(
        "podcast",
        {"language": "  English   ", "duration_minutes": 15, "style": " conversational  "},
    ) == {
        "duration_minutes": 15,
        "language": "English",
        "style": "conversational",
    }


def test_normalize_parameters_rejects_unknown_keys():
    with pytest.raises(ValueError, match="Unsupported podcast parameter"):
        normalize_parameters("podcast", {"duration_minutes": 15, "student_id": 42})


def test_normalize_parameters_rejects_invalid_counts():
    for value in (0, -1, True, "10"):
        with pytest.raises(ValueError):
            normalize_parameters("quiz", {"question_count": value})


def test_normalize_parameters_rejects_blank_strings():
    with pytest.raises(ValueError):
        normalize_parameters("summary", {"language": "   "})


def test_normalize_parameters_rejects_unknown_material_type():
    with pytest.raises(ValueError):
        normalize_parameters("essay", {})


def test_empty_parameters_are_canonical():
    assert normalize_parameters("mind_map", None) == {}
    assert normalize_parameters("mind_map", {}) == {}
