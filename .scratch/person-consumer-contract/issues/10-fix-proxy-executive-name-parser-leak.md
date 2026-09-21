# Fix the DEF 14A executive-record parser leaking role text into exec_name

Type: task
Status: resolved (2026-09-21) — full local re-parse of bronze; the production
re-export stays deferred. Residues found by the re-parse: [ticket 26](26-strip-footnote-markers-and-title-fragments-from-proxy-names.md).
Blocked by: none

## Resolution — the full bronze re-parse (2026-09-21)

Every proxy filing in the S3 bronze bucket was run through the production
parser (`parse_proxy_fundamentals`, `PARSER_VERSION="2"`) on this machine.
The run made **zero SEC requests**: its DNS guard logged exactly one host, the
bronze bucket, for 503,197 lookups. It made no Snowflake connection.
Script: [`research/10-reparse-bronze.py`](../research/10-reparse-bronze.py).
Results: [`research/10-reparse-results.json`](../research/10-reparse-results.json).

**What "every" means.** Bronze holds 26,214 accessions with an HTML primary
document, from 4,437 CIKs. Each accession's form was read from bronze, never
from the file name:
- 20,200 from the company's `submissions.json` (recent block, then pagination);
- 6,006 from SEC's daily `form.idx` files captured in bronze (75 days, 17
  April to 14 September 2026). These are August–September filings newer than
  the company's last snapshot;
- 8 remain unknown (July 2026 uploads), 0.03%.

The scope is the four forms the pipeline routes to this parser: **9,254
filings**, being 3,806 DEF 14A, 997 PRE 14A and 4,451 DEFA14A. The listing is
6.06 GB, the same 510,649 filing objects as on 20 September.

| | |
|---|---|
| filings parsed / parse errors | 9,254 / **0** |
| filings with a Summary Compensation Table | 2,212 |
| raw SCT entries (edgartools) | 18,044 |
| dropped by the repair as unattributable | 575 |
| landing rows → **collapsed** (#680 rule: latest per cik, accession, fiscal year, name) | 17,469 → **17,371** |
| **research 01's check** (no role vocabulary, ≥ 2 tokens) | **17,204 / 17,371 = 99.04%** |
| research 10's check (the 149-document sample's measure) | 99.85% after; **48.1%** before the repair |
| hand-read sample, 60 rows, seed 20260921 | right executive **60 / 60**; name clean **54 / 60** |

**The criterion is met.** The target was comparable to the 8-K source (~98%),
and the result is 99.04% on the whole bronze corpus. The hand-read sample
([`research/10-hand-read-sample.json`](../research/10-hand-read-sample.json),
with a verdict on every row) checks the one thing the score cannot:
attribution. In all 60 rows, the kept name is an executive in that filing's
table with a consistent role.

**What the score tolerates, measured, and ticketed rather than waved away**
([ticket 26](26-strip-footnote-markers-and-title-fragments-from-proxy-names.md)):
- footnote markers left on the name, in 462 rows (2.66%), e.g. `Jeff Zhu(1)`;
- trailing title fragments, in 128 rows (0.74%), e.g. `Chi-Foon Chan Co-`;
- the 167 rows (0.96%) the check still rejects, e.g. `VP/`, `SEVP`, `Member
  of the`.

The first residue matters for DEF 14A's own Tier B measurement: a digit takes
the name out of the `person-name@v2` shape.

## Resolution criterion, reworded 2026-09-21 (operator)

**This ticket is resolved locally, against bronze. No Snowflake, no AWS
compute, no deploy.** Operator direction: the pipeline re-export is not taken
until every bit of code is written and tested locally. Snowflake is suspended
and will not be restored, and the re-export's filing list, marker table,
landing load and dbt collapse all live there, so the re-export cannot be the
finish line.

Resolved when, on this machine:

1. Every DEF 14A primary document in the S3 bronze bucket is parsed with the
   fixed parser (`parse_proxy_fundamentals`, `PARSER_VERSION="2"`) — bronze
   reads only, **zero SEC requests**, no Snowflake connection.
