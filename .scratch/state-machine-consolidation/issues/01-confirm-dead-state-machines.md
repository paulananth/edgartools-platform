Type: research
Status: open

## Question

9 of the platform's 26 deployed state machines have zero executions ever
(`bootstrap_full`, `full_reconcile`, `load_daily_form_index_for_date`,
`catch_up_daily_form_index`, `bootstrap_batched`, `mdm_gold`,
`silver_mdm_gold`, `mdm_seed_universe`, `mdm_seed_from_silver` -- confirmed
live via `aws stepfunctions list-executions --max-results 1000` per
machine, 2026-08-04). Zero-executions is evidence of disuse, not proof of
deadness on its own.

For each of the 9, determine: is it (a) genuinely obsolete -- superseded by
another machine, built for a use case that no longer applies, or a
leftover from an earlier architecture -- or (b) intentionally-provisioned
tooling for a scenario that simply hasn't happened yet (disaster recovery,
a specific backfill shape, an escape hatch)? Check: git history/commit
messages for when/why each was added, CLAUDE.md and other docs for any
reference to its intended use, whether its Step Functions definition still
generates valid/current JSON (an orphaned generator would be a stronger
deadness signal), and whether anything else in the repo (scripts, other
state machines, runbooks) references or depends on it existing.

Resolve with a per-machine verdict (dead / intentionally dormant /
uncertain) before ticket 02's consolidation decision or any deletion work
proceeds -- deleting an intentionally-dormant disaster-recovery tool would
be a real loss, not just cleanup.
