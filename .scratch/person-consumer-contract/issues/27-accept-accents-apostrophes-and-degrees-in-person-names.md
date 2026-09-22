# Accept accents, curly apostrophes and degree suffixes in person names

Type: task
Status: open
Blocked by: none. It blocks DEF 14A's Tier B measurement (backfill wave 4),
as ticket 26 did.

## Question

Nothing to decide. This was found by [ticket 26](26-strip-footnote-markers-and-title-fragments-from-proxy-names.md)'s
re-parse ([`research/26-measure.json`](../research/26-measure.json),
`person_name_v2_rejected_top`).

After ticket 26, `person-name@v2` (`edgar_warehouse/domain/policy/person_name.py`,
`is_person_name_candidate`) accepts 97.0% of the 17,387 DEF 14A rows. Of the
514 it rejects, 95 are role text and 104 are honorific-only names
(`Mr. McGowan`, which has no given name to key on). Both are correct
rejections. About 316 others are real people:

| Cause | Rows | Examples |
|---|---|---|
| Degree or credential suffix | 150 | `Linda Marbán, Ph.D.`, `Manuel C. Alves Aivado, M.D., Ph.D.`, `Gilmore O’Neill, M.B., M.M.Sc.` |
| Accented or other non-ASCII letter | 88 | `José R. Mas`, `Luis A. Müller`, `Fredrik Nihlén`, `Tae‑Sik Yoon` |
| Curly apostrophe | 74 | `Kieran M. O’Sullivan`, `Scott L. D’Angelo`, `Kaes Van’t Hof` |

These people are dropped from Tier B entirely. The first two causes are
likely in Form 3/4/5 and 8-K names too, so they may not be DEF 14A-specific.

## What to do

In `person_name.py`:
- fold a curly apostrophe (`’`, `‘`) to `'` before tokenising;
- accept letters outside ASCII (Unicode letter classes, not `[A-Za-z]`);
- strip a trailing credential list (`M.D.`, `Ph.D.`, `J.D.`, `M.B.`,
  `C.P.A.`, `Esq.`) as a suffix, the way `JR`/`III` are.

Bump `NORMALIZER_VERSION`. Re-run [research 25's rescore](../research/25-rescore.py)
over the 938 labelled pairs, and check that precision, the LCB97.5 and the
homonym result (0 of 11 false merges) do not regress. Then re-measure the
DEF 14A acceptance with `26-measure.py`.

Resolved when the three causes above account for 0 rejections (or each
remaining one is explained), with research 25's precision and bound no worse.
