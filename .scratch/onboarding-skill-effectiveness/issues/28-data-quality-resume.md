# data-quality: Make progress resumable

Type: task
Status: resolved
Priority: P0
Blocked by: 04, 10, 16, 27
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-quality](../../../skills/data-quality/SKILL.md)
Step: 4 of 6
Skill dependencies: data-profiling, data-modeling
Applicability: Every source with field constraints, defects or downstream quality obligations.

## Question

What evidence allows another session to resume this phase without repeating completed work or trusting stale results?

## Scope and evidence

Use the existing onboarding log or task record as the common progress record, not a new independent state store per skill. Record check definitions and versions, measured corpus, disposition decisions and unresolved defects. Define when unchanged evidence is reused, invalidated or blocked; retain unfinished work explicitly.

A handoff must identify the next owning skill: data-onboarding or refining-rules; data-catalog owns the checks' business meaning.

Start from skills/data-quality/SKILL.md: plan, measure, decide, write, Publish quality meaning to the business catalog. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make progress resumable](./04-data-platform-resume.md); [data-profiling: Make progress resumable](./10-data-profiling-resume.md); [data-modeling: Make progress resumable](./16-data-modeling-resume.md); [data-quality: Make the entrypoint executable](./27-data-quality-entrypoint.md)

Priority rationale: Measured checks and dispositions prevent unsafe mappings.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Specify reuse, invalidation and blocker conditions in [Resume Data Quality](../../../skills/data-quality/RESUME.md), including versions, measured corpus, dispositions and unresolved defects. (2026-11-25 08:04 ET)
- [x] Resume after a staged interruption. A fresh process read the shared source log and both retained definitions, then selected **Measure the retained TestGen suite** without reimporting. (2026-11-25 08:04 ET)
- [x] Resume after measurement. Matching hashes selected **Review dispositions and hand off** with no rerun. A changed corpus hash selected measurement; a changed draft hash selected drafting/import before any stale result could be used. (2026-11-25 08:04 ET)
- [x] Add two [native TestGen draft rules](../evidence/quality-resume-testgen/testgen-rules.json); TestGen preview added nothing, strict import created two, and the suite counted one planted defect per check. No live rule or activation changed. (2026-11-25 08:04 ET)
- [x] Publish the skill and proof in [docs(quality): resume draft rules authored with TestGen](https://github.com/paulananth/edgartools-platform/pull/2134). Documentation genericity, guide paths and skill guards: **164 passed**. (2026-11-25 08:05 ET)
- [x] Learning → skill: [Resume Data Quality](../../../skills/data-quality/RESUME.md#add-draft-rules-with-testgen) fingerprints the sorted definitions rather than the timestamped export envelope and resumes from the first unfinished step. (2026-11-25 08:04 ET)

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

## Answer

Data Quality uses the existing source log for the versioned check definitions,
mapped corpus, measurements, disposition evidence and next action. It reuses
verified steps only while their evidence matches and leaves missing, stale or
unapproved evidence visible. The configuration owner remains Data Onboarding
for new feeds or Refining Rules for live feeds; Data Catalog owns business meaning.

The operator requested actual TestGen draft authoring. The import document adds
two built-in rules against an invented table: `Required` for a non-null label
and `LOV_Match` for a declared set of permitted states. It uses stable manual
rule IDs and zero tolerated failures. TestGen excludes null and empty state
values from the allowed-list test; the label check counts nulls, not blanks.
The platform's native enforcement and activation are separate.

### Proof

- Ran DataKitchen TestGen **5.134.0** against disposable local PostgreSQL 16.
  The five-row fixture contained one null label and one out-of-list state,
  as well as allowed, null-state and blank-state controls. The importer previewed
  two creations without writing definitions, then strict import created both.
- Stopped with the existing-format `## Resume` log pointing at the suite,
  the draft and readback hashes, and the measured corpus hash. A fresh process
  picked measurement through the existing source route and ran the real TestGen
  suite. TestGen recorded **one** missing label and **one** invalid state; each
  deliberately planted defect failed its zero-tolerance rule.
- A third process read the persisted result and selected disposition/handoff
  with unchanged evidence. Substituting a different corpus hash reopened
  measurement; a different draft hash reopened draft/import. These branches
  check resume routing, not additional TestGen executions.
- The disposable proof called TestGen's native import/export service and
  execution runner directly. No HTTP authentication, scheduled monitoring,
  live feed, catalog publication, or production runtime change was exercised.
