"""Leak-seal: warehouse lifecycle prefixes must be Joined Live Keys.

Relative write path silverstage/<uuid>/... is not the S3 key. StorageLocation.join()
prefixes WAREHOUSE_STORAGE_ROOT (already ending in /warehouse), so live keys are
warehouse/silverstage/.... A filter of silverstage/ matches nothing (1.71 TiB
incident, 2026-08-20). Analog: test_ecr_image_retention.py (HCL as text) plus a
production join() assertion.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

from edgar_warehouse.infrastructure.object_storage import StorageLocation

REPO_ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE_STORAGE_TF = (
    REPO_ROOT / "infra" / "terraform" / "modules" / "storage_buckets" / "main.tf"
)

STAGING_PREFIX = "warehouse/silverstage/"
IDENTITY_PREFIX = "warehouse/identity_refresh/"
SILVER_PREFIX = "warehouse/silver/"
RELATIVE_STAGING_PREFIX = "silverstage/"


def _warehouse_lifecycle_hcl() -> str:
    text = WAREHOUSE_STORAGE_TF.read_text(encoding="utf-8")
    match = re.search(
        r'resource "aws_s3_bucket_lifecycle_configuration" "warehouse" \{.*?\n\}',
        text,
        re.DOTALL,
    )
    assert match, "warehouse lifecycle resource not found"
    return match.group(0)


def _rule_blocks(hcl: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for match in re.finditer(r"\n  rule \{((?:.|\n)*?)\n  \}", hcl):
        body = match.group(1)
        id_match = re.search(r'id\s*=\s*"([^"]+)"', body)
        assert id_match, "lifecycle rule missing id"
        blocks[id_match.group(1)] = body
    return blocks


def _filter_prefix(rule_body: str) -> str:
    match = re.search(r'prefix\s*=\s*"([^"]+)"', rule_body)
    assert match, "lifecycle rule missing filter prefix"
    return match.group(1)


def _object_key(uri: str) -> str:
    return urlsplit(uri).path.lstrip("/")


def test_relative_silverstage_prefix_is_not_a_prefix_of_joined_live_keys() -> None:
    storage = StorageLocation("s3://edgartools-prod-warehouse-example/warehouse")
    joined = storage.join(
        "silverstage", "0123456789abcdef0123456789abcdef", "silver/sec/silver.duckdb"
    )
    key = _object_key(joined)
    assert key.startswith(STAGING_PREFIX)
    assert not key.startswith(RELATIVE_STAGING_PREFIX)


def test_join_staging_key_starts_with_terraform_staging_prefix() -> None:
    hcl = _warehouse_lifecycle_hcl()
    staging = _rule_blocks(hcl)["expire-silver-staging-candidates"]
    terraform_prefix = _filter_prefix(staging)
    storage = StorageLocation("s3://edgartools-prod-warehouse-example/warehouse")
    key = _object_key(
        storage.join(
            "silverstage",
            "0123456789abcdef0123456789abcdef",
            "silver/sec/silver.duckdb",
        )
    )
    assert key.startswith(terraform_prefix)
    assert terraform_prefix == STAGING_PREFIX
    assert terraform_prefix.endswith("/")


def test_lifecycle_locks_three_trailing_slash_joined_prefixes() -> None:
    rules = _rule_blocks(_warehouse_lifecycle_hcl())
    prefixes = {rule_id: _filter_prefix(body) for rule_id, body in rules.items()}
    assert prefixes["expire-silver-staging-candidates"] == STAGING_PREFIX
    assert prefixes["expire-identity-refresh-run-snapshots"] == IDENTITY_PREFIX
    assert prefixes["expire-noncurrent-silver-canonical-versions"] == SILVER_PREFIX
    # Trailing slash is required: warehouse/silver (no slash) is a prefix of
    # warehouse/silverstage/; warehouse/silver/ is not.
    assert STAGING_PREFIX.startswith("warehouse/silver")
    assert not STAGING_PREFIX.startswith(SILVER_PREFIX)


def test_staging_rule_expires_current_and_noncurrent_in_three_days() -> None:
    body = _rule_blocks(_warehouse_lifecycle_hcl())["expire-silver-staging-candidates"]
    assert re.search(r"expiration\s*\{\s*days\s*=\s*3\s*\}", body) is not None
    assert (
        re.search(
            r"noncurrent_version_expiration\s*\{\s*noncurrent_days\s*=\s*3\s*\}",
            body,
        )
        is not None
    )


def test_identity_refresh_rule_expires_current_and_noncurrent_in_seven_days() -> None:
    body = _rule_blocks(_warehouse_lifecycle_hcl())[
        "expire-identity-refresh-run-snapshots"
    ]
    assert re.search(r"expiration\s*\{\s*days\s*=\s*7\s*\}", body) is not None
    assert (
        re.search(
            r"noncurrent_version_expiration\s*\{\s*noncurrent_days\s*=\s*7\s*\}",
            body,
        )
        is not None
    )


def test_canonical_silver_rule_expires_only_noncurrent_after_seven_days() -> None:
    body = _rule_blocks(_warehouse_lifecycle_hcl())[
        "expire-noncurrent-silver-canonical-versions"
    ]
    assert re.search(r"(?<!noncurrent_version_)expiration\s*\{", body) is None
    assert (
        re.search(
            r"noncurrent_version_expiration\s*\{\s*noncurrent_days\s*=\s*7\s*\}",
            body,
        )
        is not None
    )


def test_no_rule_filter_uses_the_relative_silverstage_prefix() -> None:
    for rule_id, body in _rule_blocks(_warehouse_lifecycle_hcl()).items():
        assert _filter_prefix(body) != RELATIVE_STAGING_PREFIX, rule_id
