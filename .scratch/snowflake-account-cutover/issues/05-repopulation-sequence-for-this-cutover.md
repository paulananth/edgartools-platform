# Decide the concrete repopulation sequence for this cutover

Type: grilling
Status: resolved

Blocked by: 02, 07

## Question

Given Ticket 02's answer on how gold actually populates (and whether a
historical-backfill trigger is needed), decide the concrete sequence of
existing commands/state machines to run against `pijjxma-ppb32800` to take
it from "Terraform infra stood up, empty" to "source + gold populated."

Candidates already visible in the codebase that need evaluating against
each other once Ticket 02 resolves:

- `bronze_seed_silver_gold` Step Function (discovers CIKs directly from
  existing S3 bronze, chains `SeedFromBronze -> BatchSilver -> MdmRun ->
  MdmBackfill -> MdmSync -> MdmVerify -> GoldRefresh`) — per CLAUDE.md, the
  canonical one-click path for cold-starting/recovering an environment's
  silver/MDM/gold from an existing bronze snapshot. This looks like the
  closest existing match to this map's exact scenario (bronze/silver already
  exist, everything downstream needs repopulating).
- The standalone `gold-refresh` Step Function on its own.
- `load_history`'s full phased pipeline (Stage 0-3) — probably wrong fit,
  since it assumes bronze/silver don't yet exist and would re-fetch from SEC
  needlessly; confirm this reasoning rather than assume it.

## Notes

`grilling`-type since there's a real judgment call in choosing among
existing mechanisms (or composing them) once the facts from Ticket 02 are
in — not a pure fact-finding task.

## Answer

Resolved via `/grilling` with the user driving the map.

