# 07 Readers and custom parsing steps per feed

Type: task. Phase: B. Blocked by: 01b inventory, Codex retirement merged. Map: [map](../map.md). Plan: [plan](../plan.md).

## Checklist

- [ ] Feed list from 01b inventory (one part each, own branch and PR)
- [ ] Custody items (operator, 2026-10-05: "Custody items are from Form ADV Schedule D 5.K(3)"): the source of custody data is Form ADV Part 1A, Schedule D, Section 5.K.(3), the custodians that hold separately managed account assets. Read it as its own part of the ADV feed: one row per adviser filing and custodian, with the custodian's name, identifiers and amount held. Profile it with data-profiling first. It is expected to be a relationship (adviser to custodian, both masters) with an amount, not a free-standing "Custody" disclosure category.
