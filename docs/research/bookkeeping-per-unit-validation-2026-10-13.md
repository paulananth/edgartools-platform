# Bookkeeping per-unit validation research

Date: 2026-10-13. Code baseline: main `f9e89470`. Status: researched proposal with local baseline measurements; no fix implemented, deployment, or performance qualification. Scope: architectural finding 3 (P2), repeated full-manifest/full-work-table validation during ordinary control operations.

## Research checklist

- [x] Compare three designs against official primary sources — PostgreSQL 16, Python docs, and RFC 6962 sections read; 2026-10-13 19:46 ET.
- [x] Specify integrity, concurrency, and recovery caveats — source-grounded analysis below; 2026-10-13 19:46 ET.
- [x] Define qualification evidence needed before removing scans — benchmark and failure cases below; 2026-10-13 19:46 ET.

## Proposed recommendation

Keep Bookkeeping as the authoritative control store. Admit and freeze definitions once, enforce their immutability in PostgreSQL, then validate the run header and the particular unit involved in each operation. Preserve full reconciliation at explicit admission/audit/recovery boundaries where it has a purpose. Do not make every heartbeat reconstruct the entire run.

This changes the integrity mechanism: the database prevents unauthorized mutation rather than application code repeatedly searching for evidence of mutation. A stored digest alone does not provide that protection: a caller able to rewrite the definition and its digest can rewrite both. The trusted admission path and runtime role restrictions are essential prerequisites.

Local implementation facts supplied by the accompanying review: `_frozen()` loads the Rules export and inputs manifest, reconstructs all work, reads all `work_item` rows for the run, and reconstructs verified expansions. The measured no-heartbeat unit path has eight full scans; a renewal has two; journal delivery has `1 + 2 × event_count`. Existing `work_item` keys are `(run_id, step, unit_key)` and `(run_id, step, ordinal)`. The proposed fix should retain the five-table layout. Current runtime grants already permit reads and restricted `SECURITY DEFINER` functions rather than direct writes. `finish_expand` already bounds children to 128 and atomically locks parent/run, inserts children, accepts the parent receipt, adjusts generated/expected counts, and writes the outbox. Preserve this protocol instead of introducing another control mechanism.

The critical semantic change: current whole-run validation can detect an unrelated row corrupted by a privileged administrator on the next ordinary control call. Unit-local validation would discover that corruption when the row is used or a full audit runs. Runtime-role immutability guards prevent normal unauthorized changes but cannot be presented as protection against unrestricted administration. If immediate unrelated privileged-corruption detection remains a required invariant, retain whole-run inspection: a membership proof for the selected unit cannot detect changes to every other row. The proposed fast path requires documenting this changed detection timing.

## Current baseline, measured locally

The probe used the repository's `test_configured_bookkeeping_postgres.databases`
fixture on a disposable PostgreSQL 16 server, separate worker/verifier logins,
`artifact.copy`, and local content-addressed artifacts. SQLAlchemy's
`after_cursor_execute` counted returned rows for `_frozen()`'s whole-run query;
an `Artifacts.read` observer counted Rules/manifest reads. Each sample completed
one unit, renewed it once, and delivered its one journal event. It did not
complete the entire run. Raw observations are in
[MEASUREMENTS.json](../../.planning/workstreams/bookkeeping-scan-research/MEASUREMENTS.json).

| Units present in the run | Whole-run scans, completion plus one renewal | Work rows returned by those scans | Rules reads / input-manifest reads | Completion plus renewal, seconds |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 10 | 100 | 10 / 10 | 0.1792 |
| 100 | 10 | 1,000 | 10 / 10 | 0.2605 |
| 1,000 | 10 | 10,000 | 10 / 10 | 1.7254 |

Operation breakdown is unchanged at each size: claim/envelope 3 scans,
renewal 2, report 1, verifier claim/envelope 2, admission 2. Without renewal,
the earlier review's eight scans are reproduced. Delivering one event adds
three full scans; the source shows one initial scan plus two per event because
`journal_event()` rebuilds the expected envelope twice. Fixing only task
claiming would leave this other source of repeated whole-run work.

These are single baseline observations, excluding database initialization,
run submission, subprocess startup and journal-delivery latency from the timed
column. They include measurement overhead and use a shared warmed local test
server. They establish repeated work and its dependence on run size; they do
not establish a speedup, production latency or a completed optimization.

## Exact changes proposed in this repository

The names below describe proposed helper responsibilities, not new public CLI
commands or an implemented API.

