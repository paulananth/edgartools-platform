# Mastering builds the lookups, so no stage after a load has to

Status: open
Type: task

Operator, 2026-11-18, while `--finish` was building the lookups (18 minutes and not done): "Why do we need this build-lookups,
mastering should already build this".

## Findings (five whys, from the code)

- `mdm build-lookups` writes `mastering_lookup`, rows of (token, master): the name search, the detail keys and the cross-references.
  Only the `edgar-warehouse context` search reads them, and it refuses until they are built (`NotBuilt`). Nothing in a load or a merge reads
  them.
- It is a separate stage because it was written as a read-side projection built "after a load from the masters that changed", pinned to the
  digest of the configuration, so a changed configuration starts again from the first file.
- `tokens_of(pin, body, records)` is a pure function of one master's body and its records, so a merge that has just written a master could
  write its tokens in the same transaction. The stage re-derives every master instead: on a fresh store that is every master (3.3 million
  on the hosted load, 5.2 million lookup rows after 18 minutes, unfinished).
- Counter-weights to measure, not assume: the merge's hot path ("three operations; target milliseconds"), and the kind lock a merge holds.

## Parts

- [x] `--finish` no longer builds the lookups: a load reads none of them. `--finish --lookups` builds them first, for whoever needs the
  context search (2026-11-18 11:07 ET; `test_a_load_does_not_build_the_name_search_lookups_and_they_are_built_only_when_asked`: `finish` took no `lookups`,
  `AssertionError: ['mdm', 'build-lookups'] not in ...`)
- [ ] Design with the GoF consult: the merge writes each changed master's tokens in its own transaction, the configuration pin stays a
  rebuild command, and a master merged away removes its tokens
- [ ] Measure a merge batch with and without the token writes (statements and milliseconds per batch, locks) on a disposable store
- [ ] The same question for the links table (`silver links` rebuilds it whole after every load): can the merge keep it?
- [ ] Learning → skill: mdm-engineering and the runbooks
