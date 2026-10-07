# Data modeling requirements

The boundary of the data-modeling skill. Decided from `CONTEXT.md`, `KINDS`
and `PROFILE_KINDS` (`edgar_warehouse/mdm/clean/evidence.py`), the kinds'
Identifier Contracts (`rules/merge/kinds/`), the relationship types
(`rules/merge/relationships.yaml`), and the approved specs
(`docs/specs/rdm/spec.md`, `docs/specs/agent-context/spec.md`,
`docs/specs/profiling/`). First written by Grok (PR #839); handed to Claude by
the operator on 2026-10-07 ("I am handing it to you"), after a review found
it out of date and without a method for reference data.

## Scope

Data modeling decides where one part of a data set sits before anyone writes
a contract or starts a load, and reviews the model itself. In scope:

- **Class:** master data, reference data, relationship, transaction data or
  metadata, from data-profiling's approved findings; the skill does not
  measure the files again.
- **Master parts:** which kind in `KINDS`; a profile hangs on a kind and is
  never a kind.
- **Identity and cross-reference:** identity only from the namespaces a kind's
  Identifier Contract declares; every other identifier is a cross-reference,
  lookup only; an id made from a name only where no id exists.
- **Reference parts:** the code set, and where each field of a code goes
  (label, definition, synonym, parent, crosswalk with its match type, an
  outside standard), plus the usage and hints agents read.
- **Relationships:** the type, existing or inverse types first, the ends'
  kinds and profiles, capacities, hierarchy rules, dates, and whether it is
  onboarded with its masters.
- **Transaction parts:** the silver spec data-profiling wrote (grain, key,
  links to masters, time columns, load mode), as advice.
- **Time:** business time and recorded time kept apart for every part.
- **Reviewing the model:** overlapping or unnoted inverse types, names that
  hide their contents, reference data outside RDM, crosswalks to code sets RDM
  does not hold.

Out of scope: profiling the bytes; writing `source.yaml`, `quality.yaml`, a
configured `read:` contract, or a code set version; approving findings or
versions; switching a rule on. Those belong to data-profiling,
data-onboarding, data-quality, data-platform and refining-rules.

## Use when

The operator asks what a part is in the model, which kind or code set a
column belongs to, whether an identifier may join records, how a code list or
a relationship should be modeled, or for a review of the model. Use it after
approved findings exist, or to say that they do not.

## Refusals

- Do not approve findings or versions, and do not record words the operator
  did not say.
- Do not guess a class, a key, a link or a meaning; an unknown stays unknown,
  with the failing tests named.
- Do not add a kind, an identity namespace, or a second type for one fact:
  each is an operator ruling.
- Do not treat a cross-reference as identity, or similar names as one entity.
- Do not write rules, contracts, quality files or code set versions.
- Do not request anything from a provider's live service.

## Settled since the first version

- The RDM spec is approved (2026-10-05, PR #825) and built: the `rdm`
  database (PR #845), the policy's pin of its reference data (ticket 02).
- `edgar-warehouse context <code set>` reads `rdm.code_context` (PR #847);
  `edgar-warehouse rdm list` and `rdm describe` give a code set's meaning,
  version, usage and hints.
- Name-based matching is on main (PR #838): an id made from a name, a
  cross-reference, only where no id exists.

## Open questions

1. `silver.table_context` is specified but not built (ticket 06); until then
   the silver spec is read from the findings.
2. The review of 2026-10-07 found two pairs of overlapping parent types and
   unnoted inverse fund types (the skill's Examples): rulings for the operator.
