"""Early route registration for platform, billing and B2B feature modules.

These route modules own their endpoint implementations. This registry keeps
registration order explicit without making app.py import each feature module.
"""
from __future__ import annotations

from typing import Any


def register_foundation_routes(app: Any, db: Any) -> None:
    """Register infrastructure, usage, economics, discovery and B2B routes."""
    import kokoro_control
    from usage_billing import register_usage_billing
    from ai_economics import register_ai_economics
    from organisation_billing import register_organisation_billing
    from discovery_billing import register_discovery
    from b2b_campaign_finance import register_b2b_campaign_finance
    from b2b_admin_routes import register_b2b_admin_routes
    from b2b_campaign_payments import register_b2b_campaign_payments
    from b2b_organisation_portal import register_b2b_organisation_portal

    # Keep the pre-refactor registration order stable: several feature
    # registrations establish schema/config before later route families run.
    kokoro_control.register(app)
    register_usage_billing(app, db)
    register_ai_economics(app, db)
    register_organisation_billing(app, db)
    register_discovery(app, db)
    register_b2b_campaign_finance(app, db)
    register_b2b_admin_routes(app, db)
    register_b2b_campaign_payments(app, db)
    register_b2b_organisation_portal(app, db)


def register_account_billing_routes(
    app: Any,
    db: Any,
    *,
    User: Any,
    SystemSetting: Any,
    require_admin: Any,
    require_csrf: Any,
    limiter: Any,
    DocumentContent: Any,
    AiUsageLog: Any,
    Payment: Any,
    StudyActivityLog: Any,
    StudyTimeLog: Any,
    ContentItem: Any,
    paystack_request: Any,
) -> tuple[Any, Any]:
    """Register authentication, admin operations and student billing routes."""
    from auth_otp import register_email_otp
    from admin_operations import register_admin_operations
    from infrastructure_monitoring import register_infrastructure_monitoring
    from student_orders import register_student_orders
    from student_subscription_billing import register_student_subscription_billing

    register_email_otp(app, db, User, SystemSetting, require_admin, require_csrf, limiter)
    register_admin_operations(app, db, require_admin)
    register_infrastructure_monitoring(
        app, db, require_admin, SystemSetting, User, DocumentContent,
        AiUsageLog, Payment, StudyActivityLog, StudyTimeLog,
    )
    student_order_helpers = register_student_orders(app, db, Payment, ContentItem, User, require_csrf)
    student_subscription_helpers = register_student_subscription_billing(
        app, db, Payment, User, require_csrf, require_admin, paystack_request,
    )
    return student_order_helpers, student_subscription_helpers


def register_public_shell_route(app: Any, db: Any, limiter: Any, sweep_expired_opportunities: Any) -> None:
    from public_shell_routes import register_public_shell_routes

    register_public_shell_routes(app, db, limiter, sweep_expired_opportunities)


def register_academic_catalog_route(app: Any, University: Any, Program: Any) -> None:
    from academic_catalog_routes import register_academic_catalog_routes

    register_academic_catalog_routes(app, University, Program)

def register_notification_feature_routes(app: Any, db: Any, Notification: Any, require_csrf: Any) -> None:
    from notification_routes import register_notification_routes

    register_notification_routes(app, db, Notification, require_csrf)


def register_opportunity_feature_routes(
    app: Any, db: Any, Opportunity: Any, Organisation: Any, User: Any,
    OrganisationMember: Any, require_csrf: Any,
) -> None:
    try:
        from opportunity_runtime import register_opportunity_runtime

        register_opportunity_runtime(app, db, Opportunity, Organisation, User, OrganisationMember, require_csrf)
    except Exception as exc:
        app.logger.exception("Opportunity runtime registration failed: %s", exc)


def register_chat_feature_routes(
    app: Any, db: Any, Conversation: Any, ConversationParticipant: Any, User: Any,
) -> None:
    try:
        from e2ee_chat_models import create_e2ee_models
        ConversationKeyEnvelope = create_e2ee_models(db)
        from e2ee_chat_routes import register_e2ee_chat_routes

        register_e2ee_chat_routes(app, db, Conversation, ConversationParticipant, User, ConversationKeyEnvelope)
        import chat_group_routes  # noqa: F401 - decorator registration
        import chat_interactions  # noqa: F401 - before/after hook registration
    except Exception as exc:
        app.logger.exception("Chat runtime registration failed: %s", exc)


def register_control_feature_routes(
    app: Any, db: Any, SystemSetting: Any, User: Any, Document: Any,
    DocumentContent: Any, GeneratedMaterial: Any, log_admin_action: Any, limiter: Any,
) -> None:
    from prepza_control import register_control_routes

    register_control_routes(
        app, db, SystemSetting, User, Document, DocumentContent,
        GeneratedMaterial, log_admin_action, limiter,
    )


def register_admin_reconciled_routes(app: Any) -> None:
    """Load the separated admin route modules after their shared dependencies exist."""
    import admin_reconciled_core_a  # noqa: F401 - decorator registration
    import admin_reconciled_core_b  # noqa: F401 - decorator registration
    import admin_reconciled_opportunities  # noqa: F401 - decorator registration
    import admin_reconciled_organisation  # noqa: F401 - decorator registration
    import admin_reconciled_ambassadors  # noqa: F401 - decorator registration


def register_runtime_feature_routes(
    app: Any,
    db: Any,
    *,
    Conversation: Any,
    ConversationParticipant: Any,
    User: Any,
    Payment: Any,
    limiter: Any,
    create_paystack_transaction: Any,
    sync_paystack_payment_status: Any,
    login_required: Any,
    require_csrf: Any,
    require_admin: Any,
    RequestObservabilityEvent: Any,
) -> None:
    """Register late-bound routes after core models and helpers are available."""
    from offline_activity_routes import register_offline_activity_routes
    from e2ee_production_hardening import register_e2ee_production_hardening
    from shop_marketplace import register_shop_routes
    from study_retrieval_routes import register_study_retrieval_routes
    from request_observability import register_request_observability

    register_offline_activity_routes(app, db)
    register_e2ee_production_hardening(app, db, Conversation, ConversationParticipant)
    register_shop_routes(
        app, db, User, Payment, Conversation, ConversationParticipant, limiter,
        create_paystack_transaction, sync_paystack_payment_status,
    )
    register_study_retrieval_routes(app, db, login_required, require_csrf)
    register_request_observability(app, db, require_admin, RequestObservabilityEvent)

def register_gamification_routes(app: Any, **dependencies: Any) -> None:
    """Register XP, streak, study-time and achievement routes."""
    from gamification_routes import register_gamification_routes as register

    register(app, **dependencies)

def register_notification_preference_routes(
    app: Any,
    db: Any,
    PushSubscription: Any,
    require_csrf: Any,
    get_or_create_notification_prefs: Any,
) -> None:
    """Register notification preference and push-subscription routes."""
    from notification_routes import register_notification_preference_routes as register

    register(app, db, PushSubscription, require_csrf, get_or_create_notification_prefs)
