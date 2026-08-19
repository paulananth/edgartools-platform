# Decide the Enforcement Mechanism for the Single-Path Rule

Type: `wayfinder:grilling` (HITL)

Status: open

Blocked by: [Enumerate Every Layer Transition and Its Current
Implementation(s)](01-enumerate-layer-transitions.md)

## Question

Given Ticket 01's findings about what shapes of violation actually occur
(or don't) in this codebase, decide what mechanism will catch a *new*
single-path violation before it ships — the shard-publish-fix incident
(CLAUDE.md's "Shard-publish promotion-race 5-whys" entry: two structurally
identical write paths silently diverged, nothing caught it until three real
prod failures) is the concrete failure to weigh every candidate against.

Candidates to weigh (not exhaustive):

- An automated architecture test (e.g. asserting a fixed set of "the one
  function for transition X" symbols exist and that other call sites
  delegate to them, not reimplement them).
- A static-analysis / lint rule (feasibility depends heavily on what shape
  Ticket 01's violations turn out to have — near-duplicate function bodies
  are checkable; behavioral divergence between differently-shaped
  implementations usually isn't).
- A code-review checklist item folded into the standing
  `/gof-refactor-reviewer` pass this repo already requires before
  non-trivial changes (per CLAUDE.md).
- A naming/registry convention (e.g. every layer transition's canonical
  implementation is registered in one place, making a second, unregistered
  implementation visibly wrong).
- Some combination of the above, scoped per transition rather than one
  mechanism for all.

Weigh mechanical enforceability against cost of building/maintaining it —
this repo's own precedent (release-readiness ticket 79's fingerprint
pattern, the shard-publish fix's test suite) favors cheap, targeted checks
over heavyweight infrastructure.
