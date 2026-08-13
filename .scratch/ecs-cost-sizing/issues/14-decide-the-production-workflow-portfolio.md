# Decide the Production Workflow Portfolio

Type: grilling
Status: resolved
Blocked by: 10, 11, 13

## Question

Which production state machines should be kept as-is, reshaped, merged into a
canonical pipeline, split for isolation, made operator-only, rescheduled, or
retired?

Apply the agreed workflow value test to every inventoried state machine. Keep
distinct workflows where they provide a unique output, bounded repair path,
failure-isolation boundary, release gate, or materially better economics.
Consolidate wrappers and repeated MDM/gold chains only when immutable inputs,
resume semantics, observability, IAM, and rollback remain unambiguous. Require
a downstream-consumer and schedule audit before retirement.

## Answer

Built directly on gate 6's four operator decisions from Ticket 11 (deregister
the 7 orphaned MDM machines; accept the Step-Functions-bypass path; add
non-blocking visibility to `MdmVerify`'s masking `Catch`; default
zero-execution workflows to retirement candidates) plus Ticket 13's per-
workflow economics. Five further calls, grilled and accepted:

**1. MDM+gold composite wrapper consolidation.** `bronze_seed_silver_gold`
is the sole canonical composite chain going forward — it has real, if mixed,
evidence behind it (Ticket 13: a genuine $0.73 zero-commit failure at `mdm
export` in one instance, 680/680 successful `StrictBatchSilver` in another).
**Retire `silver_mdm_gold` and `mdm_gold`** — zero executions each, no
evidenced output, consumer, or capability distinct from
`bronze_seed_silver_gold` (Ticket 10's value test). `ownership_mdm_gold`
(1 aborted execution, Ticket 13 couldn't even reconstruct its Fargate cost)
is not resolved here — see Ticket 23, opened to settle whether it's a
deliberate narrower isolation boundary or an abandoned prototype before its
own keep/retire call is made.

**2. The other 5 zero-execution utility machines.** **Retire**
`bootstrap_full`, `catch_up_daily_form_index`, and
`load_daily_form_index_for_date` — no evidenced need, functionally covered
by `load_history`/`daily_incremental`. `mdm_seed_universe` retires with the
same reasoning (folds into the same zero-execution default from gate 6).
**`full_reconcile` is the one exception: keep**, not retired by the
zero-execution default — its name and position in the portfolio indicate a
bounded disaster-recovery capability, which Ticket 10's value test
explicitly protects ("a bounded repair/recovery capability" is one of the
five standing reasons a workflow is valuable) even at zero historical use.

**3. `generation_build`.** **Keep** — it is the only workflow in the
portfolio capable of ever producing a new graph generation; retiring it on
a zero-recent-execution technicality (one run, 21 days ago) would be an
accidental capability loss, not an intentional one. Not fully closed: see
Ticket 24, opened to get an owner's confirmation this was never actually
abandoned by decision. This satisfies Ticket 15's item 4 contingency well
enough to unblock future `BuildPartitions` sizing work, though Ticket 24's
confirmation is the harder close.

**4. `residual_holds_graph`'s uncaught verify step.** **Reshape** — add the
same non-blocking-but-visible `Catch` pattern already approved (gate 6) for
the other 5 machines sharing this `MdmVerify` state, so this workflow's
terminal status stops reporting `FAILED` 100% of the time (2/2) when 8 of 9
data-producing stages actually succeeded.

**5. Formalizing gate-6's "add visibility, don't block" fix.** A distinct
terminal marker — e.g. `verify_status` written onto the run's S3
manifest/Snowflake tracking row when the `Catch` fires — replaces the
current state where three separate tickets in this map (11, 12, 13) each
had to hand-derive this from raw Step Functions execution history.

**Portfolio shape after this ticket:** of the 26-workflow (now 25-live,
per Ticket 13's fresh count) inventory — retire 7 (gate 6's orphaned MDM
machines) + 5 (this ticket: `silver_mdm_gold`, `mdm_gold`, `bootstrap_full`,
`catch_up_daily_form_index`, `load_daily_form_index_for_date`,
`mdm_seed_universe` — 6, not 5, correcting the count as written) = 13
retirement candidates; keep `bronze_seed_silver_gold` as sole composite
chain, `full_reconcile` and `generation_build` as protected
capability-holders, `residual_holds_graph` reshaped not retired;
`ownership_mdm_gold` pending Ticket 23.

**Out of this map's planning-only scope, per its own Notes**: items 4 and 5
above are real code/ASL changes, not decided-and-done — they're follow-up
PRs, same pattern as Ticket 15's CIK-window resume fix. Retiring the 13
identified machines is itself an AWS mutation (deregistering state
machines) also deferred to implementation, not executed by this ticket.
