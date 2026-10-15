<!-- /autoplan restore point: <local-gstack-project-artifacts>/codex-bookkeeping-p2-autoplan-20261013-autoplan-restore-20261013-201216.md -->
# Bookkeeping P2: bounded validation of admitted work

Status: **APPROVED AS-IS** — operator selected A at 2026-10-14 07:40 ET.
Approval covers this reviewed plan; implementation and deployment qualification
remain separate work.
Approved source baseline: main `bebebcb2` after verified rebase. Original review
baseline: `db2e7ce3`; research measurements used `f9e89470`, whose Bookkeeping
runtime and acceptance fixtures are identical to `db2e7ce3`. Research was
`042e2910`, now rebased as
`af713546`. Original motivating code quotations remain explicitly tied to
`db2e7ce3`; upstream ordinal insertion shifts later engine line numbers by two.
Shipping synchronization: merged main `67cedee4` at 2026-10-14 21:07 ET. The
17 intervening commits change no Bookkeeping runtime code. Ticket74 is now merged
as PR960 (`9da59e01`); the coordination snapshot below remains historical evidence.
The approved design and MDM-only scope ruling are unchanged.
Research: [baseline and primary sources](../../../docs/research/bookkeeping-per-unit-validation-2026-10-13.md).
Measurements: [raw observations](../bookkeeping-scan-research/MEASUREMENTS.json).

## Outcome and acceptance contract

For the existing SEC Company and generic artifact fixture targets, routine control
work must depend on the selected unit, its leased resources and its prerequisite
closure, rather than unrelated units in the run. Retain approved Rules, immutable
work, independent verification, atomic generated children, lease fencing, durable
journal intent and explicit recovery. Keep the five existing control tables.

The baseline completed one unit with one renewal at N=10/100/1,000. It returned
100/1,000/10,000 work rows through ten whole-run scans and reread Rules and the
input manifest ten times. Observed local durations were 0.1792/0.2605/1.7254 seconds;
these single samples excluded subprocess startup and journal delivery. They are
problem evidence, not a production SLA or a measured speedup.

Acceptance gates, proposed for this bounded change:

- Instrument real commands and installed worker/verifier processes at N=100,
  1,000 and 10,000, with five repeated trials and fixed inputs/heartbeat rates.
- For qualified per-unit runs, ordinary claim/renew/report/verify/admit operations
  and per-event journal preparation perform **zero** whole-worklist reconstructions
  and **zero** whole-run work-row SELECTs. Unrelated input-manifest bytes are not
  fetched/decoded in these operations. Dependencies and a bounded expansion are
  measured separately, not called constant-time.
- With a fixed prerequisite closure, ordinary operation query/row/byte counts
  do not grow with unrelated N. Exact unit lookup uses the existing primary key.
- Real complete-run control wall time improves at least 20% over the phase-A
  command-reuse baseline at N=1,000 and 10,000. N=100 median wall time and peak RSS
  regress no more than 10%. Thresholds are proposed release gates, not results.
- Renewal p99 completes within one quarter of the lease duration and within one
  heartbeat interval on the representative local full-process workload. If setup
  or a lease setting makes that unattainable, report the failed gate; do not claim
  deployment qualification or silently change policy.
- Backlog drainage through the existing `bookkeeping finalize --limit 100`
  performs terminal evidence reconciliation only when readiness allows completion,
  rather than after every delivery batch. All final checks remain authoritative.
- Preserve normal CLI commands, task envelopes, status/exit-code meanings and
  worker/verifier role separation. The P1 destination fence and incomplete runtime
  fingerprint remain separate findings, not repaired by this P2 change.

## Chosen implementation and trust boundary

Implement three sequential deliveries: A, remove redundant validation within a
command; B, protect admitted definitions and prove origin; C, enable per-unit
validation and qualify complete paths. A is useful independently, but does not
close P2. Do not silently stop after A. Every delivery remains on its dedicated
runtime branch/worktree and passes the overlap guard before commit/push.

### A. Share a validation context within each command

Run the existing whole audit once at entry to a public command. Pass its immutable
configuration/reference context through `claim`, `envelope`, `_same_work`,
`heartbeat`, `_context` and `journal_event` instead of recursively re-running it.
Build one expected journal event per row and reuse it for append and verification.
Do not cache run state, leases, candidates, status or delivery acknowledgements.
If generated scope changes while a batch command is operating, revalidate that
scope; a static context must not conceal newly admitted work.

This should reduce the measured ten scans to roughly five public-command audits,
and a delivery batch from `1 + 2D` scans to one command audit, subject to scope
changes. Those are projections to verify. Cross-command calls still cost O(N).

### B. Protect the exact admitted definition set

Existing direct runtime functions accept caller-supplied definitions. They are
**not** a sufficient trusted admission boundary. Ordinary worker/verifier logins
must not be able to forge a fast-mode run or a generated definition through SQL.

Initial admission uses a separately authorized submitter principal. It authenticates
Rules/export, acquisition authority and original input-manifest bytes, compiles
with existing `validate`/`worklist`, and calls a restricted sealed-admission entry
point. Only that principal may admit the new validation format. Worker credentials
cannot call that entry point, supply a fast-mode tag through the legacy function,
or upgrade an existing run. Provisioning uses a local PostgreSQL role/grant contract;
this plan provisions no AWS secrets or runtime infrastructure.

Store an immutable internal `control_validation` format tag and a compact normalized
control context tied to the frozen Rules/input references and original worklist
hash. The public task `protocol` remains 1; it identifies the worker-message ABI,
not the validation implementation. New-mode tags are set only at admitted creation.
Do not backfill or convert existing runs. Existing untagged runs drain on whole-run
validation; inventory them and retire compatibility only when none are resumable.

Guard the definition fields on `pipeline_run` and `work_item`: submission, submission
hash, normalized context/tag, run/step/key/ordinal/resources/unit and generated
lineage. Once accepted, freeze completion receipts/checks and expansion seals.
Mutable attempts, status, leases, runtime pins and acknowledgements retain their
existing restricted transitions. Permit owner-only audited compaction after complete
runs and retention; deny ordinary deletion, truncation and definition replacement.

Generated scope requires an independently verifiable origin, not a row hash stored
beside the row. Extend the existing `finish_expand` path to authenticate the exact
candidate expansion bytes against the reported candidate receipt and frozen parent,
and enforce that each compiled child matches that bounded expansion and frozen
key/lease/ordinal rules. The maximum remains 128 children. The chosen storage checks
are generic control invariants, not source-specific policy. The direct SQL path must
reject fabricated child lists even under a verifier login. Its raw-byte digest
protocol must be explicit and match artifact SHA-256, including UTF-8/JSON edge cases.
If those checks cannot be expressed and qualified without duplicating uncontrolled
policy, keep the full audit path; fast-mode enablement remains blocked pending an
admission design amendment. A trusted principal or matching self-generated hashes
alone must never be reported as independent proof of child origin.

Retain the atomic parent/run lock, child insertion, parent receipt/seal, expected
count update, checkpoint and outbox intent. A sealed-parent replay only compares
existing children/seal; it cannot insert a missing child. Ordinary `finish` cannot
complete an expansion parent without its seal. Missing or conflicting replay is an
integrity error, never a repair opportunity for the worker.

Use a new checksummed numbered migration and preserve existing installed migration
files. Audit every granted mutation function and both public/owner-only entry points;
add a catalog/role acceptance check that unclassified future mutation routes fail.
No client-set session variable is accepted as proof of a trusted mutation path.

### C. Separate ordinary validation from full reconciliation

Keep `_audit_run` for admission, explicit checks, resume and ready-to-complete final
reconciliation. Introduce private `_run_context` and `_unit_context` responsibilities
inside the existing engine. Select only compact needed header fields; avoid
`SELECT *` returning a newly enlarged submission/manifest blob. No full unit map is
embedded in the hot context. One selected row comes from `(run_id, step, unit_key)`.

Every action still checks the relevant frozen descriptor, exact envelope binding,
required profile, candidate/report identity and **live** lease/status under existing
transaction fences. Generated units additionally verify their sealed bounded parent
origin. A relevant missing/corrupt artifact or descriptor mismatch blocks the root
run, not just that unit. No discovery, source re-fetch or new Rules version repairs
original evidence automatically.

Retain the prerequisite closure, including exact bytes and admitted verifier reports.
Use a command/audit-local memo of authenticated immutable evidence keyed by exact
receipt identity to avoid repeating shared ancestors; reset it at every command.
Do not cache mutable control state or persist a second control store. Complexity is
in N, dependency edges E and evidence bytes B, not a blanket linear-in-N guarantee.
Wide fan-in and repeated separate commands can still be expensive and must be shown.

Journal delivery receives one validated context for the batch, reads the unit/parent
needed for each event and produces one expected envelope. Missing lineage/evidence
blocks delivery and the root. Acknowledgement remains after append and read-back.

Finalization first performs cheap live readiness checks. While work or delivery is
pending, return existing partial status/exit semantics without a whole evidence
scan. Once ready, take one coherent read-only audit snapshot, reverify the scope and
retained completion evidence, and call the existing locked `record_checks` gate.
The audit must itself observe all work verified and all expansions sealed; otherwise
pass false completion checks and retry only on a later operator call. The SQL gate
still checks current state/count/seals/pending delivery under the run lock. With
immutable admitted definitions and sealed-parent replay, an all-verified audited
scope cannot acquire new ordinary children. Prove that statement with concurrency
and direct-call tests before choosing to omit a revision counter. Do not add a new
finalizing lifecycle state by default. If the proof fails, amend the plan and rerun
engineering review before enabling fast mode.

### Integrity detection policy, approved as-is

Ordinary calls authenticate the selected unit and relevant evidence. Whole original
input manifests, unrelated expansion artifacts and unrelated privileged row
corruption are checked at admission, explicit checks, resume and terminal audit.
A relevant failure blocks the whole run immediately when detected. An unrelated
failure may permit other work/delivery until a full audit detects it. This includes
missing/unreadable artifact-store objects, not only administrator database changes.
No timer service or periodic auditor is introduced. Operators may call existing
`bookkeeping checks` for a deliberate full audit during long runs. The operator approved this policy
with option A at 2026-10-14 07:40 ET; the explicit full-audit tightening override remains
part of the accepted plan.

## Operator contract and safe enablement

These are proposed additions, not commands available in the baseline. Use
`BOOKKEEPING_SUBMITTER_DATABASE_URL` for tagged-run initial `rules run` submission,
explicit recovery resume and ready terminal reconciliation through `finalize`/
`record_checks`, consistently with the authority amendment below. Bounded outbox
delivery before readiness continues under its existing runtime authority; the
terminal full audit and completion transition require control credentials.
Worker/verifier processes continue using their own `BOOKKEEPING_CLEAN_DATABASE_URL`.
Missing submitter configuration fails closed rather than falling back to the worker
URL for new-format submission. Add owner-only `bookkeeping grant-submitter --login
<login>` to the existing CLI/database modules. Its grant qualification rejects
superuser/owner/schema-write privileges and any worker/verifier profile membership,
including inherited/settable membership; profile granting must reject the converse.
Qualify the three principals through a focused PostgreSQL role test, rather than
expanding the unrelated doctor command. No DSN or secret value appears in errors.

