# Decide the read and transform primitives and the custom-step signature

Type: grilling
Status: resolved (2026-09-21)
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
- **Q2 Primitive size (2026-09-21, agreed):** small primitives by default
  (`text`, `upper`, `starts_with`, `number` …, chained with `steps:`); a
  **named convention** (e.g. `value_with_footnotes`) is allowed only when it
  names a published format convention, is used by two or more sources or
  columns, has its own engine unit-test table, and has a one-line vocabulary
  entry showing the chain it replaces. One source's logic is a custom step
  in that source's folder (Q6), never a shared primitive.
  `owner_display_name` stays custom.
- **Q3 Lookup snapshot (2026-09-21, agreed):** `select: { as_of:
  filing_date, fallback: earliest_after }` — the copy captured on or before
  the filing date, else the earliest copy after it. Repeatable because bronze
  only gains later-dated captures; keeps coverage for filings older than
  every capture. The lookup names its target by artifact family, never a
  path; never fetches; every row records the sha256 of the copy used.
  Changing from today's `newest` alters some Form 3/4/5 rows — the
  prototype's equivalence test must list them as expected differences.
  Assumption to verify in the prototype: the bronze path date is the
  capture date.
- **Q4 Custom steps (2026-09-21, agreed):** exactly two shapes — a
  **value step** (named inputs → one value; e.g. `owner_display_name@1`) and
  a **table reader** (Bronze Artifact → rows; e.g. a DEF 14A table). Rules:
  inputs named in the contract; output checked against the declared silver
  column or table; no network, no file writes, deterministic (the runner
  calls twice on fixtures and compares); imports listed (`requires:`) and
  checked by an architecture test; versioned `@n`, old versions kept for
  replay; a step may `reject(reason)` a record (counted, gated in ticket 05),
  any other exception stops the run naming step, version and record. The
  author may add ordinary unit tests inside the source folder. Custom
  *checks* are ticket 05's.

## Answer

The `read` section's vocabulary is decided (Q0-Q4 above):
strict YAML 1.2 → canonical JSON with a JSON Schema; restricted dotted
paths over one canonical tree (XML `$` / `@name`); repeating groups only via
`each:`; one `primitive: {arguments}` call or a `steps:` chain per column
with explicit `default:`; small primitives plus rule-bound named
conventions (research 02's draft list: 16 primitives, `value_with_footnotes`
qualifies); cross-source `lookup` by artifact family, as-of the filing date
with earliest-after fallback; two custom-step shapes with six rules. Readers
by format: `xml`, `json` (incl. zipped streamed arrays), `csv`; anything the
readers cannot parse (HTML tables) is a table-reader custom step. The
Mastering Policy adopts the same authoring convention (Q2a, handover item 5).
