# Test note: eight load lanes and workers 2 to 8

For the agent that tests the change in PR https://github.com/paulananth/edgartools-platform/pull/1824. Counts only in public reports. Never print a secret, password, token, or database address.

## What landed

PR 1824 merged 2026-11-16 06:41 ET.

- Squash head: `11bc179c`
- `main` merge: `517f12d0`
- Ticket: `.scratch/load-workers-lanes/issues/01-eight-lanes-workers-2-to-8.md`

Use current `origin/main` in a fresh `grok/` worktree. Do not edit another runtime's open PR or worktree.

## What the change is

1. **Eight lanes** in `rules/load-chain.yaml` and the data-operations skill/runbook: `A P S C L O D F`.
   - **F** is `company-facts` (runs beside 13F filings and registration on D).
   - **L** still holds the links-table builds and GLEIF. GLEIF is not an eighth lane: that failed `test_the_steps_that_build_links_share_one_lane` (`{'A', 'G', 'L'}`) and `test_the_last_links_build_follows_every_source_that_states_links` (`nport-fund` missing from GLEIF's ancestors). One lease on the links table; those steps take turns on L.
2. **Workers start at 2, cap 8** on every chain step (`workers:` in the yaml). OpenFIGI answers and company-facts already sit at 4.
3. **Skill recipe** (`skills/data-operations/SKILL.md`, Load a capture / Fit the load; `RUNBOOK.md` loop):
   - `for lane in A P S C L O D F`
   - Start `--workers 2`; a long load scales to 8 (the two-minute sample will miss the window, or a step already ran past ten minutes), at most the host's cores.
   - At **`grain: run`** (today's load default / "no bookkeeping"), `--workers` adds nothing. Scale **`--bundles` 2 to 8**. A merge into shared masters (GLEIF) stays at **one bundle** when memory is the limiter.

## Cheap tests (do these first)

From a checkout at `origin/main`:

```bash
pytest -q -p no:cacheprovider \
  tests/unit/test_load_chain.py \
  tests/unit/test_skills_cite_no_ticket.py \
  tests/unit/test_profiling_genericity.py \
  tests/unit/test_guides_name_existing_paths.py
```

These must pass, including:

- `test_the_chain_has_eight_lanes_and_company_facts_is_the_eighth` — lanes `APSCLODF`, company-facts on F
- `test_every_step_starts_at_two_workers_and_stays_at_most_eight`
- `test_the_skill_names_eight_lanes_and_the_two_to_eight_worker_scale` — skill and runbook contain `A P S C L O D F`, `Start --workers 2`, `scales to 8`
- existing deadlock / waits_for / links-lane tests still green
- `skills/data-operations/SKILL.md` still under 500 lines

Read-only plan (writes nothing):

```bash
python skills/data-operations/scripts/load_chain.py --list
python skills/data-operations/scripts/load_chain.py --plan
```

Expect eight distinct `lane` values. `--plan` needs hosted `worker.env`; do not print it.

## Hosted store (only if the operator asks to load)

- Stores folder: `~/.config/edgartools/hosted/` (`connection.env`, `worker.env`, `governance.env`). Source privately. Never print URLs.
- The previous chain **`fresh-v2`** was **stopped** 2026-11-16 around 06:27 ET. Forty of 41 steps were done. **GLEIF mastering** is the remainder: attempt 1 hit the 240-minute window; attempt 2 was finishing open run `651d5ba7` (`Finishing run ... left open before`). Resume with the **same** `load` command (Change Journal plus that open run). Do not start a second GLEIF load beside it.
- Last GLEIF command used `--workers 1 --bundles 1 --minutes 240`. After this change, yaml starts GLEIF at **workers 2, bundles 1**. At `grain: run`, extra workers add nothing; raising **bundles** on GLEIF risks memory on an 8 GiB host.
- Eight lane processes: `load_chain.py --lane` for each of `A P S C L O D F`, then `--finish`. Already-done steps are cheap no-ops.
- Check every **30 minutes**. Public reports: **counts and times only**.
- Keep the machine awake: `caffeinate -i` / `caffeinate -w <pid>`. Kill leftover caffeinate when you stop.

Do not drop or recreate hosted databases, rotate Snowflake Postgres passwords, or run `bootstrap-prod-mdm.sh`.

## What this change does not prove

The unit tests prove the **chain file and skill text**. They do not prove an 8-lane hosted load is faster, or that `--workers 8` shortens a `grain: run` merge. A live proof is a timed resume of GLEIF (same run) plus `--plan` showing eight lanes, only if the operator starts a load.

## Files to read

- `rules/load-chain.yaml` (lanes, `workers`, GLEIF on L, company-facts on F)
- `skills/data-operations/SKILL.md` (Load a capture, Fit the load)
- `skills/data-operations/RUNBOOK.md` (the `for lane in A P S C L O D F` loop)
- `tests/unit/test_load_chain.py` (the three new tests after the links-lane test)
- `skills/data-operations/scripts/load_chain.py`