Add a tightening-only `BOOKKEEPING_FORCE_FULL_AUDIT=1` setting that selects full
validation for every ordinary command on tagged runs. It must retain per-unit
origin/immutability protections, never suppress a failed check, never rewrite the
stored format and never silently switch after an integrity error. Publish both
`control_validation` and `effective_validation` in existing runs/status output;
add `runs --validation legacy|per-unit` for bounded inventory. Ordinary default
per-unit behavior is enabled only for newly admitted qualified-format runs; the
submitter must explicitly request that format until qualification passes. An unset
setting on an old run still selects the full audit. Canonical documentation calls
this **per-unit validation**; initial scope creation is **run submission**, while
existing `admit` continues meaning verifier-report admission.

Upgrade order: (0) stage the new release in a separate local uv environment,
retain the old executable, and use that new executable with owner credentials
for the migration/grants; (1) quiesce new submissions and inventory resumable legacy runs;
(2) install the new forward-only checksummed migration and grant the separate
submitter; (3) install the matching engine/CLI, retaining full auditing and legacy
submission compatibility; (4) pass restricted-role, old-code/new-schema and all
origin/concurrency tests; (5) explicitly enable qualified submissions. Existing
untagged runs drain unchanged. Reverting optimization means forcing full auditing
on the matching new engine. Returning to old code is allowed only after tagged
runs are drained and old-code/new-schema tests pass; restoring an older binary on
an active tagged run is unsupported. Never drop guards to regain compatibility.

Document command outcomes: `status` exit 0 means the query succeeded; `finalize`
and `resume` exit 3 mean the run is not complete, including blocked/partial states;
control integrity exceptions remain nonzero failures. Existing `rules run
--resume-run-id` is distinct: it returns 3 for waiting/blocked and 0 for running
or complete. Preserve that contract, document an entry-point/state matrix, and
inspect JSON state rather than equating exit 0 with completion. New errors put problem,
cause and safe next action in the final stderr line seen by worker wrappers. A
storage read failure is distinguished from an authenticated digest mismatch,
while both retain fail-closed root blocking. Recovery requires restoring the exact
original bytes/access, then explicit checks/resume; no automatic source re-fetch.

Qualification harness: planned `scripts/benchmarks/benchmark_bookkeeping_control.py`.
The proposed command is `uv run python scripts/benchmarks/benchmark_bookkeeping_control.py
--sizes 100,1000,10000 --trials 5 --lease-seconds 120 --heartbeat-seconds 10
--output .scratch/bookkeeping-p2/full-path.json`. It launches actual control and
worker/verifier processes, separates cold import/startup from command execution,
records command/phase/run/mode/N/dependency-edges/evidence-bytes/query-count/rows-read/
artifact-read-bytes/wall-seconds/peak-RSS/renewal-percentiles, and checks every
completion/evidence outcome. Bound subprocess timeouts and terminate benchmark
fixtures recoverably. The heartbeat/lease gates therefore use 10/120 seconds.
Do not overwrite the original research measurements with proposed or new results.

Documentation changes are bounded to `docs/configured-capture.md`,
`skills/bookkeeping/RUN.md`, `skills/bookkeeping/RECOVERY.md`, and the README's
control setup link/variable list. The existing CI PostgreSQL and architecture gates
remain intact. Broader repository install, community or AWS secret automation is
deferred.

Exact proposed submission selector: `rules run --control-validation legacy|per-unit`,
default legacy during qualification. Reject the selector with `--resume-run-id`;
resume reads the immutable stored format and uses the control login. New per-unit
submission requires the submitter URL, existing Rules URL and manifest root. Add
an authoritative `resumable_by_validation` count to `runs` output independent of
its row limit: running/waiting/blocked all count. Require zero resumable tagged runs
before old-code rollback; test more than 100 runs and do not infer exhaustion from
a bounded page. Public task envelopes and report identity stay byte-compatible.

Timeout qualification includes a stalled control subprocess and a lost response
following a committed transition. The baseline wrapper has a 300-second timeout;
the benchmark must record it and compare identical policies across modes, with
120-second lease expiry and 10-second heartbeat. For fault trials, an external
10-second harness deadline may terminate the client; it does not prove rollback
of a database transaction. Normalize the wrapper's TimeoutExpired into a concise
“outcome unknown; inspect status/checks and reconcile original attempt” error;
never immediately repeat a possibly committed mutation with a new identity. Lease
expiry and destination fencing remain authoritative. Ordinary renewal p99 gates
remain 10 seconds; timeout trials are separately reported failures, not trimmed
out of successful timing samples. No blanket claim that the current 300-second
control timeout is bounded by every configured lease is made.

### Engineering authority and snapshot amendments

Use the same separately authorized **control submitter** principal for new-format
initial submission, explicit resume after a full recovery audit, and ready terminal
reconciliation. It remains disjoint from worker/verifier logins; no fourth login is
introduced. On tagged runs, `record_checks` and `resume_run` reject ordinary worker/
verifier sessions, even if a legacy shared group still has EXECUTE. Only the
control principal can publish full audit results or clear a blocked state. Record
checks require the exact frozen configured final-check names, not arbitrary
`{"x":true}`; current structural counts/closed-seal/outbox conditions remain.
Blocking is sticky: false or stale checks never clear it, and a failed audit calls
block_run instead of record_checks. Document the existing finalize/resume commands
with control credentials. Untagged drain behavior stays compatible; no grant is
silently broadened for a worker to make the new command succeed.

Store `control_validation` in a new immutable column on pipeline_run, constrained
to NULL or `per-unit-v1`, separate from the original submission/message protocol.
Keep the legacy ten-argument finish_expand signature for untagged runs; tagged
runs are rejected through that signature before any write. Qualify a separate
raw-byte overload for tagged expansion as specified in the engineering section.
On every generated-unit use, additionally recompile its authenticated bounded
parent expansion with the existing Python compiler and compare the selected child
exactly, memoized within that command. This keeps the source of truth singular at
execution time and detects SQL parity drift. The SQL generic parity boundary remains
an explicit design choice: it refuses arbitrary first-seal children under a verifier
login, rather than permitting their insertion and relying only on later detection.
No SQL-specific feed policy is introduced. If parity cannot be qualified, do not
activate the new format or describe the boundary as implemented.

A coherent terminal audit uses one repeatable-read read-only database connection
through all run/work/dependency/status readers. Artifact bytes are independently
hash-verified outside PostgreSQL's MVCC snapshot; no cross-store snapshot or
atomicity claim is made. Close the read-only transaction before separately blocking
on a failure. Current-state checks under the run lock refuse a concurrently blocked
run. The compact context freezes journal source/feed, so event preparation avoids
re-fetching the whole Rules export for each event.

Definition guards freeze work_item completion receipts/checks and seals, not the
mutable pipeline_run audit-check results. Owner-only compaction may delete work
rows only after a complete retained run is marked compacted by the same atomic
operation; authorization comes from role/state invariants, never a caller-set GUC.
Audit actual inherited/settable function privileges for all pg_proc entries,
including owner-only renamed helpers, not just the explicit grant list.

### Final engineering route, recovery and cost amendments

Tagged completion dispatch is defined by the immutable unit cursor in SQL, not
caller choice. Ordinary finish refuses expansion or resource-checkpoint units;
finish_resource binds resource/revision/position exactly to the frozen cursor.
Reject combined expansion+checkpoint markers at tagged submission until a single
qualified combined transaction exists. Retain legacy behavior for untagged drain.
The seal invariant is deferred to transaction commit, and internal completion
helpers are owner-only; a public wrong route cannot supply a trusted bypass flag.

Use one shared immutable-report validator in admission, selected dependency use,
journal preparation and full audit. It checks exact report structure, full run/
step/key/attempt/effect/candidate binding, frozen output intent, required checks,
all proof references and verifier runtime binding. Derive the effect key from the
original frozen descriptor, not a dependency-resolved copy. Stored checks alone
never authenticate an arbitrary direct SQL receipt. New completion additionally
checks live lease/profile/reporter separation; historical revalidation uses retained
immutable attempt/evidence rather than demanding an expired old lease be current.

Add `blocking_generation` to the existing run row, incremented on every block,
including repeated blocked-to-blocked reports. Explicit recovery audits read that
generation in their coherent snapshot; the trusted resume overload takes the
expected generation and atomically compares it under the run lock before clearing
the block. A newer block refuses resume and requires a fresh audit. The old resume
signature rejects tagged runs; untagged compatibility is retained. This small
recovery compare-and-swap is distinct from the optional worklist revision counter:
closed immutable scope does not protect against a newer integrity observation.

Standardize control lock order: acquire the needed run lock first, then selected
work rows, then sorted lease resources; never acquire a stronger run lock after
holding work/lease locks. First-report runtime pinning takes its needed UPDATE lock
at entry instead of upgrading concurrent SHARE locks. Modify affected function
bodies in the new migration, not installed files. Qualify same-run release versus
completion and simultaneous first reports with barrier-controlled transactions,
deadlock/rollback outcomes and bounded retry rules; measure the stronger-lock cost.
No artifact-store/network read holds an ordinary mutation transaction open.

Measure renewal/completion/candidate lease queries against increasing historical
resource populations, since lease tokens survive compaction. Prefer exact frozen
resource keys where that preserves exact-set semantics, otherwise qualify a narrow
(run_id, attempt) lease index. EXPLAIN/buffers must cover this alongside worker/
verifier candidate mixes, per-run outbox and readiness queries. All later migration
and grant reconciliation uses the matching new administrative executable, even
when legacy runtime code is rolled back. An old migrator is an unsupported owner
operation; test its grant damage and guard the supported administrative workflow
with an installed-schema/version preflight. Keep the new admin environment.

The N10,000×five full-process complete-run benchmark can take hours. Start with a
bounded N100 single trial, record elapsed time and forecast the larger workload
before running it. Add harness `--max-wall-seconds` and durable per-trial checkpoints;
timeout/incomplete trials remain failed/incomplete, never qualification. Report
elapsed time for every step over ten minutes. Do not relax the five-trial gates
because an implementation run is inconvenient or incomplete.

### Current upstream verifier compatibility

Preserve the main #958 task-envelope `ordinal` exactly; the context/selected row
must not reconstruct the earlier envelope shape. Existing _same_work compares
all frozen envelope fields, including this additive field, and remains authoritative.
Current source.read/source.combine verification confirms the declared output and
fully redoes ordinal0 plus a random5% selected when verification runs. Its sample
decision is an immutable proof beside the report; streamed extracts and profiles
without confirm continue full redo/readback. This operator-approved upstream policy
is unchanged by P2. Full Bookkeeping audits authenticate retained report/proof
references; they never call domain workers or force all units to redo their work.
Preserve proof arrays/sample records in the shared retained-report validator.

Compare phaseA/per-unit full-process trials with the **same** upstream verifier
policy and runtime build. Deterministic draw fixtures are allowed for tests, not
production policy. Qualification includes ordinal0, generated ordinal offsets,
confirm versus redo/fallback and immutable sample-proof binding. The upstream
`tests/engine/test_check_confirms.py` regression suite is baseline evidence; new
P2 authority/context/SQL acceptance remains unimplemented. Current Codex capture
PRs933/937/938 are merged; preserve their configured transport, completeness-before-
effect and Journal evidence. No live SEC/source activation is implied by the sync.

Upstream delta acceptance is explicit: a generated batch at nonzero ordinal_base
preserves its absolute stored ordinals. Its first child with draw50 follows the
existing confirm path, while draw4 redoes; absolute ordinal0 always redoes. Do not
reset generated ordinal offsets to force a different sampling result. The “first
unit” wording versus ordinal==0 rule is a preexisting upstream ambiguity, separately
captured for policy clarification, not a P2 regression or an automatic policy change.

