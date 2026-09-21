# Decide the read and transform primitives and the custom-step signature

Type: grilling
Status: claimed
Blocked by: 02, 10

## Question

From ticket 02's inventory, decide the `read` section's vocabulary:

- readers by format (`xml`, `json`, `csv`, `html_table` …) and how paths and
  repeating groups are written;
- the transform primitives, their parameters and `name@version` rules;
- the custom-step signature (input: Bronze Artifact or rows; output: rows;
  no fetch, write or MDM call) and how a contract declares one;
- how `person_name@v2` (ticket 25 of the Person map) and the C-J lookup fit.

## Decisions in progress

- **Q0 File format (2026-09-21, agreed):** authored as **YAML, loaded as
  strict YAML 1.2** (every plain scalar is a string unless the schema types
  it — no `NO`→false, octal or date coercion), **validated against a
  published JSON Schema** (editor autocomplete; check 9's line-and-rule
  errors), **stored and digest-pinned as canonical JSON** like the Dataset
  Contract. Comments live in git only and never enter the digest. Rejected:
  JSON (unreadable at size, no comments), TOML (awkward nested lists),
  Python (the contract becomes code).
  *Research 10 note:* PyYAML (declared, `pyproject.toml:22`) parses YAML
  1.1; strict 1.2 needs ruamel.yaml, whose line/column API is unverified.
- **Q1 Paths, groups, transforms (2026-09-21, agreed — research 10's
  package):** (a) restricted dotted paths over one canonical tree (XML text
  in `$`, attributes in `@name`), schema-enforced, crossing a list is a
  located error, missing ≠ `null`; (b) repeating groups only via an explicit
  `each:` block (`where:` before `ordinal`, `from: document`, `join:` with
  `parts:`); (c) one `primitive: {arguments}` mapping or a `steps:` chain per
  column, explicit `default:` on every path read. Q0 consequence: strict
  YAML 1.2 via ruamel.yaml, not PyYAML.
- **Q2a One authoring convention for both languages (2026-09-21, agreed):**
  the Mastering Policy is authored like a Source Contract — strict YAML 1.2
  stored as canonical JSON, the same path rules, the same
  `primitive: {arguments}` call shape, a published JSON Schema. Rules do not
  change, only how they are written; the stored JSON can keep the shape
  Codex expects. Operator's merge needs (field priority, ordered match
  rules, "SEC is never overridden, only augmented") are already expressible
  in `docs/specs/mdm/policy-language.md` §6-8; SEC-first + null-never-
  overwrites gives augmentation, and rank precedes recency. A Steward
  override still outranks SEC (`merge-stage.md:140`) — kept. Goes to Codex
  with ticket 08, with a kind-level `default_sources` convenience so "SEC
  first" is one reviewable line.
