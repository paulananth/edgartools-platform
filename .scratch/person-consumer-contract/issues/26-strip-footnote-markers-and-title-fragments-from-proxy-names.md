# Strip footnote markers and title fragments from DEF 14A executive names

Type: task
Status: resolved 2026-09-22
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

## Resolution — 2026-09-22

Resolved on a full local re-parse of bronze, with the same method and inputs
as ticket 10: 9,254 proxy filings, 0 parse or extract errors, S3 bronze reads
only, zero SEC requests, #680 collapse → 17,387 rows. The evidence was
produced by the committed parser. The final run's rows are identical to the
run before the review fixes.
[`research/26-reparse-results.json`](../research/26-reparse-results.json),
[`research/26-measure.json`](../research/26-measure.json) (from
[`26-measure.py`](../research/26-measure.py)),
[`research/26-hand-read-sample.json`](../research/26-hand-read-sample.json).

| Measure | Ticket 10 (parser v2) | Ticket 26 (parser v3) |
|---|---|---|
| Footnote markers left in the name | 462 (2.66%) | **0** |
| Trailing title fragments | 128 (0.74%) | **0** |
| Names carrying any digit | 505 | **0** |
| Executives spelled several ways across a company's filings | 119 | **0** |
| Research 01's check | 99.039% | **99.454%** |
| Research 10's check | 99.850% | **99.902%** |
| `person-name@v2` accepts | 93.1% | **97.0%** |
| Distinct implausible values | 72 | 44 |
| Hand-read, name clean | 54 / 60 | **60 / 60** |
| Hand-read, person matches the filing | 60 / 60 | 60 / 60 |

**Hand-read.** The score stage draws 60 rows with ticket 10's seed
(20260921) from the new row set. 9 of the 60 rows are also in ticket 10's
sample, so 51 are new. Each is recorded with its verdicts under ticket 10's
rule: the kept name occurs among that filing's full name cells, the role was
read against those cells, and the field holds only the name.

**Executives spelled several ways.** 119 executives had two or more
spellings across one company's filings that differ only by a marker, such
as `Raymond F. Lancy` / `Raymond F. Lancy (1)`. 19 of them involve a
flattened superscript digit (`Daniel Pinto7` / `Pinto8` / `Pinto11`).
Name-keyed matching read each spelling as a different person. `26-measure.py`
groups both sides with the new stripper, so the "before" count asks which
of ticket 10's spellings v3 would join.

### What changed in `edgar_warehouse/parsers/proxy_fundamentals.py`

`PARSER_VERSION` 2 → 3.

- **Footnote markers anywhere in the cell**, including lists (`(6, 7)`),
  superscripts and single lowercase letters (`Justin Cochrane(f)`). The
  re-parse found a layout the ticket did not list: a superscript the HTML
  flattened to a plain digit (`Brendan Brothers6`, `Walter W. Bettinger
  II6`, 56 rows). That is also a footnote marker, so it is stripped too.
  Stripping moved into `_split_name_from_title`, ahead of the no-separator
  split, because the name is sliced from the cell. The pattern is now case
  sensitive: capital-letter markers occur 0 times, and matching them
  deleted a bracketed initial (`Robert (B) Smith`).
- **A trailing `Co-` or lone `-` starts the title**, anchored at the end of
  the cell. A lowercase `co-` counts only after a space: glued to a word,
  it would cut `Anthony Franco-` to `Anthony Fran`. The glued lowercase form
  occurs 0 times. The first re-parse left 8 rows of a second layout, the
  separator in front of a position (`Walter Klemp - Executive Chair`). That
  separator is now stripped at the cut.
- **`VP`, `V.P.`, `SEVP` join the cut set only.** A pre-code
  `/gof-refactor-reviewer` consult showed that a word in both vocabularies
  can never fire as a veto. Putting `VP` in the veto set would have
  republished `Max P. Bowman`'s pay under the previous executive. The
  camel-case vocabulary is now regex-escaped, since `v.p` is its first entry
  with a metacharacter. The consult, and the post-diff GoF review, found no
  refactor justified: the block is one day old, from one commit.
- **A side effect to be aware of:** title-only continuation cells now go
  through the same marker stripping. A continuation like `Officer 2` would
  lose its `2`. Published `exec_role` values with a digit went from 121 rows
  to 123, and neither re-parse has a `Section/Rule/Class <n>` role value, so
  it is recorded, not fixed.

### Remaining, explained

95 rows (44 distinct) still fail research 01's check, and none contains the
three spellings this ticket named:
- **74 rows are wrapped title continuations with no title word and no
  person** (`Member of the`, `of UMI`, `and Legal`).
- **21 rows (10 distinct) name a real executive glued to a title word the
  vocabulary does not know**: `Elon Musk Technoking of Tesla and`, `Joseph
  W. Logan Sales and`, `Allan L. Bridgford Member of the`, `Gary D.
  FieldsSpecial Advisor to the`, `John Donahoe IIPresident and`, `Jennifer
  Lew.Executive`. These executives are lost from those rows. At 0.12% of
  rows, each needs its own vocabulary word or layout rule, so they are left
  for now and listed here.

### Found, and split out

`person-name@v2` rejects 514 of the rows. 95 are the role text above, and
104 are honorific-only (`Mr. McGowan`), correctly rejected because they have
no given name to key on. **314 are real names the normalizer refuses**:
- 152 with a degree suffix (`Linda Marbán, Ph.D.`);
- 88 with an accent (`José R. Mas`, `Luis A. Müller`);
- 74 with a curly apostrophe (`Kieran M. O’Sullivan`).

This is the normalizer's defect, not the parser's:
[ticket 27](27-accept-accents-apostrophes-and-degrees-in-person-names.md).
`26-measure.py` records each cause's count
(`person_name_v2_rejections_by_cause`).
