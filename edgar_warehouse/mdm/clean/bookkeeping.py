"""Recoverable observations into the existing Bookkeeping root run."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text, update
from sqlalchemy.orm import Session

from edgar_warehouse.bookkeeping.models import PipelineRun
from edgar_warehouse.bookkeeping.store import BookkeepingStore

from .store import Conflict, Store, canonical


class RunCoordinator:
    def __init__(self, bookkeeping_engine, mdm: Store):
        self.engine = bookkeeping_engine
        self.mdm = mdm

    def execute(self, run_id: str, batch_id: str, action):
        """Journal one invocation separately from its atomic business commit.

        A lost terminal acknowledgement leaves a started attempt. Reconciliation
        derives business completion from observations, never from this event.
        """
        attempt = str(uuid4())

        def record(phase, detail):
            with self.mdm.engine.begin() as conn:
                conn.execute(
                    text(
                        "SELECT mdm_v2.record_attempt(CAST(:a AS uuid),CAST(:r AS uuid),:b,:p,CAST(:d AS jsonb))"
                    ),
                    {
                        "a": attempt,
                        "r": run_id,
                        "b": batch_id,
                        "p": phase,
                        "d": canonical(detail),
                    },
                )

        record("started", {})
        try:
            result = action()
        except Exception as exc:
            record("error", {"error_type": type(exc).__name__})
            raise
        record(
            "finished",
            {"generation": result["generation"], "duplicate": result["duplicate"]},
        )
        return result

    def start(
        self,
        run_id: str,
        expected_batches: list[str],
        *,
        manifest_digest: str,
        native_consumption: dict | None = None,
    ) -> None:
        if not expected_batches or len(expected_batches) != len(set(expected_batches)):
            raise ValueError("A root run requires a nonempty frozen batch manifest")
        scope = {
            "expected_batches": sorted(expected_batches),
            "manifest_digest": manifest_digest,
            "contract_version": 2,
        }
        if native_consumption is not None:
            scope["native_consumption"] = native_consumption
        with Session(self.engine) as session:
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:run,0))"),
                {"run": run_id},
            )
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

    def completed_source(self, run_id: str) -> dict:
        """A cursor is insufficient: independently reconcile whole-source work."""
        if not self.reconcile(run_id).get("source_consumption_complete", False):
            raise Conflict("Previous source publication is not fully consumed")
        with Session(self.engine) as session:
            run = BookkeepingStore(session).get_pipeline_run(run_id)
            if run is None:
                raise Conflict("Previous root run disappeared")
            return json.loads(run["scope_json"])["native_consumption"]

    def reconcile(self, run_id: str) -> dict:
        with Session(self.engine) as session:
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:run,0))"),
                {"run": run_id},
            )
            book = BookkeepingStore(session)
            run = book.get_pipeline_run(run_id)
            if run is None:
                raise Conflict("Root run was not registered")
            scope = json.loads(run["scope_json"])
            expected = set(scope["expected_batches"])
            source_report = {}
            with self.mdm.engine.connect().execution_options(
                isolation_level="REPEATABLE READ"
            ) as conn:
                observed = set(
                    conn.scalars(
                        text(
                            "SELECT batch_id FROM mdm_v2.observation WHERE run_id=CAST(:run AS uuid)"
                        ),
                        {"run": run_id},
                    )
                )
                pending = conn.scalar(
                    text("""WITH root_batches AS (
                      SELECT batch_id FROM mdm_v2.observation WHERE run_id=CAST(:run AS uuid)
                    ), review_ids AS (
                      SELECT old->>'object_id' AS id FROM root_batches r
                      JOIN mdm_v2.batch b USING(batch_id), jsonb_array_elements(b.effects->'projections') old
                      WHERE old->>'object_type'='review'
                    ), required_batches AS (
                      SELECT batch_id FROM root_batches UNION
                      SELECT p.batch_id FROM mdm_v2.projection p JOIN review_ids r ON r.id=p.object_id
                      WHERE p.object_type='review'
                    ) SELECT count(*) FROM mdm_v2.publication p JOIN required_batches r USING(batch_id)
                    WHERE p.verified_at IS NULL"""),
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
                attempts = {
                    event: count
                    for event, count in conn.execute(
                        text("""SELECT event,count(*) FROM mdm_v2.attempt_event
                    WHERE run_id=CAST(:run AS uuid) GROUP BY event"""),
                        {"run": run_id},
                    ).all()
                }
                if "native_consumption" in scope:
                    from .native_consumption import consumption_report

                    # Only bounded per-batch summaries cross this boundary; never
                    # reload millions of retained source records to reconcile.
                    summaries = conn.execute(
                        text("""SELECT b.batch_id,
                      b.effects->'continuity_proof' AS continuity_proof,
                      b.effects->'source_accounting' AS source_accounting,
                      jsonb_array_length(coalesce(b.effects->'assertions','[]')) AS normalized,
                      jsonb_array_length(coalesce(b.effects->'deferred','[]')) AS deferred,
                      NOT EXISTS(SELECT 1 FROM jsonb_array_elements(
                        coalesce(b.effects->'assertions','[]') || coalesce(b.effects->'deferred','[]')) r
                        WHERE r->>'source_code' IS DISTINCT FROM b.effects->'continuity_proof'->>'source_code'
                           OR r->>'publication_key' IS DISTINCT FROM b.effects->'continuity_proof'->>'publication') AS source_consistent
                      FROM mdm_v2.batch b JOIN mdm_v2.observation o USING(batch_id)
                      WHERE o.run_id=CAST(:run AS uuid)"""),
                        {"run": run_id},
                    ).mappings()
                    source_report = consumption_report(
                        scope["native_consumption"],
                        {r["batch_id"]: dict(r) for r in summaries},
                    )
            report = {
                "expected_batches": len(expected),
                "observed_batches": len(observed),
                "missing_batches": sorted(expected - observed),
                "unexpected_batches": sorted(observed - expected),
                "pending_publications": pending,
                "unresolved_reviews": unresolved,
                "attempt_events": attempts,
                **source_report,
            }
            complete = (
                expected == observed
                and pending == 0
                and unresolved == 0
                and source_report.get("source_consumption_complete", True)
            )
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
            else:
                session.execute(
                    update(PipelineRun)
                    .where(PipelineRun.pipeline_run_id == run_id)
                    .values(status="running", completed_at=None)
                )
            # A lost acknowledgement is harmless: another call derives the same
            # completion from retained MDM receipts and the frozen root scope.
            book.commit()
            return report
