from __future__ import annotations

from pathlib import Path

from core_models import ContentItem, Payment, SystemSetting, ViewProgress

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def test_commerce_and_legacy_progress_models_are_owned_by_core_module() -> None:
    assert "from core_models import ContentItem, Payment, SystemSetting, ViewProgress" in APP_SOURCE
    for name in ("ContentItem", "Payment", "SystemSetting", "ViewProgress"):
        assert f"class {name}(db.Model)" not in APP_SOURCE


def test_core_model_table_and_column_contracts_are_preserved() -> None:
    expected = (
        (ContentItem, "content_item", {"id", "content_type", "title", "file_url", "paper_year", "is_downloadable", "price"}),
        (Payment, "payment", {"id", "user_id", "content_item_id", "phone_number", "amount", "checkout_request_id", "status", "created_at", "provider", "reference", "provider_reference", "payment_type", "plan", "subscription_starts_at", "subscription_expires_at", "subscription_allowance_snapshot"}),
        (SystemSetting, "system_setting", {"id", "key", "value"}),
        (ViewProgress, "view_progress", {"id", "user_id", "content_item_id", "page_num", "updated_at"}),
    )
    for model, table, columns in expected:
        assert model.__tablename__ == table
        assert set(model.__table__.columns.keys()) == columns


def test_payment_and_view_progress_constraints_and_defaults_are_preserved() -> None:
    assert Payment.__table__.c.provider.default.arg == "paystack"
    assert Payment.__table__.c.payment_type.default.arg == "content"
    assert Payment.__table__.c.status.default.arg == "pending"
    assert any(
        getattr(constraint, "name", None) == "uq_view_progress_user_item"
        for constraint in ViewProgress.__table__.constraints
    )
    assert next(iter(Payment.__table__.c.user_id.foreign_keys)).target_fullname == "user.id"
    assert next(iter(Payment.__table__.c.content_item_id.foreign_keys)).target_fullname == "content_item.id"
