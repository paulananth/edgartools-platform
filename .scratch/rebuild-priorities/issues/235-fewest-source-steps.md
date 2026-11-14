# 235: A source extract has the fewest steps that make its records

Type: task. Status: open. Blocked by: none.

## Why

Operator, 2026-11-14: "when we are building source extract will it has only one step for all was this encoded
in the skill", then "we updated all the source to have one or the fewest possible steps this must be encoded in
the skill and in rules".

Found on main the same day: GLEIF masters from its reading and SEC Company from one combine, but 9 steps in 7
sources only read another step's rows and write them again (a record step). Each step reads and writes every row,
so a step that adds nothing costs a full pass of the data. The engine needs no change to drop them: a combine's
table reads the reading's rows directly, `mdm.prepare` takes a table with no record column (each row is the
record) and keeps one record per key (`distinct_on`), and a `transform` reformats a looked-up value in the read.

A folded source's rules files change, and they are part of the Change Journal's processing identity: its next
hosted run reprocesses its files. Nothing runs on the hosted store without the operator's word.

## Parts

- [x] The rule in the skills: data-onboarding ("The files are the rules"), with pointers from data-platform
  COMBINING.md and refining-rules (2026-11-14 16:38 ET)
- [x] `rules check` refuses a step that only copies another step's rows (`shape.follow`;
  `test_a_step_that_only_copies_another_steps_rows_is_refused` failed before with "DID NOT RAISE") (2026-11-14 16:38 ET)
- [x] Fold the two copy-only steps: 13F securities `record.yaml`, Form ADV `record-filings.yaml` (the record was
  the whole combine row, so every record is unchanged; target and step tests) (2026-11-14 16:38 ET)
- [x] Fold N-CEN adviser (reduce and record steps) and N-CEN fund (record step): the filing date becomes an
  instant in the read. Proved by loading N-CEN 2026q1 into two disposable stores, before and after: 6,465 fund and
  840 adviser records, 7,304 masters and 11,167 links in each; no record body and no link differs (2026-11-14 16:38 ET)
- [ ] Fold N-PORT fund `record.yaml` (a date reformat; the read can do it)
- [ ] Fold N-PORT registrant `record.yaml`
- [ ] Fold OpenFIGI `record.yaml`
- [ ] Fold Form ADV `record-custody.yaml` (it computes the custodian id)
- [ ] OpenFIGI `listing.yaml` stays: it computes each listing's currency from counts a combine joined, which no
  read can
- [ ] N-PORT security reads one quarter's zip nine times, one table a read (2026q2 on a disposable store: about
  23 of its 60 minutes); find whether one read step can give several tables from several members of a zip, and fold
  them
- [ ] Learning → skill
