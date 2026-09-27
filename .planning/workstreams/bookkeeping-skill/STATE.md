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
This skill branch was refreshed onto `origin/main` at `44387379` (including
Claude's Rules file-reader changes). The protected shared checkout and
Claude's worktree remain untouched.

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

The initial skill validation executed no pipeline handlers or databases.
The subsequent source/feed acceptance below executes only disposable local
databases, fixture approvals and bounded artifacts. The shared dirty checkout
is unchanged.

## Source/feed modes and acceptance (2026-09-27)

User additions: require `plan`, `validate`, `deploy`, and source/feed inputs;
test existing sources and feeds. The skill now prepares a pinned plan, tests
the same scope in isolation, and deploys only the supported validated scope
through the existing Rules lifecycle/runner. `DEPLOY.md` holds its conditional
details, and recovery verifies the retained source/feed membership.

The read-only `scripts/resolve_feed.py` reads the strict Rules file format and
returns exact document/dataset/member identities and the Rules body digest.
It accepts native members, dataset codes and declared families without a
source-name switch or per-source callbacks. Feed is a skill input; the
warehouse runner has no `--feed` flag. Frozen worklist keys retain the binding.
Source/provider ambiguity, missing arguments and cross-source feeds fail.
An unseen fixture source resolves through configuration alone.

`tests/integration/test_bookkeeping_source_feeds_postgres.py` exercises these
existing pairs against their unchanged source documents:

| Source | Feed | Dataset | Result |
| --- | --- | --- | --- |
| sec.submissions.company | submissions | sec.submissions.company.v1 | passed |
| gleif | level1 | gleif.level1.v1 | passed |
| gleif | relationships | gleif.relationships.v1 | passed |
| gleif | reporting_exceptions | gleif.reporting_exceptions.v1 | passed |

Each pair uses two artifact work items with one fixture record each. SEC and
level1 derive from the repository's native Company fixture; relationships
and reporting exceptions use bounded synthetic native archive records.
GLEIF archive hashes, metadata and counts are inspected before submission.
Actual sandbox Rules save/proof/approval/activation register existing MDM
contracts, and the real `rules run` CLI executes the capture target using
restricted PostgreSQL 16 roles. A limit of one returns waiting/exit 3 with
one verified item, so it cannot be mistaken for completion.

The second artifact commits before its control acknowledgement is lost.
After lease expiry, the real CLI resumes the frozen run with copy execution
disabled: reconciliation succeeds without rewriting the output. Both receipts
verify, expected/verified work is 2/2, required checks pass, pending journal
delivery is zero, and repeated delivery adds no work. Each test emits a pinned
plan and validation artifact with exact hashes/run/receipt references into
pytest's temporary directory. Databases are stopped after testing; those
fixture artifacts are test evidence, not retained deployment inputs.

Final checks:

- Source/feed resolver tests: 16 passed (including actual helper CLI failures).
- Native Company and GLEIF source suites: 69 passed.
- New existing-source PostgreSQL capture/recovery acceptance: 4 passed, no skips.
- Mandatory configured Bookkeeping PostgreSQL acceptance: 42 passed, no skips.
- Skill Creator validation and `git diff --check`: passed.

Reproduce with `uv run --extra mdm --extra s3 pytest` and the paths
`tests/unit/test_bookkeeping_skill_feeds.py`,
`tests/mdm/test_clean_company_source.py`,
`tests/mdm/test_clean_gleif_source.py`,
`tests/integration/test_bookkeeping_source_feeds_postgres.py`, and
`tests/integration/test_configured_bookkeeping_postgres.py`.
Local commands reused the existing stage-work venv with
`UV_PROJECT_ENVIRONMENT` and `uv run --no-sync`; the implementation code is
unchanged between these worktrees. Docker/PG16 prerequisites are mandatory.

GoF review of the existing shared registry, Rules reader and two-commit test
history found no evidence supporting a runtime refactor. New variation stays
in descriptors and test data. This acceptance qualifies artifact capture and
recovery only; native parsers were tested separately, not invoked as Bookkeeping
capabilities. No provider network request, live Rules approval, AWS activation,
production publication or cutover occurred.

Next implementation frontier remains source-owned bounded SEC worklists and
actual capture/parse/silver capabilities, followed by legacy entry-point
migration and PostgreSQL recovery qualification. The skill documents these
gaps instead of claiming they have already been implemented.
