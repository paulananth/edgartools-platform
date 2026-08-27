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

## Answer

**Exclusion (bullet 1): resolved the ticket's own open design question —
a column, not a new table.** Unlike a conflict (its own PENDING/REPAIRED
state machine, independent of any one revision), an exclusion is a one-shot
terminal classification of a single already-immutable Fetch Decision with
no lifecycle of its own — so "scoped" is already fully captured by that
row's existing `source_family`/`logical_source_key`/`candidate_id`
columns. Added `exclusion_reason` directly to `source_fetch_decision`
(nullable, `NOT NULL`-enforced by a real CHECK constraint whenever
`fetch_disposition = 'OPERATOR_EXCLUDED'`, mirroring the existing
`operator_authorization_reference` requirement) — distinct from
`operator_authorization_reference`: one is proof of *who* authorized the
exclusion, the other is the human-readable *why*. "Visible in Source
Change Status" means the real thing by that name, not just the Python
dataclass — `/code-review`'s Spec pass caught that the actual
`source_change_status` Postgres view (013's own comment: "for ad-hoc
operator queries against Postgres directly") wasn't updated in the first
draft; fixed by widening it too. "Cannot masquerade as a source deletion
or no-impact result" was already structurally true before this ticket —
`FetchDisposition` has no deletion value at all (retirement lives entirely
in Silver), and `OPERATOR_EXCLUDED` is a distinct enum/CHECK-constrained
value from `ProcessingDisposition.NO_IMPACT` in an entirely different
table — confirmed, not something this ticket needed to add.

**Evidence-import (bullet 2): new `EvidenceImportLedger`/
`source_evidence_import`, mirroring `ConflictLedger`'s shape.** Checksum
verification happens before any Bronze write (fails closed, not
written-then-flagged); the local write reuses the exact content-hash-keyed
relative-path scheme the Ticket 14/15 capture Facade already uses
(`{source_family}/{raw_evidence_hash}`), so imported evidence is
indistinguishable from a normal capture once it lands. "Becomes
processable" needed no new `FetchDisposition` value or Facade path: the
returned `local_bronze_reference` is immediately usable as a normal
`verified_evidence_reference` on an ordinary
`create_fetch_decision(disposition=ALREADY_CAPTURED_VERIFIED, ...)` call —
proven end-to-end by a real-Postgres integration test. Runs under the
existing `DecisionOwnerRole.ACQUISITION_OPERATOR` role (a new
`require_operator_role` helper) rather than a new role/enum — the same
role OPERATOR_REQUEST/OPERATOR_EXCLUDED fetch decisions already require,
since an import is the same class of deliberate, explicit operator action.
No new Postgres role provisioned; migration 017 grants the existing
`edgartools_acquisition_operator` role INSERT+SELECT, every other
operational role SELECT-only — proven at the real GRANT level, not just by
which Python method happens to call it (a direct-SQL bypass attempt from
every other role is rejected).

**A real, structural bug found and fixed along the way, not just a schema
addition.** Widening `source_change_status` inside 017 via
`CREATE OR REPLACE VIEW` (appending `exclusion_reason` at the end — a
mid-list insert first failed live with "cannot change name of view column
'next_action' to 'exclusion_reason'", since Postgres reads column
*position*, not just presence) works for a first install, but any later
full owner-privileged rerun of `migrate()` — e.g. `bootstrap-prod-mdm.sh`'s
disaster-recovery re-provisioning path, a real operational pattern this
repo already relies on — reproduced a permanent break: 013's own
unconditional `CREATE OR REPLACE VIEW source_change_status` statement
always reasserts the original 12-column shape, and Postgres refuses to
narrow a view back down ("cannot drop columns from view"), aborting the
whole migration before 017 even gets a chance to re-widen it in that same
run. Root cause: this is the first time any migration in this repo has
widened an object an *earlier* migration's file also unconditionally
recreates — every prior sibling (015, 016) only ever added wholly new
objects, never touched. Fixed at the actual point of fragility, in 013's
own file (not a new migration, not Python-side patching): wrapped that one
`CREATE OR REPLACE VIEW` in a `DO $$ ... EXCEPTION WHEN OTHERS ...`
block that swallows specifically the "cannot drop columns from view" case
(re-raising anything else) — a fresh install is unaffected (the view
doesn't exist yet in any shape), and a rerun after 017 has already widened
it is now a safe no-op instead of a permanent failure. Proven by a real
regression test running the actual admin-engine rerun sequence twice in a
row against real Postgres (reproduced the failure before the fix, passed
after).

**`/code-review` (Standards + Spec axes, both parallel sub-agents) found no
hard standards violations** and confirmed `evidence_import.py` is a
faithful mirror of `conflict.py`'s transaction-boundary/idempotency shape
(the same single check-then-insert race window `ConflictLedger.
record_evidence_conflict` already has, inherited, not new). One
pre-existing, out-of-scope gap the Spec reviewer flagged but this ticket
doesn't need to close: `OPERATOR_EXCLUDED`'s "authorized" property is tied
to `cause=OPERATOR_REQUEST`, not directly to `disposition`, so a
`DUE_POLICY`/coordinator-owned decision could theoretically also carry
`disposition=OPERATOR_EXCLUDED` — a broader ledger-wide role-binding gap
predating this ticket, not something bullet 1 asked this ticket to close.

**Tests:** 6 new SQLite unit tests (`test_ledger.py`), 7 new
`EvidenceImportLedger` unit tests (`test_evidence_import.py`), 5 new
migration static-assertion tests (`test_migration.py`), 7 new real-Postgres
integration tests (`test_exclusion_and_evidence_import_postgres.py` —
migration rerun-safety, the CHECK constraint proven live via a direct-SQL
bypass, the widened view's real visibility, GRANT-level operator-only
fencing, a full `EvidenceImportLedger` round trip, and the 013/017
interaction regression test), plus updates to two pre-existing real-Postgres
fixtures (`test_acquisition_ledger_postgres.py`, `test_conflict_postgres.py`)
that needed 017 applied too once `SourceFetchDecisionRecord`'s ORM mapping
grew the new column. Full repo suite green: 2686 passed, 4 skipped
(pre-existing, unrelated).
