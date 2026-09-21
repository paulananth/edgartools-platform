# Strip footnote markers and title fragments from DEF 14A executive names

Type: task
Status: open
Blocked by: none — blocks DEF 14A's own Tier B measurement (backfill wave 4)

## Question

Nothing to decide; found by [ticket 10](10-fix-proxy-executive-name-parser-leak.md)'s
full local re-parse of bronze (`research/10-reparse-results.json`,
`research/10-hand-read-sample.json`).

Ticket 10's repair takes DEF 14A names from 48.1% to **99.04%** plausible
under research 01's check across all 17,371 collapsed rows in bronze, and the
hand-read sample finds the right executive in 60 of 60 rows. However, that
check tolerates two residues that the hand-read sample caught in 6 of 60 names:

1. **Footnote markers left on the name**: **462 rows (2.66%)**, for example
   `Jeff Zhu(1)`, `Aman Narang (4)`, `Elena Gomez (5)`, `R. Bryan Riggsbee (⁸)`.
   A digit in the name puts it outside the `person-name@v2` shape (ticket 25),
   so these executives are dropped from Tier B entirely. `_strip_name_markers`
   exists but does not reach the layouts where the marker is glued to the
   title (`Jason Dies(1)Interim`) or separated by a space.
2. **Trailing title fragments**: **128 rows (0.74%)**, for example
   `Chi-Foon Chan Co-`, `TED SARANDOS co-`, `Lori Bisson -`. They are the
   first half of "Co-CEO" or "- Chief …" cut at the name/title boundary.
3. **Remaining role text**: 167 rows (0.96%, 72 distinct values) that research
   01's check does reject. They include `VP/`, `V.P.`, `SEVP` and `Technoking`
   after a name, and wrapped fragments such as `Member of the` and `of UMI`.
   See `remaining_implausible_top` in the results.

`person-name@v2` currently accepts 93.1% of these rows as person names. These
three residues are most of the gap.

## What to do

In `edgar_warehouse/parsers/proxy_fundamentals.py`:
- strip parenthesised or superscript footnote markers wherever they sit;
- treat a trailing `Co-` or a lone trailing `-` as the start of the title;
- add `VP/`, `V.P.` and `SEVP` to the title vocabulary.

Test each with the real names above. Bump `PARSER_VERSION`, then re-run
`research/10-reparse-bronze.py parse` and `score` (the downloads are cached,
so this is about 20 minutes).

Resolved when the re-parse shows footnote-marker and fragment residues at 0
(or each remaining one explained), with research 01's check no worse than
99.04% and a fresh hand-read sample.