| Existing path | Proposed change | Safety condition |
| --- | --- | --- |
| [`engine.py`, `_frozen`](../../edgar_warehouse/bookkeeping/clean/engine.py#L63) | Retain its complete audit; separate a small `_run_context` from `_audit_run` | Context rechecks the pinned Rules identity and validated configuration but never decodes the whole input manifest or enumerates all work. |
| `start`, `start_run` | Fully authenticate Rules and input manifest, compile work once, and atomically admit/seal the exact definitions | The accepted definition set must be tied to the validated manifest/Rules identities through a protected admission path. A self-generated row hash is not that tie. |
| `tasks`, `claim`, `envelope`, `renew`, `report`, `verifications`, `admit` | Use `_run_context` plus the indexed `_row` and relevant prerequisite receipts | Keep `_same_work`, exact candidate/report binding, issuer checks, live leases and destination verification. Preserve acquisition authority checks in `_run_context`. |
| `_context`, `_receipt`, `_compose` | Supply one validated immutable context within a command; authenticate only its prerequisite closure | Preserve receipt bytes/hashes and the entire referenced chain. Bounded ordinary calls do not imply bounded cost for arbitrarily wide/deep fan-in. |
| `finish_expand` | Keep its atomic transaction; record immutable parent lineage/accepted definition identity on children | First admission must reject collisions; replay compares the sealed batch and does not increment the expected count again. Zero-child expansions remain sealed. |
| `deliver`, `journal_event` | Build a verified run context once per delivery batch and an expected event once per outbox row | Append and read-back verification use that same immutable event; journal acknowledgement still follows verified delivery. Do not cache delivery status. |
| `resume`, `finalize` | Retain full definition, receipt-chain and accounting reconciliation at these boundaries | Audit a coherent scope; final completion checks that the audited scope/evidence has not changed before it commits. |

Freeze `pipeline_run.submission` and `submission_hash`, and each work row's
`run_id`, `step`, `unit_key`, `ordinal`, `resources` and `unit`. Keep state,
attempts, leases and delivery status mutable through their existing functions.
Once accepted, completion receipts/checks and a parent's expansion seal are
also immutable. Add explicit field guards and protected admission lineage in a
new numbered migration; do not edit installed checksummed migrations. Retain
the five control tables and the audited compaction exception.

The write-path review must cover direct calls to `start_run`, `finish_expand`,
`finish` and other granted functions, not just Python callers. Ordinary
completion of an expansion parent must not bypass its expansion seal. A fast
path is enabled only when admission and all mutation routes enforce these
conditions. Existing runs need a full audit plus an explicit validated-format
marker before using it; runs lacking that marker keep the existing checks.
This is compatibility within the current Bookkeeping store, not a legacy-store
fallback.

For finalization, a consistent read is only half the solution. A short
repeatable-read audit can capture a protected control/evidence revision;
`record_checks` must compare it under the run lock and retry reconciliation if
new children or accepted receipts arrived. If a revision is introduced, update
it in the already-serialized admission/completion transactions, including
zero-child seals, and never on every heartbeat. Another valid design is an
explicit finalizing state that prevents those transitions during the audit;
that adds lifecycle behavior and needs separate qualification.

### Implementation sequence and costs

1. Preserve baseline behavior in focused acceptance tests; instrument ordinary
   unit, heartbeat, dependency, expansion and journal paths separately.
2. Add immutable-field guards, protected admission/sealing and compatibility
   eligibility. Run the old audits throughout this step.
3. Split audit from run/unit validation and switch one path at a time, including
   renewal and journal delivery. Share immutable context within commands;
   cache no mutable control state.
4. Qualify recovery/finalization races, generated children and compaction;
   compare increasing run sizes, query plans and complete process paths.

The cost is a schema/grant/protocol review and more explicit integrity tests,
not a new worker framework. No GoF hierarchy is justified: history shows the
existing engine changed for protocol isolation (#801), issuer roles, fan-in
(#928) and configured capture (#933). Splitting full reconciliation from
ordinary validation addresses the measured repeated work directly. A new
Proxy or Mediator would add an execution hop without fixing its scope.

| Design | Ordinary operation | Integrity and practical limitations | Recommendation |
| --- | --- | --- | --- |
| Memoize the existing full validation | First access still loads all units; repeated calls in one process reuse results | Python caches store results in a dictionary; `Popen` launches another process. Thus a separately launched control command starts without the previous interpreter's cache. Caching live lease/status data also risks stale authority. | Optional optimization for verified immutable decoding; insufficient as the P2 fix. |
| Database-enforced immutable definitions plus unit checks | Fetch run header and indexed unit/parent rows; update live state conditionally | Requires protected admission, mutation guards, transactional fanout, and consistent boundary audits. Preserves the existing authoritative store. | Proposed default; smallest complete mechanism for this database-centered system. |
| Merkle membership proofs | Verify a unit and a short path against a trusted root | Requires canonical leaves/order, protected roots and proof storage. Dynamic work needs an append/sealing protocol; membership does not prove all required work completed or validate leases. | Consider only if independently verifiable proofs are an explicit requirement. |

The cache comparison follows [Python `functools.cache`](https://docs.python.org/3/library/functools.html#functools.cache) and [`subprocess.Popen`](https://docs.python.org/3/library/subprocess.html#subprocess.Popen). The subprocess consequence is an inference for a CLI that starts a new interpreter per control call. Merkle membership and append consistency are distinct mechanisms in [RFC 6962 §§2.1.1–2.1.2](https://www.rfc-editor.org/rfc/rfc6962.html#section-2.1.1); adapting them to Bookkeeping is a design proposal, not a PostgreSQL feature.

## How the proposed design works

1. **Protect admitted definitions.** Keep the pinned run descriptor separate from mutable execution state, logically by guarded fields in the existing layout. Freeze configuration/runtime/rules identity, unit identity and descriptor, and parent lineage after admission. A migration-owner role owns tables and guards; the runtime role must not own them or inherit that role. Restrict updates to permitted state fields and deny ordinary definition deletion, truncation, and arbitrary child insertion. Preserve the current legitimate audited compaction through its explicit authorized entry point; a blanket delete prohibition would break that lifecycle.

   PostgreSQL supports column-level privileges, while object ownership inherently permits structural changes. This makes owner separation material, not cosmetic. [PostgreSQL 16 §5.7, Privileges](https://www.postgresql.org/docs/16/ddl-priv.html).

   A row trigger can compare `OLD` and `NEW` fields and raise an error on forbidden changes. Use an all-update guard where necessary: `UPDATE OF` fires based on the statement target list and can miss modifications performed by another `BEFORE` trigger. Also guard deletes and handle `TRUNCATE` through grants or a statement trigger. [CREATE TRIGGER, Description and Notes](https://www.postgresql.org/docs/16/sql-createtrigger.html), [§43.10.1, Trigger Functions](https://www.postgresql.org/docs/16/plpgsql-trigger.html#PLPGSQL-DML-TRIGGER).

2. **Validate the unit being acted on.** Read the protected run header and exact unit using its key; for a generated unit, read its sealed parent/batch commitment as well. Compare the expected pinned identity and unit digest. Define the admitted-authority trust boundary precisely, or carry an admission attestation over the admitted scope. Membership is then established through that admission plus constrained subsequent mutation; a hash copied alongside a row is insufficient. Read lease owner, token, deadline, status, and cancellation live each time; immutable-definition caching cannot replace those checks. Avoid fetching/decoding a header blob that embeds all unit definitions, which would preserve linear per-call costs even after eliminating the work-row scan.

   Use the existing primary key `(run_id, step, unit_key)` for exact equality lookup; avoid adding a redundant index. This proposes bounded row materialization, not constant-time storage access: B-tree lookup still depends on tree depth and data/cache behavior. [PostgreSQL 16 §11.3, Multicolumn Indexes](https://www.postgresql.org/docs/16/indexes-multicolumn.html).

3. **Publish generated children atomically.** Retain the existing `finish_expand` transaction: lock the parent/run; verify current authority; insert the complete deterministic child batch; seal its accepted count/receipt; increment the expected-work count; then commit. Its first-admission collision rejection and replay branch already prevent double counting. Replays must compare the previously accepted commitment, including zero-child batches, and reject conflicting payloads. If future set-based insertion allows skipped rows, compare actual insertions with the expected batch, using `RETURNING`; do not silently accept a partial expansion. All insertion paths must use this protocol.

   PostgreSQL makes a transaction's steps visible together or rolls them all back. `RETURNING` reports successfully inserted/updated rows. [§3.4, Transactions](https://www.postgresql.org/docs/16/tutorial-transactions.html), [INSERT, Description](https://www.postgresql.org/docs/16/sql-insert.html). The batch/seal protocol is an inference applying those guarantees. No cross-database atomicity is implied.

4. **Keep transitions safe under concurrency.** Combine lease checks and the authorized state change in a conditional update or a transaction with the relevant row lock. Do not read authority, release the transaction, then update unconditionally. Use a consistent lock order across fanout and completion. A shared run counter can serialize concurrent fanout transactions briefly; keep worker execution outside it and avoid updating that counter during heartbeats.

   Row locks block conflicting writers until transaction end. [PostgreSQL 16 §13.3.2, Row-Level Locks](https://www.postgresql.org/docs/16/explicit-locking.html#LOCKING-ROWS). This preserves Bookkeeping concurrency; it does not independently repair the separate destination-fencing P1 finding.

5. **Use a consistent snapshot for full reconciliation.** Atomic fanout does not make separate `READ COMMITTED` queries see the same snapshot: reading a header, then children, can straddle another committed fanout. Use one statement or a short read-only `REPEATABLE READ` audit. A completion decision that changes authoritative state needs its own locking/serialization protocol; a consistent historical snapshot alone is insufficient to authorize it. Serializable or repeatable-read writers require whole-transaction retries when their concurrency checks abort. [PostgreSQL 16 §§13.2.1–13.2.3, Transaction Isolation](https://www.postgresql.org/docs/16/transaction-iso.html).

If a restricted function is required for admission/fanout, lock its `search_path` to trusted schemas, revoke default `PUBLIC EXECUTE`, and grant only the intended entry points. Those controls prevent the function from becoming an alternative bypass. [CREATE FUNCTION, Writing SECURITY DEFINER Functions Safely](https://www.postgresql.org/docs/16/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY).

## Qualification before removing existing checks

- Run the exact control path against disposable PostgreSQL 16 with the actual restricted application role. Demonstrate rejected definition updates, deletes, truncation, unauthorized inserts, and attempts to replace/disable guards.
- Exercise two concurrent fanouts, replay after uncertain commit, conflicting replay, zero-child sealing, failure between each fanout statement, cancellation, expired/replaced leases, stale tokens, and final completion racing a valid fanout.
- Verify recovery finds missing/extra definitions, broken parent lineage, wrong sealed digest/count, and wrong global accounting. Protect the audit's snapshot and retain explicit repair through a separate authorized role.
- Measure 100, 1,000, and 10,000 units with identical worker stubs and heartbeat rates. Record SQL calls, rows fetched, JSON bytes decoded, controller CPU, and per-operation/end-to-end latency. Record contention from fanout counters separately from ordinary unit operations. Target bounded ordinary-unit reads and approximately linear total control work; no speedup factor is established yet.
- Run `ANALYZE`, then capture `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` for old and proposed queries. Actual rows/loops and buffer use matter more than planner cost. `ANALYZE` executes statements; run mutation probes in the disposable database and roll back where appropriate. Account for instrumentation overhead and warm-cache effects. [§11.12, Examining Index Usage](https://www.postgresql.org/docs/16/indexes-examine.html), [EXPLAIN, Parameters and Notes](https://www.postgresql.org/docs/16/sql-explain.html), [§14.1.3, Caveats](https://www.postgresql.org/docs/16/using-explain.html#USING-EXPLAIN-CAVEATS).

The next implementation task is to translate the mapped fields/write paths
into an exact migration and qualify every direct function call. Removing scans
before that restricted-role qualification would reduce current detection
coverage.

## Verification performed for this research

On the current unmodified runtime, disposable PostgreSQL 16 acceptance passed:
12 tests covering generated-parent/child atomicity, stale expansion, unsealed
expansion, dependency corruption, resume drift/receipt damage, restricted
five-table migrations and compaction. Command:

```bash
LC_ALL=C LANG=C PG16_SERVER=pgserver uv run --no-sync --with pgserver pytest -q \
  tests/integration/test_generated_bookkeeping_postgres.py \
  tests/integration/test_configured_bookkeeping_postgres.py \
  -k 'generated_children or stale_expansion or unsealed_expansion or resume_blocks_drift or resume_rechecks_full_dependency or dependency_corruption or compaction_retains or exact_five_tables'
```

The research worktree used the already-installed project environment; a fresh
checkout must first install its normal test/SQLAlchemy dependencies. These
tests establish the baseline invariants the future fix must retain, not proof
that the proposed fast path works. Local document links and measurement
arithmetic were checked; the overlap guard reported no overlap for the three
research files. No runtime implementation, source activation or AWS changes
were made.
