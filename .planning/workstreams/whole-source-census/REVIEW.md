# Ordered name projection review — 2026-10-08 18:14 ET

## Spec

Independent reviewer found no scoped projection blocker and reran the two
projection/census test files: 97 passed in 18.24s. Category/LEI/key/wanted
registration/other-name read order and typed normalization are preserved.
The synthetic reduction test expresses intended last-timestamp and holder
subtraction semantics in test Python; it does not prove an implemented generic
reducer. Deliberate faults are synthetic. Captured prefix rows prove parity,
not captured fault qualification or original archive EOF. Whole-source,
cascade, installed population and active caller replacement remain open.

## Standards and GoF

Initial review found prohibited YAML anchors hidden by yaml.safe_load in tests.
Fixed recipe serialization with files.dumps, test loading with files.load,
and canonical-transform equality coverage. Final review found the imported
qualification helper absent from runtime pins. Added the helper module and
reran the captured report successfully with unchanged before/after pins.
No remaining scoped blocker from static review; reviewer did not rerun the
full native/affected suites. Parent ran 146 native and 134 affected Python
checks successfully. Preserve interpreter/functions; no GoF hierarchy warranted.

## Ownership gate

Before commit/push, the mandatory overlap guard found Claude worktree
`edgartools-platform-claude-skills-generic-2`, branch
`claude/skills-generic-bookkeeping`, also changing
`skills/data-platform/READING.md`. Operator ownership question is pending.
No commit/push of this checkpoint has occurred. Existing 13cd3d23 remains
the pushed head. The isolated Codex edits and evidence remain protected.

## Lookup integration review — 2026-10-08 18:27 ET

Both reviewers found no scoped blocker. Spec independently ran 94 lookup,
stream and combination checks in 3.21s. Parent gate: 207 affected checks pass
in 41.99s; native grammar unchanged since the 146-test gate. Standards identified
control_contract.py and bookkeeping/clean/config.py missing from the worker's
runtime pins; added both and reran successful captured worker qualification.
The captured report records worker receipt hashes, 1,000 records, table counts,
unchanged retry and replay verification, with separate-process/full-source/
cascade/installed/full-goal flags false. Publication_count and wanted values
still require independently proven complete upstream derivation.

The old overlap observation was taken against stale references across two
repositories. #876 is now merged and its Claude worktree is clean. The temporary
cross-repository guard wrapper now imports foreign refs read-only into the owned
bare repository, prevalidates all compared commits, and compares against the
same freshly fetched main commit. Do not accept a guard's empty overlap list
when Git comparison errors occur; process substitutions can hide those errors.
Final guard result must be captured before any commit/push.
