# Encode Bronze evidence identity in the Decision Watermark

Type: grilling
Status: resolved
Blocked by: 01, 02

## Question

The map already locked that the Decision Watermark always includes Bronze
evidence identity (ADR 0006), not persist-only as Ticket 09 wrote. How should
that identity be represented on the contract?

Decide:

1. Content-addressed Bronze artifact hash, capture-manifest id, ledger
   revision id, or a composite.
2. Column(s) versus a single concatenated watermark string.
3. What fail-closed means when Bronze identity is missing on an otherwise
   aligned gold/graph publication.

Predecessor: [Decision Watermark and Agent-Grade gate](../../agent-decision-data-plane/issues/09-decision-watermark-agent-grade.md)
is closed; this ticket only encodes the 0006 consequence, it does not reopen
ingest.

## Comments

- Q1 (2026-09-10): required Bronze evidence identity is **content-addressed Bronze artifact hashes**. Capture-manifest id and ledger revision are not the identity; they may appear later as optional audit notes only.
- Q2 (2026-09-10): canonical watermark is **typed columns**. A concatenated display/token may exist for logs/pins but is not source of truth and is not required for agent-grade.
- Q3 (2026-09-10): required bronze column is **one digest of the ordered unique Bronze artifact hashes**. The full hash list stays in Bronze/ledger, not on the contract row. JSON/ARRAY of hashes is not the identity.
- Q4 (2026-09-10): missing or empty bronze digest ⇒ **not READY, not agent-grade**. Ready/agent-grade views return no tradeable payload. Gold, graph, Explore, and MDM keep running. Display/Agent View may show `not_ready` with reason `missing bronze digest`.

## Answer

Bronze evidence identity on the Decision Watermark is a **digest of the ordered unique content-addressed Bronze artifact hashes**, stored as a **typed column** among the other watermark components. Capture-manifest id and ledger revision are not the identity. A concatenated display token may exist for logs/pins but is not source of truth and is not required for agent-grade. JSON or ARRAY listings of hashes are not the identity; the full hash list stays in Bronze/ledger.

Missing or empty digest: the publication is **not READY** and reads are **not agent-grade**. Ready/agent-grade views return no tradeable payload. Gold refresh, graph, Explore, and MDM keep running. Display/Agent View may show `not_ready` / `missing bronze digest`. This replaces Ticket 09's persist-only bronze gate; it does not reopen ingest.

Does not decide who writes READY ([Decide who writes a READY Decision Contract publication](06-decide-publication-ready-writer.md)) or whether `Decision Contract Version` bumps off `"1"` ([Decide whether bronze digest requires a contract version bump](09-bronze-digest-contract-version-bump.md)).