Worker-side tests assert full sample-decision shape and exact run/step/key/attempt
claim binding, with optional fallback `why`; they retain arbitrary module proofs
plus the existing decision reference. Control tests authenticate and retain every
proof reference across admission/dependency/journal/full audit, reject missing or
hash-corrupted proof bytes, and never redraw. Proof contents remain opaque business
evidence to Bookkeeping; no worker import or sample-policy schema enforcement is
added to control. Installed compatibility enumerates ordinary read, combine,
reduction through source.combine, streamed fallback and profiles without confirm,
including confirm/sampled-redo branches and new-control retained evidence. Harness
output records actual confirm/redo/fallback counts alongside unchanged verifier
policy/build so random draw mixes cannot be mistaken for a control speedup.

### Operator-confirmed MDM limit-removal scope

Operator, 2026-10-14: “Follow Claude’s current MDM scope for now” after clarification
that Ticket74 removes Merge Stage size refusals but does not change Bookkeeping's
128-child expansion or control-document byte caps. This is explicit scope, not an
inferred permission to redesign the expansion protocol. Retain its current bounds
for P2; do not justify them as PostgreSQL capacity or local Mac limitations.

At the consultation snapshot, Claude's active worktree was
`edgartools-platform-claude-nolimit`, branch
`claude/merge-no-limit`, committed `904f7318` plus living-doc edits. Ticket74 removes
Merge Stage closure/projection/assessment-history refusals, save-request16MiB,
proposal stored16MiB/sent64MiB and snapshot/query caps via migration019. It preserves
input batch cutting (1,000 records / 1MiB), per-batch shape checks and input/read-back
bounds. Some retained read-back bounds can still refuse oversized input; describe
the scope as **Merge Stage size-refusal removal**, not “all PostgreSQL limits gone.”
The ticket reports twelve PostgreSQL tests passed; this review did not rerun them.
At that snapshot, ownership rerun, installed proof, review and publication remained
Claude's checklist.
No open PR or merge was observed for Ticket74 at the checked snapshot.

A fresh independent Claude CLI consultation completed after the skill's Fable5.1
default required usage credits; retry used the included Opus model. It read both
worktrees and reported six findings. It confirms MDM-only implementation, retained
input limits and unchanged Bookkeeping caps. Its broader suggested uncapped/paged
Bookkeeping redesign is deferred under the operator's explicit MDM-only ruling;
it is not auto-applied or presented as agreement from the active Claude session.
If that future scope changes, parent-wide hot-path recompilation loses the128 bound
and requires admission-time immutable per-child provenance plus separate protocol/
atomicity review. No new fixed cap is recommended as a workaround for future scale.

P2 introduces no MDM closure/proposal/request ceiling and no total-run size ceiling.
CLI limits are scheduling/pages, not permission to stop processing the remaining
run. N100/1,000/10,000 are qualification samples, not supported-volume maxima.
Local PostgreSQL16 proves correctness, restricted roles and race behavior; capacity
claims target a separately qualified hosted PostgreSQL environment. Do not derive
production limits from local machine measurements. Preserve no-limit Merge Stage
behavior, now merged as PR960, in the future matched worker/MDM compatibility proof;
no cherry-pick or edit of Claude's implementation is needed for this planning delivery.

## What already exists

| Sub-problem | Existing implementation | Reuse |
|---|---|---|
| Authenticate immutable bytes | `Artifacts.verified/json`, Rules authority resolver | Existing exact byte/hash checks at admission and relevant use. |
| Compile original/generated work | `config.validate/worklist/generated_worklist` | Retain Python compiler; new destination consistency checks only. |
| Frozen scope audit | `engine._frozen` | Extract complete audit, retain recovery behavior. |
| Exact unit lookup | `engine._row`, work-item primary key | Reuse; no redundant index. |
| Independent worker/verifier roles | migration 006 and `grant_profile` | Preserve separation; root admission is a distinct grant. |
| Atomic generated admission | migration 004 `finish_expand` | Extend origin checks; preserve transaction and count/replay behavior. |
| Completion/checkpoints/outbox | migrations 003/004/006 | Preserve locking and local atomicity. |
| Recovery and compaction | `resume/_verify_completed`, owner-only `compact` | Preserve evidence checks and archive semantics. |
| Real PostgreSQL testing | `tests/support/pg16.py`, existing protocol fixtures | Reuse actual PostgreSQL 16 and restricted roles. |

## NOT in scope

1. P1 destination-fence authentication/enforcement: independent safety work; P2 makes no repair claim.
2. P1 complete runtime fingerprint/admission: independent reproducibility work; public worker ABI unchanged here.
3. AWS rollout/activation, secret values, new infrastructure or restoring retired workflows: separately qualified operator work.
4. A persistent controller service or new workflow engine: does not establish definition integrity and expands operations.
5. Merkle proofs: useful only if portable independent admission proofs become a requirement; no need established here.
6. Automatic old-run conversion/backfill and a new finalizing state: avoid mutation and lifecycle expansion; existing runs drain.
7. Broad repository onboarding, dashboard or skill redesign: changes stay within control-path docs and qualification.

## CEO review: strategy, scope and failure analysis

Mode: SELECTIVE EXPANSION. Ordinary questions auto-decided under the six autoplan
principles; the remaining taste choices travel to the final gate. No user challenge
is established: the user's goal remains fixing P2, and no voice recommends abandoning it.

### Step 0: premises, leverage, alternatives and temporal decisions

**Premises:** The repeated-scan problem is observed, not hypothetical. Process-local
reuse helps duplicate calls inside a command but does not remove across-command N
scaling. A protected admission path does not currently exist for all definitions;
it is a required construction and acceptance proof, not an existing guarantee.
An unrelated-evidence detection delay is a policy change; it cannot be auto-described
as behavior preservation. Local query counts are strong evidence, but the initial
single timings are not a full-path performance decision. Internal users are platform
maintainers/operators and installed Company workers, not external SaaS buyers.

**Leverage:** Existing byte authentication, compilers, primary keys, lease functions,
expansion transaction, independent verification, outbox and recovery are the leverage
map above. The initial production surface was engine.py, database.py and one new
migration; engineering adds bounded CLI/authority/report-validator contracts; likely acceptance, command tests, one benchmark harness and run/recovery
docs make the full file count exceed eight. This is a complexity smell checked, not
a reason to omit tests or introduce new services. No new class hierarchy is planned.

```text
CURRENT                       THIS PLAN                      12-MONTH IDEAL
8 global scans/unit     ->    admitted scope + local checks -> control cost explained
+ 2/renewal                    full coherent audits           by relevant work/evidence
+ 1+2D per delivery            complete process benchmarks     every mutation classified
```

| Alternative | Coverage | Effort (human / AI-assisted, provisional) | Risk | Pros | Cons |
|---|---:|---|---|---|---|
| A: command-local reuse only | 7/10 | 1 day / 1-2 hours | Low-medium | Reuses audits; faster batching and delivery; no admission redesign | Retains O(N) for every subprocess command; does not close P2 |
| B: staged reuse + guarded admission + per-unit checks | 10/10 | 4-6 days / 6-10 hours | Medium-high | Removes unrelated-N cost; retains owner/worker/verifier boundaries; measurable rollout | Requires origin enforcement and role qualification; evidence detection timing changes |
| C: portable Merkle membership/append proofs | 10/10 if fully built | 2-3 weeks / 2-4 days | High | Independent membership proofs, reusable outside PostgreSQL | Canonical leaf/proof protocol and dynamic scope sealing are unneeded complexity here |

Recommend B, with A as its first delivery. Do not declare A a completed P2 fix.
The 10x opportunity is avoiding all unrelated control work while preserving evidence,
not replacing the platform. Five low-cost adjacent improvements were considered:
command-local reuse, expected-event reuse, dependency dedup within an audit, named
integrity errors, and full-process benchmark counters. All five are included because
they sit directly in the changed control paths; the wider service/cryptographic/UI
ideas are deferred. Their estimates are provisional, not promises of review time.

HOUR 1 (human; AI ~15-30m): freeze the role/byte-origin contract and baseline counters.
HOUR 2-3 (AI ~30-60m): implement immutable-field guards and classify every SQL route.
HOUR 4-5 (AI ~1-2h): wire contexts and generated scope; qualify partial finalization.
HOUR 6+ (AI several hours including real tests): run collisions, retries, compaction,
installed-process benchmarks and rollback. Resolve these contracts in this plan;
implementation cannot choose an admission bypass to save time.

### 1. Architecture

The current dependency graph couples every ordinary command to `_frozen` and whole
artifact/worklist enumeration. The chosen split keeps authority in PostgreSQL and
business/source policy in existing Rules/worker owners. The new coupling is a compact
admitted context and expansion-origin consistency contract; it is justified only by
restricted-role proof, not by a boolean marker. PostgreSQL and the artifact store
remain failure points; failures block or wait visibly and never trigger rediscovery.

```text
BEFORE: worker/verifier -> CLI -> _frozen -> all manifests + all work + expansions
                                  |-----> lease/report/finish SQL
AFTER:  trusted root submitter -> authenticate + compile -> sealed admission SQL
        worker/verifier -> CLI -> run/unit context -> live SQL authority transition
                                 |              |----> relevant evidence closure
                                 |----> full audit only at deliberate boundaries
        parent verification -> bounded authenticated expansion -> atomic seal+children
```

### 2. Error and rescue map

The original plan named integrity principles but not exact caller-visible errors.
Use existing `Blocked`, `ControlError` and SQLAlchemy `DBAPIError` categories; attach
stable control error reasons and run/step/unit context without credentials or rows.
Integrity errors block the run, contention waits/retries within existing bounds, and
network errors preserve retryable work/outbox intent. The registry below is the exact
required rescue contract; broad catch-all conversion must not turn defects into success.

| Path / trigger | Exception/category | Rescue | Caller sees / next action | Required test |
|---|---|---|---|---|
| Root admission: missing/hash-invalid Rules or manifest | Blocked / scope_evidence_invalid | Block root if created; refuse new admission | Exact artifact role/reference and original-evidence recovery docs | Existing drift tests + sealed-admission negative |
| Root admission: ordinary worker calls sealed API | DBAPIError / admission_role_required | No writes, no automatic grant | Use separately authorized submitter connection | Direct SQL restricted login |
| Unit context: unknown/malformed/changed definition | Blocked / unit_definition_invalid | Block root | Run/step/key, mismatch reason, inspect original scope | Missing/modified row + wrong envelope |
| Generated scope: wrong bytes/hash/parent/child | Blocked or DBAPIError / expansion_origin_invalid | Roll back entire seal transaction, block on integrity failure | Parent binding; restore exact expansion evidence | Forged verifier SQL, malformed bytes, duplicate children |
| Claim/renew: contention or replaced/expired token | DBAPIError 55P03 or stale authority | Existing bounded backoff/wait, no effects from stale attempt | Waiting/stale attempt; resume/reclaim action | Existing fencing/expiry + context path |
| Report/admit: mismatched report/candidate/runtime | Blocked or DBAPIError / report_binding_invalid | Refuse and preserve evidence; no completion | Exact failed binding/check, existing verifier workflow | Existing admission negatives |
| Relevant artifact: unavailable, malformed or digest mismatch | Blocked / relevant_evidence_invalid | Block root; never silently skip | URI without credential-bearing query, recover original bytes | Dependency corruption/empty/UTF-8 cases |
| Finalize: work/delivery still pending | Existing partial result, exit 3 | Preserve waiting state, no terminal audit | Remaining counts and same finalize/resume commands | CLI backlog drain |
| Finalize: audit/locked completion sees intervening work | False readiness checks, integrity block or DBAPIError serialization/deadlock | Preserve sticky block; nonintegrity partial stays waiting; retry only after inspection | Partial state, retry existing finalization | Concurrent expansion/finalization barriers |
| Journal append/read-back unavailable/conflicting | ConnectionError, JournalConflict, DBAPIError | Leave outbox pending; propagate visible error | Pending delivery, exact retry action | Existing outage/recovery + one expected event |

