"""Protect existing authentication flows while moving them into an auth-owned module."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
AUTH = (ROOT / "frontend/src/screens/auth/AuthScreens.tsx").read_text(encoding="utf-8")


def test_auth_flow_screens_are_owned_by_the_auth_module_and_routes_are_preserved():
    assert (
        "import { ForgotPasswordScreen, ResetPasswordScreen, VerifyConfirmScreen, "
        "SignupScreen, CheckEmailScreen } from './screens/auth/AuthScreens'"
    ) in APP
    for component in (
        "ForgotPasswordScreen",
        "ResetPasswordScreen",
        "VerifyConfirmScreen",
        "SignupScreen",
        "CheckEmailScreen",
    ):
        assert f"function {component}(" not in APP
        assert f"export function {component}(" in AUTH

    for route in (
        "case 'forgot-password':   return <ForgotPasswordScreen setScreen={setScreen} />",
        "case 'signup':            return <SignupScreen setScreen={setScreen} referralCode={referralCode} referralChannel={referralChannel} />",
        "case 'check-email':       return <CheckEmailScreen setScreen={setScreen} />",
        "case 'reset-password':    return <ResetPasswordScreen setScreen={setScreen} />",
        "case 'verify-confirm':    return <VerifyConfirmScreen setScreen={setScreen} />",
    ):
        assert route in APP


def test_forgot_password_preserves_email_otp_and_password_reset_contracts():
    for contract in (
        "api<{ otp_length?: number }>('/forgot-password'",
        "api('/reset-password'",
        "JSON.stringify({ email })",
        "JSON.stringify({ email, code, new_password: newPassword })",
        "setScreen('login')",
    ):
        assert contract in AUTH


def test_reset_password_preserves_token_and_password_strength_contract():
    for contract in (
        "new URLSearchParams(window.location.search).get('token')",
        "JSON.stringify({ token, new_password: password })",
        "COMMON_WEAK_PASSWORDS",
        "At least 8 characters",
        "One lowercase letter",
        "One uppercase letter",
        "One number",
        "One symbol",
        "Not a commonly used password",
        "setScreen('login')",
    ):
        assert contract in AUTH


def test_email_verification_preserves_scanner_safe_confirmation_and_resend_contract():
    for contract in (
        "api('/verify-email/confirm'",
        "JSON.stringify({ token })",
        "api('/resend-verification'",
        "setScreen('home')",
        "setScreen('login')",
        "if (!/^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/.test(resendEmail)) return",
    ):
        assert contract in AUTH


def test_signup_preserves_academic_referral_and_otp_handoff_contract():
    for contract in (
        "api<UniversityOption[]>('/universities')",
        "`/universities/${data.university_id}/programs`",
        "api<{ otp_length?: number }>('/signup'",
        "ref: referralCode || undefined",
        "via: referralChannel || undefined",
        "sessionStorage.setItem('prepza_verification_email', payload.email)",
        "sessionStorage.setItem('prepza_verification_otp_length', String(signupResponse.otp_length || 6))",
        "setScreen('check-email')",
    ):
        assert contract in AUTH


def test_check_email_preserves_otp_verification_resend_and_storage_contract():
    for contract in (
        "api('/verify-otp'",
        "api<{ message: string; expires_in_seconds?: number; otp_length?: number }>('/resend-verification'",
        "sessionStorage.getItem('prepza_verification_email')",
        "sessionStorage.getItem('prepza_verification_otp_length')",
        "sessionStorage.removeItem('prepza_verification_email')",
        "setScreen('home')",
        "setScreen('login')",
    ):
        assert contract in AUTH
