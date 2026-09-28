# Check data quality in its own rule, before the merge

Type: build
Status: in progress
Blocked by: none. Blocks ticket 21 (the cascade merge).

## Question

Operator, 2026-09-27, answering which matching design to build: "need data
quality checks before merge, dq will be a seperate rule, finally cascade
merge".

So the order is: a Data Quality rule decides which values are fit to use,
then the cascade (ticket 21) merges on the fit values only.

Research: [data-quality 01](../../data-quality/research/01-datakitchen-testgen-observability.md)
(on branch `claude/research-dataops-testgen`): borrow TestGen's check ideas;
do not adopt the tool.

## Design (Claude, 2026-09-27; defaults, not operator rulings)

1. **A separate rules document.** `rules/quality/<kind>.yaml`, saved in the
   Rules Database as its own document kind, `quality`, with its own versions.
   It feeds MDM, so each version needs the operator's approval.
2. **Each check is data:** an id, the source, the value it reads, a test from
   a fixed list, and what a failure does:
   - `withhold`: the value is kept on the record but never used to match
     (a registered agent's address, a placeholder);
   - `reject`: the record is set aside with the reason `quality_<id>`, which
     blocks, as any defect does (a failed LEI check digit);
   - `flag`: counted and reported only.
3. **It runs in the Merge Stage, before any matching,** on the active quality
   version. A stored record is re-checked when the rule changes, and its
   stored reading never changes.
4. **Each run reports a count per check,** as it does for deferred reasons.
5. **First tests** (from the research, only what the cascade needs first):
   registered-agent address, address shared by too many entities, placeholder
   value, value in a reference file, LEI check digit.

## Checklist (times ET)

- [ ] `/gof-refactor-reviewer` on the Merge Stage and the rules loader.
- [ ] The file format, its loader, and the Rules Database kind `quality`
  (a migration: the kind list is a CHECK).
- [ ] The Merge Stage step: withhold, reject, flag; the counts per check.
- [ ] `rules/quality/company.yaml` with the first checks for SEC and GLEIF.
- [ ] Measure on the ticket 08 inputs: what each check withholds or rejects.
- [ ] The Rules skill: how to write a quality check.
- [ ] Three-axis review, PR, CI; merge on the operator's word.
