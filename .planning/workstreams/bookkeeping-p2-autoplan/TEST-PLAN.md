# Bookkeeping P2 qualification plan

Status: proposed acceptance, not implementation or deployment evidence.
Approved baseline: `bebebcb2`; original review baseline: `db2e7ce3`; research measurements: `f9e89470`. Shipping synchronization merged `67cedee4`; no intervening Bookkeeping runtime changes. Runtime functions/migrations remain unchanged by this review.
Framework: pytest, real PostgreSQL 16 (`tests/support/pg16.py`), restricted database
logins, separate installed processes and pinned local artifact/Company fixtures.
Existing tests are useful scaffolding; passing them does not qualify new branches.
No LLM/prompt runtime changes: no model eval suite applies.

## Execution and branch diagram

```text
rules CLI [new submission | resume existing]
  new -> [legacy default | explicitly qualified per-unit]
    -> submitter URL [missing -> refuse | present -> role validation]
    -> frozen Rules/manifest [invalid -> block | exact -> compile]
    -> restricted SQL submit [unauthorized -> reject | admit immutable scope]
  resume -> stored format [legacy -> full audit | per-unit -> full recovery audit]

ordinary control CLI / installed worker process
  -> format dispatch [legacy | per-unit | explicit force-full]
  -> audit/context [missing/corrupt relevant -> block ROOT | exact -> continue]
  -> selected item [absent | original | sealed generated]
  -> dependencies [none | chain | fan-in/shared ancestor | corrupt/unfinished]
  -> live authority [wrong profile | expired/taken over | authorized]
  -> claim / renew / report / verification claim / admit
    -> completion [ordinary | resource checkpoint | expansion]
    -> expansion [0..128 valid | >128 | fabricated/raw-byte mismatch]
       -> lock, children, parent seal, counts, checkpoint, outbox ALL ATOMIC
       -> sealed replay [exact compare-only | missing/conflict -> reject]

journal batch -> context once -> exact event once per row
  -> append [new | duplicate | failure]
  -> read-back [exact -> acknowledge | mismatch/failure -> pending + block/error]

finalize -> bounded delivery -> cheap readiness
  [work/report/expansion/delivery pending -> partial, no terminal audit]
  [ready -> one coherent REPEATABLE READ snapshot]
      audit [all verified+sealed+exact | not closed -> false checks]
      locked record_checks [current state/count/seals/outbox hold -> COMPLETE]
                           [changed/pending/failed -> not complete]

operator -> status/mode/count inventory -> diagnose -> restore exact evidence
  -> checks -> resume -> later finalize
  -> optimization rollback [force-full on matching code]
  -> old binary rollback [tagged resumable count 0 + compatibility proof | refuse]
owner retention -> compaction [complete/old enough -> archive | ordinary login -> deny]
```

`[→E2E]` below means actual PostgreSQL/CLI/process integration, not mocked SQL.
Pure codec/template behavior also has unit/property tests. Preserve all current CI
gates and installed-wheel dependency isolation; never turn missing PostgreSQL into
an acceptance skip. No additional AWS resources are needed for local qualification.

## Coverage grid: every proposed branch

Abbreviations: C = `tests/integration/test_configured_bookkeeping_postgres.py`;
G = `tests/integration/test_generated_bookkeeping_postgres.py`;
W = `tests/integration/test_bookkeeping_wheel_postgres.py`;
U = `tests/unit/test_configured_bookkeeping_contract.py`;
A = `tests/architecture/test_bookkeeping_control_only.py`.
Every “ADD” is mandatory future work; no proposed test is reported as existing.

