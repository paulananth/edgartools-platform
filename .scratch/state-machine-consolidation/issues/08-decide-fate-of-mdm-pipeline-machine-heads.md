Type: grilling
Status: claimed

## Question

[Ticket 07](07-collapse-mdm-tail-to-a-single-deployed-machine.md) locked the
target architecture: 1 MDM machine (exactly `Mastering → Infer
Relationships → Publish → Publish Relationships → Reconcile`, nothing
before or after — `GoldRefresh`, renamed `FactPublishtoGold`, is explicitly
excluded and stays its own separate machine), 1 merged seed machine,
`daily_incremental`, and `load_history` — each of the latter 3 calling the
MDM machine instead of inlining its states. Ticket 07 also settled
`mdm_gold`'s fate directly (**deleted outright** — it already has no head,
so it's fully redundant with the new MDM machine) and
`bronze_seed_silver_gold`'s strict release-mode branch (**left embedded and
untouched**, no equivalent built elsewhere) — neither is part of this
ticket's remaining question.

That leaves the fate of the **remaining 4** MDM Pipeline Machines
undecided: `ownership_mdm_gold`, `silver_mdm_gold`,
`bronze_seed_silver_gold`'s **default path** (its strict path is already
settled — untouched), and `residual_holds_graph`. Each is a distinct head
(different upstream stage(s)) plus the shared tail:

| Machine | Head (before the tail) |
|---|---|
| `ownership_mdm_gold` | `ParseOwnershipBronze, MdmPersons, MdmIsInsider` |
| `silver_mdm_gold` | `SeedUniverse, SeedSilverBatches, BatchSilver, MdmSecurities` (ticket 02's Notes list `SeedUniverse, SeedSilverBatches, BatchSilver, MdmRun, MdmBackfill` for the pre-tail-helper shape — re-verify head boundary during implementation) |
| `bronze_seed_silver_gold` (default path only) | its own large bronze/seed/silver head |
| `residual_holds_graph` | `MdmSecurities, MdmPersons, MdmIsInsider, MdmHolds, MdmCompanyHolds, MdmInstitutionalHolds` — also runs on `mdm_large`, not `mdm_medium`, and already correctly skips `FactPublishtoGold`/`GoldRefresh` today (ticket 07 confirmed why: no new bronze/silver capture happens in its own run, so there's nothing new for a gold rebuild to pick up) |

Given the target architecture names only 4 total machines (plus the
untouched `FactPublishtoGold`), does each of these 4 remaining heads become
its own standalone deployed machine (4 more machines, each just its head +
a call to the 1 MDM machine — total 8 machines: 1 MDM + 1 seed +
`daily_incremental` + `load_history` + `FactPublishtoGold` + these 4), or
do these heads get absorbed into one of the named machines (and if so,
which — does the seed machine grow to include ownership-parsing/
silver-batching/residual-holds derivation, or do these become new
execution-input variants of `daily_incremental`/`load_history`)?

## Answer (in progress — 1 of 4 machines decided, 3 remain open)

**`ownership_mdm_gold`: deleted outright (user-directed, 2026-09-03).**
Investigated its one live execution ever (`ownership-mdm-gold-10cik-20260725T204806Z`)
before deciding — it was a manual operator `ABORT`, not a real failure:
`parse-ownership-bronze` has no CIK-scoping capability (only `--limit`/
`--accession-list`), so it always does a universe-wide missing-artifact
scan (~189k artifacts at the time); the operator caught this and manually
redirected rather than let it run needlessly. User asked whether this
machine (and `residual_holds_graph`) should be deleted "unless something
unique is discovered" — `parse-ownership-bronze` (this machine's head) was
confirmed called nowhere else in the deploy script, a genuinely unique,
idempotent bronze-reparse-without-refetch capability. That uniqueness was
reported, but the user directed deletion anyway. Rollback snapshot at
[ownership-mdm-gold-definition-snapshot-2026-09-03.json](rollback-snapshots/ownership-mdm-gold-definition-snapshot-2026-09-03.json).
Also deleted the smaller, byte-identical `MdmPersons` duplication
(`mdm mastering --entity-type person`) that this machine shared with
`residual_holds_graph` before this — confirmed redundant with `mdm
mastering --entity-type all` (`edgar_warehouse/mdm/pipeline.py`'s
`MDMPipeline.run_all`, which already calls `run_persons`).

**`residual_holds_graph`: kept, tail left inline (not rewired to call the
new MDM machine).** Same "delete unless unique" framing applied — found it
IS unique: the only deployed pipeline that masters securities, derives
`IS_INSIDER`/`HOLDS`/`COMPANY_HOLDS`/`INSTITUTIONAL_HOLDS` in order, and
publishes/syncs/reconciles the result (the generic `mdm_backfill_relationships`
utility mode does one relationship type per manual trigger only, no
mastering, no publish). Separately: user asked whether these 4 relationship
types should fold into the new MDM machine's automatic tail (would then run
on every `daily_incremental`/`load_history` execution) — investigation found
`derive_relationships()`'s underlying `_derive_*` methods (confirmed for
`_derive_holds`, `_derive_institutional_holds`) have no incremental/diff
filtering at all, full source-table scan every invocation regardless of
`target_per_type` — folding this into a pipeline named "daily incremental"
would be architecturally inconsistent with the rest of the platform. User
agreed; tracked as its own map,
[mdm-relationship-incremental-filters](../mdm-relationship-incremental-filters/map.md).
Investigated why both of `residual_holds_graph`'s live executions failed:
execution 1 OOM'd (exit 137) at `MdmSecurities` on the old 2GiB profile —
already fixed, current code runs it on `mdm_large`; execution 2 (a retry,
started 28s later) hit a stale image-pull error on its first attempt (infra,
self-resolved), then succeeded through every single stage
(`MdmSecurities`→...→`MdmSync`), only failing 3x with a plain `exit code 1`
at the final `MdmVerify` state — root cause unrecoverable (CloudWatch log
retention is 7 days, executions are 39 days old). `MdmPersons` also deleted
from this machine's head (same redundancy as above).

