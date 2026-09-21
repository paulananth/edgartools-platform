# Fix the DEF 14A executive-record parser leaking role text into exec_name

Type: task
Status: **parser fixed 2026-09-20; not yet resolved** — resolution needs the
re-export, which is blocked by tickets 23 and 24.
Blocked by: none

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
  of three years are discarded. **Blocks the re-export.**
- [Ticket 24](24-reprocess-already-marked-fundamentals.md) — the
  `PARSER_VERSION` bump is inert: the per-filing skip is keyed on accession
  only, with no `force` path, so existing rows stay wrong. **Blocks the
  re-export.**

This ticket resolves when research 01's quality check is re-run on a
*re-exported* corpus, not on freshly parsed documents.

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
shows plausible-name rate comparable to the 8-K source (~98%).
