# Consolidate CLAUDE.md and AGENTS.md

Priority: 63, tier 4, housekeeping. Map: [Rebuild priorities](../map.md). Moved from `.scratch/agent-guides/issues/01-consolidate-claude-and-agents-md.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Status: resolved (2026-11-03 20:58 ET, operator: "ticket 63 cleanup").
Raised 2026-10-02 by the operator's choice "Split it out (Recommended)". Codex's draft PR #780 rewrote both guides. That rewrite is now taken out of the mastering qualification work and becomes this ticket.

## What Codex proposed

Codex's version is at commit `744cba55` on branch `codex/mastering-rebuild-20261001`.

- **CLAUDE.md:** shrinks to 17 lines and points to AGENTS.md in prose only.
- **AGENTS.md:** 127 lines, the shared source for all runtimes.
- **Effect:** the always-loaded guidance drops from about 1,796 lines to about 140.

## Why it was split out

- **AGENTS.md doesn't reach Claude.** Claude Code loads CLAUDE.md, not AGENTS.md. A prose mention means a Claude session never reads AGENTS.md; the file must be imported with `@AGENTS.md`.
- **Rules left out of always-loaded text:**
  - the AWS account map (`077127448006` is decommissioned);
  - the warning that dev Snowflake is decommissioned;
  - never pipe secrets to head, tail or cat;
  - the testmon commands for affected tests;
  - the Snowflake lessons (cursor form, GRANT OWNERSHIP, TIMEZONE, task cost, paramstyle);
  - the Postgres lessons (test migrations on populated tables, partial unique indexes, N+1);
  - known open items;
  - 5-whys;
  - BIGINT for count columns.

## Checklist

- [x] List every rule in today's CLAUDE.md and AGENTS.md. For each, mark it as kept, moved to an on-demand doc (linked), or dropped, with the reason: `research/63-guide-inventory.md`, section by section with the rules each holds; AGENTS.md as the one shared source imported by CLAUDE.md, reference to `docs/agents/` pages, a four-item drop list; found that the shared "How to work" section has drifted (five rules only in AGENTS.md reach no Claude session) (2026-10-16 19:58 ET)
- [ ] ~~Make AGENTS.md load for Claude (`@AGENTS.md` import in CLAUDE.md), and check it in a fresh session~~ superseded: CLAUDE.md was since cut to what every task needs (operator, 2026-10-28), so importing a shared AGENTS.md would put its lines back in every Claude session; the shared rules live in CLAUDE.md and AGENTS.md points to it instead
- [x] (2026-11-03 20:58 ET) The drift the ticket named reaches Claude: BIGINT (linked from CLAUDE.md to AGENTS.md's integer-width rule), the timezone of a "same calendar day" check and provisioning outside Terraform (both in `skills/aws-snowflake-operations/SKILL.md`, which CLAUDE.md sends Claude to before any AWS or Snowflake command), confirm the code under test and look for a built workflow (CLAUDE.md, Debugging)
- [x] (2026-11-03 20:58 ET) AGENTS.md cut from 642 to 213 lines: Scope redrawn for the rebuild; the four sections CLAUDE.md also holds (parallel work, shared local data, path ownership, task checklists) replaced by a pointer to CLAUDE.md; AWS (Terraform model, principals, infra flow, image publish, MDM, runtime settings), Snowflake pull and dbt, and High-Value Files moved unchanged to `docs/agents/aws.md`, `snowflake.md`, `architecture.md`, each linked from AGENTS.md. Guide-path and genericity lints 95 passed
- [x] (2026-11-03 20:58 ET) Operator review of the dropped list: the operator's word "ticket 63 cleanup". Dropped: AGENTS.md's own older copies of the four shared sections (their rules are in CLAUDE.md; the 2026-08-28 incident story is history). Nothing else is removed, the reference sections moved whole
- [x] (2026-11-03 20:58 ET) PR, CI green, merge: the PR is the record and merges on green under the standing rule (operator, 2026-10-17)
- [x] (2026-11-03 20:58 ET) Learning → skill: `CLAUDE.md`, "What belongs in this file": AGENTS.md holds only what the other runtimes need beyond CLAUDE.md and never copies its rules
