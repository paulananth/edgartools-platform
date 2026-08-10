Type: research
Status: resolved

## Question

9 of the platform's 26 deployed state machines have zero executions ever
(`bootstrap_full`, `full_reconcile`, `load_daily_form_index_for_date`,
`catch_up_daily_form_index`, `bootstrap_batched`, `mdm_gold`,
`silver_mdm_gold`, `mdm_seed_universe`, `mdm_seed_from_silver` -- confirmed
live via `aws stepfunctions list-executions --max-results 1000` per
machine, 2026-08-04). Zero-executions is evidence of disuse, not proof of
deadness on its own.

For each of the 9, determine: is it (a) genuinely obsolete -- superseded by
another machine, built for a use case that no longer applies, or a
leftover from an earlier architecture -- or (b) intentionally-provisioned
tooling for a scenario that simply hasn't happened yet (disaster recovery,
a specific backfill shape, an escape hatch)? Check: git history/commit
messages for when/why each was added, CLAUDE.md and other docs for any
reference to its intended use, whether its Step Functions definition still
generates valid/current JSON (an orphaned generator would be a stronger
deadness signal), and whether anything else in the repo (scripts, other
state machines, runbooks) references or depends on it existing.

Resolve with a per-machine verdict (dead / intentionally dormant /
uncertain) before ticket 02's consolidation decision or any deletion work
proceeds -- deleting an intentionally-dormant disaster-recovery tool would
be a real loss, not just cleanup.

## Answer

Method: for each machine, checked (1) git history of its ASL-generating
function in `infra/scripts/deploy-aws-application.sh` (`git log -S`), (2)
CLAUDE.md / `docs/data-architecture.md` / `docs/project-overview.md` for
documented intent, (3) whether the generator still produces valid/current
JSON (ran `tests/architecture/test_sec_fetch_lease_single_workflow_wiring.py`
+ `test_load_history_state_machine.py` live -- 58/58 passed, confirming
`bootstrap_full`/`full_reconcile`/`load_daily_form_index_for_date`/
`catch_up_daily_form_index`/`load_history`'s generators are exercised and
correct today), (4) cross-references elsewhere in the repo, (5) live AWS
state (`describe-state-machine`, fresh `list-executions` re-check, and
`list-rules`/`list-schedules` for EventBridge/Scheduler targeting).

All 26 machine names were re-confirmed via `aws stepfunctions
list-state-machines` (hyphenated, `edgartools-prod-*` -- matches the
ticket's underscore shorthand 1:1, e.g. `bootstrap_full` ->
`edgartools-prod-bootstrap-full`). All 9 re-checked live on 2026-08-10:
still **0 executions each**, all `status: ACTIVE`, all `creationDate:
2026-07-04` (the current prod account's cutover date -- i.e. these are
fresh redeploys of the same logical machines, not stale artifacts from a
different account). `aws events list-rules` (region us-east-1) returns
only `StepFunctionsGetEventsForECSTaskRule` (an internal SFN->ECS event
rule) -- **zero** EventBridge rules target any of the 9, and `aws
scheduler list-schedules` returns zero schedules. So none of the 9 has a
dormant-but-wired scheduled trigger; every one is purely operator-invoked
if invoked at all.

### 1. `bootstrap_full` -- **intentionally dormant**

- Origin: the very first commit that added `deploy-aws-application.sh` at
  all (`0751c8c1`, "separate infrastructure access control", 2026-05-02)
  already included `bootstrap_full` in the workflow loop, alongside
  `daily_incremental`, `bootstrap` (then `bootstrap_recent_10`),
  `targeted_resync`, `full_reconcile`, `load_daily_form_index_for_date`,
  and `catch_up_daily_form_index` -- provisioned as one symmetric set of
  operator entry points from day one, not accreted later as a leftover.
- CLI command `bootstrap-full` ("Load full filing history for tracked
  companies", no `--recent-limit`) is fully implemented
  (`edgar_warehouse/application/commands/bootstrap_full.py` ->
  `bronze_submissions_ingest.run_bootstrap_full`) and documented in
  `docs/project-overview.md`'s "Common operator commands" table and
  `docs/data-architecture.md`'s "Submissions bootstrap" row (status:
  Automated).
  `load_history`'s Stage 1 uses a *different* command
  (`bootstrap-next --silver-only`, windowed) -- `bootstrap-full` is not a
  literal duplicate of what `load_history` calls, it's the unwindowed,
  single-shot ancestor primitive, still wired up separately.
