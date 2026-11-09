---
name: data-governance
description: Decide what a steward may treat as governed data, including source evidence, material controls, trusted outputs, and lineage. Use for data governance, lineage, a target's graph, or whether a captured step belongs on that graph.
---

# Data governance

Governed data is evidence a steward can trust, not every file a run touched.

Read [LINEAGE.md](LINEAGE.md) before drawing, publishing, or judging lineage.
How OpenMetadata stores that picture stays in the
[openmetadata](../openmetadata/SKILL.md) skill. Subject domains and glossary
words stay in the [data-catalog](../data-catalog/SKILL.md) skill.

## What is governed

A governed path has three parts:

1. Evidence. An actual source the target reads: a captured feed or a named
   reference file. Not a file the same target wrote on the way.
2. Control. One node for a pinned run file a step reads, when that file is
   material. Its inbounds are the actual sources that build it.
3. Trusted output. A configured mastered or prepared table, and the change
   journal when the target records processed files.

Bookkeeping steps stay tasks on that one pipeline. They are not extra
pipelines and not extra graph nodes. A sibling target stays its own pipeline.

## Completion

The lineage picture matches [LINEAGE.md](LINEAGE.md), and a readback of the
live catalog shows the same edges. An HTTP success is not that match.
When the operator asks to see the shipped lineage UI, observe it with
Playwright and compare the nodes to this contract. Every other catalog step
stays on the API and CLI.
