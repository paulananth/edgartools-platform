# Demonstrated skill gaps

Status: onboarding guidance applied with operator authorization; profiling-code fixes proposed; findings unapproved.

1. **Raw XLSX support.** The documented profiling command failed on the receipt-pinned DTC workbook with `ValueError: ... found ['xlsx']`. CSV/JSON exports are supported, but their lineage and region decisions need explicit disclosure. Production workbook reading is unqualified.
2. **Dataset label is overwritten.** A run supplied `--name 'DTCC public directories September–October 2026'`; findings returned `dataset.name: null`, and REPORT.md starts `Profiling report: None`. `profile_inputs` in `skills/data-profiling/scripts/profiling/run.py` assigns `name = None` inside key discovery, overwriting the function's dataset-name parameter. Rename that local and add a regression where a part needs designed-key evaluation. This is on Claude's owned paths; no code changed here.
3. **Report furniture versus data.** Blank rows, numeric-series headings, and a guide worksheet survive the export and legitimately make several all-region key tests fail. Keep original-grid audit and declared row selections; do not silently accept a surrogate key or discard rows to force a class.
4. **Shape is not domain authority.** The run proposes a six-row CCIT member list as reference data and several MPID tables as new master kinds. These are draft algorithm outputs, not approved semantic classifications. The meaning of an account, executing broker, clearing broker and market worksheet needs review before mapping to Company or relationships.

The generic discovery guidance is applied in
[data-onboarding](../../../skills/data-onboarding/SKILL.md#discover-profile-the-whole-data-set-first).
The overlap guard exited 1 because three Claude worktrees hold changes to
`skills/data-onboarding/SKILL.md`. The operator authorized Codex to coordinate
this edit: "Authorize Codex to coordinate this skill edit". All three foreign
diffs change only the identifier example near line 571; the Codex addition is
in discover near line 156. The changes are disjoint. The thirteen-line generic
guidance was applied only in the Codex worktree; foreign hunks were untouched.
Profiling code and Claude worktrees were untouched.

## Design review

Read gof-refactor-reviewer, source input dispatch and its history. It was added
in d4f7fe36; no evidence justifies a hierarchy refactor for this investigation.
The generic region exporter is a plain audit function. GoF pattern-selector's
no-pattern verdict applies: selections are data, and runtime loading remains
separate. No DTCC-specific platform loader was added.
