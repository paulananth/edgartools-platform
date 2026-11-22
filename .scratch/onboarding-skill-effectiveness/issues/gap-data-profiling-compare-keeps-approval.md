# Capability gap: compare can replace approved findings

Type: task
Status: open
Priority: P0
Blocked by: none
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-profiling](../../../skills/data-profiling/SKILL.md)

## Question

How does `profile_data.py compare` preserve the approved findings it compares against, whatever `--out` is supplied?

## Evidence

Ticket 11's approved changed-delivery scenario requires the approved findings to remain unchanged. A prior exploratory probe on invented inputs ran `run`, approved the findings, then ran `compare` for a changed delivery with `--out` set to the approved folder. `compare` returned 0 and wrote `drift.yaml`, but also rewrote `findings.yaml` as a draft and rewrote `REPORT.md`, `fingerprints.json` and `invalid_rows.jsonl`.

`run` refuses to overwrite approved findings; `compare` does not. The skill's documented compare example uses an output folder, but the current command does not protect an approved baseline when the caller points `--out` there. This ticket records the gap; it does not change profiler runtime code.

## Required behavior

- `compare` refuses before writing anything when `--out` holds approved findings, including the folder containing `--approved`.
- The skill names a separate output folder from the approved baseline.
- A test on invented inputs verifies refusal and that approved `findings.yaml` retains its sha256.

## Ticket 11 linkage

[Ticket 11](./11-data-profiling-generic-verification.md) remains incomplete until this capability is fixed and verified.
