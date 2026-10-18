# Data Onboarding skill gaps found by the Person feed 1 onboarding

Priority: 16, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/platform-validation/issues/05c-data-onboarding-skill-gaps.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task (skill and tooling)
Status: open, not started. Found by `05-onboard-person-feed-1.md`; each gap is
quoted with the skill's own words in
`.scratch/onboarding/sec.submissions.person/onboarding-log.md`, "SKILL-GAPs".

A cold agent could not finish a new feed by configuration alone. Every step
below needed code, a hand-made workaround, or an answer the skill should have
given.

## Checklist

- [ ] ~~1. Dry run needs code: build `rules check --source <s> --sample <n>`~~ moved to ticket 14 (`rules test --sample`), operator's ruling on ticket 12 (2026-10-18 14:00 ET)
  (rules-skill ticket 03)
- [ ] ~~2. Proving run needs code and Docker: build Preview (rules-skill ticket~~ moved to ticket 14 (`rules test` runs into a disposable MDM) (2026-10-18 14:00 ET)
  04), or ship `proving_run.py`'s shape as a command. It must stand in for a
  missing reader, and must not hang on store growth (05b)
- [ ] ~~3. Digest and input manifest need code: `rules save` prints the digest;~~ moved to ticket 14 (the test run names the digest and its input manifest) (2026-10-18 14:00 ET)
  a command writes the input manifest. Rules-skill ticket 15 (`rules test`)
  would write both, with items 2 and 12
- [x] 4. The proof entry's shape is incomplete in the skill (written: `adversarial` is `fixture_sha256` and `violations`, which must be 0; `cohort` holds `files` and a `by_step` sample per step; the bound is cut to six places since switch-on refuses one above the recomputed bound or more than 0.00001 under it; checked against `activation._check_sample` and `_check_proof`; branch `claude/onboarding-gaps`, 2026-10-16 19:46 ET). Say:
  - the lower bound is cut to six places, never rounded (a rounded bound was
    refused);
  - what the adversarial set counts as a violation