- **Actively maintained as of 6 days before this investigation**: commit
  `0344a598` (2026-08-04, "feat(sec-fetch-lease): wire cross-command lease
  into all 5 SEC-fetching state machines (#349)") explicitly named
  `bootstrap_full` as one of "the 5 SEC-fetching commands" and added new
  `AcquireSecFetchLease`/`ReleaseSecFetchLease` states to its generator
  (`write_single_workflow_definition`), with dedicated tests
  (`test_bootstrap_full_acquires_lease_before_run_and_releases_before_end`,
  `test_bootstrap_full_run_warehouse_task_releases_lease_on_failure`,
  `test_bootstrap_full_no_operator_notification`) -- all passing live.
  The commit body explicitly reasons about "how these commands are already
  operated (no auto-retry exists for their failures either)" -- language
  that presumes real, if infrequent, operator use.
- Not in CLAUDE.md's condensed "When to use what" table (which recommends
  `load_history` for 10+ companies) -- the only real ambiguity signal, but
  outweighed by the above: this reads as "load_history is the default
  path," not "bootstrap_full is retired."
- **Verdict: intentionally dormant.** A real, distinct, currently-generating,
  recently-touched ad-hoc full-history loader; zero executions so far in
  this ~5-week-old prod account simply because nobody has needed an
  unwindowed full-history run yet.

### 2. `full_reconcile` -- **intentionally dormant**

- Same origin commit (`0751c8c1`, 2026-05-02) as `bootstrap_full`.
- Explicitly documented in `docs/data-architecture.md`'s "Reconciliation
  and repair" row: status **Manual/backfill-only**, entry points
  `full-reconcile`, `targeted-resync` -- "checks SEC drift... Own
  standalone Step Functions (`targeted_resync`), not chained into the main
  load/incremental pipelines." `docs/data-architecture-issues.md` Issue 11
  independently confirms `full-reconcile` is a real, scoped tool (upstream
  bronze-vs-SEC drift only) whose *known gap* is lacking downstream
  quality checks -- a scoping note, not a deadness signal.
  `targeted_resync` (the machine that *acts on* findings `full_reconcile`
  would produce) does have live executions -- it is not in the
  zero-execution list -- so the pair is asymmetric: repairs have happened,
  but the comprehensive drift-scan that would normally surface what to
  repair hasn't been run as a discrete step (operators may have found
  issues via other means, e.g. CloudWatch/manual query).
