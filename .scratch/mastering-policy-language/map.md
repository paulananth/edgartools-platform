# Mastering Policy Language

Label: `wayfinder:map`

## Destination

A **specification of the rule language** carried by `mdm_v2.policy.body`:
what a policy document declares, per identity kind and per source, for
**classification** (record → kind), **Source Record Binding and Identity
Consolidation** (sameness), and **Field Survivorship and projection**
(values and the final field set) — plus how a policy version is authored,
calibrated, activated, and replayed. Code keeps only the interpreter and a
fixed, versioned vocabulary of primitives. Every rule the platform has so
far written by hand (Company/GLEIF, Person C-J and Tiers A–D, the 99% and
99.9% bars) must be expressible in it. Handed to Codex as a proposal
against their `mdm_v2.policy` table; planning only, no code, no edit to
any Clean MDM file.

## Notes

- **Operator's idea (2026-09-20)**: "instead of hard coding all of these
  rules for de duplication and merging can we create a configuration table
  for each entity for each source … it has to be generic for any entity
  and a source … 1) de duplication rules, 2) merge rules including priority
  of sources and which fields will be in the final entity."
- **Clean MDM already has the table**: `mdm_v2.policy (digest, body jsonb)`
  (`edgar_warehouse/mdm/migrations/023_clean_mdm.sql:10-13`); every batch
  pins a digest and the Merge Stage loads it (`clean/merge.py:179-184`),
  refusing any body whose `automatic_rules` is non-empty (accepted Q16).
  The Company body is a Python dict, `clean/company_source.py:62-72`:
  `version`, `automatic_rules: []`, `required_consumers`, `fields` keyed
  by kind then field (`sources`, `allow_unknown_effective`). So the table,
  the digest, and per-field survivorship exist; the gaps are (1) no schema
  for a declarative rule, (2) authored in code, (3) nothing for
  classification, binding tiers, or thresholds.
- **Legacy** had `mdm_match_threshold (entity_type, match_method,
  auto_merge_min, review_min)` and normalization-rule seeds
  (`migrations/002_seed_data.sql:59-64`) — a config table that is being
  decommissioned with legacy MDM. Evidence of the need, not a design.
- **Glossary line the language must keep** (`CONTEXT.md`): `Merge Stage`
  avoids "identity consolidation by field priority"; `Field Survivorship`
  avoids "source rank as permission to merge identities". Source priority
  is never an input to a sameness rule.
- **Inputs the language must express**: Company consumer contract
  (`.scratch/gleif-company-augmentation/spec.md`); Person tickets 02
  (Tiers A–D, cross-reference ids) and 03 (rule C-J) in
  `.scratch/person-consumer-contract/`; Clean MDM accepted Q1–Q16
  (`docs/specs/clean-mdm/merge-stage.md`), which this map does not reopen —
  it gives them a data shape.
- Skills: `/grilling` (operator preference: **one question at a time**),
  `/domain-modeling`, `/research` (primary sources, `path:line`), `/wait-what`.
- Standing rules: never commit to `main`; Codex/Grok files read-only;
  disagreements via `.scratch/handover/`.

## Decisions so far

- Destination (grilled 2026-09-20, Q1): option (a) — the rule-language
  spec, not an operator UI, not a go/no-go decision alone.
- Data/code boundary (Q2, operator agreed by proceeding): **structure and
  parameters in data, primitives in code** — the document declares steps,
  order, verdicts, thresholds, token lists, field names, source ranks;
  code provides a fixed vocabulary of named, versioned primitives. New
  source or threshold = data change; new kind of test = code change.
- Rule families (Q3, "agreed"): **all three** — Classification, Binding &
  Consolidation, Survivorship & Projection. Relationships stay in Clean
  MDM's own relationship table, outside this map.
- [Research: what is the right unit for one policy document](issues/01-research-policy-document-granularity.md)
  — **author one document per identity kind, classify per source, pin the
  composition**: the Merge Stage pins one digest for everything because a
  batch's closure crosses kinds through relationships and re-projects
  every reachable identity under it (a body missing a kind silently
  projects zero fields); per-(kind, source) dies on survivorship (source
  rank is an ordered list inside a per-field rule); classification already
  runs per source before the policy loads (`adapters.py:58-68`), so C-J
  belongs with the dataset contract. Golden-record tools (Informatica,
  Reltio, Tamr) scope match per entity type and survivorship per
  attribute; none by (entity, source). Caveat for Codex: a Person edit
  re-hashes the composite digest stamped on Company fields — churn, not a
  fault. [research/01](research/01-policy-document-granularity.md).
- [Research: how a declared rule becomes active, and where its proof lives](issues/02-research-rule-activation-and-proof.md)
  — **option (a) with a hash pointer**: the proof sits next to the rule in
  the policy body (~923 bytes: n, correct, lower bound, cohort and file
  hashes, approver, when), the labelled sample stays outside as files named
  by SHA-256; **activation is per `(rule_id, rule_version, verdict)`**, which
  is what lets rule C-J's `person` arm go live while its `entity` arm stays
  review-only (ticket 03 gates 1–2). The bar is declared per `(kind,
  family)`. The Merge Stage check is a pure predicate recomputing the bound,
  replacing the truthiness refusal at `merge.py:183-184`. No new table, no
  status column, no new role — registration is already owner-only and
  `recovery.md:51,111` forbids a competing activation registry. Open for
  Codex: Q11 says one-sided 95%, research 18 measured one-sided 97.5%
  (n ≥ 268 vs 381 at a 99% bar). The check verifies arithmetic, not honesty
  — mitigated by attribution plus a CI re-scoring job.
  [research/02](research/02-rule-activation-and-proof.md).

## Not yet specified

- **Change and replay**: what a new policy version re-evaluates (bounded
  rebuild per `merge-stage.md`), and how a rule removal or a bar change is
  reversed. Sharper now that activation is arithmetic (research 02): the
  question left is which identities a re-registration must re-project.
- **Authoring surface**: where the kind documents are written (repo files
  registered by `store.register_policy`) and how the composition into one
  pinned body is built and validated before registration — including the
  provenance-churn caveat research 01 raised for Codex.
- **Projection**: how "which fields the final entity shows" is declared
  alongside survivorship, and which fields stay evidence-only. Waits on
  the Person map's own field/privacy ticket.
- **Migration of rules already written**: whether C-J, Tiers A–D and the
  GLEIF binding rules are restated in policy documents or referenced from
  their tickets — a question for after the prototype shows the shape.

## Out of scope

- Relationship publication rules (Clean MDM `domain-model.md` relationship
  table).
- Implementation, migrations, the interpreter itself — Codex/Grok's.
- Any edit to `.scratch/clean-mdm/`, `docs/specs/clean-mdm/`,
  `edgar_warehouse/mdm/clean/`.
- Reopening Clean MDM's accepted Q1–Q16.
- Legacy MDM's config tables in any form.
