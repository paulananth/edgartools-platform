# Bookkeeping skill

Owner: Codex. Branch: `codex/bookkeeping-skill`.
Worktree: `edgartools-platform-bookkeeping-skill`.

User request: create a skill to use Bookkeeping, checking Claude's branch for
guidance. Read-only guidance came from `claude/rules-07-skill` at `8272d572`:
`skills/rules/SKILL.md`, `REFERENCE.md`, `agents/openai.yaml` and `link.sh`.
The skill follows its repository-owned shared layout, progressive reference,
command verification and explicit gap reporting. Commands come from the
implemented Bookkeeping and Rules CLIs, not the older planned Rules syntax.
Claude's branch, worktree and files were not edited.

Used `skill-creator` and `writing-for-agents`, including invocation mechanics.
Automatic discovery remains enabled. GoF review of the link helper and its
one-commit history found no pattern refactoring worth its cost: keep a small
shell helper and preserve unrelated destination paths.

Covers submission, bounded inspection/recovery, immutable stage manifests,
actual lease/proof semantics, incomplete delivery/publication, Rules proof and
approval boundaries, and unsupported capabilities. `RECOVERY.md` is reached
for incomplete runs; schema detail stays in the implementation specification.

## Merges and base

Core PR #732 merged as `155fb8ef`; stage PR #734 merged as `dab3edf0`.
Both had all seven CI checks green, including mandatory PostgreSQL integration.
This skill branch is based on refreshed `origin/main` at `dab3edf0`; the tested
implementation tree was unchanged by the squash merges.

## Verification

- Skill Creator's `quick_validate.py`: passed, with no scaffold placeholders.
- Eleven documented command forms parsed by the real CLI without executing
  handlers or accessing a database/provider.
- Link installer tested with a temporary home: successful installation,
  idempotent repeat, refusal of an existing directory and a foreign dangling
  symlink, and rejection of malformed arguments. Neither destination changes
  when preflight rejects a conflict. Metadata and relative references passed.
- `bash -n` and `git diff --check`: passed.
- Installed shared discovery at `~/.agents/skills/bookkeeping`, with Claude's
  link at `~/.claude/skills/bookkeeping`; both resolve to this checkout's skill.

No pipeline handlers, Rules approvals, source fetches or database migrations
were executed for skill validation. The shared dirty checkout is unchanged.

Next implementation frontier remains source-owned bounded SEC worklists and
actual capture/parse/silver capabilities, followed by legacy entry-point
migration and PostgreSQL recovery qualification. The skill documents these
gaps instead of claiming they have already been implemented.
