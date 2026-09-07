# 16 — `sec_company_filing`'s One-Row-Per-Accession Model Silently Drops a Co-Filer (Co-Registrants and Ownership Filings Alike)

**What was found:** Live during [Ticket 11](11-post-cutover-reconciliation-gate.md)'s
post-cutover reconciliation run, `sec_company_filing`'s semantic-content
digest failed with 18 of 500 sampled rows (~3.6%) showing genuinely
different `cik`/`file_number`/`film_number`/`act` values between DuckDB
canonical and Snowflake — not a reconciliation-tool false positive (ruled
out by fetching the actual rows from both stores directly) and not a
freshness-lag artifact (both sides had already synced past the compared
watermark).

**Root cause, confirmed with a concrete example:** accession
`0001839882-25-068615` is a `424B3` prospectus jointly filed by **JPMorgan
Chase & Co.** (CIK `19617`) and its wholly-owned finance subsidiary
**JPMorgan Chase Financial Co. LLC** (CIK `1665650`) — a standard
guaranteed-notes shelf-registration pattern where SEC lets one accession
number cover multiple co-registrants, each with its own `file_number` suffix
(`333-270004` vs `333-270004-01`) and adjacent `film_number` (`251536624` vs
`251536625`).

`sec_company_filing`'s schema (`silver_store.py`) declares
`accession_number` as the sole primary key — one row per accession, full
stop. When SEC legitimately associates one accession with two (or more)
CIKs, whichever CIK's own submissions feed this pipeline processes first
"wins" the row; the other co-registrant's version of that same accession is
silently discarded. Because DuckDB canonical and Snowflake's independent
ingestion paths don't necessarily process the same CIK's submissions feed
first, the two stores can each land on a **different, individually valid**
co-registrant's data for the same accession — nondeterministic, and neither
side is "wrong" in isolation, but they disagree with each other and neither
represents the complete filing.

**Why this wasn't caught before:** `sec_company_filing`'s reconciliation
contract (`table_reconciliation/contracts.py`) — like every consumer of
this table — assumes one accession maps to one company. Nothing before
Ticket 11's cross-store content digest ever compared the *same* accession's
row across two independently-populated stores, so a co-registrant
collision had no way to surface: within either store alone, the row looks
complete and unremarkable.

