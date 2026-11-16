# 235: A source extract has the fewest steps that make its records

Type: task. Status: resolved. Blocked by: none.

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
- [ ] ~~Fold OpenFIGI `listing.yaml`~~ kept: it computes each listing's currency from counts a combine joined,
  which no read can; the engine change was measured not worth it (below)
- [x] N-PORT security reads one quarter's zip nine times, one table a read (2026q2 on a disposable store: about
  23 of its 60 minutes); find whether one read step can give several tables from several members of a zip, and fold
  them: no longer a waste after the folds below. The MDM path reads four members and the silver path five, each
  read opening only its own member; on 2026q2 the three small reads took about 1.5 min together, startup included,
  and the holdings read (910 MB) 5 min. No multi-member read is needed (2026-11-15 12:44 ET)
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
- [x] N-PORT security: one reading of SUBMISSION.tsv per path (operator, 2026-11-15: "Add it (Recommended)"): the
  silver path reads it once since registrant-keys.yaml; the MDM path read it twice only because it ran N-PORT fund's
  whole read (with its submissions and registrant reads) for one pair set, a series' LEI to its series id.
  `series-keys.yaml` gives that set with no lookup: the MDM path goes from 10 extract steps to 8, its three reads run
  side by side, and N-PORT fund's and registrant's rules no longer reprocess it. Proof on 2026q2: the pairs equal
  N-PORT fund's (13,687 rows, 12,892 LEIs); main against the branch on disposable stores, run side by side (24 min
  to the merge and links; 8.5 min of it the merge, slowed by two loads on one laptop): 420,690 Security, 12,937
  Fund and 1,947 registrant records equal per dataset, 409,550 masters grouping the same records, 8 set aside,
  4 reviews, 15,355 links equal once ids are mapped to records (2026-11-15 12:33 ET)
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
- [x] 13F securities in two paths (operator, 2026-11-14: "make it two split one to mdm and one to silver"; 2026-11-15:
  "continue"): `mastering` reads, reduces, combines, prepares and merges the Securities (6 steps); `silver` reads and
  lands the holdings (3 steps), waiting for no merge. Seven wastes: the landing waited for the merge only for the
  Security id (waiting); the reduce (about 11M rows to about 31K CUSIPs) and the combine stay; the silver path's read
  still writes the four tables only MDM uses (issuer name, title, class, FIGI), kept since a silver-only extract
  would copy the holdings table's definition (over-processing, accepted). Proof on the p07 cohort (52 files), main's
  one target against the split, silver run first: records equal (5,759; 5,759 masters; 0 set aside; 0 reviews),
  283,725 holdings equal column by column but `loaded_at`, and 283,725 Security ids filled by `refresh-ids` as on
  main; main 33 s, split 22 s + 20 s (2026-11-15 07:09 ET)
- [x] SEC company stays at 3 extract steps (seven wastes, 2026-11-15): two reads of different files (the main
  documents, the exchange catalog) and a combine that joins several ranked tickers to each CIK, which a read's
  pair set cannot (one value a key); no silver path to split (2026-11-15 07:31 ET)
- [x] N-CEN registrant stays at 3: the submissions read (the filing dates are another member file), the
  registrant read, and the combine that groups by CIK for the latest filing and the first date (2026-11-15 07:31 ET)
- [x] N-CEN adviser and class from 5 extract steps to 4 (operator, 2026-11-15: "Add it (Recommended)"): both read
  REGISTRANT.tsv only because N-CEN fund's read declares a registrant lookup they never use, which also made a
  change to N-PORT registrant's rules reprocess them; `sec.ncen.fund/fund-keys.yaml` gives each fund row's filing
  date and series with the filing-date lookup alone. Proof on 2026q2, main against the branch on disposable stores
  (fund mastered first so class's links have endpoints): records equal per dataset (554 advisers, 5,137 classes,
  2,054 funds; 1 set aside; 0 reviews), 8,580 links equal once each id is mapped to its records (2026-11-15 07:31 ET)
- [x] No engine change for OpenFIGI or N-CEN fund (operator, 2026-11-15: "agreed", to measuring first): one
  2026q2 OpenFIGI bundle (512 of 7,714 files) on a disposable store took 97 s; the three steps a combine with
  conditions would fold (`lines`, `listing`, `record`) took about 10 s (10%), and the merge 52 s; the join change
  for N-CEN fund would save seconds on about 7K rows a quarter. Both stay at 8, kept by the engine limit (2026-11-15 08:46 ET)
- [x] Form ADV filings stays at 5: four reads of four different CSVs in the zip, run side by side, and a combine
  that collects each filing's custodians, CIKs and related persons as lists, which a pair set cannot (2026-11-15 08:46 ET)
- [x] N-PORT fund stays at 6 (the reduce is the one-to-one LEI rule; `pairs` stays, a combine cannot filter on a
  joined column), but its registrant step read N-PORT registrant's whole read file for one CIK (operator,
  2026-11-15: "Add it (Recommended)"): `sec.nport.registrant/registrant-keys.yaml` gives each filing's registrant
  CIK with no lookup, used by N-PORT fund, N-CEN fund and N-PORT security's holdings; the step no longer waits for
  the submissions read, a change to N-PORT registrant's rules no longer reprocesses them, and N-PORT security's
  silver path drops its submissions read (6 extract steps to 5). Proof: the (accession, CIK) pairs equal the old
  read's on every captured zip (N-PORT 2026q2: 14,416; N-CEN 2025q4 to 2026q3: 505, 1,927, 501, 438); then N-PORT
  registrant, N-PORT fund and N-CEN fund on 2026q2, main against the branch: records equal per dataset (12,937 /
  2,054 / 1,947), 14,953 masters, 8 set aside, 12,886 links equal once ids are mapped to records. The holdings'
  12-minute load was not repeated: its only change is this pair set, proved equal (2026-11-15 08:46 ET)
- [x] Learning → skill: data-onboarding, "Design a source extract against the seven wastes" (a table of what
  each waste looks like in an extract), "A lookup reads its own small file", and timing the steps an engine
  change would remove before proposing it; mdm-engineering, "Choose the cheapest proof": a moved lookup is proved
  by its pair set on every delivery, a fold or split by main against the change on two disposable stores, and
  "Compare two stores" (bodies without per-store ids, silver column by column, links mapped to records with
  evidence sorted, endpoints mastered first, two loads on one laptop each slower) (2026-11-15 12:44 ET)
