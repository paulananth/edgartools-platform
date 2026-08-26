# 34 — Add exclusion and evidence-import workflows

**What to build:** Give operators safe, auditable workflows for explicit
source exclusions and checksum-verified evidence imported from another
environment or account.

**Blocked by:** 17 — Make Bronze capture retry-safe and recoverable; 18 —
Materialize ordered logical source revisions

**Status:** ready-for-agent

- [ ] An exclusion is authorized, reasoned, scoped, visible in Source Change
  Status, and cannot masquerade as a source deletion or no-impact result.
- [ ] Cross-environment evidence becomes processable only after explicit local
  authorization, checksum verification, and preserved source lineage.

## Notes

Split out of [25 — Add conflict, repair, exclusion, and evidence-import
workflows](25-add-conflict-repair-and-evidence-import.md), which resolved
that ticket's conflict/repair bullets (1, 2) plus its role-separation bullet
(5) — see that ticket's own Answer section for the full split rationale.
Exclusion and evidence-import are genuinely independent mechanisms with no
dependency on the conflict/repair schema Ticket 25 built
(`source_evidence_conflict`, `SourceRevisionLedger.materialize_repair`,
`acquisition/conflict.py`'s `ConflictLedger`) — nothing here needs to reuse
or extend them.

Some groundwork already exists to build on:
- `FetchDisposition.OPERATOR_EXCLUDED` (`ledger.py`) is already a real enum
  value on `SourceChangeStatus`/`SourceFetchDecisionRecord` — confirmed live
  via `test_postgres_roles_proofs_and_fencing_are_enforced`
  (`tests/integration/test_acquisition_ledger_postgres.py`), which already
  exercises one `OPERATOR_EXCLUDED` decision end-to-end. What's still open is
  whether that's sufficient on its own for "visible in Source Change Status,
  cannot masquerade as a source deletion or no-impact result," or whether a
  distinct exclusion-audit record (reason, scope, operator authorization) is
  also needed, analogous to how Ticket 25 gave conflicts their own
  `source_evidence_conflict` table rather than folding them into
  `source_revision` alone.
- Evidence-import (checksum verification, preserved source lineage,
  cross-environment authorization) has no existing groundwork in this
  package yet — starts from a clean slate.
