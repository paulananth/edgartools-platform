# 43 — Investigate why daily_incremental reprocesses the full active universe

Type: research
Status: resolved
Blocked by: (none)

## Question

`daily_incremental`'s first-ever prod execution (`daily-incremental-1785336584`, started
2026-07-29) took ~10-11 hours end to end. Root cause of the bulk of that time, confirmed live
via `describe-map-run`/`describe-tasks`: **Stage0CompanyIdentity runs `bootstrap-fundamentals
--mode company-identity` over 53 windows of 500 CIKs each (≈26,500 CIKs) — essentially the
entire active/tracked universe (~26,300 companies per ticket 40's count), not just companies
with new or changed activity since the last run.** Each window took ~8-14 minutes; the stage
runs at `MaxConcurrency: 1` by deliberate design (per `deploy-aws-application.sh`'s own comment,
to avoid concurrent writes racing on the shared silver DuckDB publish — the same class of
contention issue documented elsewhere in this codebase for other stages).

For a state machine named `daily_incremental` and intended to run on a recurring (presumably
daily) cadence, reprocessing the full universe's company-identity data every single day looks
architecturally suspect — not necessarily wrong (Stage 0's own purpose is "resolve Company
entities before ownership/ADV parsing needs them," which may have a real reason to always be
complete), but nobody has confirmed whether this is intentional design or an unaddressed gap.
Two consecutive daily runs, if both re-scan the full universe at ~10-11 hours each, may not even
finish before the next day's run is due to start.

Investigate:
1. Is `bootstrap-fundamentals --mode company-identity`'s CIK selection (when invoked with no
   explicit `--cik-list`, i.e. windowed from silver tracking state) capable of being scoped to
   only recently-active/changed companies, or does it always resolve the full ordered CIK list
   regardless of caller? (Check `_configured_parser_accessions`-adjacent CIK-selection logic in
   `warehouse_orchestrator.py`/`ComputeWindows`, not the accession-level gate fixed in ticket 42
   — this is a different, CIK-level selection question.)
2. Is there a genuine architectural reason Stage 0 must see the complete universe every run
   (e.g. re-resolving identity fields that can silently change for any company, not just ones
   with new filings — ticker changes, name changes, deregistration), or was `daily_incremental`
   simply built by copying `load_history`'s Stage 0 shape verbatim without reconsidering scope
   for a recurring/incremental cadence?
3. If a narrower scope is viable, what would bound it correctly (e.g. "CIKs with a filing dated
   since the last successful `daily_incremental` run," a persisted watermark) without silently
   missing out-of-band identity changes (deregistrations, ticker changes) that don't necessarily
   come with a new filing?
4. What is the actual operational impact if this is left as-is — does a ~10-11 hour daily run
   risk overlapping with the next day's scheduled trigger, and if so, what happens (the state
   machine already has other stages relying on Stage 0 completing first)?

This is a research ticket — read the code and existing execution history (this first run is
live evidence) to answer whether narrowing is possible and safe; do not implement a scope change
without a follow-up decision ticket once the investigation lands.

## Answer

Full findings (method, live SEC fetches, live AWS state checks, code citations) in the sibling
file `issues/43-research-findings.md`. Summary per the four investigation questions:

1. **CIK selection can be narrowed — the mechanism already exists but is unused for this
   purpose.** `bootstrap-fundamentals --mode company-identity` already supports an explicit
   `--cik-list` path (`bootstrap_fundamentals.py:117-126`) that skips windowing the tracked
   universe entirely. `Stage0CompanyIdentity` (`deploy-aws-application.sh:2227-2258`) simply never
   uses it — it hardcodes `--cik-offset`/`--cik-limit` against a full-universe `compute-windows`
   output.
2. **Not a deliberate design decision — a verbatim, unmodified copy of `load_history`'s Stage 0.**
   The code's own comment (`:2204-2226`) says so directly: `load_history` exists to onboard a
   brand-new universe, where "process everyone" is correct by definition; that shape was reused
   for `daily_incremental` (a recurring/incremental job) without reconsidering scope.
3. **A viable narrower bound exists, reusing only already-built code:** the real SEC daily-index
   (`.idx`, not JSON — confirmed live, see finding below) already flows through a working parser
   (`_load_daily_index_for_date`) that produces an `impacted_ciks` list — but only *inside*
   `RunWarehouseTask`, which runs *after* Stage 0. A narrowed Stage 0 needs a new pre-stage that
   parses the index first; the already-built, currently-unscheduled `catch-up-daily-form-index`
   command (self-parameterizing from `db.get_last_successful_checkpoint_date()`, no date input
   required, index-only — no CIK data fetch) is exactly that missing piece, just never wired into
   `daily_incremental`'s definition. On one sample day (2026-07-28), the daily index named 2,925
   distinct CIKs out of ~26,300 tracked (≈11%) — roughly an order-of-magnitude narrowing if
   Stage 0 consumed it instead of the full universe. Two genuine, currently-unmitigated risks a
   narrowed Stage 0 would introduce: (a) per-CIK `submissions.json` drift (name/address changes)
   with no accompanying same-day filing, invisible to `impacted_ciks`; (b) SEC daily-index
   republish after this repo's checkpoint already marked that date `succeeded` — live-evidenced
   (`company.20260710.idx` republished ~37h late) — combined with the no-`--force` cache
   short-circuit, meaning a late-corrected CIK is silently missed on every subsequent run. Neither
   is fatal but both need an explicit accept-or-mitigate decision, not silent narrowing.
4. **Operational risk is real but not yet observed in practice** — this was the *first-ever*
   execution (previously zero runs in this account), so no overlap with a "next" run has actually
   happened yet. There is also no EventBridge schedule wired to `daily_incremental` at all today
   (confirmed live: `aws events list-rules` shows no cron/rate target for it), so "runs daily" is
   currently aspirational in the name only — nobody has yet decided the actual cadence, which
   makes the overlap question premature until a schedule exists.

**Bottom line:** narrowing is architecturally possible and would reuse only already-tested code
(no new parsing/fetch logic needed), but is a genuine operator trade-off (order-of-magnitude
runtime savings vs. two specific, evidenced coverage gaps), not a pure bug fix — hence not
implemented here, per this ticket's own scope. Also incidentally resolved the ticket background's
"is the daily changes file JSON" premise: SEC never publishes daily-index content as JSON (only
`.idx`/`.xml`); the only JSON present is an auto-generated directory-file-listing, not filing
records — no fix needed in this repo's own index builder, which already targets the real format.

Status: resolved.
