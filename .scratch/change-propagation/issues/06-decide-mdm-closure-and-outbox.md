# Decide MDM affected-key closure and publication outbox

Type: grilling
Status: open
Blocked by: 02, 04, 05

## Question

How does a completed silver publication select and resolve only the affected
company, adviser, person, security, fund, audit-firm, and relationship work
while preserving matching and survivorship correctness?

Decide domain-content hashes for every source type, bounded candidate-neighbor
expansion, order dependencies among entity types, relationship derivation,
retirement/merge/supersession/quarantine propagation, retry/resume boundaries,
and the periodic full-universe reconciliation backstop. Specify how successful
MDM commits transactionally enqueue the existing publication outbox so every
entity or relationship mutation—including close and provenance-only changes—
becomes exportable exactly once by idempotent drain.
