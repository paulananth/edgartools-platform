# Stage0/Stage1/1B consolidation

## Destination

A locked, implementation-ready design for eliminating `load_history`'s
`Stage0CompanyIdentity` as a separate stage — folding its company-identity
capture into Stage1's `WindowedBootstrap`, which already produces the same
data as a byproduct — while deciding whether Stage1's own unfixed
full-window hydrate/materialize OOM stopgap (the same architectural problem
class Stage0 was just fixed for) ships as part of the same restructuring or
as a sequenced follow-up. Stage1B is reviewed for hidden coupling to
Stage0's specific output (not just Stage1's) but is not itself a
restructuring target — research already found it genuinely disjoint (see
ticket 01). Done when someone can implement the merge without further
architecture debate, including a concrete rollout gate that doesn't touch
`load_history`'s live state-machine definition until the in-flight
production backfill confirms the Aug 2026-08-05–09 Stage0 restructuring
(PR #360/#361) actually works end-to-end.

## Notes

- Repo: `edgartools-platform`. This map carries **decisions only** —
  implementation happens in a normal (non-wayfinder) session afterward,
  matching [company-identity-hydrate-elimination](../company-identity-hydrate-elimination/map.md)'s
  precedent.
- **Explicit user decision (2026-08-10):** proceed with charting this map
  despite the assigned research recommending "leave it" on the merge
  itself — the duplication cost is unmeasured/likely small, and Stage0's
  own restructuring is unproven in prod as of charting time (task #35's
  `retry5` execution is live against it). The user weighed this and chose
  to design the consolidation anyway; **implementation is gated on
  `retry5` finishing cleanly** (see ticket 03), so the live backfill is
  not put at risk by this map's own timeline.
- Key files: `infra/scripts/deploy-aws-application.sh` (`write_load_history
  _definition` — `Stage0CompanyIdentity`, `ReduceIdentityRefresh`,
  `Stage1Parallel`/`windowed_bootstrap`, `Stage1BEntityFacts`/
  `Stage1BPerFiling`/`Stage1BThirteenF`), `edgar_warehouse/application/
  warehouse_orchestrator.py` (`_run_submissions_bronze_then_silver`,
  `_resolve_bootstrap_target_ciks`, `compute-windows` handler,
  `_capture_submission_bronze_snapshots` — the un-streamed accumulation
  Stage1's own OOM stopgap comment points at), `edgar_warehouse/
  application/commands/bootstrap_fundamentals.py` (`execute()`, the
  `mode == "company-identity"` path), `edgar_warehouse/application/
  identity_refresh_publication.py` (the delta-then-reduce machinery
  Stage0 currently uses, also used by `daily_incremental`'s bounded
  Identity Refresh — ticket 04 decides its fate here).
- Prior art / do not re-litigate: [company-identity-hydrate-elimination](../company-identity-hydrate-elimination/map.md)
  already decided and shipped Stage0's own internal hydrate/publish
  restructuring (PR #360/#361) — this map is about whether Stage0 should
  exist as a *separate stage at all*, not about redoing that work.
- Skills every session on this map should consult: `/gof-refactor-reviewer`
  (already applied once in ticket 01 — re-apply if the target architecture
  in ticket 02 changes materially), `/grilling` + `/domain-modeling` for
  any ticket marked `grilling`.

## Decisions so far

- [Map current Stage0/1/1B architecture, overlap, and sequencing constraint](issues/01-map-current-architecture-and-overlap.md) — Stage0's output is a strict subset of Stage1's own capture (same function, same CIK list, same 4 tables); the stated "Stage0 must run first" invariant is factually unenforced in code (traced: `_derive_is_insider` depends on MDM `MdmCompany` rows written by Stage 2, which runs after Stage1 regardless of Stage0). Stage1B is genuinely disjoint (real read-after-write / different SEC endpoint), not a merge candidate. GoF-reviewer verdict at research time: "leave it" — evidence didn't clear Rule 0's bar, and a higher-priority sibling issue (Stage1's own un-streamed hydrate accumulation, same OOM class Stage0 was just fixed for) is untracked anywhere. User chose to proceed with the map regardless (see Notes).
- [Decide target architecture: how Stage0 merges into Stage1, and whether Stage1's streaming fix ships combined or sequenced](issues/02-decide-target-architecture.md) — **Map destination reached for the Stage0/Stage1 half.** Locked: (1) delete `Stage0CompanyIdentity` Map + `ReduceIdentityRefresh`, let Stage1's `bootstrap-next` (already a superset call) stand alone, no new code needed; (2) the streaming fix ships as its own separate future map, not combined here — it has platform-wide blast radius across all 5 SEC-fetching commands (shared `_capture_submission_bronze_snapshots`), not a load_history-local patch; Stage1 explicitly, knowingly inherits Stage0's identity-capture work into its still-un-streamed accumulation in the interim; (3) the stale sequencing-invariant comment is removed entirely, no replacement safeguard — nothing in code ever depended on it.
- [Decide the safe rollout gate and verification plan for redeploying load_history's definition against a live production pipeline](issues/03-decide-rollout-gate.md) — Bar is retry5 reaching `SUCCEEDED`, but with a carve-out: an unrelated later failure doesn't block, since the gate's real purpose (confidence in the Stage0/`ReduceIdentityRefresh` machinery this map's design replaces) is already satisfied — both succeeded live on retry5 as of this ticket's resolution. Add a bounded `--cik-limit` smoke test against the new definition before the next full-universe run (reuses the snowflake-account-cutover precedent). Rollback: manual `describe-state-machine --query definition` snapshot before redeploy, not new tooling — two uses doesn't clear Rule 0's bar for a script.
- [Decide fate of Stage0's delta-then-reduce/identity_refresh_publication.py machinery for load_history post-merge](issues/04-decide-identity-refresh-machinery-fate.md) — **Map destination fully reached; all tickets resolved.** Found a real correctness gap while writing the cleanup checklist, folded back into ticket 02 as an addendum: `compute-windows` only ever lands its once-per-run reference-data sync (`company_tickers`/`company_tickers_exchange`) in canonical via `ReduceIdentityRefresh`'s merge — deleting Reduce as ticket 02 originally specified would have silently stopped reference-data refresh for `load_history`. Fix folded into the checklist: drop `"compute-windows"` from the publish-special-case tuple at `warehouse_orchestrator.py:699` so it falls through to a normal direct canonical publish instead. Full 7-item implementation checklist written (ASL deletion, handler cleanup, the publish-path fix, `identity_refresh_publication.py` confirmed untouched since `daily_incremental` has its own separate copy, and exact test files/blocks to remove vs. rewrite).

## Not yet specified

(none — ticket 04's checklist fully specified the implementation diff.
Map destination reached; execution happens in a follow-up non-wayfinder
session per Notes.)

## Out of scope

- **The `_capture_submission_bronze_snapshots` streaming fix** (ticket 02,
  resolved 2026-08-10) — deliberately ruled out of this map's destination,
  not deferred as fog. It has platform-wide blast radius across all 5
  SEC-fetching commands (`daily_incremental`/`bootstrap`/`bootstrap_full`/
  `targeted_resync`/`bootstrap_batch`), sharing one already-optimized
  wave-based function (pipeline-throughput-architecture ticket 06/78).
  Deserves its own future wayfinder map scoped platform-wide; no ticket
  for it exists yet anywhere in `.scratch/` as of this map's closing —
  flagged here so it isn't silently lost.
- `daily_incremental`'s own (currently unbounded, zero-prod-execution)
  Stage0CompanyIdentityBounded — already ruled out of scope by
  [company-identity-hydrate-elimination](../company-identity-hydrate-elimination/map.md)'s
  ticket 03 for the identical reason (no live urgency); inherited here
  rather than re-litigated.
- Redesigning `identity_refresh_publication.py`'s shared delta-then-reduce
  contract itself (the `write_immutable_bytes`-retry-fails-closed gap
  flagged in that map's ticket 03 implementation notes) — a pre-existing,
  separately-flagged gap, not created or worsened by this map.
