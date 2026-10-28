"""Exercise an Alembic upgrade while preserving rows from an existing schema.

This script is intended for the isolated GitHub Actions migration rehearsal.
It deliberately uses real PostgreSQL and the project's configured DATABASE_URL.
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import create_engine, inspect, text

PREVIOUS_REVISION = "20261005_chat_attach_source_doc"
EXPECTED_HEAD = "20261030_shared_study_streak"
FIXTURE_ID = 987_654_321
CONTENT_HASH = "existing-db-migration-rehearsal-v1"


def make_engine():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    return create_engine(database_url, pool_pre_ping=True)


def current_revision(connection) -> str:
    revision = connection.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalar_one()
    return str(revision)


def seed(engine) -> None:
    with engine.begin() as connection:
        revision = current_revision(connection)
        if revision != PREVIOUS_REVISION:
            raise AssertionError(
                f"Expected existing database at {PREVIOUS_REVISION}, got {revision}"
            )
        columns = {item["name"] for item in inspect(connection).get_columns(
            "document_content", schema="public"
        )}
        if "material_id" in columns:
            raise AssertionError(
                "Fixture must start before the material_id migration is applied"
            )

        connection.execute(
            text(
                """
                INSERT INTO public.document_content
                    (id, content_hash, storage_path, file_type, file_size_bytes,
                     page_count, status, extracted_text)
                VALUES
                    (:id, :content_hash, 'qa/migration-rehearsal.pdf',
                     'application/pdf', 1234, 2, 'ready',
                     'Existing document content must survive an upgrade')
                """
            ),
            {"id": FIXTURE_ID, "content_hash": CONTENT_HASH},
        )
        connection.execute(
            text(
                """
                INSERT INTO public.generated_material
                    (id, document_content_id, material_type, status, payload,
                     generation_fingerprint, generation_parameters)
                VALUES
                    (:id, :id, 'summary', 'ready',
                     '{"summary":"existing material stays available"}',
                     'migration-rehearsal-fingerprint-v1', '{"source":"qa"}'::jsonb)
                """
            ),
            {"id": FIXTURE_ID},
        )

        existing = connection.execute(
            text(
                """
                SELECT dc.content_hash, dc.extracted_text, gm.payload
                FROM public.document_content AS dc
                JOIN public.generated_material AS gm
                  ON gm.document_content_id = dc.id
                WHERE dc.id = :id AND gm.id = :id
                """
            ),
            {"id": FIXTURE_ID},
        ).mappings().one()
        assert existing["content_hash"] == CONTENT_HASH
        assert existing["extracted_text"] == (
            "Existing document content must survive an upgrade"
        )
        assert "existing material stays available" in existing["payload"]
        print(
            f"SEEDED: preserved-document fixture at revision {revision}; "
            "content and generated material exist before upgrade"
        )


def verify(engine) -> None:
    with engine.begin() as connection:
        revision = current_revision(connection)
        if revision != EXPECTED_HEAD:
            raise AssertionError(
                f"Expected database at {EXPECTED_HEAD}, got {revision}"
            )
        columns = {
            item["name"]: item
            for item in inspect(connection).get_columns(
                "document_content", schema="public"
            )
        }
        if "material_id" not in columns:
            raise AssertionError("Upgrade did not add document_content.material_id")
        if columns["material_id"]["nullable"] is False:
            raise AssertionError("New material_id column must remain nullable for old rows")

        existing = connection.execute(
            text(
                """
                SELECT dc.content_hash, dc.storage_path, dc.status,
                       dc.extracted_text, dc.material_id, gm.payload
                FROM public.document_content AS dc
                JOIN public.generated_material AS gm
                  ON gm.document_content_id = dc.id
                WHERE dc.id = :id AND gm.id = :id
                """
            ),
            {"id": FIXTURE_ID},
        ).mappings().one()
        assert existing["content_hash"] == CONTENT_HASH
        assert existing["storage_path"] == "qa/migration-rehearsal.pdf"
        assert existing["status"] == "ready"
        assert existing["extracted_text"] == (
            "Existing document content must survive an upgrade"
        )
        assert existing["material_id"] is None, (
            "Legacy document rows must migrate without being assigned a material"
        )
        assert "existing material stays available" in existing["payload"]

        foreign_keys = inspect(connection).get_foreign_keys(
            "document_content", schema="public"
        )
        link_fk = next(
            (
                item for item in foreign_keys
                if item["constrained_columns"] == ["material_id"]
                and item["referred_table"] == "generated_material"
                and item["referred_columns"] == ["id"]
            ),
            None,
        )
        if link_fk is None:
            raise AssertionError(
                "document_content.material_id foreign key is missing or incorrect"
            )

        # This rehearsal now upgrades the populated database through the Shop
        # migration as well, proving the new tables and payment-review audit
        # fields can be added without disturbing legacy document/material rows.
        tables = set(inspect(connection).get_table_names(schema="public"))
        required_shop_tables = {"shop_listing", "shop_saved_listing", "shop_report", "study_friend_streak", "study_friend_streak_activity"}
        missing_shop_tables = required_shop_tables - tables
        if missing_shop_tables:
            raise AssertionError(
                f"Shop migration tables missing after upgrade: {sorted(missing_shop_tables)}"
            )
        shop_columns = {
            item["name"]
            for item in inspect(connection).get_columns("shop_listing", schema="public")
        }
        streak_columns = {item["name"] for item in inspect(connection).get_columns("study_friend_streak", schema="public")}
        if not {"id", "user_a_id", "user_b_id", "invited_by", "status", "current_streak", "longest_streak"} <= streak_columns:
            raise AssertionError("Shared streak schema columns are missing")
        required_shop_columns = {
            "posting_payment_reviewed_by",
            "posting_payment_reviewed_at",
            "posting_payment_review_note",
            "posting_fee_paid",
            "posting_payment_reference",
        }
        if required_shop_columns - shop_columns:
            raise AssertionError(
                f"Shop listing columns missing: {sorted(required_shop_columns - shop_columns)}"
            )

        # Prove the new relationship accepts a valid generated-material reference.
        connection.execute(
            text(
                """
                UPDATE public.document_content
                SET material_id = :id
                WHERE id = :id
                """
            ),
            {"id": FIXTURE_ID},
        )
        linked_id = connection.execute(
            text("SELECT material_id FROM public.document_content WHERE id = :id"),
            {"id": FIXTURE_ID},
        ).scalar_one()
        if linked_id != FIXTURE_ID:
            raise AssertionError("New material relationship did not persist")

        print(
            f"PASS: upgrade preserved existing document/material rows; "
            f"revision={revision}; nullable material_id and foreign key verified; "
            "Shop tables and posting-payment review fields verified"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("seed", "verify"), required=True)
    args = parser.parse_args()
    engine = make_engine()
    try:
        if args.phase == "seed":
            seed(engine)
        else:
            verify(engine)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
