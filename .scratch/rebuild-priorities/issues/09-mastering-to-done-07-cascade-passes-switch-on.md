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
- [ ] GoF consult, then code: Name Frequency runs the cascade from the configured readings (`name_census.census(cascade=...)`, `cascade.filer_of`), switched on or not; each filer as the Merge Stage holds it, through the Company Dataset Contract's own mapping, never a second set of paths; a test proves the census's filer equals `filer_of` on the full chain's record (invented documents, then about 50 real ones)
- [ ] Today's cascade answers over the whole population (the SEC population's 43,338 documents and the Golden Copy; about 50 min), against the 2026-09-28 answers; before it, the saved Golden Copy reading carries the cascade columns and every bound fits
- [ ] Draw each pass's new links per stratum (up to 64 a pass, seed recorded), local only (names); pre-label with certain evidence only (an LEI the SEC filer states); the rest to the operator
- [ ] Operator labels (about 300 pairs, about 1½ hours); precision per pass and stratum; the operator switches on, tunes or deletes each pass, with P2 and P3 (too few new links to prove) asked in the same question: delete or fold
- [ ] Delete `20-1-waiting-no-agreement.csv` once done; PR, CI green, merged on green
- [ ] Learning → skill