### 3. Security and threat model

The new fast path can make false definitions durable if admission is mistaken.
Likelihood is medium because runtime functions are callable directly; impact is high
because workers act on declared inputs/outputs/resources. Initial root admission gets
its own trust/grant, while bounded generated origin is verified at the destination
and tested under both worker and verifier logins. The context/tag/lineage cannot be
changed by setting a session variable or by a legacy entry point. No new public
network endpoint, source callback, credential logging or third-party dependency is
required; SQL parameters and schema-qualified definer functions remain mandatory.

### 4. Data and operator edge cases

The four paths are explicit for root admission, local validation, expansion and
delivery. Missing and invalid evidence refuse/stop; empty root work requires existing
`allow_zero_work`; zero-child expansion must still seal; repeated completion compares
identical evidence and changes no counts. Closing a worker process leaves the durable
lease/work row to recover, and a lost acknowledgement reconciles existing effects.

```text
ROOT bytes -> authenticate -> compile -> sealed rows -> claimable work
    nil/error -> refusal      empty -> allow_zero_work or refusal
UNIT key -> compact context -> selected row/parent -> live lease -> report/admit
    nil/unknown -> block        evidence error -> block         stale -> wait/refuse
EXPANSION bytes -> hash + parent + descriptor checks -> [seal + children + outbox]
    nil/invalid -> rollback    empty -> zero seal        replay -> compare, no insert
EVENT -> expected envelope once -> append -> read-back -> acknowledge
    missing lineage -> block       outage/conflict -> pending intent, visible failure
```

### 5. Code quality and GoF

Read the engine, config compiler, migrations and call history rather than proposing a
new dispatch framework. `_row`, `_same_work`, `_compose` receipt dedup and the current
atomic `finish_expand` are good seams to reuse. Recursive `_frozen` and the two event
constructions per row are the measured anti-patterns; split responsibilities and
pass explicit command-local context. GoF reviewer is available and applied; no
Proxy/Mediator/State hierarchy earns its extra indirection for this measured problem.

### 6. Tests

Actual PostgreSQL 16 is necessary for grants, trigger behavior and concurrency.
Existing generated-work, corruption, expiry and installed-process suites are reuse,
not evidence that a proposed fast path works. New branches need tests for trusted vs
ordinary root admission, fabricated child origin under direct SQL, format eligibility,
per-unit failures, readiness short-circuiting and scope/evidence races. No runtime LLM
or prompt behavior changes are planned, so AI quality evals are not applicable.

```text
admit root -> qualified tag / denied role / malformed or zero scope
unit action -> fixed prerequisite closure / bad unit / stale lease / missing evidence
parent seal -> 0..128 children / 129 refused / wrong origin / conflicting replay
finalize -> pending fast return / coherent full audit / race leaves waiting
deliver -> same event for append+verify / outage keeps intent / lost ack reconciles
upgrade -> old mode drains / new mode protected / rollback continues safe old audits
```

### 7. Performance

The original single-unit measurement is too narrow for success criteria. Full-process
trials now include startup, worker/verifier handoffs, dependency shapes, journal drain
and repeated partial finalization. Per-command reuse is a baseline to beat, not a
rejected cache idea; per-operation counts are a structural gate and wall/RSS/p99 gates
are separate. O(N+E+B) is an audit target after local evidence dedup, not a guarantee
for repeated cross-command chain traversals or real source transformation costs.

### 8. Observability and debug

Keep compact timing/row/byte counters in qualification artifacts and bounded control
logs tagged by run/step/key, phase, validation format and error reason. State/exit
codes must distinguish partial progress, integrity block and transient contention.
Do not log DSNs, raw source rows or complete envelopes. A new telemetry service or
CloudWatch dashboard is outside this plan; the existing CLI/status plus a readable
run/recovery guide is the day-one operational surface.

### 9. Rollout and rollback

The rollout is local qualification first; this review performs no AWS action. Add the
migration with old-mode behavior still supported, validate restricted roles and every
write route, then run new-client/new-mode fixtures and installed process checks.
Drain rather than rewrite existing submissions; rollback returns to whole audits,
retains all evidence/history and never rolls back schema by dropping columns/tables.
A partial rollout must refuse unknown format or absent required grants visibly.

```text
A command reuse -> baseline verified -> B additive migration+origin checks
 -> role/negative tests -> C new format contexts -> installed/full-path qualification
ROLLBACK: stop new-mode admission -> retain DB guards/evidence -> compatible full audits
```

### 10. Six-month trajectory

A bounded control API fits the existing architecture without another mutable store.
The maintenance liability is an undocumented extra writer or indefinite mixed modes;
the catalog test and old-mode drain inventory are required. This is a reversible
client optimization (4/5), with additive guard metadata kept during rollback rather
than destructive migration reversal. Portable proofs, persistent services and broad
onboarding remain deferred unless measured requirements establish their value.

### 11. UI design

Skipped: inspected plan and current CLI flow, with no screens, components, visual
states, dashboard changes or frontend interactions added. Backend control terms such
as report/input/field are not evidence of UI scope. DX review follows because commands,
role setup, docs and operational error paths change.

### Failure modes registry

| Path | Failure | Rescue/state | Existing/new test requirement | Caller visibility | Logging |
|---|---|---|---|---|---|
| Sealed root admission | Forged new mode through ordinary role | Refuse, no writes | New direct SQL role negatives | admission role error | reason + run reference |
| Unit context | Wrong immutable fields or missing unit | Root blocked | New unit-origin checks | definition mismatch | run/step/key |
| Relevant evidence | Artifact unavailable/corrupt | Root blocked | Existing corruption + new context variants | recovery action | reference/digest, no content |
| Unrelated evidence | Becomes missing while another unit runs | Detected at next deliberate audit | New detection-policy test | documented policy, then block | audit reason |
| Expansion | Candidate bytes differ / wrong parent / forged child | Roll back and block | New byte-origin SQL negatives | origin mismatch | parent identity |
| Expansion replay | Missing child repaired inadvertently | Refuse replay, no new work | New sealed replay missing-child case | conflicting replay | original seal identity |
| Completion | New work arrives during finalize | Waiting unless full scope verified | Existing gate + new barrier race | partial counts/exit 3 | readiness/audit result |
| Journal drain | Full scan every limited finalize | Short-circuit until ready | New real CLI backlog case | partial progress | bounded timing/counts |
| Audit dedup | Reuses mutable or changed evidence | Refuse or reauthenticate | New shared-ancestor/corrupt receipt | integrity block | evidence identity |
| Upgrade | New tag without guard/grant qualification | Block fast-mode admission | New mixed version/grant tests | unsupported format/grant | mode and expected action |

Zero silent, untested failure modes are accepted; every new requirement above is a
pre-enablement gate. Current code does not yet implement these gates.

### CEO outside voices and consensus

CLAUDE SUBAGENT (CEO, strategic independence): six substantive findings. Protected
admission is absent; command reuse is a valuable first step; integrity failure must
still block the root; old-run conversion is avoidable; a revision counter may duplicate
current completion locks; mutation-route classification must not drift. Two incidental
copy defects in the review input (relative links/baseline) are corrected in this plan.

CODEX SAYS (CEO, strategy challenge): six substantive findings. Specify admission
principal and origin; set full-path numerical gates and adopter; avoid repeated terminal
audits during bounded finalize; define artifact-store detection timing; model dependency
edges/bytes; drain or explicitly own old-run conversion. These are absorbed in A/B/C,
acceptance criteria, finalization, detection policy and compatibility sections.

| Dimension | Claude | Codex | Consensus |
|---|---|---|---|
| Premises valid? | Admission premise false | Admission unspecified | Confirmed concern, amended |
| Right problem? | Real hotspot, stage reuse first | Observed P2, validate full-path value | Confirmed staged goal |
| Scope calibration? | Remove conversion/counter duplication | Avoid indefinite compatibility | Confirmed drain/no default counter |
| Alternatives explored? | Command reuse overlooked | Compare command reuse before redesign | Confirmed, A included |
| Market/adoption risks? | Existing internal CLI is adequate | Name adopter and quantitative gates | Disagree on sufficiency; gates/adopter added |
| Six-month trajectory? | Mutator list drifts | Two modes lack exit | Confirmed, catalog check + drain criterion |

Consensus: 5/6 confirmed, one disagreement retained as a taste choice about the required
full-path adoption/performance gates. Missing voice: none; both actual CLIs completed.

### CEO completion summary

| Required output | Result |
|---|---|
| Mode / system audit | SELECTIVE EXPANSION; current main, dirty primary protected, no overlapping source edits |
| Step 0 | Six premises evaluated, three alternatives, leverage and temporal maps written |
| Architecture / errors | 2 authority/scope issues; 10 registry paths, no accepted silent gaps |
| Security / data | 2 admission/route issues; four-path diagrams, zero/empty/replay cases specified |
| Quality / tests | 2 duplicate-work issues; test-flow diagram, new negative/race coverage required |
| Performance / observability | 4 full-path/dependency/finalize/gate issues; bounded counters and recovery messages |
| Rollout / future | 2 compatibility/partial rollout risks; reversibility 4/5, drain + mutation catalog |
| UI | Skipped, no UI scope |
| NOT in scope / leverage / dream state | Written, 7 exclusions, existing-code map and ideal delta |
| Registries / diagrams | 10 error/rescue paths and 10 failure modes; architecture, data, flow, rollout diagrams |
| Deferred items | P1 fence, P1 fingerprint, persistent-service exploration only if future benchmarks justify it |
| Scope proposals / CEO plan | 5 small control-path additions accepted, no new infrastructure; CEO snapshot and review logs archived |
| Outside voices / completeness | Claude 6 and Codex 6 findings; 5/6 consensus; full staged approach selected |
| Remaining taste choices | Detection policy, validation format/drain, no-default-counter proof, full-path gates |


### Validation modes, work states and error transitions

```text
original full validation -> sealed new-mode admission -> running <-> waiting
                                   |                    |           |
                                   | unauthorized       +-> blocked +
                                   +-> refused          +-> complete -> audited compaction
old whole-run mode -> drains/archived; no in-place transition into new mode
pending -> running -> reported -> verified (receipt immutable)
                          |          |
                          |          +-> expansion seal immutable; replay cannot add children
                          +-> failed admission/expired lease: waits, never verified silently
```

```text
control failure
  +-- 55P03 contention -> bounded retry -> waiting if still contended
  +-- stale token / wrong issuer -> refuse transition -> preserve original work
  +-- integrity / evidence mismatch -> block root -> original-evidence recovery
  +-- journal outage -> pending outbox -> later delivery read-back -> acknowledge
No branch catches an integrity error and continues as success.
```

```text
finalize (--limit retains existing meaning)
   |
   +-> deliver bounded pending outbox batch
   +-> live readiness: work/report/seal/delivery pending?
          +-> yes: partial status, existing exit 3, no terminal evidence scan
          +-> no: coherent complete-scope audit -> locked record_checks
                     +-> incomplete/stale/conflict: waiting/block as appropriate
                     +-> all current requirements hold: complete
```

### Landscape synthesis

