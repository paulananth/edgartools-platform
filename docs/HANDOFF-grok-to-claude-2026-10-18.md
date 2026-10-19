# Handoff: Grok → Claude — one-source install and test — 2026-10-18

**From:** Grok, worktree `/Users/aneenaananth/projects/edgartools-platform-grok-test-servers`, branch `grok/test-servers-20261018`.
**Ask:** review the skill text in the draft pull request. Do not commit on this branch. Do not approve or switch on a Rules version. Do not clear the shared test instance. Do not write application code unless the operator asks.

## What is committed

Skill prose only. No application code.

- `skills/data-operations/SKILL.md` — **Install and enable one source**. One Rules source, the target from `rules/source-sequence.yaml`, save that source alone, record a proof, then the existing approval steps. `after` does not pull the next source into the run.
- `skills/data-operations/RUNBOOK.md` — **Test and clear a source run**. The test uses the test instance. Clear-out is only after that run finishes, or when the operator abandons it, and only when no other run holds a live lease.
- `skills/data-platform/SKILL.md` — points at that install section.

Checked 2026-10-18 21:02 ET, before the commit: `rules sequence check --source sec.submissions.company` exited 0, status `configured`, target `mastering`, runtime readiness not checked. `bundle.unresolved` reported no unknown commands. `scripts/dev/overlap_guard.sh` exited 0.

## Company was not enabled

`sec.submissions.company` was the source the operator asked to test first. It is installed on the shared test PostgreSQL Rules database as draft `company-person-2026-10-17.test-initialization`. That draft matches the company document on this branch, including its quality file (digest `3ec15961ae5c…`). It has no proof and no approval.

The platform merge draft of the same label does not match the policy file in the repo (17 added or changed places, including automatic matching rules and identifier verification stamps).

`rules run --source sec.submissions.company --feed submissions --target mastering` was refused: no active proved Rules version. Bookkeeping had 0 runs and 0 leases. MDM had 0 staged records and 0 current records. Nothing was approved, switched on, or cleared.

## The bounded proving run stopped

2026-10-18 21:12 ET. `rules test` on disposable store `company-proof-20261018`, five already captured company documents, exited 1. Company reading is several tables (`company`, `filings`, `addresses`, `places`). That command accepts only a reading that keeps each captured document whole in one column. It stopped before either mastering pass. The disposable store was stopped; its data is still there. That run is not a proof and was not recorded with `rules record-proof`.

The company manifest writer that already exists is `mdm prepare-clean-company`. A wired `rules run` still needs an active proved version. The operator said not to write code for this.

## Leave these alone

- Shared test containers `edgartools-test-postgres`, `edgartools-test-mysql`, and `edgartools-test-sqlserver`. Another agent may be using them. Private connection files are under `~/.local/share/edgartools/test-instances/`. Do not print them.
- `~/.local/share/edgartools/local-tests/postgres.env` does not match the test PostgreSQL password. Use the test-instance connection file.
- The primary checkout `/Users/aneenaananth/projects/edgartools-platform` is dirty on local `main`. Do not commit or reset it.
- Do not start `gleif` until this company run is complete.
- Do not request SEC.

## Next safe action

Wait for the operator. The skill text can be reviewed as written. A finished company test still needs a recorded proof and the operator's approval words before anyone switches the version on.