**Scope quantified (2026-09-06): far larger than first estimated, and
dominated by a different, more common filing pattern than co-registrant
shelf debt.** A 20,000-key cohort sample (up from the original 500,
correctly scoped to Snowflake's own authority-column watermark) found
**659 mismatched accessions (3.29%)** — consistent with the original
18/500 (3.6%) sample, extrapolating to roughly **~209,600 accessions**
across the full 6,360,796-row in-scope population (6,524,919 total rows
today). Breaking the 659 down by shape:

| Shape | Count | % |
|---|---|---|
| Genuine co-registrant (both sides complete, differ) | 181 | 27.5% |
| DuckDB row NULL-heavy (file/film#/act null, Snowflake has them) | 277 | 42.0% |
| Snowflake row NULL-heavy (reverse) | 184 | 27.9% |
| Other/ambiguous | 17 | 2.6% |

**The NULL-heavy majority (~70% of mismatches) is not corporate
co-registrant shelf debt — it's ordinary Form 3/4/5/144 ownership
filings.** Checked the actual `form` values and cross-referenced the
colliding CIKs against `sec_company`: every NULL-heavy example checked
pairs an issuer (e.g. `PENSKE AUTOMOTIVE GROUP, INC.`, `MYOMO, INC.`,
`REVVITY, INC.`) with an *individual* reporting owner (`Davis Lisa Ann`,
`Mitchell Micah`, `Michas Alexis P`) on forms `4`/`144`. SEC lists the same
Form 4/144 accession under **both** the issuer's and the insider's own
submissions feed — exactly the same one-row-per-accession collision as the
JPMorgan co-registrant case, just via a completely different, vastly more
common real-world mechanism. Forms 3/4/5/144 alone are **36.27%** of all
`sec_company_filing` rows (2,366,533 of 6,524,919) — this is not a rare
corner case confined to a handful of large financial issuers, it is a
structural gap that potentially touches every ownership filing in the
table. Notably, `sec_ownership_reporting_owner` (which correctly models
multi-owner filings via `owner_index`) has **zero rows** for the sampled
NULL-heavy accessions in DuckDB — the ownership-detail parse and this
filing-index collision appear to be two separate gaps, not one; not
investigated further here.

**Revises the original "likely scope" framing** (which guessed this was
concentrated among large shelf-registration issuers with finance
subsidiaries) — that pattern is real and accounts for the ~181 genuine
co-registrant cases, but is a minority of the total. The true common
thread across all three shapes is broader: *any* accession SEC associates
with 2+ CIKs (an issuer + a co-registrant, or an issuer + an individual
reporting owner) collides in this table's one-row-per-accession model.

**Fix direction decided and implemented (2026-09-07):** Snowflake-only
(DuckDB's `sec_company_filing` keeps `accession_number` as its sole PK —
out of scope per the user's own decision; DuckDB structurally cannot
represent a widened row, so it's a hard boundary, not just a scope choice).

**First attempt (reverted): "issuer preference" via file_number
nullness.** Hypothesized that for the ownership-filing case, exactly one
associated CIK carrying a non-null `file_number` cleanly identified the
issuer (keep that row) vs. widening for the co-registrant/ambiguous case.
**Empirically disproven live** against 3 real accessions
(`0000899243-17-027795` Revvity/Michas, `0001019849-24-000140`
Penske/Davis, `0001839882-25-068615` JPMorgan co-registrant): the
co-registrant case worked as intended, but **both tested ownership cases
had the signal backwards** — the confirmed issuer's own CIK carried the
NULL `file_number` and would have been dropped, while the individual
reporting owner's CIK carried the real `file_number` and would have been
kept. A broader 30-accession sample confirmed the "exactly one side has
file_number" split holds consistently, but there is no reliable way to
tell *which* side is the issuer from that signal alone — it's an artifact
of which filer's own SEC submissions feed happened to populate the field,
uncorrelated with issuer-vs-individual. A second candidate signal
(cross-referencing `owner_cik` against `sec_ownership_reporting_owner`)
was also tried and found unreliable (missed a confirmed individual, false-
positived on a genuine corporate co-registrant). A third candidate
(entity-name-in-`sec_company` as an issuer/individual discriminator) was
ruled out directly — individuals get `sec_company` rows too.

**Final design: widen unconditionally, disambiguate downstream at MDM's
join sites.** `sec_company_filing.sql` no longer tries to pick a winner at
all — it keeps one row per `(accession_number, cik)` for *every* multi-CIK
accession, co-registrant and ownership alike. The key insight (from
review): today's pre-fix behavior (`first-insert-wins` by `parse_sequence`)
already nondeterministically picked either CIK for MDM's `issuer_cik` —
this change doesn't introduce that risk, it makes the *correct* resolution
possible for the first time, by pushing disambiguation to where a reliable
signal actually exists. At every MDM join site that reads
`sec_company_filing` from an ownership row (which always carries its own
`owner_cik`), the issuer is unambiguously "whichever cik is NOT this row's
own owner_cik" — complete for the entire population MDM cares about, since
those joins originate from the ownership tables.

**Implementation:**
- `infra/snowflake/dbt/edgartools_gold/models/silver/sec_company_filing.sql`
  simplified from a 4-CTE issuer-preference design back down to 2 CTEs
  (`per_cik`/`last_seen`) — unconditional widening, no winner-picking.
- `filing_activity.sql`/`filing_detail.sql`'s surrogate keys widened to
  `surrogate_key(['accession_number', 'cik'])` (now unconditionally needed,
  not contingent on the narrow co-registrant case) — validated live via a
  rewritten `_filing_activity_unit_tests.yml` unit test (passes against
  real Snowflake).
- `edgar_warehouse/mdm/sql_fragments.py` (new): a shared
  `prefer_non_owner_cik_qualify(partition_cols)` helper returning a
  `QUALIFY ROW_NUMBER() OVER (PARTITION BY ... ORDER BY CASE WHEN f.cik =
  o.owner_cik THEN 1 ELSE 0 END) = 1` fragment — falls back to whatever
  single match exists when there's no non-self-referential candidate, so
  no previously-working single-CIK case regresses. Applied at all 9 real
  join sites across `edgar_warehouse/mdm/pipeline.py` (6:
  `_derive_is_insider`, `_derive_holds` x2 branches, `_derive_company_holds`
  x2 branches, `run_securities` x2 branches, `run_persons`,
  `backfill_security_issuers` x2 branches — some needed a new join to
  `sec_ownership_reporting_owner` just to get `owner_cik` into scope) and
  `edgar_warehouse/application/relationship_bulk_load.py`'s
  `insider_inventory`. `edgar_warehouse/mdm/coverage.py`'s `security_silver`
  coverage-gap count needed a different fix (a `DISTINCT` wrapper, not
  QUALIFY — it doesn't project `f.cik` at all, so widening only risked
  double-counting, not wrong identity); its other 2 similar sites were
  confirmed already safe.
- Extraction to a shared helper (rather than duplicating the QUALIFY text
  9 times) was itself run through `/gof-refactor-reviewer` given `git log`
  evidence that `pipeline.py` specifically has a documented history of this
  exact "same fix ported to some sibling call sites but not others" failure
  shape recurring — verdict: real, evidenced risk, worth the extraction.

**Validated live against real production Snowflake data, not just
compiled:** confirmed a real widened accession
(`0002007998-25-000011`) produces the wrong self-referential row
(`issuer_cik = owner_cik = 2007998`, the individual Dorria L. Ball) when
joined without the fix, and exactly the correct row
(`issuer_cik = 1530979`) with it. `dbt compile` clean for
`sec_company_filing`/`filing_activity`/`filing_detail`; the rewritten
`filing_activity` unit test passes live; full Python test suite green
(666 tests across `tests/mdm/`, `tests/application/test_relationship_bulk_load.py`,
`tests/unit/test_insider_only_loader.py` — none of which can exercise the
actual widened-row shape, since DuckDB's own `sec_company_filing` PK
structurally prevents it; the live Snowflake validation above is the real
proof for that shape).

**Not yet done:** `dbt run --full-refresh` against live prod (a real
production action — needs explicit confirmation before running, not yet
requested this session). Committing to a branch + PR first.

**Blocked by:** none — independent of Ticket 11/12's remaining scope; does
not block the DuckDB retirement cutover's own completion.

**Status:** implemented and validated live, not yet deployed to prod

- [x] Quantify the true scope: ~209,600 accessions extrapolated (3.29% of
      6.36M in-scope rows), not the originally-assumed narrow corner case
- [x] Decide the fix direction: widen unconditionally + fix MDM joins
      (issuer-preference winner-picking tried first, empirically disproven,
      reverted)
- [x] Implement and validate live against real Snowflake data (both the
      dbt model and all MDM join sites)
- [ ] Run `dbt run --full-refresh` against prod (needs explicit go-ahead)
- [ ] Confirm via a live reconciliation rerun that `sec_company_filing`'s
      semantic-content digest passes cleanly for a cohort that specifically
      includes known multi-CIK accessions post-deploy
