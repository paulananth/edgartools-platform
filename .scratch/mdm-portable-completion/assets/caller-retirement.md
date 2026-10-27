# Governed caller retirement

Baseline: main `790a2ca6`, after routine-retirement PR #1180. Qualification in
this note is local and bounded. Independent installed qualification and CI
remain open until their final-revision results are recorded.

## Implementation

Normal Store, matching, affected-record retrieval, assessments, Context,
master readers, Silver identifiers, run observation and workers use only the
governed storage contract. The owner CLI installs that contract by default;
explicit legacy installation and populated native admission are refused.
The runtime AST check forbids calls to all 34 retired SQL business routines.
The old git-snapshot parity/benchmark script was removed rather than retaining
an unmaintained second computation oracle.

Proving counts read keyset pages on one repeatable snapshot. Their new hash
contract is `governed-record-bytes-v1`: hash exact stored publication bytes in
stable storage-key order, without lossy JSON or numeric conversion. This is
an explicit replacement contract, not equality with historical SQL row hashes.

A real separate-role local bootstrap exposed a configuration-registration gap.
New owner migration 029 delegates only opaque policy/mapping/schema reference
registration under the existing save lock. Registrars gain no gate UPDATE,
master DML or master-save capability; runtime gains no registration capability.
The local setup grants required read access to its separate verifier and
registrar. Delegated registrar setup is qualified for PostgreSQL only;
MySQL retains its existing owner registration path. No hosted store is migrated.

## Tests retained and retired

[Every retired integration test](retired-calculation-tests.json) retains its
old file/name, disposition and maintained calculation/caller/storage suites:
254 functions in 33 files. Historical native projection shape and old migration
API assertions are retired with those APIs. Historical SQL 001–027 remains
unchanged; the normal owner refuses populated native conversion. Current
populated governed upgrades, restricted grants, concurrent writers, leases,
atomic faults, immutable evidence and recovery remain integration obligations.

Four SQL-body inspections in the input-size unit module were removed. The
maintained real-engine large-payload test now also persists and retrieves an
entire request above the former 16 MiB cap, alongside its 805-key bulk case.

## Development qualification

- 1,072 affected MDM/unit/architecture checks pass (96 seconds).
- PostgreSQL configured kinds, routes, worker/verifier, Proving hash and schema:
  18 checks pass; subsequent full route/retained-plan/transport/fresh-mastering
  cohort: 28 checks pass (source-chain tests passed before a stale count-table
  assertion was corrected and qualified by that subsequent cohort).
- Real local five-store setup and restore, Silver, execution and filed-identifier
  chain checks passed before the worker fixture's publication-order correction;
  the worker and separate-verifier cases pass after that correction.
- Both engines, both invented kinds: normal inspection passes, including exact
  byte hashes, waiting/set-aside records, keyset index plans and duplicate replay.
- PostgreSQL: eight and MySQL: six selected storage checks pass, covering the
  former size cap, populated worker upgrade, candidate reindexing and registration
  scope; PostgreSQL additionally exercises registrar rights, rollback and drift.
- Final installed workflow and full CI: pending. These local results are not
  substituted for those gates.

## Counts

[Reproducible source counts](caller-retirement-counts.json) separate changed
runtime modules from deleted test/oracle code. Physical lines include formatting
and comments; they are not a semantic deletion estimate. The original 4,874
historical SQL lines remain checksum-preserved. Of the original 36 legacy
routines, 34 were already retired by #1180 and two integrity guards remain.
The new registration capability and generated atomic storage capabilities are
storage enforcement, outside that legacy-business inventory.

## Review

### Standards

Own fresh branch/worktree, affected testmon cohorts under five minutes, private
diagnostics, no provider requests, no production changes. Overlap guard reports
only the two archived Claude paths explicitly assigned to Codex by the operator:
Proving counts and the retained source-chain test. The archive is untouched.

### Spec

Removes the second PostgreSQL calculation/caller route; normal configured
computation continues through the same engine on PostgreSQL and MySQL. Storage
integrity, historical data and owner conversion refusals remain. SQL Server full
workflow and master onboarding are separate pending work.

### GoF

History (#1159, #1164, #1171, #1183) shows repeated changes to parallel reader
and save branches. Delete the superseded branch and keep the existing Adapter
boundary. Another Store hierarchy would add migration/recovery cost without
eliminating an actual variation. The only new privileged operation is opaque
metadata registration, justified by the real registrar failure and covered by
rights, transaction rollback and function-definition drift checks.
