---
name: data-governance
description: Decide what a steward may trust as governed evidence and which source-to-output links belong on its lineage path, independently of catalog mechanics. Use for data governance, lineage, a target's graph, or whether a step belongs on that graph.
---

# Data governance

Governed data is evidence a steward can trust, not every file a run touched.

Read [LINEAGE.md](LINEAGE.md) before drawing, publishing, or judging lineage.
This skill decides what evidence and processing path a steward may trust. It
does not define business meaning, choose a catalog presentation, or describe a
destination's publication mechanics.

## Decisions, evidence and handoffs

Use the configured source contract, processing steps and checks to decide
which evidence enters a governed path, which processing steps can fail, and
which outputs are trusted. Use run evidence to distinguish a configured path
from processing that actually completed. A file a target writes while running
is not a new source.

| Decision or artifact | Owner | Handoff |
|---|---|---|
| Which source evidence, material controls, failable steps, checks and trusted outputs form the path | Data Governance | This skill's [LINEAGE.md](LINEAGE.md) is the neutral lineage contract. |
| Business words, subject domain, glossary meaning and catalog presentation | [Data Catalog](../data-catalog/SKILL.md) | Governance supplies the supported outputs and their evidence-backed path; the catalog projects their meaning. |
| Class, kind, identifiers, relationships and store placement | [Data Modeling](../data-modeling/SKILL.md) | Governance uses those decisions when identifying output meaning; it does not redefine them. |
| Destination mapping, publication and native readback | The selected destination's skill, such as [OpenMetadata](../openmetadata/SKILL.md) | Governance supplies the neutral path; the destination owns its mechanics and reports what its readback confirms. |
| Running, diagnosing or recovering processing | [Data Operations](../data-operations/SKILL.md) | Governance identifies the configured step and evidence needed; Operations owns execution and recovery. |

The inputs are configured source contracts and reads, step order and declared
checks, control-file dependencies, and available run evidence. The output is
the evidence-backed lineage contract: source and control inputs, failable
steps with their checks, trusted outputs, and any supported domain or product
links. State the covered scope and name any coverage or evidence gaps; leave an
unsupported edge unclaimed. Keep configured intent distinct from observed
completion.

## Shared rules

This contract describes supported lineage; it grants no permission to access a
provider, read a secret, change configuration, run processing, approve or
activate a rule, or publish a destination. Use [Data Platform hard stops](../data-platform/SKILL.md#hard-stops)
for provider access, credentials and activation; [Data Onboarding hard stops](../data-onboarding/SKILL.md#hard-stops)
for configuration-only work and public data; and [Data Operations](../data-operations/SKILL.md)
for local proof and run evidence. Create or run only a test scenario the task
explicitly authorizes.

## Completion

The proposed lineage matches [LINEAGE.md](LINEAGE.md). A destination's native
readback determines whether the published edges match what it stores; a
successful write alone does not establish that. Destination-specific checking
and presentation belong to its skill. Report uncovered scope and unavailable
run or readback evidence as gaps, not as a completed path. When the operator
asks to see shipped lineage UI, observe it with Playwright and compare the
nodes to this contract.
