# Eight load lanes and workers 2 to 8

Status: claimed
Type: task

Start every load at 2 workers and scale a long load to 8. Run the load chain as eight lanes (A P S C L O D F). Company-facts is F; GLEIF stays on L with the other links-table builds.

## Checklist

- [x] Stop the hosted `fresh-v2` chain (GLEIF attempt 2 left open/resumable). 2026-11-16 06:32 ET
- [x] Chain file: eight lanes (A P S C L O D F), company-facts on F, GLEIF stays on L, workers 2..8. Verified `test_the_chain_has_eight_lanes_and_company_facts_is_the_eighth` and `test_every_step_starts_at_two_workers_and_stays_at_most_eight`. 2026-11-16 06:32 ET
- [x] Skill and runbook name eight lanes and the 2-to-8 scale. Verified `test_the_skill_names_eight_lanes_and_the_two_to_eight_worker_scale`. 2026-11-16 06:32 ET
- [x] Tests: 142 passed (`tests/unit/test_load_chain.py` plus skill lints). 2026-11-16 06:32 ET
- [x] Learning → skill: data-operations Load a capture and Fit the load (eight lanes A P S C L O D F; start `--workers 2`, scale to 8; at `grain: run` scale `--bundles`). 2026-11-16 06:32 ET
