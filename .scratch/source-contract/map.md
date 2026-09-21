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
- **Where contracts live** (ticket 06): the **Rules Database** is the
  master; YAML is the authoring and export format; Clean MDM holds only
  active versions.
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
  1. Adding a source changes only that source's own versions in the Rules
     Database and its own folder (fixtures, optional custom code). No engine
     or other-source change.
  2. Deleting a source's folder breaks nothing else.
  3. An architecture test fails if engine code names any source.
  4. The runner reads local Bronze Artifacts only and refuses network access.
  5. Cold-onboarding trial: a fresh agent, given only the spec and one
     example, onboards an unseen source without reading engine code or
     asking a question.
  6. The Mapping Document is generated from the contract.
  7. Every term a contract uses is in `CONTEXT.md`.
  8. One command (`source prove`) checks a source end to end locally:
     validate → parse tests → mapping tests → mastering tests → batch gate.
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
- [Write the Mapping Language reference](issues/01-write-the-mapping-language-reference.md)
  — **the language now has a reference, and nothing enforces it**: every key
  specified with `path:line`; Clean MDM stores any contract body unchecked,
  and contract mistakes stop a batch instead of deferring a record. A
  dataset body is immutable per `source_code`, so a mapping change today
  means a new `source_code` and re-binding every record. Gaps (validation,
  `lei` format, formatted relationship targets, deferral instead of silent
  drops) go to Codex as proposals.
  [research/01](research/01-mapping-language-reference.md).
- [Can mastering test cases run on a laptop](issues/03-can-mastering-test-cases-run-locally.md)
  — **yes, against a local Postgres 16 container** (no SQLite path):
  seed identities through a first `MergeStage.apply()` batch; ~45-75 s for
  five cases. Mastering cases can assert declared binds, new identities,
  deferrals and surviving fields, **not engine-chosen bindings** — those
  wait for automatic rules to be activatable. The runner needs a ≥30 s
  readiness wait. [research/03](research/03-local-mastering-tests.md).
- [Research the path and expression syntax other engines use](issues/10-research-path-and-expression-syntax.md)
  — **restricted dotted paths over one canonical tree, `each:` blocks for
  repeating groups, one `primitive: {arguments}` mapping per column**:
  readable, schema-enforced, no logic in strings, same spelling as the
  `adapter` block; query and transform languages rejected. Strict YAML 1.2
  needs ruamel.yaml, not the declared PyYAML.
  [research/10](research/10-path-and-expression-syntax.md).
- [Decide the read and transform primitives and the custom-step signature](issues/04-decide-the-read-and-transform-primitives.md)
  — **strict YAML 1.2 → canonical JSON; dotted paths; `each:` groups; one
  primitive call or `steps:` chain per column; small primitives plus
  rule-bound named conventions; `lookup` as-of the filing date (else
  earliest after); two custom-step shapes (value step, table reader) that
  reject bad records and stop on bugs.** The Mastering Policy adopts the
  same authoring convention (handover item).
- [Decide how a Source Contract is registered and run](issues/06-decide-how-a-source-contract-is-registered-and-run.md)
  — **the Rules Database is the master store; Clean MDM is what production
  reads**: agents save validated immutable versions, prove them in a
  Proving Run, and activate by registering into `mdm_v2`; identity-changing
  versions need a Rule Activation Approval the agent explicitly asks for.
  One `source run` command serves every source; `source prove` shares its
  code. Lifecycle draft → proven → active → retired.
- [Decide the test-case and batch-gate format](issues/05-decide-the-test-case-and-batch-gate-format.md)
  — **named cases (parse / mapping / merge in one shape, seeds through the
  same contract, identities named by the case) plus an optional attributed
  snapshot; built-in and custom checks that report violations with row
  keys; a pinned batch gate with zero-by-default limits and a `why:` for
  each exception; `file:line`-first failures with exit codes and `--json`
  as the primary, agent-facing output.**
- [Prototype the GLEIF and Form 3/4/5 Source Contracts](issues/07-prototype-gleif-and-form-345-source-contracts.md)
  — **the language holds**: Form 3/4/5 reproduces `ownership.py` on 5,356 /
  5,356 artifacts (3.3% custom); GLEIF is 93 lines and 0% custom, and proves
  through a real Merge Stage case; checks 1-3, 6 and 8-11 exercised
  literally; check 4 holds only in part (libpq and DNS bypass a Python
  guard, so no-network must live below Python). Main finding for Codex: the adapter needs a kind per row, but
  C-J is a policy classification. [prototype/](prototype/README.md).
- [Write the Source Contract spec and the Codex handover](issues/08-write-the-source-contract-spec-and-codex-handover.md)
  — **spec written and handover sent as one note** (GLEIF first; 5 blocking
  requests). [spec](../../docs/specs/source-contract/spec.md).

## Not yet specified

- **Change and replay**: when a Source Contract's version changes, which
  silver rows are re-parsed, which assertions are re-published, and how
  that meets the Merge Stage's bounded rebuild. Sharper after research 02:
  a `lookup` that reads the newest snapshot makes a re-parse depend on when
  it runs — now settled for lookups by ticket 04 Q3 (as-of the filing date,
  else earliest after). Sharper after research 01:
  a Clean MDM dataset body is immutable per `source_code`, so a Source
  Contract version bump has no path today except a new `source_code` and
  re-binding every record — the versioning model needs a Codex proposal.
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
