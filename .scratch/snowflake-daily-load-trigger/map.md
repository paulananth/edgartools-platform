# Snowflake Daily Load Trigger

Label: `wayfinder:map`

## Destination

An implementation-ready design so the Snowflake gold/manifest load fires
**once per day, event-driven off pipeline completion** instead of on
today's fixed 6-hour blind poll (`SNOWFLAKE_RUN_MANIFEST_TASK`'s
`schedule { minutes = 360 }`, `infra/terraform/snowflake/modules/
native_pull/main.tf:749`). Reaching the end of this map means someone can
build without hitting an undecided question: the idle-detection mechanism
and its race safety, the once-per-day debounce/cap semantics, how the
trigger actually invokes Snowflake and what happens to the existing task/
stream/schedule object, and the dead-man's-switch alarm that replaces the
poll's implicit "eventually checks again" safety net — are all settled.

**Status: design complete.** An Opus design-review pass after tickets
01-03 first closed found the map wasn't actually done yet — see
[DESIGN-SUMMARY.md](DESIGN-SUMMARY.md) for that synthesis, consistency
check, and gap list (tickets 05-07 + the G6/G7 addenda on tickets 02/03
all trace back to it). All 8 decision tickets are now resolved,
including 04 (the alarm), which was the last one still open. Nothing
left to decide before implementation.

## Notes

- Grounding, already established via this session's grilling — do not
  re-derive:
  - **`sec_fetch_active` cannot be reused as the completion signal.**
    Verified live in `infra/scripts/deploy-aws-application.sh:3182-3196`:
    the lease is released *right before* `MdmRun`/`GoldRefresh` even
    start ("MDM/gold never call SEC"), so a free lease means no
    SEC-fetch-heavy phase is active — it says nothing about whether gold
    has been rebuilt. The real signal has to be the parent Step Functions
    **execution** reaching a terminal state.
  - **Watched set = gold-affecting state machines, not all 26** —
    verification/connectivity utilities (`mdm-verify-graph`, etc.) never
    produce new gold data, so waiting on them would only delay the trigger
    for no reason. **Corrected and mechanically verified by
    [Ticket 05](issues/05-derive-correct-watched-state-machine-set.md):**
    the true set is **11**, not the originally-claimed 7 —
    `daily_incremental`, `load_history`, `bootstrap`, `bootstrap_full`,
    `targeted_resync`, `full_reconcile`, `silver_mdm_gold`, plus
    `gold_refresh`, `mdm_gold`, `ownership_mdm_gold`,
    `bronze_seed_silver_gold`. The original 7 came from hand-mapping
    `GOLD_AFFECTING_COMMANDS` (a command-level set) onto state-machine
    names; the correct derivation traces every `upsert_state_machine` call
    in `deploy-aws-application.sh` and checks each one's generated ASL for
    a `gold-refresh` ECS state. Ticket 05 also decided this should be
    derived mechanically at deploy time going forward (grep the generated
    JSON), not hand-maintained as a list — so the same drift can't recur.
  - **Detection is event-driven**, not another poll: an EventBridge rule
    on Step Functions execution-status-change events (SUCCEEDED/FAILED/
    ABORTED/TIMED_OUT) for the watched set, feeding a re-check of whether
    anything else in the watched set is still `RUNNING`.
  - **Invocation is a direct Snowflake connector call** (`CALL
    PROCESS_RUN_MANIFEST_STREAM()`), not `EXECUTE TASK` against the
    existing native task object — bypassing the task/stream scheduling
    mechanism entirely rather than nudging it.
  - **The 6-hour poll is replaced, not kept as a fallback load path** —
    but a dead-man's-switch **alarm** (alert-only, no fallback execution)
    is explicitly in scope, so a broken trigger surfaces to an operator
    instead of gold silently going stale forever. These aren't
    contradictory: no execution fallback, but yes observability fallback.
  - **Phase B's `backfill-mdm-entity-ids` sweep needs no separate
    signal.** Per the [MDM Entity Resolution Ahead of Silver](../mdm-ahead-of-silver/map.md)
    map's implementation (task #132, still pending as of this map's
    creation), the sweep is being wired *inside* `daily_incremental`'s own
    Stage 2 chain — the same execution this map already watches. Once
    that wiring lands, "the `daily_incremental` execution reached a
    terminal state" already implies the sweep ran too.
