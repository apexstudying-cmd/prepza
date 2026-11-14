"""Characterize the current student subscription and payment screens before extraction."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
ADMIN_PLATFORM = (ROOT / "frontend/src/admin/AdminPlatform.tsx").read_text(encoding="utf-8")


def test_subscription_and_payment_routes_keep_app_shell_state_and_return_routing():
    for route in (
        "case 'subscription':",
        "case 'payment':",
        "case 'payment-success':",
        "case 'payment-failure':",
        "case 'payment-history':",
    ):
        assert route in APP

    assert "const [selectedPlan, setSelectedPlan] = useState('plus')" in APP
    assert "selectedPlan={selectedPlan} setSelectedPlan={setSelectedPlan}" in APP
    assert "selectedPlan={selectedPlan}" in APP
    assert "paymentStatus === 'success' ? 'payment-success' : 'payment-failure'" in APP
    assert "new URL(window.location.href)" in APP


def test_subscription_screen_preserves_plan_status_usage_and_navigation_contracts():
    for contract in (
        "type SubscriptionPlan = {",
        "type SubscriptionStatus = { plan: string; is_active: boolean; expires_at: string | null }",
        "const SUBSCRIPTION_PLAN_META:",
        "function subscriptionFeatures(plan: SubscriptionPlan): string[]",
        "function SubscriptionScreen(",
        "api<{ plans: SubscriptionPlan[] }>('/subscription/plans')",
        "api<SubscriptionStatus>('/subscription/status')",
        "api('/api/usage/me')",
        "const paidPlans = plans.filter(p => p.id !== 'free')",
        "setScreen('payment')",
        "setScreen('payment-history')",
        "status?.is_active",
        "usage.usage?.[feature]",
    ):
        assert contract in APP


def test_payment_screen_preserves_csrf_checkout_payload_redirect_and_duplicate_guard():
    for contract in (
        "function PaymentScreen(",
        "api<{ plans: SubscriptionPlan[] }>('/subscription/plans')",
        "api<{ csrf_token: string }>('/me')",
        "api<{ redirect_url: string; order_tracking_id: string; merchant_reference: string }>('/subscription/upgrade'",
        "'X-CSRF-Token': me.csrf_token",
        "JSON.stringify({ plan: selectedPlan, phone_number: phone.trim() || undefined })",
        "if (redirecting) return",
        "window.location.href = res.redirect_url",
        "setScreen('subscription')",
    ):
        assert contract in APP


def test_payment_success_and_failure_keep_status_and_timing_behavior():
    success = APP[APP.index("function PaymentSuccessScreen("):APP.index("function PaymentFailureScreen(")]
    failure = APP[APP.index("function PaymentFailureScreen("):APP.index("type PaymentHistoryItem =")]

    for contract in (
        "api<{ payments: PaymentHistoryItem[] }>('/payment-history')",
        "setTimeout(() => setScreen('home'), 6000)",
        "return () => clearTimeout(t)",
        "setScreen('payment-history')",
        "payment.status",
    ):
        assert contract in success

    for contract in (
        "api<{ payments: PaymentHistoryItem[] }>('/payment-history')",
        "const isPending = payment?.status === 'pending'",
        "Payment Still Processing",
        "Payment Failed",
        "setScreen('subscription')",
        "setScreen('payment-history')",
    ):
        assert contract in failure


def test_payment_history_keeps_response_fields_status_metadata_and_empty_state():
    for contract in (
        "type PaymentHistoryItem = {",
        "payment_type: string",
        "content_title?: string | null",
        "plan: string | null",
        "provider: string | null",
        "reference: string | null",
        "function PaymentHistoryScreen(",
        "api<{ payments: PaymentHistoryItem[] }>('/payment-history')",
        "PAYMENT_STATUS_META[p.status]",
        "<Pill text={meta.label}",
        '<EmptyState icon="💳" title="No payments yet"',
        "window.history.back()",
    ):
        assert contract in APP

    assert "export const PAYMENT_STATUS_META:" in ADMIN_PLATFORM
    assert "from './admin/AdminPlatform'" in APP
