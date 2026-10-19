# An N-PORT ISSUED_BY link starts at its filing, and a link that exists keeps its start

Priority: 113. Map: [Rebuild priorities](../map.md).

Type: task. Status: open (Claude, 2026-10-19). Blocked by: none. Changes: ticket 100's design (the quarter dated each N-PORT publication in MDM).

## Operator rulings (2026-10-19, asked while wiring the N-PORT run, ticket 79)

- The quarter: "if at all it should be captured in silver not on mdm". Asked: where an N-PORT run's quarter (`period`) comes from when the declared writer builds the run.
- The link start: "if issued by already exist do not overight if not use the filing date or quarter date or inception date". Asked: with the quarter out of MDM, how an ISSUED_BY link (Security issued by Company) gets its start.

## Found (2026-10-19 ET)

- Today (ticket 100) the quarter's `period` reaches MDM twice: the reading reads it from the run's context into both holding tables, and `mdm.prepare` dates each publication by it (`effective_column: period`). An ISSUED_BY link states no start (`valid_from: item.valid_from`, always empty), so MDM starts it, observed, at the publication's effective time (`relationships.py`: a stated `valid_from` is `stated`; none, with an effective time, is `observed`; neither, a review `unknown_relationship_start`).
- The 2026 Q2 data set: `SUBMISSION.tsv` holds each filing's `FILING_DATE` (14,416 filings, every one shaped `DD-MON-YYYY`), `REPORT_ENDING_PERIOD` and `REPORT_DATE`. No table holds an inception date (the date columns are filing, report and period dates, and maturity, expiration, settlement, termination and reset dates of instruments).
- A link already in MDM keeps its earlier observed start (`_keep_first_observed`, ticket 101); a stated start is not kept that way.

## Checklist

- [ ] Each holding carries its filing's `FILING_DATE` (joined from `SUBMISSION.tsv` by accession), parsed to a date; the ISSUED_BY link states as its start the earliest filing date of the quarter's holdings that name it, else the quarter's date (the data set period); inception date: none in the data set (recorded above), so it is not used
- [ ] The quarter leaves MDM: `mdm.prepare` no longer dates publications by `period` (`effective_column` removed from the run); the quarter is a silver column only
- [x] GoF consult on keeping a start (2026-10-19 06:57 ET): widen `_earlier_sighting` (any basis) and use it both when a run folds its own records and when a stored start is restored; a flat type key `keeps_start: true`, refused on a hierarchy so GLEIF's parent links keep correcting their stated starts; asked the operator whether a backfilled earlier start moves it back: "Keep the earlier date (Recommended)" (2026-10-19)
- [x] A link that exists keeps its start (2026-10-19 06:57 ET): `keeps_start: true` on ISSUED_BY (relationship types v5); a later start, stated or observed, never moves it forward, an earlier one moves it back, and two records in one run give one period at the earlier start; other types unchanged. `tests/mdm/test_clean_relationship_history.py` (7 new), `tests/mdm` 848 passed; the policy layer `without_issued_by_keeps_start` pins the new Company digest (peeled, the one before); the integration answer file's whole-policy digest moved (as #1075, #1083, #1085 did). Rules change `platform-2026-10-19.issued-by-keeps-start`, recorded under the standing rule on these tests
- [ ] Proof: invented holdings through the real chain and the Merge Stage on PG16, one test per case (filing date given; none, quarter date; the link already there with an earlier start; a later quarter with a later filing date)
- [ ] The real quarter: counts of links started at a filing date and at the quarter date, and none reviewed for a missing start
- [ ] Tickets 100 and 79 updated; the N-PORT target declared (the run wiring part of 79) on this design
- [ ] Three-axis review, PR, CI, merge
- [ ] Learning → skill
