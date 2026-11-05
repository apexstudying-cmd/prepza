"""Guard the Notifications screen's existing API, cache, and route behavior during extraction."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
SCREEN = ROOT / "frontend/src/screens/notifications/NotificationsScreen.tsx"
TYPES = ROOT / "frontend/src/types/notifications.ts"


def test_notifications_screen_is_module_owned_and_route_dependencies_are_explicit():
    assert "import NotificationsScreen from './screens/notifications/NotificationsScreen'" in APP
    assert "function NotificationsScreen(" not in APP
    assert "type NotificationItem =" not in APP
    assert "const NOTIFS_CACHE:" not in APP
    assert "case 'notifications':" in APP
    assert "setActiveProfileUserId={setActiveProfileUserId}" in APP
    assert "setActiveDocumentId={setActiveDocumentId}" in APP
    assert "EmptyStateView={EmptyState}" in APP
    assert "loadingView={<DelayedScreenSkeleton><SkeletonNotifications /></DelayedScreenSkeleton>}" in APP


def test_notifications_keep_existing_fetch_and_mutation_contracts():
    source = SCREEN.read_text(encoding="utf-8")
    for contract in (
        "api<{ csrf_token: string }>('/me')",
        "api<{ page: number; notifications: NotificationItem[] }>('/notifications?page=1')",
        "`/notifications/${n.id}/read`",
        "api('/notifications/read-all'",
        "`/notifications/${id}`",
        "method: 'POST'",
        "method: 'DELETE'",
        "'X-CSRF-Token': csrfToken",
    ):
        assert contract in source


def test_notifications_preserve_optimistic_cache_updates_and_error_behavior():
    source = SCREEN.read_text(encoding="utf-8")
    for contract in (
        "NOTIFS_CACHE.notifs ?? []",
        "NOTIFS_CACHE.notifs === undefined",
        "NOTIFS_CACHE.notifs = res.notifications",
        "NOTIFS_CACHE.notifs = next",
        "list.map(x => x.id === n.id ? { ...x, is_read: true } : x)",
        "list.map(x => ({ ...x, is_read: true }))",
        "list.filter(x => x.id !== id)",
        "catch { /* existing notification list remains usable */ }",
        "Could not load notifications.",
    ):
        assert contract in source


def test_notification_destinations_and_optional_route_context_remain_unchanged():
    source = SCREEN.read_text(encoding="utf-8")
    for contract in (
        "setScreen('podcast-player')",
        "setScreen('group-detail')",
        "setScreen('student-profile')",
        "setActiveProfileUserId(n.related_id)",
        "setActiveDocumentId(n.related_id)",
        "window.history.back()",
        "iconFor(n.type)",
    ):
        assert contract in source


def test_notification_response_type_preserves_the_existing_field_shapes():
    types = TYPES.read_text(encoding="utf-8")
    assert "export type NotificationItem = {" in types
    for field in (
        "id: number; type: string; title: string; body: string | null",
        "related_type: string | null; related_id: number | null",
        "is_read: boolean; created_at: string | null",
    ):
        assert field in types