| ID | Branch / realistic failure | Existing evidence inspected | Required new coverage / handling |
|---|---|---|---|
| Q01 | Initial trusted submission vs forged tag/context through legacy function | C `test_pipeline_rules_and_approval_authority`, database runtime grant list | ADD [→E2E] separate submitter, unauthorized worker/verifier direct calls, missing URL, malformed tag/context, initial idempotent replay/conflict; fail closed |
| Q02 | Principal disjointness, owner/group membership and SET ROLE | C `test_only_a_profiles_roles_report_and_verify_and_never_the_same_login`; 006 issuer uses session_user | ADD [→E2E] inherited memberships, SET ROLE, grant order, reciprocal profile granting, schema/table write privileges and PUBLIC execution; reject either grant direction |
| Q03 | New migration on populated states and checksum reuse | C `test_exact_five_tables_restricted_runtime_and_migrations`; G protocol/issuer migration tests | ADD [→E2E] all old states, zero-work/compacted stores, unchanged old checksums, exactly five tables, new migration packaged; fail on untracked/checksum drift |
| Q04 | Immutable definition, receipt/checks/seal/outbox versus permitted mutable fields | Current frozen audit compares stored rows | ADD [→E2E] each field UPDATE/INSERT/DELETE/TRUNCATE via every executable route, no caller-set bypass flag; attempts, leases, pins and delivered_at still transition |
| Q05 | Unclassified future function bypasses guards | database.py explicit function grants | ADD catalog acceptance inventory including wrappers/internal renamed functions, record_checks/resume_run/start_run, SECURITY DEFINER search_path and inherited execute privileges; tagged completion/recovery need control principal, unknown writer fails qualification |
| Q06 | Generated bytes authenticate exact reported candidate | G `test_generated_children_and_parent_intent_commit_together` covers replay shape | ADD [→E2E] authorized verifier passes arbitrary but syntactically valid children, alternate raw bytes, wrong parent/digest; reject before ANY child/count/outbox changes |
| Q07 | Generated generic compiler versus Python contract | config.py simple-field templates; generated_worklist bound 128 | ADD unit/property + PostgreSQL differential cases: escaped braces, repeated/missing fields, resource sorting/dedup, ordinals, malformed input/output/cursor, no source-policy SQL |
| Q08 | Codec edge cases hide semantic mismatch | Existing artifacts.py verifies raw SHA-256 then strict json_value | ADD raw UTF-8/non-ASCII/whitespace/key order, invalid UTF-8, duplicate keys, NaN/Infinity, NUL, numeric integer-vs-bool/float; explicitly qualify supported new-format subset and reject unsupported inputs |
| Q09 | Expansion cardinality and identity collisions | G generated happy path/stale expansion | ADD 0,1,128 valid;129 rejected; duplicate keys/ordinals, parent-child collisions, recursive generation and ordinal overflow; whole transaction rolls back |
| Q10 | First expansion atomicity and lease expiry | G `test_stale_expansion_cannot_insert_children`; C commit-expiry test | ADD [→E2E] fault after child insertion/before parent/count/outbox, expired fence at commit, verifier takeover; no partial durable scope; exact frozen checkpoint arguments and wrong completion routes refuse; tagged combined markers rejected |
| Q11 | Sealed replay inserts missing children / completes unsealed parent | G `test_unsealed_expansion_blocks_root` currently permits ordinary finish then detects | ADD [→E2E] ordinary finish rejected for expansion, exact replay compare-only, owner-damaged missing child rejects without repair, stale replay/conflicting evidence blocked |
| Q12 | Format dispatch/new-only selection/force-full | Current envelope protocol 1 | ADD legacy/per-unit/unrecognized tag, --control-validation with resume rejection, missing submitter configuration, force flag valid/invalid and no silent downgrade; public protocol/binding/effect_key and upstream ordinal unchanged; ordinal0 always redoes; generated base>0 first child draw50 confirms/draw4 redoes, absolute ordinals preserved; upstream first/random redo regression suite retained |
| Q13 | Compact context/selected unit validity | engine._row uses primary key | ADD [→E2E] unknown run/unit, null/corrupt context/ref/descriptor, parent lineage missing, selected relevant artifact missing/mismatch; block root, not merely row |
| Q14 | Delayed unrelated integrity detection | Current _frozen audits all evidence each operation | ADD paired cases: corrupt/missing original global manifest or unrelated expansion allows unaffected ordinary work, but checks/resume/finalize detect and block; explicit policy test |
| Q15 | Memo hides mutable lease/status changes | C renewal/takeover/profile runtime tests | ADD command-local exact immutable identity memo only, reset across calls, concurrent lease expiry/takeover and report identity change remain visible; stale completion refuses |
| Q16 | Dependency DAG repeats shared ancestors/exhausts recursion | C out-of-order, corruption, chain and composed-slot tests | ADD chain/deep chain/fan-in/diamond/repeated slots; compare result/byte integrity, memo hits and reads; invalid cycles/depth fail clearly or use bounded iterative walk |
| Q17 | Batch expansion changes scope after initial context | Existing tasks/envelope each re-audit | ADD concurrent first expansion while phase-A batch is running; scope revalidation or fixed immutable context discipline must include newly admitted rows correctly |
| Q18 | Journal context/event reuse loses verification | C `test_full_completion_and_duplicate_delivery`, `test_outbox_atomic_with_progress_and_lost_delivery_ack`, `test_journal_failure_and_recovery` | ADD [→E2E] one expected event reused, upstream sample proof references authenticated and retained, worker-side exact claim/fallback-why assertions, no control sample schema or redraw, forged payload/lineage, append-success/readback-failure and lost-ack; no acknowledgement before exact readback |
| Q19 | Partial finalize still audits every bounded delivery page | Baseline cli finalize delivers then always finalize | ADD >100 events, pending work/report/seal/outbox cases; readiness skips terminal audit and preserves exit3/state; final ready call audits once |
| Q20 | Coherent final audit accidentally opens fresh connections | _frozen/_receipt/check currently open independent connections | ADD [→E2E] barrier-controlled concurrent expansion/completion and shared snapshot across run/work/dependency/status reads; no mixed-snapshot true checks; one exact immutable-report validator checks full binding/checks/proofs/frozen output for retained direct-SQL evidence |
| Q21 | All-verified audited scope changes before locked record_checks | 004 record_checks locks run then checks counts/states/seals/outbox | ADD two finalizers, late expansion, blocked-state race, receipt mutation/replay, pending delivery, direct SQL calls and zero-work run; blocked remains sticky, exact final-check names and trusted control principal required; stale recovery compare-and-swap refuses a newer blocking generation; same-run release/completion and concurrent first-report lock order tested; either prove closure or keep fast mode disabled pending revision-counter amendment |
| Q22 | Terminal integrity exception fails to block root | Current _frozen blocks for certain exception types | ADD every audit/unit helper relevant failure reaches one root-block path; read-only snapshot rolled back before separate blocking transaction; no silent success |
| Q23 | Error output loses cause or leaks credentials | workers/control.py keeps last stderr line | ADD U plus process capture for missing grant, hash mismatch vs read outage, partial result; last line has problem/cause/next action/docs and no DSNs |
| Q24 | Client timeout/lost response repeats a committed mutation | workers/control.py subprocess timeout300 | ADD [→E2E] stalled call and commit-before-response loss, concise outcome-unknown error, inspect/reconcile same identity, lease expiry protection; record failed trial, no blind new-attempt retry |
| Q25 | Rollback inventory misses page >100 or blocked runs | runs defaults limit100 | ADD authoritative mode/state counts with >100 runs, running/waiting/blocked included, zero tagged resumable prerequisite and installed old/new executable matrix |
| Q26 | Forward migration incompatible with old binary / packaging | W installed isolated control migration/run tests | ADD [→E2E] retained old binary operates legacy runs with migrated schema, active tag refuses old-code rollback, staged new executable actually owns migration files and grant command; old owner migrator is unsupported, supported admin version preflight and retained new admin tool tested; installed ordinary read/combine/reduction-through-combine/streamed fallback/always-redo profile cases and sample evidence |
| Q27 | Compaction bypass contradicts immutability | C `test_compaction_retains_receipts_checkpoints_and_tokens` | ADD owner-only audited retained-summary compaction after completion/retention; ordinary deletion/truncation denied; old compacted runs stay nonresumable |
| Q28 | Claimed speedup ignores database rows visited / startup / dependencies | Research returned row counts exclude process startup/journal | ADD full-process harness N100/1000/10000×5, actual complete outcomes and confirm/redo/fallback branch counts under identical upstream policy/build, startup/wall/RSS/query/artifact metrics, EXPLAIN ANALYZE BUFFERS, fixed closures, sparse candidate/large completed prefix, cross-run backlog, increasing historical lease population, expired/contended leases and lock-upgrade contention; gate all promised thresholds |

