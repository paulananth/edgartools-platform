---
name: data-modeling
description: Decide where one profiled part sits in MDM, reference data, or silver. Its class, its kind or code set, which identifiers may join, and the relationship type. Use when the operator asks what a data set's parts are in the model, which kind a column belongs to, whether an identifier may join records, or how a relationship should be named.
---

# Data modeling

The boundary is [REQUIREMENTS.md](REQUIREMENTS.md). Read it before deciding. History of the two runtimes is in `docs/research/claude-codex-runtimes-2026-10-06.md`.

This skill decides structure. It does not measure the files and it does not write a contract.

**Hand off when:**

- there are no approved findings (`approval.status: approved` in `findings.yaml`): [data-profiling](../data-profiling/SKILL.md)
- the structure is accepted and the feed is new: [data-onboarding](../data-onboarding/SKILL.md)
- a live feed's mapping or matching should change: [refining-rules](../refining-rules/SKILL.md)
- a defect needs a check: [data-quality](../data-quality/SKILL.md)

## Hard stops

| Never | Instead |
|---|---|
| Approve findings, or write down words the operator did not say | Ask one question, then wait |
| Guess a class, a key, or a link | Leave it unknown and name the failing tests from the findings |
| Add a kind, or treat a profile as a kind | The kinds are `KINDS` in `edgar_warehouse/mdm/clean/evidence.py`. A missing kind is an operator ruling |
| Join on a cross-reference, or merge on similar names | Only `cik` and `lei` join. Say so, and stop |
| Write `source.yaml`, `quality.yaml`, or a `read:` contract | Hand off to the skill that owns that file |
| Request anything from `sec.gov` | Use the captured files and this repo |

## Workflow

1. **Name the part.** If the operator has not said which part, ask that and stop.
2. **Read the approved findings** for that part: `class`, `record_key`, `identifiers`, `relationships`, `hierarchies`, and `silver`. If the findings are missing or not approved, hand off to data-profiling. Do not profile the files here.
3. **Read the language that already exists.** `CONTEXT.md` for identities and profiles. `rules/merge/relationships.yaml` for relationship types. `docs/specs/rdm/spec.md` for a code set, remembering it is still a draft. Do not invent a type or a kind name.
4. **Look up what MDM already holds,** and only for that question:

   ```bash
   edgar-warehouse context <kind> --search "<words>"
   edgar-warehouse mdm counts
   ```

   `context` answers a name or an identifier that is already mastered. `mdm counts` answers how many entities exist. Neither command returns `rdm.code_context` or `silver.table_context`. Read those from the specs and the findings.
5. **Write the decision in plain words.** Class. Kind, code set, or silver table. Which identifiers are identity and which are cross-references. For a relationship: type, the kinds at the ends, role, and scope. Mark every unknown.
6. **Ask at most one question** when the choice belongs to the operator: a new kind, a type the policy does not name, or which of two fields is the identity. Give the recommendation. Do not continue in the same turn.
7. **Hand off** using the list above. Do not restate that skill's steps.
