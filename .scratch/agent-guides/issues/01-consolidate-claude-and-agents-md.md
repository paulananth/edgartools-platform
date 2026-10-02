# Consolidate CLAUDE.md and AGENTS.md

Status: open, not started.
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

- [ ] List every rule in today's CLAUDE.md and AGENTS.md. For each, mark it as kept, moved to an on-demand doc (linked), or dropped, with the reason
- [ ] Make AGENTS.md load for Claude (`@AGENTS.md` import in CLAUDE.md), and check it in a fresh session
- [ ] Operator review of the dropped list before any rule is removed
- [ ] PR, CI green, merge on the operator's word
