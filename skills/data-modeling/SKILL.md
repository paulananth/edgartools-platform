---
name: data-modeling
description: Decide where one profiled part of a data set sits in the model - its class, its master kind or code set, which identifiers decide identity and which are lookup only, how a code list becomes a code set (hierarchy, crosswalk, usage, hints), how a relationship is typed, and its time model - from approved profiling findings and the language the platform already has. Use when the operator asks what a part is in the model, which kind or code set a column belongs to, whether an identifier may join records, how a code list or relationship should be modeled, or to review the model itself.
---

# Data modeling

The boundary is [REQUIREMENTS.md](REQUIREMENTS.md). This skill decides
structure, with evidence and the existing language. It does not measure files
(data-profiling), write a contract (data-onboarding, refining-rules), write a
check (data-quality), or approve anything.

**Hand off when:**

- there are no approved findings (`approval.status: approved` in `findings.yaml`): data-profiling (`skills/data-profiling/SKILL.md`)
- the structure is accepted and the feed is new: data-onboarding (`skills/data-onboarding/SKILL.md`)
- a live feed's mapping or matching should change: refining-rules (`skills/refining-rules/SKILL.md`)
- a defect needs a check or a fix: data-quality (`skills/data-quality/SKILL.md`)

## Hard stops

| Never | Instead |
|---|---|
| Approve findings or a code set version, or write words the operator did not say | Ask one question, then wait |
| Guess a class, a key, a link or a meaning | Leave it unknown and name the failing tests from the findings |
| Add a kind, or treat a profile as a kind | A missing kind is an operator ruling |
| Join records on a cross-reference, or merge on similar names | Records join only through a kind's Identifier Contract or a matching rule the operator switched on |
| Name a new relationship type when an existing one, or its inverse, means the same | Use it, or ask the operator why a second type is needed |
| Write rules, contracts, quality files, or a code set version | Hand off; drafts in RDM go through data-profiling's RDM steps |
| Request anything from a provider's live service | Use the captured files and this repo |

## What the platform already says

Read these before deciding, and use their words:

- `CONTEXT.md`: the glossary (data classes, code set, crosswalk, reference
  and master data hierarchies, the kinds and their profiles).
- `edgar_warehouse/mdm/clean/evidence.py`: `KINDS` (the master kinds) and
  `PROFILE_KINDS` (a profile and the kinds it may hang on).
- `rules/merge/kinds/<kind>.yaml`, `identifiers`: the kind's Identifier
  Contract, the namespaces that decide identity.
- `rules/merge/relationships.yaml`: every relationship type, the kinds at its
  ends, capacities, profiles, and whether it is a hierarchy; their meanings are
  in `rules/context/definitions.yaml`.
- `docs/specs/rdm/spec.md` and `docs/specs/agent-context/spec.md`: how
  reference data and agent context are kept.

Ask what is already held, only for the question at hand:

```bash
edgar-warehouse context <kind> --search "<words>"      # a master already held
edgar-warehouse context <code set> --search "<words>"  # a code already held
edgar-warehouse rdm list                                 # every code set
edgar-warehouse rdm describe <code set>                  # its meaning, version, where used, hints
edgar-warehouse mdm counts                               # how many entities exist
```

## Decision rules

### 1. Class

Take the class from the approved findings, and check it against the glossary:

| Class | The part... | Lives in |
|---|---|---|
| Master data | describes things with their own identity and lifecycle; grows with the business | MDM, as a kind |
| Reference data | gives other values their meaning; small, near-constant, changed as a whole new version | RDM, as a code set |
| Relationship | links two masters, with a type, ends, and dates | MDM, with its masters |
| Transaction data | records events or facts about masters over time; only grows | silver |
| Metadata | describes the data itself (counts, files, runs) | bookkeeping, not modeled here |

A part that looks like two classes is usually two parts: a code list inside a
master file is reference data plus a master attribute that holds its codes.

### 2. A master part: its kind

- The kind is one of `KINDS`. A role a thing plays (an adviser, an auditor, a
  fund) is a profile on a kind (`PROFILE_KINDS`), never a kind.
- No kind fits: say why the part is master data, propose a name and a
  definition, and ask the operator. Stop.

### 3. Identity or cross-reference

- **Identity:** the namespaces the kind's Identifier Contract declares
  (`rules/merge/kinds/<kind>.yaml`, `identifiers`): two records with the same
  value are one entity. Records of two sources also join through the matching
  rules the operator switched on (`rules/merge/policy.yaml`,
  `automatic_rules`). Nothing else joins records.
- **Cross-reference:** every other identifier the part carries. It goes into
  the MDM cross-reference table through the contract (`cross_references`), for
  lookup only, and never joins records, even when two records share it.
- **No identifier at all:** an id made from the name (`name_id@1`) is the last
  resort, as a cross-reference too (data-profiling, "An id from a name").
- A new identity namespace changes how records merge: an operator ruling.

### 4. A reference part: its code set

- **One code set per list of codes with one meaning.** Codes of two meanings
  in one column (places and their types) are two code sets.
- **Check what exists first** (`rdm list`, `context <code set> --search`). A
  list that is already held gets a new version, never a second code set.
