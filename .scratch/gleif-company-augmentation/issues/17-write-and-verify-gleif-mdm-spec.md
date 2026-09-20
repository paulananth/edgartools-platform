# Write and verify the GLEIF MDM enrichment specification

Type: task
Status: resolved
Blocked by: none — operator decided 2026-09-19 ("write it now") that the consumer spec is written against the foundation spec as it stands, Open items and pending Clean MDM proposals included.

## Outcome

Create `spec.md` from the resolved map and decision record after the parent
Shared enrichment foundation specification is fixed. It must specify the first
Company consumer's use of shared evidence capture, cadence, source authority,
schemas, identity/review contract, temporal behavior, replay, observability,
security, rollout, and test/release gates without duplicating the source-wide
foundation contract or implementing either specification.

## Done when

The specification contains no unresolved design placeholders, cites every
material evidence artifact, and a documentation review confirms it matches the
map and repository architecture.

## Answer

Written 2026-09-19: [`spec.md`](../spec.md). It is the consumer *contract*
that Clean MDM's own `company-completion.md` delivery gate (Codex/Grok-owned)
must satisfy — not a competing implementation plan. Every section is filled
from the map's sixteen resolved tickets; the schema section binds those
evidence-level decisions to Clean MDM's `mdm_v2` tables per the
legacy-decommission directive; a Dependencies table names what still gates
release (per-family checkpoint key and pre-merge candidate table, both
proposed to Clean MDM; the foundation's Open items).

"Done when" status: no unresolved design placeholders (open items are named
dependencies, not placeholders); every material evidence artifact cited;
the documentation-review step — confirming it matches the map and the
repository architecture — has **not** yet been run and is the remaining
verification.

**Documentation review run 2026-09-19** (same session, later). Checked
every cited file exists; cohort counts (308/103/87/502) against ticket 02;
consolidation figures against ticket 04; the five jurisdiction conflicts
against ticket 03; the six GLEIF relationship type names against
`research/10-gleif-relationship-routing.md`; GLEIF field names against
`research/03-accepted-level1-records.jsonl`; the OpenCorporates-is-a-GLEIF-file
claim against `research/11-...`; dataset codes against Clean MDM's
`source-evidence.md`. Two corrections applied: the consolidation figures
were coarse (now the exact 23/7/255/23 breakdown), and the `gleif.*`
dataset codes are *proposed* in Clean MDM's spec, not installed. The
foundation spec's over-specified continuity-proof home was found in the
same pass and is now marked *Open* there. Ticket 17 "done when" is
satisfied.
