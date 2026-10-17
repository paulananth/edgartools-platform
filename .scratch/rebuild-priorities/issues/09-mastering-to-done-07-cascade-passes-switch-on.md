# Cascade name-and-address passes: label and switch on

Priority: 09, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/mastering-to-done/issues/07-cascade-passes-switch-on.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task, then approval
Status: open
Blocked by: 02

## Question

The SEC-to-GLEIF cascade passes are built and switched off (company mastering 21, #746). 248 same-name pairs wait without agreement (`company-mastering/research/20-1-waiting-no-agreement.csv`).

The remaining step: draw and label a sample per pass and stratum, show the operator the precision, and approve or tune each pass. Delete the CSV once that is done.

## Checklist

- [x] What the 2026-09-28 measurement shows (`company-mastering/research/21-cascade.bound.jsonl` against the cohort's outcomes, 6,414 Companies; counts only) 2026-10-14 15:37 ET: no pass binds an LEI other than today's two rules bind; each pass's links that today's rules do not make: P1 99, P2 8, P3 22, P4 59, P5 62, P6 222, P7 64 (536 in all; strata: clean, incorporation conflicts, name held by another candidate). A pass is proved by at least 52 labelled new links with no error (one-sided Wilson lower bound ≥ 95%), so P2 and P3 cannot be proved on this population; the labels `21-cascade.json` holds were reused from the name rules' samples (research 08), not drawn per pass
- [x] Found 2026-10-14 15:37 ET: that measurement read the SEC and GLEIF records through `company_source` and `gleif_source`, both deleted since (#904, #905), so its answers are not today's; and `name_frequency.write_name_frequency` refuses the cascade once a pass is switched on ("no configured cascade reading yet"), though `census.yaml` and `gleif/census-complete-stream.yaml` declare cascade columns
- [x] GoF consult, then code: GoF leave it (`name_frequency.py` changed three times in October, each a reader retired, never along this axis). Name Frequency runs the cascade when asked (`mdm name-census --cascade --catalog <exchange catalog>`) and always once a pass is switched on. Each population document runs through the Company chain's own readings and combination (`census-main.yaml`, `catalog.yaml`, `combine-census-captured.yaml` less its census groups, derived from the file) and the Company Dataset Contract, so a filer's forms and tickers classify it as in MDM; a record set aside is no filer. Tests: the census's filers for three invented documents equal `filer_of` on the full chain's prepared records; a fund's report forms set an operating filer aside and a ticker keeps a REIT a Company (dropping the forms or tickers join fails it). Review fixed: the first version joined only the address in Python, so forms and tickers were missing (found by the three-axis review). 400 real documents: 384 filers in 9.7 s. 74 affected tests pass (2026-10-17 17:13 ET)
- [x] The code merged: #1063, CI green, merged on green (2026-10-17 17:42 ET). For the pipeline (ticket 71): once a pass is switched on, `name-census` needs `--catalog`, and refuses to run without it
- [x] Today's cascade answers over the whole population (the SEC population's 43,338 documents and the Golden Copy), against the 2026-09-28 answers: the Golden Copy reading 39 min, the census 9 min. The census equals the pinned census outside `cascade`. 3,590 Companies get an LEI from a pass (P1 1,268, P2 85, P3 102, P4 447, P5 245, P6 1,207, P7 236); all 3,584 of 2026-09-28 get the same LEI, none lost, 6 new; 26 now bind in an earlier pass with the same LEI (P6 to P1 16, P4 5, P5 3, P2 1, P3 1) (2026-10-17 18:41 ET)
- [x] Each pass's new links, against the installed Company proof (6,414 Companies, 3,052 GLEIF records bound, second pass changed nothing; 22 min on Docker Postgres): where a pass and today's rules both bind, the LEI is the same (3,050, no conflict); new links 540: P1 103, P2 8, P3 22, P4 60, P5 62, P6 220, P7 65 (534 of them in the 2026-09-28 answers). The proof script needed a version-3 GLEIF input receipt since ticket 97 (#1013) declared the N-PORT issuer lookup set; it now passes an empty set, which flags no record. pgserver failed on the macOS shared-memory limit; Docker ran it (2026-10-17 18:41 ET)
- [ ] Draw each pass's new links per stratum (up to 64 a pass, seed recorded), local only (names); pre-label with certain evidence only (an LEI the SEC filer states); the rest to the operator
  - Found: only 11 of the 6,726 SEC filers state an LEI, so pre-labelling settles few pairs; the rest go to the operator
- [ ] Operator labels (about 300 pairs, about 1½ hours); precision per pass and stratum; the operator switches on, tunes or deletes each pass, with P2 and P3 (too few new links to prove) asked in the same question: delete or fold
- [ ] Delete `20-1-waiting-no-agreement.csv` once done; PR, CI green, merged on green
- [ ] Learning → skill

