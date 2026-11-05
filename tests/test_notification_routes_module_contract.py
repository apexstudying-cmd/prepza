"""Guard notification HTTP route ownership and contracts while extracting handlers from app.py."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
ROUTES = ROOT / "notification_routes.py"


def test_notification_routes_are_registered_at_the_original_app_initialization_boundary():
    assert "from notification_routes import register_notification_routes" in APP
    assert "register_notification_routes(app, db, Notification, require_csrf)" in APP
    for route in (
        '@app.route("/notifications")',
        '@app.route("/notifications/unread-count")',
        '@app.route("/notifications/<int:notification_id>/read", methods=["POST"])',
        '@app.route("/notifications/read-all", methods=["POST"])',
        '@app.route("/notifications/<int:notification_id>", methods=["DELETE"])',
    ):
        assert route not in APP
    assert "def _serialize_notification(" not in APP


def test_notification_route_module_preserves_paths_methods_and_endpoint_names():
    source = ROUTES.read_text(encoding="utf-8")
    assert "def register_notification_routes(app, db, Notification, require_csrf):" in source
    for contract in (
        '@app.route("/notifications")\n    def list_notifications():',
        '@app.route("/notifications/unread-count")\n    def notifications_unread_count():',
        '@app.route("/notifications/<int:notification_id>/read", methods=["POST"])\n    @require_csrf\n    def mark_notification_read(notification_id):',
        '@app.route("/notifications/read-all", methods=["POST"])\n    @require_csrf\n    def mark_all_notifications_read():',
        '@app.route("/notifications/<int:notification_id>", methods=["DELETE"])\n    @require_csrf\n    def delete_notification(notification_id):',
    ):
        assert contract in source


def test_notification_route_module_keeps_response_serialization_ordering_and_authz():
    source = ROUTES.read_text(encoding="utf-8")
    for contract in (
        '"id": notification.id',
        '"type": notification.type',
        '"title": notification.title',
        '"body": notification.body',
        '"related_type": notification.related_type',
        '"related_id": notification.related_id',
        '"is_read": notification.is_read',
        '"created_at": notification.created_at.isoformat() if notification.created_at else None',
        "pin_cutoff = datetime.utcnow() - timedelta(hours=24)",
        "is_pinned_announcement = and_(",
        ".order_by(is_pinned_announcement.desc(), Notification.created_at.desc())",
        "if not notification or notification.user_id != user_id:",
        'return jsonify({"error": "Not logged in"}), 401',
        "updated_count = (",
        'return jsonify({"message": "Notification deleted"})',
    ):
        assert contract in source
    assert source.count("@require_csrf") == 3


def test_notification_preference_helpers_remain_in_app_for_existing_callers():
    assert "def get_or_create_notification_prefs(user_id):" in APP
    assert "def should_notify(user_id, category):" in APP
