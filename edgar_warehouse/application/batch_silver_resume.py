"""Durable, run-scoped recovery contract for default-path BatchSilver batches.

Reuses relationship_bulk_load.py's content-derived batch identity and
low-level marker path/listing helpers (release_mode-agnostic), but writes a
distinct, weaker-guarantee marker than the strict/release_mode path's: this
one records only "bootstrap-batch completed for this CIK set," not strict
mode's reconciled-terminal-outcomes guarantee (inventory_fingerprint,
ledger_fingerprint, terminal_counts). The two marker shapes intentionally do
not share a schema_version namespace -- see build_default_batch_done_marker.

pipeline-resumability ticket 02 (.scratch/pipeline-resumability/issues/
02-design-resume-from-stage-mechanism.md) is the design record this module
implements.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.application.relationship_bulk_load import (
    InventoryError,
    batch_identity_for_ciks,
    build_remaining_cik_batches,
    list_done_batch_identities,
    parse_cik_batches_jsonl,
)
from edgar_warehouse.infrastructure.object_storage import (
    list_uri_child_names,
    object_exists,
    read_bytes,
    write_uri_text,
)

_SCHEMA_VERSION = 1


class ResumeRunNotFoundError(WarehouseRuntimeError):
    """A --resume-ledger-run-id was given but no frozen batch manifest exists for it.

    Distinguishes a bogus/typo'd pointer (or a run that never got far enough
    to seed cik_batches.jsonl) from a legitimately fully-completed run --
    the latter has a real manifest and simply zero remaining batches, which
    is a valid, non-error outcome of compute_remaining_batches.
    """


def resume_prefix(run_id: str) -> str:
    """Relative prefix (under WAREHOUSE_BRONZE_ROOT / context.bronze_root)
    for one BatchSilver run's manifest and markers.

    Matches default_path_resolver().cik_universe_batches_path()'s own
    relative_path convention exactly ("reference/cik_universe/runs/{run_id}/
    cik_batches.jsonl") -- NOT prefixed with "warehouse/bronze/", since
    every caller here passes context.bronze_root.root (itself already
    WAREHOUSE_BRONZE_ROOT, e.g. "s3://bucket/warehouse/bronze") as the root,
    the same way _write_cik_universe_batches does via
    context.bronze_root.write_text(relative_path, ...). A resumed run's
    ComputeRemainingBatches step reads from the same location the original
    run's SeedFromBronze wrote to.
    """
    return f"reference/cik_universe/runs/{run_id}"


def cik_batches_path(run_id: str) -> str:
    return f"{resume_prefix(run_id)}/cik_batches.jsonl"


def batch_done_prefix(run_id: str) -> str:
    return f"{resume_prefix(run_id)}/batch_done/"


def build_default_batch_done_marker(
    *,
    ciks: Iterable[int | str],
    resume_ledger_run_id: str,
    completed_at: str,
) -> dict[str, Any]:
    """Weaker-guarantee done marker for the default (non-release_mode) path."""
    cik_values = sorted(int(cik) for cik in ciks)
    if not cik_values:
        raise InventoryError("default batch done marker requires a non-empty CIK list")
    return {
        "schema_version": _SCHEMA_VERSION,
        "marker_kind": "default_batch_done",
        "batch_identity": batch_identity_for_ciks(cik_values),
        "cik_list": ",".join(str(cik) for cik in cik_values),
        "cik_count": len(cik_values),
        "resume_ledger_run_id": str(resume_ledger_run_id),
        "completed_at": str(completed_at),
    }


def write_default_batch_done_marker(
    *,
    bronze_root: str,
    ciks: Iterable[int | str],
    resume_ledger_run_id: str,
    completed_at: str,
) -> str:
    """Persist the marker after a real bootstrap-batch success. Returns the path written."""
    marker = build_default_batch_done_marker(
        ciks=ciks, resume_ledger_run_id=resume_ledger_run_id, completed_at=completed_at,
    )
    path = (
        f"{bronze_root.rstrip('/')}/"
        f"{batch_done_prefix(resume_ledger_run_id)}{marker['batch_identity']}.json"
    )
    write_uri_text(path, json.dumps(marker, indent=2, sort_keys=True) + "\n")
    return path


def compute_remaining_batches(
    *,
    bronze_root: str,
    resume_ledger_run_id: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Fail-closed remaining-batch computation for BatchSilver resume.

    Reads the ORIGINAL run's frozen cik_batches.jsonl (never regenerated --
    the candidate set a resume may use) plus its accumulated done markers,
    and returns (remaining_batches, counts). Raises ResumeRunNotFoundError
    when the pointed-at run has no readable, non-empty manifest -- this is
    what separates a bogus pointer from a legitimately fully-done run
    (counts["remaining_batch_count"] == 0 with a real manifest is a valid,
    non-error result that should proceed to MdmRun with an empty Map).
    """
    root = bronze_root.rstrip("/")
    manifest_path = f"{root}/{cik_batches_path(resume_ledger_run_id)}"
    if not object_exists(manifest_path):
        raise ResumeRunNotFoundError(
            f"resume_ledger_run_id {resume_ledger_run_id!r} has no frozen "
            f"cik_batches.jsonl at {manifest_path} -- refusing to resume"
        )
    try:
        batches_text = read_bytes(manifest_path).decode("utf-8")
        all_batches = parse_cik_batches_jsonl(batches_text)
    except (OSError, UnicodeError, InventoryError, ValueError) as exc:
        raise ResumeRunNotFoundError(
            f"resume_ledger_run_id {resume_ledger_run_id!r} manifest at "
            f"{manifest_path} could not be read/parsed: {exc}"
        ) from exc
    if not all_batches:
        raise ResumeRunNotFoundError(
            f"resume_ledger_run_id {resume_ledger_run_id!r} manifest at "
            f"{manifest_path} is empty -- refusing to resume"
        )
    done_prefix = f"{root}/{batch_done_prefix(resume_ledger_run_id)}"
    done_names = list_uri_child_names(done_prefix)
    done_ids = list_done_batch_identities(done_names)
    remaining = build_remaining_cik_batches(all_batches, done_ids)
    counts = {
        "total_batch_count": len(all_batches),
        "done_batch_count": len(done_ids),
        "remaining_batch_count": len(remaining),
    }
    return remaining, counts
