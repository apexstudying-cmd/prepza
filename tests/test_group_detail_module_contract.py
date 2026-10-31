"""Protect the behavior contract while GroupDetailScreen moves out of App.tsx."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
SCREEN = (ROOT / "frontend/src/screens/groups/GroupDetailScreen.tsx").read_text(encoding="utf-8")


def test_group_detail_is_owned_by_its_feature_module_and_route_is_unchanged():
    assert "import GroupDetailScreen from './screens/groups/GroupDetailScreen'" in APP
    assert "function GroupDetailScreen(" not in APP
    assert "case 'group-detail':" in APP
    assert "groupId={activeGroupId}" in APP
    assert "EmptyState={EmptyState}" in APP
    assert "ErrorState={ErrorState}" in APP


def test_group_detail_keeps_existing_read_and_write_api_contracts():
    for endpoint in (
        "api<{ csrf_token: string }>('/me')",
        "api<GroupSummary>(`/groups/${groupId}`)",
        "api<{ page: number; posts: GroupPostData[] }>(`/groups/${groupId}/posts?type=${postType}`)",
        "api<{ members: GroupMemberData[] }>(`/groups/${groupId}/members`)",
        "api<{ files: GroupFileData[] }>(`/groups/${groupId}/files`)",
        "`/groups/${groupId}/join`",
        "`/groups/${groupId}/leave`",
        "`/groups/${groupId}/posts`",
        "`/groups/${groupId}/posts/${p.id}/like`",
        "`/groups/${groupId}/posts/${p.id}/vote`",
        "`/groups/${groupId}/posts/${p.id}`",
        "`/groups/${groupId}/posts/${expandedId}/comments`",
        "`/groups/${groupId}/posts/${expandedId}/comments/${commentId}/helpful`",
        "`/groups/${groupId}/members/${userId}`",
        "'/documents'",
        "`/groups/${groupId}/files/${fileId}`",
    ):
        assert endpoint in SCREEN
    assert "'X-CSRF-Token': csrfToken" in SCREEN


def test_group_detail_keeps_existing_interactions_and_feedback_components():
    for contract in (
        "setTab(t)", "submitPost", "toggleLike", "toggleVote", "openPost",
        "submitComment", "markHelpful", "changeRole", "removeMember",
        "openFilePicker", "shareDoc", "removeFile", "window.history.back()",
        "window.open(f.view_url, '_blank')", "No questions yet", "No posts yet",
        "No files shared yet", "Share a document", "Mark helpful",
    ):
        assert contract in SCREEN
    assert "EmptyState: ComponentType<" in SCREEN
    assert "ErrorState: ComponentType<" in SCREEN


def test_group_domain_types_are_shared_without_changing_their_shapes():
    types = (ROOT / "frontend/src/types/groups.ts").read_text(encoding="utf-8")
    for contract in (
        "export type GroupPrivacy = 'public' | 'private' | 'course_only'",
        "export type GroupSummary", "export type GroupPostData",
        "export type GroupPostCommentData", "export type GroupPostDetail",
        "export type GroupMemberData", "export type GroupFileData",
    ):
        assert contract in types
    assert "type GroupSummary =" not in APP
    assert "type GroupPostData =" not in APP
