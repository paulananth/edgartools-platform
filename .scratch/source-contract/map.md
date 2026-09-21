# Source Contract

Label: `wayfinder:map`

## Destination

A **specification of the Source Contract**: one versioned file per source
that declares, from its Bronze Artifacts onward, how they are read, the
silver table they produce, the Dataset Contract that maps them into MDM,
and the test cases and batch gate that prove it. The spec is proven on
GLEIF and Form 3/4/5 with a throwaway local runner, and handed over only
when the acceptance checks below can be met. Planning only: no real engine,
no edit to any Clean MDM file.

## Notes

- **Operator's idea (2026-09-21):** "1) need to build pipeline using
  configuration input file 2) how it interacts with mdm and what fields need
  to be pulled ie a mapping document 3) transform and parsing configurable".
  Refined: "getting data to bronze must be decoupled … focus is how easy is
  to bring new data in and master and test just using configuration input
  file".
- **Vocabulary** (`CONTEXT.md`): **Source Contract** (the file),
  **Dataset Contract** (its MDM section, Clean MDM's own concept, unchanged),
  **Mapping Document** (generated from the contract, never hand-written).
  Avoid "source config", "pipeline config", "adapter config".
- **File shape** (Q9):
  `source` · `read` (Bronze Artifact → rows) · `silver` (declared table) ·
  `dataset` (Dataset Contract, `adapter` block included) · `tests`.
- **The MDM side already exists**: Clean MDM's `normalize`
  (`edgar_warehouse/mdm/clean/adapters.py:49-158`) turns one row into one
  assertion from an `adapter` block. One live instance, a Python dict:
  `edgar_warehouse/mdm/clean/company_source.py:32-61`. No document specifies
  it (`docs/specs/mdm/policy-language.md` §15 Open 2). Sameness and
  survivorship stay in the **Mastering Policy**
  ([mastering-policy-language map](../mastering-policy-language/map.md)).
- **Acceptance checks** (Q5, Q6) — the destination is not reached until the
  spec makes each one checkable:
  1. Adding a source changes only files in that source's own folder
     (contract, fixtures, optional custom code). No engine or other-source
     file changes.
  2. Deleting a source's folder breaks nothing else.
  3. An architecture test fails if engine code names any source.
  4. The runner reads local Bronze Artifacts only and refuses network access.
  5. Cold-onboarding trial: a fresh agent, given only the spec and one
     example, onboards an unseen source without reading engine code or
     asking a question.
  6. The Mapping Document is generated from the contract.
  7. Every term a contract uses is in `CONTEXT.md`.
  8. One command checks a source end to end locally: validate → parse tests
     → mapping tests → mastering tests → batch gate.
  9. A config error names the line and rule; a failed test shows expected
     against actual.
  10. GLEIF's contract fits in about 100 lines, tests included, and one
      session onboards it.
  11. The Mapping Document shows how much of each source is custom.
- Skills: `/grilling` (operator preference: **one question at a time**,
  with a recommendation), `/domain-modeling`, `/research` (primary sources,
  `path:line`), `/wait-what` (ASD-STE100 re-pitch).
- Standing rules: never commit to `main`; one worktree per topic; Codex/Grok
  files (`edgar_warehouse/mdm/clean/`, `docs/specs/clean-mdm/`,
  `.scratch/clean-mdm/`) are read-only — gaps go as proposals under
  `.scratch/handover/`; zero SEC requests (bronze only); Snowflake will not
  be restored; nothing is deployed until written and tested locally.

## Decisions so far

- Destination (Q1): **(a)** — a spec for a per-source contract covering
  parse/transform, silver and MDM mapping; not a mapping inventory alone,
  not orchestration, not a retrofit.
- Scope start (operator, 2026-09-21): **the contract starts at an existing
  Bronze Artifact**; getting data into bronze is decoupled and out of scope.
- Proof sources (Q2, operator reframed toward ease of onboarding):
  **GLEIF** (flat, outside source, Company, identifier contract) and
  **Form 3/4/5** (nested XML, cross-source lookup, Person and Company).
- Testing (Q3): every contract declares **parse, mapping and mastering test
  cases** with committed fixtures, plus a **batch gate on real bronze** that
  must pass before go-live; one generic runner, no source-specific test code.
- Acceptance checks (Q5, amended Q6): the eleven checks in Notes.
- Parsing escape hatch (Q4, Q6): **configurable first, custom allowed per
  source**. A custom step or check lives in the source's folder, is declared
  in the contract, is marked in the Mapping Document, is tested by the same
  cases, takes rows/artifacts and returns rows only (no fetch, write or MDM
  call), and is versioned. Promotion to a shared primitive is optional.
- Silver (Q7): **the contract declares the silver table** (columns, types,
  key, collapse); schema and collapse are generated from it. Local runs write
  Parquet.
- MDM mapping (Q8): **reuse Clean MDM's `adapter` block unchanged** as the
  Dataset Contract's mapping; gaps go to Codex as proposals. This answers
  the policy language spec's open field-alias map.
- Names (Q9): **Source Contract**, **Dataset Contract**, **Mapping
  Document**, added to `CONTEXT.md`.
- Scope (Q11): the three exclusions below stay out; how a contract is
  registered and run by one generic stage becomes a ticket.
- [Inventory what Form 3/4/5 and GLEIF parsing needs](issues/02-inventory-what-form-345-and-gleif-parsing-needs.md)
  — **16 primitives plus one custom step cover both**: Form 3/4/5 is 57/58
  columns generic (custom: `owner_display_name`, 1.7%) given a generic
  `lookup`; GLEIF 0% custom but needs a streaming zipped-JSON reader that
  handles object-or-list fields. The C-J lookup reads the newest snapshot,
  not the as-of one — a replay risk.
  [research/02](research/02-parse-needs-inventory.md).

## Not yet specified

- **Change and replay**: when a Source Contract's version changes, which
  silver rows are re-parsed, which assertions are re-published, and how
  that meets the Merge Stage's bounded rebuild. Sharper after research 02:
  a `lookup` that reads the newest snapshot makes a re-parse depend on when
  it runs; the contract may need as-of lookups.
- **Moving an old parser**: the prototype shows whether Form 3/4/5 *can* be
  expressed; the criteria for when an existing parser *should* move are for
  after the prototype.

## Out of scope

- Getting data into bronze (fetch, schedule, SEC access) — decoupled by
  operator decision; see the decoupled-bronze-pipeline map.
- Where silver is stored after Snowflake — affects every source, not only
  contract-driven ones; a separate effort.
- Step Functions generated from config — most orchestration sits before the
  Bronze Artifact; the one piece inside scope (a generic run stage) is a
  ticket.
- Retrofitting the existing parsers — a migration, not a design.
- Edits to Clean MDM files — proposals via `.scratch/handover/` only.
- The real engine's implementation.
