---
name: data-governance
description: Decide what a steward may treat as governed data, including the path from a data source through the steps that can fail to the domain and data product. Use for data governance, lineage, a target's graph, or whether a step belongs on that graph.
---

# Data governance

Governed data is evidence a steward can trust, not every file a run touched.

Read [LINEAGE.md](LINEAGE.md) before drawing, publishing, or judging lineage.
How OpenMetadata stores that picture stays in the
[openmetadata](../openmetadata/SKILL.md) skill. Subject domains and glossary
words stay in the [data-catalog](../data-catalog/SKILL.md) skill.

## What is governed

A governed path starts at a data source and ends at a data product:

1. Source. A captured feed or a named reference file the target reads. Not a
   file the same target wrote on the way.
2. Control. One pinned run file a step reads, built from the feeds its
   contract requires.
3. Steps that can fail, with their declared checks and the data quality they
   run. Plumbing steps are not drawn.
4. Trusted outputs: the prepared dataset, mastered tables, Silver tables and
   the change journal.
5. Domain, the subject of an output, and the data product made of domains.

The catalog's service layer mixes pipeline services with the database service,
so it is never this picture. Draw the whole path from the rules.

## Completion

The lineage picture matches [LINEAGE.md](LINEAGE.md), and a readback of the
live catalog shows the same edges. An HTTP success is not that match.
When the operator asks to see the shipped lineage UI, observe it with
Playwright and compare the nodes to this contract. Every other catalog step
stays on the API and CLI.
