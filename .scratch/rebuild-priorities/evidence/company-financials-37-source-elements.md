# Company facts: complete original-source element inventory

Status: draft findings. Original-source inventory completed 2026-10-16 14:46 ET. This discovers the source's elements; it does not approve routing, a production reader or analytical selection rules.

## What is in the source

The inventory read all 368 captured documents, checked each original receipt, and visited every JSON field and list item without sampling. It took 94.03 seconds. The capture contains **16 scalar data elements**, represented by **23 structural paths**, and **5,134,979 financial observations**. Taxonomy, concept and unit are data stored as object keys; they are not thousands of separate columns.

```text
document
  cik, entityName
  facts[taxonomy][concept]
    label, description
    units[unit][]
      start, end, val, accn, fy, fp, form, filed, frame
```

The 500-entry capture ledger also records 132 no-facts responses. Among the 368 captured documents, 329 contain financial facts, 38 contain a Company header with an empty name and no facts, and one is an empty document. The converted Company table held only the 329 fact-bearing Companies; it did not inventory the 38 additional headers.

## All 16 data elements

Counts are over original captured JSON, before the Parquet conversion. “Absent” differs from an explicitly present null.

| Part | Element | Meaning | Presence and original shape |
|---|---|---|---|
| Company header | `cik` | Source Company identifier, used for lookup of its existing MDM Company | 367 documents: 262 whole-number tokens, 105 text tokens; absent in the empty document |
| Company header | `entityName` | Source-supplied header name | 367 documents; 38 empty strings; absent in the empty document |
| Concept | `taxonomy` | Namespace taken from the first object-key level | 9 distinct keys; 1,057 occurrences across documents |
| Concept | `concept` | Reported concept key within its taxonomy | 8,418 distinct key strings; 139,643 occurrences; 8,495 taxonomy/concept pairs in the pinned concept catalog |
| Concept | `label` | Reported display label | Present in all 139,643 concept objects; 3,558 null and 1,496 empty |
| Concept | `description` | Reported definition text | Present in all 139,643 concept objects; 3,558 null and 1,496 empty |
| Unit | `unit` | Source unit key beneath the concept | 269 distinct keys; 140,594 occurrences across concept objects |
| Observation | `start` | Reported period start; absent for observations without a start | Present in 3,113,260 observations; absent in 2,021,719; source text |
| Observation | `end` | Reported period end or instant | Present and non-null in all 5,134,979 observations; source text |
| Observation | `val` | Original reported numeric value | All 5,134,979 observations: 4,811,345 integer tokens and 323,634 decimal/exponent tokens; no nulls |
| Observation | `accn` | Filing accession carrying the observation | Present and non-null in all observations; 17,252 distinct strings |
| Observation | `fy` | Filing's fiscal-year tag, not proof of the observation's period-end year | Present in all observations: 5,095,936 whole-number tokens and 39,043 nulls |
| Observation | `fp` | Filing's fiscal-period tag | Present in all observations: 39,043 nulls and 1,223 empty strings |
| Observation | `form` | Filing form label | Present and non-null in all observations; 44 distinct strings |
| Observation | `filed` | Reported filing date | Present and non-null in all observations; source text |
| Observation | `frame` | Source frame label where supplied | Present in 2,127,150 observations; absent in 3,007,829; source text |

The seven remaining structural paths are the root document, the facts map, taxonomy values, concept objects, units maps, unit arrays and observation objects. They contain the scalar elements above; they are not additional financial measures. No unexpected field path was found across the original documents.

## Complete financial-concept list

The 16 elements describe the JSON structure. The **8,495 taxonomy/concept pairs** describe the financial concepts actually found in this cohort. Their complete names, labels, definitions, Company coverage, observed end-year coverage, units and observation counts are in the private `all-concepts-private.csv` beside the findings. The public repository keeps counts and schema names only.

Concept key strings alone are not globally unique across taxonomies. The existing per-concept coverage report covers all 8,495 pairs and reconciles to every captured observation. That is captured coverage, not a claim that every concept supplies a comparable annual line item.

## Who determines the destination

**Data-profiling owns discovery, classification evidence and the proposed store. The operator approves those findings. Data-onboarding consumes the approved findings and implements the mappings, quality rules and table contracts.** It does not independently invent a new destination or repeat discovery.

- MDM masters business entities with identity and a lifecycle. Here, financial observations look up an existing Company by CIK; discovering a source header does not authorize creating or merging a Company.
- RDM governs approved reference code sets and their versions. Taxonomy, concept and unit dictionaries are reference/metadata candidates to assess; a key and label do not make them new MDM kinds.
- Silver keeps financial facts and events linked to their masters. Published RDM reference data can also have a silver representation, so business ownership and physical landing are separate questions.

The generic classifier's conflicting Company/reference and concept/master suggestions remain unapproved. The business definitions are in `CONTEXT.md`; routing must follow approved findings rather than the presence of a key alone. No time-model choice is needed to discover these source elements. Choosing the analytical version, annual mapping and final silver grain comes afterward.

## Integer width and numeric precision

The operator requires **BIGINT / 64-bit long for integer fields and counters**, including fiscal-year fields. The existing profiling derivative's `fy` physical type is not a contract for the new silver table. Source identifiers supplied as text keep their identifier semantics; the integer-width rule is not an instruction to cast identifiers blindly.

One original `val` integer exceeds both signed and unsigned 64-bit integer ranges and changes under the derivative's DOUBLE conversion. Preserve that original exactly and flag the representability issue for tested reader handling; do not truncate, wrap or convert through floating point. Fractional financial values also need an exact-number policy in the approved reader/table contract. This inventory makes no numeric coercion or schema change.

## Evidence and limits

Private evidence under the permitted `company-facts/profile-ticket37-20261016/` folder:

- `original-source-elements.json`: every canonical path, source type, occurrence/document counts, nulls, empty values, missing fields, distinct scalar counts and integer overflow counts, plus all input receipts.
- `inventory-original-elements37.py`: exact executed discovery code, pinned by its checksum.
- `all-concepts-private.csv`: all 8,495 concept definitions joined to measured coverage.
- `source-elements-evidence.json`: artifact and script checksums; original draft findings remain unchanged and unapproved.
- The earlier raw receipt authentication and private precision-case trace remain alongside them.

This is a complete original-source element inventory alongside the earlier generic profile of the converted tables. It is not a claim that the generic profiler directly read the original gzip files, that source/target reading is qualified, or that MDM Company lookup coverage has been tested. No provider request, source activation, catalog publication, production write or matching-rule change occurred.