- **Each field of a code goes to exactly one place:**

  | The field is... | It becomes |
  |---|---|
  | what the code stands for, in a few words | the `label` |
  | what it stands for, in full | the `definition` |
  | another name for the same code | a `synonym` |
  | the code above it, itself a code of the same set | its `parent_code` (a reference hierarchy, with level names) |
  | a code of another list (a grouping, a standard's code) | a crosswalk row to that code set: `exact`, `close`, `broad` (the target is broader) or `narrow` |
  | a code of an outside standard RDM does not hold | a crosswalk row with `to_version: outside` |

- **Never make a grouping into parent codes when the grouping's values are not
  codes of this set:** the grouping values would become valid codes, and a
  check would accept them. Make the grouping its own small code set and link
  each code to it with a `broad` crosswalk row.
- **Write the semantic layer for agents:** `usage` (each store, object and
  field whose values are codes of this set, and how a value compares: `exact`
  or `upper_trimmed`) and `hints` (`meaning`, `use_when`, `avoid_when`,
  `example_question`), from evidence only.
- A field with no place stops the import: nothing is dropped silently.

### 5. A relationship: its type

- **Look for an existing type first,** in both directions: a type whose ends
  are swapped and whose meaning is the same is its inverse. Two types for one
  fact (one per source, or one per direction) make every reader ask both; name
  the existing one, or ask the operator why a second is needed.
- **Check the ends:** the kinds at each end must be the type's `from` and `to`;
  a profile at an end is `from_profile` or `to_profile`.
- **Capacity, not type:** the role a person holds in a link (director,
  officer, owner) is a capacity of one type, not a new type. Check the type's
  name still describes every capacity it holds.
- **A hierarchy** (parent chains): say whether cycles are invalid or reviewed,
  whether one parent at a time holds per scope, and whether an ultimate parent
  is derived.
- **Dates:** each period has `valid_from` and `valid_to`; say what each comes
  from (stated, first seen, last seen).
- **Onboarded together or separately:** the findings' `onboard` says which.

### 6. A transaction part: its silver table

From the findings' silver spec: the grain (one row per what), the key, the
links to masters (the source key and the MDM id, with the overlap measured),
the time columns, and the load mode. The spec is advice; this skill does not
build the table.

### 7. Time

Keep two times apart: **business time** (`--as-of`: when it was true) and
**recorded time** (`--as-at`: when the platform knew it). For every part, say
which columns carry each (the findings' `time.as_of` and `time.as_at`), and
for a transaction part also its `event_time` (when the event happened) and,
for a time series, its `series` (key, time column, step). Each code set
version has its own `valid_from`; publishing the next one closes its
`valid_to` at the new one's `valid_from`. A code's own dates are business
time.

## Workflow

1. **Name the part.** If the operator has not said which part, ask and stop.
2. **Read the approved findings** for it: `class`, `record_key`,
   `identifiers`, `relationships`, `hierarchies`, `silver`. Missing or not
   approved: hand off to data-profiling.
3. **Read what the platform already says** (above) and ask what is held.
4. **Decide with the rules above,** one part at a time. Mark every unknown,
   with the failing test that left it unknown.
5. **Write the decision in plain words:** class; kind, code set or silver
   table; identity and cross-references; for a code set, where each field
   goes, its usage and hints; for a relationship, the type, its ends, its
   capacity and its dates; the time columns.
6. **Ask at most one question** when the choice is the operator's: a new kind,
   a new identity namespace, a second type for one fact, or which of two
   fields is the identity. Give the recommendation. Do not continue in the
   same turn.
7. **Hand off** (the list above). Do not restate that skill's steps.

## Reviewing the model itself

Asked to review the model, check:

- **Overlapping types:** two relationship types with the same ends and the
  same meaning in `rules/context/definitions.yaml`.
- **Inverse types without a note:** two types for one fact in opposite
  directions, which the definitions do not say are inverses.
- **Names that need their definition:** a type whose capacities its name
  alone does not describe.
- **Reference data outside RDM:** code lists a kind's fields or a contract
  carry with no code set behind them.
- **Code sets that cannot be checked:** a crosswalk to a code set RDM does not
  hold.

Report each with its evidence and the decision it needs; rulings are the
operator's.

## Examples

Examples only; nothing above depends on them.

- **Identity:** the company kind's Identifier Contract declares `cik`
  (`rules/merge/kinds/company.yaml`); its records join GLEIF's through the
  matching rules switched on in the policy. An EIN mapped by a contract's
  `cross_references` would be a cross-reference, lookup only (no contract maps
  one today).
- **A grouping as a crosswalk:** the EDGAR place codes (`DE`, `X1`, `XX`)
  carry a `type` (US, CANADIAN, FOREIGN, UNKNOWN). Parent codes `US` and
  `FOREIGN` would make "FOREIGN" a valid state code, so `type` became its own
  code set, `sec-place-types`, with a `broad` crosswalk row from each place
  code; the ISO 3166 codes are `exact` rows to `iso-3166` (`outside`).
- **Inverse types:** `MANAGES_FUND` (Form ADV, adviser to fund) and
  `IS_FUND-MANAGED_BY` (GLEIF's term, fund to manager) state one fact in
  opposite directions.
- **Overlapping types:** `ACCOUNTING_PARENT` and `IS_DIRECTLY_CONSOLIDATED_BY`
  both name a direct accounting parent; `IS_ULTIMATELY_CONSOLIDATED_BY` and
  `REPORTED_ULTIMATE_PARENT` both name a stated ultimate parent.
- **A name that needs its definition:** `EMPLOYED_BY` also holds directors,
  and `CONTROLS` also holds owners. The definitions say so as capacities; the
  type names alone do not.
