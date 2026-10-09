-- The match proposal snapshot plans each lookup with its own keys (profiling
-- ticket 07, tuning; operator, 2026-10-09: "tune the database before
-- continueing with the batch test").
--
-- PL/pgSQL keeps a statement's plan for the session and, after five calls,
-- may switch to a generic plan that does not see the variable's value. For a
-- lookup against a list of keys held in a variable (`= ANY(keys)`,
-- `&& keys`, `?| keys`) a generic plan cannot hash the list, so each row is
-- compared with every key: on a store of 4,000 Form ADV filings the snapshot
-- took 5.2 s with the generic plan and 0.8 s planned with its keys, and every
-- batch was slower than the one before. Research note
-- `.scratch/platform-validation/research/05b-mdm-database-tuning.md` section
-- 7 named this case and this remedy.
--
-- The setting applies only while the function runs. It is not set for the
-- session: the per-row statements in write_batch and keep_stage then plan on
-- every call and took twice as long. tests/integration/
-- test_clean_plan_cache_postgres.py holds the rule for every function.

ALTER FUNCTION mdm.match_proposal_snapshot(jsonb) SET plan_cache_mode TO force_custom_plan;
