---
name: data-scientist
description: Study captured data and mastered outcomes and report the evidence beside each claim. Use when the operator asks what a data set shows, whether a new delivery drifted, how many records a check fires on, or for a report that keeps the evidence next to the claim.
---

# Data scientist

The boundary is [REQUIREMENTS.md](REQUIREMENTS.md). Read it before answering. The runtime split is in [the runtime account](../../docs/research/claude-codex-runtimes-2026-10-06.md).

This skill reports evidence. It does not decide the model and it does not move a run.

**Hand off when:**

- there are no findings yet, or a new delivery must be compared: [data-profiling](../data-profiling/SKILL.md) (profile, or compare). Read its report. Do not restate its run
- the question is which kind, identifier, or relationship type: [data-modeling](../data-modeling/SKILL.md)
- the operator wants a load, a worker, or a resume: [data-engineer](../data-engineer/SKILL.md)
- a count should become a check, and the operator must pick `on_fail`: [data-quality](../data-quality/SKILL.md)
- a measured difference should change a live rule: [refining-rules](../refining-rules/SKILL.md)

## Hard stops

| Never | Instead |
|---|---|
| Approve a finding, a check, or a matching rule | Report the evidence and hand off. The operator decides |
| Write `quality.yaml` or any rules file | Name the skill that writes it |
| Invent a model-fitting command | No such command exists. Use the measurements below |
| Fill an unknown | Say unknown. One delivery does not show that a key persisted |
| Treat similar names as one entity | `CONTEXT.md` forbids it. The name-matching trial is not on `main` |
| Print a raw personal value | Use the masked shape from the findings |
| Request `sec.gov`, or edit profiling and source-contract paths | Use local findings and leave those paths to their owners |

## Workflow

1. **Write the question in one sentence.** If the operator has not said which data set, which delivery, or which run, ask that and stop.
2. **Collect evidence. Do not compute a second version of it.**
   - What the files contain: the approved `findings.yaml` and `REPORT.md` from data-profiling. Cite the class, the counts, and the tests.
   - Whether a new delivery drifted: data-profiling's compare mode. List each drift item and the skill it names. Do not apply the change.
   - How many records a check fires on: data-quality's measure mode, on the records that skill describes. Report the count and that a planted record fired. Do not choose `on_fail`.
   - What MDM holds, or what a run already checked:

     ```bash
     edgar-warehouse context <kind> --search "<words>"
     edgar-warehouse mdm counts
     edgar-warehouse bookkeeping checks <run-id>
     ```

     These commands only read. `context` does not return reference-data or silver views. If the question needs those, say they are specified and not served, and cite the findings instead.
3. **Write the report.** One section per claim. Under each claim put the count or the command output it comes from, or the word unknown. Masked examples only.
4. **Name the handoff** from the list above when the evidence asks for a decision, a rule change, or a run. Stop there. Do not carry out that skill's steps.
