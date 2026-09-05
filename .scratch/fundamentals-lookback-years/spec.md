# Spec: Bound the previously-unbounded fundamentals artifact families to a shared, overridable lookback

**Status:** ready-for-agent
**Type:** spec
**Date:** 2026-09-05
**Repo:** edgartools-platform
**Related:** [Artifact usefulness timelines (agent + investment analysis)](../artifact-usefulness-timelines/map.md) · [Ticket 08 — Lock 13F Agent Window](../artifact-usefulness-timelines/issues/08-lock-thirteenf-agent-window.md) · [Ticket 10 — Lock Proxy Agent Window](../artifact-usefulness-timelines/issues/10-lock-proxy-agent-window.md) · `docs/data-architecture.md` ("Data Point Catalog" / "Artifact Loader Date-Range Reference")

## Problem Statement

Four SEC document families — 8-K Item 2.02 (earnings), the DEF 14A/DEFA14A/PRE 14A
proxy family, 13F-HR/13F-HR-A (both the raw artifact parse and the derived
`sec_thirteenf_holding` extraction), and every ADV form — have **no lookback
control at all** in the warehouse's artifact-fetch/parse eligibility gate
(`_configured_parser_accessions`/`_is_configured_parser_form`,
`edgar_warehouse/application/warehouse_orchestrator.py`). Once an accession clears
filing-metadata discovery, these four families are always selected for
fetch/parse regardless of age — unlike Forms 3/4/5 and 8-K Item 5.02, which
already have real, tunable lookback flags (`ownership_lookback_years`,
`item_502_lookback_years`).

This was surfaced while auditing and documenting every SEC document type's
retention and date-range behavior (`docs/data-architecture.md`'s Data Point
Catalog). The operator wants every downloaded, date-ranged artifact to have a
documented and, where the artifact has a real per-filing date axis, an
enforced lookback — both to bound ongoing SEC fetch/parse cost the same way
ownership/item-502 already are, and so the documented defaults can never
silently drift from what the code actually does.

**Known, deliberate trade-off against prior work:** the already-resolved
[Artifact usefulness timelines](../artifact-usefulness-timelines/map.md) map
separately locked *Agent Decision Surface* usefulness windows of **3 years**
for 13F and **5 years** for proxy — a different question (how far back is
already-captured data still current for agent decisions) answered before this
spec existed. This spec's shared 2-year fetch/parse default is **narrower**
than those locked windows for those two families. The operator has explicitly
accepted this trade-off for now (see "Implementation Decisions" below) and
wants a per-family override mechanism specifically so the 3-year/5-year
figures can be restored independently later without redesigning anything, but
verifying or reconciling the actual downstream Agent Decision Surface impact
is out of scope for this spec (see "Out of Scope").

## Solution

Add one new shared lookback flag governing all four currently-unbounded
families, with a default of 2 years (matching the existing
`ownership_lookback_years`/`item_502_lookback_years` precedent), plus an
optional per-family override for each of the four so any one of them can be
tuned independently of the shared default without adding a new mechanism.
Update `docs/data-architecture.md`'s Data Point Catalog to reflect the new
bounded behavior (replacing "Unbounded" for these four families), and add an
automated test proving the documented defaults match the real code constants,
so the two can never silently drift apart again.

## User Stories

1. As a platform operator, I want 8-K Item 2.02 (earnings) artifacts bounded to a
   default lookback, so that ongoing `daily-incremental`/`bootstrap-next` runs don't
   fetch and parse earnings filings arbitrarily far back in a company's history.
2. As a platform operator, I want the DEF 14A/DEFA14A/PRE 14A proxy family bounded to a
   default lookback, so that proxy artifact fetch/parse cost is bounded the same way
   ownership and Item 5.02 already are.
3. As a platform operator, I want 13F-HR/13F-HR-A (both the raw artifact parse and the
   derived `sec_thirteenf_holding` extraction) bounded to a default lookback, so that
   13F fetch/parse cost is bounded consistently with the other three families.
4. As a platform operator, I want every ADV form (`sec_adv_filing`, `sec_adv_office`,
   `sec_adv_disclosure_event`, `sec_adv_private_fund`) bounded to a default lookback,
   so that ADV artifact fetch/parse cost is bounded consistently with the other three
   families.
5. As a platform operator, I want one shared default value (not four independently
   drifting defaults) for these four families, so that reasoning about "how far back
   does this platform fetch" has one number to remember for the common case.
6. As a platform operator, I want to be able to override the lookback for any one of
   the four families independently (without touching the other three or adding a new
   mechanism), so that a family-specific need discovered later — e.g. restoring 13F's
   previously-locked 3-year Agent Decision Surface window — doesn't require a redesign.
7. As a platform operator, I want `0` to mean "full history" for the shared flag and
   for every per-family override, matching the existing convention every other
   lookback flag in this codebase already uses, so the opt-out behavior is consistent
   and discoverable.
