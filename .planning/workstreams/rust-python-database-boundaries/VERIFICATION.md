# Boundary planning closeout verification

Source baseline: main `82f4e5ce`, inspected 2026-10-14. Scope: architecture
planning and documentation corrections. No application, Rust, SQL migration,
Rules configuration, package dependency or deployment file is changed.

## Synchronization

- Original planning commit: `9d3dfeba`, originally based on `51b45916`.
- Rebased planning/intake commits: `85cd806e` / `dc1195a9`.
- A clean rebase and `git range-diff 51b45916..beb6e2cd 82f4e5ce..dc1195a9`
  confirmed both commits preserved their patches. A second fetch confirmed the
  branch was zero behind current main at that point.
- The original head remains recoverable in the verified private cleanup bundle.
  The shared checkout, other runtime worktrees and active-workstream pointer
  are preserved.

## Source and architecture review

- Read the current Python facade and Rust combination, reduction, replay,
  ranking and JSONB preparation entry points and their Python callers.
- Checked migration018's contract3 `payload_text` override and the Python
  early return of those bytes. Native preparation covers contract2; contract3
  SQL materialization remains a separately qualified placement candidate.
- Checked current MergeStage/scope and migration020: the shared transaction lock,
  assessed-effects checks and explicit drop of `match_proposal_snapshot` replace
  the old snapshot account. The canonical map now names `scope.identities` and
  `scope.links` rather than the removed `load_closure` reader.
- Checked migration019 and current input batching/read-back definitions. Removing
  Merge Stage size refusals does not remove unrelated input/Bookkeeping contracts.
- Read existing reduction/merge/join/publication results as historical evidence,
  without treating them as new qualification or deployment evidence.
- Applied the available GoF review to actual facade/caller/Store history:
  PR911/920/921/925 extend current seams; PR960/963 revise MDM scope/transactions.
  No new pattern hierarchy or runtime refactor is justified for this ticket.
- Existing platform skill guidance assigns the generic core to Rust,
  custom code/callers to Python, and storage/atomic enforcement to databases.
  A separate skill PR clarifies current contract2/contract3 publication placement;
  it adds no new capability, command, approval flow or activation instruction.
  That correction is published as [PR979](https://github.com/paulananth/edgartools-platform/pull/979),
  with24 platform command examples resolving and one focused role test passing.

## Fresh checks

Documentation/source validation resolves all91 local Markdown links in the plan
and canonical map, checks six facade entry points and nine named Python callers,
and confirms the latest migration/lock/effects statements against current source.
It also refuses any non-Markdown changed path.

```sh
uv run --no-sync --with pytest-testmon pytest -q --testmon \
  tests/unit/test_role_skills.py \
  tests/architecture/test_engine_boundary.py
```

Result: **2 passed in 4.32s**, using a prepared project environment and a separate
local testmon cache. These tests check skill-command resolution and facade import
boundaries; they do not exercise or requalify existing native kernels.

`git diff --check` passed. Ownership checks include the canonical map before
editing it and the normal overlap guard before commits and pushes. Final PR
publication and checklist evidence is recorded in TICKET.md.

No new full-path benchmark, PostgreSQL acceptance, provider request, AWS operation,
merge or activation was performed by this closeout. Those actions belong to
separately scoped execution work with its own evidence and approvals.
