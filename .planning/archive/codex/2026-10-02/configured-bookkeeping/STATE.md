# Configured Bookkeeping implementation

Owner: Codex. Branch: `codex/configured-bookkeeping`.
Worktree: `edgartools-platform-configured-bookkeeping`.
Base: refreshed `origin/main`, `1b219f54` (2026-09-26).
Rebased onto `a425efb0` after final upstream refresh; incoming changes were
Company-mastering documentation only.

Status: core and bounded MDM/publication integration implemented; the complete
all-pipeline replacement remains unfinished. Do not deploy this branch as a
replacement for every legacy caller.

The operator explicitly assigned Codex the required Rules schema, resolver and
runner changes during this task. Those files are in `edgar_warehouse/rules/`
and the existing source documents. Claude should reuse this single table and
resolver for its remaining Rules engine and skill work. No changes are made
in Claude's worktrees or planning directories.

## Current implementation

- Fresh PostgreSQL 16 `bookkeeping_clean`; five tables; checksummed migrations;
  restricted runtime functions; deterministic fenced leases and renewal;
  ordered checkpoints; atomic verified progress plus journal intent.
- Generic capability registry; immutable configuration/input references;
  lost-ack reconciliation and required verification before resume skips work.
- Separate guarded destination transactions, with expiry checked at commit.
- Rules `pipeline` document type in the same one-table lifecycle; immutable
  version bodies, proof/approval enforcement, frozen resolver exports, and
  idempotent MDM registration before Rules activation.
- Existing Merge Stage and publication fences bound as common capabilities;
  proof is outside the business payload/idempotency key.
- Common NDJSON normalization capability uses the exact frozen dataset reading;
  an unseen Company fixture needs configuration only. Assessment retention and
  supersession transactions also reject expired authority.
- CLI status/checks/leases/resume and bounded Rules source/pipeline submission.
- SEC and GLEIF capture/MDM control declarations; graph publication document.
- Local empty-store provisioning under NOLOGIN owners; owner-only 30-day
  compaction preserving summaries, checkpoints, references and tokens.

## GoF review

Used `gof-refactor-reviewer` before implementation, including its smells,
refactoring mechanics and consequences references. Read existing code and
git history for `bookkeeping/store.py` and `mdm/clean/store.py`.

Overall: keep existing business capabilities; replace the requested control
boundary with a small registry of functions. No State/Strategy class hierarchy.

1. `bookkeeping/store.py:483`, `:556`, `:682`, `:857` mix lease/run control with
   SEC-specific parse and checkpoint methods. History includes repeated
   additions and batching/lease repairs (`c54f75b5`, `7e7f7a90`, `000897a7`,
   `c0bb6534`, `0b8e368d`). Adding a source through that interface requires
   new methods and callers. The requested shared capability registry makes
   source selection declarative. Its cost is an explicit migration of existing
   callers; implementing the core alone does not eliminate that cost.
2. `mdm/clean/store.py` already centralizes atomic commits and consumer fence
   completion. Keep it. A narrow authority adapter can call a store-local
   guard inside those transactions while retaining existing request hashes.
   Its cost is one extra authorization call and requiring destination schema
   provisioning. No business rules or identity algorithm are redesigned.

## Verification

Commands/counts and their limits are recorded in
`docs/specs/configured-bookkeeping.md`. PostgreSQL prerequisites fail rather than skip.
Core acceptance uses an isolated disposable `postgres:16-alpine`; it also
exercises actual Merge Stage effects and offline publication verification.

Complete control suite: 35 passed with no skips, including the operator CLI
and exact-digest proof/approval rejection before root creation.
Contract/source/inventory suites: 168 passed. Existing Clean MDM PostgreSQL:
56 passed, then eight assessment tests passed again after the assessment guard.
The new local `bookkeeping_clean` and `rules` stores were rechecked empty.

## Remaining work from the supplied plan

See the final section of `docs/specs/configured-bookkeeping.md` for the full
list. In particular, legacy `BookkeepingStore` and Clean MDM `RunCoordinator`
callers have not all moved to the shared interface. SEC worklists, parsing,
silver and gold adapters, the Rules proof evaluator, hosted publication, and
complete SEC/GLEIF pipeline qualification remain necessary. The old database
has not been reset or retired. No AWS rollout has happened.
