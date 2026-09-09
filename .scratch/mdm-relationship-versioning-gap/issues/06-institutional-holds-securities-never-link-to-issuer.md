Type: task
Status: resolved

## Question

Should `INSTITUTIONAL_HOLDS` derivation (`_ensure_security_by_cusip`,
`edgar_warehouse/mdm/pipeline.py:3271`) link the CUSIP-stub securities it
creates to their issuer `MdmCompany` row, and if so, how -- given 13F
holdings report issuer identity as CUSIP + free-text `issuer_name`, with no
shared key against the Form-4-derived security universe?

Note: this is a distinct root cause from this map's main quarantine-versioning
finding (Tickets 01-05) -- an entity-resolution completeness gap (a missing
FK link), not a relationship-instance conflict/quarantine bug. Filed here at
the user's direction since it surfaced from the same investigation thread
(INSTITUTIONAL_HOLDS derivation, mdm-run-throughput Ticket 07's CUSIP work)
rather than because it shares the destination.

## Context

Confirmed live in prod MDM Postgres, 2026-09-08. `_ensure_security_by_cusip`
creates a `MdmSecurity` stub with `canonical_title`/`cusip`/`security_class`
but never sets `issuer_entity_id` -- neither on the create path nor the
existing-lookup path (full function body confirms no `issuer_entity_id`
reference anywhere).

**All 1,718 CUSIP-stub securities in prod have `issuer_entity_id = NULL`
(100%)** -- confirmed via
`SELECT (issuer_entity_id IS NOT NULL), count(*) FROM mdm_security ms JOIN
mdm_entity me ON me.entity_id = ms.entity_id WHERE me.resolution_method =
'cusip_stub' GROUP BY 1` -> `(False, 1718)`.

Concrete example (Apple, cik=320193, `MdmCompany.entity_id=478fcda2-...`):

| security | cusip | issuer_entity_id | resolution_method |
|---|---|---|---|
| Common Stock [f1] | NULL | `478fcda2-...` (correct) | `issuer_title_dedup` (Form 4) |
| Common Stock | NULL | `478fcda2-...` (correct) | `issuer_title_dedup` (Form 4) |
| Restricted Stock Unit [f1] | NULL | `478fcda2-...` (correct) | `issuer_title_dedup` (Form 4) |
| Apple Inc. | `037833100` | **NULL** | `cusip_stub` (13F) |

The 13F-derived "Apple Inc." security and the three Form-4-derived
securities represent the same real-world issuer's securities but are
disconnected `mdm_security` rows with no relationship between them.

**Why the obvious fixes don't trivially work:**
- The only existing issuer-linking mechanism, `backfill_security_issuers`
  (`pipeline.py:2496`), matches securities to issuers by `canonical_title`
  against Form-4 `security_title` text ("Common Stock", "Restricted Stock
  Unit", etc.) -- a 13F stub's `canonical_title` is the issuer's *name*
  ("Apple Inc."), never a Form-4-style security-title string, so this
  mechanism structurally cannot match a CUSIP-stub security.
- Cross-referencing by CUSIP itself isn't viable either: confirmed via
  `SELECT resolution_method, count(*), count(*) FILTER (WHERE cusip IS NOT
  NULL) ... GROUP BY 1` that **zero** Form-4-derived (`issuer_title_dedup`)
  securities have a `cusip` value populated at all -- the ownership silver
  tables (`sec_ownership_non_derivative_txn`/`_derivative_txn`) have no
  `cusip` column in their schema (`silver_store.py` -- only
  `sec_thirteenf_holding` carries one), so there is no shared CUSIP key
  between the two security universes today.
- `issuer_name` (13F's free-text issuer name) is currently used only to set
  `canonical_title` on the stub (`pipeline.py:3361`) -- never used to look
  up or match against `MdmCompany.canonical_name` anywhere in the codebase
  (confirmed via grep, no other reference exists).

**Downstream consequence:** `_derive_issued_by` (`pipeline.py:2473`) only
processes securities with `issuer_entity_id IS NOT NULL`, so every
13F-derived CUSIP-stub security -- funds/ETFs and any issuer without
SEC-reporting insiders included -- is permanently excluded from `ISSUED_BY`,
and any "which company issued this security" traversal (including the
graph) dead-ends at an orphan security node for these holdings.

## Answer

Researched all three candidates before deciding:

- **Populate CUSIP on Form-4 securities: ruled out.** Confirmed against
  edgartools' own `Ownership` model (`from edgar.ownership import Ownership`)
  that Form 3/4/5 XML carries no CUSIP field at all -- not a missing silver
  column, the source data simply doesn't have it. This path would need an
  external CUSIP-to-CIK crosswalk this system doesn't have.
- **Fuzzy-match issuer_name against company name: chosen**, confirmed with
  the user (asked initially for "fuzzy match + real NLP/NER" -- clarified
  and confirmed that NER doesn't apply here, since `issuer_name` is already
  a clean, pre-extracted company-name string, not raw prose needing entity
  extraction; MDM's existing Jaro-Winkler fuzzy-name matcher is the
  closest thing this codebase has to "real" name-matching infrastructure,
  and reusing proven infrastructure over adding a new ML dependency is the
  safer choice for golden entity-linkage data).
- Accept-the-gap: superseded by the above once B was ruled out and the
  user confirmed A.

**Implementation:** new module `edgar_warehouse/mdm/security_issuer_link.py`
reuses the existing `edgar_warehouse/mdm/match.py` `FuzzyNameMatcher` and the
already-seeded `('company', 'fuzzy_name')` threshold
(`002_seed_data.sql`, auto_merge_min=0.95, review_min=0.85) -- not a new,
unproven threshold pair, since the entity being matched genuinely IS a
company. This is that matcher's first real multi-candidate production
exercise: `CompanyResolver`'s own use scopes candidates by exact CIK
(at most one candidate, "rarely needed" per its own docstring); `issuer_name`
carries no CIK to narrow by, so this compares against the whole company
universe, fetched once per run (bulk-prefetch, not per-security).

- **Write-time fix**: `_ensure_security_by_cusip`'s CREATE path (`pipeline.py`)
  now scores `issuer_name` and sets `issuer_entity_id` on AUTO_MERGE. Only
  the create path, not the existing-lookup opportunistic-backfill branch --
  deliberately, to keep that already-long function's per-call cost bounded;
  already-existing orphans are corrected by the dedicated backfill instead.
- **Backfill** for the 1,718 already-orphaned securities: `mdm
  backfill-security-issuer-links --dry-run`, mirroring Ticket 05's exact
  shape in this map. Scoped to `resolution_method = 'cusip_stub'` exactly,
  matching this ticket's own live diagnostic query.
- REVIEW-tier candidates (score in `[review_min, auto_merge_min)`) are
  deliberately NOT written to `mdm_match_review` -- that table's
  `accept_review` always calls `_merge_entities` (merge one entity into
  another), correct for its real use (deduping two same-type entities) but
  destructively wrong here (a security-to-company FK link is not a dedup).
  Logged only, for manual follow-up. Below review_min: left untouched, no
  log noise for a near-certain non-match.

## Code review

Ran the mandatory 3-axis review as 3 parallel subagents (Standards, Spec,
GoF). Real findings, all fixed before commit:

- **Standards + GoF independently converged** on the same finding: the
  REVIEW-tier structured-log block was duplicated verbatim between
  `resolve_issuer_entity_id` and `backfill_missing_issuer_links` -- in a
  brand-new file, in the same commit, no history to excuse it. Extracted
  `_log_review_candidate()`.
- **Spec** caught a real, undiscussed scope-creep: `backfill_missing_issuer_links`'s
  query was `issuer_entity_id IS NULL AND cusip IS NOT NULL`, no
  `resolution_method` filter -- broader than this ticket's own live
  diagnostic (`resolution_method = 'cusip_stub'`). Currently equivalent in
  practice (confirmed live: zero Form-4 securities have `cusip` populated),
  but an unstated widening of blast radius nonetheless. Narrowed to match
  the spec exactly (joins `MdmEntity`, filters on `resolution_method`).
- **Spec** also caught the most important finding: the user's original
  direction asked for "fuzzy-match + real NLP/NER," and only fuzzy matching
  was implemented -- a scope reduction I made unilaterally rather than
  confirming. Went back to the user with the reasoning (issuer_name is
  already a clean name field, not raw text needing NER extraction; no
  NER/embedding library exists anywhere in this codebase); user confirmed
  fuzzy-match-only is correct.
- Missing test gap (Spec): `backfill_missing_issuer_links` itself (not just
  the pure `resolve_issuer_entity_id` function) had no REVIEW-tier test at
  the integration level. Added.
- **GoF** noted (not blocking, logged as a follow-up, not fixed here): no
  operator-visible counters for `linked`/`review_logged`/`skipped_no_match`
  in the main `derive_relationships` per-run summary -- only the standalone
  backfill CLI's own summary reports them. A systematic false-link problem
  at this new, larger candidate-pool scale would currently be invisible
  short of directly auditing `issuer_entity_id` in Postgres. Left as an
  explicit gap for a future ticket, not this one.
- **GoF** also confirmed: no schema change, additive-only DB writes,
  correctly avoids the destructive `accept_review()` merge path.

**Separately found while executing Ticket 05's real backfill in prod during
this same session** (not part of this ticket's own scope, but discovered
along the way): `confirmed_chronologically_after` (`graph.py`, shared by
Ticket 05's backfill and the already-deployed `_deactivate_if_properties_changed`)
used `>=` instead of strict `>`, which crashed on a same-day supersession
against the DB's own `ck_rel_instance_valid_interval` check constraint
(requires strictly `>`). Fixed and documented in Ticket 05's own file, not
here, since it's that ticket's function -- noted here only because it was
found during this ticket's session, not because it's in this ticket's scope.

Tests: 16 new in `tests/mdm/test_security_issuer_link.py` (pure-function
matching/resolution cases, `load_company_candidates`, and
`backfill_missing_issuer_links` integration cases including the
resolution_method scoping and REVIEW-tier logging), plus 1 new end-to-end
test in `tests/mdm/test_pipeline_relationships.py` proving the write-time
wiring through `derive_relationships(["INSTITUTIONAL_HOLDS"])`. Full
`tests/mdm/` suite green (739 passed, including the separately-discovered
`confirmed_chronologically_after` fix's own 6 new tests).

**Not yet deployed.** The backfill has not been run against real prod
(1,718 already-orphaned securities) -- needs its own explicit go-ahead,
same pattern as Ticket 05.
