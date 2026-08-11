"""Per-event silver reducer (decoupled-bronze-pipeline Phase 0, ticket 12's
Answer).

Generalizes ``identity_refresh_publication.py``'s isolated-producer +
single-reducer pattern from one-shot-per-run to per-event: instead of
requiring a complete, pre-declared manifest of every expected batch before
merging once, this reducer merges whatever verified accession-deltas it is
handed in one call -- a single event, or a small SQS batch-window's worth --
safely and idempotently regardless of delivery order or duplicate delivery.
SQS gives neither ordering nor exactly-once delivery (decoupled-bronze-
pipeline ticket 04's chosen substrate), so this must be provably safe under
both before it ever sees live traffic, not merely assumed to be.

**Not wired to any live queue.** Per ticket 12's Answer, Phase 0 is isolated
testing only -- no cutover of the currently-running synchronous pipeline, no
new always-on infrastructure. This module and its tests
(tests/application/test_silver_event_reducer.py) are that isolated test.

Why this is safe under reordering and duplicates, not just assumed to be:
``merge_candidate_into_canonical`` (silver_protection.py) merges by business
key, not by arrival order -- a new key is inserted, an identical same-key row
is left alone (a duplicate delta merges to a no-op), and a differing
same-key row is resolved only via the table's declared ``authority_column``
(deterministic, not last-writer-wins). Reprocessing the same delta twice, or
processing two independent deltas in either order, converges to the same
canonical state. tests/application/test_silver_event_reducer.py proves this
against real DuckDB databases and the real merge function, not a mock.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.object_storage import (
    PromotionConflictError,
    StorageLocation,
    read_bytes,
)
from edgar_warehouse.silver_protection import merge_candidate_into_canonical

_SHA256_LENGTH = 64
DEFAULT_CANONICAL_RELATIVE_PATH = "silver/sec/silver.duckdb"


def _emit_reducer_event(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}), file=sys.stderr, flush=True)


@dataclass(frozen=True)
class AccessionDelta:
    """One accession's independently-produced, content-addressed delta.

    Mirrors ``identity_refresh_publication.IdentityRefreshInput``'s shape
    but keyed by accession (per ticket 04's chosen event granularity), not
    by CIK batch, and with no ``batch_id``/run association -- an accession
    delta is meaningful on its own, not as part of a declared run.
    """

    accession_number: str
    delta_path: str
    sha256: str


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_LENGTH and all(ch in "0123456789abcdef" for ch in value)


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_verified_to_path(storage_root: StorageLocation, relative: str, expected_sha256: str, dest_path: Path) -> Path:
    if not _valid_sha256(expected_sha256):
        raise WarehouseRuntimeError(f"accession delta for {relative!r} has an invalid checksum")
    payload = read_bytes(storage_root.join(relative))
    if _sha256_hex(payload) != expected_sha256:
        raise WarehouseRuntimeError(f"accession delta checksum mismatch for {relative}")
    dest_path.write_bytes(payload)
    return dest_path


def reduce_silver_events(
    storage_root: StorageLocation,
    *,
    deltas: Iterable[AccessionDelta],
    canonical_relative: str = DEFAULT_CANONICAL_RELATIVE_PATH,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Merge a batch of verified accession-deltas into canonical silver, once.

    Safe to call with a single delta (true per-event granularity), a small
    batch (an SQS batch-window's worth), or a batch containing a duplicate
    of an accession already merged in a prior call -- the duplicate merges
    to a no-op (see module docstring). Deduplicates *within* one call by
    accession_number up front (a genuinely duplicate event delivered twice
    in the same SQS batch is merged once, not twice, purely to avoid
    redundant I/O -- correctness does not depend on this, since a second
    merge of the identical content would also be a no-op).

    Unlike ``reduce_identity_refresh``, there is no manifest-completeness
    precondition to satisfy first: every event is independently mergeable,
    so there is no "run" that can be partially declared.
    """
    if max_attempts < 1:
        raise WarehouseRuntimeError("silver event reducer max_attempts must be positive")

    deduplicated: dict[str, AccessionDelta] = {}
    for delta in deltas:
        deduplicated[delta.accession_number] = delta
    ordered_deltas = list(deduplicated.values())

    if not ordered_deltas:
        return {
            "status": "no_op",
            "accessions_merged": [],
            "canonical_promotion_count": 0,
        }

    cache_dir = Path(tempfile.mkdtemp(prefix="silver-event-reducer-"))
    try:
        verified_paths: dict[str, Path] = {
            delta.accession_number: _read_verified_to_path(
                storage_root, delta.delta_path, delta.sha256, cache_dir / f"delta-{index}.duckdb"
            )
            for index, delta in enumerate(ordered_deltas)
        }

        for attempt in range(1, max_attempts + 1):
            _emit_reducer_event(
                "silver_event_reduce_attempt_started",
                attempt=attempt,
                max_attempts=max_attempts,
                accession_count=len(ordered_deltas),
            )
            baseline = storage_root.read_object_version(canonical_relative)
            try:
                with tempfile.TemporaryDirectory(prefix="silver-event-reduce-") as tmp:
                    tmp_path = Path(tmp)
                    if baseline.exists:
                        current = tmp_path / "canonical.duckdb"
                        current.write_bytes(read_bytes(storage_root.join(canonical_relative)))
                        remaining_deltas = ordered_deltas
                        merged_accessions: list[str] = []
                    else:
                        # First-ever publish: seed `current` from the first
                        # delta itself (merge_candidate_into_canonical
                        # requires an existing canonical_path to copy from,
                        # so there is no empty canonical to read) and merge
                        # the rest on top of it.
                        current = verified_paths[ordered_deltas[0].accession_number]
                        remaining_deltas = ordered_deltas[1:]
                        merged_accessions = [ordered_deltas[0].accession_number]

                    for index, delta in enumerate(remaining_deltas):
                        merged = tmp_path / f"merged-{index}.duckdb"
                        merge_candidate_into_canonical(verified_paths[delta.accession_number], current, merged)
                        current = merged
                        merged_accessions.append(delta.accession_number)
                    payload = current.read_bytes()

                promotion = storage_root.stage_and_promote(
                    canonical_relative, payload, expected_etag=baseline.etag
                )
                return {
                    "status": "succeeded",
                    "accessions_merged": merged_accessions,
                    "canonical_promotion_count": 1,
                    "baseline_etag": baseline.etag,
                    "result_etag": promotion.new_version.etag,
                }
            except PromotionConflictError as exc:
                _emit_reducer_event(
                    "silver_event_reduce_promotion_conflict",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    expected_etag=exc.expected_etag,
                    conflicting_etag=exc.actual_etag,
                )
                if attempt == max_attempts:
                    raise
                continue
        raise AssertionError("unreachable")
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)
