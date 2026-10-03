# Complete configured filing columns

Continue ticket 21: full configured Company and Person reading before loader retirement. This change addresses the measured calendar-date gap first; numeric flags, all other source columns, classification, reference lookup, source retirement and full empty-store proof remain required.

- [x] Review relevant engine and loader history using GoF — both independent reviews retain plain helper/evaluator; 2026-10-03 17:41 ET.
- [x] Preserve timestamp behavior; add explicit bounded calendar parsing and invalid-value policy — native acceptance and Python instant regression passed; 2026-10-03 17:41 ET.
- [x] Fix and verify root-document `each: .` validation: evaluation supported it, but contract validation refused it — Rust and Python root-document date tests passed; 2026-10-03 17:41 ET.
- [x] Verify calendar prefixes, valid ISO forms, invalid/default values and malformed contracts against the loader — six native calendar tests and 26 focused Python cases passed (including 646 adversarial mutations), with compact-date compatibility regressions; 2026-10-03 17:41 ET.
- [x] Extend captured filing projection to all text/calendar fields and compare pinned receipt bytes — receipt-hash-verified 1,000 filings / 107,197 rows, all 11 columns matched; text-calendar-qualification.json; 2026-10-03 17:41 ET.
- [x] Document implemented behavior in the installed skill — READING.md describes calendar mode, strict default and explicit compact suffix compatibility; initial 62 engine tests include installed bundle/link checks; 2026-10-03 17:41 ET.
- [ ] Review the diff, open a dependent PR, run all CI suites and aggregate gate.
- [ ] Complete numeric, flag, artifact-context and bounded-history column equivalence.
- [ ] Company/Person classification, address/reference/grouping equivalence and configured read blocks.
- [ ] GLEIF complete positive/failure equivalence and source-reader retirement.
- [ ] Installed empty-store proof: 6,414 Companies, 3,052 CIK+LEI, unchanged replay.

## Design review

Engine dispatch has a stable scalar expression interface; recent loader history changes concern source classification and address evidence. Calendar parsing belongs in the existing date expression, as one plain helper. A Strategy hierarchy would add indirection without reducing a demonstrated maintenance cost. Preserve default instant parsing and make calendar/invalid policy explicit.

## Adversarial qualification

A 646-case mutation comparison exposed four compact-date suffix differences absent from the 1,000-file corpus. Add explicit `basic_suffix: ignore` compatibility and retained strict rejection tests before claiming the calendar projection equivalent.

## Qualification status

PR #809; initial local engine run: 62 passed in 288.05s before the compact-suffix follow-up. Fresh final binding: 26 focused cases passed (including 646 adversarial mutations); complete final-head CI remains required. Independent reviews found one invalid fixture indentation introduced with the compatibility option; fixed, YAML loaded, and fixture-dependent tests plus corpus comparison passed. No source activation or legacy retirement.