- **Cost context**: the 6h poll cadence itself was a deliberate
  credit-economy tradeoff from the `ecs-cost-sizing` workstream (see
  CLAUDE.md's "Gold-build memory" 5-whys and
  `.scratch/ecs-cost-sizing/issues/22-...md`) — widened from 1 min to
  avoid `EDGARTOOLS_PROD_REFRESH_WH` burning ~67 credits/week failing to
  suspend during active backfills. This map's event-driven design should
  keep that property (no wasted warehouse wake-ups) while also fixing the
  up-to-6h freshness lag the poll traded away.
  **Live-verified post-fix baseline (2026-08-16, $3/credit):** the 6h
  cadence has run cleanly (exact 6h intervals confirmed via
  `TASK_HISTORY`) since 2026-08-14 12:53, costing **~$1-2/day
  (~$30-60/month)** in that clean window — the map's earlier ~67
  credits/week figure describes the *pre-fix* incident, not current
  steady state. Separately, found via live `QUERY_HISTORY` that
  `REFRESH_AFTER_LOAD` unconditionally refreshes all ~24 gold tables per
  manifest row (6,435 calls against 1,009 `PROCESS_RUN_MANIFEST_STREAM`
  invocations over 30 days) — a real inefficiency, but one paid
  identically under the old poll and this map's new trigger alike (both
  call it once per pending row), so it doesn't change this map's design
  and is flagged as out-of-scope follow-up material in "Not yet
  specified" below, not absorbed into any ticket here.
- Mode: decision-spec only (wayfinder default, not overridden).
  Implementation is a separate, later effort — same as
  `mdm-ahead-of-silver`'s stated mode.

## Decisions so far

<!-- the index — one line per closed ticket: enough to judge relevance, then zoom the link for the detail the ticket holds -->

