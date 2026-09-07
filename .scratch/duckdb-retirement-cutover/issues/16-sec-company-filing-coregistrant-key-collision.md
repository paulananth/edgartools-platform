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

**What to build:** still not decided — the corrected scope changes the
calculus for which fix direction makes sense. Candidate directions:

- Widen `sec_company_filing`'s business key to `(accession_number, cik)` so
  every associated CIK gets its own row — the most structurally correct
  fix, but now clearly a much bigger migration than first scoped (up to
  ~210K accessions could each gain a second row, disproportionately driven
  by the ownership-filing case) and touches every downstream reader that
  assumes one row per accession.
- Keep one row per accession, but make the choice of *which* CIK's version
  wins deterministic **and** semantically meaningful: for the ownership-
  filing case specifically, prefer the issuer/company CIK over an
  individual reporting-owner CIK (distinguishable via `sec_company`, or via
  whichever CIK also appears as a company in other tables) — this would
  resolve ~70% of mismatches with a principled rule rather than an
  arbitrary tie-break, since `sec_company_filing` is conceptually a
  per-company filing index, not a per-filer one. The remaining
  co-registrant shelf-debt case (~28%) has no such natural "correct" side
  and would still need an arbitrary but at-least-deterministic tie-break
  (e.g. lowest CIK) so DuckDB and Snowflake at least agree with each other.
- Something else — needs a real decision session, not a unilateral pick.

**Blocked by:** none — independent of Ticket 11/12's remaining scope; does
not block the DuckDB retirement cutover's own completion.

**Status:** open — scope quantified, fix direction still needs a decision

- [x] Quantify the true scope: ~209,600 accessions extrapolated (3.29% of
      6.36M in-scope rows), not the originally-assumed narrow corner case
- [ ] Decide the fix direction (see candidates above) with the user
- [ ] Implement, test, and confirm via a live reconciliation rerun that
      `sec_company_filing`'s semantic-content digest passes cleanly for a
      cohort that specifically includes known multi-CIK accessions (both
      the ownership-filing and co-registrant shapes)
