# SEC Companies waiting with a same-name GLEIF record (temporary evidence)

**Temporary.** This note and `20-1-waiting-no-agreement.csv` beside it are kept
only until the cascade passes (ticket 21) are tuned or switched on. Delete both
then. The operator said to keep it and delete it later (2026-10-02).

**What it is.** 248 SEC Companies (written 2026-09-27, during ticket 20, which
was folded into tickets 21 and 25). Each has a GLEIF record with the same name,
but the matching rules did not agree on the rest, so the record waited. Each
row gives the CIK, LEI, both names, the jurisdictions, both addresses and a
`pattern` column saying why the rules did not agree:

| Pattern | Rows |
|---|---|
| SEC has no state of incorporation | 80 |
| jurisdictions differ | 32 |
| SEC has no state; GLEIF HQ is a registered-agent address | 32 |
| SEC has no state; same city | 31 |
| GLEIF jurisdiction is country only | 21 |
| jurisdictions differ; GLEIF HQ is a registered-agent address | 18 |
| other combinations | 34 |

**Why it is kept.** It is the only list of the real records behind the cascade
passes (`issues/21-priority-name-and-address-matching.md`) and the "country
only" finding (`issues/18-source-data-findings-from-the-rules-trials.md`). Use
it to check what a pass would join before it is switched on.