- [Decide Once-Per-Day Debounce/Cap Semantics](issues/01-decide-once-per-day-debounce-cap-semantics.md) — no cap: fire on every genuine busy→idle transition, not a hard once-per-UTC-day limit. `PROCESS_RUN_MANIFEST_STREAM` no-ops cheaply when its stream is empty, and the original credit-burn cause was a fixed poll timer, not call volume — so nothing is gained by capping, while ad hoc pipeline data would otherwise sit unsynced until the next day. "Once a day" holds as an emergent property of the pipeline schedule in the steady-state case, not an enforced rule. No "already fired today" state needs to exist.
- [Design the Idle-Detection Re-Check and Race Safety](issues/02-design-idle-detection-recheck-and-race-safety.md) — a small one-off ECS task on the warehouse image (not Lambda — this repo has zero Lambda functions anywhere), triggered by an EventBridge rule that reacts to *every* terminal event for the watched ARNs (11, per [ticket 05](issues/05-derive-correct-watched-state-machine-set.md) — the "7" here was corrected after this ticket was written) including Distributed Map child/window executions (no ARN-shape filtering — the idle re-check's own RUNNING-list naturally no-ops premature fires). Race safety leans on Snowflake's own transactional stream consumption plus a fresh re-check immediately before firing, rather than building a new distributed lock.
- [Decide Invocation Plumbing and the Fate of SNOWFLAKE_RUN_MANIFEST_TASK](issues/03-decide-invocation-plumbing-and-task-object-fate.md) — reuse `EDGARTOOLS_PROD_LOADER` via the existing `MDM_SNOWFLAKE_SECRET_JSON` secret with zero new grants (live-verified against the actual prod secret and procedure ownership). The manifest **stream** must stay (it's `PROCESS_RUN_MANIFEST_STREAM`'s sole queue — not part of the task's fate), but the **task object + schedule are removed from Terraform entirely**, not kept as a dormant fallback — the loader role can already call the procedure directly, so no fallback capability is lost, and removal closes an incident class (task-schedule drift) this repo has hit twice on this exact object.
- [Derive the Correct Watched State-Machine Set](issues/05-derive-correct-watched-state-machine-set.md) — corrected the Opus review's G3 finding into a verified, complete list: **11** state machines, not the originally-claimed 7 (`daily_incremental`, `load_history`, `bootstrap`, `bootstrap_full`, `targeted_resync`, `full_reconcile`, `silver_mdm_gold`, plus `gold_refresh`, `mdm_gold`, `ownership_mdm_gold`, `bronze_seed_silver_gold`) — mechanically traced from every `upsert_state_machine` call in `deploy-aws-application.sh`. Going forward, derive this list by grepping each generated ASL definition for a `gold-refresh` command literal at deploy time, not by hand-maintaining a second list (which is exactly how the original miscount happened).
- [Resolve the Invocation Path and Secret Plumbing](issues/06-resolve-invocation-path-and-secret-plumbing.md) — G4 turned out to be a non-gap: the warehouse and MDM ECS task families share one IAM execution role, and that role already has `secretsmanager:GetSecretValue` on the Snowflake secret — only a one-line container-definition addition is needed, no new Terraform. Stays on the warehouse image (naming/semantic fit, not a new constraint). G5: invoke through a minimal single-state Step Functions machine (same shape as the existing `gold_refresh` single-workflow pattern, `Retry` block for free) triggered by EventBridge `StartExecution` with `InputPath: "$.detail"` (same shape as `daily_incremental`'s existing cron rule) — not a direct EventBridge→ECS target, which would need a brand-new IAM integration this repo has never built.
- [Decide Lost-Fire Retry and Snowpipe-Timing Handling](issues/07-decide-lost-fire-retry-and-snowpipe-timing.md) — build both cheap mitigations rather than deferring to delayed-sync-plus-alarm. G1 splits in two: ECS/connector failures are already covered by ticket 06's SFN `Retry` block (command just needs correct exit-code semantics); the stale-RUNNING-view case is fixed by excluding `detail.executionArn` (already available from ticket 06's wiring) from the command's own RUNNING check. G2: a bounded poll (~2 min, ~15-20s interval) on `SYSTEM$STREAM_HAS_DATA` before giving up, since the command already holds a warehouse session regardless — falls back to accept-and-let-the-next-transition-catch-it if exceeded, not an unbounded wait. Narrows ticket 04's alarm to genuinely pathological cases only.
- [Design the Dead-Man's-Switch Alarm](issues/04-design-dead-mans-switch-alarm.md) — a scheduled Snowflake-side check on `MIN(RECEIVED_AT)` over the unconsumed manifest stream (safe: `SELECT` doesn't advance a stream's offset), not a CloudWatch log filter or a second hand-maintained watched-set. Threshold **4 hours** — live-verified via `TASK_HISTORY` that the old poll's own worst-case freshness lag was exactly 6 hours once its schedule stabilized, so 4h alarms *before* the new design would even match the system it's replacing. Naturally distinguishes "nothing pending" (zero rows, no alarm) from "stuck" (old rows, alarm) with no special-casing. Alerts via the existing operator SNS topic.

## Not yet specified

- Whether this trigger should eventually also cover non-gold-affecting
  freshness needs (e.g. MDM graph sync freshness) — not raised by the
  user, not pulled in scope here; revisit only if it turns out to matter
  once this map's design is live.
- **`REFRESH_AFTER_LOAD` unconditionally refreshes all ~24 gold tables on
  every manifest row** rather than scoping to what the triggering
  workflow actually touched (found while resolving ticket 04, live
  `QUERY_HISTORY`: 6,435 calls against 1,009 `PROCESS_RUN_MANIFEST_STREAM`
  invocations over 30 days — ~6.4 full-table passes per invocation). This
  is a real inefficiency and likely the dominant cost driver on
  backfill-heavy days, but it's orthogonal to this map — identical cost
  under the old poll and the new trigger, since both invoke it once per
  pending row regardless of what wakes them up. A legitimate candidate
  for its own future map; not pulled into this one's scope.

## Frontier

Empty. All 8 tickets (01-07, plus the pre-review 01-03) are resolved —
the decision-spec is complete. Per this map's own stated mode
("decision-spec only... implementation is a separate, later effort"),
turning this into real Terraform/ASL/Python changes is a distinct next
step, not something any ticket here does.

## Out of scope

- Keeping the 6-hour poll as a load-triggering fallback — explicitly
  rejected in this session's grilling (replace entirely, alarm-only
  safety net instead).
