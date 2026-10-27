# Governed caller retirement

Baseline: main `790a2ca6`, after routine-retirement PR #1180. Development results below are bounded. The final independently installed
qualification and all CI results are recorded in the final section.

## Implementation

Normal Store, matching, affected-record retrieval, assessments, Context,
master readers, Silver identifiers, run observation and workers use only the
governed storage contract. The owner CLI installs that contract by default;
explicit legacy installation and populated native admission are refused.
The runtime AST check forbids calls to all 34 retired SQL business routines.
The old git-snapshot parity/benchmark script was removed after retaining 64
explicit field/identity answer pairs while both implementations agreed. All 128
individually changed answers fail the maintained-engine assertions; no retired
implementation is loaded by the new tests.

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

- Final affected MDM/unit/architecture cohort: 1,132 checks pass (91 seconds).
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
- Final installed workflow and full CI: passed at the committed repair revision;
  see the final qualification section. Local results were not substituted.

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
the two archived Claude paths explicitly assigned to Codex by the operator
(Proving counts and the retained source-chain test), plus the execution module
now also changed by Claude ticket 138. The operator explicitly authorized Codex
to take over and complete retirement at 2026-10-27 07:30 ET. Both Claude
worktrees are untouched; this PR publishes only its own tested changes.

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

## Committed installation checkpoint and CI repairs

Runtime revision `0e45ce5967e829c507429ac75cd3cd3cf91e072f` was independently
built as all five wheels outside the checkout. Fourteen targeted installed
cases pass per engine, across both configured kinds: rule consolidation,
conflicting identifier order, inspection, interrupted upgrade, an injected
atomic-write fault, candidate arrival and separate worker/verifier processes.
All ten installed parse→prepare→master variants and the installed field/census
publication/recovery case also pass after porting their assertions and verifier
grants. The actual six-store backup/restore test passes with three retained
masters and its original Silver IDs and exact integer data.

The first CI run (`40430799658`) exposed stale table/protocol expectations,
verifier metadata grants and the standalone scenario's successful exit before
harness receipt emission. These are corrected without dropping their behavioral
assertions. The four-owner MySQL registration regression then exposed a real
repeatable-read race: taking the gate lock did not refresh the earlier snapshot.
The pin duplicate lookup now uses a locking read, preserving collision checks.
The unchanged concurrency test passes; six targeted PostgreSQL and four MySQL
regression checks pass. SQL Server's retained adapter checks remain a CI gate.

Unchanged runtime statements were restored to original formatting with an AST
equality check, reducing unrelated diff churn. Final CI on the repair revision
passes; the final qualification below records the committed installation.

## Final qualification

[CI run 40491799251](https://github.com/paulananth/edgartools-platform/actions/runs/40491799251)
passes **all 21 checks** on repair head `005284685b39fdaaa1723b990edb1a97563b76db`.
The independently installed merge revision is
`0ee6f60e585942bd5db96a831cddad50ba2ac5f5`, whose parents include that PR head.
The run took **19 minutes 47 seconds** and finished at 2026-10-27 07:11 ET.

| Installed group | PostgreSQL | MySQL |
| --- | ---: | ---: |
| Merge | 58 | 58 |
| Readers, identifiers and search | 52 | 52 |
| Atomic and upgrade boundaries | 36 | 36 |
| Workers, verification and publication | 18 | 18 |
| Total | 164 | 164 |

Every expected engine/kind/case appears exactly once, every outcome passes,
all cleanup flags are true, and configuration hashes match across engines for
each case/kind. Both invented kinds cover all 18 qualification families. No
alias copies or contradictory outcomes were counted. The retained SQL Server
adapter check also passes; its complete normal workflow remains deferred.

[Counts-only qualification record](caller-retirement-ci.json) retains the
head, installed revision, outcome totals, family counts and elapsed time.
There is no provider acquisition, hosted migration, source activation or
populated native conversion in this qualification. Named merge approval remains
with the operator.
