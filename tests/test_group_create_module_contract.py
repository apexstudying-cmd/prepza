"""Protect Group Create behavior while moving its existing screen into a feature module."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
SCREEN = (ROOT / "frontend/src/screens/groups/GroupCreateScreen.tsx").read_text(encoding="utf-8")


def test_group_create_is_owned_by_group_feature_and_route_is_preserved():
    assert "import GroupCreateScreen from './screens/groups/GroupCreateScreen'" in APP
    assert "function GroupCreateScreen(" not in APP
    assert "case 'group-create':" in APP
    assert "setActiveGroupId={setActiveGroupId}" in APP
    assert "setScreen={setScreen}" in APP
    assert "from './types/users'" in APP


def test_group_create_preserves_existing_api_and_csrf_contracts():
    for contract in (
        "api<{ csrf_token: string; university_id: number | null }>('/me')",
        "api<UniversityOption[]>('/universities')",
        "api<ProgramOption[]>(" ,
        "/universities/",
        "programs",
        "api<{ users: UserSearchResult[] }>(" ,
        "/users/search?q=",
        "api<{ id: number }>('/groups'",
        "'X-CSRF-Token': csrfToken",
        "privacy: privacyValue",
        "university_id: universityId ?? undefined",
        "program_id: programId ?? undefined",
        "year: year ?? undefined",
        "member_user_ids: selected.map(s => s.id)",
    ):
        assert contract in SCREEN


def test_group_create_preserves_existing_step_selection_and_completion_flow():
    for contract in (
        "useState(1)", "step < 3", "setStep(s => s - 1)",
        "setScreen('create-modal')", "setActiveGroupId(res.id)",
        "setTimeout(() => setScreen('group-detail'), 1400)",
        "setScreen('home')", "Step {step} of 3", "Create Group",
        "Creating group…", "Taking you to the group…",
        "selected.map(s => s.id)", "setCandidates([])",
        "return () => clearTimeout(handle)",
    ):
        assert contract in SCREEN
    assert "from '../../App'" not in SCREEN


def test_user_search_type_is_shared_without_changing_its_shape():
    source = (ROOT / "frontend/src/types/users.ts").read_text(encoding="utf-8")
    assert "export type UserSearchResult = { id: number; display_name: string; year: number | null; semester: number | null }" in source
    assert "type UserSearchResult =" not in APP
    assert "UserSearchResult" in SCREEN
