"""pipeline-resumability ticket 02: Mastering's company-step resume support.

A one-time CIK snapshot (the frozen candidate set -- mirrors
batch_silver_resume.py's philosophy for BatchSilver: never re-derive from
live sec_company on resume) plus batched succeeded-CIK outcome flushes.
Batching (rather than one marker per CIK, matching
edgar_warehouse.application.daily_artifact_resume's/batch_silver_resume's
per-item shape) is a deliberate adaptation for this domain's scale --
~62,190 companies would mean ~62K S3 objects per full run with a per-item
marker; flushing accumulated succeeded-CIK batches at the same cadence as
_progress_log_interval keeps object count proportional to log-interval
granularity instead.

See .scratch/pipeline-resumability/issues/02-design-resume-from-stage-mechanism.md
for the full design record.
"""
from __future__ import annotations

import json
from collections.abc import Iterable

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.object_storage import (
    list_uri_child_names,
    object_exists,
    read_bytes,
    write_uri_text,
)

_PREFIX = "reference/mdm_company_resume/runs"


class ResumeRunNotFoundError(WarehouseRuntimeError):
    """A --resume-ledger-run-id was given but no frozen CIK snapshot exists for it."""


def snapshot_path(run_id: str) -> str:
    return f"{_PREFIX}/{run_id}/cik_snapshot.jsonl"


def outcomes_prefix(run_id: str) -> str:
    return f"{_PREFIX}/{run_id}/outcomes/"


def snapshot_exists(*, bronze_root: str, run_id: str) -> bool:
    return object_exists(f"{bronze_root.rstrip('/')}/{snapshot_path(run_id)}")


def write_snapshot(*, bronze_root: str, run_id: str, ciks: Iterable[int]) -> str:
    """Freeze this run's company candidate set. Called once, at first attempt."""
    cik_values = sorted({int(cik) for cik in ciks})
    body = "".join(json.dumps({"cik": cik}) + "\n" for cik in cik_values)
    path = f"{bronze_root.rstrip('/')}/{snapshot_path(run_id)}"
    write_uri_text(path, body)
    return path


def read_snapshot(*, bronze_root: str, run_id: str) -> list[int]:
    """Read back the frozen candidate set. Fails closed if never written."""
    path = f"{bronze_root.rstrip('/')}/{snapshot_path(run_id)}"
    if not object_exists(path):
        raise ResumeRunNotFoundError(
            f"resume_ledger_run_id {run_id!r} has no frozen CIK snapshot at "
            f"{path} -- refusing to resume"
        )
    text = read_bytes(path).decode("utf-8")
    ciks: list[int] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        ciks.append(int(json.loads(line)["cik"]))
    return ciks


def write_outcome_batch(
    *, bronze_root: str, run_id: str, batch_id: str, ciks: Iterable[int]
) -> str:
    """Flush a batch of newly-succeeded CIKs. batch_id must be unique per flush
    (caller-supplied, e.g. uuid4 hex) -- this module does not track indices."""
    cik_values = sorted({int(cik) for cik in ciks})
    path = f"{bronze_root.rstrip('/')}/{outcomes_prefix(run_id)}{batch_id}.json"
    write_uri_text(path, json.dumps(cik_values, sort_keys=True) + "\n")
    return path


def read_succeeded_ciks(*, bronze_root: str, run_id: str) -> set[int]:
    """Union every flushed outcome batch's CIKs. Empty set if none flushed yet."""
    prefix = f"{bronze_root.rstrip('/')}/{outcomes_prefix(run_id)}"
    names = list_uri_child_names(prefix)
    succeeded: set[int] = set()
    for name in names:
        if not name.endswith(".json"):
            continue
        payload = json.loads(read_bytes(f"{prefix}{name}").decode("utf-8"))
        succeeded.update(int(cik) for cik in payload)
    return succeeded
