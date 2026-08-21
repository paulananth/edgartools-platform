from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from edgar_warehouse.infrastructure.warehouse_duplicate_reclaim import (
    ApplyFlagError,
    CanonicalSilverDeniedError,
    remaining_selected,
    iter_delete_batches,
    require_apply_flags,
    select_candidates,
    summarize_by_prefix,
    validate_manifest,
    write_tsv,
)

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def _v(
    key: str,
    *,
    latest: bool,
    size: int,
    when: datetime,
    version_id: str = "v1",
) -> dict:
    return {
        "Key": key,
        "VersionId": version_id,
        "IsLatest": latest,
        "Size": size,
        "LastModified": when.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
    }


def test_selects_noncurrent_shards_and_denies_current_canonical_silver() -> None:
    listing = {
        "Versions": [
            _v(
                "warehouse/silver/sec/shards/shard-0.duckdb",
                latest=True,
                size=100,
                when=NOW,
                version_id="cur0",
            ),
            _v(
                "warehouse/silver/sec/shards/shard-0.duckdb",
                latest=False,
                size=200,
                when=NOW - timedelta(days=2),
                version_id="old0",
            ),
            _v(
                "warehouse/silver/sec/silver.duckdb",
                latest=True,
                size=50,
                when=NOW,
                version_id="curS",
            ),
            _v(
                "warehouse/silver/sec/silver.duckdb",
                latest=False,
                size=50,
                when=NOW - timedelta(days=3),
                version_id="oldS",
            ),
        ]
    }
    rows = select_candidates(listing, now=NOW)
    ids = {(row["key"], row["version_id"], row["is_latest"]) for row in rows}
    assert ("warehouse/silver/sec/shards/shard-0.duckdb", "old0", False) in ids
    assert ("warehouse/silver/sec/silver.duckdb", "oldS", False) in ids
    assert ("warehouse/silver/sec/shards/shard-0.duckdb", "cur0", True) not in ids
    assert ("warehouse/silver/sec/silver.duckdb", "curS", True) not in ids


def test_skips_identity_run_dirs_newer_than_24_hours() -> None:
    listing = {
        "Versions": [
            _v(
                "warehouse/identity_refresh/runs/fresh-run/reference_snapshot.duckdb",
                latest=True,
                size=10,
                when=NOW - timedelta(hours=1),
                version_id="fresh",
            ),
            _v(
                "warehouse/identity_refresh/runs/old-run/reference_snapshot.duckdb",
                latest=True,
                size=20,
                when=NOW - timedelta(hours=48),
                version_id="old",
            ),
        ]
    }
    rows = select_candidates(listing, now=NOW)
    assert [row["version_id"] for row in rows] == ["old"]


def test_gold_keep_set_is_union_of_per_table_newest_last_modified() -> None:
    listing = {
        "Versions": [
            _v(
                "warehouse/gold/dim_filing/run_id=run-a/dim_filing.parquet",
                latest=True,
                size=1,
                when=NOW - timedelta(days=2),
                version_id="a-dim",
            ),
            _v(
                "warehouse/gold/dim_filing/run_id=run-b/dim_filing.parquet",
                latest=True,
                size=1,
                when=NOW - timedelta(days=1),
                version_id="b-dim",
            ),
            _v(
                "warehouse/gold/fact_filing_activity/run_id=run-a/fact.parquet",
                latest=True,
                size=1,
                when=NOW - timedelta(hours=1),
                version_id="a-fact",
            ),
            _v(
                "warehouse/gold/fact_filing_activity/run_id=run-b/fact.parquet",
                latest=True,
                size=1,
                when=NOW - timedelta(days=3),
                version_id="b-fact",
            ),
        ]
    }
    rows = select_candidates(listing, now=NOW)
    kept_out = {row["version_id"] for row in rows}
    # run-b is newest for dim_filing; run-a is newest for fact — union keeps both
    # run_ids, so no current objects from those run_ids are selected.
    assert kept_out == set()
    # An older third run is reclaimable.
    listing["Versions"].append(
        _v(
            "warehouse/gold/dim_filing/run_id=run-c/dim_filing.parquet",
            latest=True,
            size=1,
            when=NOW - timedelta(days=9),
            version_id="c-dim",
        )
    )
    rows = select_candidates(listing, now=NOW)
    assert [row["version_id"] for row in rows] == ["c-dim"]


def test_empty_candidate_set_is_success() -> None:
    assert select_candidates({"Versions": []}, now=NOW) == []
    summary = summarize_by_prefix([])
    assert summary["shards"]["count"] == 0
    assert summary["identity_refresh"]["gib"] == 0


def test_manifest_with_current_canonical_silver_is_rejected() -> None:
    with pytest.raises(CanonicalSilverDeniedError):
        validate_manifest(
            [
                {
                    "key": "warehouse/silver/sec/shards/shard-0.duckdb",
                    "version_id": "cur0",
                    "is_latest": True,
                    "size_bytes": 1,
                    "last_modified": NOW.isoformat(),
                }
            ]
        )


def test_delete_batches_are_at_most_100() -> None:
    rows = [
        {
            "key": f"warehouse/identity_refresh/runs/old/k{i}",
            "version_id": str(i),
            "is_latest": True,
            "size_bytes": 1,
            "last_modified": NOW.isoformat(),
        }
        for i in range(101)
    ]
    batches = iter_delete_batches(rows)
    assert len(batches) == 2
    assert len(batches[0]["Objects"]) == 100
    assert len(batches[1]["Objects"]) == 1
    assert all("Key" in obj and "VersionId" in obj for obj in batches[0]["Objects"])


def test_apply_requires_confirm_flag_and_manifest() -> None:
    require_apply_flags(apply=False, confirm=False, manifest_path=None)
    with pytest.raises(ApplyFlagError, match="confirm-delete-duplicates"):
        require_apply_flags(apply=True, confirm=False, manifest_path="x.tsv")
    with pytest.raises(ApplyFlagError, match="manifest"):
        require_apply_flags(apply=True, confirm=True, manifest_path=None)


def test_dry_run_tsv_has_required_columns(tmp_path) -> None:
    rows = select_candidates(
        {
            "Versions": [
                _v(
                    "warehouse/silver/sec/shards/shard-1.duckdb",
                    latest=False,
                    size=8,
                    when=NOW - timedelta(days=1),
                    version_id="old1",
                )
            ]
        },
        now=NOW,
    )
    path = tmp_path / "candidate-versions.tsv"
    write_tsv(path, rows)
    text = path.read_text(encoding="utf-8")
    header = text.splitlines()[0].split("\t")
    assert header == [
        "key",
        "version_id",
        "last_modified",
        "size_bytes",
        "is_latest",
    ]
    assert "old1" in text


def test_empty_manifest_remaining_is_complete() -> None:
    leftover = remaining_selected([], {"Versions": []})
    assert leftover == []


def test_adr0004_staging_cleanup_script_is_unchanged_islatest_contract() -> None:
    script = Path("infra/scripts/cleanup-s3-staging.sh").read_text(encoding="utf-8")
    assert "--confirm-delete-staging" in script
    assert "warehouse/_staging/" in script
    assert "reclaim-warehouse-duplicates" not in script
    assert 'bool(version.get("IsLatest", False))' in script
