# Handoff: Claude → Codex — branch closeout — 2026-07-29

**From:** Claude session on `claude/adv-fund-count-reconciliation`
**Repo:** `edgartools-platform` · `origin/main` @ `0c1aa09` (PR #299)
**Ask:** close out all existing branches except `codex/aws-cost-report`, which is Codex's own
active work and stays untouched (per `CLAUDE.md`'s hard rule: Claude and Codex never commit to
the same branch, and current Codex work is protected unless explicitly handed off — it has not
been).

Do **not** delete, rebase, force-push, or commit onto `codex/aws-cost-report`. Do **not** touch
its worktree at `/Users/aneenaananth/projects/edgartools-platform-aws-cost-report`.

---

## Branch inventory (as of 2026-07-29, after this handoff's own cleanup)

| Branch | State | Action taken by Claude | Action left for Codex/operator |
| --- | --- | --- | --- |
| `main` (local) | 2 commits behind `origin/main` | none | fast-forward when convenient (`git fetch && git merge --ff-only origin/main`) |
| `claude/fix-item-202-artifact-selection` | PR #299 merged into `main`; content confirmed byte-identical to `origin/main` (`git diff origin/main claude/fix-item-202-artifact-selection` empty) | **Deleted** — local `git branch -D`, remote was already auto-deleted by GitHub on merge | none — closed out |
| `claude/adv-fund-count-reconciliation` | Active this session. Two new commits not yet on `origin/main`: `c80608b` (Release Evidence Automation, ticket 09) and `7263aff` (wayfinder tickets 27-47 + map.md) | Committed all in-progress work; nothing left uncommitted except 3 files that are pre-existing no-op diffs (see below) | **Open a PR** for `c80608b` against `main` when ready — this is real shippable code (`edgar_warehouse/application/release_evidence.py` + CLI + 58 tests, all passing). `7263aff` is planning-only markdown (`.scratch/`), safe to include in the same PR or land separately. |
| `prototype/07-dashboard-acceptance` | Throwaway wayfinder prototype branch (commit `78013d8`), per the `/prototype` skill's own convention: captured as a decision record, never meant to be merged. Ticket 07 is already resolved on the release-readiness map, citing this branch as its evidence. | **Left as-is** (operator chose "leave as permanent reference") | none — this is intentionally a leaf branch, not something to close out |
| `codex/aws-cost-report` | Codex's own active branch/worktree. No commits yet ahead of `origin/main` (still at `49138b2`); has one **uncommitted, untracked** file in its worktree: `infra/scripts/report-aws-month-to-date-cost.sh`. | **Not touched** — protected per `CLAUDE.md` | Codex's own call — this handoff does not instruct Codex on its own in-progress work |

## Known no-op local diff (`claude/adv-fund-count-reconciliation`, not a blocker)

`git status` on this branch shows 3 files as locally modified:

- `edgar_warehouse/application/warehouse_orchestrator.py`
- `tests/unit/test_ownership_lookback.py`
- `tests/unit/test_submission_phase_order.py`

This is **not new uncommitted work** — local `main` is 2 commits behind `origin/main`, and these
files' working-tree content is already byte-identical to `origin/main` (`git diff origin/main --
<file>` is empty for all three; verified before writing this doc). They were part of an earlier
same-session fix that PR #299 later shipped independently. The diff will disappear on its own
once this branch is rebased/merged onto current `origin/main` — no action needed, and nothing
would be lost by ignoring it.

## Open PRs

None open as of this handoff (`gh pr list --state open` returned empty).

## What Codex should actually do

1. Nothing to `codex/aws-cost-report` is requested by this handoff — continue that work
   independently.
2. If Codex is the one closing out `claude/adv-fund-count-reconciliation`: open a PR for commits
   `c80608b`/`7263aff` against `main`, following this repo's normal PR flow (`gh pr create`).
   Neither commit touches anything Codex is working on (`infra/scripts/report-aws-month-to-date-cost.sh`
   / cost-reporting), so no conflict is expected.
3. No other branch needs closing out — `claude/fix-item-202-artifact-selection` is already
   deleted, and `prototype/07-dashboard-acceptance` is intentionally permanent.
