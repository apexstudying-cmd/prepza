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
