"""Recoverable observations into the existing Bookkeeping root run."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from edgar_warehouse.bookkeeping.store import BookkeepingStore

from .store import Conflict, Store


class RunCoordinator:
    def __init__(self, bookkeeping_engine, mdm: Store):
        self.engine = bookkeeping_engine
        self.mdm = mdm

    def start(
        self, run_id: str, expected_batches: list[str], *, manifest_digest: str
    ) -> None:
        if not expected_batches or len(expected_batches) != len(set(expected_batches)):
            raise ValueError("A root run requires a nonempty frozen batch manifest")
        scope = {
            "expected_batches": sorted(expected_batches),
            "manifest_digest": manifest_digest,
            "contract_version": 2,
        }
        with Session(self.engine) as session:
            book = BookkeepingStore(session)
            existing = book.get_pipeline_run(run_id)
            if existing:
                if json.loads(existing["scope_json"]) != scope:
                    raise Conflict("Root run scope changed")
                return
            book.start_pipeline_run(
                {
                    "pipeline_run_id": run_id,
                    "command_name": "mdm.clean",
                    "runtime_mode": "infrastructure_validation",
                    "environment_name": "local",
                    "started_at": datetime.now(UTC),
                    "status": "running",
                    "scope": scope,
                }
            )
            book.commit()

    def reconcile(self, run_id: str) -> dict:
        with Session(self.engine) as session:
            book = BookkeepingStore(session)
            run = book.get_pipeline_run(run_id)
            if run is None:
                raise Conflict("Root run was not registered")
            expected = set(json.loads(run["scope_json"])["expected_batches"])
            with self.mdm.engine.connect() as conn:
                observed = set(
                    conn.scalars(
                        text(
                            "SELECT batch_id FROM mdm_v2.observation WHERE run_id=CAST(:run AS uuid)"
                        ),
                        {"run": run_id},
                    )
                )
                pending = conn.scalar(
                    text("""SELECT count(*) FROM mdm_v2.publication p JOIN mdm_v2.observation o USING(batch_id)
                    WHERE o.run_id=CAST(:run AS uuid) AND p.verified_at IS NULL"""),
                    {"run": run_id},
                )
                # Current review disposition, including a later valid correction,
                # is authoritative; an old publication receipt cannot clear it.
                unresolved = conn.scalar(
                    text("""SELECT count(*) FROM mdm_v2.projection p WHERE p.object_type='review'
                    AND p.body->>'open'='true' AND p.body->>'blocking' IS DISTINCT FROM 'false' AND EXISTS(SELECT 1 FROM mdm_v2.observation o
                    JOIN mdm_v2.batch b USING(batch_id),jsonb_array_elements(b.effects->'projections') old
                    WHERE o.run_id=CAST(:run AS uuid) AND old->>'object_type'='review' AND old->>'object_id'=p.object_id)"""),
                    {"run": run_id},
                )
            report = {
                "expected_batches": len(expected),
                "observed_batches": len(observed),
                "missing_batches": sorted(expected - observed),
                "unexpected_batches": sorted(observed - expected),
                "pending_publications": pending,
                "unresolved_reviews": unresolved,
            }
            complete = expected == observed and pending == 0 and unresolved == 0
            report["end_to_end_complete"] = complete
            book.record_pipeline_verification(
                run_id,
                verification_status="verified" if complete else "incomplete",
                report=report,
            )
            if complete:
                book.complete_pipeline_run(
                    run_id, status="succeeded", writes=[], raw_writes=[], metrics=report
                )
            # A lost acknowledgement is harmless: another call derives the same
            # completion from retained MDM receipts and the frozen root scope.
            book.commit()
            return report