8. As a platform operator, I want the new flag(s) to be settable via both a CLI
   argument and an environment variable, matching every existing lookback flag's
   dual-input convention, so operators and Step Functions definitions can set them the
   same way they already set the existing three.
9. As a platform operator, I want `docs/data-architecture.md`'s documented date-range
   table to say "2 years (overridable)" instead of "Unbounded" for these four families
   once the code changes, so the doc reflects reality without a separate manual step
   being forgotten.
10. As a platform operator, I want an automated test that fails if the documented
    lookback-year defaults ever stop matching the real code constants, so a future
    change to any of these defaults can't silently leave the documentation wrong.
11. As a platform operator, I want the new shared flag and its per-family overrides
    threaded through the exact same gate Forms 3/4/5 and Item 5.02 already use
    (`_configured_parser_accessions`), not a second, parallel gate, so there is exactly
    one place in the codebase that decides fetch/parse eligibility by date.
12. As a platform operator, I want this change to explicitly *not* touch company
    financials (`sec_financial_fact`/`sec_financial_derived`/`sec_accounting_flag`),
    since that family's SEC `companyfacts` source has no server-side date filter and is
    already tracked as its own separate research question, so this spec doesn't
    silently make a decision that question hasn't reached yet.
13. As a future engineer reading this spec, I want the trade-off against the
    already-locked 13F/proxy Agent Decision Surface windows stated explicitly and
    linked, so I don't mistake the narrower 2-year default for an oversight rather than
    a deliberate, reversible choice.

## Implementation Decisions

- **New shared flag:** `--fundamentals-lookback-years` / env
  `WAREHOUSE_FUNDAMENTALS_LOOKBACK_YEARS`. Default **2 years**. `0` disables the window
  (full history), matching `ownership_lookback_years`/`item_502_lookback_years`/
  `filing_lookback_years`'s existing convention exactly.
- **Per-family overrides**, each optional and falling back to
  `fundamentals_lookback_years` when unset — mirroring the existing
  `item_502_lookback_years`-falls-back-to-`ownership_lookback_years` precedent
  (`_resolve_item_502_lookback_years`), not a new fallback shape:
  - `--item-202-lookback-years` / `WAREHOUSE_ITEM_202_LOOKBACK_YEARS` (8-K Item 2.02 earnings)
  - `--proxy-lookback-years` / `WAREHOUSE_PROXY_LOOKBACK_YEARS` (DEF 14A/DEFA14A/PRE 14A)
  - `--thirteenf-lookback-years` / `WAREHOUSE_THIRTEENF_LOOKBACK_YEARS` (13F-HR/13F-HR-A, both
    the raw artifact parse and `sec_thirteenf_holding`)
  - `--adv-lookback-years` / `WAREHOUSE_ADV_LOOKBACK_YEARS` (all ADV forms)
- **Single enforcement point:** `_configured_parser_accessions`/`_is_configured_parser_form`
  in `edgar_warehouse/application/warehouse_orchestrator.py` — the same gate that already
  enforces `ownership_lookback_years`/`item_502_lookback_years`. This is the one place in
  the codebase that actually controls SEC artifact-fetch HTTP calls for these families;
  nothing needs to change in `edgar_warehouse/application/workflows/fundamentals_ingest.py`
  (`bootstrap-fundamentals`'s per-filing/thirteenf modes never make their own SEC call for
  these four families — they only re-read bronze bytes this gate already decided to fetch
  or not fetch).
- **CLI surface:** add the new flags to every subparser that currently carries
  `--ownership-lookback-years`/`--item-502-lookback-years` (`daily-incremental`,
  `bootstrap-next`, `bootstrap-full`, and any other existing call site of those two flags
  in `edgar_warehouse/cli.py`) — same subparsers, same pattern, not a new subcommand.
