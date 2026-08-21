# Audit which resolvers are actually reachable from a live `mdm run`

Type: research
Status: resolved
Blocked by: none

## Question

`SecurityResolver` had an unbounded `mdm_entity_attribute_stage` growth bug
(commit `091809b0`, this session): no skip-if-unchanged check, so every
`mdm run` restart re-staged every already-processed row from scratch,
since `run_securities()` has no resumable ledger. That commit flagged
`PersonResolver` as having the identical gap, not fixed there
("not fixing speculatively"). Before porting the fix everywhere, which
entity resolvers are *actually* exercised by a real `mdm run
--entity-type all` execution, and which of those lack the fix?

## Answer

`ls edgar_warehouse/mdm/resolvers/` lists 5 resolver classes: Company,
Adviser, Security, Person, Fund. `grep -L "_skip_if_unchanged"` on that
directory shows Adviser, Fund, and Person all lack it (Company and
Security already have it).

But lacking the check only matters if the class is actually reachable from
`MDMPipeline`. Checked each of `run_companies`/`run_advisers`/
`run_securities`/`run_persons`/`run_funds` in `pipeline.py`:

- `run_companies()` — resolves per-row via `CompanyResolver` directly
  (already has the fix, plus a resumable `resume_ledger_run_id` ledger
  release-readiness Ticket 94 built).
- `run_securities()` — resolves per-row via `SecurityResolver` directly
  (fixed this session, commit `091809b0`).
- `run_persons()` — resolves per-row via `PersonResolver` directly
  (`resolver = PersonResolver()` at `pipeline.py:749`). **Live, has the
  bug.**
- `run_advisers()` — delegates entirely to `adv_bulk.resolve_advisers_bulk`
  (`pipeline.py:512-518`).
- `run_funds()` — delegates entirely to `adv_bulk.resolve_funds_bulk`
  (`pipeline.py:809-817`).

`resolve_advisers_bulk`/`resolve_funds_bulk` (`edgar_warehouse/mdm/
adv_bulk.py`) do not construct `AdviserResolver`/`FundResolver` at all —
they're a from-scratch batched reimplementation, per the module's own
docstring: "The generic resolvers are intentionally row-oriented... ADV is
different... This module preserves source references... while using
bounded, batched database writes." Confirmed via `grep -rn
"AdviserResolver(\|FundResolver(\|PersonResolver("` across
`edgar_warehouse/` — only `PersonResolver()` is instantiated anywhere in
production code. Confirmed via `grep -rln "AdviserResolver\|FundResolver"`
across `tests/` and `edgar_warehouse/` — the only other references are the
`resolvers/__init__.py` export list, a docstring comment in
`coverage.py`, and a dashboard test that lists the class name as a string
(never calls `.resolve_one()`). Zero test files call
`AdviserResolver().resolve_one()` or `FundResolver().resolve_one()`.

**Conclusion: `AdviserResolver` and `FundResolver` are dead code.**
`resolve_one()` on both exists, is never called, and its identical
skip-if-unchanged gap has zero live impact. Only `PersonResolver` needs
the fix (Ticket 02). The dead-code disposition itself is Ticket 03.

Also discovered, incidentally, while reading `adv_bulk.py`:
`resolve_advisers_bulk`/`resolve_funds_bulk` do their own dedup via
`_existing_source_ids()` — skip staging for any `source_id` already
present in `MdmSourceRef`, regardless of content — so they do **not** have
the append-only-staging bug at all. But both also do a bare `sql =
"SELECT * FROM sec_adv_filing"` / `"SELECT * FROM sec_adv_private_fund"`
plus `LIMIT`, no `ORDER BY`, no exclusion of already-resolved rows — the
same plateau-on-restart shape release-readiness Ticket 94 found and fixed
for `run_companies()`. Filed separately as
[release-readiness Ticket 100](../../release-readiness/issues/100-adv-bulk-select-limit-plateau-on-restart.md);
out of scope for this map (see map.md's Out of scope section).
