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
- [x] Fold N-PORT fund `record.yaml`: the read makes the filing date an instant (a blank stays blank and is set
  aside, as before) and carries the start facts; mdm.prepare takes the combine's `fund` row. 7 extract steps to 6.
  Proved on 2026q2, main against this branch: 12,937 Fund records equal body for body, 7 set aside in each, and
  12,891 IS_SUBFUND_OF links with equal dates (2026-11-14 22:03 ET)
- [x] OpenFIGI stays at 8 (measured, 2026-11-14): its two reduces together hold about 9.6 million keys in 2026q2,
  under the engine's 10 million ceiling by 4%, so they stay two; `lines`, `listing` and `record` each choose by
  condition, which a combine cannot. The open part "Fold OpenFIGI `record.yaml`" below is therefore not done:
  its record step chooses each field (US composite, else the ISIN country's, else the only listing) (2026-11-14 22:03 ET)
- [x] N-CEN fund stays at 8: its adviser combine keys on `fund_id`, which the main combine adds by a join, and a
  join reads its key from the base row only (`combination.rs`); folding it needs that engine line changed, the
  operator's word (2026-11-14 22:03 ET)
- [x] Fold N-PORT registrant `record.yaml` and its reduce (operator, 2026-11-14: "agreed", after the seven-wastes
  review): the read makes the filing date an instant and carries the start facts; the combine is based on the
  filings, joins each CIK's first and latest filing and drops the filing's own columns; mdm.prepare keeps one row
  per CIK (`distinct_on`). 5 extract steps to 3. Proved on 2026q2, main against this branch, registrants then
  funds: 1,947 registrant and 12,937 Fund records equal body for body, 14,880 masters, 7 set aside, 0 reviews,
  12,891 IS_SUBFUND_OF links with equal dates (2026-11-14 22:17 ET)
- [ ] ~~Fold OpenFIGI `record.yaml`~~ not possible in rules: it chooses by condition, which a combine cannot (see above)
- [x] Form ADV in three one-path targets (operator, 2026-11-14: "agreed", after the seven-wastes review): the
  custody amounts land through their own `silver` target with no merge before them; `custodians` prepares straight
  from the custody reading (the copy-only combine and the record step deleted: the read already computes
  `custodian_id`), 3 extract steps to 1. Proved on the 2026-03 and 2026-06 files, main against this branch: 2,246
  custodian and 17,965 filing records equal body for body, 15,755 masters, 34 set aside, 80 reviews, 18,504 silver
  custody rows equal (2026-11-14 22:26 ET). June needs `--revision 1` on both: a second month of one source is a new
  publication (data-operations, "A reload whose inputs changed")
- [ ] OpenFIGI `listing.yaml` stays: it computes each listing's currency from counts a combine joined, which no
  read can
- [ ] N-PORT security reads one quarter's zip nine times, one table a read (2026q2 on a disposable store: about
  23 of its 60 minutes); find whether one read step can give several tables from several members of a zip, and fold
  them
- [x] N-PORT security in two paths (operator, 2026-11-14: "make it two split one to mdm and one to silver", then
  "rework the extracts one source at a time, starting with N-PORT security yes"): `mastering` (11 extract steps,
  MDM and its links) and `silver` (6 extract steps, the holdings); every step's body is main's, only divided
  (`load_target_steps.json`); the four small reads both need run in each. Proved on 2026q2 in a disposable store,
  silver loaded first (12 min) and MDM after it (19 min; main's one target took 68 min on the old engine): 420,690
  Security records, 2,465 issued by a fund series, 240,635 by an LEI issuer, 177,590 naming none, and 5,347,869
  holdings, each equal to main's; the Change Journal let both targets load the one zip (2026-11-14 21:14 ET)
- [x] N-PORT security: fold the issuers read into the holdings read (operator, 2026-11-14: "agreed", after the
  seven-wastes review): the MDM path reads FUND_REPORTED_HOLDING.tsv (868 MB in 2026q2) once, 10 extract steps
  from 11. Proved on 2026q2 in a disposable store: the 420,690 Security records are equal to the split's, field by
  field (only the publication key differs, which names the changed contracts); MDM path 21 min (19 before: with
  two workers the two reads had run side by side, so the fold saves a pass of work, not wall time on this
  laptop); worker peak 4.4 GB (2026-11-14 21:40 ET)
- [ ] N-PORT security: one reading of SUBMISSION.tsv per path (it is read twice in each)
- [ ] ~~A lookup read from another source's run~~ deferred: engine code, waits for the operator's word
- [x] The seven wastes are the design check for a source extract (operator, 2026-11-15: "update the source extract
  functionality skill to use 7 wastes as part of desigh"): data-onboarding, "Design a source extract against the
  seven wastes", a table of what each waste looks like in an extract and what to do instead; skill lints pass
  (2026-11-15 06:40 ET)
- [x] Ownership in two paths (operator, 2026-11-14: "make it two split one to mdm and one to silver"; 2026-11-15:
  "continue with ownership"): `mastering` reads, prepares and merges the reporting owners (4 steps); `silver` reads
  and lands the owners and the four line tables (7 steps), waiting for no merge. Seven wastes: the five landings
  waited for the merge only for the Person id, which the silver writer finds by lookup and `silver refresh-ids`
  fills later (waiting); both paths read the same extract, since dropping the line tables saves no parsing of each
  document (an owner-only extract was not made: over-production). Proof on the p07 cohort (5,356 files), main's
  one target against the split, silver run first: records equal (4,962; 4,339 masters; 781 set aside; 0 reviews),
  5,743 owner and 14,331 line rows equal column by column, and 4,962 Person ids filled by `refresh-ids` as on main;
  main 1 min 42 s, split 1 min 15 s + 1 min 9 s (2026-11-15 06:49 ET)
- [ ] Learning → skill