**Still open:** `silver_mdm_gold` and `bronze_seed_silver_gold`'s default
path — earlier discussion recommended both keep their existing heads
unchanged and rewire their tails to a nested call into the new MDM machine
(matching `daily_incremental`/`load_history`/`seed`'s pattern), chaining
into `FactPublishtoGold` afterward exactly as today — but this was never
confirmed by explicit user answer nor implemented. Needs its own pass.

**Design worked out and reviewed (2026-09-03), not yet implemented —
paused at user's request ("keep a note i dont want to work on anything
yet").** `/implement ticket 08` surfaced a real conflict before any code
was written: `silver_mdm_gold`'s and `bronze_seed_silver_gold`'s own
`Mastering` states both have a load-bearing invariant the new MDM
machine's `Mastering` doesn't honor today — no `--limit`, always a full
unbounded bulk re-run (their own comment: "A hard limit would silently
leave the majority of companies unprocessed in MDM and Neo4j"), versus
the MDM machine's `Mastering`/`Infer Relationships` always applying
`--limit` (bound to deploy-time `MDM_RUN_LIMIT`/`MDM_GRAPH_LIMIT`).
Naively rewiring either caller as-is would silently turn "reprocess
everything" into "reprocess ~100 companies." `bronze_seed_silver_gold`
also passes `--resume-ledger-run-id $.resume_from_run_id` to its
`Mastering`, which nothing else needs (confirmed safe to always include
with a `""` default for other callers —
`edgar_warehouse/mdm/pipeline.py:360`'s `str(resume_ledger_run_id or
"").strip()` treats empty-string and absent identically).

Reviewed design (`/gof-refactor-reviewer` consulted, verdict: sound, no
blocking findings): add two optional input fields to the MDM machine's
contract, `unbounded` (bool) and `resume_ledger_run_id` (string, default
`""`); a Choice+Pass pair (mirroring this file's own established idiom —
`batch_size_check`/`batch_size_default`,
`resume_from_run_id_presence_check`/`default` in
`write_bronze_seed_silver_gold_definition`) injects
`$.effective_mdm_limit`/`$.effective_mdm_graph_limit` as either a large
sentinel (unbounded) or the existing deploy-time defaults (bounded,
unchanged for `daily_incremental`/`load_history`/`seed`) *before*
`Mastering` runs; `Mastering`/`Infer Relationships` read those via
`States.Format` instead of a bash-interpolated hardcoded value.
`call_mdm_machine()` (`mdm_tail_helper.py`) needs a new optional
`extra_input` parameter to carry these caller-supplied fields through —
not yet implemented. Full design detail and the reviewer's exact findings
are in this session's transcript; re-derive from this note plus a fresh
`/gof-refactor-reviewer` pass if picked up in a different session, rather
than trusting this summary blindly.
