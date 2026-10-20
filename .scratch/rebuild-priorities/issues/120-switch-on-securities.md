# 120: Switch on Securities over captured files

Priority: 120 (operator, 2026-10-19: "Can you turn on securities"). Map: [Rebuild priorities](../map.md).

Type: task. Status: in progress (Claude, 2026-10-19). Blocked by: none.

## Found (2026-10-19 13:58 ET)

- Everything Securities need is captured locally: the 2026 Q2 N-PORT data set
  (one zip) and OpenFIGI's answers for its CUSIPs (7,674 files) and ISINs
  (7,754 files, each answer with its request). No provider request.
- `sec.nport.security` declares no run target; its chain was proved only by
  hand-chained scripts (`.scratch/onboarding/sec.nport/security_*.py`).
- The gap: its combine attaches an ISIN to a CUSIP only when OpenFIGI agrees
  (`figi-*.yaml`, operator 2026-10-15: "Use FIGI to add pairs too"), so it
  reads OpenFIGI's answers. A run reads one capture, and a step reads only
  its own run's steps, so no configuration reaches them.
- Ruling (operator, 2026-10-19, asked how to close it): "Read another run
  (Recommended)": a generic change, a step may read the verified output of
  another finished run, named in configuration.

## Design

- A combine's reading may name another source's target and step:
  `{run: {source: <source>, target: <target>, step: <step>}}`. When the
  manifest is written, every verified unit of that step in the complete runs
  of that target (the latest run's unit for a key held by several) becomes
  the slot's list, each `{run, step, key}`; their receipts join the run's
  identity.
- Bookkeeping fills such a slot the way it fills its own: the other run's
  unit must be verified, its chain is reverified against that run's frozen
  configuration, and only its receipt is handed on.
- OpenFIGI gains one target per kind that reads its answers the way the
  Securities chain needs them (`sec.nport.security/figi-requests.yaml` and
  `figi-answers.yaml`, cross-source contracts); Securities' `mastering`
  target reads those runs. The sequence runs those OpenFIGI targets before
  Securities.

## Checklist

- [x] GoF consult on Bookkeeping's slot filling and the target manifest (2026-10-19 17:56 ET): leave it; `_dependency` (config) and `_receipt` (engine) each gain one case, unchanged since #928
- [x] A slot names another run's unit; Bookkeeping fills it only from that run's verified unit, reverified against that run's own frozen configuration; the fill cache keys the run too (2026-10-19 17:56 ET). Tests (`test_configured_bookkeeping_postgres.py`): read; unknown run, not verified, corrupt receipt each block without execution; a malformed run id refused
- [x] A combine's reading, or a read's lookup set, may name `{run: {source, target, step}}`: the manifest writer lists the verified units of that target's complete runs (`Bookkeeping.verified_units`: an output held twice, the same files read again, listed once; group keys repeat across runs, so never "latest per key"), and their outputs join the processing identity (2026-10-19 17:56 ET). Tests: `tests/mdm/test_target_manifest.py` (slots, identity moves, 0 and 257 refused, a lookup read whole, bad selectors refused), the Postgres listing test
- [x] A target that only reads (no `mdm.prepare`), for another run to read; two preparations refused (2026-10-19 17:56 ET); tests in `test_target_manifest.py`
- [x] `rules test` finds another run in its own stores' Bookkeeping, not the shell's (2026-10-19 17:56 ET)
- [x] OpenFIGI targets that read the answers for Securities (`answers_cusip`, `answers_isin`: requests, answers in groups of 16, processed; no publication) and GLEIF's `umbrellas` (the sub-fund pairs) (2026-10-19 18:15 ET); first runs in \`sec-test\` complete (umbrellas 59 s; CUSIP answers run 1, 545 units, 10 min)
- [x] Securities' `mastering` and `mastering_isin` targets (one per Dataset Contract, the same 18 steps; rules files allow no anchors), with `record.yaml`, and `figi-found.yaml` taking one name (2026-10-19 18:15 ET); the Spec review found the wiring equal to the hand chain
- [x] `rules/source-sequence.yaml`: Securities' `mastering` after N-PORT fund; the comments name the targets that run first, since the inventory holds one target per source (2026-10-19 18:15 ET)
- [ ] `rules test` on Securities, recorded; approval under the standing approval; activation in `company-on`
- [ ] Runs in `company-on`: OpenFIGI's answers (CUSIP, ISIN), then Securities; counts; no identifier on two masters
- [x] Three-axis review (2026-10-19 18:15 ET). GoF: one shared helper for another run's slot list (taken); a table of reading shapes noted, not taken (five shapes, three modules; next shape decides). Standards: Bookkeeping now checks, when it fills the slot, that the other run is complete and not compacted and is the source, target and step the step declares (tests per case: unknown run, not verified, not complete, corrupt, undeclared, another step, each matched to its reason); the identity takes the outputs' digests only, in a fixed order; the operation check precedes the repeat skip; engines disposed. Spec: the target joins the processing identity, or \`mastering_isin\` would find the quarter already processed (test); Bookkeeping SPEC and data-onboarding say how another run is read. Over time (a second capture, the 256 list, compaction): ticket 121
- [x] Found by the first Securities test run (2026-10-19 22:43 ET): it read and reduced the quarter (40 min), then \`figi_pairs\` stopped on "Stale lease". Root cause, timed: claiming and reporting that unit each took 73 s (Bookkeeping rechecks the chain behind the ~480 OpenFIGI answer units it reads, each with its 16 request files), so the report came after the 120 s lease; the work itself took 20 s. Fix in configuration: Securities' targets set \`lease_seconds: 900\`, \`heartbeat_seconds: 60\`
- [x] Found on the way (2026-10-19 22:43 ET): a failed control call kept only its last stderr line, SQLAlchemy's "(Background on this error at ...)" link, hiding the database's message; \`workers/control.py\` now keeps the \`(psycopg2.errors.X)\` line, never the SQL or its parameters
- [x] Found (2026-10-19 22:43 ET): editing worker code while runs are live makes them refuse ("Pinned worker runtime changed; start a new run", correct): \`company-on\`'s ISIN run 5 is run again as a new run
- [x] Found by the second test run (2026-10-20 02:33 ET): the record read refused the combine's 22 pieces (\`record.yaml\` allowed one, as Funds' one-piece output did); \`max_artifacts: 512\`, as figi-agree.yaml reads pieces
- [x] Test run, pass 1 (2026-10-20 02:33 ET): the whole 2026 Q2 quarter, all 18 steps verified in 2 h 20 min (00:01–02:21 ET): 383,612 Security masters (equal to the 383,612 CUSIPs OpenFIGI was asked), 1,770 held back with open reviews (1,769 \`invalid_cusip_checksum\`, 1 \`invalid_cusip\`), no identifier on two masters. The test's 150-minute limit covers both passes and stopped pass 2 early; pass 2 is driven to completion and compared with pass 1's counts
- [x] Pass 2 driven to completion and compared (2026-10-20 07:50 ET): every count and the hash of every current record equal pass 1's (the one-string hash query was killed by the container's memory limit; the same hash streamed); proof recorded, approved under the standing approval, `securities-2026-10-19.long-lease` active in `company-on`
- [x] Ruling (operator, 2026-10-20 08:05 ET), asked why the ISIN Securities load separately: "One master record since all data will be available when security mastering runs why can't one run captures all attributes and builds the cross reference". The `company-on` CUSIP run was stopped at its second step, before anything reached MDM
- [ ] One Dataset Contract, one target: each Security's record key is its CUSIP, else its ISIN (`record_key` path, no key format; CUSIP and ISIN checked as identifiers, so a bad check digit is still held back)
- [ ] The combine folds an ISIN-only holding into the CUSIP row that already carries its ISIN, so no ISIN reaches MDM twice
- [ ] The FIGI answers' listing, composite and share-class FIGI and ticker carried through to the Security as cross-references
- [ ] ~~`mastering_isin`, the `security_isin` contract~~ superseded by the one target: removed from Securities
- [ ] ~~OpenFIGI's `mastering_cusip`, `mastering_isin` targets~~ superseded: the Security carries OpenFIGI's identifiers itself; marked superseded in the sequence
- [ ] `proving.counts` hashes the current records without one huge string (the memory limit killed it at 383,612 records)
- [ ] `rules test` on the one target, both passes within its deadline, recorded; approved under the standing approval; active in `company-on`; the run there; counts; no identifier on two masters
- [ ] PR, CI, merge
- [ ] Learning → skill
