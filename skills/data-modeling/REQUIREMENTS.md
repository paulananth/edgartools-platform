# Data modeling requirements

Decided from [the runtime account](../../docs/research/claude-codex-runtimes-2026-10-06.md), `CONTEXT.md`, `KINDS` in `edgar_warehouse/mdm/clean/evidence.py`, and the profiling specs. This note is the boundary. The skill that follows it does not add a second one.

## Scope

Data modeling decides where one part sits before anyone writes a contract or starts a load.

In scope:

- The part's class, using the five classes data-profiling already measures: master data, reference data, relationship, transaction data, or metadata. The tests and the evidence stay in [data-profiling](../data-profiling/SKILL.md). Modeling reads `findings.yaml`. It does not remeasure the files.
- For a master part, which kind in `KINDS` it is (`company`, `person`, `security`, `fund_structure`, `branch`, `government`, `international_organization`, `venue`). A profile (Adviser, Audit Firm, Fund) hangs on one of those kinds. It is not a kind. The words are in `CONTEXT.md`.
- Which identifiers are identity and which are cross-references. Data-onboarding already states the join rule: only `cik` and `lei` join two records into one. A cross-reference is lookup only and is never a join key (PR #835, `c170c534`).
- Whether a hierarchy is a reference hierarchy (codes inside one code set) or a master-data hierarchy (relationships between masters). That split is in [the RDM spec](../../docs/specs/rdm/spec.md) and in data-profiling's hierarchy findings.
- The relationship's type, the kinds at its ends, its role, and its scope, using `CONTEXT.md` and `rules/merge/relationships.yaml`. A type the policy does not name is a question, not a new name.
- For a transaction or reference part that MDM does not own, the silver table spec data-profiling already wrote. That spec is advice. Modeling does not build the table.

Out of scope: profiling the bytes, writing `source.yaml` or `quality.yaml`, writing a configured `read:` contract, combining readings, approving findings, and switching a rule on. Those belong to data-profiling, data-onboarding, data-quality, data-platform, and refining-rules.

## Use when

Use when the operator asks what a data set's parts are in the model, which kind or code set a column belongs to, whether an identifier may join records, or how a relationship should be named.

Use it after approved findings exist, or to stop and say that they do not. Do not use it to onboard a feed, to change a live rule, or to explain a measurement. Those are data-onboarding, refining-rules, and the data scientist skill.

## Refusals

- Do not approve findings, and do not record words the operator did not say.
- Do not guess a class, a key, or a link. An unknown stays unknown, with the failing tests named.
- Do not add a kind to `KINDS`. A kind that is not there is an operator ruling. Data-onboarding already says so.
- Do not treat a cross-reference as a join key.
- Do not merge two Companies, or a Company and a Person, because the names are alike. `CONTEXT.md` forbids that.
- Do not write a rules file or a configured read contract.
- Do not request anything from `sec.gov`. Use the captured files and this repo.
- Do not edit Claude-owned or Codex-owned paths.

## Open questions

1. [The RDM spec](../../docs/specs/rdm/spec.md) is still a draft for operator approval (profiling 01a, PR #825). A recommendation may follow that draft. RDM is not an approved store, and no command writes a code set.
2. `rdm.code_context` and `silver.table_context` are specified in [the agent-context spec](../../docs/specs/agent-context/spec.md) and are not what the context command reads yet. `edgar_warehouse/context.py` says they join the command in a later phase. Modeling reads the specs and the findings. It does not claim the command returns those views.
3. Claude's name-matching trial is on `claude/profiling-07b-name-matching` in another worktree. It is not on `main`. Similar names are not identity.
