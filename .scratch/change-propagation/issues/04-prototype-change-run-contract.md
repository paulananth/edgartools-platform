# Prototype the Change Propagation Run contract

Type: prototype
Status: open
Blocked by: 01, 02, 03

## Question

What concrete, reviewable contract should represent a Change Propagation Run
and its stage-local work?

Prototype versioned example schemas for the immutable run manifest, change
envelope, expected-producer set, stage manifest, outcome ledger, replay/repair
linkage, and publication identity. Each change must be able to carry its source
identity/version/hash, business key, `UPSERT`/`RETIRE`/`SCOPE_COMPLETE`
operation, domain-content hash, causal run, and Affected-Key Closure without
embedding secrets or mutable infrastructure identifiers.

Exercise the prototype with at least: duplicate no-op delivery, corrected
content under a repair attestation, replacement-scope disappearance, a partial
producer retry, and an out-of-order older event. Link the resulting artifact
from the resolution rather than pasting it into this ticket.
