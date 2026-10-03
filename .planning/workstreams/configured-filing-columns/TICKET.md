# Complete configured filing columns

Continue ticket 21: full configured Company and Person reading before loader retirement. This change addresses the measured calendar-date gap first; numeric flags, all other source columns, classification, reference lookup, source retirement and full empty-store proof remain required.

- [ ] Review relevant engine and loader history using GoF.
- [ ] Preserve timestamp behavior; add explicit bounded calendar parsing and invalid-value policy.
- [ ] Fix and verify root-document `each: .` validation: evaluation supported it, but contract validation refused it.
- [ ] Verify calendar prefixes, valid ISO forms, invalid/default values and malformed contracts against the loader.
- [ ] Extend captured filing projection to all text/calendar fields and compare pinned receipt bytes.
- [ ] Document implemented behavior in the installed skill.
- [ ] Review the diff, open a dependent PR, run all CI suites and aggregate gate.
- [ ] Complete numeric, flag, artifact-context and bounded-history column equivalence.
- [ ] Company/Person classification, address/reference/grouping equivalence and configured read blocks.
- [ ] GLEIF complete positive/failure equivalence and source-reader retirement.
- [ ] Installed empty-store proof: 6,414 Companies, 3,052 CIK+LEI, unchanged replay.

## Design review

Engine dispatch has a stable scalar expression interface; recent loader history changes concern source classification and address evidence. Calendar parsing belongs in the existing date expression, as one plain helper. A Strategy hierarchy would add indirection without reducing a demonstrated maintenance cost. Preserve default instant parsing and make calendar/invalid policy explicit.
