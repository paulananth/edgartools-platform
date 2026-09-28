# Check data quality in its own rule, before the merge

Type: build
Status: waiting
Blocked by: Codex PR #738 (operator, 2026-09-27 20:47 ET: "Wait for #738"). It edits
`edgar_warehouse/rules/db.py`, `cli.py`, adds Rules migration `002`, and edits
`store.py` and both SEC and GLEIF `source.yaml` files, which this ticket also
needs. Blocks ticket 21 (the cascade merge).

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

## Checklist (times ET)

- [ ] `/gof-refactor-reviewer` on the Merge Stage and the rules loader.
- [ ] The file format, its loader, and the Rules Database kind `quality`
  (a migration: the kind list is a CHECK).
- [ ] The Merge Stage step: withhold, reject, flag; the counts per check.
- [ ] `rules/quality/company.yaml` with the first checks for SEC and GLEIF.
- [ ] Measure on the ticket 08 inputs: what each check withholds or rejects.
- [ ] The Rules skill: how to write a quality check.
- [ ] Three-axis review, PR, CI; merge on the operator's word.