- [ ] ~~5. Measuring the classification proof needs code: `rules measure`, plus~~ deferred until a measured matching rule needs it (ticket 12's ruling) (2026-10-18 14:00 ET)
  the sample draw and the labelling-agent steps (Q7, Q12)
- [x] 6. Writing and checking the rules files needs code: `files.source`
  round-trip as a command (built: `edgar-warehouse rules check [--source <s>]`, offline. Each file loads (the loader refuses a value YAML would guess; a body built in code must hold JSON values only), each Bookkeeping target and the acquisition hold, and the merge rules pass `check_policy`; a loader's refusal names its kind and the file, never a line of it; an engine refusal keeps its fixed words. `files.check_document` is the one list of checks, and `rules save` / `rules load` now run it too, so they refuse a source with an invalid target or merge rules that fail `check_policy`, which they accepted before. All 13 repository documents pass. data-onboarding's "check it" steps use it, and its not-built `rules check` row (a sample dry run, moved to ticket 14's `rules test`) is gone. GoF consult: one list of checks shared with `Rules.save` (done). `tests/unit/test_rules_check.py` 6 passed, including `Rules.save` refusing before any database work; affected tests 1,777 passed (8 min 53 s locally: the integration folder was included, which should have been left to CI), 2026-10-18 17:44 ET)
- [ ] ~~7. Profile needs code: `rules profile` (rules-skill ticket 06)~~ struck: the data-profiling skill profiles a source (ticket 12's ruling) (2026-10-18 14:00 ET)
- [ ] ~~8. Quality counts need code: part of `rules check`~~ moved to ticket 14 (the test run counts each quality check) (2026-10-18 14:00 ET)
- [x] 9. Adding a kind broke pinned tests: fixed by #769 (05a). Add a line to
  the skill that a new kind leaves Company's pins alone (written in kind-neutral words, as the genericity lint requires; a change to the shared part moves them and the answer file's digest, as ticket 75 found; checked against `tests/mdm/policy_layers.company_part`, 2026-10-16 19:46 ET)
- [x] 10 (part). Fixed in #770: plain words for `token_match@1` and
  `name_shape@1`, "NOT (...)" for a negated condition, excluded words named,
  and a ceiling of 1 or more shown (2026-10-01 18:34 ET). Still open: Company's
  `max_count: 0` reads "at least  of the list", and the identifier words say
  "Company" for every kind.
- [x] 10. Mapping Document bugs for a second kind (verified by
  `tests/unit/test_rules_mapdoc.py`, 18 passed, 2026-10-16 09:07 ET):
  - a negated step is shown without "not" (fixed in #770);
  - "Company" is hard-coded in the matching rule text: each kind now names
    itself ("Exactly one Security holds that CUSIP"), and a ceiling with no
    floor (`max_count: 0`) reads "holds none of the list";
  - the arguments are shown raw: every condition the rules use has words
    (#770, `test_every_condition_the_rules_use_has_plain_words`), and an empty
    refused-flags list now reads "none". Values still show as the rules file
    holds them (a field's name, `True`, a category as SEC files it); that is
    the record's own text, kept on purpose
- [x] 11. Catalog lineage is missing for a second kind read from another
  source's feed (fixed: a source with no feed of its own gets lineage from the feed that captures its `bronze.family`; `sec.submissions.person.v1` now reads from the Company source's `submissions` feed; a family no feed captures gets none; every feed capturing the family leads there, and a feed naming no family leads nowhere. Tests `test_a_second_kind_from_another_sources_files_has_its_feed_lineage` (failing without the change) and `test_each_feed_that_captures_the_family_gives_lineage`. Not covered: a source with feeds of its own that also joins another source's files (none today); GoF leave it: `catalog.py` grew one section a ticket, never along this axis, 2026-10-17 20:31 ET)
- [x] 12. The input manifest includes a non-feed file (the ticker catalog):
  say whether `batch_hash` covers only the feed's own files (written: the manifest lists exactly the files the test read: the feed's own and any other source's file the reading joins, since the counts depend on it; a `receipts.jsonl` naming a file the test never read (Person's lists the ticker catalog, which only the Company reading joins) or missing one it read is not the manifest. Data-onboarding **test** and refining-rules step 2; the engine checks only that `batch_hash` is a well-formed reference, `bookkeeping/clean/engine.py`, 2026-10-17 20:31 ET)
- [x] 13. Say up front which variables the whole walk needs. The Rules
  Database can be a local throwaway (operator, 2026-10-01: "no login needed") (written under the variables table: none is live, so approvals go on the ticket and the walk needs only Docker or a local PostgreSQL 16 for test; operator 2026-10-06: "There is no login", 2026-10-16 19:46 ET)
- [x] 14. `rules approve --rule <id> --proof <report> --reason <counts>` switches an identifier matching rule on: the `automatic_rules` entry under a comment with the words and the report's sha256, and the Identifier Contract's `verification` stamped from the report when it has none; refuses a missing report, a missing reason, a rule that does not join on an identifier, or one already on, leaving the files unchanged; APPROVE.md uses it; `--at` records when the operator spoke, shown in ET in the comment. Three-axis review: Standards asked for rule errors in place of raw ones and a rollback on any failure (done); Spec asked for the already-verified contract, the empty-words and unknown-rule refusals tested and the words' ET time (done); GoF: leave it. 6 new tests on a copy of the rules (2026-10-18 13:32 ET). Was: (skill part done: APPROVE.md "Switch on an identifier matching rule" gives the hand steps, `verification` and the `automatic_rules` entry, as the switched-on identifier rules hold them, 2026-10-16 19:46 ET; the command is still open) APPROVE.md does not say how an identifier rule is approved. The
  approval goes on its Identifier Contract's `verification`, plus its
  `automatic_rules` entry, by hand; `rules approve --rule` records measured
  proofs only. Make it a command
- [x] 15. Switch-on needs a Clean MDM database. Say which one, and what to do
  while the operator's local store holds the retired `mdm_v2` schema (written in APPROVE.md "Switch on": the database the MDM runs use, schema `mdm`, made by `mdm migrate`; locally a disposable PostgreSQL 16; a store that still holds `mdm_v2` is not it: `mdm migrate` refuses it (`store.py`), so create a fresh one and leave the old one to the operator to drop. Review (Standards, Spec, GoF) fixed this reason and item 12's wording, 2026-10-17 20:39 ET)
- [x] 16. Relationships come with MDM (operator, 2026-10-01) (plan-parts already onboards `together` relationships with their master; added under map's Relationships: count each wording that states a relationship and bring it to the operator as a proposed link in the same onboarding, the name kept as written until ruled, 2026-10-16 19:46 ET). The skill must
  plan person–role–entity links in the same onboarding, including names that
  state a relationship ("a series of", "Trustee UAD", "dba", "ET AL")
- [x] Three-axis review (2026-10-18 17:48 ET). GoF: leave it. Standards: the `LAYOUT` comment kept beside its table, an engine refusal's words kept, the real root in the missing message, `Rules.save`'s refusal tested (all done). Spec: the round trip described as what it proves (JSON values only), `rules check` added to the skill's `--root` list, the quality output line uses it (all done); rules integration tests 13 passed after the rebase
- [ ] PR, CI, merge
- [ ] Learning → skill: data-onboarding "Write" and "Read rules files": check a rules file with `rules check --source <s>`, not Python