No planned silent integrity failure is accepted. Proposed critical behavior gaps
Q01–Q11/Q20–Q22 block per-unit enablement until real SQL/concurrency proof passes;
that is an implementation acceptance gate, not existing qualification.

## Commands and release evidence

Prepared local baseline scaffolding (already available):

```bash
LC_ALL=C LANG=C PG16_SERVER=pgserver uv run --with pgserver pytest -q \
  tests/integration/test_configured_bookkeeping_postgres.py \
  tests/integration/test_generated_bookkeeping_postgres.py \
  tests/integration/test_bookkeeping_wheel_postgres.py \
  tests/unit/test_configured_bookkeeping_contract.py \
  tests/architecture/test_bookkeeping_control_only.py
```

This broad command is a future implementation check, not an additional full suite
run during this review. First run narrowly selected new branch tests during delivery;
then the complete affected gates before claiming qualification. CI keeps its actual
PostgreSQL/container route. Local pgserver uses C locale; missing tooling is a visible
failure. Full benchmark exact command and output schema are in PLAN.md.

Required evidence: commit/migration/checksum/role grants, fixture hashes, executable
versions, PostgreSQL 16 version, mode and force setting, raw repeated measurements,
query plans/buffer visits, actual completion/readback results, timeout/fault counts
and upgrade/rollback transcript with redacted credentials. Median speed alone does
not justify dropping a failing role, integrity, race, renewal or RSS gate.

## Coordinated MDM scope (operator, 2026-10-14)

Preserve Claude Ticket74's Merge Stage size-refusal removal (merged as PR960) in
the matched future worker/MDM installed proof. No new closure, request/proposal or
projection cap comes from P2. Retain existing input batching and current Bookkeeping
protocol bounds under the operator's explicit MDM-only scope answer. Test sample
sizes and CLI page limits are not total-work ceilings. Local PG16 is correctness
qualification; hosted-capacity evidence remains a separate measured requirement.
Claude's reported12 tests are ticket evidence, not tests rerun by this review.