[Layer 1] PostgreSQL row guards, restricted function grants and indexed row lookup
are the tried-and-true mechanisms to enforce admitted definitions and live authority.
[Layer 2] Official pg-boss and AWS execution-status references demonstrate bounded
job handling and explicit completion status; they are comparisons, not new dependencies
or a proposal to revive retired deployment paths. [Layer 3] A selected-unit proof cannot
also certify that every unrelated artifact is still available; reducing global work
requires explicit admission trust and a declared global-audit detection policy.


### CEO implementation tasks

- [ ] **T1 (P2, human: 1 day / AI: 1-2 hours)** Remove duplicate audits within each command. Files: edgar_warehouse/bookkeeping/clean/engine.py, tests/integration/test_configured_bookkeeping_postgres.py. Verification: corresponding PostgreSQL/command or benchmark gate in this plan.
- [ ] **T2 (P1, human: 2 days / AI: 3-4 hours)** Protect root and generated admission and freeze definitions. Files: edgar_warehouse/bookkeeping/clean/engine.py, edgar_warehouse/bookkeeping/clean/database.py, edgar_warehouse/bookkeeping/clean/migrations/007_admitted_scope.sql, tests/integration/test_generated_bookkeeping_postgres.py, tests/integration/test_configured_bookkeeping_postgres.py. Verification: corresponding PostgreSQL/command or benchmark gate in this plan.
- [ ] **T3 (P2, human: 1 day / AI: 1-2 hours)** Enable qualified per-unit validation contexts. Files: edgar_warehouse/bookkeeping/clean/engine.py, tests/integration/test_configured_bookkeeping_postgres.py. Verification: corresponding PostgreSQL/command or benchmark gate in this plan.
- [ ] **T4 (P1, human: 1 day / AI: 1-2 hours)** Qualify readiness and coherent terminal reconciliation. Files: edgar_warehouse/bookkeeping/clean/engine.py, tests/integration/test_generated_bookkeeping_postgres.py, tests/integration/test_configured_bookkeeping_postgres.py. Verification: corresponding PostgreSQL/command or benchmark gate in this plan.
- [ ] **T5 (P2, human: 1 day / AI: 2-3 hours)** Measure complete control paths with fixed dependency closures. Files: scripts/benchmarks/benchmark_bookkeeping_control.py, tests/integration/test_configured_bookkeeping_postgres.py, tests/integration/test_generated_bookkeeping_postgres.py. Verification: corresponding PostgreSQL/command or benchmark gate in this plan.

CEO spec review: one independent round, all five dimensions PASS, overall 9/10; zero remaining spec issues. Acceptance gates and timing policy were accepted at the final A gate; implementation evidence remains pending.

## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| 1 | Intake | Review the P2 proposal; preserve original research externally | Mechanical | P5 | Concrete target and restore point; no source changes | Re-review entire platform |
| 2 | Intake | No UI; run DX for CLI/platform operator surface | Mechanical | P5 | No visual changes; setup/errors/recovery are affected | False UI keyword matches |
| 3 | CEO | Selective expansion, staged complete option B | Taste | P1/P3/P5 | Deliver command reuse first and still close unrelated-N scanning | Treat reuse-only A as complete |
| 4 | CEO | Protect initial admission and independently prove bounded child origin | Mechanical | P1 | Current grants and hashes are insufficient authority | Freeze arbitrary caller rows |
| 5 | CEO | Internal validation tag; new runs only, old runs drain | Taste | P3/P5 | Avoid public envelope ABI change and conversion/backfill | Reuse message PROTOCOL as validation version |
| 6 | CEO | Gate selected-unit evidence immediately; unrelated evidence at full audits | Taste | P3 | Necessary detection-policy distinction exposed explicitly | Claim unchanged global detection timing |
| 7 | CEO | Keep current completion lock/gate; no default worklist counter/state if closure proof passes | Taste | P4/P5 | Full audit must observe closed verified scope; prove races | Add revision counter without need |
| 8 | CEO | Include partial-finalize readiness before terminal audit | Mechanical | P1 | Bounded finalize otherwise keeps quadratic drain cost | Call every poll a boundary audit |
| 9 | CEO | Deduplicate immutable evidence within one coherent command/audit | Mechanical | P4/P5 | Shared ancestors repeat today; no mutable-state cache | Persistent receipt/status cache |
| 10 | CEO | Include complete process benchmarks and proposed numerical gates | Taste | P1 | Query-only measurements cannot establish operational value | Claim speedup from single local sample |
| 11 | CEO | Include catalog classification and direct SQL negatives | Mechanical | P1 | New function/old signature must not bypass admitted definitions | Python-call-only qualification |
| 12 | CEO | Keep P1 repairs, AWS rollout and new engines out of P2 implementation | Mechanical | P3 | Independent authority/reproducibility issues remain visible | Inflate this plan into platform cutover |

## DX review: operator and contributor experience

Mode: DX POLISH. Product: internal Python/PostgreSQL CLI and process protocol.
UI review is skipped: no page, screen, layout or component changes are proposed.
No prior comparable DX score is available; these are plan-quality scores, not a
measurement of an implemented product. Autoplan resolves intermediate questions.

### Step 0: persona, empathy, comparisons and journey

**Persona card:** A platform maintainer working in a dedicated macOS/Linux worktree,
comfortable with uv, SQL migrations and role separation. Their job is to submit a
bounded Company run, let independent processes finish it, diagnose failures and
prove completion without accessing migration-owner credentials from a worker.
They already have project dependencies; a first-time public package evaluator is
not the dominant user. Success means reproducible local proof and safe recovery.

**Empathy narrative (roleplay, not a timed user observation):** I arrive at the README
installation section because I want to see whether this change makes a Company
run cheaper to control. I see the ordered infrastructure installer and several
store variables. I do not want to provision AWS just to understand a PostgreSQL
validation change. I follow the configured-capture guide instead and find the
real PostgreSQL test path. I can see how to run a worker and a separate verifier,
but the proposed submitter role is new: I need its exact grant and connection
variable before I can trust a successful run. When finalize returns exit 3, I need
to know whether it means more delivery remains or an integrity failure requires
me to act. I want status to tell me which validation mode is effective. If a
receipt becomes unreadable, I need the failed reference and a recovery command
in the final error line my worker preserves. I also need a way to add full auditing
without rebuilding the run. The amended bounded guide supplies those steps, keeps
secrets out of examples and labels every speed claim as a pending measurement.

**Competitive DX benchmark:** These are comparison dimensions, not replacement
recommendations. No comparative onboarding times were measured or published here.