**Confirmed early: `go-live.sh`'s existing sequence *is* the answer, not
something to design from scratch.** Both of this ticket's leading
candidates (`bronze_seed_silver_gold`, standalone `gold-refresh`) are
already wired into `go-live.sh` as stages 11 and 12 — the user's framing
made explicit what the ticket's own question implied but didn't state:
since bronze and silver already exist in S3 (this map's Destination), the
task is a *new install against existing S3 state*, not a from-scratch
build. `load_history`'s full phased pipeline is confirmed the wrong fit,
as the ticket originally suspected: its Stage 1 explicitly re-fetches from
SEC via `bootstrap-next` into fresh bronze — redundant work against data
that's already there.

**Renamed, going forward: `go-live.sh` → `install.sh`.** Decision only —
the actual rename (file, `.edgartools-go-live` workspace directory,
`GO_LIVE_*` env vars, every doc/test reference) is real mechanical work,
deferred to an implementation pass, not done in this ticket.

**Real gap found and resolved: `seed-universe` is missing from the existing
sequence, and nothing else covers what it does.** Traced the actual code,
not assumed: `bronze_seed_silver_gold`'s `SeedFromBronze` step
(`seed-bronze-batches`) lists CIKs directly from *already-written* bronze
S3 paths — a fundamentally different operation from `seed-universe`, which
calls SEC's live ticker/CIK reference feed (`_sync_reference_data`) and
writes into silver's tracked-universe state. More importantly:
`gold-refresh`'s `iter_gold_tables()` builder registry has **no**
`TICKER_REFERENCE` builder at all — confirmed via grep, `build_ticker_reference_table()`
in `edgar_warehouse/serving/gold_models.py` takes `universe_rows` as a
parameter (fed only by `seed-universe`'s own run), not a `conn` like every
other registered builder. `TICKER_REFERENCE`'s Snowflake export is
populated *exclusively* by running `seed-universe` itself (it's one of
`SNOWFLAKE_EXPORT_COMMANDS`, independent of `GOLD_AFFECTING_COMMANDS`).
Running only stages 11+12 as they exist today would leave
`TICKER_REFERENCE` permanently empty on the new account even with
everything else fully populated.

**Where it fits, per the user's own framing:** `seed-universe` is not a
Snowflake-specific concern — it already runs regularly (e.g. via
`daily_incremental`) as part of maintaining the silver layer, independent
of which Snowflake account exists. Rather than inventing a special
"backfill" mechanism, the fix is to run it once, full/unscoped (not the
bounded `--limit 100` `install.sh`'s existing smoke-test stage uses), as
an early step in the sequence — establishing `TICKER_REFERENCE`'s initial
state in the new account. After that, it stays current the same way it
already does today: the existing recurring silver-layer cadence, unaffected
by this map, keeps exporting to whichever account is live.

### Final sequence (all within `install.sh`, formerly `go-live.sh`)

1. **New: `seed-universe`, full/unscoped** — added ahead of stage 11,
   framed as a one-time initial-state establishment for the new account,
   not an ongoing mechanism of its own.
2. **Existing stage 11: `bronze_seed_silver_gold`** — unchanged.
   `SeedFromBronze → BatchSilver → MdmRun → MdmBackfill → MdmSync →
   MdmVerify → GoldRefresh`, zero new SEC calls, reads only from existing
   S3 bronze.
3. **Existing stage 12: standalone `gold-refresh`** — unchanged, kept as
   the explicit, auditable trigger per its own prior-incident history
   (stage 11's internal `GoldRefresh` was never trusted alone).

Feeds directly into **Ticket 06** (runbook assembly): the rename to
`install.sh`, the new `seed-universe` stage, and Ticket 07's `01`/`03`/`04`
Terraform backport + new `07`/`08` stages all need to land in the same
implementation pass before this sequence can be trusted end to end.

**Correction, made while resolving Ticket 06:** the reasoning above
overstated why `seed-universe` needs to run unscoped. Traced
`warehouse_orchestrator.py:1686-1731`: `ticker_reference_rows` (what
actually populates `TICKER_REFERENCE`) is captured from the full SEC ticker
feed at line 1692-1693, **before** the `--limit` slice at line 1724-1725 —
so `TICKER_REFERENCE` is exported in full on *every* `seed-universe` call
regardless of `--limit`, when that code path actually runs. The real reason
to run it unscoped is different: `--limit` truncates which newly-discovered
CIKs get queued into `bootstrap_pending` tracking status (line 1724-1725,
after the already-active-CIK filter) — a bounded run could silently drop
genuinely-new companies past the first `N`. The conclusion (run it
unscoped, early in the sequence) is unchanged; only the stated rationale
was wrong.

**Second correction, same session:** line 1686 (`_sync_reference_data`) and
everything downstream of it only executes under
`_execute_warehouse_bronze_capture` — gated on `WAREHOUSE_RUNTIME_MODE=
bronze_capture`. The *existing* smoke-test stage sets
`WAREHOUSE_RUNTIME_MODE=infrastructure_validation`, which routes to the
sibling function `_execute_warehouse_infrastructure_validation`
(`warehouse_orchestrator.py:293-393`) instead — confirmed by reading it in
full: it never calls `_sync_reference_data` or `seed_universe_loader` at
all, only writes placeholder manifest JSON (`_layer_manifest`,
`_snowflake_export_manifest`) to the bronze/storage/snowflake_export roots.
So the old bounded `seed-universe --limit 100` call was never doing real
SEC fetches or a real `TICKER_REFERENCE` export in the first place — it was
a connectivity/path check, essentially free. This doesn't change the
decision (still remove that line once the real stage exists — a
manifest-only stub is pointless once real data has already been seeded),
but it does mean the new unscoped stage must explicitly set
`WAREHOUSE_RUNTIME_MODE=bronze_capture` (matching
`deploy-aws-application.sh`'s own production default, confirmed at its line
189) — reusing the smoke-test stage's `infrastructure_validation` mode by
copy-paste would have silently produced another no-op manifest stub instead
of a real seed. See Ticket 06's answer for the exact stage placement this
lands at.
