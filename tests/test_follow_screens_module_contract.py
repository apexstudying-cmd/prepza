"""Guard the existing follow screens while they move into a social feature module."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
SCREEN_PATH = ROOT / "frontend/src/screens/social/FollowScreens.tsx"
TYPES_PATH = ROOT / "frontend/src/types/social.ts"


def test_follow_screens_are_owned_by_the_social_module_and_routes_are_unchanged():
    assert "import { FollowListScreen, FollowRequestsScreen } from './screens/social/FollowScreens'" in APP
    assert "function FollowListScreen(" not in APP
    assert "function FollowRequestsScreen(" not in APP
    assert "case 'followers':" in APP
    assert "case 'following':" in APP
    assert "case 'follow-requests':" in APP
    assert "targetUserId={activeProfileUserId}" in APP


def test_follow_screens_keep_existing_follow_and_request_api_contracts():
    source = SCREEN_PATH.read_text(encoding="utf-8")
    for endpoint in (
        "api<{ csrf_token: string }>('/me')",
        r"`/users/${targetUserId}/${key}?page=1`",
        r"`/users/${person.user_id}/follow`",
        "api<{ requests: FollowRequestItem[] }>('/follow-requests')",
        r"`/follow-requests/${req.id}/${action}`",
    ):
        assert endpoint in source
    assert "'X-CSRF-Token': csrfToken" in source


def test_follow_screens_keep_existing_state_transitions_and_navigation():
    source = SCREEN_PATH.read_text(encoding="utf-8")
    for contract in (
        "setPeople((mode === 'followers' ? res.followers : res.following) || [])",
        "setPeople(list => list.map(p => p.user_id === person.user_id ? { ...p, is_following: false, is_pending: false } : p))",
        "const nowPending = res.status === 'pending'",
        "setPeople(list => list.map(p => p.user_id === person.user_id ? { ...p, is_following: !nowPending, is_pending: nowPending } : p))",
        "setRequests(list => list.filter(r => r.id !== req.id))",
        "setScreen('student-profile')",
        "setScreen('explore')",
        "window.history.back()",
        "Search…",
        "Follow Requests",
    ):
        assert contract in source


def test_social_types_keep_existing_follow_and_request_shapes():
    types = TYPES_PATH.read_text(encoding="utf-8")
    for contract in (
        "export type FollowListUser = { user_id: number; display_name: string; is_following: boolean; is_pending?: boolean }",
        "export type FollowRequestItem = { id: number; requester_id: number; requester_display_name: string; created_at: string | null }",
        "export type MessageRequestItem = { conversation_id: number; requester_id: number; requester_display_name: string; has_message: boolean; created_at: string | null }",
    ):
        assert contract in types
    assert "type FollowRequestItem =" not in APP
    assert "type MessageRequestItem =" not in APP
