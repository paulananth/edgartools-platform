# Inventory in-repo contract semantics versus SQL sketches

Type: research
Status: resolved
Blocked by: none

## Question

Against the in-repo Python serving modules and SQL sketches, what is the
canonical Decision Contract behavior today, and where do the two surfaces
disagree?

Read at least:

- `edgar_warehouse/serving/decision_contract.py`
- `edgar_warehouse/serving/watermark_aggregator.py`
- `edgar_warehouse/serving/subject_feature_screen.py`
- `edgar_warehouse/serving/subject_bundle_read.py`
- `edgar_warehouse/serving/dashboard_modes.py`
- `infra/snowflake/sql/decision_contract/*.sql`
- matching tests under `tests/unit/`

Determine specifically:

1. How `evaluate_agent_grade` decides aligned vs not.
2. Which watermark fields Python emits versus which SQL columns exist.
3. How the feature screen builds universe membership versus Ticket 14
   warehouse-active ∩ MDM-active.
4. Which issuer bundle sections Python can build versus which SQL views
   exist (including auditor SOURCE vs GOLD).
5. How Agent View vs Explore is encoded in Python, if at all.

Save findings at
`.scratch/agent-decision-contract/research/02-in-repo-contract-semantics.md`.
Cite file paths and symbols. Do not implement.

## Answer

Canonical in-repo Decision Contract behavior is the Python serving layer
(`evaluate_agent_grade`, screen/bundle builders, `dashboard_modes`). SQL
under `infra/snowflake/sql/decision_contract/` is a disagreeing sketch
surface (MDM-only universe, `GOLD_UPDATED_AT` instead of `gold_run_id`,
issuer bundle without neighborhood sections, auditor from SOURCE, no
Agent View vs Explore). Full inventory with symbols:

[.scratch/agent-decision-contract/research/02-in-repo-contract-semantics.md](../research/02-in-repo-contract-semantics.md)
