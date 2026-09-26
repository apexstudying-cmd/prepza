"""Provider-neutral private object storage helpers.

R2 is the production target for large unstructured Prepza assets. The logical
bucket name remains part of the application API, while R2 uses one physical
bucket with a logical-bucket prefix. Supabase remains the safe fallback until
R2 credentials are configured in Render.
"""
import os
from functools import lru_cache

import boto3
from botocore.config import Config


def r2_enabled():
    return all(
        os.environ.get(name, "").strip()
        for name in ("PREPZA_R2_ENDPOINT", "PREPZA_R2_ACCESS_KEY_ID",
                     "PREPZA_R2_SECRET_ACCESS_KEY", "PREPZA_R2_BUCKET")
    )


@lru_cache(maxsize=1)
def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["PREPZA_R2_ENDPOINT"].strip(),
        aws_access_key_id=os.environ["PREPZA_R2_ACCESS_KEY_ID"].strip(),
        aws_secret_access_key=os.environ["PREPZA_R2_SECRET_ACCESS_KEY"].strip(),
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def _r2_key(logical_bucket, path):
    return f"{logical_bucket.strip('/')}/{path.lstrip('/')}"


def r2_presigned_get(logical_bucket, path, expires_in=60):
    return _r2_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": os.environ["PREPZA_R2_BUCKET"].strip(),
            "Key": _r2_key(logical_bucket, path),
        },
        ExpiresIn=max(1, min(int(expires_in), 604800)),
    )


def r2_presigned_put(logical_bucket, path, expires_in=900):
    return _r2_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": os.environ["PREPZA_R2_BUCKET"].strip(),
            "Key": _r2_key(logical_bucket, path),
        },
        ExpiresIn=max(1, min(int(expires_in), 604800)),
    )


def r2_head(logical_bucket, path):
    return _r2_client().head_object(
        Bucket=os.environ["PREPZA_R2_BUCKET"].strip(),
        Key=_r2_key(logical_bucket, path),
    )


def r2_get_bytes(logical_bucket, path):
    response = _r2_client().get_object(
        Bucket=os.environ["PREPZA_R2_BUCKET"].strip(),
        Key=_r2_key(logical_bucket, path),
    )
    return response["Body"].read()


def r2_put_bytes(logical_bucket, path, data, content_type):
    _r2_client().put_object(
        Bucket=os.environ["PREPZA_R2_BUCKET"].strip(),
        Key=_r2_key(logical_bucket, path),
        Body=data,
        ContentType=content_type,
    )
    return True
