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