2. The rows are collapsed exactly as the dbt silver model now does it
   (`sec_executive_record.sql`, #680: latest per `(cik, accession_number,
   fiscal_year, exec_name)`), so the count reflects what silver would hold.
3. Research 01's quality check (no role vocabulary in the field, at least two
   tokens) runs on that collapsed set and the plausible-name rate is
   comparable to the 8-K source (~98%), reported with n and the drop count.
   Because the judge's vocabulary overlaps the parser's own, a hand-read
   random sample of kept names (with the executive's row in the filing) is
   reported alongside, as the attribution check the rate cannot give.
4. The script and its results are committed under `research/10-*`, with
   the bronze object count scanned and the count of documents with a
   Summary Compensation Table.

**Deferred, not part of this ticket**: the production re-export. It is the
first thing to run once the platform is deployed again, and only after the
code for every open ticket is written and tested locally. Its sequence is
kept below for then; step 1's pre-flight is already answered (no writer has
ever targeted `sec_executive_record` in the retirement table, #680).

## What was done (2026-09-20)

`edgar_warehouse/parsers/proxy_fundamentals.py` now repairs the names
edgartools returns, with 27 unit tests
(`tests/unit/test_proxy_fundamentals.py`, the file had none before).
`PARSER_VERSION` 1 → 2.

**Three layouts, not one.** Research 12's mechanism (the position wraps onto
the *following* rows and is carried forward as the name) is real, but sampling
real filings found two more, and the first implementation — which passed every
fixture built from research 12 alone — collapsed three Apple executives onto
Tim Cook:

| Layout | Example cell | Handling |
| --- | --- | --- |
| Position wraps to later rows | `Chairman of the` / `Board and Chief` | carried forward to the executive whose block it is; title reassembled |
| Name and position share a cell | `Luca Maestri Senior Vice President` | name ends where the position begins |
| No separator at all | `Andreas G. FrankExecutive`, `Martin RaffieldSVP Operations` | split at a lower-to-upper boundary before a position word |

**Measured against the acceptance criterion** (research 01's check: no role
vocabulary in the field, at least two tokens), on 149 DEF 14A primary
documents sampled from prod bronze, 65 of which contain a Summary
Compensation Table:

| | plausible names |
| --- | --- |
| before (edgartools as-is) | 240/494 = **48.6%** |
| after the repair | 485/485 = **100%** (9 rows dropped as unattributable) |

Target was "comparable to the 8-K source (~98%)". Evidence:
[`research/10-measure-repair.py`](../research/10-measure-repair.py),
[`research/10-measure-results.json`](../research/10-measure-results.json).
**Read that score honestly**: the judge's vocabulary overlaps the parser's
own, so it proves the repair strips recognisable role text, not that the name
it kept belongs to the right executive. Attribution is covered by the unit
tests and by reading real before/after output.

Two defects were caught by measuring rather than by testing: the first design
collapsed executives onto one person, and the camel-boundary regex was
case-insensitive, splitting **Franco** at "co" and **Whitehead** at "head".
Both have regression tests.

Three-axis `/code-review` run (Standards, Spec, GoF). GoF: no finding.
Applied: the defensive `try/except` around the repair plus a non-dataclass
test, a documented ASCII/diacritic limitation, and a cross-reference between
the two vocabularies. Escalated instead of silently accepted:

- [Ticket 23](23-fix-executive-record-collapse-key.md) — **the fix makes a
  pre-existing collapse-key defect bite.** The dbt silver model keeps one row
  per `(cik, accession_number, exec_name)` while the landing key includes
  `fiscal_year`. Corrupted names used to differ per row, so all three fiscal
  years survived under three wrong keys; correct names share one key, so two
  of three years are discarded. **Resolved, #680.**
- [Ticket 24](24-reprocess-already-marked-fundamentals.md) — the
  `PARSER_VERSION` bump is inert: the per-filing skip is keyed on accession
  only, with no `force` path, so existing rows stay wrong. **Resolved, #681.**

*Superseded 2026-09-21:* "This ticket resolves when research 01's quality
check is re-run on a *re-exported* corpus, not on freshly parsed documents."
The criterion is now the full local bronze re-parse above. It stays a
*collapsed* corpus, not a pile of freshly parsed rows: the local run applies
the dbt collapse, which is what that sentence was protecting.

**Deferred production re-export sequence** (not part of this ticket's
resolution; run when the platform is deployed again, after all code is
written and tested locally). Operator action, in this order, silver before
gold:

1. Pre-flight: `select count(*) from
   EDGARTOOLS_SILVER_LANDING.SILVER_LANDING_RETIREMENT where
   lower(target_table) = 'sec_executive_record'` returns 0 (ticket 23 item 3).
2. `edgar-warehouse bootstrap-fundamentals --mode per-filing --force` over the
   DEF 14A-bearing CIK scope — re-parses every marked accession at
   `PARSER_VERSION="2"` and lands new rows at a higher `parse_sequence`.
3. `dbt run --select sec_executive_record executive_records --full-refresh`
   — the collapse-key change is a SQL-body change, so plain `dbt run` is a
   silent no-op.
4. Re-run research 01's quality check on the collapsed silver and compare
   the plausible-name rate to the 8-K source.

## Question

Nothing to decide on this map. Research 01 found 47% of
`sec_executive_record.exec_name` values are role vocabulary ("Chairman of
the", "President and Chief", "Executive Officer") and the top "names" by
issuer count are job titles. **Corrected by research 12**: the platform's
`edgar_warehouse/parsers/proxy_fundamentals.py:108` copies `entry.name`
verbatim from the *edgartools* PyPI package (5.30.0,
`edgar/proxy/html_extractor.py:857-864`), whose row walk overwrites the
current name with wrapped title fragments on multi-year compensation
blocks. Two repair points: upstream in edgartools, or a platform-side
carry-forward in `proxy_fundamentals.py:100-118`. See
[research 12](../research/12-proxy-executive-person-pipeline.md) for the
mechanism and a proposed test. Note research 12 F8: the per-filing fetch
has no `--force`, so a parser fix alone will not re-parse already-marked
accessions. Until fixed, the proxy source cannot participate in any Person
binding rule (ticket 02 treats it as review-only evidence).

This is production parser code: it needs its own branch, the mandatory
`/gof-refactor-reviewer` consult, the three-axis `/code-review`, and a
re-export before research 01's proxy figures can be re-measured. Whoever
owns `edgar_warehouse/parsers/` takes it; this map only needs the fixed
export to exist. Resolved when a re-run of research 01's quality check
shows plausible-name rate comparable to the 8-K source (~98%). *(Superseded
2026-09-21 by the local bronze criterion at the top of this ticket.)*
