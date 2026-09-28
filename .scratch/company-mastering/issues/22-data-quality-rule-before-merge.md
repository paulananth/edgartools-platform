# Check data quality in its own rule, before the merge

Type: build
Status: in progress
Blocks ticket 21 (the cascade merge). Codex PR #738 merged (ad43cfac,
2026-09-28); nothing else blocks.

## Question

Operator, 2026-09-27, answering which matching design to build: "need data
quality checks before merge, dq will be a seperate rule, finally cascade
merge".

So the order is: a Data Quality rule decides which values are fit to use,
then the cascade (ticket 21) merges on the fit values only.

Research: [data-quality 01](../../data-quality/research/01-datakitchen-testgen-observability.md)
(on branch `claude/research-dataops-testgen`): borrow TestGen's check ideas;
do not adopt the tool.

## Design (grilling with the operator, 2026-09-27, Q1-Q13 agreed)

1. **Owner:** the Rules skill: an onboarding quality step (after Infer,
   before Check) and a "quality" mode for live feeds. Bookkeeping runs it.
2. **File:** `rules/sources/<source>/quality.yaml`, its own Rules Database
   document (kind `quality`), own versions, operator approval. A check across
   sources (over-shared addresses) sits with the kind's merge rules.
3. **Checks:** value present, in a set, in a reference file, pattern, LEI
   check digit, placeholder, registered-agent address. On failure: `reject`
   (set aside, blocks, as a defect), `withhold` (kept, never used to match),
   `flag` (counted). Defects block from day one.
4. **Fixes:** SEC name state marker to state of incorporation; an invalid
   code to empty; address standardized. A fix writes the corrected value
   beside the original and names itself on the record; MDM matches and
   merges on the corrected value.
5. **Runs** once per batch, before MDM and silver. A new version applies to
   new batches only; re-checking old batches is an explicit re-run.
6. **Proof:** a proving run on a pinned batch: exact counts and about 10
   examples per check and fix; no 95% bar.
7. **Report:** a count per check and fix in the run result.
8. **Over-shared address threshold:** measure 10, 25 and 100 entities per
   address; the operator picks.
9. **First users:** SEC Company and GLEIF.

Shape (Claude, 2026-09-27 20:47 ET): both batch paths call `adapters.normalize`
(`cli.py:205`, `gleif_source.py:495`), so quality applies there, to the mapped
fields, before the record's fingerprint. Activation folds the active quality
version into the Dataset Contract it registers (`contract.quality`);
`register_dataset` already makes a changed contract a new mapping version,
so a new quality version applies to new batches only.

## Two changes to the agreed design (Claude, 2026-09-28, under the operator's
"you can own every thing ... move forward and fix")

1. **Q2, the file's home.** `quality.yaml` is its own file with its own
   version name, but not its own Rules Database document kind. The loader
   puts it into each Dataset Contract as `contract.quality`, as
   `files.policy()` composes the kind files. Why: #738 made registration
   (`change_journal/authority.registration_authority`) and Bookkeeping's
   `source_input` require the registered contract to equal the approved
   source document exactly, so a separate document would need a second
   approval chain threaded through both. One approval now covers the
   mapping and its checks, and a quality change is a new mapping version,
   which applies to new batches only (Q5). Reversible: a later kind can
   carry the same block.
2. **Q4, the address fix only.** A standardized address is a matching copy
   (`matching.address`); the address MDM shows stays as the source wrote
   it. Why: "3050 BOWERS AVE" is a better key but a worse value to show.
   The value-correcting fixes ("DC" to empty, "/DE" to DE) do change the
   field MDM shows and merges on, as agreed; the original stays on the
   record.

## GoF consult (2026-09-28)

Leave the structure. One hook in `adapters.normalize`, which all three
readers call (`cli.batch_input`, the native GLEIF reader, Bookkeeping's
`source_input`); checks and fixes are a fixed table of functions, as the
matching tests are.

## Checklist (times ET)

- [x] `/gof-refactor-reviewer` on the Merge Stage and the rules loader.
- [x] The file format and its loader (`files.load_source`/`write_source`);
  no Rules Database kind (change 1 above).
- [x] The quality step in `normalize`: fixes, then reject, withhold, flag
  (`edgar_warehouse/mdm/clean/quality.py`); matching skips withheld values.
- [x] `rules/sources/sec.submissions.company/quality.yaml` and
  `rules/sources/gleif/quality.yaml`, the first checks and fixes.
- [x] Counts per check and fix in the run result (`quality` in the MDM run
  result and in the Bookkeeping MDM receipt) (2026-09-28 07:38 ET).
- [x] The Rules skill: step 5 "Quality", the quality mode, REFERENCE.md
  "Data quality" (07:30 ET).
- [ ] Proving run on the ticket 08 inputs: counts and examples per check and
  fix; over-shared address counts at 10, 25 and 100 (Q8).
- [ ] Full suite, three-axis review, PR, CI; merge on the operator's word.
