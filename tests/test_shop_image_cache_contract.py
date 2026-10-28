from __future__ import annotations

import object_storage


def test_shop_image_upload_cache_policy_can_be_written_to_r2_object_metadata(monkeypatch):
    class FakeS3Client:
        def __init__(self):
            self.put_kwargs = None

        def put_object(self, **kwargs):
            self.put_kwargs = kwargs

    client = FakeS3Client()
    monkeypatch.setattr(object_storage, "_r2_client", lambda: client)
    monkeypatch.setenv("PREPZA_R2_BUCKET", "prepza-test-bucket")

    object_storage.r2_put_bytes(
        "shop-listings",
        "42/7/example.webp",
        b"optimized-image-bytes",
        "image/webp",
        cache_control="private, max-age=86400, immutable",
    )

    assert client.put_kwargs == {
        "Bucket": "prepza-test-bucket",
        "Key": "shop-listings/42/7/example.webp",
        "Body": b"optimized-image-bytes",
        "ContentType": "image/webp",
        "CacheControl": "private, max-age=86400, immutable",
    }


def test_r2_put_bytes_does_not_change_cache_policy_for_other_callers(monkeypatch):
    class FakeS3Client:
        def __init__(self):
            self.put_kwargs = None

        def put_object(self, **kwargs):
            self.put_kwargs = kwargs

    client = FakeS3Client()
    monkeypatch.setattr(object_storage, "_r2_client", lambda: client)
    monkeypatch.setenv("PREPZA_R2_BUCKET", "prepza-test-bucket")

    object_storage.r2_put_bytes("documents", "42/document.pdf", b"pdf-bytes", "application/pdf")

    assert client.put_kwargs == {
        "Bucket": "prepza-test-bucket",
        "Key": "documents/42/document.pdf",
        "Body": b"pdf-bytes",
        "ContentType": "application/pdf",
    }


def test_shop_listing_upload_opts_into_private_one_day_image_caching():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "shop_marketplace.py").read_text(encoding="utf-8")

    assert 'r2_put_bytes("shop-listings", key, raw, mime, cache_control="private, max-age=86400, immutable")' in source
    # Presigned image URLs must remain usable for the same private one-day cache window.
    assert 'r2_presigned_get("shop-listings", key, expires_in=86400)' in source
