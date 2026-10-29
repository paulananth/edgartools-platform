# EdgarTools Platform

The data platform for SEC EDGAR and other provider data: a Rust source engine
reads captured files, MDM (PostgreSQL) masters them, silver lands them and
Snowflake serves gold (operator, 2026-10-14: "Snowflake is still the target
platform"; MDM's hosted target is Snowflake Postgres or Databricks Lakebase).

## What belongs in this file (operator, 2026-10-28)

1. **Only what every task needs** stays here ("do i need this for every single
   task then stays in claude.md").
2. **A specific, occasional task's rules go to its skill or rules file**, with at
   most a one-line pointer here ("specific occasional tasks move it to a skill
   or rules file").
3. **What an agent can figure out alone is deleted** (code layout, file sizes,
   commands a `--help` or the repo shows): "if agents can figure it out alone
   delete it from claude.md".

**Before any AWS, Snowflake, dbt, Terraform, image or deploy command**, use the
[aws-snowflake-operations](skills/aws-snowflake-operations/SKILL.md) skill: the
one live AWS account, the decommissioned dev environments, the Snowflake rules
and the deploy recipes.

## Parallel work (every runtime)

- **One branch per runtime, never shared**, prefixed `claude/`, `codex/` or
  `grok/`. If `git log -1` shows another runtime's commit you did not expect,
  stop and ask before committing.
- **Never commit to `main`**, not even a one-line doc fix. Before the first
  edit, create your own branch in your own worktree
  (`git worktree add ../<repo>-<topic> -b claude/<topic> origin/main`). Changes
  found on `main`: branch off `HEAD`, then reset `main` to `origin/main`.
- **One worktree per session**: a shared checkout switched by another session
  disrupts yours. If your branch changed under you, check `git branch
  --show-current`, `git reflog` and that your commits resolve before recovering;
  push your branch as soon as it is good.
- Before editing, run `git status --short` and `git log -1`, and read
  `.planning/active-workstream` when present.
- Never edit another runtime's open PR, worktree or `.planning/workstreams/`
  directory, and never stage or revert its changes; build on it once it merges.

## Shared local data (operator, 2026-10-16)

For recurring loads, delivery readiness, file changes, resource sizing and run
recovery, use [data-operations](skills/data-operations/SKILL.md).

- Initial and daily runs enumerate the entire available source delivery
  (operator: "always load everything from source"). The Change Journal skips
  files already processed with the same source, key, content hash and processing
  identity. Changed rules or relevant shared inputs also require reprocessing.
  Leave `--all` off for normal runs; use it only for an explicit forced replay.
  Read [the load sequence](docs/initial-and-daily-source-load.md) before SEC,
  GLEIF or OpenFIGI loads. Provider access retains its existing authorization.
- Use one permanent local PostgreSQL 16 server shared by all agents. Initialize
  MDM, RDM, Rules, Bookkeeping and Change Journal by default; retain existing
  silver without initializing or migrating it.
  All agents look up the same Company identities in the shared MDM.
  The server runs on the Docker context already configured on the machine
  (operator, 2026-10-17). Start, inspect, back up and copy it with
  `infra/scripts/local-test-stores.py`. The procedure is
  [Initialize shared local PostgreSQL](docs/local-agent-testing.md).
  Source its private `worker.env` before work and `verifier.env` before verification.
- Separate Git worktrees isolate code edits; routine lookups and development
  use the existing shared server, without creating a server per agent.
  Use its private runtime connection file outside Git; never print its values.
- Master data changes go through the Merge Stage. Other writes use each
  store's normal application code and restricted roles. Coordinate changes
  to shared schemas, rules and records so agents do not overwrite each other.
- Use a separate test environment only when a test could disrupt shared data,
  such as deleting records, testing recovery or applying experimental migrations.
- Coordinate shared-server maintenance with its current users. Keep lifecycle
  commands with the creating worktree; client access from other worktrees is
  allowed. Never stop, restore or replace shared data while others use it.
- This shared-server default supersedes the per-agent-copy default in local
  testing guides and skills. Their backup and copy procedures remain available
  for isolated tests. Local testing does not qualify a Snowflake deployment.

## Path ownership (operator, 2026-10-16)

Nothing is owned by Codex (operator, 2026-10-16: "nothing is owned by codex"):
any runtime edits any path. Run the guard before every commit and push:
`bash scripts/dev/overlap_guard.sh` (exit 0 = no overlap; exit 1 lists each
file an open PR or worktree of another runtime also touches). On an overlap,
build on that work once it merges, or rebase onto it; never edit beside it.
Run it on its own, never piped (`guard | tail -1 && git commit` takes `tail`'s
exit status, so a STOP lets the commit and push run; it did, 2026-10-22).

## Task checklists (MUST, every ticket, every runtime)

**HARD RULE: every ticket keeps its parts as a Markdown checklist in the
ticket file itself, and keeps it current until the ticket closes, including
while completing it.** No exception for small tickets or "last step" work.
Operator rule, 2026-09-24.

- List every part before starting: `- [ ] <part>`. Add parts that surface
  mid-work (a decision the user took, a finding, a follow-up) as they appear.
- Tick a part only when it is done and verified: `- [x] <part>`, naming how it
  was verified (test, PR, live check) on the same line.
- A part that is skipped, deferred or moved to another ticket stays on the
  list, marked `- [ ] ~~<part>~~ deferred to <ticket>: <why>`. Never delete it.
- Before reporting a ticket complete, re-read its checklist. Any unchecked part
  means the report says "incomplete" and names it.

**Time matters.** Stamp each checked part with its completion time in local
ET (`2026-09-24 14:05 ET`), never UTC. Say up front when a part will take long
(a full scan, a large test suite, a deploy), and report the elapsed time of any
step over ten minutes, so the operator can see where the time went.

- **Read the clock before every stamp:** `TZ=America/New_York date`. A
  guessed time is wrong more often than not.
- **The last part of every ticket is `Learning → skill`.** Name the skill
  line the ticket changed with what it learned, or write "none". A rule,
  practice or how-to learned here belongs in a skill (data work, MDM
  engineering) or in this file (how to work in this repo), never only in a
  ticket or in one runtime's private memory. A skill issue found while
  working is fixed in the skill, on its own branch and PR.


## How to work in this repo (every runtime)

Learned the hard way; each is a standing operator rule.

**Tests and CI**
- Run only the tests a change can affect ("Test baseline", below). No local
  test run may take more than five minutes; CI runs everything.
- Merge when every CI check is green and the PR is ready, without asking:
  merging is automatic (operator, 2026-10-17: "auto merge and not ask for
  approval"). Watch CI, merge on green, and report the merge.
  `main` requires no checks, so the watcher is the only gate: it merges only
  when every check reads `pass` (or `skipping`), counted against all checks,
  and stops on any other state. One that merged when nothing was pending put
  a red unit job on `main` (2026-10-26, #1185).
- Green means green on today's `main`: a PR whose base moved since its CI ran is
  updated (`gh pr update-branch`) and waits for CI again before it merges; two
  PRs each green alone broke `main` together (2026-10-18).
- A test states its expected answer; it never compares with a frozen copy of
  retired code. To retire such an oracle, write its answers into the test (or an
  answer file written once while the two still agree), change each answer once
  to see the test fail, and compute any value that follows the clock (ticket 88).
- A conclusion reached by reading code is not proof of behaviour: test each
  case the claim covers (one test per kind, per source), since the untested
  case is where a gap hides.
- Every background watcher (CI, a long test, a proof) has a deadline and an
  exit for every outcome, including the PR merging or closing. Stop test
  containers when a run ends, however it ends. macOS has no `timeout`
  command (a watcher wrapped in it exits at once and does nothing); give the
  deadline with a background `sleep N; kill <pid>` instead.
- A run already going (a proof, a load, a recovery) is checked every 30
  minutes, not on a tighter loop (operator, 2026-10-24: "do not use token
  constantly polling the runs check every 30 min"). A check that finds
  nothing changed sends no message. A failure, a finished part, or the end
  is reported at that check.
- Choose the cheapest proof that proves the change (the `mdm-engineering`
  skill, "Choose the cheapest proof"); say the time of any step over ten
  minutes before starting it.

**Commits, PRs and secrets**
- One branch per ticket, cut fresh off `origin/main` in its own worktree;
  never continue a ticket on a used or merged branch (PRs are squash-merged).
- Work only in this repository. Never commit, push or open a PR in another
  repository, even for a task that spans repositories.
- Commit and PR text from a file: `git commit -F <file>`, `gh pr create --body-file <file>`.
  Never an inline heredoc: backticks inside one have run as commands even with
  `<<'EOF'`, silently mangling the text.
- Never print a secret, a password, a token or a database address, and never
  ask the operator to type one into the chat. Read them from environment
  variables; if one is missing, ask the operator to set it in their own
  terminal. Redact by key name (any key containing `password`, `secret`,
  `token`, `key`, `dsn` or `url`), never by an exact list, and never pipe a
  secrets fetch to `head`, `cat` or a variable you print.
- This repository is public: counts and invented examples only, never a
  value from the data (a name, an identifier, a record).
- No request to a data provider (its site, API or documentation) without the
  operator's permission for that request.

**Talking with the operator**
- Every time shown to the operator is local ET, including times read from
  AWS, Postgres or CI, which report UTC.
- Report findings with their numbers and what they mean, not the steps you
  are about to take.
- Use the business words of `CONTEXT.md`; translate engine terms first (a
  "matching rule", not a "binding rule").
- Do not ask for approval (operator, 2026-10-17: "auto merge and not ask for
  approval"). Where a step or a skill needs an approval, record it as given
  under this rule, with these words and the ET time, and say in plain words
  what was approved, what it changes and on what evidence. A digest, hash or
  version number goes beside the explanation, never instead of it. A rule
  version has a descriptive name.
- Decide what follows from a ruling already given, say so, and go on. Stop
  only for a switch-on or a new kind of decision, and then ask one question
  at a time with your recommendation.

**Stores**
- Every integer field follows the [integer-width rule in AGENTS.md](AGENTS.md#how-to-work-in-this-repo-every-runtime),
  years and quarters included.
- Captured SEC files are additive and immutable; reprocessing retained bytes is
  not a provider re-fetch, which needs its own authorization.
- Writes into Snowflake's SQL layer go through dbt. MDM's own Postgres store
  is written by its own code (SQLAlchemy), not dbt.

**Debugging**
- Root cause first: ask "why" until the cause is not just the trigger, and fix
  the cause. A recurring lesson goes where it belongs (a skill, or this file) as
  Problem, Root cause, Fix and Lesson in 4-8 lines, never the narrative.
- Before running a multi-step workflow by hand, look for the one already built
  (a Bookkeeping run, a committed script). Confirm the code under test is the
  code running before trusting a clean result.

**Test baseline**

- No test is expected to fail: CI is green on `main`.
- **Locally, run the tests a change can affect; CI runs everything** (operator, 2026-09-29, after a
  16-minute integration run). `pytest-testmon` records which code each test executes and re-runs only
  the tests touching changed Python: `TESTMON_DATAFILE=~/.cache/edgartools/testmondata uv run pytest
  --testmon <folders>` (one shared record for every worktree; a test never recorded always runs; it needs pytest's cache,
  so never add `-p no:cacheprovider`).
  It cannot see non-Python inputs: after a change to a migration `.sql`, a rules `.yaml` or another
  data file, also run that area's test files by name. The full suite runs in CI on every PR, and
  nothing merges until it is green.
- **A change to skills, tickets or docs only** needs no project environment, so never
  `uv sync` a new worktree for it (several minutes, Rust engine included; operator,
  2026-10-28: "If the skills test is building the whole environment it is a waste").
  The genericity lint reads files only: `uv run --no-project --with pytest -- pytest -q
  -p no:cacheprovider tests/unit/test_profiling_genericity.py` (under 1 s), and after an edit to
  CLAUDE.md or AGENTS.md, `tests/unit/test_guides_name_existing_paths.py` the same way. CI runs the rest.
- **A change to the Rust engine** (`crates/source-contract/`) reaches Python only after
  `uv sync --all-extras --group dev --reinstall-package source-contract`; until then Python tests run
  the old engine. testmon then reruns nearly every test (10 minutes, ticket 138), so name the area's
  test files instead. The storage-adapter scenarios run locally on MySQL with
  `CI=true SKILL_ADAPTER_TEST_ENGINE=mysql uv run --no-sync pytest tests/storage_adapters/...` (the database clients are in the `dev` group);
  remove the `skill-adapter-proof-*` containers after.

## Code review (HARD RULES)

- **Before writing or editing any production code, consult
  `/gof-refactor-reviewer`** on the area you will touch, however small the
  change (its default verdict is "leave it", so it costs seconds).
- **`/code-review` runs three axes: Standards, Spec and GoF**, as parallel
  agents. The skill's own template lists two; add the GoF agent, briefed with
  `/gof-refactor-reviewer`'s instructions on the same diff, and report it under
  its own `## GoF` heading. The pre-code consult does not replace it.

## Agent skills

- Issues and Wayfinder maps: local Markdown under `.scratch/` (`docs/agents/issue-tracker.md`).
- Triage labels: the default five-role vocabulary (`docs/agents/triage-labels.md`).
- Domain docs: root `CONTEXT.md` and `docs/adr/` (`docs/agents/domain.md`).
- Web browsing: gstack's `/browse`, never the `mcp__claude-in-chrome__*` tools.
