"""Protect the student subscription and payment module boundary."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
BILLING = (ROOT / "frontend/src/screens/billing/SubscriptionScreens.tsx").read_text(encoding="utf-8")
TYPES = (ROOT / "frontend/src/types/billing.ts").read_text(encoding="utf-8")
PAYMENT_STATUS = (ROOT / "frontend/src/lib/paymentStatus.ts").read_text(encoding="utf-8")
ADMIN_PLATFORM = (ROOT / "frontend/src/admin/AdminPlatform.tsx").read_text(encoding="utf-8")


def test_billing_screens_are_module_owned_and_app_keeps_shared_plan_state():
    for component in (
        "SubscriptionScreen",
        "PaymentScreen",
        "PaymentSuccessScreen",
        "PaymentFailureScreen",
        "PaymentHistoryScreen",
    ):
        assert f"function {component}(" not in APP
        assert f"function {component}(" in BILLING

    assert "import { SubscriptionScreen, PaymentScreen, PaymentSuccessScreen, PaymentFailureScreen, PaymentHistoryScreen } from './screens/billing/SubscriptionScreens'" in APP
    assert "const [selectedPlan, setSelectedPlan] = useState('plus')" in APP
    assert "selectedPlan={selectedPlan} setSelectedPlan={setSelectedPlan}" in APP
    assert "selectedPlan={selectedPlan}" in APP
    assert "ErrorState={ErrorState}" in APP
    assert "EmptyState={EmptyState}" in APP
    assert "paymentStatus === 'success' ? 'payment-success' : 'payment-failure'" in APP
    assert "new URL(window.location.href)" in APP


def test_subscription_plan_and_status_types_keep_backend_response_shapes():
    for contract in (
        "export type SubscriptionPlan = {",
        "id: string",
        "price: number",
        "period: string | null",
        "podcast_minutes?: number",
        "summary_pages?: number",
        "questions?: number",
        "mind_map_nodes?: number",
        "flashcards?: number",
        "offline_study?: boolean",
        "premium_library?: boolean",
        "study_hub_uploads?: boolean",
        "export type SubscriptionStatus = {",
        "export type PaymentHistoryItem = {",
        "payment_type: string",
        "content_title?: string | null",
        "plan: string | null",
        "amount: number",
        "status: string",
        "provider: string | null",
        "reference: string | null",
        "created_at: string | null",
    ):
        assert contract in TYPES

    status_type = TYPES[TYPES.index("export type SubscriptionStatus = {"):TYPES.index("export type PaymentHistoryItem = {")]
    for field in ("plan: string", "is_active: boolean", "expires_at: string | null"):
        assert field in status_type


def test_subscription_screen_preserves_plan_status_usage_and_navigation_contracts():
    for contract in (
        "function SubscriptionScreen(",
        "api<{ plans: SubscriptionPlan[] }>('/subscription/plans')",
        "api<SubscriptionStatus>('/subscription/status')",
        "api('/api/usage/me')",
        "const paidPlans = plans.filter(p => p.id !== 'free')",
        "setScreen('payment')",
        "setScreen('payment-history')",
        "status?.is_active",
        "usage.usage?.[feature]",
        "SUBSCRIPTION_PLAN_META",
        "function subscriptionFeatures(plan: SubscriptionPlan): string[]",
    ):
        assert contract in BILLING


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
        assert contract in BILLING


def test_payment_success_and_failure_keep_status_and_timing_behavior():
    success = BILLING[BILLING.index("function PaymentSuccessScreen("):BILLING.index("function PaymentFailureScreen(")]
    failure = BILLING[BILLING.index("function PaymentFailureScreen("):BILLING.index("function PaymentHistoryScreen(")]

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


def test_payment_history_uses_shared_status_metadata_and_shell_feedback_props():
    for contract in (
        "function PaymentHistoryScreen(",
        "api<{ payments: PaymentHistoryItem[] }>('/payment-history')",
        "PAYMENT_STATUS_META[p.status]",
        "<Pill text={meta.label}",
        '<EmptyState icon="💳" title="No payments yet"',
        "ErrorState",
        "window.history.back()",
    ):
        assert contract in BILLING

    assert "export const PAYMENT_STATUS_META:" in PAYMENT_STATUS
    assert "from '../../lib/paymentStatus'" in BILLING
    assert "export { PAYMENT_STATUS_META } from '../lib/paymentStatus'" in ADMIN_PLATFORM
    assert "import { PAYMENT_STATUS_META } from './admin/AdminPlatform'" not in APP
