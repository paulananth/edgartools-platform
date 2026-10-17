# Ticket 63: what each guide holds, and where each part goes

Inventory of `CLAUDE.md` (1,385 lines) and `AGENTS.md` (584 lines) on main,
2026-10-16 (section by section, the rules inside each named). Claude Code loads
`CLAUDE.md` only; Codex loads `AGENTS.md`. Proposal for the operator's review:
nothing is removed before the operator has read the "drop" list.

**The shape proposed:** `AGENTS.md` is the one shared source of every rule for
every runtime, and `CLAUDE.md` imports it (`@AGENTS.md`) and adds only what is
Claude's own. Reference material (recipes, maps, architecture) moves to
on-demand pages under `docs/agents/`, each linked from the guide in one line.

**Why one source:** the four sections both files hold have already drifted.
`AGENTS.md`'s "How to work in this repo" carries rules `CLAUDE.md`'s copy lacks:
BIGINT and 64-bit integers for every integer field (operator, 2026-10-16), the
timezone of a "same calendar day" check, provisioning outside Terraform does
not survive a rebuild, confirm the code under test is what runs, look for a
machine built for a workflow before running it by hand. A Claude session
therefore runs without those rules today.

## Shared by both today (kept, once, in AGENTS.md)

| Section | Lines (CLAUDE / AGENTS) | Proposal | Reason |
|---|---|---|---|
| Parallel Agent Workstreams | 64 / 55 | keep, shortened to the hard rules (own branch, own worktree, never `main`, protect another runtime's work) | the dated incident stories move to the 5-whys log |
| Path ownership | 9 / 9 | keep | operator rule; the guard |
| Task checklists | 30 / 30 | keep | operator rule |
| How to work in this repo | 63 / 89 | keep AGENTS.md's fuller copy | the drift above |

## CLAUDE.md only

| Section | Lines | Proposal | Reason |
|---|---|---|---|
| AWS account map | 21 | keep 3 lines always loaded (the live account; 077127448006 decommissioned, never reprovision); detail to `docs/agents/aws-accounts.md` | a wrong account is costly; the teardown story is reference |
| Snowflake dev decommissioned | 38 | keep 3 lines (no dev Snowflake; every dev command is stale; prod is `edgartools-prod`); detail to the same page | same |
| Git/GitHub text with backticks | 17 | keep 2 lines in "How to work" (already there in AGENTS.md); story dropped | rule kept, story is history |
| Quick Navigation, Architecture, Data Layer Definitions, Key Large Files | 29 + 25 + 9 + 10 | move to `docs/agents/architecture.md` | reference, read when needed |
| ECS cost sizing (old pipeline) | 10 | **drop** (or move) | the old pipeline is retired ("Rebuild is the only system", 2026-09-26) |
| edgartools Dependency, SEC data idempotency | 5 + 6 | keep (AGENTS.md "Data And Parser Notes" holds both) | rules |
| Schema conventions (BIGINT) | 6 | superseded by AGENTS.md's integer-width rule | one rule, stronger |
| Debugging discipline: 5-whys | 19 | keep, 6 lines | operator rule |
| Hard-won operational rules | 97 | keep the Snowflake, Postgres-deployment and credential rules (about 30 lines); MDM store rules already live in the `mdm-engineering` skill and stay there | rules, not stories |
| Known open items | 17 | move to `TODOS.md` | a backlog, not a rule |
| Snowflake-side facts from the old pipeline | 23 | move to `docs/agents/snowflake.md` | reference for the target platform |
| Development Commands, Image management, dbt smoke test | 26 + ~200 + 55 | move to `docs/agents/build-and-deploy.md`; Docker recipes use the context already configured | recipes |
| gstack, Skill routing, the GoF and three-axis review rules | 44 + 46 | keep in CLAUDE.md (Claude's own); the three-axis rule is also in AGENTS.md's "GoF Design Review" | runtime-specific |
| Agent skills (tracker, triage, domain docs) | 13 | keep (3 lines) | pointers |

## AGENTS.md only

| Section | Lines | Proposal | Reason |
|---|---|---|---|
| Scope | 15 | keep, its pipeline drawing updated to the rebuild (MDM, the data skills) | the drawing names only the old AWS path |
| High-Value Files | 25 | move to `docs/agents/architecture.md` | reference |
| Tooling Rules (`gh`, `uv`, ECR) | 12 | keep; Docker lines use the context already configured | rules |
| GoF Design Review | 13 | keep | rule, both runtimes |
| Runtime Settings | 22 | move to the build page; its `edgartools-dev-*` buckets are decommissioned | stale reference |
| Data And Parser Notes | 8 | keep | rules |
| AWS Terraform Model, Principal Model, Infra Flow, Image Publish, AWS MDM | 48 + 11 + 55 + 8 + 52 | move to `docs/agents/aws.md` | reference |
| Snowflake Native S3 Pull, Dev Snowflake Connection, dbt And Dashboard | 34 + 10 + 37 | move to `docs/agents/snowflake.md`; the dev connection section **dropped** | reference; dev is decommissioned |
| Tests And Verification | 26 | keep the first two lines (affected tests; CI runs all); the rest to the build page | rule plus reference |
| Safety Rules | 15 | keep | rules |

## Drop list for the operator's review

1. ECS cost sizing (old pipeline), CLAUDE.md: the retired pipeline's sizing study.
2. AGENTS.md "Dev Snowflake Connection": dev Snowflake is decommissioned.
3. Docker recipes in both guides use the Docker context already configured.
4. The dated incident narratives inside "Parallel Agent Workstreams" and "Git/GitHub text with backticks": their rules stay.

Expected size: `AGENTS.md` about 200 lines, `CLAUDE.md` about 60 lines plus the
import, against 1,969 lines loaded today.