| Reference | Useful baseline | Adopt in this plan | Boundary |
|---|---|---|---|
| [pg-boss introduction](https://pgboss.io/introduction) | Small database-backed worker example | Short bounded control example and visible completion | Do not add Node or another queue |
| [pytest getting started](https://docs.pytest.org/en/stable/getting-started.html) | Runnable example and explicit assertion output | One focused real-PostgreSQL proof command, clear pass/fail | Use repository uv workflow; retain real roles |
| [AWS CLI return codes](https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-returncodes.html) | Explicit command-result meanings | Document status success versus finalize partial/complete | No AWS deployment/workflow changes |

Target tier: competitive internal-tool DX. Target time to first bounded proof is
under five minutes **in a prepared environment**; cold installation, Rust builds,
credentials and first PostgreSQL download are separately timed and currently
unmeasured. Do not advertise a measured zero-to-install time.

**Magical moment:** A local, pinned, no-SEC-network fixture completes through separate
worker/verifier processes; status shows stored/effective validation and the harness
shows that adding unrelated units does not add hot-path rows or artifact bytes.
Lowest-cost vehicle: existing pytest fixtures plus one benchmark script, not a web
playground. The guide starts with the existing baseline proof, then names newly
added qualification tests once implemented. Existing runnable baseline command:
`LC_ALL=C LANG=C PG16_SERVER=pgserver uv run --with pgserver pytest -q
 tests/integration/test_configured_bookkeeping_postgres.py -k full_completion`.
It requires a prepared project environment and PostgreSQL 16 support; it does not
prove the proposed optimization. Expected success is a passing selected test,
not a fabricated transcript or fixed run identifier.

| Journey stage | Actual touchpoint | Friction and planned resolution | Status |
|---|---|---|---|
| Discover | README installation section | Infra-first path obscures bounded local control proof; add control guide link | Planned |
| Evaluate | Research measurements | Startup and delivery excluded; show exclusions and full-process gates | In plan |
| Install | uv + tests/support/pg16.py | Docker unavailable locally; supported transient pgserver path, no silent skip | Baseline qualified |
| Hello world | Configured PostgreSQL fixture | No live SEC/AWS needed; copy complete prepared-environment command | In plan |
| Integrate | rules run / worker / verifier | One new authority; explicit submitter variable/grant and separate logins | Planned |
| Debug | Worker final stderr line | Add problem, cause, original reference, checks/resume and docs path | Planned |
| Upgrade | Checksummed migrations | Forward order, legacy drain, old-code/new-schema proof | Planned |
| Scale | Real subprocess harness | Query-only gains insufficient; separate startup, dependencies and total cost | Planned |
| Migrate | New-run validation format | No conversion; visible mode, bounded inventory, tightening-only override | Planned |

**First-time confusion log (simulated timestamps):** T+0:00 README installation looks
like an AWS task (resolved by bounded guide link). T+0:30 configured-capture provides
local tests but needs PostgreSQL support (name pgserver explicitly). T+1:00 the
same URL appears to serve every role (separate submitter URL/grant). T+2:00 finalize
exit 3 is ambiguous without state (document status/exit matrix). T+3:00 a fallback
would be tempting after an error (offer explicit full-audit tightening, preserve
integrity failure and original evidence). These are reasoned friction estimates,
not observations of elapsed setup time.

### Eight full DX passes

**1. Getting started: 5 → 8/10.** README installation at lines 194–220 leads into
infrastructure while this fix can be demonstrated locally. The plan now supplies
one prepared-environment test command, a pinned fixture and an explicit PostgreSQL
prerequisite, borrowing pytest's executable-example approach. A 10 requires a new
maintainer to run the implemented qualification flow in under five measured minutes;
that evidence remains pending, and cold install is a separate result.

**2. API/CLI: 5 → 9/10.** Existing `admit` means verifier admission, so calling root
submission “admit” and treating task protocol 1 as validation version would confuse
users. Retain the message ABI and command grammar; name the separate submitter
variable, owner-only grant, bounded inventory filter and two status fields. A 10
requires installed-wheel/worker contract tests to prove old JSON consumers tolerate
the additive inspection fields and unchanged task envelopes.

**3. Errors/debugging: 4 → 8/10.** `workers/control.py:20` preserves the final stderr
line, while current frozen-work errors omit safe recovery context. Require concise
problem/cause/fix and a runbook path on that line, distinguish unavailable bytes
from mismatched bytes, and test the wrapper-visible output. A 10 needs demonstrated
operator recovery without replacing immutable input or exposing DSNs.

| Error path | Baseline/current risk | Required proposed final line |
|---|---|---|
| Submitter authority absent | No dedicated path today; raw permission error would confuse | `Run submission refused: submitter configuration/role is missing; request grant-submitter from the migration owner; see skills/bookkeeping/RUN.md` |
| Relevant evidence corrupt/unreadable | `Frozen work accounting changed` or artifact error | `Run RUN blocked: REF could not be read / SHA-256 differs; restore original bytes/access, then bookkeeping checks RUN and bookkeeping resume RUN; see skills/bookkeeping/RECOVERY.md` |
| Partial finalize | Exit 3 can look like process failure | JSON retains actual run state and pending deliveries; docs say retry bounded finalize after work/delivery progresses; blocked state requires checks/recovery |

These examples specify content, not mandatory byte-for-byte message wording.
Hash mismatch must not be presented as a transient networking retry.

**4. Documentation: 5 → 9/10.** Existing configured-capture and Bookkeeping RUN/RECOVERY
already describe commands and retained evidence, so reuse their information
architecture. Add a narrow setup/upgrade/exit-code section, full copied commands,
mode visibility, expected output semantics and a README link in the same delivery.
A 10 requires every example to run against the installed implementation and its
matched migration version; no public playground or new docs framework is needed.

**5. Upgrade/migration: 4 → 9/10.** Immutable guards and a new authority make code-only
rollback unsafe while tagged runs exist. The plan now names migration/grants/code/
qualification/enablement order, full-audit tightening, legacy inventory and drain,
and forbids guard deletion as a rollback technique. A 10 needs both old-code/new-
schema and active-tag rollback refusal tests, plus a rehearsed bounded runbook.

**6. Environment/tooling: 6 → 8/10.** Existing uv and PostgreSQL fixtures support the
change and existing CI includes real integration gates; local Docker is currently
unavailable. Reuse a transient pgserver test dependency with locale C for local
verification, retain container-based CI and fail visibly when PostgreSQL is absent.
A 10 needs the implemented role bootstrap and no-network fixture verified on both
macOS and Linux; editor/TypeScript SDK changes are irrelevant to this Python tool.

**7. Community/ecosystem: 7 → 8/10.** This internal control change needs maintainers to
find the runbook and report reproducible failures, rather than a new public channel.
Reuse repository issues/PR review, add a bounded reproduction template with run
mode and redacted command/error output, and preserve the real Company fixture.
A 10 would require demonstrated newcomer handoff; broad contributing-guide repair,
SDKs, pricing or community-building are deferred because they do not close P2.

**8. Measurement/feedback: 4 → 9/10.** The research timing omits subprocess startup
and does not establish end-to-end benefit. The harness now has an exact proposed
path/command, retained JSON fields, fixed 120/10-second lease/heartbeat, five trials
and numerical gates; a prepared setup timer records feedback latency, cognitive
friction and successful completion rather than just speed. A 10 requires actual
repeated output and a maintainer confirmation, not a plan-only score inflation.

### DX scorecard and implementation checklist

| Dimension | Intake → amended | Remaining proof |
|---|---|---|
| Getting started | 5 → 8 | Timed new-maintainer prepared setup |
| API/CLI | 5 → 9 | Installed command/envelope compatibility |
| Errors | 4 → 8 | Worker-visible errors and recovery |
| Documentation | 5 → 9 | Executed examples |
| Upgrade | 4 → 9 | Cross-version and drain rehearsal |
| Environment | 6 → 8 | macOS/Linux real PostgreSQL |
| Community | 7 → 8 | Bounded handoff reproduction |
| Measurement | 4 → 9 | Full-process evidence |

Overall plan quality: **8.5/10**, competitive for an internal CLI. TTHW: unmeasured,
target <5 minutes prepared environment; cold setup unmeasured. Magical moment:
designed through existing fixture plus harness. Zero friction, learn by doing,
fighting uncertainty, opinionated defaults with a tightening escape, code in context
and a meaningful visible result are covered in the plan, with execution proof pending.

- [ ] Time the prepared local proof; record cold setup separately.
- [ ] Provide one uv-based qualification command with meaningful pass/fail output.
- [ ] Keep task protocol/names compatible and display validation modes.
- [ ] Qualify the owner-only submitter grant and role disjointness.
- [ ] Test problem/cause/fix plus docs path in wrapper-visible errors.
- [ ] Execute bounded runbook examples and upgrade/drain/rollback procedure.
- [ ] Preserve all existing real PostgreSQL, installed-wheel and architecture gates.
- [ ] Capture complete-process, dependency, renewal and backlog measurements.

TypeScript types, public free-tier/pricing and a skill-specific DX appendix are not
applicable to this internal Python control change. New docs sites, communities,
SDKs and general environment installers are NOT in scope. No finding is hidden by
marking an unimplemented item complete.

### DX implementation tasks

- [ ] **T6 (P1; human 1 day / AI-assisted 2–3 hours)** — operator interface — Specify
  submitter configuration/grants, visible modes, tightening-only full auditing and
  safe errors in existing CLI modules. Files: `bookkeeping/clean/{cli,database,engine}.py`,
  `rules/cli.py`, protocol tests. Verify real restricted principals and installed CLI.
- [ ] **T7 (P2; human 0.5 day / AI-assisted 1 hour)** — operator docs — Update the
  bounded setup/upgrade/recovery examples and reproduce them with the fixture.
  Files: `docs/configured-capture.md`, `skills/bookkeeping/{RUN,RECOVERY}.md`, README.
  Verify examples and recorded prepared-environment time.
- [ ] **T5** retains the CEO full-process harness task; DX adds exact output fields,
  startup separation and fixed lease/heartbeat rather than a duplicate benchmark.

### DX independent voices and dispositions

**CLAUDE SUBAGENT (DX — independent review):** Actual fresh Claude CLI review found
five issues: submitter setup, a safe full-audit escape, actionable errors, upgrade
order and full-process harness specification. All are included in the operator
contract; adding a broad doctor subsystem is rejected in favor of focused role tests.

**CODEX SAYS (DX — developer experience challenge):** Actual Codex review found five
remaining issues: exact format selector, installing the migration executable first,
nontruncated rollback inventory, entry-point-specific exit semantics, and ambiguous
timeout outcomes. Each is amended above. Extra inspection fields/options and one
small wrapper diagnostic are costs; no public worker protocol revision is introduced.

| Dimension | Claude | Codex | Consensus |
|---|---|---|---|
| Prepared getting started | Needs runnable bounded guide | Needs exact submission selector | CONFIRMED |
| CLI naming/contracts | Clarify admission/mode | Preserve resume-specific ABI/options | CONFIRMED |
| Errors | Final-line recovery context | Add timeout outcome ambiguity | CONFIRMED |
| Docs | Name setup/harness pages | Copy complete submission context | CONFIRMED |
| Upgrade | Forward order/drain | Install tool first; authoritative count | CONFIRMED |
| Environment | Separate principal is needed friction | Explicit role/URL setup needed | CONFIRMED |

Consensus is on direction and required proof, **not** demonstrated qualification.
No model is treated as having approved runtime activation. The full-audit tightening
escape is a sixth taste choice because it preserves a maintenance path; retaining
only manual boundary checks is viable but less recoverable. Other DX amendments
are mechanical completeness fixes.

### Additional decisions (continuing the audit trail)

| # | Phase | Decision | Class | Principle | Reason | Alternative |
|---|---|---|---|---|---|---|
| 13 | DX | Explicit submitter URL/owner grant; no general doctor expansion | Mechanical | P1/P5 | Auth setup must be executable and disjoint | Reuse worker credentials |
| 14 | DX | Visible modes and explicit tightening-only full-audit override | Taste | P3/P5 | Revert optimization without weakening origin checks | Only manual boundary auditing |
| 15 | DX | Stage new executable before forward migration; authoritative drain count | Mechanical | P1 | Baseline CLI cannot install future migration/grant; list limit misses runs | Infer rollback readiness from 100-row listing |
| 16 | DX | Preserve entry-point exit meanings and qualify final-line timeout recovery | Mechanical | P1 | Existing two resume entry points differ; response loss is ambiguous | Normalize exits or blindly retry |
| 17 | DX | Keep eight-pass DX improvements bounded to control setup/qualification | Mechanical | P3/P5 | No frontend/SaaS/SDK scope | Broad onboarding redesign |

## Engineering review: final amended plan

Mode: FULL REVIEW, engineering runs after all CEO/DX amendments. Scope accepted:
complete A→B→C; no reuse-only shortcut, no P1 repair or AWS activation. The eight-file
complexity check triggers because role/CLI/SQL/qualification/docs span boundaries,
but no new service or class hierarchy is justified. Existing modules own the work;
configuration-independent integrity at PostgreSQL remains necessary.

### Step 0: existing contracts, search and evidence calibration

The reuse table and NOT-in-scope section above are authoritative. Installed control
and worker wheels already exist; update their existing builds/package migration
inclusion, rather than create an artifact type or deployment pipeline. GoF review
of engine calls and change history supports an explicit passed validation context;
no Factory, Strategy hierarchy, observer bus or persistent controller is needed.
Sequential implementation, no parallelization opportunity: admission, contexts,
completion and tests overlap the same control module and depend on each other.

Built-ins checked against primary PostgreSQL 16 documentation:
[raw bytea SHA-256](https://www.postgresql.org/docs/16/functions-binarystring.html),
[repeatable-read snapshots](https://www.postgresql.org/docs/16/transaction-iso.html),
[partial indexes](https://www.postgresql.org/docs/16/indexes-partial.html) and
[restricted SECURITY DEFINER search_path](https://www.postgresql.org/docs/16/sql-createfunction.html).
Use these existing database mechanisms [Layer 1]; an extension, separate integrity
service or new queue does not solve an unmet requirement here. Raw byte hashing is
available natively; it does not itself prove semantic child/compiler equivalence.

### Section 1: architecture and trust

**E1 [P1, confidence 9/10] — generated origin is a construction, not current proof.**
The motivating plan requirement is “The direct SQL path must reject fabricated child
lists even under a verifier login” (section B, generated admission). Existing engine.py:489–494
computes `children = generated_worklist(expansion, config, ...)` in Python and passes
`"children": canonical(children)`; 004_generated_work.sql:53–55 then does
`INSERT INTO bookkeeping.work_item ... ON CONFLICT DO NOTHING`. Shape/replay checks
alone cannot establish that arbitrary direct SQL children equal reported bytes.
The complete fix requires a raw-byte SQL boundary and compiler-equivalence tests,
not another adjacent hash. Downside: bounded generic consistency logic in SQL must
be maintained in parity with the restricted Python template contract.

**Concrete admission contract:** A new raw-byte finish entry point receives `bytea`
and validates `encode(sha256(raw), 'hex')` against the parent's stored reported
candidate hash before parsing. Retain the frozen parent, target child step and
ordinal base; derive/check every descriptor from those bytes and the immutable
normalized generic step rules. The existing template language allows simple named
fields only (config.py:71–73); qualify literal/field tokens, escaped braces, exact
keys, nonempty string values, sorted/deduplicated resources, original child unit,
ordinal offsets, uniqueness and max128. Reuse `artifacts.json_value` strict decoding
which already rejects duplicate keys and nonfinite numbers; do not invent a second
permissive Python parser. SQL must reject unsupported byte/number/text forms before
fast-format admission, with differential cases including PostgreSQL JSONB limits.
The legacy finish-expand signature refuses tagged runs; only the qualified raw-byte
route can add their children. Parent completion requires a deferred seal invariant
that holds at transaction commit, so ordinary finish cannot bypass it and expansion
can atomically set the seal. No client-set trusted flag authorizes a trigger bypass.
New lineage/seal fields stay in existing control rows, not a sixth table.

```text
Rules approved export + ORIGINAL manifest bytes
          | authenticated by separate submitter
          v
 restricted initial submit -> immutable compact context / original units
          |                         |
          |                         v
          |              selected unit + relevant immutable evidence
          |                         |   (live lease/profile stays SQL-owned)
          v                         v
 worker reports candidate --> distinct verifier reads/checks --> raw-byte expansion SQL
                                                        | digest + generic parity
                                                        v
                            children + seal + count + checkpoint + outbox (ONE TX)
                                                        |
                    ordinary control / exact journal readback / selected dependencies
                                                        |
                       ready? ----no----> partial, no terminal evidence scan
                         yes
                          v
              one coherent full audit -> current locked completion gate
```

**E2 [P1, confidence 9/10] — snapshot propagation and closure need explicit proof.**
The plan says “Once ready, take one coherent read-only audit snapshot” (section C),
but current `_frozen`, `_receipt`, status and `_run` each open connections; for
example engine.py:226 says `with self.engine.connect() as conn:`. Thread the same
repeatable-read audit connection through all run/work/status/dependency reads,
never a context that opens a fresh connection behind it. Close that read-only
transaction before an integrity-block write; hand only audited results to the
locked SQL gate, which rechecks current closed scope/state/seals/delivery. Reject
completion if a concurrent root block won; do not let a true/false stale audit
clear that block without explicit resume. Current record_checks:87 says
`state=CASE WHEN complete THEN 'complete' ELSE 'waiting' END`, so the required
blocked-state guard is a real new obligation. A revision counter remains conditional
on failing the closed-scope proof, rather than claimed unnecessary before testing.

### Section 2: code quality, failures and maintainability

**E3 [P2, confidence 9/10] — context and immutable evidence reuse must be explicit.**
Current envelope calls `_frozen` (engine.py:319) and `_resolve_item` may call `_context`,
which calls `_frozen` again (engine.py:221). Current delivery constructs the same
event twice: `journal.append(self.journal_event(event))` and
`journal.verify(receipt, expected=self.journal_event(event))` (engine.py:600–601).
Pass one command context and exact immutable-evidence memo explicitly; helper
signatures may accept context/connection but must not introduce cross-command state.
Reset the memo at every invocation and retain live mutable authority reads. Downside:
more explicit parameter threading, justified by demonstrated repeated work.

Use one root-block failure boundary for `_unit_context`, relevant input/dependency
verification and full audits, including KeyError/TypeError and storage failures.
Preserve concise worker-visible diagnostics and independently record the cause;
a SQL rollback or storage exception must not accidentally return success. Reuse
existing reference/canonical/compiler helpers; pure new token/codec parity helpers
belong in current config/SQL contract code and tests, not a source-specific engine.
Maintain the state/validation/architecture ASCII diagrams when those contracts change.

### Section 3: test review (all proposed branches)

Read the actual protocol, role, generated, expiry, dependency, recovery, zero-work,
compaction and installed-wheel tests named in [TEST-PLAN.md](TEST-PLAN.md). Their
happy/error coverage is useful, but all **28 new qualification areas need additions**;
none is claimed already qualified. The artifact contains the full execution/branch
diagram, branch-by-branch existing-test mappings, mandatory additions and failure
handling. No runtime LLM behavior changes, so no model eval suite applies.

```text
NEW CODE/CONTROL PATHS                   NEW OPERATOR FLOWS
initial/role/immutable routes Q01-Q05     setup and mode selection Q01,Q02,Q12 [→E2E]
raw-byte generated origin Q06-Q11        expansion/replay/crash Q06-Q11 [→E2E]
context/dependencies/memo Q12-Q17         relevant vs unrelated failure Q13,Q14 [→E2E]
journal/readiness/snapshot Q18-Q22        delivery and completion races Q18-Q22 [→E2E]
errors/timeouts/inventory Q23-Q25         recovery / >100-run inventory Q23-Q25 [→E2E]
upgrade/compaction/performance Q26-Q28    old/new install/drain Q26,Q27 [→E2E]
                                        complete-process scale Q28 [→E2E]
```

Coverage status: 0/28 newly proposed areas qualified by this review; 28/28 have an
explicit planned test and safe failure outcome. Existing baseline tests remain
baseline evidence (★★★ for role/lease/replay/error behavior), never a percentage
claim about future code. Every integrity and concurrency branch is an enablement
requirement; none is deferred to a cheaper mock-only follow-up. Unit/property tests
cover pure template/codec behavior; real PostgreSQL and subprocess tests prove
privileges, atomicity, race behavior and installed contract.

### Section 4: performance, memory and scaling

**E4 [P2, confidence 9/10] — LIMIT is not proof of bounded database work.**
The claim query contains `ORDER BY ordinal LIMIT :n` (engine.py:369), verifier query
filters `state='reported'` (engine.py:415), and pending delivery index is only
`journal_outbox(created_at)` (001_control.sql:50). These can return bounded rows
while scanning a reported/completed prefix or other runs' backlog. Reuse the exact
unit primary key and existing useful pending-work index; add only narrow query-
matched partial/composite indexes when EXPLAIN ANALYZE/BUFFERS at realistic mixes
shows the need. Candidate worker, verifier and per-run pending-delivery paths must
be measured separately; preserve contention/lease behavior. Downside: index write
and migration overhead, accepted only with actual plan and full-path evidence.

**E5 [P2, confidence 9/10] — readiness/status must not hide a new O(N) scan.**
Current status (engine.py:543) executes `SELECT state,count(*) AS count ... GROUP BY
state`; calling it on every cheap readiness poll would defeat that design. Use
index-supported existential readiness/seal/outbox queries in the gate; explicitly
count grouped status and final record_checks reconciliation costs in total-run
benchmarks, even when only one result row is returned. Compact columns avoid large
manifest/context materialization, exact memo identity avoids repeated ancestors,
and N/E/B plus contention are separately reported. A constant returned-row count
alone does not establish constant physical cost: B-tree traversal, candidate
contention and the relevant dependency closure remain real work.

Proposed runtime delivery scope is now existing engine/database/config/CLI, rules
CLI and one wrapper diagnostic, one new migration, related tests/harness/docs.
This exceeds eight files for justified contract proof, not multiple new services.
Full-process improvement and renewal/RSS gates remain acceptance proposals; no new
speed result has been produced during this review.

### Engineering failure-mode registry

| Path | Realistic failure | Test requirement | Handling / visibility | Critical gap disposition |
|---|---|---|---|---|
| Initial admission | Worker forges new-format context | Q01–Q05 restricted direct SQL | Refuse/root error; no new work | Blocks enablement until proof |
| Expansion | Verifier inserts unrelated children or replay repairs missing rows | Q06–Q11 | Raw-byte parity + compare-only replay; root blocks on relevant mismatch | Blocks enablement until proof |
| Hot context | Malformed descriptor / relevant object unavailable | Q12–Q15 | One root-block boundary, exact original reference | No silent fallback accepted |
| Dependencies | Shared ancestor repeatedly verified; deep DAG failure | Q16–Q17 | Exact immutable memo, bounded/iterative validation, clear error | Required tests, no deferred mock |
| Journal | Append commits but readback/ack is lost | Q18 | Retain pending intent, reconcile same envelope/id | Existing recovery reused plus new-context tests |
| Finalize | Scope changes / direct fake checks / concurrent block | Q19–Q22 | Coherent audit, trusted exact checks, sticky block and current SQL gate | Blocks enablement until proof |
| Timeout | Client sees no response after commit | Q23–Q24 | Outcome-unknown diagnostic; inspect/reconcile same identity | Explicit fault trials |
| Rollback | Tagged blocked run omitted by limit100 | Q25–Q26 | Authoritative count, compatibility proof; refuse old binary | Required release gate |
| Compaction | Trigger blocks authorized retention or worker deletes evidence | Q27 | State/owner invariant, preserved summary/receipt | Required restricted-role test |
| Performance | Bounded returned rows mask scanned rows/global materialization | Q28 | Explain/buffers and full-process trials; failed gate remains failed | No speed/activation claim without proof |

All 28 areas now have proposed test assertions and a visible safe outcome: zero
unaddressed **silent** critical gaps in the plan. This is not a statement that the
runtime has zero critical gaps. Admission/authority/closure safeguards remain
unimplemented and block per-unit activation.

### Additional engineering decisions (continuing the audit trail)

| # | Phase | Decision | Class | Principle | Reason | Alternative |
|---|---|---|---|---|---|---|
| 18 | Eng | Restrict tagged completion/recovery to same disjoint control submitter | Mechanical | P1/P5 | Runtime fake checks/direct resume undermine full-audit policy | Trust arbitrary runtime booleans |
| 19 | Eng | Sticky root block, exact final-check names, one coherent audit connection | Mechanical | P1 | Existing record_checks can erase blocked state; helper connections mix snapshots | False checks that reopen a blocked run |
| 20 | Eng | Raw-byte SQL generic parity plus bounded Python selected-child revalidation | Taste | P1/P4 | Refuse first-seal fabricated SQL children and retain execution-time single-compiler check | Python-only detect-before-child-work with operator-approved weaker insertion boundary |
| 21 | Eng | New immutable column; legacy overload rejects tagged runs; state-based compaction | Mechanical | P1/P3 | Preserve old code on untagged runs without opening new-format bypass | Drop old signature or caller-set trusted flag |
| 22 | Eng | Measure visited rows/buffers and readiness/status cost; add proven narrow indexes | Mechanical | P1/P5 | LIMIT and one-row COUNT do not prove bounded work | Return-count-only qualification |
| 23 | Eng | All 28 branch/failure areas get tests in the implementation; sequential delivery | Mechanical | P1/P4 | Shared core and authority dependencies prevent independent edit lanes | Parallel changes to same engine or mock-only acceptance |

### Engineering independent voices and consensus

**CLAUDE SUBAGENT (eng — independent review):** Actual fresh Claude CLI review
completed with six findings. Its first attempt exhausted a 12-turn read budget;
a single focused retry completed successfully (eight scoped read/search calls).
It identified direct completion/resume authority, replay insertion, the SQL-versus-
Python compiler tradeoff, snapshot/outbox/event cost, state-based compaction and
legacy overload compatibility. The primary reviewer separately inspected the actual
generated tests which this voice explicitly did not read; no test coverage is
attributed to that voice beyond its reported evidence.

**CODEX SAYS (eng — architecture challenge):** Actual final Codex review completed
with six static findings: inconsistent lock order/upgrade, missing resource-checkpoint
route binding, weaker retained-report validation, a newer block erased by stale
resume, historical lease scans and old-migrator grant damage. Each is amended in
the preceding final engineering contract and assigned tests below. These are code-
grounded risks and future qualification obligations, not newly reproduced exploits.

| Dimension | Claude | Codex | Consensus |
|---|---|---|---|
| Architecture | Prefer single Python compiler with detect-before-work | Strong SQL boundary viable if qualified; add full route/lock contract | DISAGREE on origin boundary (choice20) |
| Tests | Direct calls/snapshots/compatibility need additions | Add lock, route, evidence, resume-generation, historical-lease cases | CONFIRMED |
| Performance | Outbox/readiness/events must be bounded | Include lease/history/lock/physical-query costs | CONFIRMED |
| Security | Fake checks/direct resume and fabricated child routes exposed | Checkpoint and retained-report routes must also bind frozen work | CONFIRMED |
| Errors | Sticky block and visible failures | Stale authorized resume needs generation guard | CONFIRMED |
| Upgrade | Legacy signature and separate format column | Keep new admin executable; old migrator can damage grants | CONFIRMED |

Consensus 5/6 refers to concern direction, not implementation passing. No user
challenge is asserted: both voices support fixing P2; they disagree on an assistant-
proposed design choice, not an explicit operator direction. Seven total taste choices
travel to the final gate. Stronger generated insertion authority remains recommended;
Python-only pre-execution checking is a viable alternative requiring a stated policy
change, and reduces duplicated compiler maintenance.

### Final engineering decisions (continuing the audit trail)

| # | Phase | Decision | Class | Principle | Reason | Alternative |
|---|---|---|---|---|---|---|
| 24 | Eng | Frozen-cursor SQL dispatch and exact checkpoint binding; deferred seal | Mechanical | P1 | Public wrong routes bypass Bookkeeping checkpoint/seal invariants | Python chooses route but direct SQL omits it |
| 25 | Eng | Shared exact retained-report validator at admission/use/audit | Mechanical | P1/P4 | Current historical validator trusts stored booleans and partial binding | Freeze unauthenticated receipt/check pairs |
| 26 | Eng | Recovery block-generation compare-and-swap, distinct from worklist revision | Mechanical | P1/P5 | Authorized stale resume can clear a newer block | Hold run lock during slow artifact recovery audit |
| 27 | Eng | Consistent run→work→sorted-lease locks, no run-lock upgrades | Mechanical | P1 | Release/completion and first-report lock cycles are code-grounded | Retry avoidable deadlocks indefinitely |
| 28 | Eng | Include historical lease scans and old-admin grant damage in qualification | Mechanical | P1 | Worklist removal alone misses cost and rollback hazards | Only inspect active work and old runtime binary |

### Engineering implementation tasks and completion summary

T2 covers all admitted-definition routes, completion dispatch, exact report binding,
control principal grants, recovery generation and immutable state guards. T4 covers
coherent readiness/final audits, sticky blocks and recovery/finalization races. T5
covers physical query/lock/lease/history/outbox/dependency/full-process evidence.
T6 covers the existing CLI/wrapper contracts and new administration preflight. These
extend the same tasks, rather than create a competing change to the same engine.

- [ ] T2: Implement complete restricted-route/definition/report/recovery contract;
  real SQL direct-call, membership, first-seal and replay acceptance required.
- [ ] T4: Pass the full snapshot/closure/stale-resume/blocked-finalize race matrix.
- [ ] T5: Qualify indexed candidates/leases/outbox and complete process value gates.

Completion summary: Step0 scope accepted A→B→C, complexity addressed without new
services. Architecture: E1/E2 plus six outside-voice amendments; code quality: E3
and shared validator/root error boundary; tests: complete diagram and 28 qualification
areas specified; performance: E4/E5 plus historical lease/lock/startup obligations.
NOT-in-scope and existing-code map written. Three deferred TODOs were recorded at
engineering review; two added during sync/coordination bring the final total to five. Zero
unaddressed silent critical plan gaps; authority/origin/concurrency qualification
is still required before activation. Both independent voices ran. Sequential work;
no parallel source lane. Lake Score: all 28 recorded recommendations select the
complete in-scope solution or explicitly defer unrelated expansion.

Suppressed findings: no speculative framework/field claim is promoted. A separate
fourth controller credential was rejected because the same disjoint control
submitter can own audited recovery/completion. Timer service, Merkle tree, a new
finalizing state and automatic old-run conversion remain excluded. Native hash
support is documentation-confirmed; codec/compiler parity is unqualified.

## Synchronization and final engineering compatibility check

Operator requested live Codex sync and rebase before continuation. Fetched current
main `bebebcb2`, examined all worktrees and relevant Codex PRs933/937/938 (merged),
and found zero open PRs at the inspected snapshot. Root main remains stale/dirty
and untouched; its old fix-pipelines state is not a live work selector. Dedicated
branch retained the recovery ref `codex/bookkeeping-p2-autoplan-pre-sync-20261013-2050`
at `b28a33a2`; clean rebase/fetch and range-diff verified all six own commits unchanged.
At validation, origin/main...HEAD was 0 behind/6 ahead. No other runtime branch was
rebased, staged, committed or pushed. Current main includes PR958 ordinal and
confirm/sample behavior plus PR959 status reconciliation.

Engineering reviewed this final upstream delta last. Fresh Claude and then Codex
CLI voices each completed with three acceptance gaps: explicit generated-offset
sampling expectations, sample-proof preservation/assertions, and reduction in the
installed matrix. All are added above and in Q12/Q18/Q26/Q28. Claude's claim of a
separate reduction profile was suppressed after direct code read: reduction is an
operation under existing source.combine. Its suggested control-side sample schema
was rejected to preserve control-only ownership; worker tests own the semantics,
while Bookkeeping authenticates report/proof references. This is a mechanical scope
correction, not an operator-approved sampling-policy redesign.

The first rebased local check had 72 passes and eight failures because the reused
source-contract binary lacked combine_tables/Reduction. Built current Rust source
into an isolated abi3 wheel/target (release build 4m11s), checked the native APIs,
and reran the exact same three-file command through a transient uv overlay:
**80 passed in 9.89s**. Shared .venv stayed unchanged. Historical command with
machine-local environment/wheel paths parameterized:
`PYTHONPATH="$PWD" UV_PROJECT_ENVIRONMENT="$PREPARED_VENV"
uv run --no-sync --with "$SOURCE_CONTRACT_WHEEL"
pytest -q tests/engine/test_check_confirms.py tests/unit/test_configured_bookkeeping_contract.py
tests/architecture/test_bookkeeping_control_only.py`.
This is current baseline/compatibility evidence, not qualification of unimplemented
P2 migrations or a measured speedup. Earlier PostgreSQL research results retain
their original baseline/date; no new full PostgreSQL acceptance is claimed.

| # | Phase | Decision | Class | Principle | Reason | Alternative |
|---|---|---|---|---|---|---|
| 29 | Sync | Preserve upstream ordinal, confirm/reduction/streamed branches and opaque sample proofs | Mechanical | P1/P3/P4 | Rebase must retain current contracts and match verifier policy in benchmarks | Recreate older envelope or force all domain work to redo |
| 30 | Sync | Preserve nonzero generated-offset sampling; defer first-unit wording clarification | Mechanical | P3 | Existing ambiguity is independent of P2; no authority to silently change policy | Reset ordinals or redesign sampling in control |

Final delta architecture: existing boundaries intact; code quality: no domain-policy
logic enters Bookkeeping; test review: installed and proof/ordinal branches specified;
performance: same verifier policy/build plus observed branch counts. Both delta voices
agree on compatibility direction (four section dimensions), after the explicit
reduction-profile correction. The original Eng 5/6 consensus and choice20 remain.

Refreshed per-phase task artifacts retain original review provenance and are rebound
to the verified rebased branch for aggregation; they do not claim CEO/DX were rerun
or their original raw measurements refreshed. The 28-area test matrix and its latest
external artifact include the upstream delta requirements.

## Claude limit-removal coordination and operator ruling

Read-only active worktree inventory and fresh Claude consultation completed. Code
paths checked: Claude-owned mdm/clean/{limits,merge,store}.py, migration019 and
Ticket74/living-doc edits. Codex source/planning ownership remains separate. The
operator explicitly chose current MDM scope, resolving the broader-cap question.
Bookkeeping has no new total-work refusal; current protocol boundaries stay unchanged.
Future hosted capacity requires measured provider-specific qualification, with no
local-Mac-derived SQL rejection. A future uncapped Bookkeeping expansion is deferred
by this scope ruling, not silently substituted for P2.

| # | Phase | Decision | Class | Principle | Reason | Alternative |
|---|---|---|---|---|---|---|
| 31 | Coordination | Follow Claude's current MDM-only removal of Merge Stage size refusals | User-confirmed | Operator ruling/P3 | Explicit 2026-10-14 scope answer; preserve ownership and hosted-capacity intent | Remove Bookkeeping128/control-document caps in this plan |

Decision accounting: 31 total, 23 mechanical auto-decisions, seven taste
recommendations accepted at the final A gate, one operator-confirmed scope ruling,
zero user-direction challenges. Claude's unused broader recommendation remains
visible in the archived consult; no claim of active-session messaging is made.

## GSTACK REVIEW REPORT

VERDICT: **APPROVED — review ticket complete.** Operator selected A at 2026-10-14 07:40 ET.
Approval base `bebebcb2`; rebased dedicated Codex worktree, recovery branch retained.
This is a review/qualification plan. Runtime implementation and deployment remain
unstarted; no P2 speedup or hosted qualification is claimed.

| Review | Trigger / reason | Runs | Status | Findings / evidence |
|---|---|---|---|---|
| CEO | User invoked autoplan on researched P2 fix | Full ten sections, Claude→Codex + independent spec pass | Complete; all seven cross-phase taste choices accepted | Six concerns per voice;5/6 consensus; spec9/10 |
| UI design | No visual/user-interface change | Skipped by scope | Not applicable | CLI/control platform only |
| DX | CLI/roles/setup/recovery affected | Full eight passes, Claude→Codex | Complete; plan8.5/10, execution proof pending | Five concerns per voice;6/6 consensus; TTHW target<5min prepared, unmeasured |
| Engineering | Required final review of amended plan | Four full sections, Claude→Codex, post-rebase delta Claude→Codex | Complete; plan8.5/10; admission/closure gates unimplemented | Six concerns per original voice;5/6 consensus; delta three gaps per voice resolved |
| Coordination | Operator requested Codex/main sync and Claude limit check | Live refs/PR/worktrees, clean rebase/range-diff, fresh Opus consultation | Complete; explicit MDM-only scope recorded | All six own commits preserved; Claude Ticket74 branch read; broader proposal deferred |
| Verification | Current baseline and plan artifact integrity | Exact three-file suite via isolated native-wheel overlay; ownership/diff/links/task checks |80 tests passed in9.89s; plan checks complete | Native release build4m11s; no P2 migration tests/speed results claimed |
| Publication verification | Main67cedee4 merged; research/planning-only diff | Independent completion audit15/15; Claude pre-landing re-review clear; artifact checks and wheel build passed | Fresh scoped `--testmon`:80 passed in65.04s; nine local links resolve | Broad unit/architecture run interrupted after908 passes; two retry shards hit285-second deadlines; full-suite success is not claimed |

Decision accounting: **31 total:23 mechanical auto-decisions,7 operator-accepted taste recommendations,
1 operator-confirmed scope ruling;0 user-direction challenges.** The Decision Audit
Trail above contains all decisions; task aggregation produced seven exact-deduped
tasks with original review provenance retained after rebase.

Cross-phase themes: initial/generated/completion authority must be real; retained
artifact/report evidence stays authenticated; recovery and closed-scope completion
need concurrency proof; full-process value must include database visits, startup,
leases, dependencies and backlog. Independent repeated concerns are resolved in the
plan and remain mandatory implementation evidence, not current runtime guarantees.

Artifacts: [test matrix and commands](TEST-PLAN.md),
[seven implementation tasks with exact files/dual effort estimates](IMPLEMENTATION-TASKS.md),
[ticket checklist](TICKET.md), original research linked at the top and external
restore/voice/test-plan/task JSONL artifacts saved in the project gstack directory.
Deferred in TODOS.md: P1 destination authority; P1 runtime fingerprint; P3 long-run
full-audit cadence; P2 generated-first-unit sampling clarification; P3 future uncapped
Bookkeeping protocol after explicit operator scope change. None is claimed repaired.

Final disposition: operator approved the complete staged A→B→C plan as-is at
2026-10-14 07:40 ET, including choices3/5/6/7/10/14/20. Current Bookkeeping bounds and
Claude's operator-confirmed MDM-only refusal removal remain accepted. Decision31
was separately answered and is unchanged. Every part of the review ticket is
checked; implementation tasks remain unstarted.

Approval evidence: user reply `A` to D1, “Approve this reviewed plan?” No overrides
were requested. The clean review logs bind to the approval checkpoint and identify
their scope as plan-only; they do not qualify runtime changes or deployment.

**UNRESOLVED DECISIONS:**

NO UNRESOLVED DECISIONS
