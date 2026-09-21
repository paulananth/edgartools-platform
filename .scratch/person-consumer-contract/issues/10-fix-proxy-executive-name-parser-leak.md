# Fix the DEF 14A executive-record parser leaking role text into exec_name

Type: task
Status: **parser fixed 2026-09-20; not yet resolved** — resolution is a full
local re-parse of bronze (see "Resolution criterion, reworded 2026-09-21").
Tickets 23 and 24, which blocked the re-export, are merged (#680, #681).
Blocked by: none

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
