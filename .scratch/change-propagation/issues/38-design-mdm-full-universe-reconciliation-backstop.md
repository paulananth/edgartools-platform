# 38 — Design the periodic MDM full-universe reconciliation backstop

**What to build:** A decision (not an implementation) for the periodic
pass that catches match/survivorship drift a bounded, 1-hop incremental
pass structurally cannot see — multi-hop ripple effects, near-miss
matches that only become visible once enough of the universe has been
re-scanned.

**Blocked by:** None — the *need* for this backstop is already decided
(Ticket 06); its internal design is not.

**Status:** ready-for-agent

## Question

What should the periodic full-universe reconciliation backstop actually
check, how often should it run, and how does it relate to the bounded,
1-hop candidate-neighbor expansion Ticket 06 decided for the incremental
path (Change Propagation Run → MDM resolution → 1-hop relationship-edge
re-check)?

Decide: what "drift" this backstop specifically looks for that the
incremental path wouldn't catch (multi-hop ripple? near-miss matches
below the incremental path's confidence threshold? both?); its cadence
and cost profile (compare against the existing `Identity Backstop Sweep`
naming precedent and cadence, a different subsystem but a close analog
worth checking before inventing a new cadence policy from scratch); how
findings get surfaced (auto-corrected, or routed through the existing
`stewardship.py` review queue — `MdmMatchReview`/`accept_review`/
`reject_review` — so a human stays in the loop for anything not
mechanically certain); and how this relates to the release-readiness
map's already-built periodic full-parity mechanism (`Relationship
Generation Snapshot`, `Per-Type Exact Relationship Parity` — a
point-in-time release-gate audit, not an ongoing incremental-correctness
backstop, but close enough in shape that this ticket should explicitly
say why it isn't the same thing before building something that
duplicates it).

## Notes

Surfaced while resolving [06 — Decide MDM affected-key closure and
publication outbox](06-decide-mdm-closure-and-outbox.md) — confirmed
twice now (once by `mdm-ahead-of-silver`'s own Ticket 04, once here) that
this backstop is a real, needed, and genuinely undesigned piece.
