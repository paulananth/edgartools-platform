"""A Merge Stage run: its frozen scope, attempts and reconciled outcome.

The run lives in MDM itself (`mdm.run`, migration 043), written only
through `start_run` and `finish_run`; the legacy Bookkeeping `pipeline_run`
it used is retired (platform validation slice 2a).
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text

from .quality import run_checks
from .store import Conflict, Store, canonical


def _count_waiting_links(mdm) -> int:
    with mdm.engine.connect() as conn:
        return conn.scalar(text("""SELECT count(*) FROM mdm.current_record WHERE object_type='review'
            AND body->>'waiting_for_end'='true' AND body->>'retired' IS DISTINCT FROM 'true'"""))


class RunCoordinator:
    def __init__(self, mdm: Store):
        self.mdm = mdm

    def _scope(self, run_id: str) -> dict | None:
        with self.mdm.engine.connect() as conn:
            return conn.scalar(
                text("SELECT scope FROM mdm.run WHERE run_id=CAST(:run AS uuid)"),
                {"run": run_id},
            )

    def execute(self, run_id: str, batch_id: str, action, *, checks: dict | None = None):
        """Journal one invocation separately from its atomic business commit.

        A lost terminal acknowledgement leaves a started attempt. Reconciliation
        derives business completion from observations, never from this event.
        `checks` is the batch's run report profile (`quality.profile` and the
        run's `as_of`), kept with the finished event of a batch this run
        merged, so the run's report sums every batch however many calls ran it.
        """
        attempt = str(uuid4())

        def record(phase, detail):
            with self.mdm.engine.begin() as conn:
                conn.execute(
                    text(
                        "SELECT mdm.record_attempt(CAST(:a AS uuid),CAST(:r AS uuid),:b,:p,CAST(:d AS jsonb))"
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
        finished = {"generation": result["generation"], "duplicate": result["duplicate"]}
        if checks is not None and not result["duplicate"]:
            finished["checks"] = checks
        record("finished", finished)
        return result

    def start(
        self,
        run_id: str,
        expected_batches: list[str],
        *,
        manifest_digest: str,
    ) -> None:
        if not expected_batches or len(expected_batches) != len(set(expected_batches)):
            raise ValueError("A root run requires a nonempty frozen batch manifest")
        scope = {
            "expected_batches": sorted(expected_batches),
            "manifest_digest": manifest_digest,
            "contract_version": 2,
        }
        existing = self._scope(run_id)
        if existing is not None and existing != scope:
            raise Conflict("Root run scope changed")
        # start_run refuses a changed scope too, for a concurrent start.
        with self.mdm.engine.begin() as conn:
            conn.execute(
                text("SELECT mdm.start_run(CAST(:run AS uuid),CAST(:scope AS jsonb))"),
                {"run": run_id, "scope": canonical(scope)},
            )

    def reconcile(self, run_id: str) -> dict:
        scope = self._scope(run_id)
        if scope is None:
            raise Conflict("Root run was not registered")
        expected = set(scope["expected_batches"])
        with self.mdm.engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as conn:
            observed = set(
                conn.scalars(
                    text(
                        "SELECT batch_id FROM mdm.run_batch WHERE run_id=CAST(:run AS uuid)"
                    ),
                    {"run": run_id},
                )
            )
            pending = conn.scalar(
                text("""WITH root_batches AS (
                  SELECT batch_id FROM mdm.run_batch WHERE run_id=CAST(:run AS uuid)
                ), review_ids AS (
                  SELECT old->>'object_id' AS id FROM root_batches r
                  JOIN mdm.batch b USING(batch_id), jsonb_array_elements(b.effects->'projections') old
                  WHERE old->>'object_type'='review'
                ), required_batches AS (
                  SELECT batch_id FROM root_batches UNION
                  SELECT p.batch_id FROM mdm.current_record p JOIN review_ids r ON r.id=p.object_id
                  WHERE p.object_type='review'
                ) SELECT count(*) FROM mdm.outbox p JOIN required_batches r USING(batch_id)
                WHERE p.verified_at IS NULL"""),
                {"run": run_id},
            )
            # Current review disposition, including a later valid correction,
            # is authoritative; an old publication receipt cannot clear it.
            unresolved = conn.scalar(
                text("""SELECT count(*) FROM mdm.current_record p WHERE p.object_type='review'
                AND p.body->>'open'='true' AND p.body->>'blocking' IS DISTINCT FROM 'false' AND EXISTS(SELECT 1 FROM mdm.run_batch o
                JOIN mdm.batch b USING(batch_id),jsonb_array_elements(b.effects->'projections') old
                WHERE o.run_id=CAST(:run AS uuid) AND old->>'object_type'='review' AND old->>'object_id'=p.object_id)"""),
                {"run": run_id},
            )
            # Every link waiting for its other end, in this run or an earlier
            # one: counted and listed, never unresolved (mastering to-do 13).
            waiting = [dict(r) for r in conn.execute(
                text("""SELECT p.body->>'subject' AS subject, p.body->'relationship'->>'type' AS type,
                p.body->'relationship'->>'target_subject' AS target_subject, p.body->'missing' AS missing,
                p.body->>'reason' AS reason FROM mdm.current_record p WHERE p.object_type='review'
                AND p.body->>'waiting_for_end'='true' AND p.body->>'retired' IS DISTINCT FROM 'true'
                ORDER BY p.object_id LIMIT 101""")).mappings()]
            # The run report checks (rebuild ticket 10): one profile per batch
            # this run merged, the last finished attempt's.
            checks = [r[0] for r in conn.execute(
                text("""SELECT DISTINCT ON (batch_id) detail->'checks' FROM mdm.attempt_event
                WHERE run_id=CAST(:run AS uuid) AND event='finished' AND detail ? 'checks'
                ORDER BY batch_id, occurred_at DESC"""),
                {"run": run_id},
            ).all()]
            attempts = {
                event: count
                for event, count in conn.execute(
                    text("""SELECT event,count(*) FROM mdm.attempt_event
                WHERE run_id=CAST(:run AS uuid) GROUP BY event"""),
                    {"run": run_id},
                ).all()
            }
        report = {
            "expected_batches": len(expected),
            "observed_batches": len(observed),
            "missing_batches": sorted(expected - observed),
            "unexpected_batches": sorted(observed - expected),
            "pending_publications": pending,
            "unresolved_reviews": unresolved,
            "waiting_links": len(waiting) if len(waiting) <= 100 else _count_waiting_links(self.mdm),
            "waiting_link_list": waiting[:100],
            "attempt_events": attempts,
            "checks": run_checks([c["profile"] for c in checks], as_of=checks[0]["as_of"]) if checks else {},
        }
        complete = (
            expected == observed
            and pending == 0
            and unresolved == 0
        )
        report["end_to_end_complete"] = complete
        # A lost acknowledgement is harmless: another call derives the same
        # completion from retained MDM receipts and the frozen root scope.
        with self.mdm.engine.begin() as conn:
            conn.execute(
                text("SELECT mdm.finish_run(CAST(:run AS uuid),CAST(:report AS jsonb),:complete)"),
                {"run": run_id, "report": canonical(report), "complete": complete},
            )
        return report
