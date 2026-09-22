# Implement classification and the binding predicates in the Merge Stage

Type: task
Status: open
Blocked by: 02

## Question

Nothing to decide once 01 and 02 land. Implement the policy runtime inside the
**existing** Merge Stage and assessment transaction. Do not build a second
merger, and do not add a source-specific matcher.

- Evaluate the policy's named, versioned primitives: classification per source
  record, candidate predicates, field rules.
- Replace the blanket refusal (`store.py:162`, `merge.py:303`) with the
  implemented predicates, so an unimplemented or unapproved rule is still
  refused, by name, with its reason.
- Keep null, clear and retract semantics, provenance per value, and Q13's
  pre-commit assessment for every proposed binding.
- TDD at the policy and transaction seams, then real PostgreSQL 16.

Proves: reordered and duplicate input, stale assessment rejection, lost
acknowledgement, retained field conflicts, reversal of an incorrect merge, and
a stable surviving ID.