- **Deploy-script wiring:** `infra/scripts/deploy-aws-application.sh` already threads
  `filing_lookback_years` through as a Step Functions input field with a load_history-side
  default-injection state (`FilingLookbackYearsDefault`). Whether the new flags need an
  equivalent injected-default state, or can simply rely on the CLI/env-var default when the
  Step Functions input omits them, is left as an implementation-time judgment call — follow
  whichever of the two existing patterns (`filing_lookback_years`'s injected-default state vs.
  `ownership_lookback_years`'s plain CLI-level default) the implementer determines fits, and
  note the choice in the ticket that implements this.
- **Documentation update:** `docs/data-architecture.md`'s "Artifact Loader Date-Range
  Reference" table and the "Fundamentals, Financials, and 13F" / "ADV Data" / "Filing
  Artifacts and Text" per-category tables must be updated so the four affected rows read "2
  years (overridable via `--<family>-lookback-years`)" instead of "Unbounded."
- **Explicitly out of scope for the code change:** company financials
  (`sec_financial_fact`/`sec_financial_derived`/`sec_accounting_flag`, `bootstrap-fundamentals
  --mode entity-facts`) gets no new flag in this spec — tracked separately as a research
  question (can SEC's `companyfacts` endpoint, or a sibling endpoint, be filtered at the
  metadata layer in one call?) and reference/company-profile data (ticker list, `sec_company`
  core fields, address, former-name, submission-file index) gets no lookback concept at all —
  confirmed policy is "always load SEC's latest published file, never re-walk history."

## Testing Decisions

- Only test external behavior (the real function's actual filtering decisions given real
  inputs), never internal call counts or mock-only assertions — matching this repo's own
  stated testing philosophy and the existing seam's own style.
- **Seam 1 (extend existing):** `tests/unit/test_ownership_lookback.py`'s
  `TestConfiguredParserAccessionsLookback` class already calls
  `warehouse_orchestrator._configured_parser_accessions(...)` directly against a mocked
  `db.get_filing`, proving the ownership/item-502 lookback filtering. Add a sibling test
  class in the same file (not a new file) proving: (a) each of the four new families is
  correctly excluded when older than the shared/per-family cutoff, (b) each is correctly
  included when within it, (c) a per-family override takes precedence over the shared
  default when both are set, (d) `0` disables filtering entirely for both the shared flag
  and each override, matching the existing `0`-means-unbounded tests already present for
  ownership/item-502 in this file.
- **Seam 2 (new, minimal):** a new test module (e.g.
  `tests/unit/test_lookback_year_documentation_parity.py`) that imports the real
  `DEFAULT_OWNERSHIP_LOOKBACK_YEARS`, `DEFAULT_ITEM_502_LOOKBACK_YEARS`,
  `DEFAULT_FILING_LOOKBACK_YEARS`, the new `DEFAULT_FUNDAMENTALS_LOOKBACK_YEARS` (and any
  per-family default constants added), plus `rolling_window_periods`'s `window_months=13`
  default from `adv_bulk_fetch.py`, and asserts each against an explicit, small
  "documented defaults" mapping living in the test file itself — proving the real code and
  the documented figures agree, rather than re-scraping `docs/data-architecture.md`'s
  markdown. Mirrors `tests/architecture/test_task_profile_source_of_truth.py`'s ethos:
  prove against the real thing, never a re-implementation.
- No new tests needed in `tests/mdm/` or `tests/architecture/` beyond the above two seams —
  this change doesn't touch MDM resolution or Step Functions state-machine shape, only the
  artifact-fetch eligibility gate and its CLI surface.

## Out of Scope

- Reconciling or auditing this change's actual downstream impact on the already-locked
  Agent Decision Surface usefulness windows (13F: 3 years, proxy: 5 years,
  [artifact-usefulness-timelines map](../artifact-usefulness-timelines/map.md)) is
  explicitly out of scope for this spec. The narrower 2-year default is a known, accepted
  trade-off for now, reversible per-family via the override flags this spec adds — not
  something this spec verifies is safe in practice.
- Company financials (`sec_financial_fact`/`sec_financial_derived`/`sec_accounting_flag`)
  getting any lookback control — deferred to a separate research ticket (can
  `companyfacts` be filtered at the metadata layer in one call?).
- Reference/company-profile data (ticker list, `sec_company` core fields, address,
  former-name, submission-file index) getting any lookback control — explicitly decided
  to have none; policy is "always load the latest SEC-published file."
- A periodic live-deployment re-verification ticket (checking the actual deployed Step
  Functions/ECS definitions against documented figures on a recurring cadence) — decided
  against; the automated code-constant-vs-doc test (Seam 2) is the only enforcement
  mechanism this spec adds.
- Any change to `infra/aws-prod-application.json`'s currently-deployed definitions
  themselves — this spec covers the code/CLI/doc change; redeploying is a separate,
  later step.

## Further Notes

- This spec's four families (Item 2.02, proxy, 13F, ADV) were identified via a full audit
  of every SEC document type's loader lookback behavior, captured in
  `docs/data-architecture.md`'s Data Point Catalog (see "Artifact Loader Date-Range
  Reference" and the per-category tables). That doc should be read alongside this spec for
  the full picture of which document types are bounded, unbounded, or out of scope, and
  why.
- The per-family override design intentionally mirrors
  `_resolve_item_502_lookback_years`'s existing fallback-to-`ownership_lookback_years`
  shape rather than inventing a new one — `/gof-refactor-reviewer` should be consulted
  before implementing per this repo's standing hard rule, but the precedent already
  established by that function is the expected outcome of that consult, not a new pattern
  to justify from scratch.
- If a future decision restores the 13F/proxy windows to their previously-locked 3-year/
  5-year figures, that's a one-line override-flag default change (`WAREHOUSE_THIRTEENF_LOOKBACK_YEARS=3`,
  `WAREHOUSE_PROXY_LOOKBACK_YEARS=5`), not a redesign — this was the explicit reason the
  override mechanism was requested over a single flat shared value.