- Explicitly enumerated in the 2026-08-04 `0344a598` commit among the "5
  SEC-fetching state machines" under consideration for the lease, and
  deliberately left *unwrapped* ("full_reconcile... don't call SEC at
  meaningful volume and stay unwrapped") -- a considered decision, not an
  oversight.
- Also touched by `4760be81` (2026-07-30, "fix(infra): raise large task
  memory to 8192MB, move gold-affecting commands onto it") -- moved onto
  the `large` task profile alongside `daily_incremental`/`bootstrap`/
  `gold_refresh`, i.e. actively kept correctly-sized 11 days before this
  investigation.
- **Verdict: intentionally dormant.** A real, current, "Manual/backfill-only"
  by design repair tool that has genuinely not been needed yet.

### 3. `load_daily_form_index_for_date` -- **intentionally dormant**

- Same origin commit (`0751c8c1`, 2026-05-02). CLI command fully
  implemented (`bronze_daily_index_ingest.run_load_daily_form_index_for_date`,
  dispatched in `cli.py`) -- "Load one SEC daily form index by business
  date," with `target_date` positional arg and `--force`.
- Documented in `docs/data-architecture.md`'s "Daily incremental" row
  (status: Automated) alongside `daily-incremental` and
  `catch-up-daily-form-index` -- a single-date backfill/repair primitive,
  distinct from `daily-incremental`'s live-date processing.
- Enumerated among the same "5 SEC-fetching machines" set in the
  2026-08-04 lease commit, deliberately left unwrapped for the same "not
  meaningful SEC volume" reason as `full_reconcile`.
- No EventBridge rule or Scheduler schedule targets it (confirmed live,
  see Method above) -- matches its designed role as an operator-run,
  single-date escape hatch rather than a background job.
- **Verdict: intentionally dormant.** A per-date repair tool for a scenario
  (one day's SEC daily index came back bad/missing) that apparently
  hasn't occurred yet against this prod account.

### 4. `catch_up_daily_form_index` -- **intentionally dormant**

- Same origin commit, same CLI module (`run_catch_up_daily_form_index`) --
  "Load missing SEC daily form indexes up to an optional end date," the
  sibling catch-up-sweep to #3's single-date reload.
- `daily_incremental` itself is **not** in the zero-execution list (it has
  run), but its own recurring EventBridge schedule is confirmed live to be
  currently **off**: `deploy-aws-application.sh`'s
  `--configure-daily-incremental-schedule` flag is explicitly documented
  as "Off-by-default operator control (release-readiness ticket 45/49)",
  and `aws events list-rules` shows zero `edgartools-*` rules exist right
  now. `catch_up_daily_form_index` is exactly the tool an operator reaches
  for once that schedule resumes and a gap is found (or after any other
  daily-index outage) -- its zero-execution count is consistent with "the
  gap scenario it exists for hasn't happened (or the schedule hasn't been
  running long enough to gap)," not obsolescence.
- **Verdict: intentionally dormant.**

### 5. `bootstrap_batched` -- **dead (superseded)**

- Same origin commit (`0751c8c1`, 2026-05-02): a `BatchBootstrap`
  `Map`/`DISTRIBUTED` state over `cik_batches.jsonl`
  (`write_bootstrap_batched_definition`), fetching new SEC submissions in
  real parallel batches (`MaxConcurrency` from `BOOTSTRAP_BATCH_CONCURRENCY`).
- **Directly superseded**, in the generator code's own words: commit
  `cb3fcdeb` (2026-05-11, "feat: phased pipeline -- bronze parallel, MDM
  bulk, gold once" -- this is the CLAUDE.md "Long-load 5-whys" fix)
  introduced `write_load_history_definition` with the comment: *"Replaces
  the original DISTRIBUTED Map over cik_batches.jsonl with an INLINE Map
  (MaxConcurrency=1) over cik_windows.jsonl written by compute-windows.
  Sequential windows ensure silver.duckdb is consistent at each step."*
  This is the exact same `cik_batches.jsonl` artifact `bootstrap_batched`
  still reads -- i.e. `load_history`'s sequential-window architecture was
  built specifically to fix a real consistency defect
  (concurrent-writer race on `silver.duckdb`) inherent to
  `bootstrap_batched`'s design, not just to add unrelated features.
- CLAUDE.md's own Phased Pipeline section independently confirms this
  machine "is not part of `load_history`'s call graph at all, and as of
  this writing has zero executions ever in prod... Treat it as
  deployed-but-unverified infrastructure, not an active throughput lever,
  until someone actually runs it." Not present in CLAUDE.md's "When to
  use what" table. No other script or state machine references it.
  (Distinct from `bootstrap-batch` the *command*, which is still very much
  alive -- used by `silver_mdm_gold`'s/`bronze_seed_silver_gold`'s
  `BatchSilver` Map at `MaxConcurrency=3` with `--artifact-policy skip`;
  that's a different, newer, deliberately no-new-SEC-calls pipeline, not
  this machine.)
- **Verdict: dead.** Superseded by `load_history`, which was built
  specifically to fix a data-consistency bug in this machine's own
  architecture. It is a leftover from the pre-`load_history` era, kept
  deployed (its generator still runs and produces valid JSON) but not
  removed, and should not be treated as a throughput lever or fallback.

### 6. `mdm_gold` -- **intentionally dormant**

- Introduced 2026-05-14 (`963c2c76`, "feat: mdm_gold state machine -- MDM
  chain + Neo4j + gold-refresh without silver batch").
- Documented in `docs/data-architecture.md`'s orchestration table: `MDM
  chain -> gold-refresh; no bronze/silver capture step` -- a distinct,
  real use case: rebuild MDM entity resolution + graph sync + gold tables
  without touching bronze/silver at all (e.g. after an MDM-only code fix,
  with no need to re-fetch or re-process any SEC data).
- Shares `write_warehouse_mdm_gold_definition` (the MDM-chain-building
  code) with `daily_incremental`/`bootstrap`, which was actively modified
  as recently as `995856c7` (2026-08-08, "Stage 14 cutover fixes -- OOM,
  promotion races, cache-hit parallelization, ADV shard data-loss (#368)")
  and `b64f1de5`/`071db87b` (2026-08-08, "implement shard-aware batch
  scheduling (ticket 12)") -- 2 days before this investigation.
- **Verdict: intentionally dormant.** A genuine "MDM/gold-only rebuild"
  escape hatch; unneeded so far because `load_history`/`silver_mdm_gold`/
  `bronze_seed_silver_gold` have covered actual operational needs to date.

### 7. `silver_mdm_gold` -- **intentionally dormant** (strongest case of the 9)

- Introduced 2026-05-14 (`f3c8be82`, "feat: silver_mdm_gold pipeline --
  reprocess already-loaded bronze"), with a same-week correctness fix
  (`8f5243a1`, 2026-05-15, "fix: silver_mdm_gold must pass
  --artifact-policy skip (5-why)") whose invariant is still enforced and
  documented today in CLAUDE.md's "Key invariants" section.
- Documented in `docs/data-architecture.md`: "Seed from existing silver ->
  cached `bootstrap-batch` -> MDM chain -> `gold-refresh`; intended for
  zero new SEC calls when policies skip artifact/parser work," and again
  under "Silver shard migration and cached replays" as
  Manual/backfill-only, "Operator-triggered recovery/replay tools, run on
  demand."
- **By far the most actively-maintained machine of the 9**: touched by
  `e23db3e1` (2026-08-08, "lower bronze_seed_silver_gold's BatchSilver to
  MaxConcurrency=2"), `995856c7` (2026-08-08, Stage 14 cutover fixes),
  `071db87b`/`b64f1de5` (2026-08-08, shard-aware batch scheduling ticket
  12), and `b1a1f3d9` (**2026-08-10, today** -- "refactor(warehouse): fold
  Stage0CompanyIdentity into Stage1's WindowedBootstrap") -- all modifying
  the `BatchSilver`/`bootstrap-batch` machinery this exact state machine
  depends on, with the most recent change landing the same day as this
  investigation.
- **Verdict: intentionally dormant.** Real, current, and under active
  engineering investment; zero executions only because nobody has yet
  needed a full no-new-SEC-calls reprocess of already-loaded bronze in
  this prod account's short life so far.

### 8. `mdm_seed_universe` (standalone SFN) -- **uncertain**

- Introduced 2026-05-04 (`957a8b45`, "feat(aws): close MDM E2E gaps for
  seed-universe in AWS"), whose *sole stated purpose* was giving this ECS
  task a way to reach MDM's then-AWS-RDS-hosted Postgres from inside the
  VPC: the same commit added `bootstrap-aws-mdm-secrets.sh`, described as
  reading "the AWS-managed RDS master user secret produced by Terraform."
- CLAUDE.md's "MDM database" note confirms MDM Postgres has since **moved
  off AWS RDS onto Snowflake's native Postgres service** (Snowflake
  Postgres, reachable over HTTPS, not VPC-gated) -- the original technical
  reason this needed to be a dedicated AWS Step Function no longer holds,
  though nobody has re-verified whether `mdm seed-universe` can now simply
  be run locally instead (CLAUDE.md says as much: "Local reachability to
  the current Snowflake-hosted instance has not been re-verified").
- The identical underlying operation (`mdm seed-universe --tracking-status
  bootstrap_pending`) is also invoked as an **inline** `MdmSeedUniverse`
  ECS-task state inside `load_history`'s own composed graph (confirmed:
  `mdm_seed_universe = ecs_state(...)`, wired in at `"MdmSeedUniverse":
  mdm_seed_universe` in `write_load_history_definition`) -- so the
  operational need itself (seed MDM's tracked universe) is being met
  continuously through `load_history`; only *this specific standalone,
  independently-parameterized* (`--tracking-status`/`--limit` override)
  entry point sits unused.
- Still listed in `docs/data-architecture.md`'s "MDM utility workflows"
  row alongside the other 8 standalone MDM machines, undifferentiated.
- **Verdict: uncertain.** Plausibly a legitimate standalone debug/limit-override
  tool (leans toward intentionally-dormant), but its founding
  VPC/RDS-access rationale is stale post-migration, it's functionally
  redundant with `load_history`'s built-in step for the common case, and
  nobody appears to have revisited whether it should still exist as a
  standalone AWS entry point since the Postgres migration.

### 9. `mdm_seed_from_silver` (standalone SFN) -- **uncertain, leaning obsolete**

- Introduced 2026-05-10 (`4031f342`, "feat: add mdm_seed_from_silver Step
  Functions workflow"), whose commit message states the **entire**
  rationale explicitly: *"Wire 'edgar-warehouse mdm seed-from-silver' into
  the MDM Step Functions pipeline so the silver -> MDM Postgres migration
  can run inside the VPC where RDS is accessible."* This is the identical
  RDS-access rationale as #8, now stale for the identical reason (MDM
  Postgres is Snowflake-hosted, not VPC-gated RDS, per CLAUDE.md's "MDM
  database" note).
- Unlike `mdm_seed_universe`, **no other composed machine invokes this
  command inline** -- grepped the whole generator file for an
  `MdmSeedFromSilver`-shaped inline state the way `MdmSeedUniverse` exists
  for #8; none found. This standalone SFN is the *only* orchestrated path
  to `mdm seed-from-silver` today.
- The CLI command itself remains fully implemented and non-dead
  (`edgar_warehouse/mdm/cli.py::_handle_seed_from_silver`, sharing
  `_seed_mdm_from_silver`'s core logic with `seed-universe`) and is listed
  in `docs/data-architecture.md`'s "MDM utility workflows" row -- so this
  is a question about whether *this specific AWS wrapper* is still
  needed, not whether the underlying capability is dead.
- **Verdict: uncertain, leaning obsolete.** Its sole documented reason for
  existing as a *standalone AWS Step Function* (VPC-only access to RDS) no
  longer applies now that MDM Postgres is Snowflake-hosted, and -- unlike
  #8 -- nothing else in the repo depends on or duplicates it. No one has
  made an explicit decision to keep or retire it since the underlying
  infrastructure it was built to work around was replaced.

### Summary tally

**6 intentionally dormant** (`bootstrap_full`, `full_reconcile`,
`load_daily_form_index_for_date`, `catch_up_daily_form_index`, `mdm_gold`,
`silver_mdm_gold`) -- real, current, in several cases very recently
(within days of this investigation, one on the same day) actively
engineered tooling for scenarios (ad-hoc full loads, drift repair,
single-date/catch-up daily-index reload, MDM/gold-only rebuild, no-new-SEC
reprocess) that simply haven't come up yet in this ~5-week-old prod
account. **1 dead** (`bootstrap_batched`) -- explicitly superseded by
`load_history`, whose own code comment documents that it was built to fix
a data-consistency defect in `bootstrap_batched`'s architecture; safe to
treat as a pure leftover. **2 uncertain** (`mdm_seed_universe`,
`mdm_seed_from_silver`) -- both standalone MDM machines whose sole
original justification (AWS-VPC-only access to a since-migrated-off-RDS
MDM Postgres) is now stale, but neither has had an explicit
keep-or-retire decision made; `mdm_seed_universe` leans dormant-but-intentional
(its underlying operation is still actively used, just via `load_history`'s
inline step rather than this standalone entry point), while
`mdm_seed_from_silver` leans closer to obsolete (nothing else in the repo
uses or depends on it, and its founding rationale is fully moot). Ticket
02's consolidation decision should treat the 6 intentionally-dormant
machines as out of scope for deletion, `bootstrap_batched` as a safe
removal candidate, and flag the 2 uncertain MDM machines for an explicit
keep/retire decision (likely: fold into ticket 02's MDM-tail
consolidation if kept, since they're single-stage MDM machines already in
scope alongside `mdm_run`/`mdm_backfill_relationships`/etc.).
