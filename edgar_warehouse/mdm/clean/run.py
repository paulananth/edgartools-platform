"""A Merge Stage run: frozen scope, attempts and reconciled governed outcome."""

from __future__ import annotations


from .store import Store


class RunCoordinator:
    def __init__(self, mdm: Store):
        self.mdm = mdm

    def scope(self, run_id: str) -> dict | None:
        from .prepared_runs import scope

        return scope(self.mdm,run_id)

    def execute(
        self, run_id: str, batch_id: str, action, *, checks: dict | None = None
    ):
        """Journal one invocation separately from its atomic business commit.

        A lost terminal acknowledgement leaves a started attempt. Reconciliation
        derives business completion from observations, never from this event.
        `checks` is the batch's run report profile (`quality.profile` and the
        run's `as_of`), kept with the finished event of a batch this run
        merged, so the run's report sums every batch however many calls ran it.
        """
        from .prepared_runs import execute

        return execute(self.mdm,run_id,batch_id,action,checks=checks)

    def start(
        self,
        run_id: str,
        expected_batches: list[str],
        *,
        manifest_digest: str,
        mapping_versions: dict[str, int] | None = None,
    ) -> None:
        from .prepared_runs import start

        return start(self.mdm,run_id,expected_batches,manifest_digest=manifest_digest,
                     mapping_versions=mapping_versions)

    def reconcile(self, run_id: str) -> dict:
        from .prepared_runs import reconcile

        return reconcile(self.mdm,run_id)
