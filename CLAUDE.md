# EdgarTools Platform

The data platform for SEC EDGAR and other provider data: a Rust source engine
reads captured files, MDM (PostgreSQL) masters them, codes go to RDM and silver
lands every detail. The platform ends at silver; gold and dashboards come later
(operator, 2026-11-12). MDM's hosted target is Snowflake Postgres or Databricks Lakebase.

## What belongs in this file (operator, 2026-10-28)

1. **Only what every task needs** stays here ("do i need this for every single
   task then stays in claude.md").
2. **A specific, occasional task's rules go to its skill or rules file**, with at
   most a one-line pointer here ("specific occasional tasks move it to a skill
   or rules file").
3. **What an agent can figure out alone is deleted** (code layout, file sizes,
   commands a `--help` or the repo shows): "if agents can figure it out alone
   delete it from claude.md".

Every rule shared by all runtimes lives here, once. `AGENTS.md` (Codex and
Grok) holds only what those runtimes need beyond this file and points here; it
never copies a rule, since copies drift (ticket 63, 2026-11-03; ticket 213).

## Skills and guides: when to open each

- **Before any AWS, Snowflake, Terraform, image or deploy command**:
  [aws-snowflake-operations](skills/aws-snowflake-operations/SKILL.md) (the one
  live AWS account, the hosted MDM store and the deploy recipes).
- **Before a load, or for delivery readiness, file changes, resource sizing and
  run recovery**: [data-operations](skills/data-operations/SKILL.md); before
  SEC, GLEIF or OpenFIGI loads also [the load sequence](docs/initial-and-daily-source-load.md).
- **Choosing tests, or starting a watcher**: [the recipes](docs/agents/watching-and-testing.md).
- **Starting, backing up or copying the local stores**:
  [Initialize shared local PostgreSQL](docs/local-agent-testing.md).
- **Choosing a skill, or installing them**: [the skills index](skills/README.md)
  (`bash skills/link.sh`).
- Issues and Wayfinder maps: local Markdown under `.scratch/` (`docs/agents/issue-tracker.md`).
- Triage labels: the default five-role vocabulary (`docs/agents/triage-labels.md`).
- Domain docs: root `CONTEXT.md` and `docs/adr/` (`docs/agents/domain.md`).
- Web browsing: gstack's `/browse`, never the `mcp__claude-in-chrome__*` tools.

## Parallel work (every runtime)

- **One branch per runtime, never shared**, prefixed `claude/`, `codex/` or
  `grok/`. If `git log -1` shows another runtime's commit you did not expect,
  stop and ask before committing.
- **Never commit to `main`**, not even a one-line doc fix. Before the first
  edit, create your own branch in your own worktree
  (`git worktree add ../<repo>-<topic> -b claude/<topic> origin/main`). Changes
  found on `main`: branch off `HEAD`, then reset `main` to `origin/main`.
- **One branch per ticket**, cut fresh off `origin/main` in its own worktree;
  never continue a ticket on a used or merged branch (PRs are squash-merged).
  Name it new: the remote keeps a merged branch's name and refuses a push to it
  (ticket 175's second PR).
- **One worktree per session**: a shared checkout switched by another session
  disrupts yours. If your branch changed under you, check `git branch
  --show-current`, `git reflog` and that your commits resolve before recovering;
  push your branch as soon as it is good.
- Before editing, run `git status --short` and `git log -1`.
- Never edit another runtime's open PR or worktree, and never stage or revert
  its changes; build on it once it merges.
- Work only in this repository. Never commit, push or open a PR in another
  repository, even for a task that spans repositories.

## Path ownership (operator, 2026-10-16)

Nothing is owned by Codex (operator, 2026-10-16: "nothing is owned by codex"):
any runtime edits any path. The overlap guard decides, before every commit and
push: `bash scripts/dev/overlap_guard.sh` (exit 0 = no overlap; exit 1 lists
each file an open PR or worktree of another runtime also touches).

- Commit and push with `bash scripts/dev/commit_push.sh <message-file>`: it
  stamps `{{now}}`, runs the guard, and commits and pushes only if the guard
  exits 0.
- Run the guard on its own, never piped or chained (`guard | tail -1 && git
  commit` takes `tail`'s exit status, so a STOP lets the commit and push run;
  it did, 2026-10-22; a `;`-chained guard did the same, 2026-11-10).
- On an overlap, build on that work once it merges, or rebase onto it; never
  edit beside it.
- The guard also fails an ET stamp in `.scratch/` that is later than the clock
  (ticket 155), and a changed ticket marked `Status: resolved` that has an open
  part (ticket 157). A ticket merges with its PR, so "PR merged" is no part of
  it: the PR is that record.

## Task checklists (MUST, every ticket, every runtime)

**HARD RULE: every ticket keeps its parts as a Markdown checklist in the
ticket file itself, and keeps it current until the ticket closes, including
while completing it.** No exception for small tickets or "last step" work.
Operator rule, 2026-09-24.

- List every part before starting: `- [ ] <part>`. Add parts that surface
  mid-work (a decision the user took, a finding, a follow-up) as they appear.
- Tick a part only when it is done and verified: `- [x] <part>`, naming how it
  was verified (test, PR, live check) on the same line.
- Stamp each checked part with its completion time in local ET
  (`2026-09-24 14:05 ET`), never UTC. **Never type a time**: write `{{now}}`
  where a stamp goes and `commit_push.sh` stamps it from the clock (a typed
  time ran ahead of the clock and shipped, 2026-11-10).
- A part that is skipped, deferred or moved to another ticket stays on the
  list, marked `- [ ] ~~<part>~~ deferred to <ticket>: <why>`. Never delete it.
- Before reporting a ticket complete, re-read its checklist. Any unchecked part
  means the report says "incomplete" and names it.
- **The last part of every ticket is `Learning → skill`.** Name the skill
  line the ticket changed with what it learned, or write "none". A rule,
  practice or how-to learned here belongs in a skill (data work, MDM
  engineering) or in this file (how to work in this repo), never only in a
  ticket or in one runtime's private memory. A skill issue found while
  working is fixed in the skill, on its own branch and PR.

## How to work in this repo (every runtime)

Learned the hard way; each is a standing operator rule.

**Tests**
- No test is expected to fail: CI is green on `main`. Locally, run only the
  tests a change can affect, by [the recipes](docs/agents/watching-and-testing.md);
  no local test run may take more than five minutes; CI runs everything. A
  skills, tickets or docs change needs no environment. Storage-adapter tests
  run through `bash scripts/dev/adapter_test.sh <tests>`.
- A fresh worktree's `.venv` folder exists before `uv sync` has run: test for
  `.venv/bin/pytest`, not the folder, before `uv run --no-sync`.
- A test states its expected answer; it never compares with a frozen copy of
  retired code. To retire such an oracle, write its answers into the test (or an
  answer file written once while the two still agree), change each answer once
  to see the test fail, and compute any value that follows the clock (ticket 88).
- A fix PR names the test that failed before the fix and how it failed (the
  assertion, not just "red"): a test that passes on the old code proves nothing
  (ticket 152's first test did, 2026-11-01). The Standards reviewer checks the line.
- A conclusion reached by reading code is not proof of behaviour: test each
  case the claim covers (one test per kind, per source), since the untested
  case is where a gap hides.

**Merging**
- Merge when every CI check is green and the PR is ready, without asking
  ("Talking with the operator", below). Watch CI, merge on green, and report
  the merge.
  `main` requires no checks, so the watcher is the only gate. Use
  `bash scripts/dev/merge_on_green.sh <pr> [minutes]` in the background, never
  a hand-written loop: it counts only the CI runs of the PR's current head
  commit and merges that commit by name. Right after a push, `gh pr checks`
  still lists the previous commit's green checks; loops that read it merged
  code CI had not run (#1185, 2026-10-26; #1245, 2026-10-30).
- Green means green on today's `main`: a PR whose base moved since its CI ran is
  updated (`gh pr update-branch`) and waits for CI again before it merges; two
  PRs each green alone broke `main` together (2026-10-18).

**Long steps and runs**
- Before any step that takes more than a few minutes (a proof, a load, a full
  test run), check it against [the seven wastes](skills/data-platform/SKILL.md#the-seven-wastes)
  and drop what adds no value: run the cheap check that can fail it first, never
  repeat a full-size step only to confirm it, and keep a failed run's stores so it
  restarts at the failed step (ticket 48, 2026-10-30: two runs of 45 min, one lost).
- Choose the cheapest proof that proves the change (the `mdm-engineering`
  skill, "Choose the cheapest proof").
- A step over ten minutes (a full scan, a large test suite, a deploy): say its
  time before starting it, sample its first two minutes with
  `scripts/dev/run_sample.py` (it reports what limits the run, and whether the
  machine can measure at all), and report its elapsed time after, so the
  operator can see where the time went.
- A run already going (a proof, a load, a recovery) is checked every 30
  minutes, not on a tighter loop (operator, 2026-10-24: "do not use token
  constantly polling the runs check every 30 min"). A check that finds
  nothing changed sends no message. A failure, a finished part, or the end
  is reported at that check.
- Every background watcher has a deadline and an exit for every outcome, and test
  containers stop when a run ends ([the detail](docs/agents/watching-and-testing.md)).

**Commits, PRs and secrets**
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

**Code and stores**
- **Build generic** (operator, 2026-11-04: "Always build generic make it a
  rule"): a case that has a sibling (a second identifier class, source, kind or
  format) is built once for all of them, as a list, a parameter or one shared
  table the rules or code read, never as a copy per case. Adding the next case
  is a line of configuration and one test. Where today's tool cannot express
  the list (the rules language has no loop), say so and make the shared path
  work for the other cases; do not copy.
- **Number types** (operator, 2026-10-16 and 2026-11-04: "always use BIGINT and
  BIGDECIMAL and NUMBER"): an integer field or counter is database `BIGINT`
  and 64-bit `long`/`i64` in code, years, quarters and positions included,
  never 32-bit `INT`/`INTEGER` or narrower. A decimal or fraction is an exact
  `BIGDECIMAL` in code and `NUMBER(precision, scale)` in a database, never
  `FLOAT`, `DOUBLE` or `REAL`; its precision and scale come from the profiled
  maximum digits and decimal places, with room for the widest value. Python's
  built-in integer has arbitrary precision: keep that source precision. Check
  representability before publication; preserve and flag an out-of-range
  original for explicit handling instead of wrapping, truncating, or
  converting it through floating point.
- Captured SEC files are additive and immutable; reprocessing retained bytes is
  not a provider re-fetch, which needs its own authorization.
- Each store is written by its own code (SQLAlchemy).

**Debugging**
- Root cause first: ask "why" until the cause is not just the trigger, and fix
  the cause. A recurring lesson goes where it belongs (a skill, or this file) as
  Problem, Root cause, Fix and Lesson in 4-8 lines, never the narrative.
- Before running a multi-step workflow by hand, look for the one already built
  (a Bookkeeping run, a committed script, a Step Functions state machine). Confirm the code under test is the
  code running before trusting a clean result.

## Code review (HARD RULES)

- **Before writing production code, consult `/gof-refactor-reviewer`** on the area you
  will touch. A change of about ten lines inside one function needs no consult (operator,
  2026-11-06: small changes came back "leave it" every time).
- **`/code-review` runs three axes: Standards, Spec and GoF**, as parallel
  agents. The skill's own template lists two; add the GoF agent, briefed with
  `/gof-refactor-reviewer`'s instructions on the same diff, and report it under
  its own `## GoF` heading. The pre-code consult does not replace it.

## Shared local data (operator, 2026-10-16)

**Loads**
- Initial and daily runs enumerate the entire available source delivery
  (operator: "always load everything from source"). The Change Journal skips
  files already processed with the same source, key, content hash and processing
  identity. Changed rules or relevant shared inputs also require reprocessing.
- Leave `--all` off for normal runs; use it only for an explicit forced replay
  (force publish: `load --force`, which ignores the Change Journal and processes
  the source again). Provider access retains its existing authorization.

**The shared server**
- Use one permanent local PostgreSQL 16 server shared by all agents, on the
  Docker context already configured on the machine (operator, 2026-10-17). All
  agents look up the same Company identities in the shared MDM. Separate Git
  worktrees isolate code edits; routine lookups and development use the
  existing shared server, without creating a server per agent.
- Initialize MDM, RDM, Rules, Bookkeeping, Change Journal and Silver by default
  (operator, 2026-11-03: "pipeline must complete both mdm and silver
  together"); a run's env files carry the silver login. Start, inspect, back up
  and copy the server with `infra/scripts/local-test-stores.py`.
- Source its private `worker.env` before work and `verifier.env` before
  verification; both live outside Git, and their values are never printed.
  `worker.env` holds `RULES_DATABASE_URL` too; it is never missing, so never ask for it
  (operator, 2026-11-02: "This must be documented, you cannot keep on asking").
- To try a source, `load` it into a disposable stores folder (`local-test-stores.py up <name>`; `stop` it
  after): [data-onboarding](skills/data-onboarding/LOAD.md).

**Writing to it**
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
  for isolated tests.
