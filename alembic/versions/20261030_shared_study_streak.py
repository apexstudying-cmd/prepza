"""Ensure the shared study streak tables exist on upgraded databases.

Revision ID: 20261030_shared_study_streak
Revises: 20261029_shop_period_payment
"""
from alembic import op

revision = "20261030_shared_study_streak"
down_revision = "20261029_shop_period_payment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The verified fresh-database baseline already contains these tables.
    # IF NOT EXISTS also repairs older populated databases that never ran the
    # legacy SQL migration; UUIDs are supplied by the application explicitly.
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.study_friend_streak (
            id VARCHAR(36) PRIMARY KEY,
            user_a_id INTEGER NOT NULL,
            user_b_id INTEGER NOT NULL,
            invited_by INTEGER NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            current_streak INTEGER NOT NULL DEFAULT 0,
            longest_streak INTEGER NOT NULL DEFAULT 0,
            last_shared_date DATE,
            weekend_pause BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_a_id, user_b_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.study_friend_streak_activity (
            id VARCHAR(36) PRIMARY KEY,
            streak_id VARCHAR(36) NOT NULL,
            user_a_id INTEGER NOT NULL,
            user_b_id INTEGER NOT NULL,
            activity_date DATE NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(streak_id, activity_date)
        )
    """)


def downgrade() -> None:
    # These tables may have existed in the verified baseline or may contain
    # pre-migration user data, so automatically dropping them is unsafe.
    pass
