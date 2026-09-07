# 16 — `sec_company_filing`'s One-Row-Per-Accession Model Silently Drops a Co-Registrant on Joint Filings

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

**Likely scope:** concentrated among large shelf-registration issuers with
wholly-owned finance subsidiaries that co-file guaranteed debt/note
programs (JPMorgan Chase Financial Co. LLC, GS Finance Corp., Morgan
Stanley Finance LLC, Wells Fargo Finance LLC, and similar structures), not
spread uniformly across the table. Not yet quantified against the full
~2M-row table — the 18/500 figure is from one reconciliation cohort sample
only.

**What to build:** not yet decided — this ticket is scoped to *deciding*
the fix, not applying one. Candidate directions, none evaluated in depth:

- Widen `sec_company_filing`'s business key to `(accession_number, cik)` so
  every co-registrant gets its own row — the most structurally correct fix,
  but touches every downstream reader that currently assumes one row per
  accession (bronze-to-silver key expectations, MDM's filing-identity
  lookups, gold/dbt models, the reconciliation contract itself) and is a
  real schema migration on a multi-million-row table.
- Leave the one-row model but make "which co-registrant wins" deterministic
  (e.g. always the numerically lowest CIK) so DuckDB and Snowflake at least
  agree with each other, accepting that the losing co-registrant's
  file_number/film_number/act are simply unrepresented.
- Something else — needs a real decision session, not a unilateral pick.

**Blocked by:** none — independent of Ticket 11/12's remaining scope; does
not block the DuckDB retirement cutover's own completion.

**Status:** open

- [ ] Quantify the true scope: how many accessions in the full table are
      shared across 2+ CIKs, not just the 18/500 sampled
- [ ] Decide the fix direction (see candidates above) with the user
- [ ] Implement, test, and confirm via a live reconciliation rerun that
      `sec_company_filing`'s semantic-content digest passes cleanly for a
      cohort that specifically includes known co-registrant accessions
