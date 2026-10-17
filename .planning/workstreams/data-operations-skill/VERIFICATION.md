# Data operations skill verification

Documentation and packaging evidence; no source run or shared-store mutation.

## Structural and packaging checks

- Skill Creator quick validation passed; SKILL.md is 80 lines with discoverable name/description and generated agent metadata.
- Actual data-skill wheel built offline. Its SKILL.md, RUNBOOK.md and agent metadata equal the authored files byte for byte.
- Extracted wheel skill links and named commands resolve against the current CLI.
- Existing installer copied the new skill to isolated temporary Codex/shared and Claude skill homes; all sibling references and commands resolve there. Global skill folders were not changed.
- Affected existing tests: 17 passed, 9 unchanged deselected by testmon, 2.50 seconds. Files: `test_role_skills.py`, `test_rules_skill_commands.py`, `test_bookkeeping_skill_feeds.py`.
- Whitespace check passed. No tests were added just to mirror documentation wording.

## Independent forward exercise

An independent agent was given only the skill/runbook and invented operational
artifacts. It produced a dry-run action report; no live operation was attempted.
Full report is retained at `/tmp/data-operations-forward-eval.md` for this session.

| Supplied case | Observed decision |
| --- | --- |
| Alpha delivery 97 of 100 receipts, producer still running; beta independent | Alpha waits with three outstanding; independent beta can proceed when its own prerequisites hold. |
| Beta: 20 files; one new key with old bytes, one changed file, 18 unchanged receipts | Provisional two selected and 18 already processed, conditional on unchanged processing identity. Suspected rename is not skipped solely by hash. |
| Gamma: verified work, three unacknowledged events, frozen V1; live V2 | Preserve V1 and recover the same producer events. No duplicate merge or premature completion. |
| Another worker has a live lease | Preserve the lease and account for resource use; expiry alone grants no authority. |
| Container: 3 GiB usable, 2 GiB per worker/verifier pair; six spare connections, four per pair; configured maximum two pairs | Evidenced upper bound one pair; actual dispatch still requires sufficient CPU/disk evidence. Host's 16 cores do not override container allocation. |
| Requested five-minute monitoring | Deadline and exits for completion, no actionable progress, cancellation and expiry; no hidden resident watcher. |

This is behavioral evidence for the instructions, not runtime qualification of
delivery readiness, renames, resource collection or scheduler automation.

## Standards

Independent review: no actionable findings. Existing command registration,
portable packaging, public/private evidence and ownership boundaries checked.

## Spec

Independent review: no actionable findings. Ongoing management, capacity,
readiness, file changes, runbooks, Bookkeeping/Journal and research covered.

## GoF

The GoF skill was available and applied independently: leave the design as
written, no findings. No scheduler, resource-lease store or duplicate control
authority is introduced; runtime code is unchanged.

## PR preparation and promotion follow-up

Rebased onto main `8d9772ae`; added configuration promotion and skill-location
guidance. The final named test files were rerun with testmon selection disabled:
26 passed in 5.38 seconds. Skill validation, a rebuilt actual wheel and isolated
installation into both agent homes all passed with the final documentation.
No global skill replacement occurred. Final Standards, Spec and GoF reviews
each reported no actionable findings.

An independent promotion scenario supplied a draft destination source with
matching retained proof/approval, a mismatched saved merge policy, and missing
delivery-completion/runtime support. The response reused exact matching
qualification instead of rerunning everything, kept different merge versions
distinct, checked source binding changes, and held unsupported source activation
and loading. It identified Git authoring files, destination Rules authority and
the package-distributed skill correctly. This is instruction evidence, not an
automated release importer or source qualification.
